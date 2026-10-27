"""Deterministic coverage, answer transitions, and attempt/acceptance diagnostics."""
import csv
import itertools
import json
from collections import Counter
from pathlib import Path

import networkx as nx

from .build import records, write
from .logic import network


def table(path,rows,fields=None):
    with Path(path).open('w',newline='') as f:
        if fields is None:
            if not rows:return
            fields=list(rows[0])
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def counted(path,counter,fields):
    table(path,[dict(zip(fields,k),count=v) for k,v in sorted(counter.items(),key=lambda item:str(item[0]))])


def report(root):
    out=root/'reports';out.mkdir(exist_ok=True)
    dimensions=('split','nodes','layout','style','topology','connectivity','density_bin','difficulty_bin')
    cells=Counter();answers=Counter();transitions=Counter();lengths=Counter();attempts=Counter();requested=Counter()
    simple={name:Counter() for name in dimensions};operations=Counter();tasks=Counter();flags=Counter();sizes=Counter();rows=[];pixels=[];variant_rows=[]
    for g in records(root):
        c=g['coverage'];summary={**c,'group_id':g['id'],'split':g['split'],'slot':g['slot']}
        summary['accepted_trial']=g['trial'];rows.append(summary);cell=tuple(summary[k] for k in dimensions);cells[cell]+=1
        flags['extended_template_groups']+=g['trial']>=1000
        flags['isolated_pocket_template_groups']+=g['trial']>=5000 and c['nodes']==6 and c['layout']=='concentric'
        for name in dimensions:simple[name][str(summary[name])]+=1
        sizes[c['nodes']]+=1
        requested[(c['nodes'],c['layout'],c['topology'],c['connectivity'],c['density_bin'])]+=1
        for feature in ('branches','merges','alternative_paths','weak_bridges','unqueried_nodes','unreachable_ordered_pairs'):
            flags[feature+'_present']+=bool(c[feature])
        flags['question_sign_fallback_groups']+=c['question_sign_fallback']
        original=g['variants'][0]
        for q in g['questions']:tasks[(g['split'],q['task'])]+=1
        for v in g['variants']:
            distances=dict(nx.all_pairs_shortest_path_length(network(v['graph'])))
            n=len(v['graph']['nodes']);m=len(v['graph']['edges']);finite=[d for a,ds in distances.items() for b,d in ds.items() if a!=b]
            variant_rows.append({'group_id':g['id'],'variant_id':v['id'],'split':g['split'],'role':v['role'],'nodes':n,'edges':m,
                 'edges_per_node':m/n,'directed_density':m/(n*(n-1)),'maximum_finite_shortest_path':max(finite,default=0),
                 'unreachable_ordered_pairs':n*(n-1)-len(finite),'layout':c['layout'],'style':v['scene']['style']})
            for q in g['questions']:
                a=v['answers'][q['id']]
                answers[(g['split'],q['task'],v['role'],json.dumps(a),str(v['scene']['style']))]+=1
                lengths[(g['split'],q['task'],v['role'],str(distances[q['source']].get(q['target'],'unreachable')))]+=1
            if v['edit']:
                op=v['edit']['operation'];operations[(g['split'],op)]+=1
                pixel=v['pixel_change'];pixels.append({'group_id':g['id'],'variant_id':v['id'],'split':g['split'],'nodes':c['nodes'],
                     'layout':c['layout'],'style':c['style'],'operation':op,'width':v['scene']['canvas'][0],**pixel})
                for q in g['questions']:
                    relevant=v['relevance'][q['id']];before=original['answers'][q['id']];after=v['answers'][q['id']]
                    transitions[(g['split'],q['task'],op,json.dumps(before),json.dumps(after),relevant,str(c['style']),c['layout'])]+=1
                    entry=v['answer_change_evidence'][q['id']]
                    flags['relevant_edit_question_cases' if relevant else 'irrelevant_edit_question_cases']+=1
                    if not relevant:
                        flags['irrelevant_same_original_weak_component']+=entry['same_original_weak_component_as_edit']
                        flags['irrelevant_deleted_on_stored_positive_path']+=entry['deleted_edge_on_stored_original_path']
        for a in json.loads((root/f'gold/attempts/{g["slot"]:05d}.json').read_text()):
            attempts[(c['nodes'],c['layout'],c['style'],g['intent']['topology'],g['intent']['connectivity'],g['intent']['density'],
                      g['intent']['relevant_task'],g['intent']['irrelevant_task'],g['intent']['operation'],g['intent']['second_operation'],a.get('reason','accepted'))]+=1
    counted(out/'coverage_cells.csv',cells,dimensions)
    for name,counts in simple.items():counted(out/f'{name}_groups.csv',Counter({(k,):v for k,v in counts.items()}),(name,))
    counted(out/'answer_distribution.csv',answers,('split','task','role','answer','style'))
    counted(out/'answer_transitions.csv',transitions,('split','task','operation','original_answer','edited_answer','relevant','style','layout'))
    counted(out/'question_path_lengths.csv',lengths,('split','task','role','path_length'))
    counted(out/'operations.csv',operations,('split','operation'))
    counted(out/'tasks.csv',tasks,('split','task'))
    counted(out/'attempts_by_cell_reason.csv',attempts,('nodes','layout','style','topology','connectivity','density_bin','relevant_task','irrelevant_task','operation','second_operation','result'))
    table(out/'group_features.csv',rows);table(out/'variant_features.csv',variant_rows);table(out/'edit_pixel_changes.csv',pixels)
    missing=[]
    for n,layout,topology,conn,density in itertools.product(range(6,21),('grid','staggered_layers','radial','concentric'),('dag','cyclic'),('connected','disconnected'),('sparse','moderate')):
        count=requested[n,layout,topology,conn,density]
        if not count:missing.append({'nodes':n,'layout':layout,'topology':topology,'connectivity':conn,'density_bin':density,
                                    'groups':0,'status':'not covered; see explicit compatibility/scheduling constraints, not a balanced Cartesian product'})
    table(out/'unmet_coverage_cells.csv',missing)
    acceptance=[]
    for n in sorted(sizes):
        total=sum(v for k,v in attempts.items() if k[0]==n);accepted=sizes[n]
        reasons=Counter()
        for k,v in attempts.items():
            if k[0]==n and k[-1]!='accepted':reasons[k[-1]]+=v
        acceptance.append({'nodes':n,'attempted':total,'accepted':accepted,'rejected':total-accepted,'acceptance_rate':accepted/total,
                           'failure_reasons':json.dumps(reasons,sort_keys=True)})
    table(out/'acceptance_by_size.csv',acceptance)
    result={'groups':sum(sizes.values()),'diagram_renderings':4*sum(sizes.values()),'png_files':4*sum(sizes.values()),'svg_files':4*sum(sizes.values()),
            'single_qa_instances':8*sum(sizes.values()),'original_variant_question_comparisons':6*sum(sizes.values()),
            'independence_unit':'One independently seeded base graph group; two questions and four variants are dependent observations. Base graphs are unique up to isomorphism.',
            'nodes':dict(sizes),'splits':dict(simple['split']),'layout':dict(simple['layout']),'style':dict(simple['style']),
            'density':dict(simple['density_bin']),'difficulty':dict(simple['difficulty_bin']),
            'topology':dict(simple['topology']),'connectivity':dict(simple['connectivity']),'feature_counts':dict(flags),
            'attempted':sum(attempts.values()),'rejected':sum(attempts.values())-sum(sizes.values()),
            'unmet_size_layout_topology_connectivity_density_cells':len(missing),'human_reviews':0,
            'shortcut_diagnostics':'Descriptive answer/style/layout/task/operation contingency and pixel statistics only; no fitted model, training or model inference. Chance correlations and within-cell selection bias remain.'}
    write(out/'coverage_summary.json',result)
    return result
