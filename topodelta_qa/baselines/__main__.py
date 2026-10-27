"""Separate Phase 2A CLI; run imports only worker-safe modules."""
import argparse
import json
import sys
from pathlib import Path
from .contract import canonical, strict_json


def main():
    parser = argparse.ArgumentParser(prog="python -m topodelta_qa.baselines")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--dataset", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--config", type=Path, default=Path("configs/baseline_pilot.json"))
    prep.add_argument("--seed", type=int, default=20261027)
    prep.add_argument("--split", choices=("train","validation","test"), default="validation")
    prep.add_argument("--release-test", action="store_true")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--worker", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--authorize-provider", action="store_true")
    for name in ("oracle","report"):
        p = sub.add_parser(name)
        p.add_argument("--dataset", type=Path, required=True)
        p.add_argument("--selection", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--replicates", type=int, default=1000)
        if name == "report":
            p.add_argument("--checkpoint", type=Path, required=True)
            p.add_argument("--baseline", choices=("direct","parse"),required=True)
            p.add_argument("--protocol", choices=("single","paired"),required=True)
    p = sub.add_parser("compare")
    p.add_argument("--a",type=Path,required=True)
    p.add_argument("--b",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--replicates",type=int,default=1000)
    args = parser.parse_args()
    try:
        if args.command == "run":
            from .runner import run
            state = run(args.worker,args.output,args.authorize_provider)
            result = {"requests_terminal":len(state["requests"]),"attempts":len(state["attempts"]),
                      "reserved_usd":state["reserved_usd"],"mock_only":state["mock_only"],"halt_reason":state["halt_reason"]}
        else:
            if args.output.exists():
                raise ValueError("Refusing to overwrite an existing artifact")
            if hasattr(args,"dataset") and args.output.resolve().is_relative_to(args.dataset.resolve()):
                raise ValueError("Outputs must be outside the sealed dataset")
            from .prepare import write
            if args.command == "prepare":
                from .prepare import prepare
                from .runner import config_valid
                config = strict_json(args.config.read_text())
                config_valid(config)
                result = prepare(args.dataset,args.output,config,args.seed,args.split,args.release_test)
            elif args.command in ("oracle","report"):
                from .report import oracle, score
                selection = strict_json(args.selection.read_text())
                if args.command == "oracle":
                    state = oracle(args.dataset,selection)
                    args.output.mkdir(parents=True)
                    write(args.output/"privileged_predictions.json",state)
                    reports = {p:score(args.dataset,selection,state,"oracle",p,args.replicates) for p in ("single","paired")}
                    for p,r in reports.items():
                        write(args.output/f"{p}.json",r)
                    expected = ("per_image_answer_accuracy","certificate_validity","joint_success","answer_change_accuracy","parse_graph_exact_accuracy")
                    if any(r["metrics"][name]["value"] != 1 for r in reports.values() for name in expected):
                        raise RuntimeError("Oracle did not achieve perfect expected semantics")
                    result = {"label":"PRIVILEGED ORACLE, NOT IMAGE MODEL PERFORMANCE", "status":"passed",
                              "groups":reports["single"]["groups"],"single_cases":reports["single"]["expected_cases"],
                              "paired_cases":reports["paired"]["expected_cases"],"provider_calls":0}
                    write(args.output/"summary.json",result)
                else:
                    result = score(args.dataset,selection,strict_json(args.checkpoint.read_text()),args.baseline,args.protocol,args.replicates)
                    write(args.output,result)
            else:
                from .report import compare
                result = compare(strict_json(args.a.read_text()),strict_json(args.b.read_text()),args.replicates)
                write(args.output,result)
        print(canonical(result if args.command not in ("report","compare") else {"output":str(args.output),"status":"written"}))
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        # Never print provider response bodies or configuration values in errors.
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
