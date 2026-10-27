"""Bounded checks for the saved presentation and its Git exclusion boundary."""
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import instructor_demo as demo


IGNORE_CASES = {
    'outputs/topodelta_qa_v0.3.0-rc1/inference/images/full.png': True,
    'outputs/instructor_demo_work/temporary.png': True,
    'full_release.tar.gz': True,
    'regeneration.zip': True,
    'configs/evaluator_id_key.json': True,
    'gold/id_key.json': True,
    '.env': True,
    '.env.local': True,
    'service_credentials.json': True,
    'api_keys.json': True,
    'private.pem': True,
    '.venv/bin/python': True,
    'topodelta_qa/__pycache__/cached.pyc': True,
    '.pytest_cache/results': True,
    'instructor_demo/images/example.png': False,
    'instructor_demo/samples/example.json': False,
    'instructor_demo/reports/validation.json': False,
    'instructor_demo/gallery.html': False,
    'instructor_demo/README.md': False,
    'docs/RELEASE_CANDIDATE_REPORT.md': False,
    'scripts/instructor_demo.py': False,
    'topodelta_qa/release/independent.py': False,
    'tests/test_instructor_demo.py': False,
    'configs/release_candidate.json': False,
    '.env.example': False,
}


def check_ignore():
    # Only the disposable directory gets a Git index; the workspace stays unchanged.
    with tempfile.TemporaryDirectory(prefix='topodelta-demo-git-') as tmp:
        root=Path(tmp)
        shutil.copyfile(demo.PROJECT/'.gitignore',root/'.gitignore')
        subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
        result=subprocess.run(['git','-C',str(root),'check-ignore','--no-index','--stdin'],
                              input='\n'.join(IGNORE_CASES)+'\n',text=True,capture_output=True,check=True)
        ignored=set(result.stdout.splitlines())
        actual={path:path in ignored for path in IGNORE_CASES}
        assert actual==IGNORE_CASES,(actual,IGNORE_CASES)
        return actual


class InstructorDemoTests(unittest.TestCase):
    def test_saved_examples_and_teaching_claim(self):
        with contextlib.redirect_stdout(io.StringIO()):result=demo.verify()
        self.assertEqual(result['independent_demo_checks'],{'groups':16,'answers':128,'certificates':128,'edits':32})
        self.assertEqual(result['demo_tasks'].keys(),{'direct_edge','reachability','shortest_path'})
        page=(demo.DEMO/'gallery.html').read_text()
        self.assertNotIn('<script',page)
        self.assertNotIn('<iframe',page)
        self.assertIn('Delete VA → JM',page)
        self.assertIn('VA → VQ → JM',page)

    def test_rebuild_uses_only_bundled_inputs_and_is_byte_identical(self):
        with tempfile.TemporaryDirectory(prefix='topodelta-demo-build-') as tmp:
            root=Path(tmp)/'demo';shutil.copytree(demo.DEMO,root)
            names=('gallery.html','annotation_example.json','README.md','INSTRUCTOR_SUMMARY.md','STATUS.md')
            before={name:demo.sha(root/name) for name in names}
            with patch.object(demo,'DEMO',root),patch.object(demo,'DATA',Path(tmp)/'absent-release'):
                with contextlib.redirect_stdout(io.StringIO()):demo.render();result=demo.verify()
                self.assertFalse(result['local_full_release_manifest_checked'])
                self.assertEqual(before,{name:demo.sha(root/name) for name in names})
                with self.assertRaisesRegex(AssertionError,'refuses overwrite'):demo.extract()
                image=next((root/'images').glob('*.png'));image.write_bytes(b'corrupted copy')
                with self.assertRaises(AssertionError):demo.verify()

    def test_ignore_boundary(self):
        self.assertEqual(check_ignore(),IGNORE_CASES)


if __name__=='__main__':unittest.main()
