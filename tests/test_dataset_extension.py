import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

TEST_KEY = Path(__file__).resolve().parent / "fixtures/public_test_identity.json"
from topodelta_qa.dataset import generate, read_jsonl, extended_split_schedule
from topodelta_qa.schema import Config
from topodelta_qa.verify import validate_dataset


class DatasetExtensionTests(unittest.TestCase):
    def test_preserve_parent_and_repeat_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'parent'
            generate(Config(groups=3,max_attempts=100),parent,id_key_file=TEST_KEY)
            original={p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()}
            config=Config(groups=8,max_attempts=1000)
            for name in ('first','repeat'):
                generate(config,root/name,id_key_file=TEST_KEY,seed_dataset=parent)
                result=validate_dataset(root/name)
                self.assertEqual(result['status'],'passed')
                self.assertEqual(result['dataset_version'],'0.2.0')
                groups=read_jsonl(root/name/'gold/groups.jsonl')
                self.assertEqual(groups[:3],read_jsonl(parent/'gold/groups.jsonl'))
                self.assertEqual(Counter(g['split'] for g in groups),{'train':5,'validation':1,'test':2})
                for g in groups[:3]:
                    for v in g['variants']:
                        for asset in v['assets'].values():
                            self.assertEqual((parent/'inference'/asset).read_bytes(),(root/name/'inference'/asset).read_bytes())
            first={p.relative_to(root/'first'):p.read_bytes() for p in (root/'first').rglob('*') if p.is_file()}
            repeated={p.relative_to(root/'repeat'):p.read_bytes() for p in (root/'repeat').rglob('*') if p.is_file()}
            self.assertEqual(first,repeated)
            self.assertEqual(original,{p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError):generate(config,root/'first',id_key_file=TEST_KEY,seed_dataset=parent)
            with self.assertRaises(ValueError):generate(Config(groups=2),root/'too_small',id_key_file=TEST_KEY,seed_dataset=parent)
            self.assertFalse((root/'too_small').exists())

    def test_split_quota_impossibility_is_explicit(self):
        with self.assertRaises(ValueError):
            extended_split_schedule(Config(groups=4),[{'split':'validation'}])

    def test_cancelled_inference_entrypoints_fail_before_access(self):
        from topodelta_qa.baselines.runner import run
        from topodelta_qa.live.control import execute
        with self.assertRaisesRegex(ValueError,'dataset-only'):
            run(Path('/nonexistent'),Path('/nonexistent'),authorized=True)
        with self.assertRaisesRegex(ValueError,'cancelled'):
            execute(Path('/nonexistent'),'old-proposal')

if __name__=='__main__':unittest.main()
