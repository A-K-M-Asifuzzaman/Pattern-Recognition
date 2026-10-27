# TopoDelta-QA v0.2.0: local 1,000-group build

Date: 2026-10-27. Scope: deterministic local dataset generation, rendering,
algorithmic annotation and validation. **Phase 2B inference is cancelled.** No
paid requests, model inference, training, model downloads or human reviews were
performed. The existing pilot and baseline artifacts remain frozen.

The new release is [outputs/topodelta_qa_v0.2.0](../outputs/topodelta_qa_v0.2.0/),
with its [dataset card](../outputs/topodelta_qa_v0.2.0/DATASET_CARD.md),
[sealed manifest](../outputs/topodelta_qa_v0.2.0/manifest.json), and separate
[build evidence](../outputs/dataset_build_1000/). This is a dataset delivery;
it does not authorize baseline inference or establish publication readiness.

## Composition and exact changes

The target is **1,000 total groups**, comprising the unchanged 120-group v0.1.1
pilot plus 880 additions. Each group has two questions and four diagram variants:
original, redraw, and two independent single-operation edits of the original.

| Cohort | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| Retained | 84 | 18 | 18 | 120 |
| Added | 616 | 132 | 132 | 880 |
| Release | 700 | 150 | 150 | 1,000 |

There are 4,000 PNGs, 4,000 SVGs, 2,000 pixel-change masks, 2,000 base questions,
8,000 single-image cases and 6,000 ordered paired-image cases. A paired case has
two images; case counts are statistical observations, not provider calls.
No provider calls are planned or dispatched.

| Base question type | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| Direct edge | 458 | 106 | 102 | 666 |
| Reachability | 476 | 93 | 98 | 667 |
| Shortest path | 466 | 101 | 100 | 667 |

Edit counts are addition 667, deletion 667, reversal 666. Among the 4,000
edited-image/question comparisons, 1,170 change the answer and 2,830 preserve it.
Another 2,000 paired cases compare redraws and preserve answers. The release has
9 irrelevant comparisons that lose an edge on the stored original positive path;
another valid route still supports the answer.

The extension adds a frozen-prefix generation path, exact residual split quotas,
and embedded parent manifest/config/records/rejections. The new sampler schedule
balances the 880 additions separately; the underlying graph sampler and renderer
are unchanged. Earlier IDs, graphs, questions, annotations, images, masks, and
split assignments stay exact. Version 0.2.0 is explicit in the manifest; graph
sampler version 0.1.0 remains its historical identifier.

Generation refuses an existing output directory and reports exhausted attempt
budgets with partial records rather than silently declaring success. Regression
tests cover these cases, impossible split quotas, frozen-prefix preservation,
and byte-identical repeated small extensions.

## Preservation and cancellation

[Preservation assertions](../outputs/dataset_build_1000/preservation.json) checked
all recorded payload hashes: original pilot 1,212 files; corrected pilot 1,213;
Phase 1B 739; Phase 2A 94; Phase 2B 306. The corrected parent manifest hash is
`d781309f095aa8f02b6f0ebb9fb33910075171b094c25ee1faadcbc98834d7d4`.
All 120 retained group records, 960 PNG/SVG files, and 240 masks match exactly.
The parent remains in its original directory; it was not replaced by the extension.

[Cancellation](../outputs/phase2b_cancellation/CANCELLATION.json) records zero
live/paid calls and preserves six pre-change source files. The project-mode
config disables real adapter entrypoints before paths or credentials are read,
including with former approval flags. Existing prompts, selection and run
artifacts remain unchanged. This local guard is project policy enforcement,
not an OS security boundary against arbitrary manually executed historical code.

## Validation evidence

The primary validator checks the complete manifest inventory and hashes, frozen
lineage, semantic answers, certificates, edits, mixed relevance, unchanged-edge
geometry, rendered primitives, all pixel masks and changed-edge footprints,
exports, opaque IDs, attempt accounting and exact directed split isolation.
**All checks passed**, with current generator source hashes matching the release.
The result is [validation.json](../outputs/dataset_build_1000/validation.json).

The [independent semantic check](../outputs/dataset_build_1000/independent/semantics.json)
passed 8,000 answers, 8,000 relevance flags, 2,000 edits and 1,000 mixed-relevance
group checks. It validated 2,664 edge claims, 1,013 positive path certificates,
3,091 complete reachable-set certificates and 1,232 finite-shortest-path
certificates. It recomputes answers from raw records with Floyd–Warshall and
checks negative closure, rooted reachability, real paths and shortest-path
potentials independently of the project semantic helpers and NetworkX.

The [independent split check](../outputs/dataset_build_1000/independent/split_isolation.json)
considered all 3,720,000 cross-split variant pairs. A directed-degree invariant
eliminated impossible matches; all 234 eligible candidates received exact
adjacency backtracking. No isomorphic overlap was found. Every descendant stays
with its base graph; redraws and both edited variants are included.

[Export checks](../outputs/dataset_build_1000/independent/export_boundary.json)
passed 20,000 exported answer/certificate occurrences, 6,000 paired deltas and
pair kinds, 4,000 SVG primitive inventories and 4,000 strict integer edit-count
fields. All 8,000 public assets have modification time zero and all 4,000 PNG
headers have no auxiliary metadata. Public schemas allow only protocol inputs;
IDs and filenames use the existing opaque keyed scheme. The evaluator key,
graphs, certificates and relevance labels remain outside inference exports.
SVG necessarily exposes its visible vector primitives; future image-only workers
must receive PNGs and allowlisted question text, not source SVG or the dataset root.

Primary and independent checks still share Python/JSON, saved graph records and
the mathematical task specification. Rendering checks reuse the same scene and
renderer and can reproduce a common rendering bug. The new check reuses the
previous agent's independent audit helpers; it is algorithmic independence,
not an independently staffed audit. The shared-dependency analysis in
[Phase 1B](PHASE1B_AUDIT.md#independent-semantics-and-shared-dependencies) still applies.

## Sampling and distributions

The complete history has **1,753 attempted / 1,000 accepted / 753 rejected**
(57.05% acceptance). Of these, the additions have 1,544 attempted / 880 accepted /
664 rejected (56.99% acceptance). No item was excluded using model performance.

| Rejection reason | Complete history | Added cohort |
|---|---:|---:|
| Hidden or ambiguous arrowhead | 501 | 440 |
| Edge/arrow intersects node | 146 | 123 |
| Cross-split isomorphism duplicate | 84 | 83 |
| No edit operand | 22 | 18 |

[Attempt reconstruction](../outputs/dataset_build_1000/attempted_base_samples.csv)
reruns the deterministic base sampler for every attempt and asserts exact
agreement with every accepted base graph. The
[acceptance table](../outputs/dataset_build_1000/acceptance_distribution.csv)
compares attempted versus accepted node/edge distributions and scheduled task
and operation pairs. It reconstructs base graphs and schedule intent, not complete
question sets for proposals rejected before question selection.

| Nodes | Attempted | Accepted | Acceptance |
|---|---:|---:|---:|
| 6 | 217 | 164 | 75.58% |
| 7 | 249 | 214 | 85.94% |
| 8 | 228 | 220 | 96.49% |
| 9 | 261 | 198 | 75.86% |
| 10 | 248 | 122 | 49.19% |
| 11 | 280 | 78 | 27.86% |
| 12 | 270 | 4 | 1.48% |

This is substantial acceptance bias toward smaller, less dense diagrams.
Twelve-node coverage is especially weak. All layouts use rotated circular
positions and a planar sparse edge construction, with three rendering styles;
the release does not cover general graph layouts or real flowchart semantics.
Finite shortest paths range from 1 to 7 edges. Edited graphs have 0–18 edges
and directed density 0–0.3.

Detailed tables are separate files:

- [Split/task](../outputs/dataset_build_1000/independent/split_task.csv),
  [original→edited answer transitions](../outputs/dataset_build_1000/independent/answer_transitions.csv),
  [operation/relevance](../outputs/dataset_build_1000/independent/operation_relevance.csv).
- [Nodes](../outputs/dataset_build_1000/independent/node_relevance.csv),
  [edges](../outputs/dataset_build_1000/independent/edge_relevance.csv),
  [density](../outputs/dataset_build_1000/independent/density_summary.csv),
  [path lengths](../outputs/dataset_build_1000/independent/path_lengths.csv),
  [layout/style](../outputs/dataset_build_1000/independent/layout_style.csv).
- [All graph variants](../outputs/dataset_build_1000/independent/graph_variants.csv)
  and [edited comparison features](../outputs/dataset_build_1000/independent/edited_question_features.csv),
  including grayscale statistics and pixel differences. Changed pixels occupy
  0.0491%–0.7613% of the canvas; this alone does not establish perceptual salience.

Answer-change rates differ by task: direct edge 28.15%, reachability 25.56%,
shortest path 34.03%; and by operation: addition 27.74%, deletion 27.21%, reversal
32.81%. These are descriptive shortcut signals, not fitted prediction results
or proof of no leakage. No diagnostic models were fitted under the current
no-training instruction. Earlier 120-group shortcut findings cannot establish
the same results for the 880 additions.

## Commands and tests

Run from the project root using the already installed Python 3.12.6,
NetworkX 3.6.1, Pillow 12.3.0 and PyYAML 6.0.3. No dependency installation or
network access was needed. Exact successful commands:

```sh
python3 -m topodelta_qa generate --config configs/dataset_1000.yaml --seed-dataset outputs/pilot_v0.1.1 --id-key-file outputs/pilot_v0.1.1/gold/id_key.json > outputs/dataset_build_1000/generation_run.txt 2>&1
python3 -m topodelta_qa validate --dataset outputs/topodelta_qa_v0.2.0 --output outputs/dataset_build_1000/validation.json > outputs/dataset_build_1000/validation_run.txt 2>&1
python3 scripts/dataset_1000_audit.py --dataset outputs/topodelta_qa_v0.2.0 --output outputs/dataset_build_1000/independent > outputs/dataset_build_1000/independent_run.txt 2>&1
python3 -m scripts.dataset_1000_preservation > outputs/dataset_build_1000/preservation_run.txt 2>&1
python3 -m unittest discover -s tests -p test_pilot.py -v > outputs/dataset_build_1000/test_pilot.txt 2>&1
python3 -m unittest discover -s tests -p test_phase1b.py -v > outputs/dataset_build_1000/test_phase1b.txt 2>&1
python3 -m unittest discover -s tests -p test_dataset_extension.py -v > outputs/dataset_build_1000/test_extension.txt 2>&1
```

The 17 pilot tests passed in 5.013s, 4 Phase 1B tests in 1.030s, and 3 extension /
cancellation tests in 9.526s: **24 passed**. These include hand-authored adversarial
evaluator fixtures, alternative paths, malformed/missing predictions, strict edit
counts, split isolation, corruption detection and deterministic repeat generation.
No model was called. Historical Phase 2B dispatch tests were not rerun as an
active inference plan. Two initial preservation-helper failures (script import
context, then tuple-versus-JSON-list comparison) are retained in the build logs;
the helper was corrected and its assertions rerun successfully. Neither changed data.

The generator refuses reuse of the delivered output path. For reproduction,
select a fresh `--output`; preserve the same config output value, parent and
private ID key. Exact small-extension byte replay passed, including the manifest;
a second complete 1,000-group generation was not run. Full validation regenerates
all saved image primitives and masks, but does not replay every sampling choice.
PNG byte reproduction requires matching FreeType/zlib/font and pinned packages.

## Review limits and next use

A [new-group contact sheet](../outputs/dataset_build_1000/independent/new_groups_contact_sheet.png)
contains 12 added groups selected reproducibly for task, operation, size and style
coverage; [selection records](../outputs/dataset_build_1000/independent/preview_selection.json)
explain the choice. It is a prepared preview, **not an agent visual audit or human
validation**. No enlarged visual review of the additions occurred in this build.
Automated geometric checks do not resolve all possible perceptual ambiguities.
The earlier blank 120-group human-review packet remains preserved; no reviews
were populated and no 1,000-group human-review campaign occurred.

The dataset is intended for controlled synthetic experiments after a separate
authorization and protocol review. This report does not establish baseline
superiority, novelty, human agreement or publication readiness. No learned
topology-delta verifier has been built.
