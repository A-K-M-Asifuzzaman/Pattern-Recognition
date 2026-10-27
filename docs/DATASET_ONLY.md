# Dataset-only work

Current instruction: build **1,000 total groups** locally with deterministic code.
The Phase 2B inference proposal is **cancelled**, with no smoke/full inference run.
No paid APIs, model inference, training or model downloads are permitted.
`configs/project_mode.json` records this mode; supported baseline and live-run
entrypoints reject dispatch in this mode, including with former approval flags.
The historical proposal, prompts, selection and artifacts remain preserved.
Cancellation and pre-change source hashes are in
`outputs/phase2b_cancellation/CANCELLATION.json`.

## Completed release

The build and automated checks passed. See the
[1,000-group report](DATASET_1000_REPORT.md) for evidence, distributions and limits.

`outputs/topodelta_qa_v0.2.0` contains the frozen v0.1.1 pilot's 120 groups plus
880 new groups. The pilot remains at `outputs/pilot_v0.1.1` without modification.
Retained groups keep IDs, questions, graphs, answers, certificates, images and split
assignments. The final target is 700 train / 150 validation / 150 test groups;
new groups fill the remaining 616 / 132 / 132 positions. All descendants stay with
their base graph. Exact directed isomorphism checks compare every new variant
against every retained/new variant in other splits.

Reproducible seed 20261027; nodes 6–12; two questions per group, four PNG/SVG
variants, independent addition/deletion/reversal edits, explicit semantic deltas,
pixel masks, geometry and algorithmic answer/evidence annotations. Newly proposed
groups use a separately balanced schedule over the 880 additions. The release
records its frozen prefix and parent manifest/config/records/rejections so it
validates without accessing the parent directory. The parent identity key remains
private evaluator metadata; it is never printed or put in public exports.

Generation rejects geometric/semantic/isomorphism failures, retains rejection
reasons and fails visibly if its attempt budget is exhausted. It never filters
using model predictions. Saved records and rendered primitives are revalidated;
independent Floyd–Warshall and raw-record checks cross-check the annotations.

```sh
python3 -m topodelta_qa generate --config configs/dataset_1000.yaml --seed-dataset outputs/pilot_v0.1.1 --id-key-file outputs/pilot_v0.1.1/gold/id_key.json
python3 -m topodelta_qa validate --dataset outputs/topodelta_qa_v0.2.0 --output outputs/dataset_build_1000/validation.json
```

Use a new `--output` directory for reproduction; existing datasets are never
overwritten. Historical Phase 2A/2B source hashes may differ after the cancellation
and extension changes; snapshots retain their exact prior source. Frozen data,
prompts and selection stay unchanged. Automated checks are not human validation,
model evaluation, novelty evidence or publication readiness.
