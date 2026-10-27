# TopoDelta-QA · Phase 1

**Current mode: dataset creation only. Phase 2B inference is cancelled.**
Completed: **1,000 groups** in [v0.2.0](outputs/topodelta_qa_v0.2.0/DATASET_CARD.md), including 120 retained pilot groups and 880 additions. Generation, rendering, algorithmic annotation and automated validation ran locally. No model inference, paid APIs, training or downloads. See [the build report](docs/DATASET_1000_REPORT.md) and [active workflow](docs/DATASET_ONLY.md).


A local, reproducible synthetic pilot for question-conditioned topology changes
in directed graph diagrams. Novelty and method superiority remain unverified.
Gold answers come from deterministic algorithms, never an LLM.

Phase 1B: see [the independent audit](docs/PHASE1B_AUDIT.md) and
[blank 120-group human-review packet](outputs/phase1b/human_review/packet/index.html).
The original pilot is preserved in `outputs/versions/phase1-v0.1.0/` and its sealed
archive; the original `outputs/pilot` remains unchanged. Corrected version 0.1.1 replaces
public identifiers, filenames, and metadata while preserving every graph, answer,
and image byte. Verifier patch 0.1.2 reports
historical source differences and strictly validates integer edit counts. The
original version is blocked for baseline use because public IDs and file times
revealed variant roles. Use the corrected version and keep its evaluator-only
`gold/id_key.json`, the reproduction key in `configs/evaluator_id_key.json`, and
all legacy-version metadata outside the inference runner.

The preserved 120-group pilot is in `outputs/pilot_v0.1.1/`. Start with its
[dataset card](outputs/pilot_v0.1.1/DATASET_CARD.md), [audit](outputs/pilot_v0.1.1/reports/audit.json),
[generation report](outputs/pilot_v0.1.1/reports/generation.json), and
[contact sheet](outputs/pilot_v0.1.1/reports/contact_sheet.png).
Automated checks are separate from human review: **human visual validation has
not occurred**. No model inference or learned verifier is included.

## Environment and commands

The verified environment is CPython **3.12.6**, NetworkX **3.6.1**, Pillow
**12.3.0**, and PyYAML **6.0.3**. `.python-version` and `requirements.txt` pin these.
No model, system renderer, external font, GPU, API key, or paid service is needed.
SVG and PNG use a shared primitive scene; Pillow supplies its embedded Aileron
Regular font. SVG embeds that font, so system font substitution is unnecessary.

From this project directory, in an environment with those dependencies:

```sh
python3 -m topodelta_qa generate --config configs/pilot.yaml
python3 -m topodelta_qa validate --dataset outputs/pilot_v0.1.1
python3 -m topodelta_qa audit --dataset outputs/pilot_v0.1.1
python3 -m topodelta_qa evaluate --dataset outputs/pilot_v0.1.1 --predictions predictions.jsonl
python3 -m topodelta_qa evaluate --dataset outputs/pilot_v0.1.1 --predictions paired_predictions.jsonl --protocol paired
python3 -m unittest discover -s tests -v
```

Generation refuses to overwrite an existing directory. The delivered pilot already
exists; reproduce into a fresh directory:

```sh
python3 -m topodelta_qa generate --config configs/pilot.yaml --output outputs/pilot_v0.1.1_repeat
python3 -m topodelta_qa validate --dataset outputs/pilot_v0.1.1_repeat
python3 -c 'import json; from pathlib import Path; a=json.loads(Path("outputs/pilot_v0.1.1/manifest.json").read_text()); b=json.loads(Path("outputs/pilot_v0.1.1_repeat/manifest.json").read_text()); assert a["files"] == b["files"]; print("Identical dataset payload hashes; inspect manifest provenance separately")'
```

Validation checks every listed file against its hash and regenerates the image
primitives. Comparing the validated file-hash maps covers every payload file. Verifier patches
change source hashes inside manifest provenance; those differences are expected.
For byte-identical historical manifests, use the frozen source snapshot as
documented in the Phase 1B audit. Timestamps
and absolute output paths are excluded. Reproduction assumes the pinned Python
and library builds; PNG bytes across other FreeType/zlib builds are not promised.
The small repeat-generation test compares every byte, including the manifest.
The delivered verification report also records a complete 120-group repeat run.

For a clean environment, use CPython 3.12.6 and install `requirements.txt` in a
virtual environment. If the pinned libraries are already installed locally,
this offline setup also exposes the `topodelta` console command:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e .
.venv/bin/topodelta --help
```

The offline installation requires the pinned build tool, setuptools 84.0.0,
to be available locally. The module commands above need no package installation.
The three runtime dependencies have no additional runtime dependency tree.

## Layout and scope

- `topodelta_qa/schema.py`: typed graph/config/question and serialized-record contracts.
- `semantics.py`: NetworkX solver, independent BFS/relaxation, edits, certificates,
  and exact directed isomorphism checks.
- `render.py`: geometry, shared SVG/PNG rendering, clearance validation.
- `dataset.py`: seeded sampling, rejection accounting, splits, exports, audit,
  dataset card, contact sheet, and provenance manifest.
- `verify.py`: saved-data integrity, independent semantic checks, rendering
  regeneration, delta footprint checks, isolation, and export allowlists.
- `evaluate.py`: protocol-specific accuracy, evidence/delta metrics, and group bootstrap.
- `cli.py`: generation, validation, audit, and evaluation commands.
- `tests/test_pilot.py`: semantic, geometry, leakage, metric, failure, and reproduction checks.

Each accepted group has 6–12 nodes, four variants, and two shared questions. One
variant redraws exactly the same labeled graph. Each edited variant independently
adds, deletes, or reverses one original edge. At least one edit changes one answer
and preserves the other. Edits preserve every unchanged route, node position,
label, style, and canvas. Reversals count as one operation and two directed edge
set differences. Answer evidence and changed-edge annotations are separate.

Graph sampling uses randomly directed subsets of convex-polygon triangulations.
Generation rejects invalid geometry and cross-split isomorphism duplicates. All
four variants are checked against all variants in other splits, ignoring labels;
exact VF2 checks make the final duplicate decision. Within-split duplicates are
allowed. Task-pair and operation schedules are separately shuffled and balanced;
styles are independently sampled. See the card for acceptance and selection bias.

## Inference boundary

Give a baseline runner **only `outputs/pilot_v0.1.1/inference/`**. It contains neutral
assets, public questions, and [protocol instructions](outputs/pilot_v0.1.1/inference/README.md).
PNG paths are relative to that directory. Runner metadata can identify groups and
splits, but single-image model calls receive only the current image, question,
answer format, and generic instructions. No other cases or images are context.
Paired calls receive exactly their ordered two images and current question.

Keep `gold/`, `reports/`, `DATASET_CARD.md`, and `manifest.json` with the evaluator.
They contain privileged graph structure, answers, relevance, certificates,
semantic deltas, and pixel differences. Public row keys are validated by exact
allowlists. Inputs contain neither edit-operation nor relevance hints.

Prediction formats, negative evidence, and alternative valid paths are documented
in the inference README. [Metric definitions](docs/METRICS.md) explain denominators,
empty sets, invalid/missing fields, joint success, and uncertainty intervals.
Choose `--split test` for test-only evaluation. Use `--output outputs/evaluation.json`
to save a report outside the sealed dataset; protocol and split are recorded.

Generation writes partial gold and explicit attempt/rejection reports before
raising an error if its attempt budget is exhausted. It never relabels failed
candidates to reach the quota. It never filters on VLM success or failure.

Recorded automated results and exact commands are in
[Phase 1B audit](docs/PHASE1B_AUDIT.md) and [current raw test output](outputs/phase1b/test_results.txt).
The [Phase 1 verification record](docs/VERIFICATION.md) documents the earlier frozen source version.
Remaining research decisions include human legibility review, broader graph and
rendering families, answer/relevance balancing, model baselines, evidence
elicitation, external validity, novelty review, and release licensing.


## Phase 2A baseline harness

The [baseline protocol](docs/BASELINE_PROTOCOL.md) and frozen
[prompt templates](prompts/phase2a/) define direct VLM, parse-then-solve and
privileged oracle tracks. [The runbook](docs/BASELINE_RUNBOOK.md) gives commands,
isolation requirements, safe resume and the proposed model/budget.
[The Phase 2A report](docs/PHASE2A_REPORT.md) records local checks and results.

For these experiments, give the provider worker only the newly prepared
`outputs/phase2a/worker/` bundle and installed code in an isolated environment.
It is narrower than the historical inference export: PNG bytes and current question
only reach the model, paired order is randomized, and no SVG or original-first hint
is sent. Keep `outputs/phase2a/evaluation/` and every dataset/gold/old-release/report
folder off the worker. The worker CLI is `python3 -m topodelta_qa.baselines run`;
preparation and offline scoring are separate commands. Never put API keys in config.

No real provider inference has run. The example budget is a proposal, not approval;
null reservation settings and an authorization gate deliberately prevent dispatch.
The 18-group validation oracle sanity check is privileged access, not VLM performance.
Test predictions remain absent. There is no learned topology-delta verifier.
