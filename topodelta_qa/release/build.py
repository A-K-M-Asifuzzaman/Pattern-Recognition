"""Bounded, resumable deterministic creation. No inference/network code paths."""
import argparse
import hashlib
import json
import os
import shutil
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import networkx as nx
from PIL import ImageChops, ImageFont

from .drawing import RENDERER, png, svg
from .independent import verify_group
from .logic import network
from .sample import construct, make_plan


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n'


def write(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(canonical(value));os.replace(temporary,path)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def records(root):
    for path in sorted((Path(root)/'gold/records').glob('*.json')):yield json.loads(path.read_text())


def source_hashes():
    root=Path(__file__).resolve().parents[1]
    files=[Path(__file__).with_name(n+'.py') for n in ('__init__','drawing','logic','sample','independent','build')]
    files += [root/'render.py']
    return {p.relative_to(root.parent).as_posix():sha(p) for p in files}


def fingerprint(graph):
    g=network(graph)
    degree=tuple(sorted((g.in_degree(v),g.out_degree(v)) for v in g))
    return len(g),g.number_of_edges(),degree,nx.weisfeiler_lehman_graph_hash(g,iterations=3)


class IsoIndex:
    def __init__(self):self.buckets=defaultdict(list);self.exact_checks=0

    def match(self,group):
        seen=set()
        for v in group['variants']:
            graph=v['graph'];encoded=canonical(graph)
            if encoded in seen:continue
            seen.add(encoded);g=network(graph)
            for owner,split,role,other in self.buckets[fingerprint(graph)]:
                if split==group['split'] and not owner.startswith('history:') and not (v['role']=='original' and role=='original'):continue
                self.exact_checks+=1
                if nx.is_isomorphic(g,other):return {'group':owner,'split':split}
        return None

    def add(self,group):
        seen=set()
        for v in group['variants']:
            encoded=canonical(v['graph'])
            if encoded in seen:continue
            seen.add(encoded)
            self.buckets[fingerprint(v['graph'])].append((group['id'],group['split'],v['role'],network(v['graph'])))


def render(group,root):
    root=Path(root);original=None
    for variant in group['variants']:
        image=png(variant['scene'])
        if original is None:original=image.copy()
        if variant['edit']:
            channels=ImageChops.difference(original,image).split()
            difference=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
            mask=difference.point(lambda x:255 if x else 0)
            count=sum(mask.histogram()[1:]);assert count>=RENDERER['minimum_edit_changed_pixels'],'undetectably_small_edit'
            variant['pixel_change']={'changed_pixels':count,'fraction':count/(image.width*image.height),
                                     'box':list(mask.getbbox()),'mask_raw_sha256':hashlib.sha256(mask.tobytes()).hexdigest()}
        variant['assets']={ext:f'images/{variant["id"]}.{ext}' for ext in ('png','svg')}
        stem=root/'inference/images'/variant['id']
        image.save(stem.with_suffix('.png.tmp'),format='PNG',compress_level=1)
        os.replace(stem.with_suffix('.png.tmp'),stem.with_suffix('.png'))
        stem.with_suffix('.svg.tmp').write_text(svg(variant['scene']))
        os.replace(stem.with_suffix('.svg.tmp'),stem.with_suffix('.svg'))
        variant['asset_hashes']={ext:sha(root/'inference'/path) for ext,path in variant['assets'].items()}
        for path in variant['assets'].values():os.utime(root/'inference'/path,(0,0))
    return group


def initialize(root,config,key_path,history):
    assert not root.exists(),f'Output exists: use --resume for an unfinished matching build: {root}'
    for path in ('gold/records','gold/attempts','inference/images','inference/fonts'):(root/path).mkdir(parents=True,exist_ok=True)
    key=json.loads(key_path.read_text());assert len(bytes.fromhex(key['key_hex']))==32
    write(root/'gold/id_key.json',key)
    plan=make_plan(config);write(root/'gold/plan.json',plan)
    shutil.copyfile(history/'gold/groups.jsonl',root/'gold/historical_blacklist.jsonl')
    write(root/'gold/build.json',{'config':config,'source_hashes':source_hashes(),'historical_manifest_sha256':sha(history/'manifest.json'),
                                 'historical_path':'outputs/topodelta_qa_v0.2.0','retained_historical_groups':0,'renderer':RENDERER})
    (root/'inference/fonts/Aileron-Regular.ttf').write_bytes(ImageFont.load_default(size=26).path.getvalue())
    return plan


def build(config_path,root,limit=None,resume=False):
    config=json.loads(config_path.read_text());target=config['groups'] if limit is None else min(limit,config['groups'])
    if resume:
        assert root.exists() and not (root/'manifest.json').exists(),'Only unfinished builds may resume'
        metadata=json.loads((root/'gold/build.json').read_text())
        assert metadata['config']==config and metadata['source_hashes']==source_hashes(),'Build/config source changed; preserve checkpoint and use a new version'
        plan=json.loads((root/'gold/plan.json').read_text())
    else:plan=initialize(root,config,Path('configs/evaluator_id_key.json'),Path('outputs/topodelta_qa_v0.2.0'))
    key=json.loads((root/'gold/id_key.json').read_text())['key_hex']
    index=IsoIndex()
    for line in (root/'gold/historical_blacklist.jsonl').read_text().splitlines():
        historical=json.loads(line);historical['id']='history:'+historical['id'];index.add(historical)
    existing=list(records(root));assert [g['slot'] for g in existing]==list(range(len(existing))), 'Noncontiguous checkpoint'
    for group in existing:index.add(group)
    start=len(existing);del existing
    pending=deque();started=time.monotonic();run_rejects=Counter();timings=[]
    log_path=root.parent/(root.name+'.runtime.jsonl')
    def commit():
        future,attempts=pending.popleft();group=future.result()
        write(root/f'gold/attempts/{group["slot"]:05d}.json',attempts)
        write(root/f'gold/records/{group["slot"]:05d}.json',group)
        return group['slot']+1
    with ProcessPoolExecutor(max_workers=config['workers']) as pool:
        for slot in range(start,target):
            if slot%config['batch_groups']==0:
                free=shutil.disk_usage(root).free
                assert free>=config['minimum_free_gib']*1024**3,'disk_reserve_exhausted'
                print(f'Creating slot {slot}/{target}; free {free/1024**3:.1f} GiB; rejections this run {sum(run_rejects.values())}',flush=True)
            intent=plan[slot];attempts=[];slot_start=time.monotonic()
            for trial in range(config['max_trials_per_slot']):
                try:
                    group=construct(intent,trial,config,key);verify_group(group)
                    match=index.match(group)
                    if match:raise AssertionError('historical_or_other_group_isomorphism_duplicate')
                except AssertionError as exc:
                    reason=str(exc) or 'assertion_failed';run_rejects[reason]+=1
                    attempts.append({'trial':trial,'status':'rejected','reason':reason})
                    continue
                attempts.append({'trial':trial,'status':'accepted'});index.add(group)
                pending.append((pool.submit(render,group,str(root)),attempts));break
            else:
                write(root/f'gold/attempts/{slot:05d}.failed.json',attempts)
                raise RuntimeError(f'No valid candidate for {intent}; quality constraints unchanged')
            timings.append(time.monotonic()-slot_start)
            if len(pending)>=config['workers']:
                accepted=commit()
                if accepted%config['batch_groups']==0:
                    entry={'groups_committed':accepted,'elapsed_run_seconds':round(time.monotonic()-started,3),
                           'run_rejections':dict(run_rejects),'disk_bytes_free':shutil.disk_usage(root).free}
                    with log_path.open('a') as f:f.write(canonical(entry))
                    print(f'Committed {accepted}; elapsed {entry["elapsed_run_seconds"]}s',flush=True)
        while pending:commit()
    assert len(list((root/'gold/records').glob('*.json')))==target
    runtime={'status':'checkpoint_complete' if target<config['groups'] else 'generation_complete',
             'groups':target,'from_group':start,'elapsed_seconds':round(time.monotonic()-started,3),
             'new_rejections':dict(run_rejects),'exact_iso_candidate_checks':index.exact_checks,
             'candidate_construction_seconds':round(sum(timings),3),'workers':config['workers']}
    with log_path.open('a') as f:f.write(canonical(runtime))
    print(json.dumps(runtime,indent=2),flush=True)
    return runtime


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path('configs/release_candidate.json'))
    p.add_argument('--output',type=Path,default=Path('outputs/topodelta_qa_v0.3.0-rc1'))
    p.add_argument('--limit',type=int);p.add_argument('--resume',action='store_true');a=p.parse_args()
    build(a.config,a.output,a.limit,a.resume)


if __name__=='__main__':main()
