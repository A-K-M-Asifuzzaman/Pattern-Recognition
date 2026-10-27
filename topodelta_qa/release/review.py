"""Reproducible agent-inspection sheets and blank, blind human-review packets."""
import argparse
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .build import records, write
from .logic import question_text


def tags(g):
    c=g['coverage']
    return {f'{k}:{c[k]}' for k in ('nodes','layout','style','density_bin','topology','connectivity','difficulty_bin')} | {
        'task:'+q['task'] for q in g['questions']} | {'op:'+v['edit']['operation'] for v in g['variants'][2:]}


def select(groups,count,namespace,required=()):
    selected=list(required);ids={g['id'] for g in selected};covered=set().union(*(tags(g) for g in selected)) if selected else set()
    remaining=[g for g in groups if g['id'] not in ids]
    # Greedy marginal coverage, then hash sampling avoids a huge exhaustive product claim.
    while len(selected)<min(count,len(groups)):
        if not remaining:break
        key=lambda g:(-len(tags(g)-covered),hashlib.sha256((namespace+g['id']).encode()).hexdigest())
        chosen=min(remaining,key=key);selected.append(chosen);covered|=tags(chosen)
        remaining.remove(chosen)
    return selected


def stratified(groups,count,namespace,required=()):
    sizes=sorted({g['coverage']['nodes'] for g in groups});target=min(count,len(groups));chosen=[]
    for i,n in enumerate(sizes):
        quota=target//len(sizes)+(i<target%len(sizes))
        subset=[g for g in groups if g['coverage']['nodes']==n]
        retained=[g for g in required if g['coverage']['nodes']==n]
        assert len(retained)<=quota<=len(subset),'Review size-stratum quota infeasible'
        chosen.extend(select(subset,quota,namespace+str(n)+':',retained))
    assert len(chosen)==target and len({g['id'] for g in chosen})==target
    return chosen


def sheets(root,groups,out,namespace):
    out.mkdir(parents=True,exist_ok=False);font=ImageFont.load_default(size=17)
    summaries=[]
    for page in range(0,len(groups),4):
        chosen=groups[page:page+4];canvas=Image.new('RGB',(4*768,len(chosen)*850),'#dddddd');draw=ImageDraw.Draw(canvas)
        for row,g in enumerate(chosen):
            c=g['coverage'];label=f'{g["id"]} | n={c["nodes"]} {c["layout"]} style={c["style"]} {c["density_bin"]} {c["topology"]} {c["connectivity"]}'
            draw.text((8,row*850+3),label,font=font,fill='black')
            for col,v in enumerate(g['variants']):
                with Image.open(root/'inference'/v['assets']['png']) as im:
                    im=im.resize((768,768),Image.Resampling.LANCZOS);canvas.paste(im,(col*768,row*850+64))
                caption=f'{v["role"]} '+(v['edit']['operation'] if v['edit'] else '')
                draw.text((col*768+8,row*850+30),caption,font=font,fill='black')
            summaries.append({'group_id':g['id'],'slot':g['slot'],'sheet':f'sheet_{page//4:03d}.png','row':row,
                              'coverage':c,'operations':[v['edit']['operation'] for v in g['variants'][2:]]})
        canvas.save(out/f'sheet_{page//4:03d}.png',compress_level=1)
    write(out/'selection.json',{'namespace':namespace,'selected_groups':summaries,'all_four_images':True,
          'status':'prepared; inspection records must be written only after actual viewing'})
    return summaries


def checkpoint(root,out):
    groups=list(records(root));assert len(groups)==500
    chosen=select(groups,32,'rc-checkpoint-visual-v1:')
    return sheets(root,chosen,out,'rc-checkpoint-visual-v1:')


def human_packet(root,out,count=400):
    # Lightweight summaries retain only data needed for stratification.
    summaries=[];flagged=[]
    for g in records(root):
        summary={k:g[k] for k in ('id','slot','coverage','questions')}
        summary['variants']=[{'edit':v['edit']} for v in g['variants']]
        summaries.append(summary)
        if any(v['geometry_checks']['minimum_route_clearance'] is not None and v['geometry_checks']['minimum_route_clearance']<8 for v in g['variants']):flagged.append(summary)
    selected=stratified(summaries,count,'rc-human-400-v1:');ids={g['id'] for g in selected}
    selected += [g for g in flagged if g['id'] not in ids]
    out.mkdir(parents=True,exist_ok=False);(out/'groups').mkdir()
    key=root/'gold/human_review_key.jsonl';index=[]
    import random
    with key.open('w') as answer_file:
        for g in selected:
            group=json.loads((root/f'gold/records/{g["slot"]:05d}.json').read_text())
            variants=group['variants'].copy();random.Random('blind-human:'+g['id']).shuffle(variants)
            panels=[];answers=[]
            for label,v in zip('ABCD',variants):
                asset='../../../inference/'+v['assets']['png']
                fields=[]
                for i,q in enumerate(group['questions']):
                    fields.append(f'<p>{html.escape(question_text(q))}<br>Answer: <input aria-label="Image {label} question {i+1} answer"></p>')
                panels.append(f'<section><h2>Image {label}</h2><a href="{asset}"><img src="{asset}" alt="Diagram {label}"></a>'+''.join(fields)+'<p>Readability: <input> Ambiguity: <input> Edge directions clear: <input></p><p>Problematic labels/edges and notes:<textarea></textarea></p></section>')
                answers.append({'blind_image':label,'variant_id':v['id'],'role':v['role'],'edit':v['edit'],'answers':v['answers'],'certificates':v['certificates']})
            page=f'<!doctype html><meta charset="utf-8"><title>Blind diagram review {g["id"]}</title><style>body{{font:18px system-ui;margin:24px}}main{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}img{{width:100%}}input{{margin:5px}}textarea{{width:100%;height:70px}}</style><h1>Group {g["id"]}</h1><p>Arrows run from tail to arrowhead. Crossings are not junctions unless there is an explicit node. Click images to enlarge. Forms are blank and print-friendly; use the CSV template to save a review.</p><main>'+''.join(panels)+'</main><p>Reviewer identity: __________ Date: __________ Disagreement: __________ Adjudication: __________ Exclusion reason: __________</p>'
            (out/'groups'/f'{g["id"]}.html').write_text(page)
            index.append(f'<li><a href="groups/{g["id"]}.html">{g["id"]}</a></li>')
            answer_file.write(json.dumps({'group_id':g['id'],'questions':group['questions'],'images':answers},sort_keys=True,separators=(',',':'))+'\n')
    (out/'index.html').write_text(f'<!doctype html><meta charset="utf-8"><title>TopoDelta-QA blind human review</title><h1>Blank human-review packet</h1><p>{min(count,len(summaries))} reproducibly stratified groups plus all automatically flagged accepted groups. No reviews have occurred. No answers or edit roles are present in this packet.</p><ul>'+''.join(index)+'</ul>')
    (out/'review_record_template.csv').write_text('reviewer_identity,review_date,group_id,blind_image,question_number,answer,readability,ambiguity,edge_direction_clear,problematic_labels_or_edges,disagreement,adjudicator_identity,adjudication_date,adjudication,exclude,exclusion_reason\n')
    write(root/'gold/human_review_selection.json',{'sample_seed':'rc-human-400-v1:','stratified_sample_groups':min(count,len(summaries)),'automatically_flagged_groups':len(flagged),
          'total_packet_groups':len(selected),'group_ids':[g['id'] for g in selected],'flag_rule':'accepted minimum route clearance <8 pixels; geometric rejection threshold remains 5 pixels',
          'stratification':'26 or 27 groups per exact node count, greedy layout/style/task/density/operation coverage then hash ranking within each size',
          'human_reviews_completed':0})
    return len(selected)


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('outputs/topodelta_qa_v0.3.0-rc1'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',action='store_true');a=p.parse_args()
    if a.checkpoint:checkpoint(a.dataset,a.output)


if __name__=='__main__':main()
