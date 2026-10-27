"""Recompute semantics and primitives from saved records; never trust stored gold alone."""
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

from . import __version__
from .identity import POLICY, public_id, read_key
from .dataset import digest, extended_split_schedule, input_exports, oid, read_jsonl, source_hashes, split_schedule, structural_audit
from .render import RENDERER, png, svg, unchanged_geometry, validate_scene
from .schema import Config, Graph, Question
from .semantics import answer_equal, cross_split_duplicates, edit, reference_answer, solve, valid_certificate


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_group(group: dict) -> None:
    variants = group["variants"]
    require(len(variants) == 4, "A group needs four variants")
    require([v["role"] for v in variants] == ["original", "redraw", "edited", "edited"], "Incorrect variant roles")
    questions = [Question(**q) for q in group["questions"]]
    require(len(questions) == 2 and len({q.id for q in questions}) == 2, "Two distinct questions required")
    original = Graph.parse(variants[0]["graph"])
    require(original == Graph.parse(variants[1]["graph"]), "Redraw changed graph meaning")
    require(variants[0]["scene"] != variants[1]["scene"], "Redraw must change the rendering")
    mixed = False
    for i, v in enumerate(variants):
        graph = Graph.parse(v["graph"])
        require(graph.nodes == original.nodes, "Edit changed labels or node set")
        validate_scene(graph, v["scene"])
        expected_keys = {q.id for q in questions}
        require(all(set(v[k]) == expected_keys for k in ("answers", "certificates", "relevance")), "Question-key mismatch")
        relevance = []
        for q in questions:
            gold = v["answers"][q.id]
            require(answer_equal(gold, solve(graph, q)) and answer_equal(gold, reference_answer(graph, q)), "Wrong gold answer")
            require(valid_certificate(graph, q, gold, v["certificates"][q.id]), "Invalid gold certificate")
            relevant = not answer_equal(reference_answer(original, q), gold)
            require(type(v["relevance"][q.id]) is bool and v["relevance"][q.id] == relevant, "Wrong relevance")
            relevance.append(relevant)
        if i >= 2:
            require(all(type(v["edit"].get(key)) is int for key in ("operation_count", "directed_set_difference_count")), "Edit counts must be integers")
            reconstructed, delta = edit(original, v["edit"]["operation"], tuple(v["edit"]["operand"]))
            require(reconstructed == graph and delta == v["edit"], "Wrong edit operation/directed delta")
            require(v["semantic_changed_edges"] == {key: delta[key] for key in ("added", "deleted")}, "Wrong semantic changed-edge annotation")
            require(unchanged_geometry(variants[0]["scene"], v["scene"], set(original.edges) & set(graph.edges)), "Unchanged geometry moved")
            mixed |= sum(relevance) == 1
        else:
            require(v["edit"] is None and not any(relevance), "Original/redraw edit metadata invalid")
    require(mixed, "No edit has mixed relevance across the two questions")
    require(variants[2]["graph"] != variants[3]["graph"], "Edited variants must differ")


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    require(not Path(relative).is_absolute() and path.resolve().is_relative_to(root.resolve()), "Path escapes dataset")
    require(path.is_file() and not path.is_symlink(), f"Missing or symlinked asset: {relative}")
    return path


def validate_dataset(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    require(manifest["status"] == "complete", "Incomplete generation")
    source_matches = manifest["provenance"]["source_hashes"] == source_hashes()
    require(manifest["renderer"] == json.loads(json.dumps(RENDERER)), "Renderer configuration mismatch")
    listed = set(manifest["files"])
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"manifest.json"}
    require(listed == actual, "Manifest file inventory mismatch")
    for path, expected in manifest["files"].items():
        require(digest(safe_file(root, path)) == expected, f"Hash mismatch: {path}")
    config = Config(**json.loads((root / "config.json").read_text()))
    require(manifest["provenance"]["config"] == config.__dict__, "Manifest config mismatch")
    policy = manifest.get("id_policy")
    require(policy is None or policy == {"name": POLICY, "key_path": "gold/id_key.json"}, "Unsupported identity policy")
    id_key = read_key(safe_file(root, policy["key_path"])) if policy else None
    groups = read_jsonl(root / "gold/groups.jsonl")
    require(len(groups) == config.groups, "Dataset size mismatch")
    lineage = manifest.get("lineage")
    expected_splits = split_schedule(config)
    if lineage:
        require(lineage["policy"] == "frozen-prefix-v1" and manifest["dataset_version"] == "0.2.0", "Unsupported extension lineage")
        parent_manifest_path = safe_file(root, "gold/parent_manifest.json")
        require(digest(parent_manifest_path) == lineage["parent_manifest_sha256"], "Parent manifest hash mismatch")
        parent_manifest = json.loads(parent_manifest_path.read_text())
        for parent_path, copied_path in (("gold/groups.jsonl", "gold/parent_groups.jsonl"),
                                         ("config.json", "gold/parent_config.json"),
                                         ("reports/rejections.jsonl", "gold/parent_rejections.jsonl"),
                                         ("gold/id_key.json", "gold/id_key.json")):
            require(digest(safe_file(root, copied_path)) == parent_manifest["files"][parent_path], "Parent content hash mismatch")
        parent_groups = read_jsonl(root / "gold/parent_groups.jsonl")
        parent_config = Config(**json.loads((root / "gold/parent_config.json").read_text()))
        inherited = lineage["retained_groups"]
        require(type(inherited) is int and 0 < inherited < len(groups) and inherited == len(parent_groups) == parent_config.groups,
                "Invalid retained group count")
        require(groups[:inherited] == parent_groups, "Frozen parent groups changed")
        require(parent_config.seed == config.seed and parent_config.min_nodes == config.min_nodes and parent_config.max_nodes == config.max_nodes,
                "Parent sampler configuration changed")
        require(lineage["parent_version"] == parent_manifest.get("dataset_version", "0.1.0") and
                lineage["inherited_attempts"] == parent_manifest["counts"]["attempted"] and
                lineage["new_schedule_groups"] == config.groups - inherited, "Parent lineage counts mismatch")
        parent_rejects = read_jsonl(root / "gold/parent_rejections.jsonl")
        require(read_jsonl(root / "reports/rejections.jsonl")[:len(parent_rejects)] == parent_rejects, "Inherited rejections changed")
        expected_splits = extended_split_schedule(config, parent_groups)
    all_ids = []
    for index, group in enumerate(groups):
        require(group["split"] == expected_splits[index], "Split schedule mismatch")
        require(group["generator_version"] == __version__, "Generator version mismatch")
        require(group["seed"] == int(oid(config.seed, group["attempt"]), 16), "Seed mismatch")
        legacy_id = oid(config.seed, "group", group["attempt"])
        expected_id = public_id(legacy_id, id_key) if id_key else legacy_id
        require(group["id"] == expected_id, "Group ID mismatch")
        if id_key:
            require(all(v["id"] == public_id(oid(legacy_id, "variant", i), id_key) for i, v in enumerate(group["variants"])), "Variant ID mismatch")
            require(all(q["id"] == public_id(oid(legacy_id, "question", i), id_key) for i, q in enumerate(group["questions"])), "Question ID mismatch")
        all_ids.append(group["id"])
        validate_group(group)
        for v in group["variants"]:
            all_ids.append(v["id"])
            for ext, relative in v["assets"].items():
                require(relative == f'images/{v["id"]}.{ext}', "Nonneutral asset path")
                path = safe_file(root / "inference", relative)
                require(digest(path) == v["asset_hashes"][ext], "Per-asset hash mismatch")
            require((root / "inference" / v["assets"]["svg"]).read_text() == svg(v["scene"]), "SVG differs from recorded primitives")
            with Image.open(root / "inference" / v["assets"]["png"]) as image:
                require(image.mode == "RGB" and image.size == (800, 800), "Invalid raster format")
                require(ImageChops.difference(image, png(v["scene"])).getbbox() is None, "PNG differs from recorded primitives")
        original_image = png(group["variants"][0]["scene"])
        for v in group["variants"][2:]:
            channels = ImageChops.difference(original_image, png(v["scene"])).split()
            expected_mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2]).point(lambda x: 255 if x else 0)
            metadata = v["pixel_diff"]
            path = safe_file(root, metadata["path"])
            with Image.open(path) as mask:
                require(mask.mode == "L" and ImageChops.difference(mask, expected_mask).getbbox() is None, "Wrong pixel diff")
            require(digest(path) == metadata["sha256"] and sum(expected_mask.histogram()[1:]) == metadata["changed_pixels"], "Pixel diff metadata mismatch")
            require(list(expected_mask.getbbox()) == metadata["box"], "Pixel diff box mismatch")
            # Every changed pixel must be inside the changed edges' antialiased footprint.
            allowed = Image.new("L", (800, 800))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(allowed)
            changed = {tuple(e) for key in ("added", "deleted") for e in v["edit"][key]}
            for drawing in (group["variants"][0]["scene"], v["scene"]):
                for edge in drawing["edges"]:
                    if tuple(edge["edge"]) in changed:
                        points = edge["line"] + edge["arrowhead"]
                        xs, ys = zip(*points)
                        draw.rectangle((min(xs) - 6, min(ys) - 6, max(xs) + 6, max(ys) + 6), fill=255)
            require(ImageChops.subtract(expected_mask, allowed).getbbox() is None, "Pixels changed outside edited-edge footprints")
    require(len(all_ids) == len(set(all_ids)) and all(re.fullmatch(r"[0-9a-f]{24}", i) for i in all_ids), "Opaque IDs invalid/duplicated")
    require(not cross_split_duplicates(groups), "Cross-split directed graph isomorphism leakage")
    expected = input_exports(groups, id_key)
    for path, rows in zip(("inference/single.jsonl", "inference/paired.jsonl", "gold/single.jsonl", "gold/paired.jsonl"), expected):
        require(read_jsonl(root / path) == rows, f"Export mismatch: {path}")
    # Exact public allowlists prevent adjacency, gold, role, relevance, or certificates leaking.
    common = {"id", "group_id", "split", "question", "instructions", "answer_format"}
    for kind, extra in (("single", {"image"}), ("paired", {"images", "pair_instructions"})):
        for row in read_jsonl(root / f"inference/{kind}.jsonl"):
            require(set(row) == common | extra, "Inference field leakage")
    summary = json.loads((root / "reports/generation.json").read_text())
    rejects = read_jsonl(root / "reports/rejections.jsonl")
    attempted_ids = [g["attempt"] for g in groups] + [r["attempt"] for r in rejects]
    require(sorted(attempted_ids) == list(range(summary["attempted"])), "Attempt accounting mismatch")
    require(summary["accepted"] == len(groups) and summary["rejected"] == len(rejects), "Counts mismatch")
    require(summary == manifest["counts"], "Manifest counts mismatch")
    from collections import Counter
    require(summary["rejection_reasons"] == dict(Counter(r["reason"] for r in rejects)), "Rejection reason counts mismatch")
    require(json.loads((root / "reports/audit.json").read_text()) == structural_audit(groups), "Stored audit mismatch")
    return {"status": "passed", "validator_version": "0.1.2",
            "dataset_version": manifest.get("dataset_version", "0.1.0"),
            "identity_policy": POLICY if id_key else "legacy-parent-index-hash (role leakage; audit only)",
            "generator_source_matches_current": source_matches,
            "provenance_note": "Historical source differences are reported; dataset hashes, semantics and rendering remain mandatory checks.",
            "groups": len(groups), "images": len(groups) * 4,
            "checks": ["manifest_hashes", "independent_semantics", "certificates", "edit_deltas", "mixed_relevance",
                       "scene_geometry", "unchanged_geometry", "svg_primitives", "png_primitives", "pixel_diffs",
                       "split_isolation", "exact_directed_isomorphism", "inference_allowlist", "attempt_accounting"],
            "human_visual_review": "not performed"}
