"""Provider-safe schemas and strict, public-text-only question interpretation."""
import hashlib
import json
import re


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def question(text):
    templates = (
        ("reachability", r"Is there a directed path from (\S+) to (\S+)\?"),
        ("direct_edge", r"Is there a directed edge from (\S+) to (\S+)\?"),
        ("shortest_path", r"What is the minimum number of directed edges in a path from (\S+) to (\S+)\? Return 'unreachable' if none exists\."),
    )
    for task, pattern in templates:
        match = re.fullmatch(pattern, text)
        if match and match[1] != match[2]:
            return task, match[1], match[2]
    raise ValueError("Question is outside the frozen public templates")


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def arr(items, low=0, high=None):
    value = {"type": "array", "items": items, "minItems": low}
    if high is not None:
        value["maxItems"] = high
    return value


STRING = {"type": "string", "minLength": 1}
BOOL = {"type": "boolean"}
INTEGER = {"type": "integer", "minimum": 0}
EDGE = arr(STRING, 2, 2)
GRAPH = obj({"nodes": arr(STRING, 1), "edges": arr(EDGE)})
DELTA = obj({"added": arr(EDGE), "deleted": arr(EDGE)})


def schema(baseline, protocol, text):
    count = 1 if protocol == "single" else 2 if protocol == "paired" else 0
    if not count or baseline not in ("direct", "parse"):
        raise ValueError("Unknown baseline/track")
    task, _, _ = question(text)
    if baseline == "parse":
        return obj({"graphs": arr(GRAPH, count, count)})
    answer = {"anyOf": [INTEGER, {"type": "string", "enum": ["unreachable"]}]} if task == "shortest_path" else BOOL
    negative = obj({"kind": {"type": "string", "enum": ["reachable_set"]}, "nodes": arr(STRING, 1)})
    if task == "direct_edge":
        cert = obj({"kind": {"type": "string", "enum": ["edge_claim"]}, "source": STRING, "target": STRING, "present": BOOL})
    else:
        positive = {"kind": {"type": "string", "enum": ["path" if task == "reachability" else "shortest_path"]}, "path": arr(STRING, 2)}
        if task == "shortest_path":
            positive["distances"] = arr(obj({"node": STRING, "distance": {"anyOf": [INTEGER, {"type": "null"}]}}), 1)
        cert = {"anyOf": [obj(positive), negative]}
    return obj({"answer": answer, "certificate": cert}) if count == 1 else obj({
        "answers": arr(answer, 2, 2), "certificates": arr(cert, 2, 2), "delta": DELTA, "answer_changed": BOOL})


def validate_schema(value, spec):
    """Validate exactly the small JSON Schema vocabulary emitted above."""
    if "anyOf" in spec:
        for choice in spec["anyOf"]:
            try:
                validate_schema(value, choice)
                return
            except ValueError:
                pass
        raise ValueError("No schema alternative matches")
    expected = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}[spec["type"]]
    if type(value) is not expected:
        raise ValueError("Incorrect JSON type")
    if "enum" in spec and value not in spec["enum"]:
        raise ValueError("Value outside enum")
    if expected is dict:
        if set(value) != set(spec["required"]):
            raise ValueError("Missing or unexpected object fields")
        for k, v in value.items():
            validate_schema(v, spec["properties"][k])
    elif expected is list:
        if len(value) < spec.get("minItems", 0) or len(value) > spec.get("maxItems", float("inf")):
            raise ValueError("Incorrect array length")
        for v in value:
            validate_schema(v, spec["items"])
    elif expected is str and len(value) < spec.get("minLength", 0):
        raise ValueError("Empty label")
    elif expected is int and value < spec.get("minimum", value):
        raise ValueError("Negative integer")


def graph(value):
    validate_schema(value, GRAPH)
    nodes, edges = value["nodes"], [tuple(e) for e in value["edges"]]
    if len(nodes) != len(set(nodes)) or len(edges) != len(set(edges)):
        raise ValueError("Duplicate graph node or edge")
    if any(u == v or u not in nodes or v not in nodes for u, v in edges):
        raise ValueError("Invalid graph edge")
    return {"nodes": sorted(nodes), "edges": sorted([list(e) for e in edges])}


def validate_output(value, baseline, protocol, text):
    validate_schema(value, schema(baseline, protocol, text))
    if baseline == "parse":
        for g in value["graphs"]:
            graph(g)
    else:
        certs = [value["certificate"]] if protocol == "single" else value["certificates"]
        for cert in certs:
            key = "path" if "path" in cert else "nodes" if "nodes" in cert else None
            if key and len(cert[key]) != len(set(cert[key])):
                raise ValueError("Duplicate evidence label")
            if "distances" in cert:
                labels = [r["node"] for r in cert["distances"]]
                if len(labels) != len(set(labels)):
                    raise ValueError("Duplicate distance label")
        if protocol == "paired":
            added, deleted = ([tuple(e) for e in value["delta"][k]] for k in ("added", "deleted"))
            if len(added) != len(set(added)) or len(deleted) != len(set(deleted)) or set(added) & set(deleted):
                raise ValueError("Duplicate or contradictory delta")
            if any(u == v for u, v in added + deleted):
                raise ValueError("Delta self-loop")
    return value


def certificate_to_legacy(cert):
    cert = dict(cert)
    if "distances" in cert:
        cert["distances"] = {r["node"]: r["distance"] for r in cert["distances"]}
    return cert
