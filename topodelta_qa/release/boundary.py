"""Check public/gold alignment from raw records, independently of export projection."""
import itertools
import json
from collections import Counter

from .build import records, write
from .sample import opaque


def text(q):
    a,b=q['source'],q['target']
    if q['task']=='reachability':return f'Is there a directed path from {a} to {b}?'
    if q['task']=='direct_edge':return f'Is there a directed edge from {a} to {b}?'
    assert q['task']=='shortest_path'
    return f"What is the minimum number of directed edges in a path from {a} to {b}? Return 'unreachable' if none exists."


def verify_exports(root,out):
    variants={};questions={};groups=set();key=json.loads((root/'gold/id_key.json').read_text())['key_hex']
    for g in records(root):
        groups.add(g['id'])
        for q in g['questions']:
            assert q['id'] not in questions;questions[q['id']]={**q,'group_id':g['id'],'split':g['split']}
        for v in g['variants']:
            assert v['id'] not in variants
            variants[v['id']]={'group_id':g['id'],'role':v['role'],'answers':v['answers'],'certificates':v['certificates'],
                               'edges':set(map(tuple,v['graph']['edges'])),'image':v['assets']['png']}
    result=Counter()
    for kind in ('single','paired'):
        last='';seen=set()
        with (root/f'inference/{kind}.jsonl').open() as public,(root/f'gold/{kind}.jsonl').open() as gold:
            for p_line,g_line in itertools.zip_longest(public,gold):
                assert p_line is not None and g_line is not None,'public_gold_length_mismatch'
                p=json.loads(p_line);g=json.loads(g_line);ident=p['id']
                assert ident==g['id'] and ident>last and ident not in seen;seen.add(ident);last=ident
                q=questions[g['question_id']];gid=q['group_id']
                assert gid==p['group_id']==g['group_id'] and p['split']==g['split']==q['split']
                assert p['question']==text(q)
                assert p['answer_format']==("nonnegative integer or 'unreachable'" if q['task']=='shortest_path' else 'boolean')
                extra={'image'} if kind=='single' else {'images','pair_instructions'}
                assert set(p)=={'id','group_id','split','question','instructions','answer_format'}|extra,'forbidden_public_field'
                vs=[variants[g['variant_id']]] if kind=='single' else [variants[i] for i in g['variant_ids']]
                assert all(v['group_id']==gid for v in vs)
                if kind=='single':
                    assert p['image']==vs[0]['image'] and type(g['answer']) is type(vs[0]['answers'][q['id']])
                    assert g['answer']==vs[0]['answers'][q['id']] and g['certificate']==vs[0]['certificates'][q['id']]
                    expected=opaque(key,'rc1-case',gid,q['id'],g['variant_id'],'single')
                else:
                    assert len(vs)==2 and vs[0]['role']=='original' and vs[1]['role']!='original'
                    assert p['images']==[v['image'] for v in vs]
                    assert g['answers']==[v['answers'][q['id']] for v in vs]
                    assert all(type(a) is type(v['answers'][q['id']]) for a,v in zip(g['answers'],vs))
                    assert g['certificates']==[v['certificates'][q['id']] for v in vs]
                    assert set(map(tuple,g['delta']['added']))==vs[1]['edges']-vs[0]['edges']
                    assert set(map(tuple,g['delta']['deleted']))==vs[0]['edges']-vs[1]['edges']
                    changed=g['answers'][0]!=g['answers'][1]
                    assert g['pair_kind']==('redraw' if vs[1]['role']=='redraw' else 'relevant_edit' if changed else 'irrelevant_edit')
                    expected=opaque(key,'rc1-case',gid,q['id'],g['variant_ids'][1],'paired')
                assert ident==expected
                result[kind+'_cases']+=1;result['answer_certificate_occurrences']+=len(vs)
        assert result[kind+'_cases']==len(groups)*(8 if kind=='single' else 6)
    report={'status':'passed','checked':dict(result),'inference_field_allowlists':'exact',
            'public_row_order':'opaque case ID','paths':'opaque variant IDs, PNG references only',
            'shared_dependencies':'Private HMAC identity helper is shared. Semantic annotations were independently validated before this raw-record export alignment check.',
            'worker_isolation':'No inference executed. Future workers must receive decoded PNGs and allowlisted question text only, excluding SVG/source/IDs/splits/filesystem metadata.'}
    write(out/'export_boundary.json',report);return report
