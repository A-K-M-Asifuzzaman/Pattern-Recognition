import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from topodelta_qa.release.boundary import verify_exports
from topodelta_qa.release.build import canonical, render, write
from topodelta_qa.release.exports import export, schemas
from topodelta_qa.release.package import archive, compare, file_sha
from topodelta_qa.release.sample import construct, make_plan
from topodelta_qa.release.split_audit import invariant, exact
from topodelta_qa.release.review import human_packet, stratified
from topodelta_qa.release.diagnostics import image_statistics, association
from topodelta_qa.release.diagnostics import report as shortcut_report
from topodelta_qa.release.reports import report as coverage_report
from PIL import Image


class PackagingTests(unittest.TestCase):
    def test_descriptive_shortcut_statistics(self):
        image=Image.new('RGB',(2,2),'white');image.putpixel((1,1),(0,0,0))
        self.assertEqual(image_statistics(image)['nonbackground_fraction'],.25)
        self.assertEqual(image_statistics(image)['mean_gray'],191.25)
        self.assertEqual(association({('a','yes'):2,('b','no'):2}),1.0)

    def test_schemas_exports_alignment_and_corruption_detection(self):
        config=json.loads(Path('configs/release_candidate.json').read_text());intent=make_plan(config)[0];key='ab'*32
        for trial in range(100):
            try:g=construct(intent,trial,config,key);break
            except AssertionError:continue
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in ('gold/records','gold/attempts','inference/images','reports'):(root/folder).mkdir(parents=True)
            write(root/'gold/id_key.json',{'key_hex':key});g=render(g,root);write(root/'gold/records/00000.json',g)
            export(root);schemas(root);verify_exports(root,root/'reports')
            write(root/'gold/attempts/00000.json',[{'trial':g['trial'],'status':'accepted'}])
            self.assertEqual(coverage_report(root)['groups'],1)
            statistics=[]
            for v in g['variants']:
                with Image.open(root/'inference'/v['assets']['png']) as im:
                    statistics.append({'group_id':g['id'],'variant_id':v['id'],'split':g['split'],**image_statistics(im)})
            shortcut_report(root,statistics,root/'reports')
            self.assertEqual(len((root/'reports/variant_features.csv').read_text().splitlines()),5)
            self.assertEqual(json.loads((root/'reports/shortcut_diagnostics.json').read_text())['status'],'completed')
            Draft202012Validator(json.loads((root/'schemas/group.schema.json').read_text())).validate(g)
            for kind in ('single','paired'):
                for side in ('inference','gold'):
                    schema=json.loads((root/f'schemas/{kind}_{side}.schema.json').read_text());validator=Draft202012Validator(schema)
                    for line in (root/f'{side}/{kind}.jsonl').read_text().splitlines():validator.validate(json.loads(line))
            self.assertEqual(human_packet(root,root/'review/packet',count=1),1)
            page=(root/f'review/packet/groups/{g["id"]}.html').read_text()
            for role in ('original','redraw','edited'):self.assertNotIn(role,page)
            self.assertNotIn('value=',page)
            self.assertEqual(len((root/'review/packet/review_record_template.csv').read_text().splitlines()),1)
            self.assertTrue((root/'gold/human_review_key.jsonl').exists())
            path=root/'gold/single.jsonl';rows=path.read_text().splitlines();bad=json.loads(rows[0]);bad['answer']='corrupted';rows[0]=canonical(bad).strip();path.write_text('\n'.join(rows)+'\n')
            with self.assertRaises(AssertionError):verify_exports(root,root/'reports')

    def test_review_stratifies_exact_sizes_and_keeps_required_groups(self):
        groups=[]
        for n in range(6,21):
            for i in range(3):groups.append({'id':f'{n}:{i}','coverage':{'nodes':n,'layout':'grid','style':i,'density_bin':'sparse','topology':'dag','connectivity':'connected','difficulty_bin':'short'},'questions':[{'task':'reachability'}],'variants':[{'edit':None},{'edit':{'operation':'addition'}}]})
        chosen=stratified(groups,15,'test:',[groups[0]])
        self.assertEqual(len(chosen),15);self.assertEqual({g['coverage']['nodes'] for g in chosen},set(range(6,21)));self.assertIn(groups[0],chosen)

    def test_independent_refinement_is_label_invariant_and_exact(self):
        a={'nodes':list('ABCDEF'),'edges':[['A','B'],['B','C'],['C','A'],['D','E']]}
        b={'nodes':list('UVWXYZ'),'edges':[['W','V'],['V','U'],['U','W'],['X','Y']]}
        self.assertEqual(invariant(a),invariant(b));self.assertTrue(exact(a,b))
        b['edges'].append(['Y','Z']);self.assertNotEqual(invariant(a),invariant(b));self.assertFalse(exact(a,b))

    def test_archive_integrity_and_complete_manifest_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp)
            for name in ('one','two'):
                root=parent/name;(root/'gold/records').mkdir(parents=True);(root/'gold/attempts').mkdir();(root/'inference/images').mkdir(parents=True)
                group={'slot':0,'variants':[{'assets':{'png':'images/x.png','svg':'images/x.svg'}}]}
                write(root/'gold/records/00000.json',group);write(root/'gold/attempts/00000.json',[{'status':'accepted','trial':0}])
                (root/'inference/images/x.png').write_bytes(b'test raster bytes');(root/'inference/images/x.svg').write_text('<svg/>')
                files={p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()};write(root/'manifest.json',{'files':files})
            result=compare(parent/'one',parent/'two',parent/'compare.json');self.assertTrue(result['manifest_bytes_equal'])
            result=archive(parent/'one',parent/'archives');self.assertEqual(result['status'],'passed');self.assertEqual(result['total_members_checked'],5)
            (parent/'two/inference/images/x.svg').write_text('corrupted')
            with self.assertRaises(AssertionError):compare(parent/'one',parent/'two',parent/'bad.json')


if __name__=='__main__':unittest.main()
