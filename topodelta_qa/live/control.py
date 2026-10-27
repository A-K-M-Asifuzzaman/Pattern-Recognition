"""Parent coordinator: verifies sealed inputs, checks isolation, gates smoke -> full."""
import copy
import json
import shutil
from pathlib import Path
from .plan import write,sha
from .isolation import launch,profile
from ..baselines.contract import digest,validate_output

ROOT=Path(__file__).resolve().parents[2]


def read(p):return json.loads(p.read_text())


def verify(output):
    p=read(output/'proposal.json');ident=p.pop('proposal_id')
    if digest(p)!=ident:raise ValueError('Proposal identity differs')
    p['proposal_id']=ident
    for name,h in p['sealed_worker_files'].items():
        path=(output/name).resolve()
        if not path.is_relative_to(output.resolve()) or sha(path)!=h:raise ValueError('Worker inputs/code changed')
    for name,h in p['sealed_evaluation_files'].items():
        if sha(output/name)!=h:raise ValueError('Validation-only scoring view changed')
    for name,h in p['controller_files'].items():
        if sha(ROOT/name)!=h:raise ValueError('Coordinator code changed; prepare a new proposal')
    for name,h in read(output/'preserved_inputs.json').items():
        if sha(ROOT/name)!=h:raise ValueError('Frozen Phase 2A artifact changed')
    return p


def preflight(output):
    p=verify(output);results={}
    forbidden=[ROOT/'outputs/pilot_v0.1.1/gold/groups.jsonl',ROOT/'outputs/pilot_v0.1.1/gold/id_key.json',
               ROOT/'outputs/phase2a/evaluation/oracle/privileged_predictions.json',ROOT/'outputs/phase2a/evaluation/selection.json',
               ROOT/'outputs/phase1b/human_review/answer_key/answers.json',ROOT/'configs/evaluator_id_key.json',
               output/'evaluation/validation_view/gold/groups.jsonl',output/'smoke_selection.json']
    canary=output/'private_gold_canary.txt'
    canary.write_text('FICTIONAL ISOLATION CANARY; NO DATASET CONTENTS\n')
    for name,stage_record in p['stages'].items():
        stage=Path(stage_record['stage_path']);link=stage/'tmp/gold-link'
        if not link.is_symlink():link.symlink_to(forbidden[0])
        targets=[str(x.resolve()) for x in forbidden]+[str(canary.resolve()),str(link)]
        for network in (False,True):
            label=name+('/live-network-profile' if network else '/offline-profile')
            r=launch(stage,'probe',[json.dumps(targets)],network=network)
            result={'exit_code':r.returncode,'stderr':r.stderr}
            if r.returncode==0:result.update(json.loads(r.stdout))
            else:result['status']='failed'
            results[label]=result
        r=launch(stage,'mock') if name=='smoke' else None
        if r:
            results[name+'/mock_resume']={'exit_code':r.returncode,'stderr':r.stderr,
                                          **(json.loads(r.stdout) if r.returncode==0 else {'status':'failed'})}
        (output/'profiles').mkdir(exist_ok=True)
        (output/f'profiles/{name}.offline.sb').write_text(profile(stage,False))
        (output/f'profiles/{name}.live.sb').write_text(profile(stage,True))
    passed=all(r.get('status')=='passed' for r in results.values())
    result={'status':'passed' if passed else 'BLOCKED','proposal_id':p['proposal_id'],'mechanism':'macOS Seatbelt default deny',
            'launched_outside_app_sandbox':passed,'checks':results,'paid_calls':0,
            'limitation':'Nested sandbox creation fails inside the app sandbox; use the unsandboxed host launcher. No fallback to an unrestricted worker.'}
    write(output/'isolation_checks.json',result)
    if not passed:raise RuntimeError('Isolation/preflight failed; live inference remains blocked')
    return result


def smoke_gate(output):
    p=verify(output);stage=Path(p['stages']['smoke']['stage_path']);b=read(stage/'inputs/bundle.json')
    state=read(stage/'results/checkpoint.json');ledger=read(stage/'results/dispatch_ledger.json')
    if state['mock_only'] or ledger['mock_only'] or state['bundle_sha256']!=digest(b):raise ValueError('Smoke is not real matching inference')
    if set(state['requests'])!={r['id'] for r in b['requests']} or any(r['status']!='success' for r in state['requests'].values()):
        raise ValueError('Smoke has missing, failed or invalid responses; do not run full')
    for r in b['requests']:validate_output(state['requests'][r['id']]['output'],r['baseline'],r['protocol'],r['question'])
    if len(ledger['attempts'])!=len(state['attempts']) or state['reserved_usd']>11+1e-9:raise ValueError('Smoke accounting mismatch')
    for a in ledger['attempts']:
        if a.get('limit_breach'):raise ValueError('Live token usage exceeded estimate/limit')
        if a['completed']:
            u=a.get('usage',{})
            if not all(type(u.get(k)) is int and u[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
                raise ValueError('Live usage unavailable; stop before full')
            if u['total_tokens']!=u['prompt_tokens']+u['completion_tokens']:raise ValueError('Live token totals disagree')
    before=(len(state['attempts']),len(ledger['attempts']))
    r=launch(stage,'live',network=True,credential=True)
    if r.returncode:raise RuntimeError('Live safe-resume check failed')
    after=(len(read(stage/'results/checkpoint.json')['attempts']),len(read(stage/'results/dispatch_ledger.json')['attempts']))
    if before!=after:raise ValueError('Resume duplicated smoke attempts')
    result={'status':'passed','proposal_id':p['proposal_id'],'live_schema_validation':True,'usage_accounting':True,
            'resume_added_provider_attempts':0,'semantic_model_accuracy_is_not_a_gate':True}
    write(output/'smoke_gate.json',result)
    return state,ledger


def seed_full(output,state,ledger):
    p=verify(output);smoke=Path(p['stages']['smoke']['stage_path']);full=Path(p['stages']['full']['stage_path'])
    target=full/'results/checkpoint.json'
    if target.exists():return
    # Reuse identical completed requests, retaining original attempt IDs, reservations, usage and raw/cache provenance.
    b=read(full/'inputs/bundle.json');allowed={r['id']:r for r in b['requests']}
    from ..baselines.runner import payload,cache_key
    for ident,result in state['requests'].items():
        if ident not in allowed or cache_key(b['config'],payload(full/'inputs',b,allowed[ident]))!=result['cache_key']:
            raise ValueError('Smoke payload differs from full request; cannot reuse')
    seeded=copy.deepcopy(state);seeded['bundle_sha256']=digest(b);seeded['smoke_source_bundle_sha256']=state['bundle_sha256']
    for directory in ('raw','cache'):
        if (smoke/'results'/directory).exists():shutil.copytree(smoke/'results'/directory,full/'results'/directory,dirs_exist_ok=True)
    write(full/'results/dispatch_ledger.json',ledger)
    write(target,seeded)
    write(output/'smoke_reuse.json',{'imported_completed_requests':len(state['requests']),'imported_attempts':len(state['attempts']),
                                   'reserved_usd_included_in_full':state['reserved_usd'],'source_bundle_sha256':state['bundle_sha256']})


def execute(output,approval):
    mode_file=ROOT/'configs/project_mode.json'
    if mode_file.exists() and read(mode_file).get('mode')=='dataset_only':
        raise ValueError('Phase 2B is cancelled; dataset-only mode prohibits model inference')
    p=verify(output)
    if approval!=p['proposal_id']:raise ValueError('Approve the exact sealed proposal ID before live dispatch')
    preflight(output)
    stage=Path(p['stages']['smoke']['stage_path'])
    r=launch(stage,'live',network=True,credential=True)
    if r.returncode:raise RuntimeError('Smoke failed; full remains blocked. Private results retained.')
    state,ledger=smoke_gate(output)
    seed_full(output,state,ledger)
    full=Path(p['stages']['full']['stage_path'])
    r=launch(full,'live',network=True,credential=True)
    if r.returncode:raise RuntimeError('Full run stopped. Private results retained; do not change protocol.')
    write(output/'live_completion.json',{'proposal_id':p['proposal_id'],'smoke':json.loads((stage/'results/checkpoint.json').read_text())['halt_reason'],
         'full':json.loads((full/'results/checkpoint.json').read_text())['halt_reason'],'note':'Run the separate offline scoring command after responses are saved.'})


def score_saved(output,stage_name):
    p=verify(output);stage=Path(p['stages'][stage_name]['stage_path'])
    state=read(stage/'results/checkpoint.json')
    if state['mock_only']:raise ValueError('Mocks are not live baseline results')
    from ..baselines.report import score,compare
    selection=read(output/f'evaluation/{stage_name}_selection.json');view=output/'evaluation/validation_view'
    reports={}
    for protocol in ('single','paired'):
        for baseline in ('direct','parse'):
            report=score(view,selection,state,baseline,protocol)
            report['evaluation_source']='Phase 2A validation-only oracle export; original test/full gold files never opened'
            report['breakdown_note']+=' Original per-group style metadata unavailable in this derived evaluator view.'
            write(output/f'results/{stage_name}/{baseline}_{protocol}.json',report);reports[baseline,protocol]=report
        write(output/f'results/{stage_name}/comparison_{protocol}.json',compare(reports['direct',protocol],reports['parse',protocol]))
