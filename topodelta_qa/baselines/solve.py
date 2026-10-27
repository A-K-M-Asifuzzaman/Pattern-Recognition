"""Deterministic solving of extracted graphs; no gold endpoints or graph helpers."""
from collections import deque
from .contract import graph, question


def solve(value, text):
    value = graph(value)
    task, source, target = question(text)
    nodes, edges = value["nodes"], value["edges"]
    if source not in nodes or target not in nodes:
        raise ValueError("Extracted graph lacks a query endpoint")
    adjacency = {n: [] for n in nodes}
    for u, v in edges:
        adjacency[u].append(v)
    d, parents, queue = {source: 0}, {}, deque([source])
    while queue:
        u = queue.popleft()
        for v in adjacency[u]:
            if v not in d:
                d[v], parents[v] = d[u] + 1, u
                queue.append(v)
    if task == "direct_edge":
        ans = [source, target] in edges
        return ans, {"kind": "edge_claim", "source": source, "target": target, "present": ans}
    if target not in d:
        return (False if task == "reachability" else "unreachable"), {"kind": "reachable_set", "nodes": sorted(d)}
    path = [target]
    while path[-1] != source:
        path.append(parents[path[-1]])
    path.reverse()
    if task == "reachability":
        return True, {"kind": "path", "path": path}
    return d[target], {"kind": "shortest_path", "path": path,
                       "distances": [{"node": n, "distance": d.get(n)} for n in nodes]}


def derive(graphs, text):
    solved = [solve(g, text) for g in graphs]
    if len(solved) == 1:
        return {"answer": solved[0][0], "certificate": solved[0][1]}
    if len(solved) != 2:
        raise ValueError("Expected one or two extracted graphs")
    a, b = (set(map(tuple, g["edges"])) for g in graphs)
    answers = [x[0] for x in solved]
    return {"answers": answers, "certificates": [x[1] for x in solved],
            "delta": {"added": [list(e) for e in sorted(b-a)], "deleted": [list(e) for e in sorted(a-b)]},
            "answer_changed": type(answers[0]) is not type(answers[1]) or answers[0] != answers[1]}
