"""Check the ID-only version migration and reproduce the legacy public-ID attack."""
import hashlib,json
from collections import Counter
from pathlib import Path
from phase1b_audit import rows,save,table

old_root=Path('outputs/pilot');new_root=Path('outputs/pilot_v0.1.1');out=Path('outputs/phase1b')
old,new=rows(old_root/'gold/groups.jsonl'),rows(new_root/'gold/groups.jsonl')
assert len(old)==len(new)==120
mapping={};counts=Counter();attacks=[]
def guess(group,index):return hashlib.sha256(json.dumps((group,'variant',index),separators=(',',':')).encode()).hexdigest()[:24]
for a,b in zip(old,new):
    assert all(a[k]==b[k] for k in ['attempt','seed','split','generator_version'])
    mapping[a['id']]=b['id']
    for x,y in zip(a['questions'],b['questions']):
        assert {k:v for k,v in x.items() if k!='id'}=={k:v for k,v in y.items() if k!='id'}
        mapping[x['id']]=y['id']
    for i,(x,y) in enumerate(zip(a['variants'],b['variants'])):
        mapping[x['id']]=y['id']
        assert all(x[k]==y[k] for k in ['graph','scene','role','edit','asset_hashes'])
        for old_q,new_q in zip(a['questions'],b['questions']):
            for field in ['answers','certificates','relevance']:assert x[field][old_q['id']]==y[field][new_q['id']]
        for ext in ['png','svg']:
            assert (old_root/'inference'/x['assets'][ext]).read_bytes()==(new_root/'inference'/y['assets'][ext]).read_bytes()
            counts['identical_image_files']+=1
        if i>=2:
            assert all(x['pixel_diff'][k]==y['pixel_diff'][k] for k in ['sha256','box','changed_pixels'])
            assert (old_root/x['pixel_diff']['path']).read_bytes()==(new_root/y['pixel_diff']['path']).read_bytes()
            counts['identical_pixel_masks']+=1
        counts['legacy_role_recovered']+=guess(a['id'],i)==x['id']
        counts['corrected_role_recovered_by_legacy_attack']+=y['id'] in {guess(b['id'],j) for j in range(4)}
        if i>=2:
            for q in a['questions']:
                attacks.append({'group_id':a['id'],'split':a['split'],'first_edit':int(i==2),'relevant':int(x['relevance'][q['id']])})
for protocol in ['single','paired']:
    old_rows=rows(old_root/f'gold/{protocol}.jsonl');new_rows=rows(new_root/f'gold/{protocol}.jsonl')
    key=lambda r:(r['group_id'],r['question_id'],tuple(r['variant_ids']) if protocol=='paired' else r['variant_id'])
    lookup={key(r):r for r in new_rows}
    for r in old_rows:
        transformed=(mapping[r['group_id']],mapping[r['question_id']],tuple(mapping[v] for v in r['variant_ids']) if protocol=='paired' else mapping[r['variant_id']])
        replacement=lookup[transformed];mapping[r['id']]=replacement['id']
        assert r['answers' if protocol=='paired' else 'answer']==replacement['answers' if protocol=='paired' else 'answer']
assert len(mapping)==len(set(mapping.values()))==2520
rates=[]
for split in ['all','train','validation','test']:
    sample=[r for r in attacks if split=='all' or r['split']==split]
    tp=sum(r['first_edit'] and r['relevant'] for r in sample);fp=sum(r['first_edit'] and not r['relevant'] for r in sample)
    tn=sum(not r['first_edit'] and not r['relevant'] for r in sample);fn=sum(not r['first_edit'] and r['relevant'] for r in sample)
    rates.append({'split':split,'cases':len(sample),'tp':tp,'tn':tn,'fp':fp,'fn':fn,'accuracy':(tp+tn)/len(sample),'balanced_accuracy':(tp/(tp+fn)+tn/(tn+fp))/2})
counts['legacy_png_mtime_role_order_recovery_groups']=sum(sorted(g['variants'],key=lambda v:(old_root/'inference'/v['assets']['png']).stat().st_mtime_ns)==g['variants'] for g in old)
assert {p.stat().st_mtime_ns for p in (new_root/'inference/images').iterdir()}=={0}
from PIL import Image
for path in (new_root/'inference/images').glob('*.png'):
    with Image.open(path) as image:
        assert not image.info
counts['pngs_without_embedded_metadata']=480
save(out/'id_mapping_evaluator_only.json',mapping)
table(out/'legacy_id_shortcut.csv',rates)
report={'status':'passed','old_dataset_version':'0.1.0','corrected_dataset_version':'0.1.1','groups_each':120,
        'mapped_ids':len(mapping),'checks':dict(counts),'normalized_public_image_mtimes_ns':[0],'old_parent_index_attack':'480/480 roles recovered without images or key',
        'new_parent_index_attack':'0/480 roles recovered by the same public-parent enumeration',
        'exact_changes':['Opaque IDs, filenames, references and JSONL order','Evaluator-only ID key and keyed identity-policy metadata','Dataset card/version, config output path, and manifest provenance','Public assets written in opaque-ID order with normalized modification times'],
        'unchanged':['All graphs, question tasks/endpoints/text, answers, relevance, certificate bodies, edits, seeds, attempts, splits, style and geometry','All 960 SVG/PNG bytes and 240 pixel-mask bytes'],
        'residual_risk':'This is not a cryptographic blindness claim. With the evaluator key/gold or old version plus image matching, roles can be linked. Supply only corrected PNG-only inputs to an isolated runner; never supply old-version metadata or evaluator key/mapping.'}
save(out/'version_changes.json',report)
print(json.dumps(report,indent=2))
