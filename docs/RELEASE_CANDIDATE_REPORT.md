# TopoDelta-QA v0.3.0-rc1 research dataset release candidate

Build status: COMPLETE — local research dataset release candidate, with the
limitations and confirmed cross-perturbation shortcut documented below.

Scope clarification (2026-10-28): **Human validation is outside scope and did not
occur.** No reviewer response is awaited and no additional human-review materials
are being created. Existing materials are preserved unchanged. The high-risk
agent visual audit and all deterministic completion checks are complete. See
`docs/RELEASE_CANDIDATE_CLOSEOUT.md` and the machine-readable
`outputs/topodelta_qa_v0.3.0-rc1_CLOSEOUT.json`.

The sealed dataset, complete replay, existing archives and original delivery
inventory remain unchanged. The sealed companion audit retains the original
report snapshot; this working report incorporates the later scope clarification.

## Authorized scope and preservation

Dataset creation only, with local deterministic generation, rendering and
algorithmic annotation. Phase 2B inference remains cancelled. No paid requests,
model inference, training, model downloads or external publication are authorized
or performed. Historical releases, their manifests, old prompts and baseline
artifacts are preserved. This release has a separate source namespace,
configuration and output directory; it does not silently replace v0.2.0.

No historical group is retained: old 800-pixel canvases and 22-pixel text do not
meet the new minimum 1152-pixel canvas and 26-pixel text. All historical variants
also enter an exact-isomorphism blacklist. Prior engineering/audit access exposed
old splits; no old test set is described as pristine and no exposed old group is
moved into new test. No layout/style holdout is claimed.

## Sampling investigation and fixes

The old rejection log is preserved in
`outputs/release_candidate_work/v020_rejection_by_size_reason.csv`. Its 12-node
acceptance was 4/270, versus 220/228 for eight nodes. Most larger-graph failures
were intersecting edge/node/arrow geometry or ambiguous arrowheads on a fixed
circle. Scaling that sampler would amplify the size bias.

The new generator constructs safe geometric corridor pools, a connected core,
optional isolated distractor, DAG ordering or forced directed cycle, and bounded
edge density. It enumerates edits and question pairs that satisfy mixed relevance
before independently checking them. Exact node-size quotas control size counts;
within-cell topology/question selection remains biased and is reported.

Four layouts are grid, staggered layers, radial hub/ring and concentric rings.
Four grayscale styles are plain box, rounded gray, heavy frame and double frame.
Size, appearance and semantic streams use separate deterministic seeds.
Compatibility constraints make radial/concentric normally sparse, six-node
cycles connected/moderate, six-node cycles exclude concentric, and small
six/seven-node disconnected cells sparse. No fully balanced Cartesian product
is claimed. Coverage bins and quotas describe base graphs; edited variants can
change topology, density or connectivity and are separately enumerated in
`reports/variant_features.csv`. Disconnected groups include an isolated distractor, while both
questions and edits remain within the same original nontrivial connected region.

Preflight snapshots preserve each unsuccessful design: an overly restricted
second-addition pool, infeasible small disconnected moderate cells, a bridge-only
sampler with exhausted small cyclic topology choices, and the seven-corridor
six-node concentric moderate conflict. Those defects were fixed constructively;
geometry thresholds were never reduced. After 10,045 groups, another small
concentric topology cell exhausted the first eight templates. Source/config,
header and every accepted payload hash were preserved. Additional templates are
selected only at trials >=1000, expanding the small concentric outer ring. Prior
accepted records/assets remain byte-identical; only the unfinished build header
was explicitly migrated. The fresh complete generation must reproduce that
accepted prefix and all later groups.

The isolated-pocket revision subsequently expanded a five-node core to eight
safe corridors. At slot 11431, 15,000 candidates for a six-node disconnected DAG
in test still failed the historical/cross-split topology checks. Rather than
increasing retries again, the explicit staged coverage configuration redirects
78 remaining scheduled cells of that type to connected moderate six-node DAGs;
concentric redirects to a feasible grid/staggered/radial layout. This is a
coverage-plan revision, not proof that all possible disconnected graphs are
infeasible. Exact node and split quotas, styles, questions and edit-operation
schedules, and every accepted group remain unchanged. The original plans,
source/config snapshots and failed-attempt logs are preserved. Earlier accepted
disconnected DAG coverage remains. The full visual sample fixes its slots before
this revision; its final table reports actual rather than assumed coverage.

Density is m/n: sparse [0.6,1.25), moderate [1.25,1.75]. Directed density
m/[n(n-1)] is also reported. Structural difficulty uses maximum finite directed
shortest-path lengths 0–2, 3–4, and 5–19; it is not measured human/model difficulty.
Alternative-route coverage means a direct edge has another directed route of at
most four edges. Weak undirected bridges are the recorded bottleneck proxy.

## Semantics, evidence and common failure dependencies

Each group contains original, complete labeled-graph-preserving redraw, and two
edits independently applied to the original. One identical edit must change one
question answer and preserve the other. Relevance comes from recomputed answers.
Addition/deletion are one directed difference; reversal is one operation and two
signed directed differences. Unchanged edge geometry, nodes, labels, style and
canvas remain identical in edited variants.

Primary annotation uses NetworkX. The independent verifier imports no primary
solver, schema, renderer or NetworkX: it reads raw JSON and uses Floyd–Warshall,
strict answer types, signed set differences and structural certificates. It
accepts any valid path, not just the stored shortest path. A negative certificate
contains the source, excludes the target, is closed under outgoing edges, and
contains only reachable vertices. Closure/rooting therefore certifies absence.
A finite shortest-path certificate supplies a real path and feasible distance
potentials rooted at zero; its target potential equals path length, proving
optimality. Changed edges, answer evidence and answer-change explanations occupy
separate fields.

Correlated-bug risks remain: both verifiers share Python/JSON, the task
specification, and the serialized graph. A wrong graph could agree semantically
while differing from its image. Saved-image validation regenerates with the same
renderer/geometry helpers, so a common renderer defect could reproduce itself.
The independent exact isomorphism checker has its own refinement and adjacency
backtracking implementation, but shares the mathematical filtering principle.
Export alignment shares the HMAC identity helper, while independently deriving
question text, membership, answers and deltas from raw records. Visual inspection
is by the same agent, not a separate human team.

## Splits, protocol and leakage boundary

All variants/questions stay with their base graph. Splits target 70/15/15 with
exact per-size cumulative rounding. Base graphs are globally distinct up to
exact directed isomorphism ignoring arbitrary labels. Every variant is compared
against all variants in other splits and against historical variants. Hash/color
refinement is only a candidate filter; candidates receive exact adjacency tests.
Allowed within-group unlabeled relationships and same-split descendant overlap
are counted separately. Global base uniqueness also precludes repeated complete
graph/question/edit structures; it does not make within-group observations
independent.

Single-image cases contain one PNG and one question. Paired cases contain original
and candidate PNGs plus the same question, and require both answers and the
protocol's declared paired components. Public linkage does not authorize joining
single-image cases into a paired protocol. No baseline performance is measured.
The old root evaluator/Graph schema supports 6–12 nodes and the old record layout;
it is not an RC evaluator. Use `topodelta_qa.release.verify` for RC validation.
Future learned-baseline/evaluator adapters are outside this dataset-only work.

Inference JSON uses strict field allowlists and opaque HMAC IDs/filenames sorted
by opaque case ID. It contains no gold answers, graph structures, certificates,
relevance or variant roles. PNG metadata are empty. SVG necessarily exposes
visible vector geometry and labels, so future image-only workers must receive
decoded PNGs plus allowlisted question text, excluding SVG, IDs, split fields,
gold, source, reports and filesystem metadata. Sealing rewrites asset creation
order globally by opaque filename and sets mtime zero. This packaging is not an
enforced inference-worker sandbox; no inference worker is run.

Shortcut diagnostics are descriptive contingency counts and Cramers V, separately
by existing group-isolated split, with conditional task/operation tables. They
cover task wording, operation, style, layout, size, image mean/standard deviation/ink and
changed-pixel fractions. No predictor is trained or fitted. These associations
are diagnostics, not proof of no leakage, and no items are removed based on model
or diagnostic performance.

## Rendering and review

All four saved PNGs/SVGs per group are checked against stored geometry and hashes.
Checks cover label clipping/overlap, edge/node clearance, arrow clearance,
crossings/overlaps, minimum edge length, pixel detectability and unchanged raster
footprints outside the edited edge regions. Text is 26 pixels, arrowheads 22 by
16 pixels, canvases adaptive >=1152. No parallel/reciprocal connections are used.
Crossings are non-junctions without nodes and are rejected in this release.

Native PNG strokes are not supersampled; enlargement can show stair steps.
Template-based straight planar layouts and a 90-degree/style redraw are narrower
than natural diagram diversity. Geometry checks do not prove human readability.
The completed agent visual audit inspected all four images in 216 groups,
stratified by exact size, appearance, tasks, operations and density, including
16 additional high-risk examples.
Checkpoint observations and enlarged views are preserved separately.

The human packet contains 400 reproducibly stratified groups plus every accepted
group with minimum route clearance <8 pixels (the rejection threshold is still
5 pixels). It has shuffled blind A–D panels, questions, blank answer/readability/
ambiguity/direction fields, reviewer identity/date and disagreement/adjudication/
exclusion fields. The answer key is separate in gold. No human reviews or
inter-rater agreement are fabricated.

## Reproduction, licensing and limitations

Exact environment, dependencies, font bytes and renderer versions are recorded
inside the release. A second complete generation must rerun sampling, rendering,
annotation, exports and validation in a separate directory, then compare actual
payload SHA-256 digests, annotation records and canonical manifest bytes without
normalization. Runtime timestamps remain outside deterministic content.

Chunk archives include all payload files exactly once and are checked member by
member against the release manifest. All license notices come from already
installed dependencies; no downloads occur. The bundled font's embedded names
say “No Rights Reserved.” and identify Sora Sagano, but complete standalone font
terms were not retrieved. Font redistribution provenance and project-code
licensing remain author decisions. CC BY 4.0 is a dataset-license proposal only,
not a grant or a legal conclusion. This is local packaging, not publication.

Automated validation, agent visual inspection and actual human review are reported
separately. Passing automation or reaching 20,000 groups does not establish
novelty, superiority, human validation or publication readiness.

## Actual first-build counts and distributions

The first complete build contains 20,000 base groups, 80,000 distinct diagram
renderings, 80,000 PNGs and 80,000 SVGs (160,000 image asset files), 160,000
single-image QA instances and 120,000 original–variant–question comparisons.
The base group is the aggregation/resampling unit. The four images, eight
single-image answers and six paired comparisons in each group are dependent.
Separately seeded unique bases are not a claim of i.i.d. draws: global uniqueness
constraints and quotas couple acceptance decisions, and allowed same-split
descendant overlaps create additional relationships. Those relationships are
reported separately rather than counted as new independent base graphs.

| Node band | Target | Accepted | Exact sizes |
| --- | ---: | ---: | --- |
| 6–8 | 4,000 | 4,000 | 1,334 / 1,333 / 1,333 |
| 9–12 | 4,000 | 4,000 | 1,000 each |
| 13–16 | 6,000 | 6,000 | 1,500 each |
| 17–20 | 6,000 | 6,000 | 1,500 each |

| Split | Groups | Direct-edge questions | Reachability questions | Shortest-path questions |
| --- | ---: | ---: | ---: | ---: |
| Train | 14,000 | 9,331 | 9,359 | 9,310 |
| Validation | 3,000 | 1,992 | 1,978 | 2,030 |
| Test | 3,000 | 2,010 | 1,996 | 1,994 |

Question counts above count each base question once; each is evaluated on four
images. Test data were accessed for dataset construction and validation only;
no baseline inference, prompt tuning or performance-based item removal occurred.

DAG/cyclic counts are 10,000 each. Connected/disconnected counts are
15,226/4,774. Sparse/moderate counts are 14,547/5,453. Structural difficulty
short/medium/long counts are 3,629/11,393/4,978. Layout counts are grid 5,058,
staggered layers 5,063, radial 5,060 and concentric 4,819; styles are exactly
5,000 each. There are 134 empty cells in the enumerated 15-size × 4-layout ×
2-topology × 2-connectivity × 2-density grid. Compatibility constraints and
finite scheduled coverage explain these omissions; no Cartesian balance claim
is made.

Across both edited variants there are 13,333 additions, 13,334 deletions and
13,333 reversals. All 20,000 first edits have mixed relevance for the two
questions. Across both edits and questions there are 21,086 relevant and 58,914
irrelevant observations. All 58,914 irrelevant cases lie in the same original
weak component as the edit; 1,924 delete an edge from a stored positive path yet
preserve the answer. Alternative paths, branches, merges, weak bridges,
unqueried nodes and unreachable ordered pairs occur in respectively 14,673,
19,942, 19,968, 17,848, 20,000 and 19,957 groups. These are presence counts,
not exclusive classes or independent observations. Thirty-seven groups use a
logged question-sign fallback; 52 use expanded templates and one uses the
isolated-pocket template.

Original direct-edge answers are 6,635 true / 6,698 false; reachability answers
are 6,511 true / 6,822 false. Original shortest-path answers include 6,346
unreachable and 6,988 finite distances (1 through 10). Complete answer values,
original/edited transitions, relevance, path length, density, layout/style and
split tables are in `reports/`; a compact readable copy is supplied in
`outputs/topodelta_qa_v0.3.0-rc1_audit/DISTRIBUTIONS.md`.

The canonical final-source trace contains 121,684 attempted candidates and
101,684 rejections (16.44% acceptance). Rejections comprise 99,968 forbidden
historical/other-group isomorphisms, 1,125 unavailable density capacities,
538 short edges, 27 missing verified mixed-edit question pairs and 26 missing
cyclic cores. Six-node acceptance is only 1,334/100,708 (1.325%); exact size
quotas prevent this from shrinking the accepted six-node count, while within-cell
selection bias remains substantial. Accepted and attempted distributions are
reported separately. Earlier aborted development traces and their source/config
snapshots remain in `release_candidate_work/`; they are not mislabeled as
canonical attempts from the final generator.

## Completed agent visual audit and prepared human review

The completed agent audit covers 216 distinct groups / all 864 images: 200
reproducibly stratified groups and 16 additional high-trial, dense or preserved
boundary cases. Exact-size coverage ranges from 13 to 22 groups; layouts
concentric/grid/radial/staggered cover 54/65/51/46 groups, styles cover
57/55/52/52, sparse/moderate 159/57, DAG/cyclic 111/105, and connected/disconnected
154/62. Base question types direct-edge/reachability/shortest-path cover
139/150/143 cases; additions/deletions/reversals cover 139/150/143 edits.
Seven distinct groups were also opened in native enlarged views. All records,
selection recipes, contact sheets, enlarged images and evidence hashes are in
`outputs/topodelta_qa_v0.3.0-rc1_audit/`.

No unresolved visual defect was observed at the recorded scales. This is sampled
agent inspection, not proof of human readability. Original endpoint descriptions
in checkpoint notes and one batch-2 note contained description errors; affected
images were reopened, descriptions corrected, and original notes preserved.
No dataset record or image was changed by that correction. Raster stair steps
remain visible under enlargement.

The reproducible human packet contains exactly 400 groups, with 26 or 27 per
exact node count and greedy coverage across appearance, tasks, density and edits.
No accepted group triggered the documented <8-pixel route-clearance review flag,
so no extra flagged group was added. `review/packet/index.html` and its blank
review-record CSV are separate from `gold/human_review_key.jsonl` and the
selection record. Actual human reviews, adjudications, exclusions and agreement
measurements: zero.


## Regression and preservation evidence

Fourteen RC regression tests passed in 7.875 seconds. They exercise exact size/
split/style schedules, constructive semantics, wrong-answer and geometry mutations,
alternative paths, incomplete negative and shortest-path certificates, exact
isomorphism ignoring labels, formerly infeasible template/cyclic cells, the
78-cell revision preserving its earlier plan prefix, resume/repeat identity,
overwrite refusal, orphan-image rejection, schema/export corruption, stratified
blank review selection, descriptive shortcut calculations and archive corruption.
Legacy suites also passed: 17 pilot tests (4.978 s), four Phase 1B tests (1.028 s)
and three 1,000-group extension tests (9.275 s). Total: 38 passing tests. Logs are
preserved in `outputs/release_candidate_work/tests_release_inventory.txt` and
`tests_legacy_{pilot,phase1b,extension}.txt`.

The accepted 500-group checkpoint passed 4,000 independent answer and certificate
checks, 1,000 edit checks and 2,000 saved PNG/SVG pair checks before expansion.
Thirty-two checkpoint groups were visually inspected and are included, once,
in the final 216-group audit.

Read-only final preservation checks verified the frozen manifests and all 13,581
inventoried payload files across pilot, v0.1.1, v0.2.0, Phase 1B, Phase 2A and
cancelled Phase 2B outputs. Another 47 frozen source/build-evidence files remain
identical. The versioned v0.1.0 snapshot's 1,245 files and its archive hash match
the frozen Phase 1B report. The snapshot's previously documented `.DS_Store`
remains an OS metadata exception, not a changed dataset payload.

The checkpoint and accepted-prefix inventories were rechecked. No accepted
record, canonical attempt trace or image was overwritten by a staged generator
revision. Unfinished `gold/build.json` / `gold/plan.json` changes were explicit
and preserved in migration records. Aborted `.failed.json` attempt markers were
moved to the work evidence directory with their exact hashes verified, keeping
development failures outside the deterministic final release. See
`preservation_final.json`, `historical_snapshot_preservation.json`, the three
accepted-prefix inventories and migration records.

## Commands and local execution boundaries

Commands run from `/Volumes/ssd(mac)2/Antu Sir Paper` using Python 3.12.6.
The recorded environment is macOS 26.6.2 arm64, Pillow 12.3.0, NetworkX 3.6.1,
PyYAML 6.0.3, jsonschema 4.26.0, FreeType 2.14.3 and zlib 1.3.1.zlib-ng.
Bundled Aileron font SHA-256:
`69853909b940023570964e29cffe30da95aea8de3627736b5cd15ab30143169f`.
Renderer `rc1-native-v1`, deterministic seed 2026102803, two render/validation
workers, batches of 100 and a 25-GiB free-space reserve are configured explicitly.
No additional dependency or font/model download was performed.

```sh
python3 -m unittest discover -s tests -p 'test_release*.py' -v
python3 -m unittest discover -s tests -p 'test_pilot.py' -v
python3 -m unittest discover -s tests -p 'test_phase1b.py' -v
python3 -m unittest discover -s tests -p 'test_dataset_extension.py' -v

# Staged first build; explicit source/header migrations are documented above.
python3 -m topodelta_qa.release.build --limit 500
python3 -m topodelta_qa.release.verify --dataset outputs/topodelta_qa_v0.3.0-rc1 --output outputs/release_candidate_work/checkpoint_validation_final --expected 500
python3 -m topodelta_qa.release.build --resume
python3 -m topodelta_qa.release.package prepare --dataset outputs/topodelta_qa_v0.3.0-rc1
python3 -m topodelta_qa.release.verify --dataset outputs/topodelta_qa_v0.3.0-rc1 --output outputs/topodelta_qa_v0.3.0-rc1/reports --expected 20000
python3 -m topodelta_qa.release.boundary_cli --dataset outputs/topodelta_qa_v0.3.0-rc1
python3 -m topodelta_qa.release.package seal --dataset outputs/topodelta_qa_v0.3.0-rc1

# Complete fresh replay, without copying generated records or assets.
python3 -m topodelta_qa.release.build --output outputs/temporary_rc_regeneration
python3 -m topodelta_qa.release.package prepare --dataset outputs/temporary_rc_regeneration
python3 -m topodelta_qa.release.verify --dataset outputs/temporary_rc_regeneration --output outputs/temporary_rc_regeneration/reports --expected 20000
python3 -m topodelta_qa.release.boundary_cli --dataset outputs/temporary_rc_regeneration
python3 -m topodelta_qa.release.package seal --dataset outputs/temporary_rc_regeneration
python3 -m topodelta_qa.release.package compare --dataset outputs/topodelta_qa_v0.3.0-rc1 --other outputs/temporary_rc_regeneration --output outputs/release_candidate_work/reproducibility.json
python3 -m topodelta_qa.release.package archives --dataset outputs/topodelta_qa_v0.3.0-rc1 --output outputs/topodelta_qa_v0.3.0-rc1_archives
python3 outputs/release_candidate_work/check_preservation.py
```

The sequential command driver and return codes are recorded in
`outputs/release_candidate_work/finish_build_pipeline.py` and `commands.jsonl`.
A fresh user reproduction starts with the final frozen source and config, not
with historical intermediate generator revisions. The release's
`reproduction/REPRODUCE.md` identifies the exact minimal historical blacklist,
private evaluator identity-key placement, environment and fresh-output commands.
Credentials are neither needed nor displayed. Gold/key material belongs only
in the evaluator/reproduction environment, never a future inference worker.


## Full automated validation and shortcut results

The first full validation passed: 20,000 groups, 160,000 independently recomputed
answers, 160,000 certificates, 40,000 exact edits and pixel-footprint checks,
80,000 PNGs and 80,000 SVGs. Every saved image regenerated exactly; all PNG
metadata were empty and no duplicate PNG was found. Exact expected asset inventory
also passed. The raw-record export audit passed 160,000 single-image cases,
120,000 paired cases and 400,000 answer/certificate occurrences, with strict
field allowlists and opaque sorted IDs.

The independent all-variant split audit covered 56,000 train, 12,000 validation
and 12,000 test variants: 1,488,000,000 theoretical cross-split variant pairs.
Invariant filtering left zero cross-split exact candidates; there were 3,069
exact candidate comparisons overall, including one historical candidate. No
forbidden cross-split, historical or duplicate-base isomorphism was found.
There are 3,068 allowed same-split descendant overlap relationships, counted as
relationships rather than distinct groups. Allowed within-group unlabeled
isomorphisms comprise 20,000 original/redraw, 98 original/edited and 98
redraw/edited relationships. An edit may preserve unlabeled isomorphism while
changing the complete labeled graph; this is not a failed edit. No repeated
complete graph/question/edit structure can exist with globally unique base
topologies.

Shortcut contingencies use 56,000 train, 12,000 validation and 12,000 test
edit/question observations, correlated within groups. Marginal Cramers V ranges
from 0.00163 to 0.03859. The largest measured value is operation on test; wording
(task-template), style, layout, size and the selected image-statistic bins are
also reported, along with task/operation-conditional counts. These are descriptive
associations, not trained prediction accuracies or proof of no leakage. Conditional,
nonlinear, endpoint-label and other unmeasured shortcuts remain possible. The
readable table is `outputs/topodelta_qa_v0.3.0-rc1_audit/SHORTCUT_DIAGNOSTICS.md`.


A standalone blind-review copy is also supplied at
`outputs/topodelta_qa_v0.3.0-rc1_human_review/review/packet/index.html`.
It contains only the 400 blank group pages, template, 1,600 referenced PNGs,
instructions and a SHA-256 inventory. It excludes gold, graph/certificate files,
SVGs, paired inference JSON and the answer key. This avoids unblinding image roles
through joins to paired exports. Page/image references, blank answer controls,
400/1,600 counts and the header-only review CSV were checked. The original
separate answer key remains in the sealed release's gold directory.

A further style-versus-answer contingency check uses the existing answer table,
separately by split, task and image role. Cramers V ranges from 0.00497 to
0.06472; the maximum is edited shortest-path answers on test, where distance
categories include sparse outcomes and repeated edits are correlated. The full
27-row table is `style_answer_associations.csv` in the audit folder. This is
another descriptive diagnostic, not evidence of exact statistical independence.
The font and nominal text size are fixed across all items; styles/layouts vary
on separate seed streams. Irrelevant edits make up 73.6425% of the 80,000
edit/question observations, an explicit label imbalance that future evaluation
must account for. No fitted model, inference, item removal or holdout claim was
used in these diagnostics.


Actual square canvas widths range from 1152 to 1536 pixels. Across 40,000 edited variants, changed-pixel counts range from 226 to 2,534; the minimum required is 120. Pixel masks and unchanged-region checks are automated evidence of detectable raster changes, not a measured human detection threshold.

## Confirmed cross-perturbation shortcut

The small marginal associations above describe the 80,000 matched edited-variant
question cases. They exclude the 40,000 redraw comparisons. Across all 120,000
paired comparisons, a style difference identifies a redraw, and every redraw
answer is unchanged. Direct raw-record counts confirm:

| Style differs from original | Answer unchanged | Answer changed |
| --- | ---: | ---: |
| Yes | 40,000 | 0 |
| No | 58,914 | 21,086 |

Cramers V for this combined table is 0.32648. Unchanged labels comprise 82.4283%
of all paired comparisons. This is a real perturbation-family shortcut; the
release must not be described as free of appearance shortcuts. Redraws deliberately
change embedding orientation/style, while edits deliberately preserve appearance.
Their gold `pair_kind` supports separate redraw-invariance and edit-sensitivity
reporting. A pooled preservation score can be inflated by identifying redraws.
No pooled baseline was run, no prompts were tuned, and no item was removed or
altered using this diagnostic. Separating comparison strata is necessary for
interpreting later experiments; it does not eliminate unmeasured shortcuts.

`outputs/topodelta_qa_v0.3.0-rc1_audit/CROSS_PROTOCOL_SHORTCUT.json` records the
counts, scope and method. This remains a research release candidate with an
explicit evaluation limitation, not a leakage-free or publication-ready benchmark.

The all-comparison count diagnostic can be reproduced with
`PYTHONPATH=. python3 outputs/release_candidate_work/cross_protocol_diagnostic.py`.
It reads raw records and writes only the companion audit table. SVGs were checked
as source/geometry; browser-dependent SVG font rendering was not separately
rasterized. The agent visual audit used the actual saved PNGs.

Exact node/edge-count and both density-measure frequency tables across all 80,000
variants, by split and role, are also supplied in the companion audit's
`edge_density_distribution.csv`. They sum to 20,000 originals, 20,000 redraws and
40,000 edited variants. Reproduce with
`python3 outputs/release_candidate_work/edge_density_distribution.py`.

Text-size values above refer to a nominal 26-pixel font. Across all 576 allowed
two-letter labels, its measured layout bounding boxes are 28–50 pixels wide and
18–19 pixels high; every scene records the actual `label_box`. These font metrics
are recorded in `text_geometry_sizes.json` in the companion audit and do not
establish human readability. Arrow geometry is 22 pixels long by 16 pixels wide.


## Final completion and verdict

Both complete generations and their independent semantic/rendering/split/export
checks passed. The fresh replay started at group zero, generated all 20,000 groups
in 2,035.959 seconds, and independently regenerated its exports,
review packet, reports, provenance and seal. No generated record, image, export or
validation report was copied from the first build into the replay.

The comparison read and SHA-256 checked every actual payload: 200,484
files, including 20,000 annotation records and 160,000 PNG/SVG assets. There are
zero differing files. Canonical manifest objects and manifest bytes are identical;
no normalization was applied. Both manifest hashes are
`10fcb8dd41f48542301f22dd09f4bbb553095333335a3db7427a098bced09e0a`. The retained replay is a second physical copy
of the same 20,000-group dataset, not another 20,000 independent observations.

All 21 core chunk archives passed full extraction-stream integrity checks:
200,485 safe relative regular-file members, every member SHA-256
matched the sealed release, with no missing or repeated member. Twenty group chunks
contain 1,000 groups each; a separate metadata/export chunk completes the release.
Companion audit and blind-review archives have separate inventories and checks.
Final companion packaging command: `PYTHONPATH=. python3 outputs/release_candidate_work/finalize_delivery.py`.

| Stored artifact | Logical file bytes | Logical GiB / allocated GiB |
| --- | ---: | ---: |
| Sealed release | 6,602,467,982 | 6.149 / 6.564 |
| Retained complete replay | 6,602,467,982 | 6.149 / 6.564 |
| Core chunk archives | 3,323,703,071 | 3.095 / 3.213 |

Logical sizes and filesystem allocation (`du -sk`) are reported separately;
historical releases are excluded. Runtime logs record free-space checks throughout generation.
The delivery inventory separately records companion audit/review archive sizes.

Verdict: **COMPLETE LOCAL RESEARCH DATASET RELEASE CANDIDATE WITH DOCUMENTED
LIMITATIONS**. All requested count targets and automated completion gates passed.
There were 216 agent-inspected groups, including 16 additional high-risk groups,
and zero actual human reviews. Human validation is outside scope and is not a
completion gate. Existing review materials are preserved; no additional materials
are being created and no reviewers are awaited. Deterministic correctness checks
establish the stated graph/software properties. Agent judgments of visual
readability apply at the inspected scales and do not establish human readability.
No expansion, paid APIs or model benchmarking were performed. License adoption
and font redistribution confirmation concern any future external distribution.
The confirmed
redraw/style shortcut requires separate comparison-stratum reporting; pooled
preservation results cannot support strong edit-sensitivity claims. Planar
synthetic templates, restricted disconnected structure, substantial six-node
acceptance bias, unmeasured shortcuts, correlated observations and the legacy
6–12-node evaluator limitation remain as described above. No publication
readiness, novelty, human validation or model superiority is claimed.
