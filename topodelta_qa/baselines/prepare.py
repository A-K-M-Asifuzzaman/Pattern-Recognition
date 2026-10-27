"""Privileged preparation exports pixels and public text, never gold to the worker."""
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from PIL import Image
from .contract import canonical, digest, question, schema

ROOT = Path(__file__).resolve().parents[2]


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def flip(case_id, seed):
    return int(digest([seed, "presentation-order", case_id]), 16) % 2 == 1


def prepare(dataset, output, config, seed=20261027, split="validation", release_test=False):
    if output.exists() or output.resolve().is_relative_to(dataset.resolve()):
        raise ValueError("Use a new output outside the frozen dataset")
    if split == "test" and not release_test:
        raise ValueError("Test prediction preparation requires explicit --release-test after freeze")
    if split not in ("train", "validation", "test"):
        raise ValueError("Use an existing grouped split")
    manifest = json.loads((dataset/"manifest.json").read_text())
    if manifest.get("dataset_version") != "0.1.1":
        raise ValueError("Only corrected v0.1.1 is permitted")
    # Validate source files against the sealed inventory before exporting them.
    from ..verify import validate_dataset
    validate_dataset(dataset)
    groups = [g for g in read_rows(dataset/"gold/groups.jsonl") if g["split"] == split]
    groups.sort(key=lambda g: digest([seed, g["id"]]))
    # shortcut: validation has only 18 groups, use every group; stratify explicitly if a future split exceeds 24.
    if split == "validation" and len(groups) > 24:
        raise ValueError("Larger validation split needs a prespecified stratified selection")
    gids = {g["id"] for g in groups}
    if not gids:
        raise ValueError("Empty selected split")
    prompts = {name: (ROOT/f"prompts/phase2a/{name}.txt").read_text() for name in ("common", "direct", "parse")}
    worker = output/"worker"
    (worker/"images").mkdir(parents=True)
    images, cases, requests = {}, [], []
    for protocol in ("single", "paired"):
        for row in read_rows(dataset/f"inference/{protocol}.jsonl"):
            if row["group_id"] not in gids:
                continue
            question(row["question"])
            paths = [row["image"]] if protocol == "single" else list(row["images"])
            reverse = protocol == "paired" and flip(row["id"], seed)
            if reverse:
                paths.reverse()
            hashes = []
            for relative in paths:
                source = (dataset/"inference"/relative).resolve()
                if not source.is_relative_to((dataset/"inference/images").resolve()) or source.suffix != ".png":
                    raise ValueError("Only internal PNGs may be exported")
                with Image.open(source) as im:
                    # Pixels only: strip all source metadata including any PNG text chunks.
                    clean = Image.frombytes("RGB", im.size, im.convert("RGB").tobytes())
                    stream = io.BytesIO()
                    clean.save(stream, format="PNG")
                data = stream.getvalue()
                sha = hashlib.sha256(data).hexdigest()
                (worker/f"images/{sha}.png").write_bytes(data)
                hashes.append(sha)
                images[sha] = {"sha256": sha, "size": list(clean.size)}
            case = {"id": row["id"], "group_id": row["group_id"], "protocol": protocol,
                    "question": row["question"], "reversed": reverse, "images": hashes}
            cases.append(case)
            for baseline in ("direct", "parse"):
                requests.append({"id": digest([baseline, protocol, row["id"]]), "case_id": row["id"],
                                 "baseline": baseline, "protocol": protocol, "question": row["question"], "images": hashes})
    requests.sort(key=lambda r: r["id"])
    freeze = {"protocol_sha256": hashlib.sha256((ROOT/"docs/BASELINE_PROTOCOL.md").read_bytes()).hexdigest(),
              "prompt_hashes": {k: hashlib.sha256(v.encode()).hexdigest() for k,v in prompts.items()},
              "schemas_sha256": digest([schema(r["baseline"], r["protocol"], r["question"]) for r in requests]),
              "implementation_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(Path(__file__).parent.glob("*.py"))},
              "dataset_manifest_sha256": hashlib.sha256((dataset/"manifest.json").read_bytes()).hexdigest()}
    bundle = {"format": "topodelta-phase2a-worker-v1", "config": config, "prompts": prompts,
              "requests": requests, "images": images, "freeze": freeze}
    write(worker/"bundle.json", bundle)
    strata = {"task": Counter(), "operation": Counter(), "nodes": Counter(), "layout_style": Counter()}
    for g in groups:
        for q in g["questions"]:
            strata["task"][q["task"]] += 1
        for v in g["variants"]:
            if v["edit"]:
                strata["operation"][v["edit"]["operation"]] += 1
            strata["nodes"][str(len(v["graph"]["nodes"]))] += 1
            strata["layout_style"][f'circular/style{v["scene"]["style"]}'] += 1
    selection = {"split": split, "seed": seed, "group_ids": [g["id"] for g in groups],
                 "selection": "all existing validation groups (<24); seeded order, no reallocation" if split == "validation" else "all existing groups in chosen split",
                 "strata_units": "questions for task, edited variants for operation, all variants for nodes/layout-style",
                 "strata": strata, "cases": cases, "freeze": freeze, "bundle_sha256": digest(bundle)}
    write(output/"evaluation/selection.json", selection)
    write(output/"proposal_counts.json", {"groups": len(groups), "single_cases": sum(c["protocol"] == "single" for c in cases),
          "paired_cases": sum(c["protocol"] == "paired" for c in cases), "initial_calls": len(requests),
          "maximum_attempts": len(requests)*config["max_attempts"],
          "image_occurrences_initial": sum(len(r["images"]) for r in requests),
          "output_token_ceiling_initial": len(requests)*config["settings"]["max_completion_tokens"],
          "model": config["model"], "measured_cost_usd": None, "paid_inference_authorized": False})
    return {"groups": len(groups), "requests": len(requests), "worker": str(worker), "bundle_sha256": digest(bundle)}
