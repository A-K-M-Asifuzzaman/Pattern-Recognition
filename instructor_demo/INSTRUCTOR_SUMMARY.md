# Five-minute instructor demo

Open `gallery.html` locally. This is an answer-visible dataset demonstration,
not a model experiment. All 16 groups and all 64 PNGs are saved training examples.

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:40 | Gallery opening / teaching example | “We ask whether a local graph edit matters to a particular question.” |
| 0:40–1:50 | Original next to Edit A | “Both questions use VA and JM. Removing VA → JM makes the direct-edge answer false, while VA → VQ → JM keeps reachability true. Same edit, different relevance.” |
| 1:50–2:30 | Redraw and Edit B | “The redraw preserves every labeled edge. Edit B reverses VA → JM: one operation, two directed-edge differences. Each edit starts from the original.” |
| 2:30–3:10 | Small JSON example | “The changed-edge delta is separate from the evidence supporting each answer. These are typed algorithmic annotations.” |
| 3:10–4:00 | Index: select a small/large, cyclic/DAG or different-layout group | “The gallery spans all sizes 6–20, four layouts/styles and all three tasks/edit operations. It is a teaching selection, not an evaluation sample.” |
| 4:00–5:00 | README counts and STATUS.md | “The release has 20,000 groups, 80,000 diagrams in PNG and SVG, 160,000 QA instances and 120,000 comparisons. A complete rebuild matched 200,484 payload hashes and manifest bytes.” |

## Questions worth inviting

- Why can deleting a path edge preserve reachability? Another path can survive.
- What proves a negative answer? A rooted, outgoing-closed reachable set excluding
  the target; an empty list alone is insufficient.
- Why does shortest-path evidence need more than a path? A witness proves an upper
  bound; feasible distance potentials certify optimality.
- Is a reversal two edits? It is one declared operation with two signed edge changes.

## State these limits explicitly

“Deterministic correctness checks passed. An agent inspected 216 groups,
including 16 high-risk groups; those readability judgments are not human
validation. **No human validation or model results are available or implied.**
The known redraw/style shortcut means redraw invariance and edit sensitivity
must be reported separately. This is a research dataset release candidate.”

No inference, paid requests, expansion or benchmarking is needed during the demo.
Click any PNG for its saved full resolution. The small JSON is a presentation
projection; the linked saved sample records contain the complete annotations.
