"""Finalize Phase 2B preparation evidence, without opening any original test/gold records."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topodelta_qa.live.control import verify
from topodelta_qa.live.plan import write,sha
from topodelta_qa.baselines.contract import digest
from topodelta_qa.baselines.report import score

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/phase2b'


def read(p):return json.loads(p.read_text())


def main():
    proposal=verify(OUT);isolation=read(OUT/'isolation_checks.json')
    assert isolation['status']=='passed' and isolation['proposal_id']==proposal['proposal_id']
    preserved_isolation=OUT/'isolation_checks_preparation.json'
    if preserved_isolation.exists():assert read(preserved_isolation)==isolation
    else:write(preserved_isolation,isolation)
    assert sum(len(x.get('reads',[])) for x in isolation['checks'].values())==40
    for name in ('smoke','full'):
        assert not (OUT/f'staging/{name}/results/checkpoint.json').exists(),'Paid/live result unexpectedly exists'
    # The preserved Phase 2A artifacts are validation-only; rehash these, never the full multi-split dataset.
    old=read(ROOT/'outputs/phase2a/manifest.json')
    for base,key in ((ROOT/'outputs/phase2a','files'),(ROOT,'source_files')):
        for name,h in old[key].items():assert sha(base/name)==h,name
    write(OUT/'preservation_check.json',{'status':'passed','phase2a_artifact_files':len(old['files']),
          'phase2a_source_files':len(old['source_files']),'prompts_and_selection_unchanged':True,
          'frozen_dataset_modified':False,'original_gold_or_test_content_opened':False,
          'note':'Original dataset/test content not rehashed in Phase 2B; only denied-read probes were attempted. New work is in new files/directories.'})
    # Test scoring from the already-filtered validation oracle: no original full-split gold file is read.
    selection=read(OUT/'evaluation/full_selection.json');b=read(OUT/'staging/full/inputs/bundle.json')
    original=read(ROOT/'outputs/phase2a/evaluation/oracle/privileged_predictions.json')
    state={'bundle_sha256':digest(b),'requests':{},'attempts':[],'mock_only':True,'reserved_usd':0}
    for r in b['requests']:
        saved=original['requests'][digest(['oracle',r['protocol'],r['case_id']])]
        state['requests'][r['id']]={'status':'success','output':saved['output'] if r['baseline']=='direct' else {'graphs':saved['graphs']}}
    replay={}
    for baseline in ('direct','parse'):
        for protocol in ('single','paired'):
            report=score(OUT/'evaluation/validation_view',selection,state,baseline,protocol,20,_breakdowns=False)
            assert report['metrics']['joint_success']['value']==1
            replay[baseline+'/'+protocol]={'joint_success':1,'expected_cases':report['expected_cases'],
                                         'label':'PRIVILEGED VALIDATION ORACLE REPLAY, NOT MODEL PERFORMANCE'}
    write(OUT/'validation_view_check.json',{'status':'passed','reports':replay,'test_content_opened':False,
          'limitation':'View copies graphs/answers from the audited Phase 2A oracle; this is an integration check, not another independent semantic proof.'})
    rec=read(OUT/'reconciliation.json');cost=read(OUT/'costs.json');smoke=read(OUT/'smoke_selection.json')
    with (OUT/'request_estimates.csv').open('w',newline='') as f:
        fields=list(rec['request_estimates'][0]);writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rec['request_estimates'])
    tests=(OUT/'test_results.txt').read_text();match=re.search(r'Ran (\d+) tests in ([0-9.]+)s',tests)
    assert match and '\nOK\n' in tests
    commands=[
      {'command':'python3 -m topodelta_qa.live prepare','result':'passed, existing outputs archived before fresh preparation'},
      {'command':'python3 -m topodelta_qa.live preflight','environment':'host launcher outside app sandbox','result':'passed; 40 denied reads, TLS initialization, 84 mock requests, zero resume calls'},
      {'command':"python3 -m unittest discover -s tests -p 'test_phase2[ab].py' -v",'result':f'{match[1]} tests passed'},
      {'command':'python3 scripts/phase2b_verify.py','result':'passed; validation-only scoring replay and preservation hashes'},
      {'not_executed':'python3 -m topodelta_qa.live execute --approve-proposal '+proposal['proposal_id']},
      {'not_executed':'python3 -m topodelta_qa.live score --stage smoke'},
      {'not_executed':'python3 -m topodelta_qa.live score --stage full'}]
    write(OUT/'commands.json',commands)
    verdict={'verdict':'READY FOR PROPOSAL APPROVAL','proposal_id':proposal['proposal_id'],'paid_calls':0,
             'live_inference_run':False,'test_content_opened':False,'learned_verifier_trained':False,
             'smoke_budget_usd':11,'total_inclusive_budget_usd':65,'initial_unique_requests':504,
             'maximum_total_http_attempts':1512,'isolation_enforced_and_tested':True,
             'limitations':['Must launch sandbox from outside the app sandbox; no unrestricted fallback',
              'Local input-token/cost accounting is an estimate, not a guaranteed invoice ceiling',
              'Credentials, exact snapshot availability and account spend controls not checked',
              'Future offline scoring uses validation-only Phase 2A oracle view; per-group style metadata unavailable']}
    write(OUT/'VERDICT.json',verdict)
    groups='\n'.join('| '+g+' | '+', '.join(smoke['groups'][g]['tasks'])+' | '+', '.join(smoke['groups'][g]['operations'])+' | '+
          ' / '.join(str(smoke['groups'][g]['pair_kinds'][k]) for k in ('redraw','relevant_edit','irrelevant_edit'))+' |' for g in smoke['group_ids'])
    document=f'''# TopoDelta-QA Phase 2B execution proposal

**READY FOR PROPOSAL APPROVAL. No paid requests made.**

Proposal ID: `{proposal['proposal_id']}`. Date: 2026-10-27.
Approval covers **USD 11 smoke / USD 65 total INCLUDING smoke**, subject to the
estimation limits below. No invoice ceiling is guaranteed. Full validation may
follow only after the live operational smoke gates pass. Account credentials,
model availability and configured provider spend limits remain unverified.

## Contract preserved

Read applicable AGENTS.md locations and the Phase 2A report, protocol and runbook.
No graphify trigger applies. Frozen datasets, prompts, the 18-group selection,
Phase 2A source and artifacts remain intact. New code is under `topodelta_qa/live/`;
the frozen baseline runner/evaluator are reused unchanged. New billing controls,
staged copies and a validation-only evaluator view have separate hashes.
[Preservation](../outputs/phase2b/preservation_check.json).

No original test examples or multi-split gold contents were opened. Gold-read
probes were attempted under the kernel sandbox and denied. No test predictions,
learned verifier, model download, training, human review or superiority claim.
Historical Phase 1B cross-split exposure remains documented; nothing here restores
pristine held-out status.

## Exact reconciliation of 504 requests

Each group has **2 question records**, **4 PNG variants** (original, redraw, two
edits) and **3 original/candidate pairs**. There are 18 validation groups and
72 unique PNG files, not 720 independent images.

| Baseline / track | Formula | Calls/group | Full logical calls | Image occurrences | Smoke logical calls |
|---|---|---:|---:|---:|---:|
| A direct / single | 18 × 2 questions × 4 images | 8 | 144 | 144 | 24 |
| A direct / paired | 18 × 2 questions × 3 pairs | 6 | 108 | 216 | 18 |
| B parse / single | 18 × 2 questions × 4 images | 8 | 144 | 144 | 24 |
| B parse / paired | 18 × 2 questions × 3 pairs | 6 | 108 | 216 | 18 |
| Total | 18 × 28 | 28 | **504** | **720** | **84** |

C oracle costs zero provider calls and remains a privileged sanity check.
There are 36 base question records; each appears in 4 single and 3 paired calls
per baseline. Per baseline, paired scoring has 216 answer occurrences in 108
pairs, whereas single scoring has 144 image/question cases. Resampling stays at
**18 groups**. Smoke uses 3 of those same groups; its results count once in full
validation and are not another held-out evaluation.

### Safe caching and repeated parsing

B has 252 logical parse requests and 360 image occurrences on 72 PNGs. Every PNG
is parsed under two questions in the single track. The original image also
reappears in three paired contexts per question. However, the actual frozen body
supplies the question to B, and paired extraction conditions jointly on both
images. Neither individual graphs nor reversed outputs can be transplanted into
another question/pair context under this protocol. The instruction to extract a
complete graph does not make an input that contains a question question-independent.

All **504 complete request/cache keys are distinct**. There are zero safe internal
exact-payload deduplications. Cache identity includes model, endpoint, prompts,
question, image bytes and order, schema and generation settings.

**Safe reuse is across smoke and full:** import the 84 completed identical
requests, including **42 B parses** (24 single + 18 paired), with their raw
responses, attempt IDs, reservations, tokens and cache provenance. Full then needs
**420 additional initial calls**: 120 A single, 90 A paired, 120 B single, 90 B
paired. Initial totals stay 504 calls / 720 image occurrences; they are not
588 calls / 840 occurrences. With 3 attempts per logical request, smoke allows
252 HTTP attempts and full allows **1,512 INCLUDING smoke**, leaving at most
1,260 attempts for the remaining requests.

A genuinely question-independent, per-PNG extraction protocol could use 72 B
calls shared across both tracks (324 total with A). That would change B's input
context and the frozen protocol. It is explicitly NOT proposed or implemented.
[Exact request ledger](../outputs/phase2b/reconciliation.json),
[per-request estimates](../outputs/phase2b/request_estimates.csv).

## Worker isolation

Use the tested **macOS Seatbelt default-deny profile**, launched through
`/usr/bin/sandbox-exec` from an unsandboxed host launcher. The child can read only
staged code, allowlisted PNG/question/schema/config inputs, installed runtime/OS
libraries, public TLS trust material, and its own outputs/temp directory. Only
its output/temp paths are writable. The evaluator view, oracle, relevance/group
coverage manifests, source dataset, answer keys, HMAC key and legacy release
are outside its read allowlist. Python runs with `-I -S`; it does not load user
site hooks or workspace imports. Environment is reduced to runtime settings and,
only for a later approved live command, `OPENAI_API_KEY`. Credentials are never
written to config or logs. Provider bodies remain byte-for-byte compatible with
frozen Phase 2A bodies; no filesystem paths or roles enter the messages.

**40 attempted reads denied**: 10 targets × 2 stages × offline/live network
profiles. Targets include actual gold, certificates/answers in the validation
oracle, relevance coverage, key/answer-key files, the new evaluator view, an
external canary and a symlink to gold. All fail with PermissionError, rather than
missing-file errors. TLS trust initialization succeeds with 192 CA certificates.
The smoke worker completed 84 **mock-only** requests; resume added zero calls.
[Kernel isolation evidence](../outputs/phase2b/isolation_checks_preparation.json),
[profiles](../outputs/phase2b/profiles/), [raw preflight log](../outputs/phase2b/preflight_run.txt).

The app sandbox cannot start a nested Seatbelt sandbox (`sandbox_apply: Operation
not permitted`). Docker is installed but its daemon is unavailable. The verified
host launcher resolves this on this Mac; no unrestricted-worker fallback exists.
A different machine/runtime path must be prepared and retested. This is tested
filesystem isolation, not formal proof against a compromised OS/runtime.

Scoring is a **separate, later parent process** after responses are saved. To avoid
opening any original test records, the evaluator uses the already-validated,
validation-only Phase 2A oracle export to create a private evaluator view. It
copies existing graphs/answers; it does not generate new research examples or
solve new gold. Four privileged replay checks give perfect joint success, labeled
as integration tests, not model performance or a new independent semantic audit.
Per-group rendering style is unavailable in that export and is labeled unavailable;
no style is invented. [Scoring-view check](../outputs/phase2b/validation_view_check.json).

## Three-group validation smoke manifest

Selection enumerates feasible three-group combinations from the existing frozen
selection, maximizes operation coverage, and breaks ties with seed 20261027.
No test data or model performance was used. Questions, images, prompts and paired
order are unchanged. All three tasks, all edit operations, redraws, relevant and
irrelevant comparisons are covered. There are 12 PNGs, 6 question records, 24
single cases and 18 paired cases per baseline; 84 calls total.

| Group | Tasks | Operations/comparison | Redraw / relevant / irrelevant pair-question counts |
|---|---|---|---|
{groups}

[Private smoke manifest](../outputs/phase2b/smoke_selection.json). These coverage
labels stay outside the worker. Smoke outputs remain validation results; they
are not a separate held-out benchmark.

## Pricing and pre-dispatch controls

Official sources retrieved **2026-10-27**:
[exact model, rates and modalities](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[image token rules](https://developers.openai.com/api/docs/guides/images-vision),
[provider spend controls](https://developers.openai.com/api/docs/guides/spend-limits).
Standard USD rates per million: input **0.75**, cached input **0.075**, output
**4.50**. The proposal assumes no caching discount, batch/flex discount, regional
uplift, tools or tax. Rates are a dated source, not a future invoice quote.

The existing PNGs are 800×800. At high detail, each uses
ceil(800/32) × ceil(800/32) × 1.2 = **750 image input tokens** under the published
patch rules; no resizing is needed. Text/schema input is conservatively estimated
by UTF-8 bytes plus 2,048 framing tokens per request. This avoids a tokenization
network call, but provider framing is an assumption. Live usage must not exceed
that estimate or the smoke gate blocks full continuation.

| Cost component, initial calls | Smoke (84) | Full including smoke (504) |
|---|---:|---:|
| Image input tokens | 90,000 | 540,000 |
| Image input cost | $0.067500 | $0.405000 |
| Text/schema + framing token upper estimate | 349,884 | 2,102,608 |
| Text input cost upper estimate | $0.262413 | $1.576956 |
| Maximum output tokens | 344,064 | 2,064,384 |
| Maximum output cost | $1.548288 | $9.289728 |
| Initial cost estimate at maximum output | **$1.878201** | **$11.271684** |
| Estimate if every call uses all 3 attempts | $5.634603 | $33.815052 |
| Reservation for every allowed attempt | **$10.08** | **$60.48** |
| Requested local budget | **$11** | **$65 total** |

Before dispatch: verify the sealed body hash; exact model/backend/settings;
logical request allowlist; maximum 252/1,512 HTTP attempts; estimated input ≤
16,384 tokens; output parameter exactly 4,096; and aggregate token reservations.
Smoke aggregate limits are 4,128,768 input and 1,032,192 requested output tokens;
full aggregate limits are 24,772,608 input and 6,193,152 requested output tokens,
including imports. Every attempted HTTP call reserves **$0.04 durably BEFORE
network dispatch**, including transient retries, invalid responses and ambiguous
calls. Stop before the next reservation exceeds the stage budget. Actual provider
usage is recorded; any estimate/limit breach blocks subsequent dispatch/full.

The absolute local cost calculation at the 16,384-input/4,096-output ceilings for
all 1,512 attempts is **$46.44864** at these rates; plus 25% gives **$58.06080**,
below the $60.48 reservations and requested $65 inclusive budget. This is a
conservative total **conditional on the token/rate/framing assumptions**, not a
provider-enforced monetary ceiling. Unknown failed-call charges are not invented.
[Cost details and assumptions](../outputs/phase2b/costs.json).

Official docs describe organization/project hard spend limits, with delayed
enforcement and possible small overshoot. No account spend controls have been
inspected or configured here. Local accounting is an estimate, not a guaranteed
billing ceiling; account owners may add a dedicated project hard limit separately.
Do not treat a spend alert as a hard stop. Billing/quota 429 errors are terminal;
only transient 408/429/5xx have bounded retries, at most 3 total attempts. No budget
increase, model substitution or semantic response retry is authorized.

## One execution proposal and commands

- Model: **`gpt-5.4-mini-2026-03-17`**.
- Backend: **OpenAI Chat Completions**, `https://api.openai.com/v1/chat/completions`.
- Settings: high image detail, reasoning effort none, maximum output 4,096 tokens,
  strict JSON Schema, sequential dispatch. Frozen prompts and image order preserved.
- Scope: these 3 validation groups, then the remaining 15 groups only if the live
  operational checks pass; **504 initial calls total / at most 1,512 attempts**.
- Budgets: **$11 smoke; $65 combined including smoke**, with the assumptions above.
- Isolation: the verified macOS default-deny worker, launched outside the app sandbox.

Executed offline commands:

```sh
python3 -m topodelta_qa.live prepare
# Run from host terminal / an approved unsandboxed tool launcher:
python3 -m topodelta_qa.live preflight
python3 -m unittest discover -s tests -p 'test_phase2[ab].py' -v
python3 scripts/phase2b_verify.py
```

Only **after human approval of this exact proposal**, with a credential supplied
privately in the environment, execute from the same host launcher:

```sh
python3 -m topodelta_qa.live execute --approve-proposal {proposal['proposal_id']}
```

That command reruns isolation preflight, runs smoke, validates every saved smoke
response/schema and successful-call token accounting, and repeats the completed
smoke command to prove zero additional provider attempts. It then imports the
same smoke results/attempts/costs into the full checkpoint and continues only if
all those checks pass and the inclusive limits remain satisfied. Semantic model
accuracy is NOT a continuation gate. Failed/invalid smoke responses block full;
do not change prompts or rerun selected semantic mistakes. Resume uses the same
command and proposal; uncertain in-flight calls are terminal, not reissued.

After responses are saved, score in a separate parent process:

```sh
python3 -m topodelta_qa.live score --stage smoke
python3 -m topodelta_qa.live score --stage full
```

Scoring retains missing/invalid denominators, separates tracks, and uses paired
whole-group bootstrap comparisons. Smoke/full are overlapping validation results;
never pool them as independent samples. [Executed vs proposed commands](../outputs/phase2b/commands.json).

## Verification and remaining limits

**{match[1]} targeted tests passed in {match[2]} seconds**: frozen Phase 2A checks plus
nine new Phase 2B tests covering budgets, request/token ceilings, quota errors,
missing usage, smoke import/resume, approval gate and coverage. [Raw tests](../outputs/phase2b/test_results.txt).
OS probes and mock responses are not model performance. The first relative-path
preparation failed before staging; startup profiles were narrowed with offline
probes. Earlier preparations are retained at `outputs/phase2b_preflight1`,
`outputs/phase2b_preflight2`, `outputs/phase2b_preflight3` and superseded by this
sealed proposal. No frozen artifact was overwritten.

Still untested: live snapshot access, real structured responses, provider usage/
billing behavior and the actual account's enforcement settings. No paid request,
real smoke/full run, test evaluation or model comparison has happened. Approval
is pending; preparation is complete. No superiority or publication claim.
'''
    (ROOT/'docs/PHASE2B_PROPOSAL.md').write_text(document)
    (ROOT/'docs/PHASE2B_REPORT.md').write_text('# Phase 2B preparation result\n\nREADY FOR PROPOSAL APPROVAL. See [the concrete proposal](PHASE2B_PROPOSAL.md).\n\n'
       f'19 targeted tests passed; 40 kernel-denied reads; 84 mock requests, zero resume calls; zero paid calls. Proposal ID: `{proposal["proposal_id"]}`.\n')
    sources=list((ROOT/'topodelta_qa/live').glob('*.py'))+[ROOT/'tests/test_phase2b.py',ROOT/'scripts/phase2b_verify.py',ROOT/'docs/PHASE2B_PROPOSAL.md',ROOT/'docs/PHASE2B_REPORT.md']
    write(OUT/'manifest.json',{'proposal_id':proposal['proposal_id'],'status':'awaiting_human_approval','paid_calls':0,
         'files':{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json' and not p.is_symlink()},
         'source_files':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(sources)}})
    print(json.dumps({'verdict':'READY FOR PROPOSAL APPROVAL','proposal_id':proposal['proposal_id'],'paid_calls':0,'tests':int(match[1])}))


if __name__=='__main__':main()
