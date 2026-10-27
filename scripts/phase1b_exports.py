"""Independent export/key alignment, embedded-font, and evidence separation checks."""
import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from phase1b_audit import rows, answer, evidence, equal, table, save


def run(root=Path('outputs/pilot'),out=Path('outputs/phase1b')):
    groups=rows(root/'gold/groups.jsonl');gs={g['id']:g for g in groups}
    variants={v['id']:v for g in groups for v in g['variants']}
    questions={q['id']:q for g in groups for q in g['questions']}
    count=Counter();styles=set();font_hashes=set();separation=[]
    for protocol in ['single','paired']:
        public={r['id']:r for r in rows(root/f'inference/{protocol}.jsonl')}
        gold=rows(root/f'gold/{protocol}.jsonl')
        assert len(gold)==len({r['id'] for r in gold})==len(public)
        assert set(public)=={r['id'] for r in gold}
        for r in gold:
            q=questions[r['question_id']];p=public[r['id']]
            g=gs[r['group_id']]
            assert p['group_id']==g['id'] and p['split']==g['split']
            from phase1b_audit import question_text
            assert p['question']==question_text(q)
            vs=[variants[r['variant_id']]] if protocol=='single' else [variants[i] for i in r['variant_ids']]
            expected_paths=[v['assets']['png'] for v in vs]
            assert ([p['image']] if protocol=='single' else p['images'])==expected_paths
            claims=[r['answer']] if protocol=='single' else r['answers']
            certs=[r['certificate']] if protocol=='single' else r['certificates']
            for v,claim,cert in zip(vs,claims,certs):
                assert v in g['variants']
                assert equal(answer(v['graph'],q),claim) and evidence(v['graph'],q,claim,cert)
                count['export_answer_certificate_pairs']+=1
            if protocol=='paired':
                a,b=[set(map(tuple,v['graph']['edges'])) for v in vs]
                assert set(map(tuple,r['delta']['added']))==b-a and set(map(tuple,r['delta']['deleted']))==a-b
                kind='redraw' if a==b else 'relevant_edit' if not equal(*claims) else 'irrelevant_edit'
                assert r['pair_kind']==kind
                count['paired_export_deltas_and_kinds']+=1
    for g in groups:
        for v in g['variants']:
            xml=ET.fromstring((root/'inference'/v['assets']['svg']).read_text())
            tags=Counter(e.tag.split('}')[-1] for e in xml.iter())
            assert tags['line']==tags['polygon']==len(v['graph']['edges'])
            assert tags['text']==len(v['graph']['nodes']) and tags['rect']==len(v['graph']['nodes'])+1
            style=next(e.text for e in xml.iter() if e.tag.endswith('}style'));styles.add(style)
            encoded=re.search('base64,([A-Za-z0-9+/=]+)',style).group(1)
            font_hashes.add(hashlib.sha256(base64.b64decode(encoded)).hexdigest())
            count['svg_primitive_counts']+=1
        for v in g['variants'][2:]:
            assert type(v['edit']['operation_count']) is int and type(v['edit']['directed_set_difference_count']) is int
            count['strict_integer_edit_count_fields']+=2
            deleted=set(map(tuple,v['edit']['deleted']))
            for q in g['questions']:
                cert=g['variants'][0]['certificates'][q['id']]
                path=cert.get('path',[]);support=set(zip(path,path[1:]))
                separation.append({'group_id':g['id'],'variant_id':v['id'],'question_id':q['id'],
                                   'relevant':v['relevance'][q['id']], 'certificate_kind':cert['kind'],
                                   'deleted_edge_on_one_stored_original_path':bool(support&deleted),
                                   'answer_unchanged_despite_losing_stored_path':bool(support&deleted) and not v['relevance'][q['id']]})
    manifest=json.loads((root/'manifest.json').read_text())
    assert len(styles)==1 and font_hashes=={manifest['provenance']['font_sha256']}
    table(out/'evidence_separation.csv',separation)
    report={'status':'passed','counts':dict(count),'distinct_svg_stylesheets':len(styles),'embedded_font_hashes':sorted(font_hashes),
            'irrelevant_cases_losing_one_stored_positive_path':sum(r['answer_unchanged_despite_losing_stored_path'] for r in separation),
            'notes':'SVG contains the visible graph as vector primitives, not a hidden adjacency list. The fixed embedded font is identical in all 480 SVGs. JSON questions contain only task/endpoints; PNG-only inference must enforce the documented runner boundary.'}
    save(out/'export_boundary.json',report)
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('outputs/pilot'));p.add_argument('--output',type=Path,default=Path('outputs/phase1b'))
    args=p.parse_args();run(args.dataset,args.output)
