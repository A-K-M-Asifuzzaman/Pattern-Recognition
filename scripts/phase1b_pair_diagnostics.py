"""Report redraw-mixture effects separately from edit-only shortcut diagnostics."""
import argparse
import csv
import random
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
from phase1b_audit import rows,table,auc

parser=argparse.ArgumentParser();parser.add_argument('--dataset',type=Path,default=Path('outputs/pilot'));parser.add_argument('--output',type=Path,default=Path('outputs/phase1b'))
args=parser.parse_args();root=args.dataset;out=args.output
edits=list(csv.DictReader((out/'edited_question_features.csv').open()))
records=[{k:r[k] for k in ['group_id','split','variant_id','question_id','task']}|{
    'pair_kind':'edited','relevant':int(r['relevant']),'changed_pixel_fraction':float(r['changed_pixel_fraction']),
    'mean_absolute_pixel_difference':float(r['mean_absolute_pixel_difference'])} for r in edits]
for g in rows(root/'gold/groups.jsonl'):
    a,b=g['variants'][:2]
    with Image.open(root/'inference'/a['assets']['png']) as im:original=im.convert('L')
    with Image.open(root/'inference'/b['assets']['png']) as im:redraw=im.convert('L')
    diff=ImageChops.difference(original,redraw)
    for q in g['questions']:
        records.append({'group_id':g['id'],'split':g['split'],'variant_id':b['id'],'question_id':q['id'],'task':q['task'],
                        'pair_kind':'redraw','relevant':0,'changed_pixel_fraction':sum(diff.histogram()[1:])/640000,
                        'mean_absolute_pixel_difference':ImageStat.Stat(diff).mean[0]})
table(out/'all_pair_pixel_features.csv',records)
report=[]
for split in ['train','validation','test']:
    rs=[r for r in records if r['split']==split];gids=sorted({r['group_id'] for r in rs})
    for feature in ['changed_pixel_fraction','mean_absolute_pixel_difference']:
        rng=random.Random(20261027);scores=[]
        for _ in range(300):
            draws=rng.choices(gids,k=len(gids));sample=[r for gid in draws for r in rs if r['group_id']==gid]
            value=auc(sample,feature)
            if value is not None:scores.append(value)
        scores.sort()
        report.append({'split':split,'feature':feature,'pairs':len(rs),'auroc_increasing_feature':auc(rs,feature),
                       'group_bootstrap_95_low':scores[int(.025*(len(scores)-1))],'group_bootstrap_95_high':scores[int(.975*(len(scores)-1))]})
table(out/'shortcut_all_pair_pixels.csv',report)
