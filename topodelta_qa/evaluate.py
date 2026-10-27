"""Protocol-separated evaluation with strict answer types and group-bootstrap intervals."""
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dataset import read_jsonl
from .schema import Graph, Question
from .semantics import answer_equal, valid_certificate


def valid_answer(value: Any, task: str) -> bool:
    return (type(value) is int and value >= 0 or value == "unreachable" and type(value) is str) if task == "shortest_path" else type(value) is bool


def edge_scores(predicted: set, gold: set) -> tuple[float, float, float]:
    """Both empty => (1,1,1); any one empty => (0,0,0)."""
    if not predicted and not gold:
        return 1.0, 1.0, 1.0
    if not predicted or not gold:
        return 0.0, 0.0, 0.0
    tp = len(predicted & gold)
    precision, recall = tp / len(predicted), tp / len(gold)
    return precision, recall, 2 * precision * recall / (precision + recall) if tp else 0.0


def parse_delta(value: Any, nodes: tuple[str, ...]) -> set | None:
    if not isinstance(value, dict) or set(value) != {"added", "deleted"}:
        return None
    result = set()
    edge_sets = []
    for kind in ("added", "deleted"):
        edges = value[kind]
        if not isinstance(edges, list):
            return None
        unique = set()
        for edge in edges:
            if (not isinstance(edge, list) or len(edge) != 2 or any(type(n) is not str for n in edge)
                    or edge[0] == edge[1] or any(n not in nodes for n in edge)):
                return None
            pair = tuple(edge)
            if pair in unique:
                return None
            unique.add(pair)
            result.add((kind, *pair))
        edge_sets.append(unique)
    return None if edge_sets[0] & edge_sets[1] else result


def load_predictions(path: Path, protocol: str, expected_ids: set[str]) -> tuple[dict, dict]:
    predictions, errors = {}, {"malformed_lines": 0, "invalid_rows_without_id": 0}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors["malformed_lines"] += 1
            continue
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            errors["invalid_rows_without_id"] += 1
            continue
        if row.get("protocol") != protocol:
            raise ValueError(f"Line {number}: protocol must be {protocol}; protocols cannot be mixed")
        ident = row["id"]
        if ident not in expected_ids:
            raise ValueError(f"Line {number}: unknown prediction ID {ident}")
        if ident in predictions:
            raise ValueError(f"Line {number}: duplicate prediction ID {ident}")
        predictions[ident] = row
    return predictions, errors


def percentile(values: list[float], p: float) -> float:
    rank = (len(values) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] * (1 - rank + lo) + values[hi] * (rank - lo)


def aggregate(contributions: dict, replicates: int, seed: int) -> dict:
    """Resample whole groups; recompute each ratio with its original denominator."""
    names = sorted({name for group in contributions.values() for name in group})
    gids = sorted(contributions)
    result = {}
    bootstrap = {name: [] for name in names}
    rng = random.Random(seed)
    for _ in range(replicates):
        sample = rng.choices(gids, k=len(gids))
        for name in names:
            numerator = sum(contributions[g].get(name, (0, 0))[0] for g in sample)
            denominator = sum(contributions[g].get(name, (0, 0))[1] for g in sample)
            if denominator:
                bootstrap[name].append(numerator / denominator)
    for name in names:
        numerator = sum(group.get(name, (0, 0))[0] for group in contributions.values())
        denominator = sum(group.get(name, (0, 0))[1] for group in contributions.values())
        samples = sorted(bootstrap[name])
        result[name] = {"value": numerator / denominator if denominator else None,
                        "numerator": numerator, "denominator": denominator,
                        "ci95": [percentile(samples, 0.025), percentile(samples, 0.975)] if samples else None,
                        "bootstrap_defined_replicates": len(samples)}
    return result


def evaluate_records(groups: list[dict], single_gold: list[dict], paired_gold: list[dict], predictions: dict,
                     protocol: str, replicates: int = 1000, seed: int = 0) -> dict:
    if protocol not in ("single", "paired") or not groups or replicates < 1:
        raise ValueError("Invalid evaluation configuration")
    variants = {v["id"]: v for group in groups for v in group["variants"]}
    questions = {q["id"]: Question(**q) for group in groups for q in group["questions"]}
    contributions = {g["id"]: defaultdict(lambda: [0.0, 0]) for g in groups}
    missing, invalid_answers, invalid_certificates, invalid_deltas = 0, 0, 0, 0

    def add(group_id, name, value):
        contributions[group_id][name][0] += float(value)
        contributions[group_id][name][1] += 1

    def check(variant_id, qid, answer, cert):
        q = questions[qid]
        graph = Graph.parse(variants[variant_id]["graph"])
        is_valid = valid_answer(answer, q.task)
        correct = is_valid and answer_equal(answer, variants[variant_id]["answers"][qid])
        evidence = valid_certificate(graph, q, answer, cert)
        return is_valid, correct, evidence

    if protocol == "single":
        results = {}
        for row in single_gold:
            prediction = predictions.get(row["id"], {})
            missing += row["id"] not in predictions
            valid, correct, evidence = check(row["variant_id"], row["question_id"], prediction.get("answer"), prediction.get("certificate"))
            invalid_answers += not valid
            invalid_certificates += not evidence
            results[(row["variant_id"], row["question_id"])] = (valid, correct, evidence, prediction.get("answer"))
            for name, value in (("per_image_answer_accuracy", correct), ("certificate_validity", evidence), ("joint_success", correct and evidence)):
                add(row["group_id"], name, value)
        for row in paired_gold:
            first, second = [results[(v, row["question_id"])] for v in row["variant_ids"]]
            add(row["group_id"], f'{row["pair_kind"]}_pair_accuracy', first[1] and second[1])
            if row["pair_kind"] == "redraw":
                add(row["group_id"], "raw_redraw_agreement", first[0] and second[0] and answer_equal(first[3], second[3]))
    else:
        for row in paired_gold:
            prediction = predictions.get(row["id"], {})
            missing += row["id"] not in predictions
            answers, certs = prediction.get("answers"), prediction.get("certificates")
            answers = answers if isinstance(answers, list) and len(answers) == 2 else [None, None]
            certs = certs if isinstance(certs, list) and len(certs) == 2 else [None, None]
            checked = [check(v, row["question_id"], a, c) for v, a, c in zip(row["variant_ids"], answers, certs)]
            for valid, correct, evidence in checked:
                invalid_answers += not valid
                invalid_certificates += not evidence
                add(row["group_id"], "per_image_answer_accuracy", correct)
                add(row["group_id"], "certificate_validity", evidence)
            pair_correct = all(c[1] for c in checked)
            add(row["group_id"], f'{row["pair_kind"]}_pair_accuracy', pair_correct)
            if row["pair_kind"] == "redraw":
                add(row["group_id"], "raw_redraw_agreement", all(c[0] for c in checked) and answer_equal(*answers))
            nodes = Graph.parse(variants[row["variant_ids"][0]]["graph"]).nodes
            predicted_delta = parse_delta(prediction.get("delta"), nodes)
            gold_delta = parse_delta(row["delta"], nodes)
            invalid_deltas += predicted_delta is None
            p, r, f1 = edge_scores(predicted_delta, gold_delta) if predicted_delta is not None else (0.0, 0.0, 0.0)
            for name, value in (("edge_delta_precision", p), ("edge_delta_recall", r), ("edge_delta_f1", f1),
                                ("exact_delta_accuracy", predicted_delta == gold_delta),
                                ("joint_success", pair_correct and all(c[2] for c in checked) and predicted_delta == gold_delta)):
                add(row["group_id"], name, value)
    metrics = aggregate(contributions, replicates, seed)
    if protocol == "single":
        for name in ("edge_delta_precision", "edge_delta_recall", "edge_delta_f1", "exact_delta_accuracy"):
            metrics[name] = {"value": None, "ci95": None, "denominator": 0,
                             "reason": "Not measured by the single-image protocol"}
    return {"protocol": protocol, "groups": len(groups), "metrics": metrics,
            "handling": {"missing_predictions": missing, "invalid_or_missing_answers": invalid_answers,
                         "invalid_or_missing_certificates": invalid_certificates, "invalid_or_missing_deltas": invalid_deltas},
            "bootstrap": {"unit": "group", "method": "percentile", "replicates": replicates, "seed": seed},
            "joint_definition": "correct answer and valid certificate per image" if protocol == "single" else "both answers correct, both certificates valid, exact signed edge delta",
            "per_image_unit": "unique image-question case" if protocol == "single" else "image-question occurrence in an ordered pair; reference images repeat",
            "model_results": "User-supplied predictions only; no model inference performed by this tool"}


def evaluate_dataset(root: Path, path: Path, protocol: str, split: str = "all", replicates: int = 1000, seed: int = 0) -> dict:
    groups = [g for g in read_jsonl(root / "gold/groups.jsonl") if split == "all" or g["split"] == split]
    gids = {g["id"] for g in groups}
    single = [r for r in read_jsonl(root / "gold/single.jsonl") if r["group_id"] in gids]
    paired = [r for r in read_jsonl(root / "gold/paired.jsonl") if r["group_id"] in gids]
    all_ids = {r["id"] for r in read_jsonl(root / f"gold/{protocol}.jsonl")}
    predictions, errors = load_predictions(path, protocol, all_ids)
    result = evaluate_records(groups, single, paired, predictions, protocol, replicates, seed)
    result["handling"].update(errors)
    result["split"] = split
    result["predictions_outside_selected_split"] = len(set(predictions) - {r["id"] for r in (single if protocol == "single" else paired)})
    return result
