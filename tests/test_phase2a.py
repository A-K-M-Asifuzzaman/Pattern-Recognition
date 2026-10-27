import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from topodelta_qa.baselines.contract import digest, schema, strict_json, validate_output
from topodelta_qa.baselines.prepare import flip, write
from topodelta_qa.baselines.runner import (OpenAIAdapter, TransientError, cache_key, load_bundle, payload, run)
from topodelta_qa.baselines.solve import derive, solve
from topodelta_qa.baselines.report import legacy_prediction, oracle, score, compare

ROOT = Path(__file__).resolve().parents[1]
HAND = json.loads((ROOT/'tests/fixtures/phase2a_hand_cases.json').read_text())
TEXT = 'Is there a directed edge from A to B?'
OUTPUT = {'answer':True,'certificate':{'kind':'edge_claim','source':'A','target':'B','present':True}}


def envelope(value):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}


class Mock:
    secret = 'secret-fixture-credential'
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def send(self, body, ident):
        self.calls.append((body,ident))
        value = next(self.responses)
        if isinstance(value,BaseException):
            raise value
        return value


def bundle_at(root, count=1):
    worker = root/'worker'
    (worker/'images').mkdir(parents=True)
    stream = io.BytesIO()
    Image.new('RGB',(4,4),'white').save(stream,format='PNG')
    data = stream.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    (worker/f'images/{sha}.png').write_bytes(data)
    config = json.loads((ROOT/'configs/baseline_pilot.json').read_text())
    config.update(max_spend_usd=2.,reserve_per_attempt_usd=.1,reserve_basis='mock fixture only, no dollars spent')
    requests = [{'id':digest(['direct','single',str(i)]),'case_id':str(i),'baseline':'direct','protocol':'single',
                 'question':TEXT,'images':[sha]} for i in range(count)]
    prompts = {k:(ROOT/f'prompts/phase2a/{k}.txt').read_text() for k in ('common','direct','parse')}
    bundle = {'format':'topodelta-phase2a-worker-v1','config':config,'requests':requests,'prompts':prompts,
              'images':{sha:{'sha256':sha,'size':[4,4]}},
              'freeze':{'prompt_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in prompts.items()},
                        'schemas_sha256':digest([schema(r['baseline'],r['protocol'],r['question']) for r in requests])}}
    write(worker/'bundle.json',bundle)
    return worker,bundle


class Phase2ATests(unittest.TestCase):
    def test_preparation_schema_hash_order_metadata_stripping_and_test_gate(self):
        from topodelta_qa.baselines.prepare import prepare
        from PIL.PngImagePlugin import PngInfo
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';(data/'inference/images').mkdir(parents=True);(data/'gold').mkdir()
            write(data/'manifest.json',{'dataset_version':'0.1.1'})
            g={'id':'fixture','split':'validation','questions':[{'task':'direct_edge'}],
               'variants':[{'graph':HAND['graph'],'scene':{'style':0},'edit':None}]}
            (data/'gold/groups.jsonl').write_text(json.dumps(g)+'\n')
            pnginfo=PngInfo();pnginfo.add_text('gold_answer','MUST NOT ENTER REQUEST')
            Image.new('RGB',(4,4),'white').save(data/'inference/images/source.png',pnginfo=pnginfo)
            rows=[{'id':str(i),'group_id':'fixture','split':'validation','question':TEXT,'image':'images/source.png'} for i in range(2)]
            (data/'inference/single.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            (data/'inference/paired.jsonl').write_text('')
            config=json.loads((ROOT/'configs/baseline_pilot.json').read_text())
            with patch('topodelta_qa.verify.validate_dataset',return_value={}):
                prepare(data,root/'out',config)
            worker=root/'out/worker';bundle=load_bundle(worker)
            self.assertEqual(len(bundle['requests']),4)
            self.assertEqual([r['id'] for r in bundle['requests']],sorted(r['id'] for r in bundle['requests']))
            for row in bundle['requests']:
                self.assertNotIn('MUST NOT ENTER REQUEST',json.dumps(payload(worker,bundle,row)))
            with self.assertRaises(ValueError):prepare(data,root/'out',config)
            with self.assertRaises(ValueError):prepare(data,root/'test',config,split='test')
            self.assertFalse((root/'test').exists())

    def test_hand_calculated_solver_and_oracle_order(self):
        for row in HAND['cases']:
            self.assertEqual(solve(HAND['graph'],row['question']),(row['answer'],row['certificate']))
        base = HAND['graph']; edited = copy.deepcopy(base)
        edited['edges'].remove(HAND['deletion']['edge'])
        for reverse in (False,True):
            result = derive([edited,base] if reverse else [base,edited],HAND['deletion']['question'])
            suffix = 'reverse' if reverse else 'forward'
            self.assertEqual(result['answers'],HAND['deletion'][f'answers_{suffix}'])
            self.assertEqual(result['delta'],HAND['deletion'][f'delta_{suffix}'])
            self.assertTrue(result['answer_changed'])
            self.assertEqual(legacy_prediction({'id':'pair','protocol':'paired','reversed':reverse},result)['delta'],HAND['deletion']['delta_forward'])
        reverse_edge = copy.deepcopy(base)
        reverse_edge['edges'].remove(['A','B']);reverse_edge['edges'].append(['B','A'])
        self.assertEqual(derive([base,reverse_edge],TEXT)['delta'],{'added':[['B','A']],'deleted':[['A','B']]})
        self.assertEqual(derive([base,base],TEXT)['delta'],{'added':[],'deleted':[]})
        self.assertEqual([flip(str(i),42) for i in range(30)],[flip(str(i),42) for i in range(30)])
        self.assertEqual(set(flip(str(i),42) for i in range(30)),{False,True})

    def test_strict_schema_and_public_question_parser(self):
        from topodelta_qa.baselines.contract import question
        with self.assertRaises(ValueError):question(TEXT+' GOLD=A->B')
        for bad in ({**OUTPUT,'gold':True},{**OUTPUT,'answer':1},{'answer':True},None):
            with self.assertRaises(ValueError):validate_output(bad,'direct','single',TEXT)
        for text in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(ValueError):strict_json(text)
        with self.assertRaises(ValueError):
            validate_output({'graphs':[{'nodes':['A','B'],'edges':[['A','B'],['A','B']]}]},'parse','single',TEXT)
        with self.assertRaises(ValueError):solve({'nodes':['A'],'edges':[]},TEXT)
        with self.assertRaises(ValueError):
            validate_output({'answer':1,'certificate':{'kind':'shortest_path','path':['A','B'],'distances':[{'node':'A','distance':0},{'node':'A','distance':0}]}},'direct','single',HAND['cases'][2]['question'])

    def test_allowlist_and_cache_keys_cover_all_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker,bundle = bundle_at(Path(tmp))
            row = bundle['requests'][0]; body = payload(worker,bundle,row)
            serialized = json.dumps(body)
            for forbidden in ('case_id','group_id','variant_id','gold','reversed','filename','timestamp',row['id']):
                self.assertNotIn(forbidden,serialized)
            self.assertEqual(set(body),{'model','reasoning_effort','max_completion_tokens','messages','response_format'})
            key = cache_key(bundle['config'],body)
            changed = []
            for field,value in (('model','other-exact-model'),('max_completion_tokens',10),('response_format',{}),('messages',[])):
                b = copy.deepcopy(body);b[field]=value;changed.append(b)
            b = copy.deepcopy(body);b['messages'][1]['content'][2]['image_url']['url'] += 'changed';changed.append(b)
            b = copy.deepcopy(body);b['messages'][0]['content'] += 'prompt change';changed.append(b)
            self.assertTrue(all(cache_key(bundle['config'],b)!=key for b in changed))
            self.assertNotEqual(key,cache_key({**bundle['config'],'endpoint':'https://example.org/v1/chat/completions'},body))
            bundle['requests'][0]['gold_graph'] = HAND['graph'];write(worker/'bundle.json',bundle)
            with self.assertRaises(ValueError):load_bundle(worker)

    def test_resume_cache_raw_redaction_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);worker,bundle = bundle_at(root,2)
            raw = envelope(OUTPUT);raw['debug'] = 'secret-fixture-credential';raw['api_key']='another-secret'
            mock = Mock([raw]);out=root/'run'
            state = run(worker,out,adapter=mock)
            self.assertEqual(len(mock.calls),1)
            self.assertEqual(len(state['requests']),2)
            self.assertEqual(sum(x.get('cache_hit',False) for x in state['requests'].values()),1)
            run(worker,out,adapter=mock)
            self.assertEqual(len(mock.calls),1)
            self.assertTrue(state['mock_only'])
            self.assertEqual(state['attempts'][0]['usage']['total_tokens'],15)
            for p in out.rglob('*.json'):
                self.assertNotIn(mock.secret,p.read_text());self.assertNotIn('another-secret',p.read_text())
            with self.assertRaises(ValueError):run(worker,root/'not-authorized')
            bundle['config']['model']='changed-model';write(worker/'bundle.json',bundle)
            with self.assertRaises(ValueError):run(worker,out,adapter=mock)

    def test_retry_failure_invalid_and_budget_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);worker,b = bundle_at(root)
            mock = Mock([TransientError(429,{'error':'rate'}),TransientError(503,{'error':'server'}),envelope(OUTPUT)])
            state = run(worker,root/'retry',adapter=mock,sleep=lambda _:None)
            self.assertEqual(len(mock.calls),3)
            self.assertEqual(len(set(x[1] for x in mock.calls)),3)
            self.assertAlmostEqual(state['reserved_usd'],.3)
            invalid = Mock([envelope({})]);state=run(worker,root/'invalid',adapter=invalid)
            self.assertEqual(next(iter(state['requests'].values()))['status'],'invalid')
            self.assertEqual(len(invalid.calls),1)
            failed=Mock([TransientError(500,{}) for _ in range(3)])
            state=run(worker,root/'failed',adapter=failed,sleep=lambda _:None)
            self.assertEqual(next(iter(state['requests'].values()))['status'],'failed')
            run(worker,root/'failed',adapter=failed)
            self.assertEqual(len(failed.calls),3)
            b['config']['max_spend_usd']=.05;write(worker/'bundle.json',b)
            budget=Mock([]);state=run(worker,root/'budget',adapter=budget)
            self.assertEqual(len(budget.calls),0);self.assertEqual(state['requests'],{})
            b['config']['reserve_per_attempt_usd']=None;write(worker/'bundle.json',b)
            with self.assertRaises(ValueError):run(worker,root/'unbounded',adapter=Mock([]))

    def test_reported_cost_over_reservation_stops_and_stays_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);worker,_=bundle_at(root,2)
            raw=envelope(OUTPUT);raw['cost_usd']=.2
            mock=Mock([raw])
            with self.assertRaises(RuntimeError):run(worker,root/'run',adapter=mock)
            with self.assertRaises(ValueError):run(worker,root/'run',adapter=mock)
            self.assertEqual(len(mock.calls),1)

    def test_crash_does_not_redispatch_uncertain_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);worker,_=bundle_at(root)
            with self.assertRaises(KeyboardInterrupt):run(worker,root/'run',adapter=Mock([KeyboardInterrupt()]))
            no_calls=Mock([]);state=run(worker,root/'run',adapter=no_calls)
            self.assertEqual(next(iter(state['requests'].values()))['status'],'uncertain')
            self.assertEqual(no_calls.calls,[]);self.assertAlmostEqual(state['reserved_usd'],.1)

    def test_adapter_serialization_and_no_secret_in_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker,b=bundle_at(Path(tmp));body=payload(worker,b,b['requests'][0])
            response=unittest.mock.MagicMock()
            response.__enter__.return_value.read.return_value=json.dumps(envelope(OUTPUT)).encode()
            opener=unittest.mock.MagicMock();opener.open.return_value=response
            with patch.dict('os.environ',{'OPENAI_API_KEY':'test-not-real'}),patch('urllib.request.build_opener',return_value=opener):
                adapter=OpenAIAdapter(b['config']);self.assertEqual(adapter.send(body,'attempt'),envelope(OUTPUT))
            req=opener.open.call_args.args[0]
            self.assertNotIn('test-not-real',req.data.decode())
            self.assertEqual(req.get_header('Authorization'),'Bearer test-not-real')

    def test_independent_hand_gold_bridge_and_fixed_denominators(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from phase1b_fixtures import fixture
        groups,sg,pg=fixture()
        g=groups[0]
        for i,v in enumerate(g['variants']):
            v.update(role='original' if i==0 else 'redraw' if i==1 else 'edited',
                     scene={'style':0},edit=None if i<2 else {'operation':'deletion' if i==2 else 'reversal'})
        with tempfile.TemporaryDirectory() as tmp:
            dataset=Path(tmp)
            for name,rows in (('groups',groups),('single',sg),('paired',pg)):
                p=dataset/f'gold/{name}.jsonl';p.parent.mkdir(exist_ok=True);p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            (dataset/'manifest.json').write_text('{}')
            cases=[]
            qlookup={q['id']:QuestionText(q) for q in g['questions']}
            for protocol,rows in (('single',sg),('paired',pg)):
                for i,row in enumerate(rows):
                    cases.append({'id':row['id'],'group_id':'fixture','protocol':protocol,'reversed':protocol=='paired' and i%2==0,
                                  'question':qlookup[row['question_id']]})
            selection={'group_ids':['fixture'],'split':'test','cases':cases,'bundle_sha256':'hand-fixture',
                       'freeze':{'dataset_manifest_sha256':hashlib.sha256(b'{}').hexdigest()}}
            state=oracle(dataset,selection)
            for protocol,rows in (('single',sg),('paired',pg)):
                r=score(dataset,selection,state,'oracle',protocol,20)
                for name in ('per_image_answer_accuracy','certificate_validity','joint_success','parse_graph_exact_accuracy','answer_change_accuracy'):
                    self.assertEqual(r['metrics'][name]['value'],1,name)
                self.assertEqual(r['resources']['http_attempts'],0)
                self.assertEqual(compare(r,r,20)['metrics']['joint_success']['ci95'],[0,0])
            # Use hand answers as hypothetical valid outputs, NOT model performance.
            direct=copy.deepcopy(state);direct.pop('privileged_oracle');direct['mock_only']=True
            direct['requests']={digest(['direct',c['protocol'],c['id']]):copy.deepcopy(state['requests'][digest(['oracle',c['protocol'],c['id']])]) for c in cases}
            paired=score(dataset,selection,direct,'direct','paired',20)
            self.assertIn('MOCK',paired['label'])
            first=next(c for c in cases if c['protocol']=='paired')
            req=direct['requests'][digest(['direct','paired',first['id']])]
            req['output']['answer_changed']=not req['output']['answer_changed']
            paired=score(dataset,selection,direct,'direct','paired',20)
            self.assertEqual(paired['metrics']['legacy_joint_success']['value'],1)
            self.assertLess(paired['metrics']['joint_success']['value'],1)
            empty={**direct,'requests':{}}
            for protocol,n in (('single',len(sg)),('paired',len(pg))):
                r=score(dataset,selection,empty,'direct',protocol,20)
                self.assertEqual(r['expected_cases'],n)
                self.assertEqual(r['metrics']['per_image_answer_accuracy']['value'],0)
                self.assertEqual(r['metrics']['joint_success']['value'],0)
                self.assertEqual(r['metrics']['answer_change_accuracy']['denominator'],len(pg))
            req['output']={};r=score(dataset,selection,direct,'direct','paired',20)
            self.assertEqual(r['metrics']['joint_success']['denominator'],len(pg))
            self.assertEqual(r['metrics']['per_image_answer_accuracy']['denominator'],2*len(pg))
            parse=copy.deepcopy(state);parse.pop('privileged_oracle');parse['mock_only']=True
            parse['requests']={digest(['parse',c['protocol'],c['id']]):{'status':'success','output':{'graphs':copy.deepcopy(state['requests'][digest(['oracle',c['protocol'],c['id']])]['graphs'])}} for c in cases}
            r=score(dataset,selection,parse,'parse','paired',20)
            self.assertEqual(r['metrics']['joint_success']['value'],1)
            self.assertEqual(r['metrics']['parse_edge_f1']['value'],1)
            self.assertEqual(r['breakdown']['operation:deletion']['joint_success']['value'],1)
            self.assertEqual(r['breakdown']['task:reachability']['answer_change_accuracy']['value'],1)
            # A well-formed extraction that misses a query endpoint fails solving, not request parsing.
            req=parse['requests'][digest(['parse','paired',first['id']])]
            req['output']['graphs'][0]={'nodes':['B'],'edges':[]}
            r=score(dataset,selection,parse,'parse','paired',20)
            self.assertEqual(r['failure_observations']['solver_input_failure'],1)
            self.assertEqual(r['failure_observations']['solving_failure_with_exact_graph'],0)
            self.assertLess(r['metrics']['parse_graph_exact_accuracy']['value'],1)
            self.assertEqual(r['metrics']['joint_success']['denominator'],len(pg))


def QuestionText(q):
    from topodelta_qa.schema import Question
    return Question(**q).text()


if __name__=='__main__':unittest.main()
