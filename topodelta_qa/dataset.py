import hashlib
import json
import math
import os
import platform
import random
import shutil
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import networkx as nx
import PIL
import yaml
from PIL import Image, ImageChops, ImageDraw, ImageFont, features

from . import __version__
from .identity import POLICY, public_id, read_key, remap_group
from .render import RENDERER, RenderError, png, positions, scene, unchanged_geometry, validate_scene, write_assets
from .schema import Config, Graph, GroupRecord, OPERATIONS, Question, TASKS
from .semantics import answer_equal, certificate, cross_split_duplicates, edit, isomorphic, solve, valid_certificate

INSTRUCTIONS = "An arrow points from its tail node to its arrowhead node. Labels are arbitrary identifiers. Only directed graph structure is relevant; no executable flowchart semantics apply."


def oid(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()[:24]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def split_schedule(config: Config) -> list[str]:
    train = int(config.groups * config.train_fraction)
    validation = int(config.groups * config.validation_fraction)
    result = ["train"] * train + ["validation"] * validation + ["test"] * (config.groups - train - validation)
    random.Random(config.seed).shuffle(result)
    return result


def extended_split_schedule(config: Config, prefix: list[dict]) -> list[str]:
    """Retain frozen group assignments and fill the final split quotas exactly."""
    counts = Counter(split_schedule(config))
    counts.subtract(g["split"] for g in prefix)
    if len(prefix) >= config.groups or any(n < 0 for n in counts.values()):
        raise ValueError("Target cannot preserve the frozen prefix and requested split quotas")
    remaining = [split for split in ("train", "validation", "test") for _ in range(counts[split])]
    random.Random(oid(config.seed, "extension-splits", len(prefix), config.groups)).shuffle(remaining)
    return [g["split"] for g in prefix] + remaining


def design_schedule(config: Config, name: str) -> list[int]:
    result = [i % 3 for i in range(config.groups)]
    random.Random(oid(config.seed, name)).shuffle(result)
    return result


def base_graph(rng: random.Random, config: Config) -> tuple[Graph, list[str], list[tuple[str, str]]]:
    n = rng.randint(config.min_nodes, config.max_nodes)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    nodes = sorted(rng.sample([a + b for a in alphabet for b in alphabet], n))
    order = rng.sample(nodes, n)
    polygon = order.copy()
    allowed = {tuple(sorted((order[i], order[(i + 1) % n]))) for i in range(n)}
    # Random ear clipping triangulates a convex polygon without extra dependencies.
    while len(polygon) > 3:
        i = rng.randrange(len(polygon))
        allowed.add(tuple(sorted((polygon[i - 1], polygon[(i + 1) % len(polygon)]))))
        polygon.pop(i)
    edges = []
    probability = rng.uniform(0.45, 0.85)
    for u, v in sorted(allowed):
        if rng.random() < probability:
            edges.append((u, v) if rng.random() < 0.5 else (v, u))
    return Graph(tuple(nodes), tuple(sorted(edges))), order, sorted(allowed)


def choose_edit(graph: Graph, allowed, operation: str, rng: random.Random):
    if operation == "addition":
        candidates = [(u, v) for u, v in allowed if (u, v) not in graph.edges and (v, u) not in graph.edges]
        if candidates:
            u, v = rng.choice(candidates)
            return edit(graph, operation, (u, v) if rng.random() < 0.5 else (v, u))
    elif graph.edges:
        return edit(graph, operation, rng.choice(graph.edges))
    raise ValueError("no_edit_operand")


def choose_questions(graph: Graph, changed: Graph, tasks, rng: random.Random, group_id: str) -> list[Question]:
    pools = {}
    for task in tasks:
        pools[task] = {True: [], False: []}
        for u in graph.nodes:
            for v in graph.nodes:
                if u == v:
                    continue
                q = Question("candidate", task, u, v)
                relevant = not answer_equal(solve(graph, q), solve(changed, q))
                pools[task][relevant].append((u, v))
    choices = [(a, b) for a, b in (tasks, tasks[::-1]) if pools[a][True] and pools[b][False]]
    if not choices:
        raise ValueError("no_mixed_relevance_questions")
    relevant_task, irrelevant_task = rng.choice(choices)
    chosen = [(relevant_task, rng.choice(pools[relevant_task][True])),
              (irrelevant_task, rng.choice(pools[irrelevant_task][False]))]
    rng.shuffle(chosen)
    return [Question(oid(group_id, "question", i), task, *uv) for i, (task, uv) in enumerate(chosen)]


def propose(config: Config, attempt: int, accepted: int, split: str) -> GroupRecord:
    seed = int(oid(config.seed, attempt), 16)
    rng = random.Random(seed)
    graph, order, allowed = base_graph(rng, config)
    operation_index = design_schedule(config, "operations")[accepted]
    operation_a, operation_b = OPERATIONS[operation_index], OPERATIONS[(operation_index + 1) % 3]
    graph_a, delta_a = choose_edit(graph, allowed, operation_a, rng)
    graph_b, delta_b = choose_edit(graph, allowed, operation_b, rng)
    angle = rng.uniform(0, math.tau)
    points = positions(order, angle)
    style = rng.randrange(3)
    original = scene(graph, points, style)
    redraw = scene(graph, positions(order, angle + rng.uniform(0.35, 0.8)), (style + 1) % 3)
    drawings = [original, redraw, scene(graph_a, points, style), scene(graph_b, points, style)]
    graphs = [graph, graph, graph_a, graph_b]
    for g, drawing in zip(graphs, drawings):
        validate_scene(g, drawing)
    group_id = oid(config.seed, "group", attempt)
    task_index = design_schedule(config, "tasks")[accepted]
    tasks = (TASKS[task_index], TASKS[(task_index + 1) % 3])
    questions = choose_questions(graph, graph_a, tasks, rng, group_id)
    variants = []
    for i, (g, drawing) in enumerate(zip(graphs, drawings)):
        ident = oid(group_id, "variant", i)
        answers = {q.id: solve(g, q) for q in questions}
        certs = {q.id: certificate(g, q) for q in questions}
        if not all(valid_certificate(g, q, answers[q.id], certs[q.id]) for q in questions):
            raise ValueError("invalid_generated_certificate")
        delta = None if i < 2 else (delta_a if i == 2 else delta_b)
        variants.append({"id": ident, "role": ("original", "redraw", "edited", "edited")[i],
                         "graph": g.json(), "scene": drawing, "answers": answers, "certificates": certs,
                         "edit": delta,
                         "relevance": {q.id: not answer_equal(solve(graph, q), answers[q.id]) for q in questions},
                         "assets": {ext: f"images/{ident}.{ext}" for ext in ("png", "svg")}})
    for v in variants[2:]:
        v["semantic_changed_edges"] = {key: v["edit"][key] for key in ("added", "deleted")}
    return {"id": group_id, "split": split, "attempt": attempt, "seed": seed,
            "generator_version": __version__, "questions": [q.json() for q in questions], "variants": variants}


def input_exports(groups: list[dict], id_key: str | None = None) -> tuple[list, list, list, list]:
    single, paired, single_gold, paired_gold = [], [], [], []
    for group in groups:
        original = group["variants"][0]
        for q_data in group["questions"]:
            q = Question(**q_data)
            answer_format = "nonnegative integer or 'unreachable'" if q.task == "shortest_path" else "boolean"
            common = {"group_id": group["id"], "split": group["split"], "question": q.text(),
                      "instructions": INSTRUCTIONS, "answer_format": answer_format}
            for variant in group["variants"]:
                ident = oid(group["id"], q.id, variant["id"], "single")
                if id_key is not None:
                    ident = public_id(ident, id_key)
                single.append({"id": ident, **common, "image": variant["assets"]["png"]})
                single_gold.append({"id": ident, "group_id": group["id"], "split": group["split"],
                                    "question_id": q.id, "variant_id": variant["id"],
                                    "answer": variant["answers"][q.id], "certificate": variant["certificates"][q.id]})
            for variant in group["variants"][1:]:
                ident = oid(group["id"], q.id, variant["id"], "paired")
                if id_key is not None:
                    ident = public_id(ident, id_key)
                paired.append({"id": ident, **common, "images": [original["assets"]["png"], variant["assets"]["png"]],
                               "pair_instructions": "Answer the question independently for image 1 and image 2. Identify directed edges added and deleted from image 1 to image 2. Supply an evidence certificate for each answer."})
                paired_gold.append({"id": ident, "group_id": group["id"], "split": group["split"],
                                    "question_id": q.id, "variant_ids": [original["id"], variant["id"]],
                                    "answers": [original["answers"][q.id], variant["answers"][q.id]],
                                    "certificates": [original["certificates"][q.id], variant["certificates"][q.id]],
                                    "pair_kind": "redraw" if variant["role"] == "redraw" else "relevant_edit" if variant["relevance"][q.id] else "irrelevant_edit",
                                    "delta": {key: variant["edit"][key] if variant["edit"] else [] for key in ("added", "deleted")}})
    for rows in (single, paired, single_gold, paired_gold):
        rows.sort(key=lambda row: row["id"])
    return single, paired, single_gold, paired_gold


def structural_audit(groups: list[dict]) -> dict:
    counts = {key: Counter() for key in ("splits", "nodes", "edge_counts", "tasks", "answers", "operations", "relevance_patterns", "styles", "pair_kinds", "task_by_split", "operation_by_split", "answer_by_split", "operation_by_style")}
    for group in groups:
        counts["splits"][group["split"]] += 1
        counts["nodes"][str(len(group["variants"][0]["graph"]["nodes"]))] += 1
        for q in group["questions"]:
            counts["tasks"][q["task"]] += 1
            counts["task_by_split"][f'{group["split"]}:{q["task"]}'] += 1
            for v in group["variants"]:
                key = f'{q["task"]}:{json.dumps(v["answers"][q["id"]])}'
                counts["answers"][key] += 1
                counts["answer_by_split"][f'{group["split"]}:{key}'] += 1
        for v in group["variants"]:
            counts["edge_counts"][str(len(v["graph"]["edges"]))] += 1
            counts["styles"][str(v["scene"]["style"])] += 1
            if v["edit"]:
                counts["operations"][v["edit"]["operation"]] += 1
                counts["operation_by_split"][f'{group["split"]}:{v["edit"]["operation"]}'] += 1
                counts["operation_by_style"][f'{v["scene"]["style"]}:{v["edit"]["operation"]}'] += 1
                counts["relevance_patterns"]["".join("1" if v["relevance"][q["id"]] else "0" for q in group["questions"])] += 1
    for row in input_exports(groups)[3]:
        counts["pair_kinds"][row["pair_kind"]] += 1
    return {"groups": len(groups), "images": 4 * len(groups), "single_cases": 8 * len(groups),
            "paired_cases": 6 * len(groups), "distributions": {key: dict(sorted(value.items())) for key, value in counts.items()},
            "automated_checks": {"cross_split_isomorphism_duplicates": cross_split_duplicates(groups)},
            "human_visual_review": "not performed", "model_evaluation": "not performed"}


def contact_sheet(root: Path, groups: list[dict]) -> None:
    chosen = groups[:12]
    sheet = Image.new("RGB", (4 * 230, len(chosen) * 260), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for row, group in enumerate(chosen):
        tasks = "/".join(q["task"] for q in group["questions"])
        for col, v in enumerate(group["variants"]):
            with Image.open(root / "inference" / v["assets"]["png"]) as image:
                sheet.paste(image.resize((225, 225), Image.Resampling.LANCZOS), (col * 230, row * 260 + 30))
            caption = v["edit"]["operation"] if v["edit"] else v["role"]
            draw.text((col * 230 + 4, row * 260 + 2), f'{caption} · style {v["scene"]["style"]}', fill="black", font=font)
            draw.text((col * 230 + 4, row * 260 + 16), tasks, fill="black", font=font)
    sheet.save(root / "reports/contact_sheet.png")


def source_hashes() -> dict:
    root = Path(__file__).resolve().parent.parent
    files = sorted((root / "topodelta_qa").glob("*.py"))
    files += [root / name for name in ("pyproject.toml", "requirements.txt", ".python-version") if (root / name).is_file()]
    return {p.relative_to(root).as_posix(): digest(p) for p in files}


def generate(config: Config, output: Path | None = None, id_key_file: Path = Path("configs/evaluator_id_key.json"),
             seed_dataset: Path | None = None) -> dict:
    root = output or Path(config.output)
    if root.exists():
        raise ValueError(f"Output already exists; choose a new directory: {root}")
    id_key = read_key(id_key_file)
    groups, rejections, lineage = [], [], None
    proposal_config = config
    if seed_dataset is not None:
        from .verify import validate_dataset
        validate_dataset(seed_dataset)
        parent_config = Config(**json.loads((seed_dataset / "config.json").read_text()))
        if (config.seed != parent_config.seed or config.min_nodes != parent_config.min_nodes or config.max_nodes != parent_config.max_nodes
                or id_key != read_key(seed_dataset / "gold/id_key.json")):
            raise ValueError("Extension must retain the seed, node limits and evaluator ID key")
        groups = read_jsonl(seed_dataset / "gold/groups.jsonl")
        rejections = read_jsonl(seed_dataset / "reports/rejections.jsonl")
        splits = extended_split_schedule(config, groups)
        proposal_config = replace(config, groups=config.groups - len(groups))
        parent_manifest = json.loads((seed_dataset / "manifest.json").read_text())
        lineage = {"policy": "frozen-prefix-v1", "parent_version": parent_manifest.get("dataset_version", "0.1.0"),
                   "parent_manifest_sha256": digest(seed_dataset / "manifest.json"), "retained_groups": len(groups),
                   "inherited_attempts": parent_manifest["counts"]["attempted"], "new_schedule_groups": proposal_config.groups}
        print(f"Validated seed dataset; retaining {len(groups)} groups and all split assignments", flush=True)
    else:
        splits = split_schedule(config)
    for subdir in ("inference/images", "gold/pixel_diffs", "reports"):
        (root / subdir).mkdir(parents=True, exist_ok=True)
    write_json(root / "gold/id_key.json", {"key_hex": id_key})
    inherited = len(groups)
    if seed_dataset is not None:
        for source, target in (("manifest.json", "parent_manifest.json"), ("config.json", "parent_config.json"),
                               ("gold/groups.jsonl", "parent_groups.jsonl"), ("reports/rejections.jsonl", "parent_rejections.jsonl")):
            shutil.copyfile(seed_dataset / source, root / "gold" / target)
        for p in (seed_dataset / "gold/pixel_diffs").iterdir():
            shutil.copyfile(p, root / "gold/pixel_diffs" / p.name)
    attempts = lineage["inherited_attempts"] if lineage else 0
    start_attempt = attempts
    write_json(root / "config.json", asdict(config))
    for attempt in range(start_attempt, config.max_attempts):
        attempts += 1
        try:
            group = propose(proposal_config, attempt, len(groups) - inherited, splits[len(groups)])
            from .verify import validate_group
            validate_group(group)
            for prior in groups:
                if prior["split"] != group["split"]:
                    if any(isomorphic(Graph.parse(a["graph"]), Graph.parse(b["graph"])) for a in group["variants"] for b in prior["variants"]):
                        raise ValueError("cross_split_isomorphism_duplicate")
        except (RenderError, ValueError) as exc:
            rejections.append({"attempt": attempt, "reason": str(exc)})
            continue
        group = remap_group(group, id_key)
        original_image = png(group["variants"][0]["scene"])
        for v in group["variants"][2:]:
            diff = ImageChops.difference(original_image, png(v["scene"])).convert("RGB")
            channels = diff.split()
            mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2]).point(lambda x: 255 if x else 0)
            path = root / "gold/pixel_diffs" / f'{v["id"]}.png'
            mask.save(path)
            v["pixel_diff"] = {"path": path.relative_to(root).as_posix(), "changed_pixels": sum(mask.histogram()[1:]),
                               "box": mask.getbbox(), "sha256": digest(path)}
            v["semantic_changed_edges"] = {key: v["edit"][key] for key in ("added", "deleted")}
        groups.append(group)
        if len(groups) % 20 == 0:
            print(f"Accepted {len(groups)}/{config.groups}; attempted {attempts}; rejected {len(rejections)}", flush=True)
        if len(groups) == config.groups:
            break
    complete = len(groups) == config.groups
    write_jsonl(root / "reports/rejections.jsonl", rejections)
    summary = {"status": "complete" if complete else "failed", "requested": config.groups,
               "attempted": attempts, "rejected": len(rejections), "accepted": len(groups),
               "rejection_reasons": dict(sorted(Counter(r["reason"] for r in rejections).items()))}
    if lineage:
        summary["inherited"] = {"groups": inherited, "attempted": start_attempt,
                                "rejected": start_attempt - inherited}
    write_json(root / "reports/generation.json", summary)
    if not complete:
        write_jsonl(root / "gold/groups.jsonl", groups)
        raise RuntimeError(f"Generation exhausted its budget: {summary}. Partial records and rejection report saved to {root}")
    for v in sorted((v for g in groups for v in g["variants"]), key=lambda v: v["id"]):
        write_assets(v["scene"], root / "inference/images" / v["id"])
        v["asset_hashes"] = {ext: digest(root / "inference" / path) for ext, path in v["assets"].items()}
        for path in v["assets"].values():
            os.utime(root / "inference" / path, (0, 0))
    write_jsonl(root / "gold/groups.jsonl", groups)
    single, paired, single_gold, paired_gold = input_exports(groups, id_key)
    for path, rows in (("inference/single.jsonl", single), ("inference/paired.jsonl", paired),
                       ("gold/single.jsonl", single_gold), ("gold/paired.jsonl", paired_gold)):
        write_jsonl(root / path, rows)
    audit = structural_audit(groups)
    write_json(root / "reports/audit.json", audit)
    version = "0.2.0" if lineage else "0.1.1"
    write_dataset_card(root, config, summary, audit, version)
    (root / "inference/README.md").write_text(PUBLIC_PROTOCOL)
    contact_sheet(root, groups)
    manifest = {"dataset": "TopoDelta-QA", "dataset_version": version,
                "id_policy": {"name": POLICY, "key_path": "gold/id_key.json"},
                "public_asset_metadata": {"write_order": "opaque_id", "mtime_epoch": 0},
                "generator_version": __version__, "status": "complete",
                "provenance": {"python": platform.python_version(), "networkx": nx.__version__, "pillow": PIL.__version__,
                               "pyyaml": yaml.__version__, "source_hashes": source_hashes(), "config": asdict(config),
                               "font_sha256": hashlib.sha256(ImageFont.load_default(size=22).path.getvalue()).hexdigest(),
                               "raster_libraries": {name: features.version(name) for name in ("freetype2", "zlib")}},
                "renderer": RENDERER, "counts": summary,
                "files": {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}}
    if lineage:
        manifest["lineage"] = lineage
    write_json(root / "manifest.json", manifest)
    return summary


PUBLIC_PROTOCOL = """# TopoDelta-QA inference protocols

This directory is the complete image-only input export. Share this directory with
an inference runner. Keep the parent manifest, gold directory, reports, and dataset
card with the evaluator. Public group IDs and split membership support grouping;
no variant role, graph structure, answer, relevance, edit label, mask, or gold
certificate is included here. SVG assets contain drawing primitives and embedded
font data; the baseline JSONL inputs reference PNG only.

An arrow points from its tail to its arrowhead. Labels are arbitrary identifiers.
These are directed graphs, without executable flowchart semantics. Paths follow
arrows and lengths count edges. A missing path is the string "unreachable".

Run single.jsonl and paired.jsonl separately. Never combine their predictions.
For single-image calls supply only the current PNG, question, answer format, and
generic instructions; do not use other rows or variants as context. For paired
calls supply exactly the ordered two PNGs and current question. Group IDs and
splits are runner metadata.

Each JSONL row has an opaque case ID, public group ID, split, question, answer
format, and image path(s) relative to this directory. Paths in a pair are ordered:
image 1 is the reference; image 2 is the candidate. The candidate can be a redraw
or an edited graph. No edit operation or relevance label is given.

Return one JSON object per case:

Single: {"protocol":"single","id":"CASE_ID","answer":true,"certificate":{...}}
Paired: {"protocol":"paired","id":"CASE_ID","answers":[true,false],
         "certificates":[{...},{...}],"delta":{"added":[["U","V"]],"deleted":[]}}

Examples above illustrate the output shape only; they are not dataset answers.
Use JSON booleans for reachability and direct-edge answers. For shortest path use
a nonnegative integer or "unreachable". An edge ["U","V"] means U → V.
Delta lists describe graph changes from image 1 to image 2, independently of the
question. A reversal deletes ["U","V"] and adds ["V","U"]. An unchanged redraw
has two empty delta lists. Do not return changed edges as a substitute for answer
evidence. Empty evidence does not certify absence.

Evidence certificate formats (use labels read from the images):
- Reachability yes: {"kind":"path","path":["U",...,"V"]}.
- Reachability no OR unreachable shortest path:
  {"kind":"reachable_set","nodes":[all and only nodes reachable from U,
  including U]}. The complete reachable set must exclude V.
- Finite shortest path: {"kind":"shortest_path","path":["U",...,"V"],
  "distances":{"U":0,...}}. Give every node a nonnegative integer potential or
  null. The target potential must equal the path length. Every edge from a finite
  node must reach a finite node with potential at most source potential + 1.
  Actual shortest distances (null for unreachable nodes) are one valid choice.
- Direct-edge yes/no: {"kind":"edge_claim","source":"U","target":"V",
  "present":true_or_false}. Both endpoints and the explicit claim are required.

Alternative valid paths and lower-bound potentials are accepted. If collecting
only answer predictions, omit certificates; answer accuracy remains available,
while certificate validity and joint success will count the omitted evidence as
incorrect. Missing cases remain in every applicable denominator. Invalid answers,
certificates, and deltas score zero for their respective metrics. Duplicate IDs,
unknown IDs, and mixed/missing protocols cause an explicit input error.
"""


def write_dataset_card(root: Path, config: Config, summary: dict, audit: dict, version: str = "0.1.1") -> None:
    counts = audit["distributions"]
    text = f"""# TopoDelta-QA Phase 1 dataset card

Dataset version {version} (graph sampler {__version__}). Synthetic dataset; no real-world diagrams or human labels.
Novelty, usefulness, and method superiority are unverified hypotheses. No learned
verifier has been built. No model inference, paid API, remote publication, model
download, or human visual review was performed.

## Composition and provenance

- Seed: {config.seed}; {summary['accepted']} accepted groups, {summary['attempted']}
  attempts, {summary['rejected']} rejected attempts. Every rejected attempt and
  reason is recorded in reports/rejections.jsonl and reports/generation.json.
- Four variants per group: original, meaning-preserving redraw, and two single
  edge edits independently applied to the original. Two shared questions per group.
- {audit['images']} PNGs and {audit['images']} SVGs; {audit['single_cases']} single
  image-question cases; {audit['paired_cases']} ordered question-pair cases.
- Group splits: {json.dumps(counts['splits'], sort_keys=True)}.
- Question tasks: {json.dumps(counts['tasks'], sort_keys=True)}.
- Edit operations: {json.dumps(counts['operations'], sort_keys=True)}.
- Accepted original node-count distribution: {json.dumps(counts['nodes'], sort_keys=True)}.
- NetworkX gold answers are cross-checked with independent Python BFS and
  repeated distance relaxation. Gold is never generated by an LLM.
- manifest.json records normalized config, generator source and environment pins,
  runtime versions, bundled font hash, renderer parameters, and all asset hashes.
  Hashes detect accidental changes; the manifest is not a signed trust artifact.

## Intended use

Study answer preservation under redraws, answer sensitivity to question-relevant
edge edits, and validity of structured evidence. Arrow direction is tail to
arrowhead. Labels are arbitrary identifiers, without executable flow semantics.
Shortest path is unweighted; no path is the literal string "unreachable".
At least one edit in every accepted group changes exactly one of its two answers.
A reversal is one operation and two signed directed-edge differences.

## Rendering and validation

Edges are straight, with explicitly recorded arrow triangles and rectangular node
boxes. All unchanged edges and every node, label, style, and canvas remain fixed
for edits. Redraws rotate layout and change neutral grayscale styling. Three
neutral styles are assigned independently of the balanced task/operation schedules.
Drawings with crossings, near-overlapping routes, unreadable label boxes,
edge-node intersections, or occluded arrowheads are rejected geometrically.
PNG and SVG primitives are regenerated and checked; pixel differences are checked
against changed-edge footprints. reports/contact_sheet.png is evaluator material.
Automated geometry checks and agent inspection do not establish human legibility.
Human visual validation has **not** occurred.

## Access and leakage controls

Public identifiers use HMAC with an evaluator-only key in gold/id_key.json.
Never share that key or the historical ID mapping with the inference runner.
Use inference/ alone for a baseline runner, especially inference/single.jsonl and
inference/paired.jsonl. Never pass gold/, reports/, this card, or manifest.json to
an image-only model. Public inputs use neutral opaque IDs and filenames. Gold
contains canonical structures, certificates, answers, exact deltas, relevance,
seeds, and geometry; semantic edit annotations and pixel masks are distinct.
Splits keep every variant and question together. Exact directed VF2 isomorphism
checks all variants across different splits while ignoring labels. Within-split
isomorphic graphs are allowed. Similar but non-isomorphic structures can remain.

## Evaluation

See inference/README.md for prediction formats and docs/METRICS.md in the source
project for metric definitions. Paired accuracy always requires both answers to
be correct. Certificate validity accepts alternate valid paths. Absence requires
an explicit complete reachable set or endpoint presence claim. Group-bootstrap
95% percentile intervals resample whole groups. Protocol results remain separate.
There are no empirical VLM benchmark scores in this dataset release.

## Limitations and open research decisions

This is a small, synthetic, acceptance-filtered pilot. Graphs are sampled from
subsets of convex-polygon triangulations; they are planar, sparse, and do not
include reciprocal edge pairs. Isolated nodes and directed cycles can occur.
Geometry rejection favors smaller and sparser drawings; the requested 6–12 node
range does not guarantee equal coverage or inclusion of each size. Two-letter
uppercase labels, one embedded font, circular layouts/rotations, straight routes,
and grayscale styles limit visual diversity. Style, task, and operation are not
relevance markers, but chance correlations and structural answer priors remain.
Task pairs and edit operations are balanced; answer classes and relevance are not.
Questions are selected after edits to enforce mixed relevance. This is a selection
bias, not an estimate of natural graph questions. A second edit is not required
to be relevant. Redraws vary only rotation and grayscale style, not graph embedding
families. The bootstrap reflects variability among these synthetic groups, not
external-domain uncertainty. Samples were never filtered on VLM failures.

Research decisions remain: human readability protocol; broader graph/layout/label
families including reciprocal edges; answer/relevance balance; prespecified model
baselines and prompting; evidence elicitation; larger held-out external sets;
novelty review; and whether a learned verifier is justified. No superiority or
novelty claim follows from this pilot.
"""
    (root / "DATASET_CARD.md").write_text(text)
