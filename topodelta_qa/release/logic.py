"""Primary NetworkX annotations; raw records support the independent verifier."""
import networkx as nx

TASKS = ('reachability','shortest_path','direct_edge')
OPERATIONS = ('addition','deletion','reversal')


def network(graph):
    g=nx.DiGraph();g.add_nodes_from(graph['nodes']);g.add_edges_from(graph['edges']);return g


def question_text(q):
    u,v=q['source'],q['target']
    if q['task']=='reachability':return f'Is there a directed path from {u} to {v}?'
    if q['task']=='direct_edge':return f'Is there a directed edge from {u} to {v}?'
    return f"What is the minimum number of directed edges in a path from {u} to {v}? Return 'unreachable' if none exists."


def answer(g,q,dist=None):
    if q['task']=='direct_edge':return g.has_edge(q['source'],q['target'])
    d=nx.single_source_shortest_path_length(g,q['source']) if dist is None else dist[q['source']]
    if q['task']=='reachability':return q['target'] in d
    return d.get(q['target'],'unreachable')


def annotate(graph,q):
    g=network(graph);a=answer(g,q);u,v=q['source'],q['target']
    if q['task']=='direct_edge':return a,{'kind':'edge_claim','source':u,'target':v,'present':a}
    d=nx.single_source_shortest_path_length(g,u)
    if a is False or a=='unreachable':return a,{'kind':'reachable_set','nodes':sorted(d)}
    path=nx.shortest_path(g,u,v)
    if q['task']=='reachability':return a,{'kind':'path','path':path}
    return a,{'kind':'shortest_path','path':path,'distances':{n:d.get(n) for n in graph['nodes']}}


def changed(graph,operation,operand):
    old=set(map(tuple,graph['edges']));new=set(old);u,v=operand
    if operation=='addition':
        assert (u,v) not in old and (v,u) not in old;new.add((u,v))
    elif operation=='deletion':
        assert (u,v) in old;new.remove((u,v))
    else:
        assert operation=='reversal' and (u,v) in old and (v,u) not in old
        new.remove((u,v));new.add((v,u))
    delta={'operation':operation,'operand':[u,v],'operation_count':1,
           'directed_set_difference_count':len(old^new),
           'added':[list(e) for e in sorted(new-old)],'deleted':[list(e) for e in sorted(old-new)]}
    return {'nodes':graph['nodes'],'edges':[list(e) for e in sorted(new)]},delta


def coverage(graph,questions):
    g=network(graph);u=g.to_undirected();n=len(g);m=g.number_of_edges()
    all_d=dict(nx.all_pairs_shortest_path_length(g));finite=[d for a,ds in all_d.items() for b,d in ds.items() if a!=b]
    alternative=any(len(list(nx.all_simple_paths(g,a,b,cutoff=4)))>1 for a,b in g.edges)
    return {'nodes':n,'edges':m,'directed_density':m/(n*(n-1)),'edges_per_node':m/n,
            'density_bin':'sparse' if m/n<1.25 else 'moderate',
            'topology':'dag' if nx.is_directed_acyclic_graph(g) else 'cyclic',
            'connectivity':'connected' if nx.is_connected(u) else 'disconnected',
            'branches':sum(g.out_degree(v)>=2 for v in g),'merges':sum(g.in_degree(v)>=2 for v in g),
            'alternative_paths':alternative,'weak_bridges':len(list(nx.bridges(u))),
            'maximum_finite_shortest_path':max(finite,default=0),
            'difficulty_bin':'short' if max(finite,default=0)<=2 else 'medium' if max(finite)<=4 else 'long',
            'unreachable_ordered_pairs':n*(n-1)-len(finite),
            'unqueried_nodes':n-len({q[k] for q in questions for k in ('source','target')})}
