"""Privileged offline scoring; never imported by the provider worker."""
import hashlib
import json
import random
from collections import Counter, defaultdict
from .contract import certificate_to_legacy, digest, validate_output
from .prepare import read_rows, write
from .solve import derive
from ..evaluate import aggregate, edge_scores, evaluate_records, parse_delta, percentile, valid_answer
from ..schema import Question
from ..semantics import answer_equal


def context(dataset, selection):
    if hashlib.sha256((dataset/"manifest.json").read_bytes()).hexdigest() != selection["freeze"]["dataset_manifest_sha256"]:
        raise ValueError("Dataset manifest differs from selected frozen release")
    groups = [g for g in read_rows(dataset/"gold/groups.jsonl") if g["id"] in selection["group_ids"]]
    if set(g["id"] for g in groups) != set(selection["group_ids"]) or any(g["split"] != selection["split"] for g in groups):
        raise ValueError("Selection violates grouped split")
    gids = set(selection["group_ids"])
    singles, pairs = ([r for r in read_rows(dataset/f"gold/{p}.jsonl") if r["group_id"] in gids] for p in ("single", "paired"))
    expected = {(p, r["id"]) for p, rows in (("single", singles), ("paired", pairs)) for r in rows}
    if {(c["protocol"], c["id"]) for c in selection["cases"]} != expected or len(selection["cases"]) != len(expected):
        raise ValueError("Selection must include every expected case exactly once")
    return groups, singles, pairs


def oracle(dataset, selection):
    groups, singles, pairs = context(dataset, selection)
    variants = {v["id"]: v for g in groups for v in g["variants"]}
    gold = {("single", r["id"]): r for r in singles} | {("paired", r["id"]): r for r in pairs}
    result = {"bundle_sha256": selection["bundle_sha256"], "privileged_oracle": True, "mock_only": False,
              "requests": {}, "attempts": [], "reserved_usd": 0}
    for case in selection["cases"]:
        row = gold[(case["protocol"], case["id"])]
        vids = [row["variant_id"]] if case["protocol"] == "single" else list(row["variant_ids"])
        if case["reversed"]:
            vids.reverse()
        graphs = [variants[v]["graph"] for v in vids]
        value = derive(graphs, case["question"])
        validate_output(value, "direct", case["protocol"], case["question"])
        result["requests"][digest(["oracle", case["protocol"], case["id"]])] = {"status": "success", "output": value,
                                                                                   "graphs": graphs}
    return result


def legacy_prediction(case, value):
    row = {"id": case["id"], "protocol": case["protocol"]}
    if case["protocol"] == "single":
        row.update(answer=value["answer"], certificate=certificate_to_legacy(value["certificate"]))
    else:
        answers, certs = value["answers"][:], [certificate_to_legacy(c) for c in value["certificates"]]
        delta = value["delta"]
        if case["reversed"]:
            answers.reverse()
            certs.reverse()
            delta = {"added": delta["deleted"], "deleted": delta["added"]}
        row.update(answers=answers, certificates=certs, delta=delta)
    return row


def ratio(contributions, sample, name):
    if name == "answer_change_balanced_accuracy":
        a = ratio(contributions, sample, "answer_change_recall")
        b = ratio(contributions, sample, "answer_change_specificity")
        return (a+b)/2 if a is not None and b is not None else None
    n = sum(contributions[g].get(name, [0,0])[0] for g in sample)
    d = sum(contributions[g].get(name, [0,0])[1] for g in sample)
    return n/d if d else None


def balanced(metrics, contributions, replicates, seed):
    gids = sorted(contributions)
    rng = random.Random(seed)
    samples = [ratio(contributions, rng.choices(gids, k=len(gids)), "answer_change_balanced_accuracy") for _ in range(replicates)]
    samples = sorted(x for x in samples if x is not None)
    metrics["answer_change_balanced_accuracy"] = {"value": ratio(contributions, gids, "answer_change_balanced_accuracy"),
         "ci95": [percentile(samples,.025), percentile(samples,.975)] if samples else None,
         "bootstrap_defined_replicates": len(samples), "definition": "mean of gold-positive recall and gold-negative specificity, including abstentions"}


def resources(state, request_ids):
    attempts = [a for a in state["attempts"] if a["request_id"] in request_ids]
    usage = Counter()
    usage_calls = 0
    for a in attempts:
        if isinstance(a.get("usage"), dict):
            usage_calls += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if type(a["usage"].get(key)) is int:
                    usage[key] += a["usage"][key]
    costs = [a.get("provider_cost_usd") for a in attempts]
    latencies = [a["latency_seconds"] for a in attempts if a.get("latency_seconds") is not None]
    return {"http_attempts": len(attempts), "usage_reported_calls": usage_calls, "tokens_reported": dict(usage),
            "calls_with_unavailable_usage": len(attempts)-usage_calls,
            "sum_request_latency_seconds": sum(latencies), "latency_measured_calls": len(latencies),
            "mean_request_latency_seconds": sum(latencies)/len(latencies) if latencies else None,
            "provider_reported_cost_usd": sum(costs) if costs and all(x is not None for x in costs) else None,
            "known_partial_provider_cost_usd": sum(x for x in costs if x is not None),
            "calls_with_unknown_cost": sum(x is None for x in costs),
            "budget_reserved_usd": sum(a["reserved_usd"] for a in attempts),
            "cache_hits": sum(state["requests"].get(r,{}).get("cache_hit",False) for r in request_ids),
            "billing_note": "Reservations are configured bounds, not measured costs; no provider calls for oracle."}


def score(dataset, selection, state, baseline, protocol, replicates=1000, seed=20261027,
          filter_axis=None, filter_value=None, _breakdowns=True):
    if replicates < 1 or baseline not in ("direct", "parse", "oracle"):
        raise ValueError("Invalid report configuration")
    if state["bundle_sha256"] != selection["bundle_sha256"]:
        raise ValueError("Results do not belong to this frozen selection")
    if (baseline == "oracle") != bool(state.get("privileged_oracle")):
        raise ValueError("Oracle results must be explicitly privileged and separately labeled")
    groups, singles, pairs = context(dataset, selection)
    variants = {v["id"]: v for g in groups for v in g["variants"]}
    questions = {q["id"]: Question(**q) for g in groups for q in g["questions"]}
    if filter_axis == "task":
        singles = [r for r in singles if questions[r["question_id"]].task == filter_value]
        pairs = [r for r in pairs if questions[r["question_id"]].task == filter_value]
    elif filter_axis == "operation":
        def operation(vid):
            v = variants[vid]
            return v["edit"]["operation"] if v["edit"] else v["role"]
        if protocol == "single":
            singles = [r for r in singles if operation(r["variant_id"]) == filter_value]
            # A single-image operation slice does not define two complete independent answers.
            pairs = []
        else:
            pairs = [r for r in pairs if operation(r["variant_ids"][1]) == filter_value]
    active_gids = {r["group_id"] for r in (singles if protocol == "single" else pairs)}
    groups = [g for g in groups if g["id"] in active_gids]
    gold = {r["id"]: r for r in (singles if protocol == "single" else pairs)}
    cases = {c["id"]: c for c in selection["cases"] if c["protocol"] == protocol and c["id"] in gold}
    predictions, values, parsed = {}, {}, {}
    statuses, failures = Counter(), Counter()
    request_ids = {digest([baseline, protocol, ident]) for ident in cases}
    expected_ids = {digest([b,c["protocol"],c["id"]]) for b in (("oracle",) if baseline == "oracle" else ("direct","parse")) for c in selection["cases"]}
    if set(state["requests"]) - expected_ids:
        raise ValueError("Unknown result request IDs")
    for ident, case in cases.items():
        result = state["requests"].get(digest([baseline, protocol, ident]), {})
        status = result.get("status", "missing")
        statuses[status] += 1
        if status != "success":
            continue
        try:
            output = result["output"]
            validate_output(output, "parse" if baseline == "parse" else "direct", protocol, case["question"])
            if baseline == "parse":
                parsed[ident] = output["graphs"]
                try:
                    output = derive(output["graphs"], case["question"])
                except ValueError:
                    failures["solver_input_failure"] += 1
                    continue
            elif baseline == "oracle":
                parsed[ident] = result["graphs"]
            predictions[ident] = legacy_prediction(case, output)
            values[ident] = output
        except (ValueError, TypeError, KeyError):
            statuses["success"] -= 1
            statuses["invalid"] += 1
    contributions = {}
    for g in groups:
        sg, pg = [r for r in singles if r["group_id"] == g["id"]], [r for r in pairs if r["group_id"] == g["id"]]
        old = evaluate_records([g], sg, pg, predictions, protocol, 1, seed)
        contributions[g["id"]] = {k: [v.get("numerator",0),v["denominator"]] for k,v in old["metrics"].items()}
        if protocol == "paired":
            contributions[g["id"]]["legacy_joint_success"] = contributions[g["id"]]["joint_success"][:]
            contributions[g["id"]]["joint_success"] = [0,0]
    def add(gid, name, num, den=1):
        slot = contributions[gid].setdefault(name, [0.,0])
        slot[0] += float(num)
        slot[1] += den
    if protocol == "single":
        from ..semantics import valid_certificate
        from ..schema import Graph
        for row in singles:
            p = predictions.get(row["id"])
            if not p:
                continue
            correct = answer_equal(p["answer"], row["answer"])
            failures["answer_error_cause_unresolved" if baseline == "direct" else "derived_answer_error"] += not correct
            failures["evidence_invalid"] += not valid_certificate(
                Graph.parse(variants[row["variant_id"]]["graph"]), questions[row["question_id"]], p["answer"], p["certificate"])
    confusion = Counter({k:0 for k in ("tp","fp","tn","fn","missing_positive","missing_negative")})
    for row in pairs:
        gid, q = row["group_id"], questions[row["question_id"]]
        truth = not answer_equal(*row["answers"])
        if protocol == "paired":
            value = values.get(row["id"], {})
            change = value.get("answer_changed")
            p = predictions.get(row["id"], {})
            if value:
                ans = p["answers"]
                correct = all(answer_equal(a,b) for a,b in zip(ans,row["answers"]))
                delta_good = parse_delta(p["delta"], tuple(variants[row["variant_ids"][0]]["graph"]["nodes"])) == parse_delta(row["delta"], tuple(variants[row["variant_ids"][0]]["graph"]["nodes"]))
                # Use frozen evaluator's certificate semantics, accepting alternative evidence.
                from ..semantics import valid_certificate
                from ..schema import Graph
                evidence = all(valid_certificate(Graph.parse(variants[v]["graph"]), q, a, c)
                               for v,a,c in zip(row["variant_ids"],ans,p["certificates"]))
                failures["answer_error_cause_unresolved" if baseline == "direct" else "derived_answer_error"] += not correct
                failures["edge_delta_mismatch"] += not delta_good
                failures["evidence_invalid"] += not evidence
                add(gid, "joint_success", correct and delta_good and evidence and change == truth)
                add(gid, "change_answer_self_consistency", change == (not answer_equal(*ans)))
            else:
                add(gid, "joint_success", 0)
                add(gid, "change_answer_self_consistency", 0)
        else:
            lookup = {(r["variant_id"],r["question_id"]): predictions.get(r["id"],{}) for r in singles}
            ans = [lookup[(v,row["question_id"])].get("answer") for v in row["variant_ids"]]
            change = not answer_equal(*ans) if all(valid_answer(a,q.task) for a in ans) else None
        valid = type(change) is bool
        tp, fp, tn, fn = (valid and truth and change, valid and not truth and change,
                          valid and not truth and not change, valid and truth and not change)
        for k,v in (("tp",tp),("fp",fp),("tn",tn),("fn",fn),("missing_positive",not valid and truth),("missing_negative",not valid and not truth)):
            confusion[k] += int(v)
        add(gid,"answer_change_accuracy",valid and change == truth)
        add(gid,"answer_change_precision",tp,int(tp or fp))
        add(gid,"answer_change_recall",tp,int(truth))
        add(gid,"answer_change_specificity",tn,int(not truth))
        add(gid,"answer_change_f1",2*int(tp),2*int(tp)+int(fp)+int(fn)+int(not valid and truth))
        failures["change_prediction_incorrect_or_missing"] += not valid or change != truth
    parse_units = 0
    for ident, row in gold.items():
        gid = row["group_id"]
        result = state["requests"].get(digest([baseline, protocol, ident]), {})
        add(gid,"invalid_response_rate",result.get("status") == "invalid" or (result.get("status") == "success" and ident not in values and ident not in parsed))
        add(gid,"request_failure_rate",result.get("status", "missing") in ("missing","failed","uncertain","inflight"))
        if baseline not in ("parse","oracle"):
            continue
        vids = [row["variant_id"]] if protocol == "single" else list(row["variant_ids"])
        if cases[ident]["reversed"]:
            vids.reverse()
        extracted = parsed.get(ident, [None]*len(vids))
        for vid, pg in zip(vids, extracted):
            gg = variants[vid]["graph"]
            parse_units += 1
            exact = False
            if pg:
                pn, gn = set(pg["nodes"]), set(gg["nodes"])
                pe, ge = set(map(tuple,pg["edges"])), set(map(tuple,gg["edges"]))
                exact = pn == gn and pe == ge
                ns, es = edge_scores(pn,gn), edge_scores(pe,ge)
                failures["reconstruction_mismatch"] += not exact
            else:
                ns, es = (0,0,0), (0,0,0)
                failures["missing_or_invalid_parse"] += 1
            add(gid,"parse_graph_exact_accuracy",exact)
            for prefix, scores in (("parse_node",ns),("parse_edge",es)):
                for name, val in zip(("precision","recall","f1"),scores):
                    add(gid,f"{prefix}_{name}",val)
            add(gid,"parse_node_set_accuracy",bool(pg) and set(pg["nodes"]) == set(gg["nodes"]))
            if exact and ident not in values:
                failures["answer_unavailable_despite_exact_graph"] += 1
            elif exact:
                prediction = predictions[ident]
                answer = prediction["answer"] if protocol == "single" else prediction["answers"][row["variant_ids"].index(vid)]
                expected_answer = variants[vid]["answers"][row["question_id"]]
                failures["solving_failure_with_exact_graph"] += not answer_equal(answer,expected_answer)
    metrics = aggregate(contributions,replicates,seed)
    balanced(metrics,contributions,replicates,seed)
    breakdown = {}
    if _breakdowns:
        strata = defaultdict(dict)
        for g in groups:
            for axis,key in (("node_count",str(len(g["variants"][0]["graph"]["nodes"]))),
                             ("layout","circular"), ("base_style",str(g["variants"][0]["scene"]["style"]))):
                strata[f"{axis}:{key}"][g["id"]] = contributions[g["id"]]
        for key, subset in strata.items():
            breakdown[key] = aggregate(subset,replicates,seed)
            balanced(breakdown[key],subset,replicates,seed)
        for axis in ("task", "operation"):
            keys = set()
            for row in gold.values():
                if axis == "task":
                    keys.add(questions[row["question_id"]].task)
                else:
                    v = variants[row["variant_id"] if protocol == "single" else row["variant_ids"][1]]
                    keys.add(v["edit"]["operation"] if v["edit"] else v["role"])
            for key in sorted(keys):
                breakdown[f"{axis}:{key}"] = score(dataset,selection,state,baseline,protocol,replicates,seed,axis,key,False)["metrics"]
    return {"baseline":baseline,"protocol":protocol,"split":selection["split"],"groups":len(groups),
            "label":"PRIVILEGED ORACLE SANITY CHECK" if baseline == "oracle" else "MOCK ORCHESTRATION ONLY, NOT MODEL PERFORMANCE" if state.get("mock_only") else "REAL PROVIDER PREDICTIONS",
            "expected_cases":len(gold),"statuses":dict(statuses),"metrics":metrics,"answer_change_confusion":dict(confusion),
            "change_prediction":"explicit paired field" if protocol == "paired" else "derived from separate single-image answers",
            "parse_image_occurrences":parse_units,"failure_observations":dict(failures),"resources":resources(state,request_ids),
            "breakdown":breakdown,"breakdown_note":"Layout is circular only; base_style is a group property. Single operation slices omit paired/derived-change metrics because they do not contain both images. All paired joint metrics include explicit change.",
            "bootstrap":{"unit":"group","replicates":replicates,"seed":seed,"preliminary":True},
            "group_contributions":contributions,"bundle_sha256":selection["bundle_sha256"]}


def compare(a,b,replicates=1000,seed=20261027):
    if a["protocol"] != b["protocol"] or a["bundle_sha256"] != b["bundle_sha256"] or a["split"] != b["split"]:
        raise ValueError("Comparison must share track, inputs and split")
    ca, cb = a["group_contributions"], b["group_contributions"]
    if set(ca) != set(cb):
        raise ValueError("Paired comparison requires identical groups")
    gids = sorted(ca)
    rng = random.Random(seed)
    samples = [rng.choices(gids,k=len(gids)) for _ in range(replicates)]
    result = {}
    for name in sorted(set(a["metrics"]) & set(b["metrics"])):
        av,bv = ratio(ca,gids,name),ratio(cb,gids,name)
        diffs = [(ratio(ca,s,name),ratio(cb,s,name)) for s in samples]
        values = sorted(x-y for x,y in diffs if x is not None and y is not None)
        result[name] = {"a_minus_b":av-bv if av is not None and bv is not None else None,
                        "ci95":[percentile(values,.025),percentile(values,.975)] if values else None,
                        "defined_replicates":len(values)}
    return {"a":a["baseline"],"b":b["baseline"],"protocol":a["protocol"],"metrics":result,
            "method":"paired whole-group percentile bootstrap, identical resampled IDs for both baselines",
            "groups":len(gids),"replicates":replicates,"seed":seed,"preliminary":True,
            "mock_only": "MOCK" in a["label"] or "MOCK" in b["label"]}
