"""Offline Phase 2A artifact checks; no provider adapter calls."""
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topodelta_qa.baselines.contract import canonical, digest
from topodelta_qa.baselines.prepare import read_rows, write
from topodelta_qa.baselines.runner import load_bundle, payload, cache_key
from topodelta_qa.baselines.report import score
from topodelta_qa.baselines.solve import solve, derive

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/pilot_v0.1.1'
OUT=ROOT/'outputs/phase2a'


def main():
    worker=OUT/'worker';bundle=load_bundle(worker)
    selection=json.loads((OUT/'evaluation/selection.json').read_text())
    assert digest(bundle)==selection['bundle_sha256']
    assert len(selection['group_ids'])==18 and selection['split']=='validation'
    public={ (p,r['id']):r for p in ('single','paired') for r in read_rows(DATA/f'inference/{p}.jsonl') }
    assert {r['group_id'] for r in selection['cases']}==set(selection['group_ids'])
    inspected=0
    for case in selection['cases']:
        row=public[case['protocol'],case['id']]
        paths=[row['image']] if case['protocol']=='single' else row['images'][:]
        if case['reversed']:paths.reverse()
        assert row['split']=='validation' and row['question']==case['question']
        for relative,sha in zip(paths,case['images']):
            with Image.open(DATA/'inference'/relative) as a,Image.open(worker/f'images/{sha}.png') as b:
                assert a.size==b.size and a.convert('RGB').tobytes()==b.tobytes() and not b.info
            inspected+=1
    keys=set()
    for row in bundle['requests']:
        body=payload(worker,bundle,row)
        assert set(body)=={'model','reasoning_effort','max_completion_tokens','messages','response_format'}
        assert set(body['messages'][0])=={'role','content'}
        text=canonical(body)
        for forbidden in ('group_id','variant_id','question_id','case_id','pair_kind','asset_hashes','relevance','timestamp','.svg','.png'):
            assert forbidden not in text
        assert row['id'] not in text and row['case_id'] not in text
        for item in body['messages'][1]['content']:
            if item['type']=='text':
                assert item['text'] in ('Question: '+row['question'],'Image A','Image B')
            else:
                assert set(item)=={'type','image_url'} and item['image_url']['url'].startswith('data:image/png;base64,')
        keys.add(cache_key(bundle['config'],body))
    files=list(worker.rglob('*'))
    assert all(p.name=='bundle.json' or p.suffix=='.png' for p in files if p.is_file())
    write(OUT/'boundary_checks.json',{'status':'passed','provider_calls':0,'worker_requests_checked':len(bundle['requests']),
          'unique_request_body_cache_keys':len(keys),'png_occurrences_compared_to_frozen_pixels':inspected,
          'unique_pngs':len(bundle['images']),'test_cases_prepared':0,
          'paired_orders':{'reversed':sum(c['reversed'] for c in selection['cases']),
                           'forward':sum(c['protocol']=='paired' and not c['reversed'] for c in selection['cases'])},
          'model_payload_allowlist':True,'os_isolation_deployed':False,
          'limitation':'Payload allowlists and clean export are checked; actual process/container isolation must be enforced for a real run.'})
    hand=json.loads((ROOT/'tests/fixtures/phase2a_hand_cases.json').read_text())
    results=[]
    for case in hand['cases']:
        actual=solve(hand['graph'],case['question'])
        assert actual==(case['answer'],case['certificate'])
        results.append({'question':case['question'],'expected_answer':case['answer'],'actual_answer':actual[0],
                        'certificate_matches_hand_calculation':actual[1]==case['certificate']})
    edited={'nodes':hand['graph']['nodes'],'edges':[e for e in hand['graph']['edges'] if e!=hand['deletion']['edge']]}
    for reverse in (False,True):
        actual=derive([edited,hand['graph']] if reverse else [hand['graph'],edited],hand['deletion']['question'])
        suffix='reverse' if reverse else 'forward'
        assert actual['answers']==hand['deletion'][f'answers_{suffix}'] and actual['delta']==hand['deletion'][f'delta_{suffix}']
    write(OUT/'hand_oracle_checks.json',{'status':'passed','label':'HAND-CALCULATED SANITY FIXTURES, NOT MODEL RESULTS',
          'fixture_sha256':hashlib.sha256((ROOT/'tests/fixtures/phase2a_hand_cases.json').read_bytes()).hexdigest(),
          'cases':results,'forward_and_reverse_deletion_delta':'passed','shared_dependencies':'Python/JSON, task specification; fixture expected values do not call the solver or generator.'})
    empty={'bundle_sha256':selection['bundle_sha256'],'requests':{},'attempts':[],'mock_only':True,'reserved_usd':0}
    denominators={}
    for protocol in ('single','paired'):
        r=score(DATA,selection,empty,'direct',protocol,100,_breakdowns=False)
        assert r['metrics']['per_image_answer_accuracy']['value']==0 and r['metrics']['joint_success']['value']==0
        assert r['metrics']['answer_change_accuracy']['denominator']==108
        denominators[protocol]={'label':'EMPTY-PREDICTION DENOMINATOR FIXTURE, NOT MODEL PERFORMANCE',
              'expected_cases':r['expected_cases'],'missing':r['statuses']['missing'],
              'answer_denominator':r['metrics']['per_image_answer_accuracy']['denominator'],
              'joint_denominator':r['metrics']['joint_success']['denominator'],
              'change_denominator':r['metrics']['answer_change_accuracy']['denominator']}
    write(OUT/'empty_denominator_checks.json',{'status':'passed','protocols':denominators})
    print(json.dumps({'status':'passed','requests':len(bundle['requests']),'provider_calls':0}))


if __name__=='__main__':main()
