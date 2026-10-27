# TopoDelta-QA instructor demo · v0.3.0-rc1

**Dataset presentation only.** Open [the offline gallery](gallery.html), then use
[the five-minute instructor script](INSTRUCTOR_SUMMARY.md). No server, internet,
API key, inference or model is required. Answers are deliberately visible.

## Problem and design

A graph edit can change one answer while preserving another. TopoDelta-QA pairs
directed graph diagrams with reachability, shortest-path-length and direct-edge
questions. Each base group has an original, a complete labeled-graph-preserving
redraw and two edits independently applied to the original. Each of its two
questions is answered on all four images. At least one identical edit changes
one question's answer and preserves the other.

**Start with group `cb2cb52cb5e1d654b236734a`.** Delete **VA → JM**. Reachability remains true via
**VA → VQ → JM**; direct-edge presence changes true → false. Changed edges and
answer-supporting evidence are separate annotations.

## Verified release counts

| Unit | Count |
| --- | ---: |
| Base groups | 20,000 |
| Diagram renderings | 80,000 |
| PNG files / SVG files | 80,000 / 80,000 |
| Single-image QA instances | 160,000 |
| Original–variant–question comparisons | 120,000 |

These counts match the actual sealed manifest; this presentation does not add
samples. The group is the aggregation unit. Its images/questions are correlated;
global uniqueness constraints also couple acceptance. Do not count renderings
as independent base graphs.

| Base-graph nodes | Groups |
| --- | ---: |
| 6–8 | 4,000 |
| 9–12 | 4,000 |
| 13–16 | 6,000 |
| 17–20 | 6,000 |

Train / validation / test: **14,000 / 3,000 / 3,000**.
DAG / cyclic: **10,000 / 10,000**.
Connected / disconnected: **15,226 / 4,774**.
Sparse / moderate: **14,547 / 5,453**.
Layouts: concentric 4,819, grid 5,058, radial 5,060, staggered layers 5,063. Four style families have **5,000 base groups each**.
Density uses edges/nodes: sparse [0.6, 1.25), moderate [1.25, 1.75], for base graphs.
Edits can leave those bins. Exact sizes, answer transitions and task/operation
counts are in [the copied reports](reports/coverage_summary.json).

| Task (base questions, before four-image replication) | Train | Validation | Test |
| --- | ---: | ---: | ---: |
| direct_edge | 9,331 | 1,992 | 2,010 |
| reachability | 9,359 | 1,978 | 1,996 |
| shortest_path | 9,310 | 2,030 | 1,994 |

The 40,000 edits comprise **13,333 additions, 13,334
deletions and 13,333 reversals**. Across 80,000 edit/question cases,
**21,086 are relevant / 58,914 irrelevant**;
redraw comparisons are separate. Rejection sampling accepted 20,000 of
121,684 attempted candidates and rejected 101,684; see
[acceptance by size](reports/acceptance_by_size.csv).

## Read the annotations

[The small JSON example](annotation_example.json) is a labeled presentation
projection of one original/edit pair, not a replacement schema. Complete saved
records for all 16 groups are in `samples/`; the canonical
[group schema](reports/group.schema.json) is also included.

| Field | Meaning |
| --- | --- |
| `questions` | Task, source/target labels and opaque question ID |
| `variants[].graph` / `scene` | Directed labeled graph / rendered geometry |
| `edit` / `semantic_changed_edges` | One declared operation / signed edge delta |
| `answers` / `certificates` | Typed algorithmic answers / supporting evidence |
| `relevance` | Whether that edit changes that question's answer |
| `answer_change_evidence` | Before/after answer evidence, distinct from the delta |

A reversal is **one operation and two directed-edge differences**. Any valid
supporting path is acceptable. Negative reachability needs a rooted, closed
reachable set; finite shortest paths also include distance potentials proving
optimality. An empty edge list does not prove non-reachability.

## Reproduction and evidence

The complete second generation matched **200,484 payload hashes** and
manifest bytes, including **20,000 records** and **160,000 PNG/SVG assets**;
no normalization was applied. All **21 core archives / 200,485 members** passed
integrity checks. See [status](STATUS.md), [provenance](selection.json),
[the manifest header receipt](reports/release_manifest_summary.json) and
[the full report](../docs/RELEASE_CANDIDATE_REPORT.md).

From the repository root, using the existing local environment:

```sh
PYTHONPATH=. python3 scripts/instructor_demo.py build
PYTHONPATH=. python3 scripts/instructor_demo.py verify
python3 -m unittest discover -s tests -p 'test_instructor_demo.py' -v
```

The prebuilt gallery is designed to open by double-clicking `gallery.html`.
Browser rendering could not be inspected in this environment: Chrome is absent
and the in-app browser blocks local file URLs. Static links/data checks and
direct saved-PNG inspection are recorded separately in `reports/browser_check.json`.
Source rebuild uses
only these saved samples/reports. Sample JSONs preserve canonical asset references;
this small bundle includes PNGs, not SVG/font assets. Reproducing the **full release**
uses `python3 -m topodelta_qa.release.build --output outputs/repeat`, followed by
prepare/verify/boundary/seal/compare commands in the full report and sealed
`reproduction/REPRODUCE.md`. It requires the recorded environment plus the local
historical blacklist and evaluator identity key. Those inputs are intentionally
not committed. No new full generation is part of this presentation.

## Limits and Git preparation

This is a synthetic, template-based, planar research release candidate. Sampling
is biased, especially for six-node topology uniqueness; 134 coverage cells are empty.
Style differences identify redraws whose answers are unchanged: report redraw
invariance separately from edited-case sensitivity. Low marginal shortcut
associations do not prove absence of leakage. The legacy evaluator supports the
older 6–12-node format; it is not a release-candidate baseline evaluator.

This synthetic dataset has a **200-group agent visual audit** plus
**16 additional high-risk groups** (216 distinct groups /
864 images in total). Deterministic graph/image checks
establish defined software properties; agent judgments concern apparent visual
readability at inspected scales. **No human validation or model benchmarking
occurred.** Human validation is outside scope. Existing review materials remain
local and unchanged; no additional review materials were created for this demo.

At the original demo handover the workspace had **no Git repository or tracking
index** before ignore changes; that inspection is preserved in `reports/git_preparation.json`.
The root `.gitignore` now excludes `outputs/`, credentials/identity keys, virtual
environments and caches. Source (`topodelta_qa/`, `scripts/`, `tests/`), configs
without keys, docs and this bounded demo are eligible for ordinary tracking.
Only **16 saved groups / 64 PNGs** are included here, all from train, selected for
teaching coverage rather than performance. The original root README is preserved
in the initial Git commit and the root README's historical section; the frozen
legacy source inventory refers to those original bytes. Full collections and
temporary outputs stay local.
Current repository delivery is documented in [the root README](../README.md).
License adoption and font
redistribution provenance need author review before any external publication;
this demo grants no license. No novelty, superiority or publication readiness
is claimed.
