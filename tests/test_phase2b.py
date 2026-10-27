"""Phase 2B tests use only fictional fixtures and the prepared validation inputs."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from topodelta_qa.baselines.contract import digest
from topodelta_qa.baselines.runner import payload,cache_key
from topodelta_qa.live.limits import estimate,image_tokens
from topodelta_qa.live.worker import execute
from topodelta_qa.live.isolation import profile
from topodelta_qa.live.control import execute as controller_execute,seed_full,smoke_gate

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase2a_fixture',ROOT/'tests/test_phase2a.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def tiny_stage(root):
    worker,b=helper.bundle_at(root)
    stage=root/'stage';stage.mkdir();worker.rename(stage/'inputs');(stage/'results').mkdir()
    b['config'].update(max_spend_usd=11.,reserve_per_attempt_usd=.04)
    helper.write(stage/'inputs/bundle.json',b)
    row=b['requests'][0];key=cache_key(b['config'],payload(stage/'inputs',b,row))
    helper.write(stage/'inputs/dispatch_limits.json',{'stage':'smoke','maximum_http_attempts':252,'allowed_cache_keys':{row['id']:key},
       'max_total_reserved_input_tokens':252*16384,'max_total_requested_output_tokens':252*4096})
    return stage,b


class Phase2BTests(unittest.TestCase):
    def test_image_cost_and_input_output_limits(self):
        self.assertEqual(image_tokens(800,800),750)
        with self.assertRaises(ValueError):image_tokens(4096,4096)
        with tempfile.TemporaryDirectory() as tmp:
            worker,b=helper.bundle_at(Path(tmp));body=payload(worker,b,b['requests'][0])
            result=estimate(body,[[800,800]])
            self.assertLess(result['input_token_estimate'],16384)
            self.assertEqual(result['maximum_output_tokens'],4096)
            body['messages'][0]['content']='x'*20000
            with self.assertRaises(ValueError):estimate(body,[[800,800]])
            body['max_completion_tokens']=8192
            with self.assertRaises(ValueError):estimate(body,[[800,800]])

    def test_reservations_usage_and_mocked_real_adapter_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage,b=tiny_stage(Path(tmp));value=helper.envelope(helper.OUTPUT)
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional-test-credential'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send',return_value=value) as send:
                state=execute(stage)
                self.assertFalse(state['mock_only']) # Stubbed transport, never a real model result.
                self.assertEqual(send.call_count,1)
                execute(stage)
                self.assertEqual(send.call_count,1)
            ledger=json.loads((stage/'results/dispatch_ledger.json').read_text())
            self.assertEqual(len(ledger['attempts']),1)
            self.assertEqual(ledger['attempts'][0]['reserved_input_tokens'],16384)
            self.assertEqual(state['reserved_usd'],.04)
            self.assertFalse(ledger['attempts'][0]['limit_breach'])
            self.assertNotIn('fictional-test-credential',(stage/'results/dispatch_ledger.json').read_text())

    def test_request_ceiling_blocks_transport_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage,b=tiny_stage(Path(tmp))
            attempts=[{'attempt_id':str(i),'reserved_input_tokens':16384,'requested_output_tokens':4096} for i in range(252)]
            helper.write(stage/'results/dispatch_ledger.json',{'mock_only':False,'attempts':attempts})
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send') as send:
                with self.assertRaises(RuntimeError):execute(stage)
                self.assertEqual(send.call_count,0)

    def test_missing_usage_is_preserved_and_flagged_at_gate_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage,b=tiny_stage(Path(tmp));value=helper.envelope(helper.OUTPUT);value['usage']=None
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send',return_value=value):
                state=execute(stage)
            self.assertTrue(list((stage/'results/raw').glob('*.json')))
            self.assertEqual(len(state['requests']),1)
            self.assertEqual(json.loads((stage/'results/dispatch_ledger.json').read_text())['attempts'][0]['usage'],{})
            p={'stages':{'smoke':{'stage_path':str(stage)}},'proposal_id':'fixture'}
            with patch('topodelta_qa.live.control.verify',return_value=p),patch('topodelta_qa.live.control.launch') as launcher:
                with self.assertRaises(ValueError):smoke_gate(Path(tmp))
                launcher.assert_not_called()

    def test_billing_429_does_not_retry(self):
        from topodelta_qa.baselines.runner import TransientError
        with tempfile.TemporaryDirectory() as tmp:
            stage,b=tiny_stage(Path(tmp))
            err=TransientError(429,{'body':json.dumps({'error':{'code':'project_spend_limit_exceeded'}})})
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send',side_effect=err) as send:
                state=execute(stage)
                self.assertEqual(send.call_count,1)
                self.assertEqual(next(iter(state['requests'].values()))['status'],'failed')

    def test_smoke_reuse_keeps_attempts_tokens_and_costs_without_new_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);smoke,b=tiny_stage(root)
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send',return_value=helper.envelope(helper.OUTPUT)):
                state=execute(smoke)
            ledger=json.loads((smoke/'results/dispatch_ledger.json').read_text())
            full=root/'full';(full/'inputs').mkdir(parents=True);(full/'results').mkdir()
            import shutil
            shutil.copytree(smoke/'inputs',full/'inputs',dirs_exist_ok=True)
            fb=copy.deepcopy(b);fb['config']['max_spend_usd']=65.
            helper.write(full/'inputs/bundle.json',fb)
            limits=json.loads((full/'inputs/dispatch_limits.json').read_text());limits.update(stage='full',maximum_http_attempts=1512,
                 max_total_reserved_input_tokens=1512*16384,max_total_requested_output_tokens=1512*4096)
            helper.write(full/'inputs/dispatch_limits.json',limits)
            p={'stages':{'smoke':{'stage_path':str(smoke)},'full':{'stage_path':str(full)}}}
            with patch('topodelta_qa.live.control.verify',return_value=p):seed_full(root,state,ledger)
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send') as send:
                completed=execute(full);self.assertEqual(send.call_count,0)
            self.assertEqual(completed['reserved_usd'],.04)
            self.assertEqual(len(completed['attempts']),1)
            self.assertEqual(completed['attempts'][0]['attempt_id'],state['attempts'][0]['attempt_id'])

    def test_budget_stops_before_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage,b=tiny_stage(Path(tmp))
            helper.write(stage/'results/checkpoint.json',{'bundle_sha256':digest(b),'mock_only':False,'reserved_usd':11.,'requests':{},'attempts':[]})
            with patch.dict('os.environ',{'OPENAI_API_KEY':'fictional'}),patch('topodelta_qa.baselines.runner.OpenAIAdapter.send') as send:
                state=execute(stage)
                self.assertEqual(state['halt_reason'],'budget_exhausted');self.assertEqual(send.call_count,0)

    def test_default_deny_and_approval_gate(self):
        text=profile(ROOT/'outputs/phase2b/staging/smoke')
        self.assertIn('(deny default)',text);self.assertNotIn('(allow default)',text)
        self.assertNotIn('network-outbound',text)
        self.assertNotIn('(subpath "/System")',text) # Do not whitelist Data volume aliases.
        self.assertIn('network-outbound',profile(ROOT/'outputs/phase2b/staging/smoke',True))
        with patch('topodelta_qa.live.control.verify',return_value={'proposal_id':'specific-approved-hash'}),patch('topodelta_qa.live.control.preflight') as preflight:
            with self.assertRaises(ValueError):controller_execute(ROOT/'outputs/phase2b','not-approved')
            preflight.assert_not_called()

    def test_prepared_validation_counts_and_smoke_coverage(self):
        p=ROOT/'outputs/phase2b'
        rec=json.loads((p/'reconciliation.json').read_text());smoke=json.loads((p/'smoke_selection.json').read_text())
        self.assertEqual(rec['counts'],{'direct/single':144,'direct/paired':108,'parse/single':144,'parse/paired':108})
        self.assertEqual(rec['safe_exact_duplicate_reuses'],0)
        self.assertEqual(len(smoke['group_ids']),3)
        self.assertEqual(set(t for g in smoke['groups'].values() for t in g['tasks']),{'reachability','direct_edge','shortest_path'})
        self.assertIn('reversal',{o for g in smoke['groups'].values() for o in g['operations']})
        self.assertTrue(all(any(g['pair_kinds'].get(k,0) for g in smoke['groups'].values()) for k in ('redraw','relevant_edit','irrelevant_edit')))
        bundle=json.loads((p/'staging/smoke/inputs/bundle.json').read_text());self.assertEqual(len(bundle['requests']),84)
        old=json.loads((ROOT/'outputs/phase2a/worker/bundle.json').read_text())
        self.assertEqual(bundle['prompts'],old['prompts'])
        self.assertEqual(bundle['config']['settings'],old['config']['settings'])

if __name__=='__main__':unittest.main()
