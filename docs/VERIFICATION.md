# Recorded Phase 1 verification

Executed locally on 2026-10-27. These are automated software and synthetic-data
checks. They are not human readability findings or model benchmark scores.

## Completed deliverables

The package, CLI, pinned environment/config, independent semantic reference
algorithms, evidence validators, SVG/PNG renderer, generation/rejection logs,
separate public/gold exports, structural audit, contact sheet, dataset card, and
protocol-separated evaluator are implemented.

The accepted pilot is `outputs/pilot/`:

| Item | Observed count |
|---|---:|
| Attempted groups | 209 |
| Rejected groups | 89 |
| Accepted groups | 120 |
| PNG diagrams | 480 |
| SVG diagrams | 480 |
| Shared questions | 240 |
| Single-image question cases | 960 |
| Ordered paired-image question cases | 720 |
| Train / validation / test groups | 84 / 18 / 18 |
| Reachability / shortest-path / direct-edge questions | 80 / 80 / 80 |
| Addition / deletion / reversal operations | 80 / 80 / 80 |
| Redraw / relevant-edit / irrelevant-edit question-pairs | 240 / 142 / 338 |
| Exact cross-split isomorphism duplicates | 0 |

Accepted original node sizes span 6–12. Their counts are 20, 27, 28, 25, 13, 6,
and 1, respectively. This skew is a rendering-acceptance limitation, not evidence
of balanced difficulty. The contact sheet's first 12 groups cover every task,
every edit operation, and all three rendering styles.

## Rejections and failures

| Rejection reason | Count |
|---|---:|
| Hidden or ambiguous arrowhead | 61 |
| Edge-node or arrow-node intersection | 23 |
| No valid operand for scheduled edit | 4 |
| Exact cross-split isomorphism duplicate | 1 |

Each rejection retains its attempt number and reason. No sample was relabeled to
reach the quota. No automated checks remain failing. The test suite deliberately
forces budget exhaustion and checks that partial records and an explicit failure
report survive; this is a tested failure path, not a failure of the delivered run.

## Executed checks

`python3 -m unittest discover -s tests -v` passed **17 tests**, with zero failures
(last recorded run: 4.973 seconds). Raw output: `outputs/test_results.txt`.

Tests cover all three edit operations and preconditions, reversal delta semantics,
question-conditioned mixed relevance, positive/negative/unreachable answers,
alternative valid paths, explicit absence certificates, invalid evidence,
rendering rejection/tampering, group isolation, exact isomorphism beyond degree
signatures, prediction format errors, wrong and missing answers, independent
certificate/delta penalties, empty-set behavior, group-bootstrap determinism,
repeat-generation byte equality, refusal to overwrite, and visible exhaustion.

The final saved pilot passed all 14 reported check categories: manifest hashes,
independent semantics, certificates, exact edit deltas, mixed relevance, scene
geometry, unchanged geometry, SVG primitives, PNG primitives, pixel differences,
split isolation, exact directed isomorphism, inference allowlists, and attempt
accounting. Validation additionally recomputes the saved structural audit and
checks rejection-reason totals. See `outputs/pilot_validation.json`.

Two complete 120-group runs into `outputs/release` and `outputs/release_repeat`
produced identical relative-file inventories and identical SHA-256 hashes for
**all 1,213 files**, including the manifest. The validated release was moved to
`outputs/pilot` without changing its contents. Earlier generated runs were moved
to a system temporary directory; they are not additional dataset releases.
See `outputs/reproducibility.json`.

The CLI installed successfully with no network dependency resolution:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e .
.venv/bin/topodelta --help
```

The installed console entry point successfully ran `audit` and both `evaluate`
protocols. CLI audit equaled the sealed audit report. Empty prediction files
retained all 960 single-image and 720 paired-image cases, scored applicable metrics
zero, and reported missing counts. Single-image edge-delta metrics remained null.
These are deliberately empty prediction fixtures, not model outputs:

```sh
.venv/bin/topodelta audit --dataset outputs/pilot --output outputs/audit_check.json
.venv/bin/topodelta evaluate --dataset outputs/pilot --predictions outputs/empty_predictions.jsonl --protocol single --output outputs/empty_prediction_single_check.json
.venv/bin/topodelta evaluate --dataset outputs/pilot --predictions outputs/empty_predictions.jsonl --protocol paired --output outputs/empty_prediction_paired_check.json
```

The test suite separately verifies gold-derived oracle fixtures and deliberately
wrong answers/certificates/deltas. Such fixtures test implementation correctness;
their perfect or imperfect scores are not research results.

## Exact reproduction

Use CPython 3.12.6 and the versions in `requirements.txt`. The manifest additionally
records FreeType/zlib versions and the bundled font hash. From the project root:

```sh
python3 -m unittest discover -s tests -v
python3 -m topodelta_qa generate --config configs/pilot.yaml --output outputs/pilot_repeat
python3 -m topodelta_qa validate --dataset outputs/pilot_repeat
python3 -m topodelta_qa audit --dataset outputs/pilot_repeat
python3 -c 'import json; from pathlib import Path; assert json.loads(Path("outputs/pilot/manifest.json").read_text()) == json.loads(Path("outputs/pilot_repeat/manifest.json").read_text()); print("reproduction passed")'
```

`outputs/pilot_repeat` must not already exist. To evaluate real predictions, use
that protocol's public IDs and prediction format from `inference/README.md`:

```sh
python3 -m topodelta_qa evaluate --dataset outputs/pilot --predictions predictions.jsonl --protocol single --split test
python3 -m topodelta_qa evaluate --dataset outputs/pilot --predictions paired_predictions.jsonl --protocol paired --split test
```

## Unperformed work and remaining research decisions

Human visual review has **not** occurred. Automated geometry checks and agent
inspection of the contact sheet are not a human validation study. No VLM was run,
no paid API was called, no model was downloaded, nothing was remotely published or
deployed, and the proposed learned verifier was not built. Novelty and method
superiority are unverified hypotheses.

Decisions remain on a human readability protocol; richer layouts, labels, graph
families and reciprocal edges; balancing answer/relevance distributions; model
baseline selection and prompting; evidence elicitation; external held-out data;
novelty assessment; and release licensing. See the dataset card for the sampling,
visual diversity, and synthetic-domain limitations.
