"""Read only the frozen Phase 2A validation bundle and validation-only oracle export."""
import copy
import hashlib
import itertools
import json
import shutil
from collections import Counter
from decimal import Decimal
from pathlib import Path
from ..baselines.contract import digest, question, schema
from ..baselines.runner import load_bundle, payload, cache_key
from .limits import SOURCES, estimate, INPUT_LIMIT, OUTPUT_LIMIT, RESERVE_USD

ROOT=Path(__file__).resolve().parents[2]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source,output):
    source=source.resolve();output=output.resolve()
    if output.exists():raise ValueError('Preserve existing artifacts; use a new Phase 2B output')
    bundle=load_bundle(source/'worker');selection=json.loads((source/'evaluation/selection.json').read_text())
    if selection['split']!='validation' or len(selection['group_ids'])!=18 or selection['bundle_sha256']!=digest(bundle):
        raise ValueError('Only the frozen 18-group validation selection is permitted')
    oracle=json.loads((source/'evaluation/oracle/privileged_predictions.json').read_text())
    if oracle['bundle_sha256']!=digest(bundle):raise ValueError('Validation oracle provenance differs')
    features={gid:{'tasks':set(),'operations':set(),'pair_kinds':Counter()} for gid in selection['group_ids']}
    for c in selection['cases']:
        f=features[c['group_id']];f['tasks'].add(question(c['question'])[0])
        if c['protocol']=='paired':
            value=oracle['requests'][digest(['oracle','paired',c['id']])]['output']
            delta=value['delta'];nadd,ndel=len(delta['added']),len(delta['deleted'])
            op='redraw' if nadd+ndel==0 else 'reversal' if nadd==ndel==1 else 'addition' if nadd else 'deletion'
            # Normalize to original-first for operation strata only; worker never receives these fields.
            if c['reversed'] and op in ('addition','deletion'):op='deletion' if op=='addition' else 'addition'
            f['operations'].add(op)
            kind='redraw' if op=='redraw' else 'relevant_edit' if value['answer_changed'] else 'irrelevant_edit'
            f['pair_kinds'][kind]+=1
    combos=[]
    for ids in itertools.combinations(selection['group_ids'],3):
        tasks=set().union(*(features[g]['tasks'] for g in ids));ops=set().union(*(features[g]['operations'] for g in ids))
        kinds=sum((features[g]['pair_kinds'] for g in ids),Counter())
        if len(tasks)==3 and 'reversal' in ops and all(kinds[k] for k in ('redraw','relevant_edit','irrelevant_edit')):
            combos.append((-(len(ops)),digest([selection['seed'],'phase2b-smoke',ids]),ids))
    if not combos:raise ValueError('Requested smoke coverage is unavailable')
    ids=min(combos)[2];smoke_ids=set(ids)
    output.mkdir(parents=True)
    frozen={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'docs/PHASE2A_REPORT.md',ROOT/'docs/BASELINE_PROTOCOL.md',ROOT/'docs/BASELINE_RUNBOOK.md',source/'manifest.json',source/'worker/bundle.json',source/'evaluation/selection.json']}
    frozen.update({str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'prompts/phase2a').glob('*.txt')})
    write(output/'preserved_inputs.json',frozen)
    rows=[];counts=Counter();keys=Counter()
    for r in bundle['requests']:
        body=payload(source/'worker',bundle,r);sizes=[bundle['images'][h]['size'] for h in r['images']]
        e=estimate(body,sizes);k=cache_key(bundle['config'],body);keys[k]+=1
        gid=next(c['group_id'] for c in selection['cases'] if c['protocol']==r['protocol'] and c['id']==r['case_id'])
        rows.append({'request_id':r['id'],'case_id':r['case_id'],'group_id':gid,'baseline':r['baseline'],'protocol':r['protocol'],
                     'cache_key':k,'smoke':gid in smoke_ids,**e})
        counts[f"{r['baseline']}/{r['protocol']}"]+=1
    write(output/'reconciliation.json',{'counts':counts,'groups':18,'base_questions':36,'unique_images':72,'statistical_resampling_unit':'group',
          'single_cases_per_baseline':144,'paired_cases_per_baseline':108,'image_occurrences_per_baseline':360,
          'unique_initial_provider_requests':len(keys),'safe_exact_duplicate_reuses':sum(v-1 for v in keys.values()),
          'question_conditioned':True,'cross_question_parse_reuse':False,'request_estimates':rows})
    write(output/'smoke_selection.json',{'split':'validation','group_ids':list(ids),'seed':selection['seed'],'method':'all feasible three-group combinations; maximize operation coverage, then seeded hash tie-break',
          'groups':{g:{'tasks':sorted(features[g]['tasks']),'operations':sorted(features[g]['operations']),'pair_kinds':features[g]['pair_kinds']} for g in ids},
          'not_held_out':True,'case_ids':[c['id'] for c in selection['cases'] if c['group_id'] in smoke_ids]})
    estimates={}
    for stage in ('smoke','full'):
        chosen=[r for r in rows if stage=='full' or r['smoke']]
        n=len(chosen);im=sum(r['image_tokens'] for r in chosen);text=sum(r['text_token_bound_with_framing'] for r in chosen)
        estimates[stage]={'unique_requests':n,'maximum_http_attempts':n*3,'image_input_tokens':im,'text_input_token_upper_estimate':text,
          'image_cost_usd':str(Decimal(im)*Decimal('.75')/1000000),'text_input_cost_upper_estimate_usd':str(Decimal(text)*Decimal('.75')/1000000),
          'maximum_output_tokens_initial':n*4096,'maximum_output_cost_usd_initial':str(Decimal(n*4096)*Decimal('4.50')/1000000),
          'estimated_initial_cost_at_max_output_usd':str(sum(Decimal(r['estimated_usd_at_max_output']) for r in chosen)),
          'estimated_all_attempts_cost_usd':str(sum(Decimal(r['estimated_usd_at_max_output']) for r in chosen)*3),
          'reserved_total_all_attempts_usd':str(RESERVE_USD*n*3),'budget_usd':11 if stage=='smoke' else 65}
    write(output/'costs.json',{'sources':SOURCES,'estimates':estimates,'per_attempt_input_limit':INPUT_LIMIT,'per_attempt_output_limit':OUTPUT_LIMIT,
          'per_attempt_reservation_usd':str(RESERVE_USD),'framing_allowance_tokens':2048,'rate_safety_factor':'1.25',
          'conservative_max_input_output_cost_all_1512_attempts_usd':str((Decimal(16384)*Decimal('.75')+Decimal(4096)*Decimal('4.50'))/1000000*1512),
          'billing_ceiling_guaranteed':False,'assumptions':['Standard non-regional USD rates, no taxes/tools/surcharges','No provider cache discount assumed',
          'Each 800x800 high image is 750 input tokens under current patch rules','Text token count <= UTF-8 bytes; provider/schema framing <= 2048 tokens',
          'Local estimates are not a guaranteed provider billing ceiling; stop if live usage exceeds limits or estimates']})
    # New bundles change billing configuration only; prompts/settings/questions/order/pixels are copied intact.
    stages={}
    for name in ('smoke','full'):
        worker=output/f'staging/{name}/inputs';worker.mkdir(parents=True)
        b=copy.deepcopy(bundle)
        if name=='smoke':b['requests']=[r for r in b['requests'] if any(x['request_id']==r['id'] and x['smoke'] for x in rows)]
        b['config'].update(max_spend_usd=11. if name=='smoke' else 65.,reserve_per_attempt_usd=.04,
          reserve_basis='Phase 2B: <=16384 estimated input, 4096 output, USD .75/4.50 per million, 25% margin, .04 reserved per attempt; costs.json')
        b['freeze']['schemas_sha256']=digest([schema(r['baseline'],r['protocol'],r['question']) for r in b['requests']])
        hashes={h for r in b['requests'] for h in r['images']};b['images']={h:v for h,v in b['images'].items() if h in hashes}
        write(worker/'bundle.json',b)
        for h in hashes:
            (worker/'images').mkdir(exist_ok=True);shutil.copyfile(source/f'worker/images/{h}.png',worker/f'images/{h}.png')
        code=worker.parent/'code';(code/'topodelta_qa/live').mkdir(parents=True)
        shutil.copyfile(ROOT/'topodelta_qa/__init__.py',code/'topodelta_qa/__init__.py')
        shutil.copytree(ROOT/'topodelta_qa/baselines',code/'topodelta_qa/baselines',ignore=shutil.ignore_patterns('__pycache__'))
        for filename in ('__init__.py','limits.py','worker.py'):
            shutil.copyfile(ROOT/f'topodelta_qa/live/{filename}',code/f'topodelta_qa/live/{filename}')
        import PIL
        site=str(Path(PIL.__file__).resolve().parent.parent)
        (code/'bootstrap.py').write_text('import sys\nfrom pathlib import Path\nsys.path[:0] = ['+repr(str(code))+','+repr(site)+']\nfrom topodelta_qa.live.worker import main\nmain()\n')
        for p in ('results','tmp'):(worker.parent/p).mkdir()
        allowed={r['request_id']:r for r in rows if name=='full' or r['smoke']}
        write(worker/'dispatch_limits.json',{'stage':name,'maximum_http_attempts':252 if name=='smoke' else 1512,
            'max_input_tokens':16384,'max_output_tokens':4096,'max_total_reserved_input_tokens':(252 if name=='smoke' else 1512)*16384,
            'max_total_requested_output_tokens':(252 if name=='smoke' else 1512)*4096,
            'allowed_cache_keys':{k:v['cache_key'] for k,v in allowed.items()},'smoke_request_ids':[r['request_id'] for r in rows if r['smoke']]})
        stages[name]={'bundle_sha256':digest(b),'requests':len(b['requests']),'stage_path':str(worker.parent.resolve())}
    from .view import build
    build(source,output,stages,smoke_ids)
    proposal={'model':bundle['config']['model'],'backend':bundle['config']['endpoint'],'stages':stages,'costs':estimates,
              'original_selection_sha256':sha(source/'evaluation/selection.json'),'prompt_hashes':bundle['freeze']['prompt_hashes'],
              'requires_explicit_approval':True,'full_includes_smoke':True,'no_test_access':True,'isolation':'macOS sandbox-exec default-deny profile, launched outside app sandbox',
              'phase2a_source_bundle_sha256':digest(bundle)}
    proposal['sealed_worker_files']={p.relative_to(output).as_posix():sha(p) for p in sorted((output/'staging').rglob('*'))
                                    if p.is_file() and ('/inputs/' in str(p) or '/code/' in str(p))}
    proposal['sealed_evaluation_files']={p.relative_to(output).as_posix():sha(p) for p in sorted((output/'evaluation').rglob('*')) if p.is_file()}
    proposal['controller_files']={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    proposal['proposal_id']=digest(proposal)
    write(output/'proposal.json',proposal)
    print(json.dumps({'proposal_id':proposal['proposal_id'],'smoke_requests':84,'full_requests_including_smoke':504,'paid_calls':0}))
