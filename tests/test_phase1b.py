import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from phase1b_fixtures import run
from topodelta_qa.dataset import generate, oid, read_jsonl
from topodelta_qa.schema import Config
from topodelta_qa.verify import validate_dataset, validate_group


class Phase1BTests(unittest.TestCase):
    def test_hand_authored_adversarial_evaluator_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(Path(tmp))['status'],'passed')

    def test_public_parent_index_enumeration_cannot_recover_variant_roles(self):
        from topodelta_qa.identity import public_id, read_key
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data'
            config=Config(groups=1,max_attempts=100)
            generate(config,root)
            group=read_jsonl(root/'gold/groups.jsonl')[0]
            self.assertEqual({p.stat().st_mtime_ns for p in (root/'inference/images').iterdir()},{0})
            guesses={oid(group['id'],'variant',i) for i in range(4)}
            self.assertFalse(guesses & {v['id'] for v in group['variants']})
            key=read_key(root/'gold/id_key.json')
            bad=Path(tmp)/'bad_key.json';bad.write_text(json.dumps({'key_hex':' '*64}))
            with self.assertRaises(ValueError):
                read_key(bad)
            legacy_group=oid(config.seed,'group',group['attempt'])
            for i,v in enumerate(group['variants']):
                self.assertEqual(v['id'],public_id(oid(legacy_group,'variant',i),key))
            self.assertFalse(any('key' in str(r).lower() for r in read_jsonl(root/'inference/single.jsonl')))

    def test_edit_counts_reject_booleans_and_floats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data'
            generate(Config(groups=1,max_attempts=100),root)
            original=json.loads((root/'gold/groups.jsonl').read_text().splitlines()[0])
            for field in ('operation_count','directed_set_difference_count'):
                for malformed in (True,1.0):
                    group=copy.deepcopy(original)
                    variant=next(v for v in group['variants'] if v['edit'] and v['edit'][field]==1)
                    variant['edit'][field]=malformed
                    with self.assertRaisesRegex(ValueError,'Edit counts must be integers'):
                        validate_group(group)

    def test_historical_source_difference_is_not_data_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data'
            generate(Config(groups=1,max_attempts=100),root)
            with patch('topodelta_qa.verify.source_hashes',return_value={'historical.py':'different'}):
                result=validate_dataset(root)
                self.assertEqual(result['status'],'passed')
                self.assertFalse(result['generator_source_matches_current'])
                # Reporting source differences must never bypass asset integrity.
                path=root/'inference/single.jsonl'
                path.write_text(path.read_text()+'{}\n')
                with self.assertRaisesRegex(ValueError,'Hash mismatch'):
                    validate_dataset(root)

if __name__=='__main__':unittest.main()
