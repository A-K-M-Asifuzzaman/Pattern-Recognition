"""Independent raw-JSON Floyd–Warshall and certificate verification.

No imports from the generator, renderer, primary solver, Graph schema or NetworkX.
"""
import math


def distances(graph):
    nodes=graph['nodes'];assert 6<=len(nodes)<=20 and len(nodes)==len(set(nodes))
    index={n:i for i,n in enumerate(nodes)};n=len(nodes)
    d=[[0 if i==j else math.inf for j in range(n)] for i in range(n)]
    edges=set(map(tuple,graph['edges']));assert len(edges)==len(graph['edges'])
    for u,v in edges:
        assert u in index and v in index and u!=v
        d[index[u]][index[v]]=1
    for k in range(n):
        row=d[k]
        for i in range(n):
            prefix=d[i][k]
            if math.isinf(prefix):continue
            target=d[i]
            for j in range(n):
                value=prefix+row[j]
                if value<target[j]:target[j]=value
    return index,d


def answer(graph,q,computed):
    index,d=computed;value=d[index[q['source']]][index[q['target']]]
    if q['task']=='direct_edge':return [q['source'],q['target']] in graph['edges']
    if q['task']=='reachability':return not math.isinf(value)
    assert q['task']=='shortest_path'
    return 'unreachable' if math.isinf(value) else value


def evidence(graph,q,claim,cert,computed):
    try:
        actual=answer(graph,q,computed)
        if type(actual) is not type(claim) or actual!=claim:return False
        u,v=q['source'],q['target'];edges=set(map(tuple,graph['edges']));index,d=computed
        if q['task']=='direct_edge':
            return cert=={'kind':'edge_claim','source':u,'target':v,'present':claim} and type(cert['present']) is bool
        if claim is False or claim=='unreachable':
            reached=cert['nodes'];s=set(reached)
            return (cert['kind']=='reachable_set' and len(s)==len(reached) and u in s and v not in s
                    and s<=set(graph['nodes']) and all(not math.isinf(d[index[u]][index[n]]) for n in s)
                    and all(a not in s or b in s for a,b in edges))
        path=cert['path']
        if not path or path[0]!=u or path[-1]!=v or len(path)!=len(set(path)):return False
        if any(e not in edges for e in zip(path,path[1:])):return False
        if q['task']=='reachability':return cert['kind']=='path'
        p=cert['distances']
        return (cert['kind']=='shortest_path' and set(p)==set(graph['nodes'])
                and all(x is None or type(x) is int and x>=0 for x in p.values())
                and type(p[u]) is int and p[u]==0 and p[v]==claim and len(path)-1==claim
                and all(p[n] is not None for n in path)
                and all(p[a] is None or p[b] is not None and p[b]<=p[a]+1 for a,b in edges))
    except (KeyError,TypeError,ValueError):return False


def verify_group(group):
    variants=group['variants'];assert len(variants)==4 and len(group['questions'])==2
    original=variants[0]['graph'];original_edges=set(map(tuple,original['edges']))
    assert original==variants[1]['graph'];baseline={};mixed=False
    for i,v in enumerate(variants):
        graph=v['graph'];assert graph['nodes']==original['nodes'];computed=distances(graph);flags=[]
        for q in group['questions']:
            claim=answer(graph,q,computed);saved=v['answers'][q['id']]
            assert type(claim) is type(saved) and claim==saved,'wrong_answer'
            if i==0:baseline[q['id']]=claim
            relevant=type(claim) is not type(baseline[q['id']]) or claim!=baseline[q['id']]
            assert type(v['relevance'][q['id']]) is bool and v['relevance'][q['id']]==relevant,'wrong_relevance'
            assert evidence(graph,q,claim,v['certificates'][q['id']],computed),'invalid_certificate'
            flags.append(relevant)
        if i<2:
            assert v['edit'] is None;continue
        new=set(map(tuple,graph['edges']));delta=v['edit'];operand=tuple(delta['operand'])
        assert type(delta['operation_count']) is int and delta['operation_count']==1
        assert type(delta['directed_set_difference_count']) is int and delta['directed_set_difference_count']==len(new^original_edges)
        assert set(map(tuple,delta['added']))==new-original_edges and set(map(tuple,delta['deleted']))==original_edges-new
        if delta['operation']=='addition':assert new-original_edges=={operand} and not original_edges-new
        elif delta['operation']=='deletion':assert original_edges-new=={operand} and not new-original_edges
        else:assert delta['operation']=='reversal' and original_edges-new=={operand} and new-original_edges=={operand[::-1]}
        assert v['semantic_changed_edges']=={k:delta[k] for k in ('added','deleted')}
        old_scene=variants[0]['scene'];scene=v['scene']
        assert all(old_scene[k]==scene[k] for k in ('canvas','nodes','style'))
        old_geometry={tuple(e['edge']):e for e in old_scene['edges']};new_geometry={tuple(e['edge']):e for e in scene['edges']}
        assert all(old_geometry[e]==new_geometry[e] for e in original_edges&new)
        explanation=v['answer_change_evidence']
        for q in group['questions']:
            entry=explanation[q['id']]
            assert type(entry['before']) is type(baseline[q['id']]) and entry['before']==baseline[q['id']]
            assert type(entry['after']) is type(v['answers'][q['id']]) and entry['after']==v['answers'][q['id']]
            assert entry['relevant']==v['relevance'][q['id']]
            assert entry['basis']=='two independently certified answers; signed graph delta is separate'
        mixed |= sum(flags)==1
    assert mixed,'no_mixed_relevance'
    return {'answers':8,'certificates':8,'edits':2,'groups':1}
