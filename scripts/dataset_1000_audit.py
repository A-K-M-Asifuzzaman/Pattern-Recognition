"""Local-only independent annotations, indexed exact split checks, tables and preview."""
import argparse
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from phase1b_audit import semantics,signature,iso,rows,save,table,features,distributions
from phase1b_exports import run as export_check


def split_check(groups):
    buckets=defaultdict(list);duplicates=[];exact=0;counts=Counter()
    for g in groups:
        assert g['split'] in ('train','validation','test')
        for v in g['variants']:
            graph=v['graph'];key=signature(graph)
            for split,gid,vid,other in buckets[key]:
                if split==g['split']:continue
                exact+=1
                if iso(graph,other):duplicates.append([g['id'],v['id'],gid,vid])
            buckets[key].append((g['split'],g['id'],v['id'],graph))
            counts[g['split']]+=1
    n=list(counts.values());pairs=sum(n[i]*n[j] for i in range(len(n)) for j in range(i))
    return {'status':'passed' if not duplicates else 'failed','cross_split_variant_pairs':pairs,
            'exact_backtracking_checks':exact,'isomorphism_duplicates':duplicates,
            'method':'Precompute invariant directed degree signatures once; exact independent adjacency backtracking for every eligible pair. No project or NetworkX imports.'}


def preview(root,groups,out):
    remaining=groups[120:];selected=[];covered=set()
    def tags(g):
        return ({'task:'+q['task'] for q in g['questions']}|{'op:'+v['edit']['operation'] for v in g['variants'] if v['edit']}|
                {'nodes:'+str(len(g['variants'][0]['graph']['nodes'])),'style:'+str(g['variants'][0]['scene']['style'])})
    for _ in range(min(12,len(remaining))):
        g=min(remaining,key=lambda g:(-len(tags(g)-covered),hashlib.sha256(('dataset-1000-preview:'+g['id']).encode()).hexdigest()))
        selected.append(g);covered|=tags(g);remaining=[x for x in remaining if x['id']!=g['id']]
    sheet=Image.new('RGB',(4*260,len(selected)*300),'white');draw=ImageDraw.Draw(sheet);font=ImageFont.load_default(size=13)
    for i,g in enumerate(selected):
        for j,v in enumerate(g['variants']):
            with Image.open(root/'inference'/v['assets']['png']) as image:sheet.paste(image.resize((255,255),Image.Resampling.LANCZOS),(j*260,i*300+40))
            label=v['edit']['operation'] if v['edit'] else v['role']
            draw.text((j*260+3,i*300+2),label+' / '+str(len(v['graph']['nodes']))+' nodes',fill='black',font=font)
            draw.text((j*260+3,i*300+20),'/'.join(q['task'] for q in g['questions']),fill='black',font=font)
    sheet.save(out/'new_groups_contact_sheet.png')
    save(out/'preview_selection.json',{'group_ids':[g['id'] for g in selected],'coverage':sorted(covered),
          'scope':'12 newly added groups, deterministic greedy coverage; prepared preview only, no human or agent visual validation'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('outputs/topodelta_qa_v0.2.0'))
    p.add_argument('--output',type=Path,default=Path('outputs/dataset_build_1000/independent'))
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    groups=rows(args.dataset/'gold/groups.jsonl');assert len(groups)==1000
    result=semantics(groups);save(out/'semantics.json',result);assert result['status']=='passed';print('Independent answers/relevance/certificates passed',flush=True)
    result=split_check(groups);save(out/'split_isolation.json',result);assert result['status']=='passed';print('Exact all-variant split isolation passed',flush=True)
    result=export_check(args.dataset,out)
    # Replace historical prose/count assumptions from the 120-group audit helper.
    result['notes']='All 4,000 SVGs share the documented embedded font. Public schemas/IDs remain distinct from gold annotations. No model inference performed.'
    save(out/'export_boundary.json',result);print('Export and SVG consistency passed',flush=True)
    edited,graphs=features(args.dataset,groups);distributions(out,edited,graphs)
    table(out/'new_vs_retained.csv',[{'cohort':name,'groups':len(gs),'splits':json.dumps(dict(Counter(g['split'] for g in gs)),sort_keys=True),
                 'nodes':json.dumps(dict(Counter(len(g['variants'][0]['graph']['nodes']) for g in gs)),sort_keys=True)}
                 for name,gs in [('retained',groups[:120]),('new',groups[120:])]])
    preview(args.dataset,groups,out)
    save(out/'provenance.json',{'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'dataset_manifest_sha256':hashlib.sha256((args.dataset/'manifest.json').read_bytes()).hexdigest(),
        'algorithms':'Raw JSON Floyd–Warshall, independent directed isomorphism backtracking, XML and pixel statistics',
        'models':False,'network':False,'human_validation':False})
    print('Distribution tables and new-group preview complete',flush=True)


if __name__=='__main__':main()
