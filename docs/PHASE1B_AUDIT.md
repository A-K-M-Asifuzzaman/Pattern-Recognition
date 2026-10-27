# TopoDelta-QA Phase 1B audit

**Verdict: READY FOR BASELINE PILOT — corrected dataset v0.1.1 only.**
**Original v0.1.0: BLOCKED for baseline use** because its public IDs and file times
reveal variant roles. Readiness is conditional on isolated PNG-only model inputs;
it is not publication readiness, proof of novelty, proof of no shortcuts, or human
validation. No VLM inference, paid API, model training/download, remote publication,
deployment, or learned topology-delta verifier was performed.

Audit date: 2026-10-27. The corrected release is
[outputs/pilot_v0.1.1](../outputs/pilot_v0.1.1/). It has **the same 120 groups**:
no graph, task, endpoint, question text, answer, relevance, certificate body, edit,
seed, split, rendering style/geometry, or image pixel was changed or excluded.

## Preservation and exact version changes

Before edits, the original pilot, source, config, tests, docs, and prior reports
were copied to [the versioned snapshot](../outputs/versions/phase1-v0.1.0/).
Its inventory covers **1,245 files**. All original pilot files remain unchanged in
`outputs/pilot`; all inventoried snapshot hashes match. A
[sealed archive](../outputs/versions/phase1-v0.1.0.tar.gz) contains the inventoried
files plus snapshot.json; its hash is in the preservation report. A later Finder
`.DS_Store` at the snapshot root triggered an initial extra-file check. It was
retained and recorded, and is outside the dataset and sealed archive. No frozen
file was deleted or overwritten.

[Version correspondence](../outputs/phase1b/version_changes.json) and the separate
[evaluator-only ID mapping](../outputs/phase1b/id_mapping_evaluator_only.json)
verify a one-to-one mapping of **2,520 IDs**, including groups, questions, images,
and single/paired cases. **All 960 PNG/SVG files and 240 pixel masks are byte
identical** across versions. The new version changes IDs, filenames, references,
JSONL ordering, dataset-card/version and manifest/config metadata. It adds a
reproducible evaluator-only ID key. Public assets are written in opaque-ID order
and receive a common modification time. No additional research groups were added.
Do not provide the old release or mapping to a baseline runner: matching the
unchanged images back to the old release would restore its leaked roles.

## Confirmed defects and fixes

1. **Public parent/index hashes disclosed roles.** The old formula is
   `variant_id = sha256(JSON(group_id, "variant", index))[:24]`. Public group IDs
   let a runner try indices 0–3 and recover **480/480 roles without images**.
   First edits have 120 changed answers out of 240 comparisons; second edits have
   only 22/240. The rule “first edit changes, second edit does not” achieves
   **0.804 test balanced accuracy** using IDs alone (ordinary accuracy 0.736).
   These are shortcut diagnostics, not model benchmark scores.
   The shared export/generation code now uses HMAC IDs with an evaluator-only
   32-byte key. The same public-parent attack recovers **0/480 corrected roles**.
   The key is in evaluator `gold/id_key.json` and the local reproduction config,
   never in the inference folder.
2. **Filesystem chronology also disclosed roles.** Original PNG modification
   times recover role order in **120/120 groups**. Keyed filenames alone did not
   solve this. Assets are now written globally in opaque-ID order and all 960
   public image assets have modification time zero. Birth/creation order then
   follows opaque filenames rather than original/redraw/edit order. The regression
   test checks common modification times. Baseline model payloads should contain
   decoded PNGs and question/instructions only, without filesystem metadata.
3. **Integer edit counts accepted booleans/floats.** Python dictionary equality
   let JSON `true` or `1.0` stand in for integer `1` in edit metadata. Both count
   fields now require `type(value) is int`. All actual saved counts were already
   integers, so no gold count repair was necessary.
4. **Historical source provenance was treated as data corruption.** An unrelated
   source change formerly blocked validation of intact historical artifacts.
   Validator component 0.1.2 reports the source mismatch, while retaining all
   required hash, semantic, certificate, delta, rendering, export, split, and count
   checks. Generator/sampler version remains 0.1.0; corrected dataset version is
   explicitly 0.1.1 in its manifest.

[Pre-fix mutation confirmations](../outputs/phase1b/pre_fix_confirmations.json),
[the ID/chronology findings](../outputs/phase1b/version_changes.json), and
[the implementation diff](../outputs/phase1b/implementation_changes.patch) retain
evidence. Runtime changes are confined to identity handling, export ordering,
validation, and the CLI's evaluator-key parameter. The evaluator scoring formulas
were not changed: no scoring defect was found. Four Phase 1B regression tests were
added to the original 17 tests. Old prediction IDs intentionally do not match the
corrected release; use its public case IDs for new baseline predictions.

## Independent semantics and shared dependencies

The audit inspected the actual source/schema, generator, renderer, evaluator,
verifier, tests, config, records, exports, manifest and prior reports. Applicable
AGENTS.md locations were checked; the graphify trigger was not invoked.

[Independent results](../outputs/phase1b/semantics.json) on the corrected release:
**960/960 answers, 960/960 relevance flags, 240/240 edit reconstructions, and
120/120 mixed-relevance group requirements passed**. Redraws preserve the entire
labeled graph. Edits independently derive from the original. Reversals have one
operation and two directed differences. Every unchanged edge retains its geometry;
all nodes, labels, styles and canvases remain fixed under edits.

The new checker imports neither project semantic/schema/edit helpers nor NetworkX.
It reads raw JSON and uses **Floyd–Warshall** for directed distances/reachability.
It separately reconstructs edge differences and validates certificates. All 960
certificates passed: 320 explicit edge claims, 129 positive paths, 371 complete
reachable sets, and 140 finite-shortest-path certificates. A negative set contains
the source, excludes the target, contains only source-reachable nodes, and is
closed under outgoing edges. Those conditions establish completeness. Finite
shortest paths use a real length-L path and a feasible potential with source 0,
target L, and p(v)≤p(u)+1 on each edge out of a finite node. This supplies matching
upper/lower bounds. Null distances cannot hide a reachable vertex.

Evidence is not the changed-edge annotation. Paths, reachable sets, potentials,
and endpoint claims are validated on their stated graph; no arbitrary stored path
must be matched. The pilot has zero irrelevant cases that delete an edge on its
one stored original positive path. A hand-authored diamond explicitly tests loss
of one route while another remains; this difficult distinction needs better
future sampling coverage, not a fabricated claim about current coverage.

Shared dependencies and common-mode risks remain:

| Component | Existing checks | Phase 1B independence and residual risk |
|---|---|---|
| Answers | NetworkX plus BFS/relaxation share Graph/Question parsing and equality helper | Raw JSON + Floyd–Warshall; Python/JSON and the task/direction specification remain shared |
| Edits/evidence | Generator and verifier reuse edit, certificate, reference_answer and distances | Separate set-delta, rooted/closed-set, path and potential code; both could still misunderstand the same mathematical specification |
| Isomorphism | Generation and primary validation both use NetworkX VF2 | Independent degree-constrained adjacency backtracking; same saved graph structures remain inputs |
| Rendering | PNG/SVG regeneration and geometry checks share scene/render factories | Actual PNG review of 30 groups; no independent complete raster graph decoder for all 480 images |
| Evaluation | Some earlier fixtures derive expected outputs from generator helpers | Hand-authored expected answers/deltas/evidence, plus independent export alignment; scorer remains code under test |
| Reproducibility | Same deterministic sampler can reproduce the same bug | Historical and corrected full repeats test determinism, not external validity or human legibility |

This is implementation independence by the same agent, not a separately staffed
human audit or formal proof. A common wrong arrow interpretation in both saved
structure and rendering could evade two structure-only solvers; the visual sample
and future human review address part of that risk.

## Adversarial evaluator audit

The [hand fixture](../outputs/phase1b/evaluator_fixtures/hand_fixture.json) uses six
nodes: A→B→D→E and A→C→D→E, with F isolated. One edit deletes D→E; another reverses
B→D. Expected answers, certificates and deltas are written by hand, without
calling the generator or solvers. It has eight single-image and six paired cases.
[Results](../outputs/phase1b/evaluator_fixtures/results.json) cover 15 scoring cases,
four ID/protocol cases, four empty-set cases and six extra negative/shortest-path
certificate checks against both implementations. None is a model result.

| Adversarial condition | Observed requirement |
|---|---|
| Both answers wrong but identical | Raw redraw agreement 1; redraw pair accuracy 1/2 |
| Correct original, wrong edited answer | Relevant pair accuracy 0; one-answer accuracy cannot count as pair success |
| Correct answer changes, wrong edge identification | Answer pair passes; delta and joint fail for that pair |
| Correct edges, wrong answers | Delta passes; pair and joint fail |
| Alternative valid path | Evidence and joint pass; no exact gold-path matching |
| Invalid/incomplete path or negative set | Evidence and joint fail; correct answers still count for answer accuracy |
| Empty predicted and gold delta | Precision/recall/F1 = 1/1/1 |
| Exactly one empty delta or missing delta | Zero respective scores, including missing prediction on a true empty redraw |
| Missing or malformed-only predictions | Every expected case remains in its denominator and scores zero |
| Duplicate, unknown or mixed-protocol IDs | Explicit file error; no favorable arbitrary selection |
| Reordered predictions | Loaded scores and bootstrap intervals exactly unchanged |

Pair success requires **both answers correct**. Paired joint success requires
both correct answers, both valid certificates, and exact signed delta. Single-image
joint success requires its correct answer and valid certificate; delta metrics
are null, never borrowed from the paired protocol. Single-image accuracy counts
960 unique image/question cases; paired accuracy counts 1,440 answer occurrences
in 720 ordered pairs, with reference images repeated. Protocols are never pooled.
Malformed rows/JSON are counted; unknown/duplicate IDs reject the file. Missing or
invalid fields cannot improve scores by vanishing from expected denominators.
Group-bootstrap intervals resample complete groups, not individual rows.

## Split isolation and public-input boundary

[Independent split/metadata checks](../outputs/phase1b/leakage.json) consider every
variant: **53,568 cross-split pairs**, five exact backtracking comparisons after
safe degree/node/edge prefilters, **zero directed isomorphism overlaps**. Variants
and questions stay with their original group. Within-split duplicates remain
allowed. No hashes alone make the final isomorphism decision.

The public-key allowlist by itself originally missed the ID attack; it must not be
called proof of no leakage. All 1,680 corrected public rows now also use the keyed
identity policy. [Export alignment](../outputs/phase1b/export_boundary.json)
independently checks 2,400 answer/certificate occurrences, 720 paired deltas/kinds,
and 480 integer count fields. Duplication does not increase independent sample size.

All 480 SVGs were parsed: only svg/style/rect/line/polygon/text tags, 4,080 visible
line/arrowhead pairs, fixed identical embedded-font data, and no hidden answer,
role, relevance or adjacency metadata, comments, external images or scripts.
SVG vector geometry inherently makes the visible graph machine-readable. Thus
**PNG-only calls must not receive SVG XML**, evaluator gold, the key, the mapping,
legacy releases, reports, or this audit. Group IDs are runner metadata; one
single-image call receives only its image/question, and one paired call receives
only its ordered two images/question. No inference runner is implemented here.

HMAC does not erase historical publication or prevent matching identical images
to the retained old version. Key/gold access trivially defeats blinding. The
0/480 result is a check of this concrete parent/index attack, not proof of no
possible identifier or image shortcut. Export/mount only the corrected inference
folder into an isolated runner and omit IDs/path metadata from model messages.

## Distributions, acceptance and shortcuts

[Readable tables and all CSV slices](../outputs/phase1b/DISTRIBUTIONS.md) cover split,
task, original/edited answers, relevance, operation, n/m/density, directed query
distances, layout/rotation and style. The 480-row edited-question feature table
supports joint slicing. There are 80 base questions per task and 80 edits per
operation, but answer/relevance classes are not balanced: 142 relevant, 338
irrelevant edited-question comparisons and 240 unchanged redraw pairs.

| Split | Groups | Reachability Q | Shortest Q | Direct Q | Relevant edit/Q | Irrelevant edit/Q |
|---|---|---|---|---|---|---|
| train | 84 | 54 | 54 | 60 | 101 | 235 |
| validation | 18 | 11 | 13 | 12 | 22 | 50 |
| test | 18 | 15 | 13 | 8 | 19 | 53 |

Deterministic replay of the frozen sampler recovered all 209 attempted base
candidates and exactly matched all 120 accepted proposals and rejection outcomes.
The old rejection log lacked candidate features; none were invented. Most failures
occur before question selection, so rejected-question answer distributions are
unavailable. There were 61 arrowhead failures, 23 edge/arrow-node intersections,
four missing operands and one isomorphism rejection. No VLM-performance filtering
occurred. Acceptance strongly changes graph size:

| Nodes | Attempted | Accepted | Rejected | Acceptance |
|---|---|---|---|---|
| 6 | 22 | 20 | 2 | 90.9% |
| 7 | 28 | 27 | 1 | 96.4% |
| 8 | 28 | 28 | 0 | 100.0% |
| 9 | 32 | 25 | 7 | 78.1% |
| 10 | 40 | 13 | 27 | 32.5% |
| 11 | 17 | 6 | 11 | 35.3% |
| 12 | 42 | 1 | 41 | 2.4% |

| Population | Groups | Mean nodes | Mean edges | Mean directed density |
|---|---|---|---|---|
| attempted | 209 | 9.239 | 10.249 | 0.1413 |
| accepted | 120 | 8.050 | 8.500 | 0.1547 |
| rejected | 89 | 10.843 | 12.607 | 0.1232 |

Acceptance lowers absolute edge counts but raises mean directed density because
accepted graphs are smaller. All layouts are circular rotations, not diverse
embedding families. First-edit mixed relevance is forced; second edits have a
much lower change rate. This design prior persists even though its cheap metadata
exposure is fixed. No item was removed based on diagnostic performance.

### Diagnostic scope

No model was trained. Fixed rules, descriptive task/operation strata and increasing-
feature AUROCs are reported separately on original train/validation/test groups.
There is no fitted threshold/orientation or selected best test rule. All tested
rules are reported; rank intervals use 300 whole-group bootstrap resamples.
This is post hoc and uncorrected for multiple probes, not preregistered inference.
Text probes cover template/task, length, endpoint initials and lexical ordering,
not every possible n-gram adversary. Operation is evaluator-only, used here as a
proxy for visually inferable operation. Pixel probes cover changed fraction, mean
absolute difference, gray mean and ink fraction. Two questions share an image
difference, so pixels alone cannot distinguish the mixed-relevance questions.

| Feature (increasing direction) | Train AUROC | Validation AUROC | Test AUROC |
|---|---|---|---|
| text_character_count | 0.525 | 0.469 | 0.576 |
| changed_pixel_fraction | 0.525 | 0.342 | 0.494 |
| mean_absolute_pixel_difference | 0.511 | 0.360 | 0.467 |
| original_mean_gray | 0.528 | 0.551 | 0.506 |
| edited_ink_fraction | 0.478 | 0.460 | 0.479 |
| id_first_nibble | 0.489 | 0.443 | 0.455 |

The unchanged-only rule obtains 0.736 test accuracy but 0.500 balanced accuracy.
Task-only test balanced accuracies are 0.431/0.576/0.492; operation-only values are
0.469/0.471/0.560. The [legacy ID rule](../outputs/phase1b/legacy_id_shortcut.csv)
was substantially stronger at 0.804 test balanced accuracy and motivated a real
versioned fix. Validation changed-pixel AUROC is 0.342 in the increasing direction,
while test is 0.494: smaller changes associate with relevance in validation, a
signal to disclose rather than proof of no shortcuts. When redraws are included,
all-pair test changed-pixel AUROC is 0.294 because large layout/style changes
preserve answers. Read [grouped intervals](../outputs/phase1b/shortcut_rank_diagnostics.csv),
[all-pair probes](../outputs/phase1b/shortcut_all_pair_pixels.csv), and endpoint/
task-operation tables alongside these summaries. Held-out splits have only 18
groups each; these limited diagnostics cannot establish external validity or
absence of richer shortcuts.

## Agent visual audit and human packet

The agent opened 30 reproducibly selected groups, all four actual PNGs each
(**120 diagrams**), plus six 5× arrowhead crops and two 2× enlarged individual
originals. Selection covers tasks, all operations, n=6–12, all styles and splits
(19 train, 7 validation, 4 test), closest arrow tips, smallest pixel changes,
high density/degree and seeded fill. Only the available circular layout family
can be covered. [Per-group JSON](../outputs/phase1b/visual_audit.json) and
[CSV](../outputs/phase1b/visual_audit.csv) retain findings and both legacy/corrected
IDs. Selection was made on the original stable IDs; version comparison proves the
inspected PNG bytes are identical in the corrected release. Boards retain their
legacy headers for traceability, not as baseline inputs.

No unreadable label, hidden/merged arrowhead, unintended crossing, overlap/clipping
or invisible edit was confirmed in these unblinded comparisons. Close heads at
RB, TG, HA, ZT, JN and DJ remained distinct in enlarged views. All 240 edited variants
also retain unchanged geometry exactly. [Crop provenance](../outputs/phase1b/visual_enlargements/index.json)
records source and coordinates. This is **agent visual audit**, not human validation,
a blinded/timed detectability study, or proof about uninspected groups or smaller
screens. Human readability and inter-reviewer disagreement remain unresolved.

The [corrected 120-group review index](../outputs/phase1b/human_review/packet/index.html)
provides original/redraw/two-edited diagrams, questions, blank answers, readability,
ambiguity, edge-direction and change-detectability fields, reviewer identity/date,
disagreement, adjudicator/date, adjudication and exclusion reason. Its 480 PNGs
match the corrected assets. The [blank CSV](../outputs/phase1b/human_review/packet/review_records_blank.csv)
has 960 image/question rows. All reviewer, answer and adjudication fields are blank.
The [answer key](../outputs/phase1b/human_review/answer_key/answers.csv) and JSON key
are separate and algorithmic, not human consensus. No reviews or exclusions were
populated. Forms support local JSON download without network requests; all links
and blank fields were checked, but browser download interaction was not tested
end-to-end. The preliminary legacy packet is retained separately and superseded.

## Verification and exact commands

**21 tests passed** in 5.910s in the saved run, including four Phase 1B
tests. See [raw results](../outputs/phase1b/test_results.txt),
[corrected primary validation](../outputs/phase1b/corrected_primary_validation.json),
[independent semantic checks](../outputs/phase1b/semantics.json),
[adversarial fixtures](../outputs/phase1b/evaluator_fixtures/results.json), and
[corrected reproducibility](../outputs/phase1b/corrected_reproducibility.json).
The frozen original sampler reproduced all 1,213 original files. The final corrected
generator reproduced **all 1214 corrected files, including manifest,
identically**, using the same evaluator-only key. Public modification times were
also checked. Dataset size remains 120. No post-fix required check remains failing.
Intermediate candidates and preliminary reports are not additional releases.

Executed core commands:

```sh
python3 -m topodelta_qa generate --config configs/pilot.yaml
python3 -m topodelta_qa validate --dataset outputs/pilot_v0.1.1
python3 scripts/phase1b_versions.py
python3 scripts/phase1b_refresh.py
python3 scripts/phase1b_exports.py --dataset outputs/pilot_v0.1.1 --output outputs/phase1b
python3 scripts/phase1b_text_diagnostics.py --output outputs/phase1b
python3 scripts/phase1b_pair_diagnostics.py --dataset outputs/pilot_v0.1.1 --output outputs/phase1b
python3 scripts/phase1b_fixtures.py --output outputs/phase1b/evaluator_fixtures
python3 -m unittest discover -s tests -v
python3 -m topodelta_qa generate --config configs/pilot.yaml --output outputs/phase1b/corrected_repeat
python3 -m topodelta_qa validate --dataset outputs/phase1b/corrected_repeat
```

Generation refuses existing output directories. To reproduce the corrected release
in a new location, use `--output outputs/pilot_v0.1.1_repeat` and, if needed,
`--id-key-file outputs/pilot_v0.1.1/gold/id_key.json`; preserve that key with the
evaluator. Compare every file hash and manifest. The initial independent audit and
attempt replay commands were:

```sh
python3 scripts/phase1b_audit.py --dataset outputs/pilot --output outputs/phase1b
PYTHONDONTWRITEBYTECODE=1 python3 scripts/phase1b_replay.py --source outputs/versions/phase1-v0.1.0/source --dataset outputs/pilot --output outputs/phase1b
PYTHONDONTWRITEBYTECODE=1 python3 scripts/phase1b_before_checks.py
python3 scripts/phase1b_zoom.py --dataset outputs/pilot --output outputs/phase1b
```

For a fresh standalone corrected automated audit, run `phase1b_audit.py` with the
corrected dataset and a **new** output directory, then the export/text/pair probes
with that directory. This rebuilds machine tables, a blank packet and inspection
materials; it does not invent new agent observations or human reviews. The
migration/refresh scripts are one-time operations and refuse overwriting archives.
Full final artifact/source hashes are in outputs/phase1b/manifest.json.

## Remaining research decisions

Execute and adjudicate human reviews; enforce model-runner input isolation; broaden
graph families, reciprocal edges, labels/fonts and layouts; improve answer/change
balance and supporting-path edit coverage; prespecify model baselines, prompts and
evidence elicitation; obtain larger external held-out evaluations; and decide
licensing and novelty only after review. The corrected pilot supports bounded
baseline experiments, not publication or superiority claims. No learned verifier
was built.
