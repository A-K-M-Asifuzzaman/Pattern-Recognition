"""Construct spaced graph cores and jointly select verified edits and questions."""
import hashlib
import hmac
import json
import math
import random

import networkx as nx

from .drawing import LAYOUTS, template, scene, validate_scene
from .logic import TASKS, OPERATIONS, answer, annotate, changed, coverage, network


def seed(*values):
    return int(hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()[:24],16)


def opaque(key,*values):
    return hmac.new(bytes.fromhex(key),json.dumps(values,separators=(',',':')).encode(),hashlib.sha256).hexdigest()[:24]


def make_plan(config):
    sizes=[]
    for band in config['size_bands']:
        low,high,total=band['min'],band['max'],band['groups']
        for i,n in enumerate(range(low,high+1)):
            sizes += [n]*(total//(high-low+1)+(i<total%(high-low+1)))
    assert len(sizes)==config['groups']
    random.Random(seed(config['seed'],'size-plan')).shuffle(sizes)
    appearances={}
    for name in ('layout','style','task','operation','topology','connectivity','density'):
        limit=4 if name in ('layout','style','connectivity') else 3 if name in ('task','operation') else 2
        sequence=[i%limit for i in range(len(sizes))]
        random.Random(seed(config['seed'],name)).shuffle(sequence);appearances[name]=sequence
    per_size={n:[i for i,k in enumerate(sizes) if n==k] for n in set(sizes)}
    splits={};cumulative=0
    for n,slots in sorted(per_size.items()):
        end=cumulative+len(slots)
        train=round(end*.7)-round(cumulative*.7);val=round(end*.15)-round(cumulative*.15)
        sequence=['train']*train+['validation']*val+['test']*(len(slots)-train-val)
        random.Random(seed(config['seed'],'split',n)).shuffle(sequence)
        splits.update(zip(slots,sequence));cumulative=end
    plan=[]
    for slot,n in enumerate(sizes):
        layout=LAYOUTS[appearances['layout'][slot]]
        disconnected=appearances['connectivity'][slot]==0
        cyclic=bool(appearances['topology'][slot])
        density='moderate' if appearances['density'][slot] else 'sparse'
        # Compatibility is explicit: radial/concentric pools prioritize route separation.
        if layout in ('radial','concentric') or n<=7 and disconnected:density='sparse'
        if n==6 and cyclic:
            disconnected=False;density='moderate'
            if layout=='concentric':layout=('grid','staggered_layers','radial')[seed(config['seed'],'six-cyclic-compatible-layout',slot)%3]
        if slot>=config.get('small_cell_revision_start_slot',len(sizes)) and n==6 and not cyclic and disconnected:
            disconnected=False;density='moderate'
            if layout=='concentric':layout=('grid','staggered_layers','radial')[seed(config['seed'],'six-dag-compatible-layout',slot)%3]
        plan.append({'slot':slot,'nodes':n,'layout':layout,'style':appearances['style'][slot],
                     'relevant_task':TASKS[appearances['task'][slot]],
                     'irrelevant_task':TASKS[(appearances['task'][slot]+1)%3],
                     'operation':OPERATIONS[appearances['operation'][slot]],
                     'second_operation':OPERATIONS[(appearances['operation'][slot]+1)%3],
                     'topology':'cyclic' if cyclic else 'dag',
                     'connectivity':'disconnected' if disconnected else 'connected',
                     'density':density,'split':splits[slot]})
    return plan


def construct(intent,trial,config,key):
    slot=intent['slot'];rng=random.Random(seed(config['seed'],'structure',slot,trial))
    appearance=random.Random(seed(config['seed'],'appearance',slot,trial))
    n=intent['nodes'];size,raw,pool=template(n,intent['layout'],appearance.randrange(8)+(16 if trial>=5000 else 8 if trial>=1000 else 0))
    undirected=nx.Graph();undirected.add_nodes_from(range(n));undirected.add_edges_from(pool)
    isolated=None
    if intent['connectivity']=='disconnected':
        choices=[i for i in range(n) if nx.is_connected(undirected.subgraph(set(range(n))-{i}))]
        assert choices,'disconnected_core_unavailable';isolated=rng.choice(choices)
        if trial>=5000 and n==6 and intent['layout']=='concentric':isolated=n-1
    main=set(range(n))-{isolated};core=main
    core_pool=[e for e in pool if set(e)<=core]
    forced=set()
    cyclic_order=[]
    if intent['topology']=='cyclic':
        cycles=nx.cycle_basis(undirected.subgraph(core));assert cycles,'cyclic_core_unavailable'
        cyclic_order=rng.choice(cycles)
        forced={tuple(sorted(e)) for e in zip(cyclic_order,cyclic_order[1:]+cyclic_order[:1])}
    weighted=nx.Graph();weighted.add_nodes_from(core)
    for a,b in core_pool:weighted.add_edge(a,b,weight=rng.random())
    selected=forced|{tuple(sorted(e)) for e in nx.minimum_spanning_edges(weighted,data=False)}
    minimum=len(selected)
    available=len(core_pool)
    capacity=available-int('addition' in (intent['operation'],intent['second_operation']))
    if intent['density']=='moderate':
        low=max(minimum,math.ceil(1.25*n));high=min(capacity,math.floor(1.75*n))
    else:
        low=max(minimum,math.ceil(.6*n));high=min(capacity,math.ceil(1.25*n)-1)
    assert high>=low,'density_capacity_unavailable'
    target=rng.randint(low,high)
    extras=[e for e in core_pool if e not in selected];rng.shuffle(extras)
    selected.update(extras[:target-len(selected)])
    rank_order=rng.sample(sorted(core),len(core));rank={v:i for i,v in enumerate(rank_order)}
    directed={(a,b) if rank[a]<rank[b] else (b,a) for a,b in selected}
    for a,b in zip(cyclic_order,cyclic_order[1:]+cyclic_order[:1]):
        directed.discard((b,a));directed.add((a,b))
    labels=rng.sample([a+b for a in 'ABCDEFGHJKLMNPQRSTUVWXYZ' for b in 'ABCDEFGHJKLMNPQRSTUVWXYZ'],n)
    graph={'nodes':sorted(labels),'edges':[list(e) for e in sorted((labels[a],labels[b]) for a,b in directed)]}
    old_net=network(graph);old_dist=dict(nx.all_pairs_shortest_path_length(old_net))
    same_region={labels[i] for i in main}
    if intent['operation']=='addition':
        first_operands=[(labels[a],labels[b]) for a,b in core_pool if not ({(a,b),(b,a)}&directed)]
        first_operands += [(b,a) for a,b in first_operands]
    else:first_operands=list(map(tuple,graph['edges']))
    rng.shuffle(first_operands)
    for operand in first_operands:
        first,delta=changed(graph,intent['operation'],operand)
        new_net=network(first);new_dist=dict(nx.all_pairs_shortest_path_length(new_net));rel=[];irrelevant=[]
        for u in sorted(same_region):
            for v in sorted(same_region):
                if u==v:continue
                for task,bucket,want in ((intent['relevant_task'],rel,True),(intent['irrelevant_task'],irrelevant,False)):
                    q={'task':task,'source':u,'target':v};a=answer(old_net,q,old_dist);b=answer(new_net,q,new_dist)
                    if (type(a) is not type(b) or a!=b)==want:bucket.append(q)
        if rel and irrelevant:break
    else:raise AssertionError('no_verified_mixed_edit_questions')
    q1=rng.choice(rel)
    # Positive/negative intent alternates independently of style/layout; fallback is recorded.
    want_positive=bool(seed(config['seed'],'question-sign',slot)%2)
    signed=[q for q in irrelevant if (answer(old_net,q,old_dist) is True or type(answer(old_net,q,old_dist)) is int)==want_positive]
    choices=signed or irrelevant
    # Prefer real alternative-route evidence for positive reachability questions.
    alternatives=[]
    if intent['irrelevant_task']=='reachability' and want_positive:
        for q in choices:
            if not old_net.has_edge(q['source'],q['target']):continue
            without=old_net.copy();without.remove_edge(q['source'],q['target'])
            if nx.has_path(without,q['source'],q['target']):alternatives.append(q)
    q2=rng.choice(alternatives or choices)
    qdata=[q1,q2];rng.shuffle(qdata)
    for i,q in enumerate(qdata):q['id']=opaque(key,'rc1',slot,trial,'question',i)
    second_op=intent['second_operation'];operands=[]
    if second_op=='addition':
        for a,b in pool:
            if a not in main or b not in main:continue
            u,v=labels[a],labels[b]
            if (u,v) not in map(tuple,graph['edges']) and (v,u) not in map(tuple,graph['edges']):
                operands.extend([(u,v),(v,u)])
    else:operands=[tuple(e) for e in graph['edges'] if set(e)<={labels[i] for i in core}]
    rng.shuffle(operands);ranked=[]
    stored=annotate(graph,q2)[1].get('path',[]);support=set(zip(stored,stored[1:]))
    for candidate in operands:
        other,edit=changed(graph,second_op,candidate);g=network(other)
        same=answer(g,q2)==answer(old_net,q2,old_dist)
        on_path=candidate in support and second_op in ('deletion','reversal')
        ranked.append((int(same)*2+int(same and on_path),other,edit))
    assert ranked,'second_edit_unavailable'
    _,second,delta2=max(ranked,key=lambda row:row[0])
    points={labels[i]:list(raw[i]) for i in range(n)}
    if appearance.randrange(2):points={label:[size-x,y] for label,(x,y) in points.items()}
    redraw_points={label:[y,size-x] for label,(x,y) in points.items()}
    style=intent['style'];redraw_style=(style+1+appearance.randrange(3))%4
    graphs=[graph,graph,first,second];variants=[]
    for i,g in enumerate(graphs):
        drawing=scene(g,redraw_points if i==1 else points,size,redraw_style if i==1 else style)
        geometry=validate_scene(g,drawing);answers={};certs={}
        for q in qdata:answers[q['id']],certs[q['id']]=annotate(g,q)
        edit=None if i<2 else delta if i==2 else delta2
        relevance={q['id']:answers[q['id']]!=variants[0]['answers'][q['id']] if i else False for q in qdata}
        variant={'id':opaque(key,'rc1',slot,trial,'variant',i),'role':('original','redraw','edited','edited')[i],
                 'graph':g,'scene':drawing,'answers':answers,'certificates':certs,'relevance':relevance,'edit':edit,'geometry_checks':geometry}
        if edit:
            variant['semantic_changed_edges']={k:edit[k] for k in ('added','deleted')}
            variant['answer_change_evidence']={q['id']:{'before':variants[0]['answers'][q['id']], 'after':answers[q['id']],
                     'relevant':relevance[q['id']],'basis':'two independently certified answers; signed graph delta is separate',
                     'original_certificate':variants[0]['certificates'][q['id']], 'edited_certificate':certs[q['id']],
                     'same_original_weak_component_as_edit':all(x in same_region for x in (q['source'],q['target'],*edit['operand'])),
                     'deleted_edge_on_stored_original_path':bool(set(map(tuple,edit['deleted'])) & set(zip(variants[0]['certificates'][q['id']].get('path',[]),variants[0]['certificates'][q['id']].get('path',[])[1:])))} for q in qdata}
        variants.append(variant)
    features=coverage(graph,qdata)
    assert features['topology']==intent['topology'] and features['connectivity']==intent['connectivity'] and features['density_bin']==intent['density'],'coverage_mismatch'
    return {'id':opaque(key,'rc1',slot,trial,'group'),'slot':slot,'trial':trial,'seed':seed(config['seed'],'structure',slot,trial),
            'split':intent['split'],'generator_version':'0.3.0-rc1','intent':intent,'questions':qdata,'variants':variants,
            'coverage':{**features,'layout':intent['layout'],'style':style,'question_sign_fallback':not bool(signed)}}
