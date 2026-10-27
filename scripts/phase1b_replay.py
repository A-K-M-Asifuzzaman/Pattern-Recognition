"""Replay immutable historical generator to recover attempted-candidate metadata."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();sys.path.insert(0,str(args.source.resolve()))
    import topodelta_qa.dataset as generator
    from topodelta_qa.schema import Config
    assert Path(generator.__file__).resolve().is_relative_to(args.source.resolve())
    groups=generator.read_jsonl(args.dataset/'gold/groups.jsonl')
    rejects=generator.read_jsonl(args.dataset/'reports/rejections.jsonl')
    accepted={g['attempt']:g for g in groups}; rejected={r['attempt']:r for r in rejects}
    config=Config(**json.loads((args.dataset/'config.json').read_text()))
    real_base,real_scene=generator.base_graph,generator.scene
    captured={}
    def base(*a,**kw):
        result=real_base(*a,**kw);captured['graph']=result[0].json();return result
    def scene(*a,**kw):
        result=real_scene(*a,**kw)
        if 'style' not in captured:captured['style']=result['style']
        return result
    generator.base_graph=base;generator.scene=scene
    records=[];accepted_before=0;matches=0
    for attempt in range(len(groups)+len(rejects)):
        captured.clear();reason=''
        try:
            proposal=generator.propose(config,attempt,accepted_before,generator.split_schedule(config)[accepted_before])
        except ValueError as exc:
            reason=str(exc)
        if attempt in accepted:
            original=accepted[attempt]
            assert json.loads(json.dumps(proposal))=={k:v for k,v in original.items() if k!='variants'}|{'variants':[{k:v for k,v in v.items() if k not in ('asset_hashes','pixel_diff')} for v in original['variants']]}
            assert not reason
            matches+=1
        else:
            assert reason==rejected[attempt]['reason'] or not reason and rejected[attempt]['reason']=='cross_split_isomorphism_duplicate'
        graph=captured['graph']; n,m=len(graph['nodes']),len(graph['edges'])
        op_index=generator.design_schedule(config,'operations')[accepted_before]
        task_index=generator.design_schedule(config,'tasks')[accepted_before]
        records.append({'attempt':attempt,'accepted':int(attempt in accepted),'reason':'' if attempt in accepted else rejected[attempt]['reason'],
                        'nodes':n,'edges':m,'density':m/(n*(n-1)), 'style':captured.get('style','not_reached'),
                        'operation_first':generator.OPERATIONS[op_index], 'operation_second':generator.OPERATIONS[(op_index+1)%3],
                        'task_pair':generator.TASKS[task_index]+'/'+generator.TASKS[(task_index+1)%3]})
        accepted_before+=attempt in accepted
    out=args.output;out.mkdir(exist_ok=True,parents=True)
    def write(name,data):
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    write('attempted_candidates.csv',records)
    tables=[]
    for feature in ['nodes','edges','style','operation_first','task_pair']:
        totals=Counter(str(r[feature]) for r in records);ok=Counter(str(r[feature]) for r in records if r['accepted'])
        for value in sorted(totals):
            tables.append({'feature':feature,'value':value,'attempted':totals[value],'accepted':ok[value],
                           'rejected':totals[value]-ok[value],'acceptance_rate':ok[value]/totals[value]})
    write('acceptance_distribution.csv',tables)
    (out/'replay.json').write_text(json.dumps({'status':'passed','attempts_replayed':len(records),'accepted_proposals_exactly_matched':matches,
        'rejection_reasons':dict(Counter(r['reason'] for r in records if not r['accepted'])),
        'source':str(args.source),'limitations':'Historical rejection log lacks candidate features; recovered by deterministic replay of the snapshotted generator. Four candidates fail before a style is sampled. Replay is not independent evidence that this sampler is unbiased.'},sort_keys=True,indent=2)+'\n')
    print('Historical replay matched',matches,'accepted proposals and',len(rejects),'rejection outcomes')

if __name__=='__main__':main()
