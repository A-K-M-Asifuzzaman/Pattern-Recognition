"""Staged worker entry: no evaluator import, no gold input, no unsandboxed fallback."""
import json
import sys
from pathlib import Path
from ..baselines import runner as legacy
from ..baselines.contract import digest, question, validate_output
from .limits import estimate, INPUT_LIMIT, OUTPUT_LIMIT, MODEL, ENDPOINT


def read(path):return json.loads(path.read_text())


def checked(stage):
    worker=stage/'inputs';b=legacy.load_bundle(worker);limits=read(worker/'dispatch_limits.json')
    if b['config']['model']!=MODEL or b['config']['endpoint']!=ENDPOINT:raise ValueError('Unapproved backend/model')
    name=limits['stage']
    count=252 if name=='smoke' else 1512 if name=='full' else 0
    if not count or limits['maximum_http_attempts']!=count:raise ValueError('Invalid attempt ceiling')
    if (b['config']['max_attempts']!=3 or b['config']['reserve_per_attempt_usd']!=.04 or
        b['config']['max_spend_usd']!=(11 if name=='smoke' else 65)):
        raise ValueError('Budget configuration differs from proposal')
    if set(limits['allowed_cache_keys'])!={r['id'] for r in b['requests']}:raise ValueError('Request allowlist differs')
    for r in b['requests']:
        body=legacy.payload(worker,b,r)
        if legacy.cache_key(b['config'],body)!=limits['allowed_cache_keys'][r['id']]:raise ValueError('Payload changed')
        estimate(body,[b['images'][h]['size'] for h in r['images']])
    return b,limits


def execute(stage):
    b,limits=checked(stage)
    state_path=stage/'results/checkpoint.json';ledger_path=stage/'results/dispatch_ledger.json'
    original=legacy.OpenAIAdapter
    class Guarded(original):
        def send(self,body,attempt_id):
            state=read(state_path)
            current=next(a for a in state['attempts'] if a['attempt_id']==attempt_id)
            ident=current['request_id']
            if legacy.cache_key(b['config'],body)!=limits['allowed_cache_keys'].get(ident):raise RuntimeError('Request outside frozen allowlist')
            row=next(r for r in b['requests'] if r['id']==ident)
            e=estimate(body,[b['images'][h]['size'] for h in row['images']])
            ledger=read(ledger_path) if ledger_path.exists() else {'mock_only':False,'attempts':[]}
            attempts=ledger['attempts']
            if ledger['mock_only'] or any(a.get('limit_breach') for a in attempts):raise RuntimeError('Invalid or exceeded accounting ledger')
            if len(attempts)>=limits['maximum_http_attempts']:raise RuntimeError('HTTP attempt limit reached before dispatch')
            if any(a['attempt_id']==attempt_id for a in attempts):raise RuntimeError('Duplicate attempt prevented')
            if sum(a['reserved_input_tokens'] for a in attempts)+INPUT_LIMIT>limits['max_total_reserved_input_tokens']:raise RuntimeError('Total input reservation limit')
            if sum(a['requested_output_tokens'] for a in attempts)+OUTPUT_LIMIT>limits['max_total_requested_output_tokens']:raise RuntimeError('Total output request limit')
            record={'attempt_id':attempt_id,'request_id':ident,'reserved_input_tokens':INPUT_LIMIT,
                    'requested_output_tokens':OUTPUT_LIMIT,'estimated_input_tokens':e['input_token_estimate'],
                    'estimated_usd_at_max_output':e['estimated_usd_at_max_output'],'reserved_usd':'.04','completed':False}
            attempts.append(record);legacy.atomic(ledger_path,ledger)
            try:raw=super().send(body,attempt_id)
            except legacy.TransientError as exc:
                try:
                    error=json.loads(exc.raw.get('body','{}')).get('error',{})
                    code=error.get('code') if isinstance(error,dict) else None
                except (ValueError,TypeError):code=None
                if code in ('organization_usage_limit_exceeded','organization_spend_limit_exceeded',
                            'project_spend_limit_exceeded','credit_balance_exhausted','insufficient_quota'):
                    raise legacy.PermanentError(exc.status,exc.raw) from None
                raise
            usage=raw.get('usage',{}) if isinstance(raw,dict) else {}
            if not isinstance(usage,dict):usage={}
            tokens={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(usage.get(k)) is int and usage[k]>=0}
            record.update(completed=True,usage=tokens)
            record['limit_breach']=(tokens.get('prompt_tokens',0)>e['input_token_estimate'] or
                                    tokens.get('prompt_tokens',0)>INPUT_LIMIT or tokens.get('completion_tokens',0)>OUTPUT_LIMIT)
            legacy.atomic(ledger_path,ledger)
            return raw
    legacy.OpenAIAdapter=Guarded
    try:return legacy.run(stage/'inputs',stage/'results',authorized=True)
    finally:legacy.OpenAIAdapter=original


def mock_check(stage):
    b,_=checked(stage)
    class Mock:
        secret=''
        def __init__(self):self.calls=0
        def send(self,body,attempt):
            self.calls+=1
            text=body['messages'][1]['content'][0]['text'][len('Question: '):]
            task,source,target=question(text)
            n=sum(x['type']=='image_url' for x in body['messages'][1]['content'])
            spec=body['response_format']['json_schema']['schema']
            if 'graphs' in spec['properties']:value={'graphs':[{'nodes':[source,target],'edges':[]} for _ in range(n)]}
            else:
                answer='unreachable' if task=='shortest_path' else False
                cert={'kind':'edge_claim','source':source,'target':target,'present':False} if task=='direct_edge' else {'kind':'reachable_set','nodes':[source]}
                value={'answer':answer,'certificate':cert} if n==1 else {'answers':[answer,answer],'certificates':[cert,cert],'delta':{'added':[],'deleted':[]},'answer_changed':False}
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],
                    'usage':{'prompt_tokens':100,'completion_tokens':100,'total_tokens':200}}
    output=stage/'results/mock_only';mock=Mock()
    one=legacy.run(stage/'inputs',output,adapter=mock,sleep=lambda _:None);before=mock.calls
    two=legacy.run(stage/'inputs',output,adapter=mock,sleep=lambda _:None)
    assert before==mock.calls and one['mock_only'] and all(r['status']=='success' for r in two['requests'].values())
    return {'status':'passed','label':'MOCK ORCHESTRATION ONLY','completed_requests':len(two['requests']),
            'mock_calls':before,'resume_added_calls':mock.calls-before,'paid_calls':0}


def main():
    stage=Path(__file__).resolve().parents[3]
    mode=sys.argv[1]
    if mode=='probe':
        import ssl
        checked(stage);results=[]
        for target in json.loads(sys.argv[2]):
            try:
                with open(target,'rb') as stream:stream.read(1)
                result='UNSAFE_READ_SUCCEEDED'
            except PermissionError:result='permission_denied'
            except OSError:result='OTHER_ERROR_NOT_PROOF_OF_ISOLATION'
            results.append({'path':target,'result':result})
        trust=ssl.create_default_context().cert_store_stats()
        result={'status':'passed' if all(r['result']=='permission_denied' for r in results) and trust['x509_ca']>0 else 'failed',
                'reads':results,'tls_trust_store':trust,'provider_calls':0}
    elif mode=='mock':result=mock_check(stage)
    elif mode=='live':
        state=execute(stage)
        result={'requests':len(state['requests']),'attempts':len(state['attempts']),'halt_reason':state['halt_reason'],'mock_only':state['mock_only']}
    else:raise ValueError('Unknown isolated worker mode')
    print(json.dumps(result))


if __name__=='__main__':main()
