import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from PIL import Image

from topodelta_qa.release.build import IsoIndex, build, records, sha
from topodelta_qa.release.drawing import validate_scene, template
from topodelta_qa.release.independent import distances, evidence, verify_group
from topodelta_qa.release.sample import construct, make_plan
from topodelta_qa.release.verify import validate


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads(Path('configs/release_candidate.json').read_text())
        cls.key='ab'*32

    def test_exact_size_split_appearance_plan_and_checkpoint_coverage(self):
        plan=make_plan(self.config)
        self.assertEqual(len(plan),20000)
        self.assertEqual(Counter(p['split'] for p in plan),{'train':14000,'validation':3000,'test':3000})
        sizes=Counter(p['nodes'] for p in plan)
        self.assertEqual(sum(sizes[n] for n in range(6,9)),4000)
        self.assertEqual(sum(sizes[n] for n in range(9,13)),4000)
        self.assertEqual(sum(sizes[n] for n in range(13,17)),6000)
        self.assertEqual(sum(sizes[n] for n in range(17,21)),6000)
        self.assertEqual(set(p['nodes'] for p in plan[:500]),set(range(6,21)))
        self.assertEqual(len({p['layout'] for p in plan[:500]}),4)
        self.assertEqual(len({p['operation'] for p in plan[:500]}),3)
        self.assertEqual(Counter(p['style'] for p in plan),{i:5000 for i in range(4)})
        self.assertTrue(all(p['density']=='sparse' for p in plan if p['nodes']<=7 and p['connectivity']=='disconnected'))

    def test_constructive_semantics_geometry_and_mutations(self):
        plan=make_plan(self.config)
        for intent in plan[:60]:
            for trial in range(100):
                try:group=construct(intent,trial,self.config,self.key);break
                except AssertionError:continue
            else:self.fail(str(intent))
            self.assertEqual(verify_group(group)['answers'],8)
            self.assertTrue(all(v['answer_change_evidence'][q['id']]['same_original_weak_component_as_edit']
                                for v in group['variants'][2:] for q in group['questions']))
        corrupted=copy.deepcopy(group);qid=group['questions'][0]['id'];corrupted['variants'][0]['answers'][qid]='wrong'
        with self.assertRaisesRegex(AssertionError,'wrong_answer'):verify_group(corrupted)
        corrupted=copy.deepcopy(group);corrupted['variants'][2]['scene']['nodes'][0]['center'][0]+=2
        with self.assertRaises(AssertionError):verify_group(corrupted)
        corrupted=copy.deepcopy(group['variants'][0]);corrupted['scene']['nodes'][0]['box'][0]=-1
        with self.assertRaises(AssertionError):validate_scene(corrupted['graph'],corrupted['scene'])

    def test_hand_certificates_accept_alternatives_and_reject_incomplete_absence(self):
        graph={'nodes':list('ABCDEF'),'edges':[['A','B'],['A','C'],['B','D'],['C','D'],['D','E']]}
        computed=distances(graph)
        q={'task':'reachability','source':'A','target':'E'}
        for route in [['A','B','D','E'],['A','C','D','E']]:
            self.assertTrue(evidence(graph,q,True,{'kind':'path','path':route},computed))
        q={'task':'reachability','source':'A','target':'F'}
        self.assertTrue(evidence(graph,q,False,{'kind':'reachable_set','nodes':list('ABCDE')},computed))
        self.assertFalse(evidence(graph,q,False,{'kind':'reachable_set','nodes':['A']},computed))
        q={'task':'shortest_path','source':'A','target':'E'}
        cert={'kind':'shortest_path','path':['A','C','D','E'],'distances':dict(zip('ABCDEF',[0,1,1,2,3,None]))}
        self.assertTrue(evidence(graph,q,3,cert,computed))
        cert['distances']['C']=None
        self.assertFalse(evidence(graph,q,3,cert,computed))

    def test_exact_iso_ignores_labels(self):
        a={'id':'a','split':'train','variants':[{'role':'original','graph':{'nodes':list('ABCDEF'),'edges':[['A','B'],['B','C']]}}]}
        b={'id':'b','split':'test','variants':[{'role':'original','graph':{'nodes':list('UVWXYZ'),'edges':[['V','U'],['U','W']]}}]}
        index=IsoIndex();index.add(a);self.assertEqual(index.match(b)['group'],'a')
        b['split']='train';self.assertEqual(index.match(b)['group'],'a')
        b['variants'][0]['role']='edited';self.assertIsNone(index.match(b))

    def test_known_cyclic_moderate_cell_has_a_verified_addition(self):
        intent=make_plan(self.config)[158]
        for trial in range(100):
            try:group=construct(intent,trial,self.config,self.key);break
            except AssertionError:continue
        else:self.fail('Known cyclic six-node moderate cell must be feasible')
        verify_group(group)
        self.assertEqual(group['variants'][3]['edit']['operation'],'addition')

    def test_extended_small_concentric_templates_expand_corridor_capacity(self):
        self.assertGreater(max(len(template(6,'concentric',i)[2]) for i in range(8,16)),
                           max(len(template(6,'concentric',i)[2]) for i in range(8)))
        intent=make_plan(self.config)[10045]
        for trial in range(1000,1100):
            try:group=construct(intent,trial,self.config,self.key);break
            except AssertionError:continue
        else:self.fail('Expanded concentric cell must be constructively feasible')
        verify_group(group)

    def test_isolated_pocket_preserves_a_richer_five_node_core(self):
        _,_,pool=template(6,'concentric',16)
        self.assertEqual(len([e for e in pool if 5 not in e]),8)
        intent=make_plan(self.config)[11325]
        for trial in range(5000,5100):
            try:group=construct(intent,trial,self.config,self.key);break
            except AssertionError:continue
        else:self.fail('Reserved isolated-pocket cell must be feasible')
        verify_group(group)
        self.assertEqual(group['coverage']['connectivity'],'disconnected')

    def test_staged_small_cell_revision_preserves_the_prior_plan_prefix(self):
        old=copy.deepcopy(self.config);old.pop('small_cell_revision_start_slot')
        before=make_plan(old);after=make_plan(self.config);boundary=self.config['small_cell_revision_start_slot']
        self.assertEqual(before[:boundary],after[:boundary])
        self.assertEqual(before[boundary]['connectivity'],'disconnected')
        self.assertEqual(after[boundary]['connectivity'],'connected')
        self.assertEqual(after[boundary]['density'],'moderate')
        self.assertTrue(all(a['nodes']==b['nodes'] and a['split']==b['split'] for a,b in zip(before,after)))

    def test_resume_matches_full_repeat_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=copy.deepcopy(self.config)
            config.update(groups=4,workers=1,size_bands=[{'min':13,'max':16,'groups':4}])
            path=root/'config.json';path.write_text(json.dumps(config))
            build(path,root/'resumed',limit=2)
            first=list(records(root/'resumed'));build(path,root/'resumed',resume=True)
            self.assertEqual(first,list(records(root/'resumed'))[:2])
            build(path,root/'repeat')
            left={p.relative_to(root/'resumed'):sha(p) for p in (root/'resumed').rglob('*') if p.is_file()}
            right={p.relative_to(root/'repeat'):sha(p) for p in (root/'repeat').rglob('*') if p.is_file()}
            self.assertEqual(left,right)
            for p in (root/'resumed/inference/images').glob('*.png'):
                with Image.open(p) as image:self.assertFalse(image.info)
            validate(root/'resumed',root/'checks',expected=4)
            (root/'resumed/inference/images/orphan.png').write_bytes(b'orphan')
            with self.assertRaisesRegex(AssertionError,'orphan_or_missing_assets'):
                validate(root/'resumed',root/'checks',expected=4)
            with self.assertRaises(AssertionError):build(path,root/'resumed')


if __name__=='__main__':unittest.main()
