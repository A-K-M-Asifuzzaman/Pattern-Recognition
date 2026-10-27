# TopoDelta-QA v0.3.0-rc1 scope closeout

Status: **COMPLETE — 20,000-group local research dataset release candidate**.
Scope clarification: 2026-10-28. Human validation is outside scope and did not
occur. No reviewers are awaited. No additional human-review materials were
created for this closeout; all existing materials are preserved unchanged.

## Completed work

| Component | Completed result |
| --- | --- |
| Dataset | 20,000 base groups; 80,000 diagrams, each exported as PNG and SVG |
| QA exports | 160,000 single-image QA cases; 120,000 original–variant–question comparisons |
| Semantic checks, each build | 160,000 answers and certificates; 40,000 exact edits |
| Image checks, each build | All 80,000 PNG/SVG pairs; scene/primitive consistency, pixel footprints, metadata and duplicate checks passed |
| Splits and exports | All-variant directed-isomorphism audit and strict inference/gold export checks passed in both builds |
| Full regeneration | Second complete 20,000-group generation from slot zero; all 200,484 payload hashes and canonical manifest bytes matched, without normalization |
| Agent visual audit | 216 groups / 864 images, including 16 additional high-risk groups; seven groups also inspected in native enlarged views |
| Core archives | 21 archives; all 200,485 members passed the full streamed integrity check |
| Tests | 38 regression tests passed; full-run checks are recorded separately |
| Human validation | None; outside scope |

The high-risk agent audit is finished. Records cover each inspected group and all
four images. No unresolved visual defect was observed at the recorded scales.
This is an agent judgment, not a deterministic guarantee or a human assessment.

## What the evidence establishes

Deterministic checks recompute answers and certificates from serialized graphs,
verify declared edit deltas, compare stored geometry and generated image data,
and enforce export/split/integrity invariants. They establish correctness under
the implemented definitions and recorded environment. Shared renderer/geometry
dependencies can reproduce the same error; those dependencies are documented in
the full report. SVGs were checked as source/primitives, not separately rasterized
through a browser.

Agent visual inspection evaluates apparent label readability, directions,
overlap, clipping and edit visibility at the viewed scales. It is sampled and
subjective. It does not prove that people can read every image, establish
inter-rater agreement, or validate all 20,000 groups visually. **No human
validation occurred.**

The known redraw/style shortcut remains documented: style differences identify
redraw comparisons, whose answers are unchanged. Redraw invariance and edit
sensitivity require separate reporting. Planar templates, sampling bias and
other documented limitations remain. These findings do not expand the work into
model benchmarking or publication readiness.

## Preservation and closeout verification

The sealed dataset and replay, the original delivery JSON, all 21 core archives,
the two existing companion archives, and existing review materials were left
unchanged. The original report snapshot remains in the sealed companion audit.
The working report and delivery README clarify the current scope; they do not
replace those sealed snapshots.

The closeout reconciled existing full-run reports, rechecked matching manifest
bytes, and rehashed all 23 existing archives and 2,407 existing human-material
files against recorded hashes. It did not rerun generation or rendering, create
additional review materials, or change dataset membership. The completed full
validation, regeneration and streamed archive checks remain the evidence for
those respective stages.

Machine-readable closeout: `outputs/topodelta_qa_v0.3.0-rc1_CLOSEOUT.json`.
Exact reconciliation command:

```sh
python3 outputs/release_candidate_work/reconcile_closeout.py
```

The reconciliation is a one-time record and refuses to overwrite its existing
closeout JSON. Original generation, validation, comparison and packaging commands
and results remain in `docs/RELEASE_CANDIDATE_REPORT.md` and the companion audit.

No dataset expansion, paid APIs, model inference, training, model downloads,
model benchmarking or external publication was performed.
