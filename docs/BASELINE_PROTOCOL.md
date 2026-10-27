# TopoDelta-QA Phase 2A baseline contract, revision 1

Status: frozen initial prompts; no real inference authorized or performed. Dataset:
`outputs/pilot_v0.1.1`, 120 existing groups. Never regenerate or edit these examples.
This document is written before any Phase 2A inference, including oracle execution.

## Tracks and input boundary

Single-image: one PNG + generated question -> answer and certificate. Paired-image:
two PNGs + question -> answers/certificates in presented order, signed directed
edge delta from Image A to Image B, and explicit boolean `answer_changed`.
A seeded hash of the pair ID chooses the order, shared by A/B/C baselines. Labels
are only Image A and Image B. Addition means present in B and absent in A; deletion
means present in A and absent in B. Reversing presentation swaps additions and
deletions. Redraws allow both lists empty. Neither role nor operation is disclosed.

Provider bodies contain only PNG data URIs, generic task instructions, the question,
neutral image labels, JSON Schema, model ID and generation settings. IDs, paths,
timestamps, roles, split, gold graphs/labels/certificates, SVGs, HMAC key, source
metadata, old releases, reports and review packets never enter provider bodies.
Preparation re-encodes pixels into metadata-free PNGs. Run only the exported worker
bundle in a separate account/container with no workspace/gold/legacy mount; the
runner's allowlist is an application boundary, not an OS security sandbox. The
privileged coordinator and oracle must run separately. The worker needs the package,
its frozen prompts/config and bundle only. Provider credentials come from environment
variables and are excluded from logs. Do not give an agent provider filesystem tools.

## Baselines and certificates

A (direct VLM) receives the question and images and emits the semantic response.
B (parse-then-solve) uses the **same model, high image detail, max token limit,
reasoning setting and strict JSON Schema mode** to extract every visible node label and
directed edge from each presented image, then uses BFS and set operations locally.
Both make one call per case; B repeats extraction across questions/pairs to keep
case conditioning explicit. Different prompts/output lengths mean these are NOT
compute-matched. Calls, image occurrences, tokens, latency and costs are reported.
C (oracle graph) uses privileged gold graphs and the same deterministic B solver;
it is an evaluator sanity check, never an image-based competitor.

All baselines use the same deterministic public-template question parser, applied
to question TEXT, including for oracle. A sees the text; no baseline is silently
given gold endpoints. Assumption: the three exact generated templates cover this
pilot. Unknown templates fail visibly; this is not general language understanding.
B graph extraction uses no gold node count, labels, endpoints or graph constraints
beyond unique string labels, simple directed edges and no self-loops. Missing query
endpoints make solving fail, rather than silently treating them as unreachable.

Direct response fields are `answer,certificate` (single), or
`answers,certificates,delta,answer_changed` (paired). Certificates use:

- Reachability true: `{kind:"path",path:[source,...,target]}`; any simple directed path.
- Reachability false / shortest `"unreachable"`:
  `{kind:"reachable_set",nodes:[all and only source-reachable labels, including source]}`.
- Finite shortest: `{kind:"shortest_path",path:[source,...,target],distances:[{node:"label",distance:integer_or_null},...]}`.
  Exactly one entry per visible node, source 0, target equal answer/path length,
  and each edge out of a finite node ends at finite potential ≤ source potential+1.
- Direct edge: `{kind:"edge_claim",source:"label",target:"label",present:boolean}`.

The array of distances is the provider wire format (strict structured outputs
cannot express arbitrary required label keys); convert it losslessly to the legacy
evaluator's dictionary. Duplicate labels are invalid. No gold evidence is supplied.
Extraction output is `{graphs:[{nodes:[labels],edges:[[tail,head],...]}]}` in image
order. Schemas use closed objects; local validation additionally enforces list
lengths, types, unique edges/labels and certificate structure. Semantic certificate
truth is checked against gold only in the separate evaluation process.

## Evaluation and contradictions resolved

The frozen v0.1.1 evaluator expects original-first pairs and has no explicit change
field. Keep it unchanged. The Phase 2A bridge reverses predicted answers/evidence
and swaps added/deleted lists when needed. Legacy pair accuracy requires BOTH
answers correct. Phase 2A paired joint additionally requires a valid, correct
`answer_changed`. Report the legacy joint separately. Missing, failed, malformed,
truncated, refused, invalid-schema and incomplete records remain in all primary
expected-case denominators. A schema-invalid response contributes zero as a whole;
a schema-valid but semantically wrong certificate only fails its applicable metrics.
Single change scores are derived from two valid single answers; they are not a
single-image explicit change task. Never pool tracks or their sample units.

Answer-change metrics: accuracy, positive precision/recall/F1, specificity,
balanced accuracy, confusion counts and missing/invalid counts. Abstentions are
wrong in primary accuracy, count against recall/specificity in their gold class,
and are not silently treated as predicted negatives. Undefined precision is null.
Directed delta P/R/F1 follows the frozen evaluator: both empty = 1; exactly one
empty or missing = 0. Evidence alternatives accepted. Parse metrics use exact
labeled graph/node/edge quality per image occurrence against gold; invalid parses
score zero. Extra nodes/edges count as errors. Break down task, operation, node
count and layout/style with whole-group bootstrap. A vs B uses the SAME sampled
group IDs for paired differences; 1,000 percentile resamples, seed 20261027.
Intervals/differences on 18 groups are preliminary, not superiority claims.

Failures: graph mismatch establishes reconstruction/perception error in B; correct
parsed graph but wrong derived semantics establishes implementation/solving error.
Missing endpoints establish solver input failure. For A, wrong answers alone do
not establish perception versus reasoning. Delta/change/certificate failures are
observable outcomes, not asserted latent causes. Do not filter test items by results.

## Splits, freezing and prior exposure

Use existing 84 train / 18 validation / 18 test groups; select ALL 18 validation
groups because the split is smaller than 24, with no reallocation. The selection
manifest reports task/operation/size/layout strata and seeded ordering. Tune future
prompts on train/development only, versioning each change. This revision is written
from task definitions, with no VLM outputs. Hash prompts, schemas, settings, this
protocol and selected input pixels in each bundle; any change requires a new run.
Test prediction generation is disabled unless an explicit later test-release flag
is supplied after freezing. No test predictions are produced in Phase 2A.

Prior exposure: Phase 1B examined gold/distributions across all splits and agent
visually inspected 30 groups including four test groups. Source/dataset authors and
this agent have had gold access. Oracle sanity checks below use validation only.
We cannot establish pristine held-out test evaluation. Isolated future VLM calls
will have no gold context, but this is not an uncontaminated research development
history. Human reviews remain blank and no human validation is claimed.

## Execution, billing and resume

No paid inference is authorized. Offline preparation, unit mocks and privileged
oracle checks may run. Provider execution requires an explicit authorization flag,
environment credential (unless an explicitly local unauthenticated endpoint),
a configured exact model, positive USD limit, and a documented conservative USD
reservation per HTTP attempt. Unknown/unconfigured bounds fail closed. Reserve
BEFORE dispatch, including retries, invalids and uncertain calls. A reservation is
not measured cost. Provider-reported cost is nullable and never fabricated; log
usage and optional cost only when present. A local spending ledger cannot enforce
a provider invoice cap if the configured bound is false; verify rates/input limits
and set provider-side controls before authorization. Never claim an exact quote.

Cache keys include provider endpoint identity, exact model, prompts, ordered image
hashes, question, schema and settings. Atomic checkpoint writes + exclusive run
lock prevent concurrent dispatch. Successful and invalid/failed completions are
terminal; resume skips them. A crash with a dispatch in flight is marked uncertain
and NOT automatically reissued. Providers may not deduplicate requests: a stable
logical ID plus unique attempt IDs supply traceability, not exactly-once billing.
Only transient HTTP 408/429/5xx are retried, at most 3 attempts, sequential capped
backoff. Transport ambiguity is terminal. No semantic correction/retry or selective
rerunning to improve scores. Raw provider JSON is preserved with credentials
redacted; headers and authorization never are. Caches/checkpoints are private.

## Concrete initial run proposal (not authorization)

Propose OpenAI Chat Completions, exact snapshot `gpt-5.4-mini-2026-03-17`,
`reasoning_effort=none`, `max_completion_tokens=4096`, image detail `high`, no
sampling-temperature override, strict JSON Schema, sequential requests, up to
three attempts. An explicit OpenAI-compatible endpoint is also supported, but
must support the same image/schema contract; configure and freeze another model
and endpoint rather than silently substituting a model. No model is downloaded.
Model/account availability has not been probed with a paid request.

Validation includes 144 single cases and 108 paired cases per baseline. Run A and
B on both tracks: 504 initial calls, 720 image occurrences; at most 1,512 HTTP
attempts. Maximum requested output is 2,064,384 tokens initially or 6,193,152 with
three attempts on every request. Cache hits may reduce calls; report actual counts.
The suggested USD 40 local reservation cap is a proposal only. The per-attempt
reservation and its verified input-token/rate basis are deliberately unset, so
execution fails closed until they are supplied in a new frozen bundle. If that
cap cannot cover the verified worst-case reservations, revise the proposal or
accept an explicitly incomplete run; do not silently drop unattempted cases.

Cost proposal: C = (uncached input tokens × input rate + cached input tokens ×
cached rate + output tokens × output rate) / 1,000,000, including billed image
input tokens and all charged retries. The published snapshot page currently lists
USD 0.75 / 0.075 / 4.50 per million tokens; these are indicative rates checked
2026-10-27, not a quote, measured costs, or account eligibility. At those rates the
output-only ceiling is about USD 9.29 initially / USD 27.87 with all retries;
input/image costs are additional and not yet measured. Verify current account
pricing, image tokenization, discounts/uplifts and a conservative per-attempt input
bound before setting reservations. Provider-reported costs remain null if absent.

Official references: [model/snapshot, modalities and rates](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[Chat Completions structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat),
[PNG data URI and image detail](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat).
These docs were consulted read-only; no provider endpoint was invoked.
