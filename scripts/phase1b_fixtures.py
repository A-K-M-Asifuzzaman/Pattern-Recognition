"""Hand-authored six-node adversarial evaluator fixtures; no generator/solver calls."""
import argparse
import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from topodelta_qa.evaluate import edge_scores, evaluate_records, load_predictions
from topodelta_qa.schema import Graph, Question
from topodelta_qa.semantics import valid_certificate
from phase1b_audit import evidence, matrix, answer, iso, save


def fixture():
    nodes=list('ABCDEF'); base=[['A','B'],['A','C'],['B','D'],['C','D'],['D','E']]
    deleted=base[:-1]; reversed_graph=[['A','B'],['A','C'],['C','D'],['D','B'],['D','E']]
    reach={'id':'reach','task':'reachability','source':'A','target':'E'}
    direct={'id':'direct','task':'direct_edge','source':'A','target':'B'}
    positive={'kind':'path','path':['A','B','D','E']}
    negative={'kind':'reachable_set','nodes':['A','B','C','D']}
    alternative={'kind':'path','path':['A','C','D','E']}
    edge={'kind':'edge_claim','source':'A','target':'B','present':True}
    variants=[]
    for ident,edges,ans,cert in [('original',base,True,positive),('redraw',base,True,positive),
                                 ('deleted',deleted,False,negative),('reversed',reversed_graph,True,alternative)]:
        variants.append({'id':ident,'graph':{'nodes':nodes,'edges':sorted(edges)},'answers':{'reach':ans,'direct':True},
                         'certificates':{'reach':cert,'direct':edge}})
    group={'id':'fixture','questions':[reach,direct],'variants':variants,'split':'test'}
    sg=[];pg=[]
    for qid in ['reach','direct']:
        for v in variants:
            sg.append({'id':f's_{v["id"]}_{qid}','group_id':'fixture','question_id':qid,'variant_id':v['id'],
                       'answer':v['answers'][qid],'certificate':v['certificates'][qid]})
        for v in variants[1:]:
            pg.append({'id':f'p_{v["id"]}_{qid}','group_id':'fixture','question_id':qid,'variant_ids':['original',v['id']],
                       'answers':[True,v['answers'][qid]],'certificates':[variants[0]['certificates'][qid],v['certificates'][qid]],
                       'pair_kind':'redraw' if v['id']=='redraw' else 'relevant_edit' if v['id']=='deleted' and qid=='reach' else 'irrelevant_edit',
                       'delta':{'added':[],'deleted':[]} if v['id']=='redraw' else {'added':[],'deleted':[['D','E']]} if v['id']=='deleted' else {'added':[['D','B']],'deleted':[['B','D']]}})
    return [group],sg,pg


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    groups,sg,pg=fixture()
    oracle={r['id']:{'id':r['id'],'protocol':'paired','answers':copy.deepcopy(r['answers']),
                    'certificates':copy.deepcopy(r['certificates']),'delta':copy.deepcopy(r['delta'])} for r in pg}
    single={r['id']:{'id':r['id'],'protocol':'single','answer':r['answer'],'certificate':copy.deepcopy(r['certificate'])} for r in sg}
    save(out/'hand_fixture.json',{'description':'Diamond A→B→D→E and A→C→D→E; F isolated. Delete D→E or reverse B→D. Query reach A→E and direct A→B.',
                                 'groups':groups,'single_gold':sg,'paired_gold':pg})
    results=[]
    def check(name,predictions,expected,protocol='paired'):
        report=evaluate_records(groups,sg,pg,predictions,protocol,20,7)
        for metric,value in expected.items():
            actual=report['metrics'][metric]['value']
            assert abs(actual-value)<1e-12,(name,metric,actual,value)
        assert report['metrics']['joint_success']['denominator']==(6 if protocol=='paired' else 8)
        results.append({'fixture':name,'status':'passed','expected':expected,'observed':{k:report['metrics'][k] for k in expected},'handling':report['handling']})
        (out/f'{name}.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in predictions.values()))
    check('oracle',oracle,{'joint_success':1,'per_image_answer_accuracy':1,'edge_delta_f1':1})
    p=copy.deepcopy(oracle);p['p_redraw_reach']['answers']=[False,False]
    check('both_wrong_identical',p,{'raw_redraw_agreement':1,'redraw_pair_accuracy':0.5,'joint_success':5/6})
    p=copy.deepcopy(oracle);p['p_deleted_reach']['answers']=[True,True]
    check('correct_original_wrong_edit',p,{'relevant_edit_pair_accuracy':0,'per_image_answer_accuracy':11/12,'joint_success':5/6})
    p=copy.deepcopy(oracle);p['p_deleted_reach']['delta']={'added':[],'deleted':[]}
    check('correct_change_wrong_edges',p,{'relevant_edit_pair_accuracy':1,'edge_delta_f1':5/6,'joint_success':5/6})
    p=copy.deepcopy(oracle);p['p_deleted_reach']['answers']=[False,True]
    check('right_edges_wrong_answers',p,{'relevant_edit_pair_accuracy':0,'edge_delta_f1':1,'joint_success':5/6})
    p=copy.deepcopy(oracle);p['p_redraw_reach']['certificates'][0]={'kind':'path','path':['A','C','D','E']}
    check('alternative_evidence',p,{'certificate_validity':1,'joint_success':1})
    p=copy.deepcopy(oracle);p['p_deleted_reach']['certificates'][1]={'kind':'reachable_set','nodes':['A','B','C']}
    check('incomplete_negative_certificate',p,{'certificate_validity':11/12,'joint_success':5/6,'per_image_answer_accuracy':1})
    p=copy.deepcopy(oracle);p['p_deleted_reach']['certificates'][0]={'kind':'path','path':['A','E']}
    check('invalid_positive_certificate',p,{'certificate_validity':11/12,'joint_success':5/6})
    p=copy.deepcopy(oracle);p['p_redraw_reach'].pop('delta')
    check('missing_delta_empty_gold',p,{'edge_delta_f1':5/6,'joint_success':5/6})
    p=copy.deepcopy(oracle);p.pop('p_deleted_reach')
    check('missing_prediction',p,{'per_image_answer_accuracy':10/12,'joint_success':5/6,'relevant_edit_pair_accuracy':0})
    check('all_missing',{}, {'per_image_answer_accuracy':0,'edge_delta_f1':0,'joint_success':0})
    order=list(oracle);random.Random(33).shuffle(order);p={i:oracle[i] for i in order}
    check('reordered_predictions',p,{'joint_success':1})
    loaded,_=load_predictions(out/'reordered_predictions.jsonl','paired',set(oracle))
    assert evaluate_records(groups,sg,pg,loaded,'paired',20,7)==evaluate_records(groups,sg,pg,oracle,'paired',20,7)
    assert evaluate_records(groups,sg,pg,p,'paired',20,7)==evaluate_records(groups,sg,pg,oracle,'paired',20,7)
    p=copy.deepcopy(single);p['s_original_reach']['answer']=False;p['s_redraw_reach']['answer']=False
    check('single_both_wrong_identical',p,{'raw_redraw_agreement':1,'redraw_pair_accuracy':0.5,'per_image_answer_accuracy':6/8,'joint_success':6/8},'single')
    check('single_all_missing',{}, {'per_image_answer_accuracy':0,'joint_success':0},'single')
    io=[]
    for name,payload,error in [('duplicate', [oracle['p_redraw_reach']]*2,True),('unknown',[{'id':'unknown','protocol':'paired'}],True),
                               ('malformed_id',[{'id':12,'protocol':'paired'}],False),('protocol_mix',[{'id':'p_redraw_reach','protocol':'single'}],True)]:
        path=out/f'{name}_ids.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in payload))
        raised=False
        try:
            predictions,handling=load_predictions(path,'paired',set(oracle))
            if name=='malformed_id':
                assert not predictions and handling['invalid_rows_without_id']==1
        except ValueError:raised=True
        assert raised==error,name
        io.append({'case':name,'rejected_file':raised,'status':'passed'})
    path=out/'malformed_json.jsonl';path.write_text('{bad\n')
    predictions,handling=load_predictions(path,'paired',set(oracle));assert not predictions and handling['malformed_lines']==1
    check('malformed_cannot_drop_denominator',predictions,{'joint_success':0,'per_image_answer_accuracy':0})
    empties=[]
    for p,g,expected in [(set(),set(),(1,1,1)),(set(),{1},(0,0,0)),({1},set(),(0,0,0)),({1,2},{2,3},(.5,.5,.5))]:
        assert edge_scores(p,g)==expected
        empties.append({'predicted':sorted(p),'gold':sorted(g),'scores':expected})
    base=groups[0]['variants'][0]['graph'];negative={'kind':'reachable_set','nodes':list('ABCDE')}
    short={'id':'short','task':'shortest_path','source':'A','target':'E'}
    finite={'kind':'shortest_path','path':['A','C','D','E'],'distances':{'A':0,'B':1,'C':1,'D':2,'E':3,'F':None}}
    bad=copy.deepcopy(finite);bad['distances']['D']=1
    cases=[(short,3,finite,True),(short,3,bad,False),
           ({**short,'target':'F'},'unreachable',negative,True),
           ({**short,'target':'F'},'unreachable',{'kind':'reachable_set','nodes':list('ABCD')},False),
           ({'id':'negative','task':'reachability','source':'E','target':'A'},False,{'kind':'reachable_set','nodes':['E']},True),
           ({'id':'negative','task':'reachability','source':'E','target':'A'},False,{'kind':'reachable_set','nodes':['E','F']},False)]
    for query,claimed,cert,expected in cases:
        assert evidence(base,query,claimed,cert)==expected
        assert valid_certificate(Graph.parse(base),Question(**query),claimed,cert)==expected
    # Check the independent audit algorithms against explicit known nonisomorphic regular graphs.
    cycle={'nodes':list('ABCDEF'),'edges':[list(e) for e in zip('ABCDEF','BCDEFA')]}
    triangles={'nodes':list('ABCDEF'),'edges':[list(e) for e in zip('ABCDEF','BCAEFD')]}
    assert not iso(cycle,triangles) and iso(cycle,cycle)
    assert answer(base,short)==3 and answer(base,{**short,'target':'F'})=='unreachable'
    report={'status':'passed','hand_authored_graphs':3,'scoring_cases':results,'input_id_cases':io,
            'empty_set_cases':empties,'independent_and_primary_certificate_cases':len(cases),
            'independent_algorithm_self_checks':'passed','not_model_results':True}
    save(out/'results.json',report)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('outputs/phase1b/evaluator_fixtures'))
    args=p.parse_args();r=run(args.output);print('Passed',len(r['scoring_cases']),'hand-authored scoring cases and ID/certificate/empty-set checks')
