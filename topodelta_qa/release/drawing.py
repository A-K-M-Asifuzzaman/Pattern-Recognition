"""Spaced layouts, a constructive visibility pool, and measurable raster geometry."""
import html
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from ..render import (box_polygon, polygon_distance, segment_polygon_distance,
                      segment_distance, point_distance, intersects)

LAYOUTS = ('grid', 'staggered_layers', 'radial', 'concentric')
STYLES = (
    {'name': 'plain_box', 'background': '#ffffff', 'fill': '#ffffff', 'ink': '#171717', 'width': 3, 'radius': 0},
    {'name': 'soft_round', 'background': '#fafafa', 'fill': '#e9e9e9', 'ink': '#292929', 'width': 3, 'radius': 12},
    {'name': 'heavy_frame', 'background': '#ffffff', 'fill': '#ffffff', 'ink': '#101010', 'width': 4, 'radius': 0},
    {'name': 'double_frame', 'background': '#f6f6f6', 'fill': '#ffffff', 'ink': '#242424', 'width': 2, 'radius': 6},
)
FONT_SIZE = 26
NODE_W, NODE_H = 88, 62
ARROW_LENGTH, ARROW_HALF_WIDTH, GAP = 22, 8, 9
RENDERER = {'version': 'rc1-native-v1', 'font': 'Pillow bundled Aileron Regular',
            'font_size': FONT_SIZE, 'node_size': [NODE_W, NODE_H], 'arrow_length': ARROW_LENGTH,
            'arrow_half_width': ARROW_HALF_WIDTH, 'endpoint_gap': GAP,
            'minimum_node_gap': 20, 'minimum_edge_clearance': 5,
            'minimum_arrow_clearance': 5, 'minimum_edit_changed_pixels': 120,
            'supersampling': 1, 'crossings': 'rejected; crossings never imply junctions',
            'styles': STYLES, 'layouts': LAYOUTS}


@lru_cache(maxsize=512)
def template(n, family, template_id):
    # Templates vary geometry, independently of the graph/question streams.
    import random
    rng = random.Random(f'rc-layout:{n}:{family}:{template_id}')
    if family == 'grid':
        cols = math.ceil(math.sqrt(n))
        raw = [(i % cols * 230, i // cols * 230) for i in range(n)]
    elif family == 'staggered_layers':
        cols = 3 if n <= 12 else 4
        raw = [(i % cols * 245 + (i // cols % 2)*95, i // cols * 215) for i in range(n)]
    elif family == 'radial':
        radius = max(320, n*31)
        raw = [(0, 0)] + [(radius*math.cos(2*math.pi*i/(n-1)), radius*math.sin(2*math.pi*i/(n-1))) for i in range(n-1)]
    elif family == 'concentric':
        outer = n-1 if template_id >= 8 and n <= 8 else math.ceil(n*.65)
        if template_id>=16 and n==6:outer=4
        inner = n-outer
        radius = max(350, outer*40)
        raw = [(radius*math.cos(2*math.pi*i/outer), radius*math.sin(2*math.pi*i/outer)) for i in range(outer)]
        raw += [(radius*.43*math.cos(2*math.pi*(i+.35)/inner), radius*.43*math.sin(2*math.pi*(i+.35)/inner)) for i in range(inner)]
        if template_id>=16 and n==6:raw[-2:]=[(0,0),(radius*.28,radius*.28)]
    else:
        raise ValueError('unknown layout')
    raw = [(x+rng.uniform(-12,12), y+rng.uniform(-12,12)) for x,y in raw]
    min_x,max_x = min(x for x,y in raw),max(x for x,y in raw)
    min_y,max_y = min(y for x,y in raw),max(y for x,y in raw)
    size = max(1152, math.ceil((max(max_x-min_x,max_y-min_y)+240)/128)*128)
    points = tuple((round(x-(min_x+max_x)/2+size/2,4),round(y-(min_y+max_y)/2+size/2,4)) for x,y in raw)
    candidates = []
    for a in range(n):
        for b in range(a+1,n):
            if all(i in (a,b) or point_distance(points[i],points[a],points[b]) >= 64 for i in range(n)):
                candidates.append((math.dist(points[a],points[b]), a,b))
    chosen = []
    pocket=family=='concentric' and n==6 and template_id>=16
    for _,a,b in sorted(candidates,key=lambda e:((n-1 in e[1:]) if pocket else False,e)):
        good = True
        for c,d in chosen:
            shared = {a,b}&{c,d}
            if not shared:
                if segment_distance(points[a],points[b],points[c],points[d]) < 14:
                    good = False; break
            else:
                s = next(iter(shared));u = b if a==s else a;v = d if c==s else c
                p,q = points[u],points[v];o = points[s]
                cosine = sum((p[k]-o[k])*(q[k]-o[k]) for k in (0,1))/(math.dist(p,o)*math.dist(q,o))
                if cosine > math.cos(math.radians(32)):
                    good = False; break
        if good:
            chosen.append((a,b))
    return size,points,tuple(chosen)


def scene(graph, points, size, style):
    font = ImageFont.load_default(size=FONT_SIZE)
    nodes = []
    for label in graph['nodes']:
        x,y = points[label];bounds = font.getbbox(label, anchor='mm')
        nodes.append({'label':label,'center':[x,y], 'box':[x-NODE_W/2,y-NODE_H/2,x+NODE_W/2,y+NODE_H/2],
                      'label_box':[x+bounds[0],y+bounds[1],x+bounds[2],y+bounds[3]]})
    edges = []
    for u,v in graph['edges']:
        a,b = points[u],points[v];dx,dy = b[0]-a[0],b[1]-a[1];length = math.hypot(dx,dy)
        ex,ey = dx/length,dy/length
        clip = min(NODE_W/(2*abs(ex)) if ex else math.inf,NODE_H/(2*abs(ey)) if ey else math.inf)+GAP
        start = [a[0]+clip*ex,a[1]+clip*ey];end = [b[0]-clip*ex,b[1]-clip*ey]
        base = [end[0]-ARROW_LENGTH*ex,end[1]-ARROW_LENGTH*ey]
        arrow = [end,[base[0]-ARROW_HALF_WIDTH*ey,base[1]+ARROW_HALF_WIDTH*ex],
                 [base[0]+ARROW_HALF_WIDTH*ey,base[1]-ARROW_HALF_WIDTH*ex]]
        edges.append({'edge':[u,v],'line':[start,end],'arrowhead':arrow})
    return {'canvas':[size,size],'style':style,'nodes':nodes,'edges':edges}


def validate_scene(graph, drawing):
    points = {n['label']:n['center'] for n in drawing['nodes']}
    assert drawing == scene(graph,points,drawing['canvas'][0],drawing['style']), 'scene_mismatch'
    width,height = drawing['canvas'];assert width==height and width>=1152
    for i,n in enumerate(drawing['nodes']):
        x0,y0,x1,y1 = n['box'];a,b,c,d = n['label_box']
        assert 24 <= x0 < x1 <= width-24 and 24 <= y0 < y1 <= height-24,'clipped_node'
        assert x0+7 <= a < c <= x1-7 and y0+7 <= b < d <= y1-7,'clipped_label'
        for m in drawing['nodes'][i+1:]:
            assert polygon_distance(box_polygon(n['box']),box_polygon(m['box']))>=20,'label_or_node_overlap'
    minimum = math.inf
    for i,e in enumerate(drawing['edges']):
        a,b = e['line'];assert math.dist(a,b)>=65,'short_edge'
        for p in [a,b]+e['arrowhead']:
            assert 12 <= p[0] <= width-12 and 12 <= p[1] <= height-12,'clipped_edge'
        for n in drawing['nodes']:
            # Bounding circles prefilter exact box checks without accepting a collision.
            if point_distance(n['center'],a,b)>90 and math.dist(n['center'],b)>100:
                continue
            assert segment_polygon_distance(a,b,box_polygon(n['box']))>=5,'edge_through_node'
            assert polygon_distance(e['arrowhead'],box_polygon(n['box']))>=5,'arrow_through_node'
        for other in drawing['edges'][i+1:]:
            c,d = other['line'];clearance = segment_distance(a,b,c,d)
            minimum = min(minimum,clearance)
            assert clearance>=5,'crossing_or_overlapping_edges'
            # Arrow triangles fit inside a radius-25 disk around their mid-axis.
            if min(point_distance(b,c,d),point_distance(d,a,b))>50 and math.dist(b,d)>65:
                continue
            assert segment_polygon_distance(a,b,other['arrowhead'])>=5,'hidden_arrowhead'
            assert segment_polygon_distance(c,d,e['arrowhead'])>=5,'hidden_arrowhead'
            assert polygon_distance(e['arrowhead'],other['arrowhead'])>=5,'overlapping_arrowheads'
    return {'minimum_route_clearance':None if math.isinf(minimum) else round(minimum,4),
            'font_pixels':FONT_SIZE,'arrow_length_pixels':ARROW_LENGTH,'arrow_width_pixels':2*ARROW_HALF_WIDTH}


def png(drawing):
    style = STYLES[drawing['style']];im = Image.new('RGB',drawing['canvas'],style['background']);draw = ImageDraw.Draw(im)
    for edge in drawing['edges']:
        draw.line([tuple(p) for p in edge['line']],fill=style['ink'],width=style['width'])
        draw.polygon([tuple(p) for p in edge['arrowhead']],fill=style['ink'])
    font = ImageFont.load_default(size=FONT_SIZE)
    for node in drawing['nodes']:
        draw.rounded_rectangle(node['box'],radius=style['radius'],fill=style['fill'],outline=style['ink'],width=style['width'])
        if style['name']=='double_frame':
            x0,y0,x1,y1 = node['box'];draw.rounded_rectangle((x0+5,y0+5,x1-5,y1-5),radius=3,outline=style['ink'],width=1)
        draw.text(tuple(node['center']),node['label'],anchor='mm',font=font,fill=style['ink'])
    return im


def svg(drawing):
    style=STYLES[drawing['style']];w,h=drawing['canvas']
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
         '<style>@font-face{font-family:Diagram;src:url(../fonts/Aileron-Regular.ttf)}text{font-family:Diagram;font-size:26px;dominant-baseline:central;text-anchor:middle}</style>',
         f'<rect width="{w}" height="{h}" fill="{style["background"]}"/>']
    for edge in drawing['edges']:
        a,b=edge['line'];points=' '.join(f'{x},{y}' for x,y in edge['arrowhead'])
        out += [f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{style["ink"]}" stroke-width="{style["width"]}"/>',f'<polygon points="{points}" fill="{style["ink"]}"/>']
    for node in drawing['nodes']:
        x0,y0,x1,y1=node['box'];x,y=node['center']
        out += [f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="{style["radius"]}" fill="{style["fill"]}" stroke="{style["ink"]}" stroke-width="{style["width"]}"/>']
        if style['name']=='double_frame':
            out += [f'<rect x="{x0+5}" y="{y0+5}" width="{x1-x0-10}" height="{y1-y0-10}" rx="3" fill="none" stroke="{style["ink"]}" stroke-width="1"/>']
        out += [f'<text x="{x}" y="{y}" fill="{style["ink"]}">{html.escape(node["label"])}</text>']
    return '\n'.join(out+['</svg>\n'])
