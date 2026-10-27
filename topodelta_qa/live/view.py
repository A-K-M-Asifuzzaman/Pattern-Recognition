"""Validation-only evaluator view derived from the preserved, already-checked oracle export."""
import copy
import json
from collections import defaultdict
from pathlib import Path
from .plan import write,sha
from ..baselines.contract import digest,question,certificate_to_legacy
from ..baselines.report import legacy_prediction


def build(source,output,stages,smoke_ids):
    selection=json.loads((source/'evaluation/selection.json').read_text())
    oracle=json.loads((source/'evaluation/oracle/privileged_predictions.json').read_text())
    groups={g:{'id':g,'split':'validation','questions':{},'variants':{}} for g in selection['group_ids']}
    singles=[];pairs=[]
    for case in selection['cases']:
        if case['protocol']!='single':continue
        g=groups[case['group_id']];task,u,v=question(case['question']);qid=digest([g['id'],case['question']])
        g['questions'][qid]={'id':qid,'task':task,'source':u,'target':v}
        saved=oracle['requests'][digest(['oracle','single',case['id']])];value=saved['output'];vid=case['images'][0]
        variant=g['variants'].setdefault(vid,{'id':vid,'graph':saved['graphs'][0],'answers':{},'certificates':{},
                         'role':'edited','edit':None,'scene':{'style':'unavailable_in_validation_only_export'}})
        variant['answers'][qid]=value['answer'];variant['certificates'][qid]=certificate_to_legacy(value['certificate'])
        singles.append({'id':case['id'],'group_id':g['id'],'question_id':qid,'variant_id':vid,
                        'answer':value['answer'],'certificate':certificate_to_legacy(value['certificate'])})
    for case in selection['cases']:
        if case['protocol']!='paired':continue
        g=groups[case['group_id']];qid=digest([g['id'],case['question']]);vids=case['images'][:]
        value=oracle['requests'][digest(['oracle','paired',case['id']])]['output']
        p=legacy_prediction(case,value)
        if case['reversed']:vids.reverse()
        nadd,ndel=len(p['delta']['added']),len(p['delta']['deleted'])
        kind='redraw' if nadd+ndel==0 else 'relevant_edit' if value['answer_changed'] else 'irrelevant_edit'
        g['variants'][vids[0]]['role']='original'
        if kind=='redraw':g['variants'][vids[1]]['role']='redraw'
        else:g['variants'][vids[1]]['edit']={'operation':'reversal' if nadd==ndel==1 else 'addition' if nadd else 'deletion'}
        pairs.append({'id':case['id'],'group_id':g['id'],'question_id':qid,'variant_ids':vids,'answers':p['answers'],
                      'certificates':p['certificates'],'delta':p['delta'],'pair_kind':kind})
    view=output/'evaluation/validation_view'
    records=[]
    for g in groups.values():
        g['questions']=list(g['questions'].values());g['variants']=list(g['variants'].values())
        assert len(g['questions'])==2 and len(g['variants'])==4
        records.append(g)
    for name,rows in [('groups',records),('single',singles),('paired',pairs)]:
        p=view/f'gold/{name}.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
    write(view/'manifest.json',{'type':'validation-only evaluation view, not a new dataset','groups':18,
        'source_oracle_sha256':sha(source/'evaluation/oracle/privileged_predictions.json'),
        'source_selection_sha256':sha(source/'evaluation/selection.json'),
        'limitation':'Gold graphs/answers copied from Phase 2A validation oracle, already audited; style per group unavailable. No full-split gold file opened.'})
    for name in ('smoke','full'):
        selected=copy.deepcopy(selection)
        if name=='smoke':
            selected['group_ids']=[g for g in selected['group_ids'] if g in smoke_ids]
            selected['cases']=[c for c in selected['cases'] if c['group_id'] in smoke_ids]
        selected['freeze']['dataset_manifest_sha256']=sha(view/'manifest.json')
        selected['bundle_sha256']=stages[name]['bundle_sha256']
        write(output/f'evaluation/{name}_selection.json',selected)
