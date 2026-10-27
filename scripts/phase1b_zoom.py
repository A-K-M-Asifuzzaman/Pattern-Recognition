"""Reproducible enlargements of actual PNG bytes for agent review, not new inputs."""
import argparse
import json
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser();parser.add_argument('--dataset',type=Path,default=Path('outputs/pilot'));parser.add_argument('--output',type=Path,default=Path('outputs/phase1b'))
args=parser.parse_args();root=args.dataset;out=args.output/'visual_enlargements';out.mkdir(exist_ok=True)
selection=json.loads((args.output/'visual_selection.json').read_text())
groups={g['id']:g for g in map(json.loads,(root/'gold/groups.jsonl').read_text().splitlines())}
records=[]
for sequence,label in [(6,'RB'),(9,'TG'),(15,'HA'),(16,'ZT'),(17,'JN'),(23,'DJ')]:
    g=groups[selection[sequence-1]['group_id']];v=g['variants'][0]
    node=next(n for n in v['scene']['nodes'] if n['label']==label);x,y=node['center']
    box=(round(x-95),round(y-95),round(x+95),round(y+95))
    with Image.open(root/'inference'/v['assets']['png']) as image:
        image.resize((1600,1600),Image.Resampling.NEAREST).save(out/f'{sequence:02d}_original_2x.png')
        image.crop(box).resize((950,950),Image.Resampling.NEAREST).save(out/f'{sequence:02d}_{label}_5x.png')
    records.append({'sequence':sequence,'group_id':g['id'],'variant_id':v['id'],'node_label':label,'crop_box':box,
                    'original_png':v['assets']['png'],'full_view':f'{sequence:02d}_original_2x.png','detail_view':f'{sequence:02d}_{label}_5x.png',
                    'method':'nearest-neighbor mechanical enlargement; no re-rendering or interpolation of new geometry'})
(out/'index.json').write_text(json.dumps(records,indent=2)+'\n')
