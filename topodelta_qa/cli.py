import argparse
import json
import sys
from pathlib import Path

from .dataset import generate, read_jsonl, structural_audit, write_json
from .evaluate import evaluate_dataset
from .schema import Config
from .verify import validate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(prog="topodelta")
    sub = parser.add_subparsers(dest="command", required=True)
    generation = sub.add_parser("generate")
    generation.add_argument("--config", type=Path, required=True)
    generation.add_argument("--id-key-file", type=Path, default=Path("configs/evaluator_id_key.json"), help="Evaluator-only reproducibility key; never include in inference input")
    generation.add_argument("--seed-dataset", type=Path, help="Extend a validated frozen dataset without changing its groups or split assignments")
    generation.add_argument("--output", type=Path, help="Override output directory; existing directories are never overwritten")
    for name in ("validate", "audit", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("--dataset", type=Path, required=True)
        command.add_argument("--output", type=Path, help="Optional JSON report outside the sealed dataset")
        if name == "evaluate":
            command.add_argument("--predictions", type=Path, required=True)
            command.add_argument("--protocol", choices=("single", "paired"), default="single")
            command.add_argument("--split", choices=("all", "train", "validation", "test"), default="all")
            command.add_argument("--bootstrap-replicates", type=int)
            command.add_argument("--seed", type=int)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            result = generate(Config.load(args.config), args.output, args.id_key_file, args.seed_dataset)
        else:
            if args.output and args.output.resolve().is_relative_to(args.dataset.resolve()):
                raise ValueError("Report output must be outside the sealed dataset")
            validation = validate_dataset(args.dataset)
            if args.command == "validate":
                result = validation
            elif args.command == "audit":
                result = structural_audit(read_jsonl(args.dataset / "gold/groups.jsonl"))
            else:
                config = Config(**json.loads((args.dataset / "config.json").read_text()))
                result = evaluate_dataset(args.dataset, args.predictions, args.protocol, args.split,
                                          args.bootstrap_replicates if args.bootstrap_replicates is not None else config.bootstrap_replicates,
                                          args.seed if args.seed is not None else config.seed)
            if args.output:
                write_json(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
