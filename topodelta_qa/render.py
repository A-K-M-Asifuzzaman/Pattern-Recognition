"""Shared SVG/PNG scene, strict geometric acceptance, no task-dependent styling."""
import base64
import html
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .schema import Graph, Scene

SIZE = 800
NODE_W, NODE_H = 64, 48
FONT_SIZE = 22
STYLES = (
    {"background": "#ffffff", "node_fill": "#ffffff", "ink": "#202020", "width": 2.5},
    {"background": "#fafafa", "node_fill": "#eeeeee", "ink": "#303030", "width": 3.0},
    {"background": "#ffffff", "node_fill": "#f5f5f5", "ink": "#101010", "width": 2.0},
)
RENDERER = {"version": "1", "canvas": [SIZE, SIZE], "node_size": [NODE_W, NODE_H],
            "font": "Pillow bundled Aileron Regular", "font_size": FONT_SIZE,
            "arrow_length": 15, "arrow_half_width": 6, "endpoint_gap": 5,
            "minimum_edge_clearance": 6, "supersampling": 2, "styles": STYLES}


class RenderError(ValueError):
    pass


def positions(order: list[str], angle: float) -> dict[str, list[float]]:
    return {n: [round(400 + 292 * math.cos(angle + i * 2 * math.pi / len(order)), 4),
                round(400 + 292 * math.sin(angle + i * 2 * math.pi / len(order)), 4)]
            for i, n in enumerate(order)}


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def intersects(a, b, c, d) -> bool:
    def on(p, q, r):
        return abs(cross(p, q, r)) < 1e-7 and all(min(p[i], q[i]) - 1e-7 <= r[i] <= max(p[i], q[i]) + 1e-7 for i in (0, 1))
    return (cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0
            or on(a, b, c) or on(a, b, d) or on(c, d, a) or on(c, d, b))


def point_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def segment_distance(a, b, c, d):
    return 0 if intersects(a, b, c, d) else min(point_distance(a, c, d), point_distance(b, c, d), point_distance(c, a, b), point_distance(d, a, b))


def box_polygon(box):
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def sides(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def inside(p, poly):
    signs = [cross(a, b, p) for a, b in sides(poly)]
    return all(s >= -1e-7 for s in signs) or all(s <= 1e-7 for s in signs)


def segment_polygon_distance(a, b, poly):
    if inside(a, poly) or inside(b, poly):
        return 0
    return min(segment_distance(a, b, c, d) for c, d in sides(poly))


def polygon_distance(a, b):
    if inside(a[0], b) or inside(b[0], a):
        return 0
    return min(segment_distance(p, q, r, s) for p, q in sides(a) for r, s in sides(b))


def scene(graph: Graph, points: dict[str, list[float]], style: int) -> Scene:
    if set(points) != set(graph.nodes) or type(style) is not int or style not in range(len(STYLES)):
        raise RenderError("invalid_scene_configuration")
    font = ImageFont.load_default(size=FONT_SIZE)
    nodes = []
    for label in graph.nodes:
        x, y = points[label]
        bbox = font.getbbox(label, anchor="ms")
        nodes.append({"label": label, "center": [x, y],
                      "box": [x - NODE_W / 2, y - NODE_H / 2, x + NODE_W / 2, y + NODE_H / 2],
                      "label_box": [x + bbox[0], y + 7 + bbox[1], x + bbox[2], y + 7 + bbox[3]]})
    edges = []
    for u, v in graph.edges:
        ux, uy = points[u]
        vx, vy = points[v]
        dx, dy = vx - ux, vy - uy
        length = math.hypot(dx, dy)
        if length <= NODE_W:
            raise RenderError("short_edge")
        ex, ey = dx / length, dy / length
        clip = min(NODE_W / (2 * abs(ex)) if ex else math.inf,
                   NODE_H / (2 * abs(ey)) if ey else math.inf) + 5
        start, end = [ux + clip * ex, uy + clip * ey], [vx - clip * ex, vy - clip * ey]
        base = [end[0] - 15 * ex, end[1] - 15 * ey]
        arrow = [end, [base[0] - 6 * ey, base[1] + 6 * ex], [base[0] + 6 * ey, base[1] - 6 * ex]]
        edges.append({"edge": [u, v], "line": [start, end], "arrowhead": arrow})
    return {"canvas": [SIZE, SIZE], "style": style, "nodes": nodes, "edges": edges}


def validate_scene(graph: Graph, drawing: Scene) -> None:
    """Reject crossings, near-overlaps, occluded heads, clipped or overlapping labels."""
    try:
        points = {n["label"]: n["center"] for n in drawing["nodes"]}
        if scene(graph, points, drawing["style"]) != drawing:
            raise RenderError("scene_graph_or_geometry_mismatch")
        nodes, edges = drawing["nodes"], drawing["edges"]
        for i, n in enumerate(nodes):
            x0, y0, x1, y1 = n["box"]
            a, b, c, d = n["label_box"]
            if not (8 <= x0 < x1 <= SIZE - 8 and 8 <= y0 < y1 <= SIZE - 8 and x0 + 6 <= a < c <= x1 - 6 and y0 + 6 <= b < d <= y1 - 6):
                raise RenderError("unreadable_or_clipped_label")
            for m in nodes[i + 1:]:
                if polygon_distance(box_polygon(n["box"]), box_polygon(m["box"])) < 12:
                    raise RenderError("node_overlap")
        for i, edge in enumerate(edges):
            a, b = edge["line"]
            if math.dist(a, b) < 40:
                raise RenderError("short_edge")
            for p in [a, b] + edge["arrowhead"]:
                if not all(4 <= x <= SIZE - 4 for x in p):
                    raise RenderError("clipped_edge")
            for n in nodes:
                poly = box_polygon(n["box"])
                if segment_polygon_distance(a, b, poly) < 3 or polygon_distance(edge["arrowhead"], poly) < 3:
                    raise RenderError("edge_node_or_arrow_node_intersection")
            for other in edges[i + 1:]:
                c, d = other["line"]
                if segment_distance(a, b, c, d) < 6:
                    raise RenderError("crossing_or_ambiguous_edge_overlap")
                if (segment_polygon_distance(a, b, other["arrowhead"]) < 4
                        or segment_polygon_distance(c, d, edge["arrowhead"]) < 4
                        or polygon_distance(edge["arrowhead"], other["arrowhead"]) < 4):
                    raise RenderError("hidden_or_ambiguous_arrowhead")
    except (KeyError, TypeError, ZeroDivisionError) as exc:
        raise RenderError("invalid_geometry") from exc


def png(drawing: Scene) -> Image.Image:
    style = STYLES[drawing["style"]]
    im = Image.new("RGB", (SIZE * 2, SIZE * 2), style["background"])
    draw = ImageDraw.Draw(im)
    scale = lambda p: tuple(x * 2 for x in p)
    font = ImageFont.load_default(size=FONT_SIZE * 2)
    for e in drawing["edges"]:
        draw.line([scale(p) for p in e["line"]], fill=style["ink"], width=round(style["width"] * 2))
        draw.polygon([scale(p) for p in e["arrowhead"]], fill=style["ink"])
    for n in drawing["nodes"]:
        draw.rectangle(scale(n["box"]), fill=style["node_fill"], outline=style["ink"], width=round(style["width"] * 2))
        x, y = n["center"]
        draw.text((x * 2, (y + 7) * 2), n["label"], font=font, anchor="ms", fill=style["ink"])
    return im.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def svg(drawing: Scene) -> str:
    style = STYLES[drawing["style"]]
    font_bytes = ImageFont.load_default(size=FONT_SIZE).path.getvalue()
    encoded = base64.b64encode(font_bytes).decode()
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">',
           f'<style>@font-face{{font-family:Diagram;src:url(data:font/ttf;base64,{encoded})}}text{{font-family:Diagram;font-size:22px}}</style>',
           f'<rect width="800" height="800" fill="{style["background"]}"/>']
    for e in drawing["edges"]:
        a, b = e["line"]
        points = " ".join(f"{x},{y}" for x, y in e["arrowhead"])
        out.extend([f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{style["ink"]}" stroke-width="{style["width"]}"/>',
                    f'<polygon points="{points}" fill="{style["ink"]}"/>'])
    for n in drawing["nodes"]:
        x0, y0, x1, y1 = n["box"]
        x, y = n["center"]
        out.extend([f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="{style["node_fill"]}" stroke="{style["ink"]}" stroke-width="{style["width"]}"/>',
                    f'<text x="{x}" y="{y+7}" text-anchor="middle" fill="{style["ink"]}">{html.escape(n["label"])}</text>'])
    return "\n".join(out + ["</svg>\n"])


def write_assets(drawing: Scene, stem: Path) -> None:
    png(drawing).save(stem.with_suffix(".png"), optimize=False)
    stem.with_suffix(".svg").write_text(svg(drawing))


def unchanged_geometry(original: dict, edited: dict, unchanged_edges: set[tuple[str, str]]) -> bool:
    return (all(original[k] == edited[k] for k in ("canvas", "style", "nodes"))
            and {tuple(e["edge"]): e for e in original["edges"] if tuple(e["edge"]) in unchanged_edges}
            == {tuple(e["edge"]): e for e in edited["edges"] if tuple(e["edge"]) in unchanged_edges})
