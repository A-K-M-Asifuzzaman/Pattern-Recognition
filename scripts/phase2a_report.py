"""Build the readable Phase 2A delivery report from recorded offline evidence."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topodelta_qa.baselines.contract import digest, schema
from topodelta_qa.baselines.prepare import write

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/phase2a'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())


def main():
    selection=read(OUT/'evaluation/selection.json');bundle=read(OUT/'worker/bundle.json')
    oracle={p:read(OUT/f'evaluation/oracle/{p}.json') for p in ('single','paired')}
    assert digest(bundle)==selection['bundle_sha256']
    assert all(r['metrics']['joint_success']['value']==1 for r in oracle.values())
    assert read(OUT/'boundary_checks.json')['status']=='passed'
    assert read(OUT/'hand_oracle_checks.json')['status']=='passed'
    tests=(OUT/'test_results.txt').read_text()
    match=re.search(r'Ran (\d+) tests in ([0-9.]+)s',tests)
    assert match and '\nOK\n' in tests
    assert not (ROOT/'outputs/phase2a_provider_not_authorized').exists()
    assert 'No provider inference authorized' in (OUT/'authorization_gate_check.txt').read_text()
    preservation={}
    for name,root in [('original',ROOT/'outputs/pilot'),('corrected',ROOT/'outputs/pilot_v0.1.1'),
                      ('snapshot',ROOT/'outputs/versions/phase1-v0.1.0'),('phase1b_reports',ROOT/'outputs/phase1b')]:
        manifest=read(root/('snapshot.json' if name=='snapshot' else 'manifest.json'))
        mismatches=[relative for relative,expected in manifest['files'].items() if not (root/relative).is_file() or sha(root/relative)!=expected]
        assert not [p for p in mismatches if p!='.DS_Store'],(name,mismatches)
        preservation[name]={'inventoried_files':len(manifest['files']),'content_changes_excluding_finder_metadata':[p for p in mismatches if p!='.DS_Store'],
                            'finder_metadata_changes':[p for p in mismatches if p=='.DS_Store'],
                            'manifest_sha256':sha(root/('snapshot.json' if name=='snapshot' else 'manifest.json'))}
    write(OUT/'preservation.json',preservation)
    # Preserve the pre-existing README exactly, checked against the Phase 1B source inventory.
    prior=(ROOT/'README.md').read_text().split('\n\n## Phase 2A baseline harness\n')[0]
    prior_hash=hashlib.sha256(prior.encode()).hexdigest()
    old=read(ROOT/'outputs/phase1b/manifest.json')['source_files']
    expected=old.get('README.md')
    if expected:
        assert prior_hash==expected,(prior_hash,expected)
    (OUT/'README_before_phase2a.md').write_text(prior)
    write(OUT/'freeze.json',selection['freeze'])
    schemas={f'{r["baseline"]}/{r["protocol"]}/{r["question"].split(" from ")[0]}':schema(r['baseline'],r['protocol'],r['question']) for r in bundle['requests']}
    write(OUT/'output_schemas.json',schemas)
    with (OUT/'oracle_metrics.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['protocol','metric','value','numerator','denominator','ci95','label'])
        for p,r in oracle.items():
            for name,v in sorted(r['metrics'].items()):
                writer.writerow([p,name,v['value'],v.get('numerator'),v.get('denominator'),json.dumps(v['ci95']),r['label']])
    with (OUT/'oracle_breakdowns.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['protocol','stratum','metric','value','denominator','ci95','label'])
        for p,r in oracle.items():
            for key,metrics in sorted(r['breakdown'].items()):
                for name,v in sorted(metrics.items()):
                    writer.writerow([p,key,name,v['value'],v.get('denominator'),json.dumps(v['ci95']),r['label']])
    commands=[
      {'command':'python3 -m topodelta_qa.baselines prepare --dataset outputs/pilot_v0.1.1 --output outputs/phase2a --config configs/baseline_pilot.json','exit':0,'note':'Executed three times with prior outputs archived, never overwritten'},
      {'command':'python3 -m topodelta_qa.baselines oracle --dataset outputs/pilot_v0.1.1 --selection outputs/phase2a/evaluation/selection.json --output outputs/phase2a/evaluation/oracle','exit':0},
      {'command':'python3 scripts/phase2a_checks.py','exit':0},
      {'command':'python3 -m unittest discover -s tests -v','exit':0},
      {'command':'python3 -m topodelta_qa validate --dataset outputs/pilot_v0.1.1 --output outputs/phase2a/dataset_validation.json','exit':0,'evidence':'../phase2a_preflight2/dataset_validation.json; source root unchanged, final artifact hashes rechecked'},
      {'command':'python3 -m topodelta_qa.baselines run --worker outputs/phase2a/worker --output outputs/phase2a_provider_not_authorized','exit':1,'note':'Expected authorization rejection before directory creation or credential/provider access'},
      {'command':'python3 scripts/phase2a_report.py','exit':0}]
    write(OUT/'commands.json',commands)
    verdict={'verdict':'READY FOR AUTHORIZED INFERENCE','real_inference_performed':False,'provider_calls':0,
             'learned_verifier_trained':False,'test_predictions_produced':0,'human_validation':False,
             'remaining_requirements':['Explicit provider/model/budget authorization','Credential or authorized preinstalled local backend',
                                       'Verified per-attempt reservation and cost basis in a new frozen bundle','Actual worker filesystem isolation',
                                       'Account snapshot/image/schema compatibility confirmation'],
             'ran':['31 local unit tests','18-group validation privileged oracle','504 request-body boundary checks','Hand-calculated semantic fixtures',
                    'Empty-prediction fixed-denominator checks','Frozen dataset validation and preservation hashes','Expected unauthorized-run rejection'],
             'did_not_run':['Real direct VLM inference','Real graph extraction inference','Real A-vs-B comparisons','Test inference','Model training/download','Paid APIs','Human review']}
    write(OUT/'VERDICT.json',verdict)
    rows=[]
    for name in ('per_image_answer_accuracy','redraw_pair_accuracy','raw_redraw_agreement','relevant_edit_pair_accuracy',
                 'irrelevant_edit_pair_accuracy','answer_change_accuracy','edge_delta_f1','certificate_validity','joint_success','parse_graph_exact_accuracy'):
        vals=[]
        for p in ('single','paired'):
            v=oracle[p]['metrics'][name]
            vals.append('n/a' if v['value'] is None else f'{v["value"]:.3f} ({v.get("denominator","class ratios")})')
        rows.append('| '+name+' | '+' | '.join(vals)+' |')
    strata=selection['strata']
    report=f'''# TopoDelta-QA Phase 2A delivery

**Verdict: READY FOR AUTHORIZED INFERENCE.** No real inference is authorized or
performed. This is harness/protocol readiness, not a completed model benchmark or
publication readiness. Date: 2026-10-27.

[Protocol](BASELINE_PROTOCOL.md), [runbook and exact commands](BASELINE_RUNBOOK.md),
[frozen prompt files](../prompts/phase2a/), [source](../topodelta_qa/baselines/),
[tests](../tests/test_phase2a.py), [selected groups](../outputs/phase2a/evaluation/selection.json),
[freeze hashes](../outputs/phase2a/freeze.json), [wire schemas](../outputs/phase2a/output_schemas.json).

## What ran

**{match[1]} tests passed in {match[2]} seconds** ([raw output](../outputs/phase2a/test_results.txt)).
Ten Phase 2A tests cover HTTP serialization via mocks, allowlists, strict JSON/schema
and query parsing, both presentation orders, redraw/reversal deltas, hand-computed
semantics, PNG metadata stripping, schema-hash ordering, safe cache/resume, failures,
retries, secret redaction, reservation overrun, test-release gate, fixed denominators,
explicit change in joint success, parse reconstruction/input failures and paired
bootstrap behavior. Existing tests use temporary fixtures; the frozen pilot was
not regenerated or modified.

Offline checks: **504 provider bodies**, **72 metadata-free PNGs**, **360 selected
image occurrences** compared pixel-for-pixel against v0.1.1; zero forbidden
metadata in the allowlisted requests. Pair ordering: **51 forward / 57 reversed**.
All 504 payload/cache keys are distinct. No provider body contains public case/group
IDs, source filenames, SVG, timestamps, gold annotations or role/operation labels.
[Boundary evidence](../outputs/phase2a/boundary_checks.json). The actual OS sandbox
for a future runner has NOT been deployed; copy/mount only the worker inputs.

Empty-output fixtures retain 144 single cases and 108 paired cases (216 answer
occurrences), with 108 answer-change comparisons in both tracks. Primary answer,
certificate, joint and change accuracy stay zero. These are denominator tests,
not model performance. [Evidence](../outputs/phase2a/empty_denominator_checks.json).

The unauthorized CLI invocation exited 1 before any output directory, credential
read or network dispatch. Mocks exercised adapters without network calls. Six
independent hand-calculated single cases, a diamond with alternative routes,
negative/unreachable cases, deletion/reversal and both presented orders test the
oracle/bridge against explicit expected values, rather than gold generated by
that solver. [Hand calculations](../tests/fixtures/phase2a_hand_cases.json),
[recorded checks](../outputs/phase2a/hand_oracle_checks.json).

## Privileged oracle sanity check

The oracle parsed the same public question TEXT used by A and B and solved gold
graphs with the deterministic extraction solver. It did not copy saved gold
answers/certificates as predictions. It is privileged access, NOT an image-based
competitor. Zero provider calls, no measured API cost. Validation only; no real
test predictions. There are 18 groups, 144 single cases and 108 paired cases.
All applicable semantic success metrics are perfect, and invalid/failure rates
are zero. The [single JSON](../outputs/phase2a/evaluation/oracle/single.json),
[paired JSON](../outputs/phase2a/evaluation/oracle/paired.json),
[metric CSV](../outputs/phase2a/oracle_metrics.csv) and
[breakdown CSV](../outputs/phase2a/oracle_breakdowns.csv) retain numerator/denominator,
strata, uncertainty, confusion and group contributions.

| Oracle metric | Single value (denominator) | Paired value (denominator) |
|---|---:|---:|
{chr(10).join(rows)}

Oracle success intervals are [1,1] under 1,000 group resamples. This is a sanity
property, not empirical evidence of image-model generalization. Paired comparisons
are implemented with the same resampled group IDs for both models; no real A/B
comparison exists yet. A self-comparison regression checks zero difference.

## Selection and exposure

All existing validation groups are used because 18 < 24. Seed 20261027 controls
selection order and pair order; no split reallocation or performance filtering.
No training/development prompt tuning using model outputs occurred. Base-question
strata: {dict(strata['task'])}. Edited-variant operations: {dict(strata['operation'])}.
Node counts across 72 variants: {dict(strata['nodes'])}. Layout/styles:
{dict(strata['layout_style'])}. Each group has four variants and two questions;
these counts are not independent observations. Validation has no 11/12-node group;
we do not borrow one from test. All layouts are circular rotations.

The initial prompts are frozen by content hashes. Future tuning belongs on train/
development only and requires a new version. Test preparation requires an explicit
release flag. Phase 1B exposed gold/distributions from all splits and visually
inspected four test groups. This project cannot claim pristine held-out development,
human validation or publication readiness.

## Contradictions resolved and defects caught

- The historical inference export contains SVGs and original-first pair metadata.
  The narrower worker export carries re-encoded PNGs only; payloads use randomized
  neutral Image A/B. The offline bridge flips answers, evidence and signed deltas
  back for the unchanged v0.1.1 evaluator. Additions/deletions always refer to the
  presented direction. Redraw deltas may be empty.
- Legacy paired joint lacks an explicit answer-change component. Phase 2A reports
  it separately and requires the explicit change to be correct for primary joint.
  Missing/schema-invalid responses fail their whole expected case; semantic
  evidence errors fail evidence/joint while answer accuracy remains meaningful.
- Arbitrary-key shortest-distance maps conflict with strict provider schemas.
  The wire schema uses unique node/distance entries; the bridge converts them to
  the frozen dictionary certificate. No evidence or endpoints from gold enter A/B.
- A and B share model/settings/image detail/schema mode, but prompts and lengths
  differ. They are not compute-matched; per-track actual HTTP calls, token usage,
  latency, costs/reservations and failures are reported when available.
- First preflight found a schema-hash ordering mismatch. It was corrected in the
  shared preparation path and regression-tested. Failure attribution was also
  tightened per image: a missing endpoint in one parsed image does not establish
  a solving bug in the other correctly parsed image. Both earlier outputs are
  retained at `outputs/phase2a_preflight1` / `outputs/phase2a_preflight2` and superseded.

## Remaining requirements and costs

Real direct VLM, graph extraction, real A/B comparisons, model training/download,
learned verifier, test inference, paid APIs and human review did NOT run. No mock
response is presented as model performance. Remaining requirements: explicit
provider/model/budget approval; credentials or an authorized installed local model;
verified account compatibility; a conservative per-attempt reservation with cited
pricing/input bound; actual filesystem isolation of the worker. Provider-native
costs may be unavailable, and local reservations cannot guarantee an invoice cap
if their user-supplied bound is false. Ambiguous transport/crash calls remain
terminal uncertainties; providers are not assumed to offer exactly-once billing.

The concrete [run/cost proposal](BASELINE_PROTOCOL.md#concrete-initial-run-proposal-not-authorization)
uses a configurable exact snapshot, 504 initial calls / at most 1,512 attempts,
720 initial image occurrences, a 4,096 output-token limit and a proposed USD 40
reservation cap. This is not authorization, measured cost or an exact invoice.
Input/image tokens are unknown. Null reservation fields intentionally block calls.
Do not auto-substitute a model, increase a budget or drop unattempted cases.

## Preservation and reproducibility

[Preservation hashes](../outputs/phase2a/preservation.json) cover the original,
corrected, snapshot and Phase 1B report inventories. Every content hash matches
(excluding any explicitly listed Finder metadata). The prior README is preserved
separately; the live README has only an added Phase 2A section. Dataset remains
120 groups, unchanged examples, splits, questions, answers and pixels.
[Full frozen validation](../outputs/phase2a_preflight2/dataset_validation.json)
passed; final preservation/payload checks bind the same manifest.

The frozen bundle SHA256 is `{selection['bundle_sha256']}`. Model/schema/settings,
prompt and image hashes, protocol/source hashes and selected IDs are recorded.
[Executed commands](../outputs/phase2a/commands.json) include expected negative
checks; the runbook distinguishes later proposed commands. No production backend
or complete end-to-end container/billing integration was tested. Small-pilot
intervals and future differences remain preliminary.
'''
    (ROOT/'docs/PHASE2A_REPORT.md').write_text(report)
    source_files=[ROOT/'README.md',ROOT/'configs/baseline_pilot.json',ROOT/'tests/test_phase2a.py',ROOT/'tests/fixtures/phase2a_hand_cases.json']
    source_files+=list((ROOT/'topodelta_qa/baselines').glob('*.py'))+list((ROOT/'prompts/phase2a').glob('*.txt'))
    source_files+=[ROOT/'docs'/name for name in ('BASELINE_PROTOCOL.md','BASELINE_RUNBOOK.md','PHASE2A_REPORT.md')]
    source_files+=list((ROOT/'scripts').glob('phase2a_*.py'))
    write(OUT/'manifest.json',{'phase':'2A','verdict':verdict['verdict'],'dataset_version':'0.1.1',
          'files':{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'},
          'source_files':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(source_files)},
          'real_inference':False,'human_validation':False})
    print(json.dumps({'verdict':verdict['verdict'],'tests':int(match[1]),'provider_calls':0,'report':str(ROOT/'docs/PHASE2A_REPORT.md')}))


if __name__=='__main__':main()
