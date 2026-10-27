# Evaluation definitions

Results always name one protocol and one split. The evaluator validates the sealed
dataset before scoring. Ground truth is evaluator-only. No model inference is
performed. Synthetic oracle fixtures in the tests exercise the evaluator; they
are not empirical benchmark results.

## Protocols and units

**Single image:** one prediction per unique image-question case (960 in the full
pilot). Answer accuracy and certificate validity use these cases. Pair metrics
look up two independently collected single-image predictions. No image other
than the current row may be supplied to a single-image model call. Edge deltas
are not requested by this protocol; their scores are null, not inferred or zero.

**Paired images:** one prediction per ordered reference/candidate/question tuple
(720 in the full pilot). A row contains two answers, two certificates, and a signed
directed edge delta. Per-image accuracy averages the 1,440 image-question
**occurrences**, including repeated reference images. This unit differs from
single-image accuracy. The evaluator never averages the protocols together.

Public IDs and split/group membership are runner metadata. Opaque IDs link model
outputs to gold without exposing graph structure, role, or relevance. The current
question and images determine the requested answer. Pairs always use original
as reference and redraw or independently edited original as candidate.

## Accuracy and agreement

An answer is correct only if its JSON type and value match the deterministic gold.
Reachability and direct-edge tasks require booleans. Shortest path requires a
nonnegative integer, or exactly the string `"unreachable"`. Booleans are not
integers for scoring. String `"true"`, null, and numeric strings are invalid.

- **Per-image answer accuracy:** number of correct answers / expected image-question units.
- **Raw redraw agreement:** redraw pairs with two valid, equal predictions / expected
  redraw pairs. Both answers can agree while being wrong. Two missing/invalid
  answers do not agree.
- **Redraw pair accuracy:** redraw pairs with both answers correct / expected redraw pairs.
- **Relevant-edit pair accuracy:** original/edited/question pairs whose deterministic
  answer changes, with both answers correct / all such pairs.
- **Irrelevant-edit pair accuracy:** original/edited/question pairs whose deterministic
  answer stays the same, with both answers correct / all such pairs.

Edit relevance is question-conditioned **answer change**. It is not membership in
one arbitrary supporting path. An edit can alter supporting evidence without
changing the answer. Changed edges are not treated as answer certificates.

## Signed edge delta

Represent each directed addition as `(added, source, target)` and deletion as
`(deleted, source, target)`. A reversal contributes two different signed items.
Compare predicted set P with gold set G. With both nonempty:

`precision = |P ∩ G| / |P|`, `recall = |P ∩ G| / |G|`,
`F1 = 2PR / (P + R)`, with F1 = 0 if there is no true positive.

If both sets are empty, all three scores are 1. If exactly one set is empty, all
three scores are 0. This explicitly defines the empty-gold recall convention.
Report the mean of each per-pair precision, recall, and F1 (macro over expected
question-pairs), not F1 recomputed from the mean precision and recall. Since each
image pair has two questions, its delta occurs twice. Redraw empty sets are
included, so delta metrics must be read alongside the pair-kind audit counts.
**Exact delta accuracy** additionally requires P = G.

Malformed delta fields, duplicate edges within a list, unknown endpoints, loops,
or claiming the same directed edge as both added and deleted make the delta
invalid. Missing or invalid deltas score zero, even for a true empty redraw.

## Certificate validity

A certificate is valid if it proves the submitted answer in the candidate graph.
Validity is the fraction of expected answer units with valid certificates. A
wrong answer cannot have a valid certificate. There is no exact matching against
the stored gold certificate; any valid path or potential can be submitted.

- Positive reachability: a simple path with the requested endpoints; every edge
  must exist in the directed order. A shortest path is not required.
- Negative reachability and unreachable shortest path: the complete reachable
  set from the source, including the source, excluding the target. Independent
  BFS checks exact completeness, including rejection of unreachable extras.
- Finite shortest path: a directed simple path of the submitted length, plus
  potentials for every graph node. Source potential is 0; target potential equals
  the length; all finite potentials are nonnegative integers. For every edge from
  a finite node, its destination is finite with potential at most source + 1.
  The path gives the upper bound and the potentials prove the lower bound.
  True shortest distances with null for unreachable nodes are one valid choice.
- Direct edge: explicit source, target, and boolean presence/absence claim.

An empty path, empty evidence object, or empty reachable set does not prove absence.
Certificates use labels visible in images. Gold certificates are never model inputs.

## Joint success

For single image, joint success is the fraction of expected cases with both a
correct answer and a valid certificate. For paired image it is the fraction of
expected pairs with **both** answers correct, **both** certificates valid, and
**exactly** the correct signed edge delta. These are protocol-specific definitions.
A merely consistent redraw does not satisfy joint success.

## Missing, malformed, and ambiguous submissions

Every expected case stays in its denominator. Omitted cases score zero for every
applicable metric. Wrong or invalid answers, invalid certificates, and invalid
deltas are counted and penalized separately; a missing certificate does not erase
a correct answer's accuracy. Missing paired answer/certificate arrays, or arrays
not of length two, make both respective fields missing.

Malformed JSON lines and rows without a string ID are counted and ignored; the
expected cases they fail to supply still score zero. Unknown IDs, repeated IDs,
and missing/mixed protocol labels cause a visible error instead of selecting an
arbitrary prediction. These errors are not silently converted into scores. Rows
from nonselected splits are explicitly counted and excluded from scoring. A file
containing only test predictions can be evaluated with `--split test`.

## Group-bootstrap confidence intervals

All contributions retain their group ID. Sample N groups with replacement from
the N selected groups, retaining every variant, question, and pair contribution
of each sampled group. Recompute each numerator/denominator ratio per replicate.
Use linear-interpolated 2.5th and 97.5th percentiles for a 95% interval. The default
is 1,000 replicates and the dataset config's seed; both can be overridden on the CLI.
A replicate with no applicable denominator is undefined for that metric and
excluded, with the number of defined replicates recorded. Metrics with no
applicable cases have null values and intervals. Intervals reflect synthetic
group sampling variability, not human reliability or external-domain performance.
