"""Independent raw-record audit. No imports from topodelta_qa or NetworkX.

Floyd–Warshall semantics, explicit set deltas, independent certificate checks,
and degree-constrained adjacency backtracking for exact directed isomorphism.
"""
import argparse
import csv
import hashlib
import html
import itertools
import json
import math
import random
import re
import shutil
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

SEED = 20261027


def rows(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def table(path, data):
    if not data:
        Path(path).write_text('')
        return
    with Path(path).open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def equal(a, b):
    return type(a) is type(b) and a == b


def matrix(graph):
    nodes = graph['nodes']
    assert len(nodes) == len(set(nodes)) and 6 <= len(nodes) <= 12
    assert len(graph['edges']) == len(set(map(tuple, graph['edges'])))
    d = {(u, v): 0 if u == v else math.inf for u in nodes for v in nodes}
    for u, v in graph['edges']:
        assert u in nodes and v in nodes and u != v
        d[u, v] = 1
    for k in nodes:
        for i in nodes:
            for j in nodes:
                d[i, j] = min(d[i, j], d[i, k] + d[k, j])
    return d


def answer(graph, q, d=None):
    d = matrix(graph) if d is None else d
    u, v = q['source'], q['target']
    if q['task'] == 'direct_edge':
        return [u, v] in graph['edges']
    if q['task'] == 'reachability':
        return d[u, v] < math.inf
    assert q['task'] == 'shortest_path'
    return 'unreachable' if d[u, v] == math.inf else d[u, v]


def evidence(graph, q, claimed, cert):
    """A second implementation, without primary answer/certificate helpers."""
    try:
        d = matrix(graph)
        if not equal(answer(graph, q, d), claimed) or not isinstance(cert, dict):
            return False
        u, v = q['source'], q['target']
        if q['task'] == 'direct_edge':
            return (cert.get('kind') == 'edge_claim' and cert.get('source') == u and cert.get('target') == v
                    and type(cert.get('present')) is bool and cert['present'] == claimed)
        if claimed is False or claimed == 'unreachable':
            reached = cert.get('nodes')
            if cert.get('kind') != 'reachable_set' or not isinstance(reached, list):
                return False
            s = set(reached)
            if len(s) != len(reached) or u not in s or v in s or not s <= set(graph['nodes']):
                return False
            # Rooted membership and edge closure establish exact completeness.
            return (all(d[u, n] < math.inf for n in s)
                    and all(a not in s or b in s for a, b in graph['edges']))
        path = cert.get('path')
        edges = set(map(tuple, graph['edges']))
        if not isinstance(path, list) or len(path) < 2 or path[0] != u or path[-1] != v:
            return False
        if len(path) != len(set(path)) or any(e not in edges for e in zip(path, path[1:])):
            return False
        if q['task'] == 'reachability':
            return cert.get('kind') == 'path'
        p = cert.get('distances')
        if cert.get('kind') != 'shortest_path' or not isinstance(p, dict) or set(p) != set(graph['nodes']):
            return False
        if any(x is not None and (type(x) is not int or x < 0) for x in p.values()):
            return False
        return (type(p[u]) is int and p[u] == 0 and p[v] == claimed and len(path) - 1 == claimed
                and all(p[n] is not None for n in path)
                and all(p[a] is None or p[b] is not None and p[b] - p[a] <= 1 for a, b in edges))
    except (KeyError, TypeError, ValueError, AssertionError):
        return False


def signature(graph):
    edges = set(map(tuple, graph['edges']))
    return (len(graph['nodes']), len(edges), tuple(sorted((sum(v == n for u, v in edges), sum(u == n for u, v in edges)) for n in graph['nodes'])))


def iso(a, b):
    if signature(a) != signature(b):
        return False
    ea, eb = set(map(tuple, a['edges'])), set(map(tuple, b['edges']))
    degree = lambda n, es: (sum(v == n for u, v in es), sum(u == n for u, v in es))
    candidates = {u: [v for v in b['nodes'] if degree(u, ea) == degree(v, eb)] for u in a['nodes']}
    order = sorted(a['nodes'], key=lambda u: (len(candidates[u]), -sum(degree(u, ea)), u))
    mapping, used = {}, set()

    def visit(i):
        if i == len(order):
            return True
        u = order[i]
        for v in candidates[u]:
            if v in used or any(((u, x) in ea) != ((v, y) in eb) or ((x, u) in ea) != ((y, v) in eb) for x, y in mapping.items()):
                continue
            mapping[u] = v
            used.add(v)
            if visit(i + 1):
                return True
            used.remove(v)
            del mapping[u]
        return False
    return visit(0)


def semantics(groups):
    errors, certificates = [], Counter()
    counts = Counter()
    for g in groups:
        try:
            vs = g['variants']
            assert len(vs) == 4 and len(g['questions']) == 2
            original = vs[0]['graph']
            assert original == vs[1]['graph'], 'redraw labeled graph changed'
            mixed = False
            for i, v in enumerate(vs):
                graph = v['graph']
                d = matrix(graph)
                assert graph['nodes'] == original['nodes']
                flags = []
                for q in g['questions']:
                    actual = answer(graph, q, d)
                    assert equal(v['answers'][q['id']], actual), 'wrong answer'
                    relevant = not equal(answer(original, q), actual)
                    assert type(v['relevance'][q['id']]) is bool and relevant == v['relevance'][q['id']], 'wrong relevance'
                    assert evidence(graph, q, actual, v['certificates'][q['id']]), 'unsound certificate'
                    flags.append(relevant)
                    counts['answers'] += 1
                    counts['relevance_flags'] += 1
                    certificates[v['certificates'][q['id']]['kind']] += 1
                if i < 2:
                    assert v['edit'] is None
                    continue
                old, new = set(map(tuple, original['edges'])), set(map(tuple, graph['edges']))
                added, deleted = new - old, old - new
                edit = v['edit']
                operand = tuple(edit['operand'])
                assert edit['operation_count'] == 1
                assert added == set(map(tuple, edit['added'])) and deleted == set(map(tuple, edit['deleted']))
                assert edit['directed_set_difference_count'] == len(added) + len(deleted)
                if edit['operation'] == 'addition':
                    assert added == {operand} and not deleted
                elif edit['operation'] == 'deletion':
                    assert deleted == {operand} and not added
                else:
                    assert edit['operation'] == 'reversal'
                    assert deleted == {operand} and added == {operand[::-1]} and len(added) + len(deleted) == 2
                assert v['semantic_changed_edges'] == {k: edit[k] for k in ('added', 'deleted')}
                assert not any(k in v['certificates'][q['id']] for q in g['questions'] for k in ('added', 'deleted'))
                o, s = vs[0]['scene'], v['scene']
                assert all(o[k] == s[k] for k in ('canvas', 'nodes', 'style'))
                old_geometry = {tuple(e['edge']): e for e in o['edges']}
                new_geometry = {tuple(e['edge']): e for e in s['edges']}
                assert all(old_geometry[e] == new_geometry[e] for e in old & new), 'unchanged route moved'
                mixed |= sum(flags) == 1
                counts['edits'] += 1
            assert mixed, 'no mixed-relevance edit'
            counts['groups'] += 1
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            errors.append({'group_id': g['id'], 'error': str(exc) or type(exc).__name__})
    return {'status': 'passed' if not errors else 'failed', 'checked': dict(counts), 'certificate_kinds': dict(certificates), 'errors': errors}


def leakage(root, groups):
    errors, buckets, duplicates = [], defaultdict(list), []
    eligible = exact = 0
    variants = [(g, v) for g in groups for v in g['variants']]
    for i, (g, v) in enumerate(variants):
        for other_g, other_v in variants[:i]:
            if g['split'] == other_g['split']:
                continue
            eligible += 1
            if signature(v['graph']) == signature(other_v['graph']):
                exact += 1
                if iso(v['graph'], other_v['graph']):
                    duplicates.append([g['id'], v['id'], other_g['id'], other_v['id']])
    id_splits = defaultdict(set)
    for kind in ('single', 'paired'):
        allowed = {'id','group_id','split','question','instructions','answer_format'} | ({'image'} if kind == 'single' else {'images','pair_instructions'})
        for row in rows(root / f'inference/{kind}.jsonl'):
            if set(row) != allowed:
                errors.append(f'{kind}: unexpected keys {row["id"]}')
            id_splits[row['group_id']].add(row['split'])
            if not re.fullmatch('[0-9a-f]{24}', row['id']) or not re.fullmatch('[0-9a-f]{24}', row['group_id']):
                errors.append('nonopaque ID')
            for path in [row['image']] if kind == 'single' else row['images']:
                if not re.fullmatch(r'images/[0-9a-f]{24}\.png', path):
                    errors.append('nonneutral image path')
    for g in groups:
        if id_splits[g['id']] != {g['split']}:
            errors.append('group split mismatch')
    svg_tags, svg_attributes, svg_text_nodes = Counter(), Counter(), 0
    for g, v in variants:
        path = root / 'inference' / v['assets']['svg']
        text = path.read_text()
        tree = ET.fromstring(text)
        labels = []
        for element in tree.iter():
            tag = element.tag.split('}')[-1]
            svg_tags[tag] += 1
            for attr in element.attrib:
                svg_attributes[attr] += 1
                if attr.startswith('data-') or attr in ('id', 'class', 'href', 'opacity', 'display'):
                    errors.append(f'Unexpected SVG metadata: {path.name}:{attr}')
            if tag not in {'svg','style','rect','line','polygon','text'}:
                errors.append(f'unexpected SVG tag {tag}')
            if tag == 'text':
                labels.append(element.text)
                svg_text_nodes += 1
        if labels != v['graph']['nodes'] or '<!--' in text:
            errors.append(f'SVG label/metadata mismatch {path.name}')
        if not re.fullmatch('[0-9a-f]{24}', path.stem):
            errors.append('SVG filename disclosure')
    return {'status':'passed' if not errors and not duplicates else 'failed', 'cross_split_variant_pairs':eligible,
            'exact_backtracking_checks':exact,'isomorphism_duplicates':duplicates,'public_rows':1680,
            'svg_files':len(variants),'svg_tags':dict(svg_tags),'svg_attributes':dict(svg_attributes),
            'visible_svg_label_nodes':svg_text_nodes,'errors':errors,
            'boundary':'SVG visible vector primitives permit graph reconstruction. PNG-only calls must not receive SVG source or gold. Public group/pair IDs also require isolation at runner level; no runner is implemented.'}


def features(root, groups):
    edited, graphs = [], []
    for g in groups:
        original = g['variants'][0]
        with Image.open(root / 'inference' / original['assets']['png']) as image:
            old = image.convert('L')
        old_mean = ImageStat.Stat(old).mean[0]
        old_ink = sum(old.histogram()[:180]) / 640000
        for index, v in enumerate(g['variants']):
            n, m = len(v['graph']['nodes']), len(v['graph']['edges'])
            center = v['scene']['nodes'][0]['center']
            rotation = (math.atan2(center[1] - 400, center[0] - 400) % math.tau)
            graphs.append({'group_id':g['id'],'split':g['split'],'variant_id':v['id'],'role':v['role'],
                           'node_count':n,'edge_count':m,'directed_density':m/(n*(n-1)),
                           'layout':'circular_rotation','rotation_radians':rotation,'rotation_octant':int(rotation/math.tau*8),
                           'style':v['scene']['style']})
            if index < 2:
                continue
            with Image.open(root/'inference'/v['assets']['png']) as image:
                new = image.convert('L')
            diff = ImageChops.difference(old, new)
            changed = sum(diff.histogram()[1:]) / 640000
            for q in g['questions']:
                d0, d1 = matrix(original['graph']), matrix(v['graph'])
                length0, length1 = d0[q['source'],q['target']], d1[q['source'],q['target']]
                edited.append({'group_id':g['id'],'split':g['split'],'variant_id':v['id'],'question_id':q['id'],
                               'task':q['task'],'source':q['source'],'target':q['target'],
                               'original_answer':json.dumps(answer(original['graph'],q)), 'edited_answer':json.dumps(answer(v['graph'],q)),
                               'relevant':int(not equal(answer(original['graph'],q),answer(v['graph'],q))),
                               'operation':v['edit']['operation'],'node_count':n,'original_edges':len(original['graph']['edges']),
                               'edited_edges':m,'original_density':len(original['graph']['edges'])/(n*(n-1)), 'edited_density':m/(n*(n-1)),
                               'original_path_length':'unreachable' if math.isinf(length0) else length0,
                               'edited_path_length':'unreachable' if math.isinf(length1) else length1,
                               'style':v['scene']['style'],'layout':'circular_rotation',
                               'changed_pixel_fraction':changed,'mean_absolute_pixel_difference':ImageStat.Stat(diff).mean[0],
                               'original_mean_gray':old_mean,'edited_mean_gray':ImageStat.Stat(new).mean[0],
                               'original_ink_fraction':old_ink,'edited_ink_fraction':sum(new.histogram()[:180])/640000,
                               'text_character_count':len(question_text(q)),'id_first_nibble':int(v['id'][0],16)})
    return edited, graphs


def question_text(q):
    u, v = q['source'], q['target']
    if q['task'] == 'reachability': return f'Is there a directed path from {u} to {v}?'
    if q['task'] == 'direct_edge': return f'Is there a directed edge from {u} to {v}?'
    return f"What is the minimum number of directed edges in a path from {u} to {v}? Return 'unreachable' if none exists."


def distributions(out, edits, graphs):
    by = [(['split','task'], 'split_task'),
          (['split','task','operation','original_answer','edited_answer','relevant'],'answer_transitions'),
          (['split','operation','relevant'],'operation_relevance'),
          (['split','node_count','relevant'],'node_relevance'),
          (['split','original_edges','edited_edges','relevant'],'edge_relevance'),
          (['split','original_path_length','edited_path_length','relevant'],'path_lengths'),
          (['split','style','layout','relevant'],'layout_style')]
    for keys, name in by:
        counts = Counter(tuple(r[k] for k in keys) for r in edits)
        table(out/f'{name}.csv',[{**dict(zip(keys,k)),'count':v} for k,v in sorted(counts.items(),key=str)])
    table(out/'graph_variants.csv',graphs)
    table(out/'edited_question_features.csv',edits)
    density = []
    for split in ['train','validation','test']:
        for role in ['original','redraw','edited']:
            rs = [r for r in graphs if r['split']==split and r['role']==role]
            density.append({'split':split,'role':role,'count':len(rs),'density_min':min(r['directed_density'] for r in rs),
                            'density_mean':statistics.mean(r['directed_density'] for r in rs),'density_max':max(r['directed_density'] for r in rs),
                            'nodes_mean':statistics.mean(r['node_count'] for r in rs),'edges_mean':statistics.mean(r['edge_count'] for r in rs)})
    table(out/'density_summary.csv',density)


def auc(rs, key):
    positive, negative = [r for r in rs if r['relevant']], [r for r in rs if not r['relevant']]
    if not positive or not negative: return None
    return sum((p[key]>n[key])+0.5*(p[key]==n[key]) for p in positive for n in negative)/(len(positive)*len(negative))


def binary(rs, predicate):
    tp=tn=fp=fn=0
    for row in rs:
        predicted, actual = bool(predicate(row)),bool(row['relevant'])
        tp+=predicted and actual; tn+=not predicted and not actual
        fp+=predicted and not actual; fn+=not predicted and actual
    return {'n':len(rs),'accuracy':(tp+tn)/len(rs),'balanced_accuracy':((tp/(tp+fn))+(tn/(tn+fp)))/2,
            'true_positive':tp,'true_negative':tn,'false_positive':fp,'false_negative':fn}


def shortcuts(edits, out):
    # Prespecified rules/rank directions: no fitting, threshold selection, or model training.
    rules = [('always_unchanged',lambda r:False)]
    rules += [('text_task_is_'+task,lambda r,t=task:r['task']==t) for task in ['reachability','shortest_path','direct_edge']]
    rules += [('operation_is_'+op,lambda r,o=op:r['operation']==o) for op in ['addition','deletion','reversal']]
    rules += [('changed_pixels_gt_0.005',lambda r:r['changed_pixel_fraction']>0.005),
              ('original_ink_gt_0.02',lambda r:r['original_ink_fraction']>0.02)]
    rule_results=[]
    for split in ['train','validation','test']:
        rs=[r for r in edits if r['split']==split]
        for name,predicate in rules:
            rule_results.append({'split':split,'rule':name,**binary(rs,predicate)})
    ranked=[]
    keys=['text_character_count','changed_pixel_fraction','mean_absolute_pixel_difference','original_mean_gray',
          'edited_mean_gray','original_ink_fraction','edited_ink_fraction','id_first_nibble']
    for split in ['train','validation','test']:
        rs=[r for r in edits if r['split']==split]
        gids=sorted({r['group_id'] for r in rs}); rng=random.Random(SEED)
        for key in keys:
            estimates=[]
            for _ in range(300):
                sampled=rng.choices(gids,k=len(gids))
                sample=[r for gid in sampled for r in rs if r['group_id']==gid]
                value=auc(sample,key)
                if value is not None: estimates.append(value)
            estimates.sort()
            ranked.append({'split':split,'feature':key,'auroc_increasing_feature':auc(rs,key),
                           'group_bootstrap_95_low':estimates[int(.025*(len(estimates)-1))],
                           'group_bootstrap_95_high':estimates[int(.975*(len(estimates)-1))]})
    table(out/'shortcut_fixed_rules.csv',rule_results)
    table(out/'shortcut_rank_diagnostics.csv',ranked)
    save(out/'shortcut_protocol.json',{'seed':SEED,'unit':'edited image/question, 4 rows per group',
         'split_unit':'original group; original dataset split assignments unchanged','fitting':'none',
         'rules':'All listed rules reported; thresholds fixed in audit source, not chosen on validation/test scores.',
         'rank_direction':'increasing feature only; no selecting better sign', 'bootstrap':'300 whole-group resamples per split',
         'limitations':['Post hoc audit after viewing dataset design; not a preregistered confirmatory result.',
                        'Operation is evaluator-only, not directly supplied to a baseline.',
                        'Two questions share each image difference; pixels alone cannot distinguish mixed relevance.',
                        'AUROC associations and weak fixed-rule scores do not prove absence of shortcuts.',
                        'One external test split has only 18 synthetic groups; no external-domain inference.']})


def risk(group):
    vs=group['variants']; n=len(vs[0]['graph']['nodes']); m=len(vs[0]['graph']['edges'])
    heads=[e['arrowhead'][0] for e in vs[0]['scene']['edges']]
    head_gap=min((math.dist(a,b) for a,b in itertools.combinations(heads,2)),default=800)
    degree=max((sum(node in e for e in vs[0]['graph']['edges']) for node in vs[0]['graph']['nodes']),default=0)
    return {'node_count':n,'edge_count':m,'density':m/(n*(n-1)), 'minimum_tip_separation':head_gap,
            'minimum_changed_pixels':min(v['pixel_diff']['changed_pixels'] for v in vs[2:]), 'max_total_degree':degree}


def visual_selection(root, groups, out):
    ranks={g['id']:risk(g) for g in groups}; selected=[]; reasons=defaultdict(list)
    def take(g,reason):
        reasons[g['id']].append(reason)
        if g not in selected: selected.append(g)
    for n in range(6,13): take(min((g for g in groups if ranks[g['id']]['node_count']==n),key=lambda g:g['id']),f'node_count_{n}')
    for split in ['train','validation','test']:
        for style in range(3): take(min((g for g in groups if g['split']==split and g['variants'][0]['scene']['style']==style),key=lambda g:g['id']),f'{split}_style_{style}')
    for key,reverse in [('minimum_tip_separation',False),('minimum_changed_pixels',False),('density',True),('max_total_degree',True)]:
        for g in sorted(groups,key=lambda g:(ranks[g['id']][key],g['id']),reverse=reverse)[:3]: take(g,key)
    for g in sorted(groups,key=lambda g:hashlib.sha256(f'{SEED}:{g["id"]}'.encode()).hexdigest()):
        if len(selected)>=30: break
        take(g,'seeded_fill')
    assert len(selected)>=30
    selected=selected[:30]
    (out/'visual_boards').mkdir()
    selection=[]
    font=ImageFont.load_default(size=19)
    for index,g in enumerate(selected):
        board=Image.new('RGB',(1600,1720),'white'); draw=ImageDraw.Draw(board)
        draw.text((10,5),f'{index+1:02d}  {g["id"]}  {g["split"]}  n={ranks[g["id"]]["node_count"]}',fill='black',font=font)
        for j,q in enumerate(g['questions']): draw.text((10,30+j*24),question_text(q),fill='black',font=font)
        for j,v in enumerate(g['variants']):
            x=(j%2)*800; y=100+(j//2)*810
            label=v['role'] if not v['edit'] else f'edit {j-1}: {v["edit"]["operation"]}'
            draw.text((x+6,y-22),label,fill='black',font=font)
            with Image.open(root/'inference'/v['assets']['png']) as image: board.paste(image,(x,y))
        name=f'{index+1:02d}_{g["id"]}.png'; board.save(out/'visual_boards'/name)
        selection.append({'sequence':index+1,'group_id':g['id'],'split':g['split'],'board':f'visual_boards/{name}',
                          'reasons':';'.join(reasons[g['id']]),**ranks[g['id']]})
    table(out/'visual_selection.csv',selection)
    save(out/'visual_selection.json',selection)
    return selection


def review_packet(root, groups, out):
    packet=out/'human_review/packet'; key_dir=out/'human_review/answer_key'
    (packet/'images').mkdir(parents=True); (packet/'groups').mkdir(); key_dir.mkdir(parents=True)
    style='body{font:17px system-ui;max-width:1700px;margin:24px auto;padding:12px} .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px} img{width:100%;max-width:800px} fieldset{margin:14px 0} textarea{width:95%;min-height:65px} input{margin:6px} @media print{input,textarea{border:1px solid #aaa}}'
    index=['<!doctype html><meta charset="utf-8"><title>TopoDelta-QA human review</title><style>'+style+'</style>',
           '<h1>TopoDelta-QA: 120-group review packet</h1><p>No human reviews have been recorded. Forms start blank. Review images at native resolution or zoom. Do not consult the separate answer key before independent annotation.</p><ol>']
    key=[]; template=[]; image_hashes={}
    for i,g in enumerate(groups):
        page=['<!doctype html><meta charset="utf-8"><title>Review '+g['id']+'</title><style>'+style+'</style>',
              '<a href="../index.html">All groups</a><h1>Group '+str(i+1)+': '+g['id']+'</h1><form>',
              '<label>Reviewer identity <input name="reviewer_identity"></label><label>Date <input type="date" name="review_date"></label>',
              '<p>Arrows point from tail to arrowhead. Labels are arbitrary; no executable flowchart semantics. Count edges for shortest path; use “unreachable” if none exists.</p><ol>']
        page += ['<li>'+html.escape(question_text(q))+'</li>' for q in g['questions']]
        page += ['</ol><div class="grid">']
        for j,v in enumerate(g['variants']):
            filename=Path(v['assets']['png']).name
            shutil.copy2(root/'inference'/v['assets']['png'],packet/'images'/filename)
            image_hashes[filename]=sha(packet/'images'/filename)
            role=['original','redraw','edited 1','edited 2'][j]
            page += [f'<fieldset><legend>{role}</legend><a href="../images/{filename}"><img alt="{role} diagram" src="../images/{filename}"></a>']
            for k,q in enumerate(g['questions']):
                page += [f'<label>Question {k+1} answer <input name="{j}_{k}_answer" autocomplete="off"></label><br>']
                key.append({'group_id':g['id'],'variant_id':v['id'],'role':role,'question_id':q['id'],'question':question_text(q),
                            'answer':v['answers'][q['id']],'certificate':v['certificates'][q['id']], 'edit':v['edit']})
                template.append({'group_id':g['id'],'variant_id':v['id'],'role':role,'question_id':q['id'],
                                 'reviewer_identity':'','date':'','answer':'','readability':'','ambiguity':'','edge_direction':'',
                                 'edit_detectability':'','disagreement':'','adjudicator_identity':'','adjudication_date':'','adjudication':'','exclusion_reason':''})
            for field,prompt in [('readability','Label and arrowhead readability'),('ambiguity','Crossings, overlaps, clipping, or ambiguity'),('direction','Edge-direction confidence and uncertain edges'),('edit_detectability','Visible changes compared with original (if applicable)')]:
                page += [f'<label>{prompt}<textarea name="{j}_{field}"></textarea></label>']
            page += ['</fieldset>']
        page += ['</div><label>Disagreement<textarea name="disagreement"></textarea></label><label>Adjudicator identity<input name="adjudicator_identity"></label><label>Adjudication date<input type="date" name="adjudication_date"></label><label>Adjudication<textarea name="adjudication"></textarea></label><label>Exclusion reason<textarea name="exclusion_reason"></textarea></label>',
                 '<button type="button" id="download">Download this review as JSON</button></form>',
                 '<script>document.getElementById("download").onclick=()=>{const r=Object.fromEntries(new FormData(document.querySelector("form")));r.group_id="'+g['id']+'";const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:"application/json"}));a.download="review_'+g['id']+'.json";a.click();URL.revokeObjectURL(a.href);};</script>']
        (packet/'groups'/f'{g["id"]}.html').write_text('\n'.join(page))
        index.append(f'<li><a href="groups/{g["id"]}.html">Group {i+1} · {g["id"]}</a></li>')
    (packet/'index.html').write_text('\n'.join(index+['</ol>']))
    table(packet/'review_records_blank.csv',template)
    save(packet/'image_hashes.json',image_hashes)
    save(key_dir/'answers.json',key)
    table(key_dir/'answers.csv',[{k:v for k,v in r.items() if k not in ('certificate','edit')} for r in key])
    (out/'human_review/README.md').write_text('Open packet/index.html in a browser. Each group has four full-resolution images, two questions, blank answers and review fields. Download filled forms as JSON or use review_records_blank.csv. Reviews and adjudications are unperformed; no reviewer identity/date/answer is prefilled. Keep answer_key/ separate until independent review is complete. The answer key is algorithmic gold, not human adjudication. Files are local and make no network requests.\n')
    return {'groups':len(groups),'images':len(image_hashes),'blank_answer_rows':len(template),'recorded_human_reviews':0}


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('outputs/pilot'));p.add_argument('--output',type=Path,default=Path('outputs/phase1b'))
    args=p.parse_args(); out=args.output;out.mkdir(parents=True,exist_ok=False)
    gs=rows(args.dataset/'gold/groups.jsonl')
    save(out/'semantics.json',semantics(gs)); print('Independent semantics complete',flush=True)
    save(out/'leakage.json',leakage(args.dataset,gs)); print('Exact independent split/metadata audit complete',flush=True)
    edits,graphs=features(args.dataset,gs);distributions(out,edits,graphs);shortcuts(edits,out);print('Distribution and unfitted shortcut diagnostics complete',flush=True)
    selection=visual_selection(args.dataset,gs,out)
    save(out/'review_packet_summary.json',review_packet(args.dataset,gs,out))
    save(out/'audit_provenance.json',{'seed':SEED,'script_sha256':sha(__file__),'dataset_manifest_sha256':sha(args.dataset/'manifest.json'),
                                    'independent_semantics':'raw JSON + Floyd–Warshall; no project imports, no NetworkX',
                                    'visual_review':'boards selected, pending agent inspection','selected_groups':len(selection)})
    print('Boards and blank human-review packet prepared',flush=True)

if __name__=='__main__': main()
