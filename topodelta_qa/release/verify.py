"""Saved-file validation, streamed with two bounded local processes."""
import argparse
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .build import records, sha, write
from .drawing import RENDERER, png, svg, validate_scene
from .independent import verify_group
from .logic import annotate
from .split_audit import Index
from .diagnostics import image_statistics, report as shortcut_report


def saved_record(task):
    path,root=map(Path,task);group=json.loads(path.read_text());counts=verify_group(group)
    assert len({q['id'] for q in group['questions']})==2
    assert all(q['source']!=q['target'] and q['source'] in group['variants'][0]['graph']['nodes'] and q['target'] in group['variants'][0]['graph']['nodes'] for q in group['questions'])
    original=None;hashes=[];statistics=[]
    for v in group['variants']:
        assert v['geometry_checks']==validate_scene(v['graph'],v['scene'])
        for q in group['questions']:
            a,_=annotate(v['graph'],q)
            assert type(a) is type(v['answers'][q['id']]) and a==v['answers'][q['id']]
        generated=png(v['scene'])
        statistics.append({'group_id':group['id'],'variant_id':v['id'],'split':group['split'],**image_statistics(generated)})
        if original is None:original=generated.copy()
        for ext,relative in v['assets'].items():
            assert relative==f'images/{v["id"]}.{ext}' and re.fullmatch('[0-9a-f]{24}',v['id'])
            asset=root/'inference'/relative
            assert sha(asset)==v['asset_hashes'][ext] and asset.stat().st_mtime==0
        with Image.open(root/'inference'/v['assets']['png']) as image:
            assert image.mode=='RGB' and image.size==tuple(v['scene']['canvas']) and not image.info
            assert ImageChops.difference(image,generated).getbbox() is None
        assert (root/'inference'/v['assets']['svg']).read_text()==svg(v['scene'])
        hashes.append((v['id'],v['asset_hashes']['png']))
        if v['edit']:
            channels=ImageChops.difference(original,generated).split()
            mask=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2]).point(lambda x:255 if x else 0)
            count=sum(mask.histogram()[1:]);metadata=v['pixel_change']
            assert count>=RENDERER['minimum_edit_changed_pixels'] and count==metadata['changed_pixels']
            assert list(mask.getbbox())==metadata['box'] and count/(generated.width*generated.height)==metadata['fraction']
            assert hashlib.sha256(mask.tobytes()).hexdigest()==metadata['mask_raw_sha256']
            allowed=Image.new('L',generated.size);draw=ImageDraw.Draw(allowed)
            edges={tuple(e) for k in ('added','deleted') for e in v['edit'][k]}
            for drawing in (group['variants'][0]['scene'],v['scene']):
                for edge in drawing['edges']:
                    if tuple(edge['edge']) not in edges:continue
                    points=edge['line']+edge['arrowhead'];xs,ys=zip(*points)
                    draw.rectangle((min(xs)-5,min(ys)-5,max(xs)+5,max(ys)+5),fill=255)
            assert ImageChops.subtract(mask,allowed).getbbox() is None,'unintended_raster_change'
    return counts,group['id'],hashes,statistics


def validate(root,out,expected=None,limit=None):
    paths=sorted((root/'gold/records').glob('*.json'))
    if limit is not None:paths=paths[:limit]
    if expected is not None:assert len(paths)==expected
    counters=Counter();images={};group_ids=set();statistics=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for count,gid,hashes,stats in pool.map(saved_record,((str(p),str(root)) for p in paths),chunksize=8):
            statistics.extend(stats)
            assert gid not in group_ids;group_ids.add(gid);counters.update(count)
            for vid,digest in hashes:
                assert digest not in images,f'Duplicate PNG {vid}, {images.get(digest)}'
                images[digest]=vid
            if len(group_ids)%1000==0:print(f'Validated {len(group_ids)} groups and {len(images)} PNG/SVG pairs',flush=True)
    index=Index();index.add_history(json.loads(line) for line in (root/'gold/historical_blacklist.jsonl').read_text().splitlines())
    if limit is None:
        expected_assets={vid+'.'+ext for vid in images.values() for ext in ('png','svg')}
        assert {p.name for p in (root/'inference/images').iterdir()}==expected_assets,'orphan_or_missing_assets'
    plan=json.loads((root/'gold/plan.json').read_text())
    for g in records(root):
        if limit is not None and g['slot']>=limit:break
        assert g['intent']==plan[g['slot']] and g['split']==plan[g['slot']]['split'],'plan_membership_mismatch'
        index.verify_add(g)
    splits=index.report();out.mkdir(parents=True,exist_ok=True)
    if limit is None:shortcut_report(root,statistics,out)
    write(out/'split_isomorphism.json',splits)
    result={'status':'passed','checked':dict(counters),'pngs':len(images),'svgs':len(images),
            'duplicate_pngs':0,'png_metadata_free':len(images),'saved_png_svg_regeneration':'all passed',
            'pixel_footprint_and_detectability_checks':counters['edits'],'human_review':False,
            'independent_semantics':'Raw JSON Floyd–Warshall and structural certificate validation; no primary/NetworkX imports',
            'split_isomorphism':'Independent refinement plus exact adjacency backtracking across all variants and historical blacklist'}
    write(out/'validation.json',result);print(json.dumps(result,indent=2),flush=True);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('outputs/topodelta_qa_v0.3.0-rc1'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected',type=int);p.add_argument('--limit',type=int);a=p.parse_args()
    validate(a.dataset,a.output,a.expected,a.limit)


if __name__=='__main__':main()
