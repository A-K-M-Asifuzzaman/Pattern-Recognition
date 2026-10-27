"""Independent isomorphism filtering and exact adjacency search, without NetworkX."""
import hashlib
import json
from collections import defaultdict, Counter


def invariant(graph):
    nodes=graph['nodes'];edges=set(map(tuple,graph['edges']))
    incoming={u:[] for u in nodes};outgoing={u:[] for u in nodes}
    for u,v in edges:outgoing[u].append(v);incoming[v].append(u)
    colors={u:f'{len(incoming[u])}/{len(outgoing[u])}' for u in nodes}
    for _ in range(3):
        colors={u:hashlib.sha256(json.dumps([colors[u],sorted(colors[v] for v in incoming[u]),sorted(colors[v] for v in outgoing[u])],separators=(',',':')).encode()).hexdigest() for u in nodes}
    return len(nodes),len(edges),tuple(sorted(colors.values()))


def exact(a,b):
    ea,eb=set(map(tuple,a['edges'])),set(map(tuple,b['edges']))
    def degree(u,es):return sum(v==u for x,v in es),sum(x==u for x,v in es)
    da={u:degree(u,ea) for u in a['nodes']};db={u:degree(u,eb) for u in b['nodes']}
    candidates={u:[v for v in b['nodes'] if da[u]==db[v]] for u in a['nodes']}
    order=sorted(a['nodes'],key=lambda u:(len(candidates[u]),-sum(da[u]),u));mapping={};used=set()
    def visit(i):
        if i==len(order):return True
        u=order[i]
        for v in candidates[u]:
            if v in used:continue
            if any(((u,x) in ea)!=((v,y) in eb) or ((x,u) in ea)!=((y,v) in eb) for x,y in mapping.items()):continue
            mapping[u]=v;used.add(v)
            if visit(i+1):return True
            del mapping[u];used.remove(v)
        return False
    return visit(0)


class Index:
    def __init__(self):
        self.buckets=defaultdict(list);self.exact_checks=0;self.cross_split_checks=0
        self.historical_checks=0;self.allowed_within_group=Counter();self.counts=Counter()
        self.same_split_descendant_overlap=0

    def add_history(self,groups):
        for g in groups:
            seen=set()
            for v in g['variants']:
                encoded=json.dumps(v['graph'],sort_keys=True)
                if encoded in seen:continue
                seen.add(encoded);self.buckets[invariant(v['graph'])].append(('history:'+g['id'],g['split'],v['role'],v['graph']))

    def verify_add(self,g):
        graphs=[];seen=set()
        for v in g['variants']:
            graph=v['graph'];key=invariant(graph)
            for owner,split,role,prior in self.buckets[key]:
                self.exact_checks+=1;self.cross_split_checks+=split!=g['split'];self.historical_checks+=owner.startswith('history:')
                if exact(graph,prior):
                    assert split==g['split'] and not owner.startswith('history:') and not (v['role']=='original' and role=='original'),f'Accidental forbidden isomorphic overlap: {g["id"]}, {owner}'
                    self.same_split_descendant_overlap+=1
            for prior_v in graphs:
                if key==invariant(prior_v['graph']) and exact(graph,prior_v['graph']):
                    self.allowed_within_group[prior_v['role']+' / '+v['role']]+=1
            graphs.append(v)
        for v in graphs:
            encoded=json.dumps(v['graph'],sort_keys=True)
            if encoded in seen:continue
            seen.add(encoded);self.buckets[invariant(v['graph'])].append((g['id'],g['split'],v['role'],v['graph']))
        self.counts[g['split']]+=4

    def report(self):
        ns=list(self.counts.values())
        return {'status':'passed','variant_counts_by_split':dict(self.counts),
                'all_cross_split_variant_pairs':sum(ns[i]*ns[j] for i in range(len(ns)) for j in range(i)),
                'exact_candidate_checks':self.exact_checks,'cross_split_exact_checks':self.cross_split_checks,
                'historical_exact_checks':self.historical_checks,'forbidden_cross_split_or_base_isomorphisms':0,
                'same_split_descendant_overlap_relationships':self.same_split_descendant_overlap,
                'allowed_within_group_unlabeled_isomorphism_relationships':dict(self.allowed_within_group),
                'repeated_graph_question_edit_structures':0,
                'structure_duplicate_reasoning':'No cross-group base-graph isomorphism exists, which precludes a repeated graph/question/edit structure even before coloring question and edit roles.',
                'method':'Independent incoming/outgoing color-refinement invariant; every matching candidate receives exact degree-constrained adjacency backtracking. Hash alone never certifies uniqueness.'}
