# Phase 2A runbook

The current protocol is [BASELINE_PROTOCOL.md](BASELINE_PROTOCOL.md). No real
inference is authorized by this work. Do not run the provider command below until
explicit model/budget authorization and input isolation are arranged.

## Commands already run locally

```sh
python3 -m topodelta_qa.baselines prepare --dataset outputs/pilot_v0.1.1 --output outputs/phase2a --config configs/baseline_pilot.json
python3 -m topodelta_qa.baselines oracle --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a/evaluation/selection.json --output outputs/phase2a/evaluation/oracle
python3 scripts/phase2a_checks.py
python3 -m unittest discover -s tests -v
```

Outputs are write-once except resumable provider checkpoints. Use a new preparation
or report path for a fresh run. The first two preflights are retained in
`outputs/phase2a_preflight1` and `outputs/phase2a_preflight2`; authoritative prepared inputs are in
`outputs/phase2a`. A schema-hash ordering regression made the first worker bundle
unusable; it never reached a provider. Its local oracle results are superseded. Preflight 2 passed the boundary/oracle
checks; a subsequent report fix made failure attribution specific to each image
in a pair. Its source-frozen bundle is retained and superseded by the final one.
An early oracle command also failed because preparation was still running; it
created no artifact. Preparation now completes before dependent commands run.
No dataset files or Phase 1B reports were overwritten.

The worker CLI has no `--dataset` argument. Only the `prepare`, `oracle`, and
`report` commands need privileged dataset access. `run` imports worker-safe code
only. Inputs under `worker/` comprise one JSON bundle and metadata-free PNGs;
`evaluation/selection.json`, oracle outputs and all reports stay off the worker.
The JSON bundle carries opaque runner IDs but those do not enter provider bodies.
The request builder ignores all filesystem metadata and rejects unknown fields.

## Before a real run

1. Authorize a model/provider and a USD limit. Suggested snapshot/settings and
   exact call/token ceilings are in the protocol and `proposal_counts.json`.
2. Verify that the account can serve the exact snapshot with images and strict
   JSON Schema. Recheck account pricing and compute a conservative per-attempt
   reservation, including schema/prompt/image input, the full output ceiling and
   any provider uplift. Configure `reserve_per_attempt_usd` and `reserve_basis` in
   a NEW copy of `configs/baseline_pilot.json`. The checked-in nulls intentionally
   block dispatch. Never place a credential value in this file.
3. Prepare a NEW bundle with that configuration. This freezes budget, model,
   prompts, code, schemas, question text and PNG hashes. Editing a prepared bundle
   invalidates its evaluation identity; do not edit the existing one.
4. Mount only the worker bundle, installed Python/package and a private output
   directory into a new container/account. Exclude this workspace, old releases,
   SVGs, evaluator gold/key, selection manifest, oracle, audit and review materials.
   Supply the configured credential environment variable via a secret manager or
   shell environment without recording its value. No automatic model downloads.
5. Execute once and resume using the identical output directory and bundle.
   Cached completions and failed/invalid/uncertain terminal requests are skipped.
   No automatic semantic repair. A crash during dispatch creates an uncertain
   failure that is NOT retried. Cache/checkpoint/raw JSON files remain private.

Example commands for that **later authorized** run (not executed):

```sh
python3 -m topodelta_qa.baselines prepare --dataset outputs/pilot_v0.1.1 --output outputs/phase2a_authorized --config configs/baseline_authorized.json
# In the isolated worker environment, with credentials supplied externally:
python3 -m topodelta_qa.baselines run --worker /inputs/worker --output /results/run --authorize-provider
# Resume: invoke the same command with the same input and output paths.
```

For an explicitly local backend, select `provider=openai_compatible`, a loopback
Chat Completions URL, and an exact locally installed model identifier. A loopback
endpoint may omit credentials. It still needs explicit authorization, budget
settings and verified image/schema support; the harness never downloads models.
HTTPS is required for remote endpoints; redirects are rejected.

## Offline scoring after returning results

Run each report separately; keep single and paired protocols separate. Example
unexecuted commands (substitute the authorized selection and returned checkpoint):

```sh
python3 -m topodelta_qa.baselines report --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a_authorized/evaluation/selection.json --checkpoint /results/run/checkpoint.json --baseline direct --protocol single --output outputs/direct_single.json
python3 -m topodelta_qa.baselines report --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a_authorized/evaluation/selection.json --checkpoint /results/run/checkpoint.json --baseline parse --protocol single --output outputs/parse_single.json
python3 -m topodelta_qa.baselines report --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a_authorized/evaluation/selection.json --checkpoint /results/run/checkpoint.json --baseline direct --protocol paired --output outputs/direct_paired.json
python3 -m topodelta_qa.baselines report --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a_authorized/evaluation/selection.json --checkpoint /results/run/checkpoint.json --baseline parse --protocol paired --output outputs/parse_paired.json
python3 -m topodelta_qa.baselines compare --a outputs/direct_single.json --b outputs/parse_single.json --output outputs/comparison_single.json
python3 -m topodelta_qa.baselines compare --a outputs/direct_paired.json --b outputs/parse_paired.json --output outputs/comparison_paired.json
```

Reports preserve expected denominators and include all metric numerators, group
contributions, confusion/abstention counts, task/operation/size/layout slices,
resource accounting and group confidence intervals. The comparisons use identical
sampled group IDs for both baselines. JSON reports from mocks are labeled **MOCK
ORCHESTRATION ONLY, NOT MODEL PERFORMANCE**. Oracle reports are explicitly privileged.

Single-image operation slices omit derived pair/change metrics: selecting only
images with one operation cannot supply two independent single-image answers.
Task slices and all paired-operation slices include pair/change metrics. Layout
has only one family (circular); base style is a group attribute, not a claim that
redraws use the same style. Parse scores count image occurrences; repeated images
within paired cases are not independent graphs. Latency is measured per HTTP
attempt and summed; it is not GPU time. Tokens/costs remain unknown when unavailable.

Keep real test predictions absent until a later explicit test release after a
prompt/protocol freeze. `prepare --split test` refuses without `--release-test`;
that flag is a deliberate research release action, not a way to hide the prior
cross-split exposure documented in the protocol. Do not tune on test outputs or
remove items based on their scores.
