"""NetworkX primary answers; reference BFS and exhaustive relaxation use no NetworkX."""
from collections import deque
from typing import Any

import networkx as nx

from .schema import Answer, Certificate, Edge, EditDelta, Graph, Question


def network(graph: Graph) -> nx.DiGraph:
    result = nx.DiGraph()
    result.add_nodes_from(graph.nodes)
    result.add_edges_from(graph.edges)
    return result


def distances(graph: Graph, source: str) -> dict[str, int]:
    if source not in graph.nodes:
        raise ValueError("Unknown source")
    adjacency = {n: [] for n in graph.nodes}
    for u, v in graph.edges:
        adjacency[u].append(v)
    result, queue = {source: 0}, deque([source])
    while queue:
        u = queue.popleft()
        for v in adjacency[u]:
            if v not in result:
                result[v] = result[u] + 1
                queue.append(v)
    return result


def reference_answer(graph: Graph, q: Question) -> Answer:
    if q.source not in graph.nodes or q.target not in graph.nodes:
        raise ValueError("Unknown question endpoint")
    if q.task == "direct_edge":
        return (q.source, q.target) in graph.edges
    # Bellman–Ford-style repeated relaxation independently cross-checks BFS lengths.
    distance = {n: len(graph.nodes) + 1 for n in graph.nodes}
    distance[q.source] = 0
    for _ in range(len(graph.nodes) - 1):
        for u, v in graph.edges:
            distance[v] = min(distance[v], distance[u] + 1)
    reachable = q.target in distances(graph, q.source)
    if reachable != (distance[q.target] <= len(graph.nodes) - 1):
        raise ValueError("Independent reference algorithms disagree")
    return reachable if q.task == "reachability" else distance[q.target] if reachable else "unreachable"


def solve(graph: Graph, q: Question) -> Answer:
    g = network(graph)
    if q.task == "direct_edge":
        answer = g.has_edge(q.source, q.target)
    elif q.task == "reachability":
        answer = nx.has_path(g, q.source, q.target)
    else:
        try:
            answer = nx.shortest_path_length(g, q.source, q.target)
        except nx.NetworkXNoPath:
            answer = "unreachable"
    if not answer_equal(answer, reference_answer(graph, q)):
        raise ValueError("Primary and independent solvers disagree")
    return answer


def answer_equal(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def edit(graph: Graph, operation: str, edge: Edge) -> tuple[Graph, EditDelta]:
    edges = set(graph.edges)
    u, v = edge
    if u not in graph.nodes or v not in graph.nodes or u == v:
        raise ValueError("Invalid edit endpoint")
    if operation == "addition" and edge not in edges:
        edges.add(edge)
    elif operation == "deletion" and edge in edges:
        edges.remove(edge)
    elif operation == "reversal" and edge in edges and (v, u) not in edges:
        edges.remove(edge)
        edges.add((v, u))
    else:
        raise ValueError("Edit precondition failed")
    added, deleted = sorted(edges - set(graph.edges)), sorted(set(graph.edges) - edges)
    return Graph(graph.nodes, tuple(sorted(edges))), {
        "operation": operation, "operand": list(edge), "operation_count": 1,
        "added": [list(e) for e in added], "deleted": [list(e) for e in deleted],
        "directed_set_difference_count": len(added) + len(deleted),
    }


def certificate(graph: Graph, q: Question) -> Certificate:
    answer = solve(graph, q)
    if q.task == "direct_edge":
        return {"kind": "edge_claim", "source": q.source, "target": q.target, "present": answer}
    reached = distances(graph, q.source)
    if answer is False or answer == "unreachable":
        return {"kind": "reachable_set", "nodes": sorted(reached)}
    path = nx.shortest_path(network(graph), q.source, q.target)
    if q.task == "reachability":
        return {"kind": "path", "path": path}
    # A feasible distance potential proves the path's lower bound on every edge.
    return {"kind": "shortest_path", "path": path,
            "distances": {n: reached.get(n) for n in graph.nodes}}


def valid_certificate(graph: Graph, q: Question, answer: Any, cert: Any) -> bool:
    """Accept any valid path/potential or complete closed reachable set, never a gold-path match."""
    try:
        if not answer_equal(answer, reference_answer(graph, q)) or not isinstance(cert, dict):
            return False
        if q.task == "direct_edge":
            return (cert.get("kind") == "edge_claim" and cert.get("source") == q.source
                    and cert.get("target") == q.target and type(cert.get("present")) is bool
                    and cert["present"] == answer)
        if answer is False or answer == "unreachable":
            nodes = cert.get("nodes")
            if cert.get("kind") != "reachable_set" or not isinstance(nodes, list):
                return False
            reached = set(nodes)
            # Equality checked against independent BFS ensures no unconnected extras.
            return len(reached) == len(nodes) and reached == set(distances(graph, q.source)) and q.target not in reached
        path = cert.get("path")
        if not isinstance(path, list) or not path or path[0] != q.source or path[-1] != q.target:
            return False
        if len(set(path)) != len(path) or any((u, v) not in graph.edges for u, v in zip(path, path[1:])):
            return False
        if q.task == "reachability":
            return cert.get("kind") == "path"
        d = cert.get("distances")
        if cert.get("kind") != "shortest_path" or not isinstance(d, dict) or set(d) != set(graph.nodes):
            return False
        if d[q.source] != 0 or type(d[q.source]) is not int or len(path) - 1 != answer or d[q.target] != answer:
            return False
        if any(x is not None and (type(x) is not int or x < 0) for x in d.values()):
            return False
        if any(d[n] is None for n in path):
            return False
        return all(d[u] is None or (d[v] is not None and d[v] <= d[u] + 1) for u, v in graph.edges)
    except (TypeError, KeyError, ValueError):
        return False


def isomorphic(a: Graph, b: Graph) -> bool:
    if len(a.nodes) != len(b.nodes) or len(a.edges) != len(b.edges):
        return False
    # Degree signatures only prefilter; exact directed VF2 is the final decision.
    ga, gb = network(a), network(b)
    if sorted(ga.degree(n) for n in ga) != sorted(gb.degree(n) for n in gb):
        return False
    return nx.is_isomorphic(ga, gb)


def cross_split_duplicates(groups: list[dict]) -> list[dict]:
    seen: list[tuple[str, str, Graph]] = []
    result = []
    for group in groups:
        for variant in group["variants"]:
            graph = Graph.parse(variant["graph"])
            for split, group_id, prior in seen:
                if split != group["split"] and isomorphic(graph, prior):
                    result.append({"group": group["id"], "other_group": group_id,
                                   "variant": variant["id"]})
            seen.append((group["split"], group["id"], graph))
    return result
