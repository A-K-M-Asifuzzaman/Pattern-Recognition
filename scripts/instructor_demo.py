"""Extract, render and verify a bounded, answer-visible demo; no inference or generation."""
import argparse
import csv
import hashlib
import html
import json
import shutil
from collections import Counter
from pathlib import Path

from topodelta_qa.release.independent import verify_group
from topodelta_qa.release.logic import question_text

PROJECT=Path(__file__).resolve().parents[1]
DATA=PROJECT/'outputs/topodelta_qa_v0.3.0-rc1'
DEMO=PROJECT/'instructor_demo'
HERO='cb2cb52cb5e1d654b236734a'

def read(path):return json.loads(path.read_text())
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def escaped(value):return html.escape(str(value))
def answer(value):return json.dumps(value,ensure_ascii=False)
def edge_text(edges):return ', '.join(a+' → '+b for a,b in edges) or 'none'

def extract():
    assert not DEMO.exists(),'Preserve an existing presentation; extraction refuses overwrite'
    manifest=read(DATA/'manifest.json');coverage=read(DATA/'reports/coverage_summary.json')
    for key,count in manifest['counts'].items():assert coverage[key]==count,key
    assert manifest['counts']['groups']==20000 and not manifest['human_validation'] and not manifest['model_inference']
    (DEMO/'images').mkdir(parents=True);(DEMO/'samples').mkdir();(DEMO/'reports').mkdir()
    audited=[readline for readline in map(json.loads,(PROJECT/'outputs/topodelta_qa_v0.3.0-rc1_audit/visual_records.jsonl').read_text().splitlines()) if readline['features']['split']=='train']
    pool=[read(DATA/f'gold/records/{row["slot"]:05d}.json') for row in audited]
    hero=read(DATA/'gold/records/01722.json');assert hero['id']==HERO
    chosen=[hero];layout=Counter([hero['coverage']['layout']]);style=Counter([hero['coverage']['style']]);seen=set()
    def tags(group):
        c=group['coverage'];return {(k,str(c[k])) for k in ('layout','style','topology','connectivity','density_bin')}|{('task',q['task']) for q in group['questions']}|{('operation',v['edit']['operation']) for v in group['variants'][2:]}
    seen.update(tags(hero))
    for n in [6,9,13,17,7,10,14,18,8,11,15,19,12,16,20]:
        candidates=[g for g in pool if g['coverage']['nodes']==n and g['id'] not in {x['id'] for x in chosen}]
        assert candidates,n
        group=min(candidates,key=lambda g:(-len(tags(g)-seen),layout[g['coverage']['layout']]+style[g['coverage']['style']],hashlib.sha256(('instructor-demo-v1:'+g['id']).encode()).hexdigest()))
        chosen.append(group);seen.update(tags(group));layout[group['coverage']['layout']]+=1;style[group['coverage']['style']]+=1
    assert len(chosen)==len({g['id'] for g in chosen})==16
    assert set(layout)=={'grid','radial','concentric','staggered_layers'} and set(style)==set(range(4))
    assert all(g['split']=='train' for g in chosen)
    sources={};catalog=[]
    def copy(source,target):
        relative=source.relative_to(DATA).as_posix();assert sha(source)==manifest['files'][relative],relative
        shutil.copyfile(source,target);assert sha(target)==manifest['files'][relative]
        sources[target.relative_to(DEMO).as_posix()]={'release_path':relative,'sha256':manifest['files'][relative]}
    for g in chosen:
        verify_group(g);copy(DATA/f'gold/records/{g["slot"]:05d}.json',DEMO/'samples'/f'{g["id"]}.json')
        for v in g['variants']:copy(DATA/'inference'/v['assets']['png'],DEMO/v['assets']['png'])
        catalog.append({'group_id':g['id'],'slot':g['slot'],'split':g['split'],'source_record':f'gold/records/{g["slot"]:05d}.json','nodes':g['coverage']['nodes'],'layout':g['coverage']['layout'],'style':g['coverage']['style']})
    report_names=['coverage_summary.json','validation.json','split_isomorphism.json','export_boundary.json','acceptance_by_size.csv','answer_distribution.csv','answer_transitions.csv','tasks.csv','operations.csv','question_path_lengths.csv','unmet_coverage_cells.csv','shortcut_associations.csv','shortcut_diagnostics.json']
    for name in report_names:copy(DATA/'reports'/name,DEMO/'reports'/name)
    copy(DATA/'schemas/group.schema.json',DEMO/'reports/group.schema.json')
    supplemental={
        'reproducibility.json':PROJECT/'outputs/release_candidate_work/reproducibility.json',
        'archive_integrity.json':PROJECT/'outputs/topodelta_qa_v0.3.0-rc1_archives/ARCHIVES.json',
        'agent_visual_summary.json':PROJECT/'outputs/topodelta_qa_v0.3.0-rc1_audit/visual_summary.json',
        'cross_protocol_shortcut.json':PROJECT/'outputs/topodelta_qa_v0.3.0-rc1_audit/CROSS_PROTOCOL_SHORTCUT.json',
        'scope_closeout.json':PROJECT/'outputs/topodelta_qa_v0.3.0-rc1_CLOSEOUT.json',
        'environment.json':DATA/'reproduction/environment.json',
        'licensing_inventory.json':DATA/'licenses/inventory.json'}
    for name,source in supplemental.items():
        if source.is_relative_to(DATA):copy(source,DEMO/'reports'/name)
        else:
            shutil.copyfile(source,DEMO/'reports'/name)
            sources['reports/'+name]={'project_path':source.relative_to(PROJECT).as_posix(),'sha256':sha(source)}
    write(DEMO/'reports/release_manifest_summary.json',{'notice':'Header projection of the actual sealed manifest; full 200484-file inventory stays local.','version':manifest['version'],'counts':manifest['counts'],'payload_files':len(manifest['files']),'manifest_sha256':sha(DATA/'manifest.json'),'human_validation':False,'model_inference':False})
    write(DEMO/'selection.json',{'method':'Fixed six-node teaching example plus one additional training group per exact size 6–20, greedily covering layout/style/topology/density/tasks/operations from the completed agent-audit pool; SHA-256 tie-break. No model performance used.','seed_label':'instructor-demo-v1:','hero_group':HERO,'groups':catalog,'group_count':16,'png_count':64,'source_files':sources,'local_git_tracking_inspection':'No .git repository or index existed; git status and git ls-files both reported not a repository. No tracking was changed.'})
    print('Extracted 16 saved training groups and 64 byte-identical PNGs; no rendering or expansion.')

def evidence(cert):
    if cert['kind'] in ('path','shortest_path'):
        text=' → '.join(cert['path'])
        if cert['kind']=='shortest_path':text+='; distance potentials included below.'
        return text
    if cert['kind']=='reachable_set':return 'Rooted, outgoing-closed reachable set: {'+', '.join(cert['nodes'])+'}; target excluded.'
    return cert['source']+' → '+cert['target']+(' is present.' if cert['present'] else ' is absent from the full graph.')

def render():
    selection=read(DEMO/'selection.json');groups=[read(DEMO/'samples'/f'{r["group_id"]}.json') for r in selection['groups']]
    styles=read(DEMO/'reports/environment.json')['renderer']['styles'];parts=[]
    for i,g in enumerate(groups):
        original=g['variants'][0];c=g['coverage'];panels=[]
        questions=''.join(f'<li><strong>Q{j+1} · {escaped(q["task"])}</strong>: {escaped(question_text(q))}</li>' for j,q in enumerate(g['questions']))
        for vi in (0,2,1,3):
            v=g['variants'][vi];title=['Original','Topology-preserving redraw','Edit A · applied to original','Edit B · applied to original'][vi]
            e=v['edit'];changes='Original labeled graph.' if v['role']=='original' else 'Same complete labeled graph and answers; appearance changes.'
            if e:changes=f'{e["operation"].capitalize()} {edge_text([e["operand"]])}. Added: {edge_text(e["added"])}. Deleted: {edge_text(e["deleted"])}. {e["operation_count"]} operation; {e["directed_set_difference_count"]} directed-edge difference(s).'
            qa=[]
            for j,q in enumerate(g['questions']):
                qid=q['id'];before=original['answers'][qid];after=v['answers'][qid];relevant=v['relevance'][qid]
                note=('answer changes · relevant' if relevant else 'answer preserved · irrelevant') if e else 'same question on this image'
                qa.append(f'<li><strong>Q{j+1}: {escaped(answer(after))}</strong> <span class="transition">({escaped(answer(before))} → {escaped(answer(after))}; {note})</span><br><span class="evidence">Evidence: {escaped(evidence(v["certificates"][qid]))}</span></li>')
            panels.append(f'<section class="variant"><h3>{title}</h3><a class="diagram" href="{v["assets"]["png"]}" target="_blank" rel="noopener"><img src="{v["assets"]["png"]}" alt="{title}: group {g["id"]}, {c["nodes"]} nodes" loading="lazy" width="{v["scene"]["canvas"][0]}" height="{v["scene"]["canvas"][1]}"></a><p class="delta">{escaped(changes)}</p><ol class="answers">'+''.join(qa)+'</ol><details><summary>Saved answer certificates</summary><pre>'+escaped(json.dumps(v['certificates'],indent=2))+'</pre></details></section>')
        hero='''<aside class="teaching"><strong>Same edit, two questions.</strong> Delete VA → JM. Reachability stays <b>true</b> through VA → VQ → JM; the direct-edge answer changes <b>true → false</b>. Edit relevance belongs to a question, not just to a changed edge. Edit B also demonstrates one reversal with two directed-edge differences.</aside>''' if g['id']==HERO else ''
        parts.append(f'<article id="g-{g["id"]}"><header><p class="eyebrow">GROUP {i+1:02d} / 16 · TRAIN</p><h2>{"The teaching example" if i==0 else str(c["nodes"])+" nodes · "+c["layout"].replace("_"," ")}</h2><p>{c["nodes"]} nodes · {c["edges"]} original edges · {c["layout"]} · {escaped(styles[c["style"]]["name"])} · {c["topology"]} · {c["connectivity"]} · {c["density_bin"]}</p><p class="id">{g["id"]} · <a href="samples/{g["id"]}.json">complete saved annotation</a> · <a href="#top">back to index</a></p></header>{hero}<ol class="questions">{questions}</ol><div class="variants">'+''.join(panels)+'</div></article>')
    navigation=''.join(f'<a href="#g-{g["id"]}">{i+1:02d} · {g["coverage"]["nodes"]} nodes · {g["coverage"]["layout"].replace("_"," ")}</a>' for i,g in enumerate(groups))
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TopoDelta-QA · instructor gallery</title><style>
:root{color-scheme:light;--ink:#172b32;--muted:#4f6268;--line:#c8d3d4;--accent:#075e66}*{box-sizing:border-box}body{margin:0;background:#f5f7f5;color:var(--ink);font:17px/1.55 system-ui,sans-serif}main{max-width:1360px;margin:auto;padding:28px}h1{font-size:clamp(2.1rem,5vw,3.6rem);line-height:1.1;letter-spacing:-.035em}h2{font-size:2rem;line-height:1.2}h3{margin:0 0 12px;font-size:1.2rem}a{color:var(--accent);text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #e19319;outline-offset:4px}.lead{max-width:850px}.eyebrow{font-size:.8rem;font-weight:750;letter-spacing:.12em}.notice{border-left:4px solid var(--accent);padding:12px 18px;background:white}.index{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:26px 0 42px}.index a{padding:9px 12px;background:white;border:1px solid var(--line);text-decoration:none}.index a:hover{background:#e7f0ed}article{border-top:2px solid var(--ink);padding:30px 0 42px;scroll-margin-top:16px}article header p{margin:.4rem 0}.id{font-size:.85rem;overflow-wrap:anywhere}.teaching{background:#e3efe8;padding:18px 22px;margin:20px 0;border-left:5px solid var(--accent)}.questions{padding:18px 18px 18px 42px;background:white}.questions li+li{margin-top:8px}.variants{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.variant{background:white;border:1px solid var(--line);padding:18px;min-width:0}.diagram{display:block;background:white}.diagram img{display:block;width:100%;height:auto;border:1px solid #e5e8e5}.delta{font-weight:600;font-size:.95rem}.answers{padding-left:22px}.answers li+li{margin-top:12px}.transition,.evidence{color:var(--muted);font-size:.9rem}details{border-top:1px solid var(--line);padding-top:10px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.45 ui-monospace,monospace}.footer{padding:22px 0;color:var(--muted)}@media(max-width:760px){main{padding:18px}.index{grid-template-columns:repeat(2,1fr)}.variants{grid-template-columns:1fr}h2{font-size:1.65rem}}@media print{.index{display:none}article{break-before:page}.variants{grid-template-columns:1fr 1fr}.variant{break-inside:avoid}body{background:white;font-size:11px}}
</style></head><body><main id="top"><p class="eyebrow">TOPODELTA-QA · DATASET PRESENTATION</p><h1>One graph edit.<br>Two different answer effects.</h1><p class="lead">Sixteen saved training groups from v0.3.0-rc1. Every group has an original, a redraw, two separate edits and two questions. All answers below are saved algorithmic annotations, not model predictions.</p><div class="notice"><strong>No human validation or model results.</strong> Automated correctness checks and agent judgments of readability are separate. Click a diagram to inspect its saved full-resolution PNG. Arrows point from tail to arrowhead; crossings are not junctions. This release rejects crossings.</div><p><a href="README.md">Concise README</a> · <a href="INSTRUCTOR_SUMMARY.md">Five-minute script</a> · <a href="annotation_example.json">Small JSON example</a> · <a href="STATUS.md">Status and limitations</a></p><nav class="index" aria-label="Choose one of sixteen groups">'''+navigation+'</nav>'+''.join(parts)+'''<footer class="footer">Intentional presentation selection, not a random evaluation sample. All examples are from train. The redraw/style shortcut is documented: report redraw invariance separately from edit sensitivity. No model benchmarking, inference, paid API, dataset expansion or human validation occurred.</footer></main></body></html>'''
    (DEMO/'gallery.html').write_text(page)
    g=groups[0];original,edited=g['variants'][0],g['variants'][2]
    example={'presentation_projection':True,'description':'One saved original/edit pair with two questions. Complete four-variant record is linked in the gallery. Geometry and duplicate explanation fields are omitted here.','source_record':selection['source_files']['samples/'+g['id']+'.json'],'group_id':g['id'],'split':g['split'],'original_graph':original['graph'],'edited_variant_id':edited['id'],'changed_edges':edited['semantic_changed_edges'],'edit_operation':edited['edit'],'questions':[{'id':q['id'],'task':q['task'],'text':question_text(q),'original_answer':original['answers'][q['id']],'edited_answer':edited['answers'][q['id']],'edit_relevant':edited['relevance'][q['id']],'original_answer_evidence':original['certificates'][q['id']],'edited_answer_evidence':edited['certificates'][q['id']]} for q in g['questions']]}
    write(DEMO/'annotation_example.json',example)
    documentation()
    print('Rendered offline HTML and a small annotation projection from saved data.')

def documentation():
    header=read(DEMO/'reports/release_manifest_summary.json');counts=header['counts'];coverage=read(DEMO/'reports/coverage_summary.json');visual=read(DEMO/'reports/agent_visual_summary.json');repro=read(DEMO/'reports/reproducibility.json');arc=read(DEMO/'reports/archive_integrity.json');selection=read(DEMO/'selection.json')
    bands=[(a,b,sum(coverage['nodes'][str(n)] for n in range(a,b+1))) for a,b in [(6,8),(9,12),(13,16),(17,20)]]
    band_rows='\n'.join(f'| {a}–{b} | {n:,} |' for a,b,n in bands)
    layout_text=', '.join(f'{k.replace("_"," ")} {n:,}' for k,n in coverage['layout'].items())
    with (DEMO/'reports/tasks.csv').open() as stream:tasks=list(csv.DictReader(stream))
    task_rows='\n'.join('| '+task+' | '+' | '.join(f'{sum(int(r["count"]) for r in tasks if r["task"]==task and r["split"]==split):,}' for split in ('train','validation','test'))+' |' for task in ('direct_edge','reachability','shortest_path'))
    operations=Counter()
    with (DEMO/'reports/operations.csv').open() as stream:
        for row in csv.DictReader(stream):operations[row['operation']]+=int(row['count'])
    readme=f'''# TopoDelta-QA instructor demo · v0.3.0-rc1

**Dataset presentation only.** Open [the offline gallery](gallery.html), then use
[the five-minute instructor script](INSTRUCTOR_SUMMARY.md). No server, internet,
API key, inference or model is required. Answers are deliberately visible.

## Problem and design

A graph edit can change one answer while preserving another. TopoDelta-QA pairs
directed graph diagrams with reachability, shortest-path-length and direct-edge
questions. Each base group has an original, a complete labeled-graph-preserving
redraw and two edits independently applied to the original. Each of its two
questions is answered on all four images. At least one identical edit changes
one question's answer and preserves the other.

**Start with group `{HERO}`.** Delete **VA → JM**. Reachability remains true via
**VA → VQ → JM**; direct-edge presence changes true → false. Changed edges and
answer-supporting evidence are separate annotations.

## Verified release counts

| Unit | Count |
| --- | ---: |
| Base groups | {counts['groups']:,} |
| Diagram renderings | {counts['diagram_renderings']:,} |
| PNG files / SVG files | {counts['png_files']:,} / {counts['svg_files']:,} |
| Single-image QA instances | {counts['single_qa_instances']:,} |
| Original–variant–question comparisons | {counts['original_variant_question_comparisons']:,} |

These counts match the actual sealed manifest; this presentation does not add
samples. The group is the aggregation unit. Its images/questions are correlated;
global uniqueness constraints also couple acceptance. Do not count renderings
as independent base graphs.

| Base-graph nodes | Groups |
| --- | ---: |
{band_rows}

Train / validation / test: **{int(coverage['splits']['train']):,} / {int(coverage['splits']['validation']):,} / {int(coverage['splits']['test']):,}**.
DAG / cyclic: **{coverage['topology']['dag']:,} / {coverage['topology']['cyclic']:,}**.
Connected / disconnected: **{coverage['connectivity']['connected']:,} / {coverage['connectivity']['disconnected']:,}**.
Sparse / moderate: **{coverage['density']['sparse']:,} / {coverage['density']['moderate']:,}**.
Layouts: {layout_text}. Four style families have **5,000 base groups each**.
Density uses edges/nodes: sparse [0.6, 1.25), moderate [1.25, 1.75], for base graphs.
Edits can leave those bins. Exact sizes, answer transitions and task/operation
counts are in [the copied reports](reports/coverage_summary.json).

| Task (base questions, before four-image replication) | Train | Validation | Test |
| --- | ---: | ---: | ---: |
{task_rows}

The 40,000 edits comprise **{operations['addition']:,} additions, {operations['deletion']:,}
deletions and {operations['reversal']:,} reversals**. Across 80,000 edit/question cases,
**{coverage['feature_counts']['relevant_edit_question_cases']:,} are relevant / {coverage['feature_counts']['irrelevant_edit_question_cases']:,} irrelevant**;
redraw comparisons are separate. Rejection sampling accepted {coverage['groups']:,} of
{coverage['attempted']:,} attempted candidates and rejected {coverage['rejected']:,}; see
[acceptance by size](reports/acceptance_by_size.csv).

## Read the annotations

[The small JSON example](annotation_example.json) is a labeled presentation
projection of one original/edit pair, not a replacement schema. Complete saved
records for all 16 groups are in `samples/`; the canonical
[group schema](reports/group.schema.json) is also included.

| Field | Meaning |
| --- | --- |
| `questions` | Task, source/target labels and opaque question ID |
| `variants[].graph` / `scene` | Directed labeled graph / rendered geometry |
| `edit` / `semantic_changed_edges` | One declared operation / signed edge delta |
| `answers` / `certificates` | Typed algorithmic answers / supporting evidence |
| `relevance` | Whether that edit changes that question's answer |
| `answer_change_evidence` | Before/after answer evidence, distinct from the delta |

A reversal is **one operation and two directed-edge differences**. Any valid
supporting path is acceptable. Negative reachability needs a rooted, closed
reachable set; finite shortest paths also include distance potentials proving
optimality. An empty edge list does not prove non-reachability.

## Reproduction and evidence

The complete second generation matched **{repro['payload_files_compared']:,} payload hashes** and
manifest bytes, including **{repro['annotation_records_compared']:,} records** and **{repro['image_hashes_compared']:,} PNG/SVG assets**;
no normalization was applied. All **{len(arc['archives'])} core archives / {arc['total_members_checked']:,} members** passed
integrity checks. See [status](STATUS.md), [provenance](selection.json),
[the manifest header receipt](reports/release_manifest_summary.json) and
[the full report](../docs/RELEASE_CANDIDATE_REPORT.md).

From the repository root, using the existing local environment:

```sh
PYTHONPATH=. python3 scripts/instructor_demo.py build
PYTHONPATH=. python3 scripts/instructor_demo.py verify
python3 -m unittest discover -s tests -p 'test_instructor_demo.py' -v
```

The prebuilt gallery is designed to open by double-clicking `gallery.html`.
Browser rendering could not be inspected in this environment: Chrome is absent
and the in-app browser blocks local file URLs. Static links/data checks and
direct saved-PNG inspection are recorded separately in `reports/browser_check.json`.
Source rebuild uses
only these saved samples/reports. Sample JSONs preserve canonical asset references;
this small bundle includes PNGs, not SVG/font assets. Reproducing the **full release**
uses `python3 -m topodelta_qa.release.build --output outputs/repeat`, followed by
prepare/verify/boundary/seal/compare commands in the full report and sealed
`reproduction/REPRODUCE.md`. It requires the recorded environment plus the local
historical blacklist and evaluator identity key. Those inputs are intentionally
not committed. No new full generation is part of this presentation.

## Limits and Git preparation

This is a synthetic, template-based, planar research release candidate. Sampling
is biased, especially for six-node topology uniqueness; {coverage['unmet_size_layout_topology_connectivity_density_cells']} coverage cells are empty.
Style differences identify redraws whose answers are unchanged: report redraw
invariance separately from edited-case sensitivity. Low marginal shortcut
associations do not prove absence of leakage. The legacy evaluator supports the
older 6–12-node format; it is not a release-candidate baseline evaluator.

This synthetic dataset has a **{visual['stratified_groups']}-group agent visual audit** plus
**{visual['additional_high_risk_groups']} additional high-risk groups** ({visual['distinct_groups']} distinct groups /
{visual['images_inspected']} images in total). Deterministic graph/image checks
establish defined software properties; agent judgments concern apparent visual
readability at inspected scales. **No human validation or model benchmarking
occurred.** Human validation is outside scope. Existing review materials remain
local and unchanged; no additional review materials were created for this demo.

At the original demo handover the workspace had **no Git repository or tracking
index** before ignore changes; that inspection is preserved in `reports/git_preparation.json`.
The root `.gitignore` now excludes `outputs/`, credentials/identity keys, virtual
environments and caches. Source (`topodelta_qa/`, `scripts/`, `tests/`), configs
without keys, docs and this bounded demo are eligible for ordinary tracking.
Only **16 saved groups / 64 PNGs** are included here, all from train, selected for
teaching coverage rather than performance. The original root README is preserved
in the initial Git commit and the root README's historical section; the frozen
legacy source inventory refers to those original bytes. Full collections and
temporary outputs stay local.
Current repository delivery is documented in [the root README](../README.md).
License adoption and font
redistribution provenance need author review before any external publication;
this demo grants no license. No novelty, superiority or publication readiness
is claimed.
'''
    (DEMO/'README.md').write_text(readme)
    (DEMO/'INSTRUCTOR_SUMMARY.md').write_text(f'''# Five-minute instructor demo

Open `gallery.html` locally. This is an answer-visible dataset demonstration,
not a model experiment. All 16 groups and all 64 PNGs are saved training examples.

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:40 | Gallery opening / teaching example | “We ask whether a local graph edit matters to a particular question.” |
| 0:40–1:50 | Original next to Edit A | “Both questions use VA and JM. Removing VA → JM makes the direct-edge answer false, while VA → VQ → JM keeps reachability true. Same edit, different relevance.” |
| 1:50–2:30 | Redraw and Edit B | “The redraw preserves every labeled edge. Edit B reverses VA → JM: one operation, two directed-edge differences. Each edit starts from the original.” |
| 2:30–3:10 | Small JSON example | “The changed-edge delta is separate from the evidence supporting each answer. These are typed algorithmic annotations.” |
| 3:10–4:00 | Index: select a small/large, cyclic/DAG or different-layout group | “The gallery spans all sizes 6–20, four layouts/styles and all three tasks/edit operations. It is a teaching selection, not an evaluation sample.” |
| 4:00–5:00 | README counts and STATUS.md | “The release has {counts['groups']:,} groups, {counts['diagram_renderings']:,} diagrams in PNG and SVG, {counts['single_qa_instances']:,} QA instances and {counts['original_variant_question_comparisons']:,} comparisons. A complete rebuild matched {repro['payload_files_compared']:,} payload hashes and manifest bytes.” |

## Questions worth inviting

- Why can deleting a path edge preserve reachability? Another path can survive.
- What proves a negative answer? A rooted, outgoing-closed reachable set excluding
  the target; an empty list alone is insufficient.
- Why does shortest-path evidence need more than a path? A witness proves an upper
  bound; feasible distance potentials certify optimality.
- Is a reversal two edits? It is one declared operation with two signed edge changes.

## State these limits explicitly

“Deterministic correctness checks passed. A {visual['stratified_groups']}-group agent visual audit was
followed by {visual['additional_high_risk_groups']} additional high-risk groups; those readability judgments are not human
validation. **No human validation or model results are available or implied.**
The known redraw/style shortcut means redraw invariance and edit sensitivity
must be reported separately. This is a research dataset release candidate.”

No inference, paid requests, expansion or benchmarking is needed during the demo.
Click any PNG for its saved full resolution. The small JSON is a presentation
projection; the linked saved sample records contain the complete annotations.
''')
    status='''# Status for the instructor demo

These are actual saved outcomes, not model scores. No checks are left running
when this presentation is handed over.

| State | Check or decision | Evidence / result |
| --- | --- | --- |
| Completed | Dataset construction | 20,000 base groups; manifest counts verified |
| Completed | Full semantic/image validation, both builds | 160,000 answers/certificates, 40,000 edits, 80,000 PNG/SVG pairs per build |
| Completed | All-variant split/isomorphism audit | No forbidden cross-split or historical overlap; allowed same-split descendants are reported |
| Completed | Inference/gold export checks | 160,000 single-image and 120,000 paired cases |
| Completed | Second complete regeneration | 200,484 payload hashes and manifest bytes matched; zero normalizations |
| Completed | Core archives | 21 archives; 200,485 safe members verified |
| Completed | Agent visual audit | 200 stratified groups plus 16 high-risk groups = 216 groups / 864 images; no unresolved defect observed at inspected scales |
| Completed | Demo selection and source integrity | 16 training groups / 64 exact saved PNGs; source hashes recorded in selection.json |
| Completed | Demo semantic checks | 128 answers, 128 certificates and 32 edits recomputed locally |
| Completed | Demo static HTML checks | 16 groups, 64 local PNG links, questions, saved answers and edit explanations |
| Completed | Demo saved-PNG agent inspection | All 64 on contact sheets; teaching original/deletion and largest original opened at native resolution; sampled readability judgment only |
| Completed | Demo regression checks | Three tests: semantic presentation, isolated rebuild/corruption rejection, Git exclusion boundary |
| Pending (tools unavailable) | Rendered HTML browser inspection | Chrome absent; in-app browser security policy blocks local file URLs; no workaround attempted |
| Completed | Initial demo Git scope inspection | No repository/index existed at initial handover; ignore behavior checked in a throwaway repository; no local files removed |
| Running | Dataset or model jobs | None |
| Pending, outside presentation scope | Author licensing / font-provenance decision | Needed before any future external publication; not a demo completion gate |
| Outside scope | Human validation | Did not occur; no reviewer wait or new review materials |
| Outside scope | Model inference, paid APIs, training, downloads, benchmarks | Not performed; no model results |

Release evidence: [validation](reports/validation.json),
[split audit](reports/split_isomorphism.json),
[exports](reports/export_boundary.json),
[regeneration](reports/reproducibility.json),
[archives](reports/archive_integrity.json),
[agent inspection](reports/agent_visual_summary.json),
[scope closeout](reports/scope_closeout.json).

Presentation checks: see `reports/demo_verification.json`,
`reports/git_preparation.json` and `reports/browser_check.json` for the final
local results. The current [repository check receipt](reports/repository_checks.json)
and [test log](reports/repository_tests.txt) accompany GitHub preparation.
Full generated outputs, credentials and caches are excluded from
ordinary Git tracking. Those receipts describe the original demo handover;
current repository preparation is recorded in `../docs/REPOSITORY_PREPARATION.md`.

Deterministic checks validate implemented graph/rendering properties. Agent
readability judgments are sampled and subjective. No human validation, novelty,
model superiority or publication readiness is established. The redraw/style
shortcut remains documented in [the actual diagnostic](reports/cross_protocol_shortcut.json).
'''
    (DEMO/'STATUS.md').write_text(status)


def verify():
    selection=read(DEMO/'selection.json');header=read(DEMO/'reports/release_manifest_summary.json');coverage=read(DEMO/'reports/coverage_summary.json');checked=Counter()
    for name,ref in selection['source_files'].items():assert sha(DEMO/name)==ref['sha256'],name
    for key,count in header['counts'].items():assert coverage[key]==count,key
    for field in ('nodes','splits','topology','connectivity','density','layout','style'):
        assert sum(coverage[field].values())==header['counts']['groups'],field
    features=coverage['feature_counts']
    assert features['relevant_edit_question_cases']+features['irrelevant_edit_question_cases']==header['counts']['groups']*4
    assert coverage['attempted']==coverage['groups']+coverage['rejected']
    for name in ('tasks.csv','operations.csv'):
        with (DEMO/'reports'/name).open() as stream:
            rows=list(csv.DictReader(stream))
        for split,count in coverage['splits'].items():
            assert sum(int(row['count']) for row in rows if row['split']==split)==count*2,(name,split)
    groups=[read(DEMO/'samples'/f'{r["group_id"]}.json') for r in selection['groups']]
    assert len(groups)==16 and len(list((DEMO/'images').glob('*.png')))==64
    tasks=Counter(q['task'] for g in groups for q in g['questions'])
    operations=Counter(v['edit']['operation'] for g in groups for v in g['variants'] if v['edit'])
    assert set(tasks)=={'direct_edge','reachability','shortest_path'}
    assert set(operations)=={'addition','deletion','reversal'}
    assert set(g['coverage']['nodes'] for g in groups)==set(range(6,21))
    assert Counter(g['coverage']['layout'] for g in groups)==dict.fromkeys(('grid','radial','concentric','staggered_layers'),4)
    assert Counter(g['coverage']['style'] for g in groups)==dict.fromkeys(range(4),4)
    for g in groups:checked.update(verify_group(g));assert g['split']=='train'
    assert checked=={'groups':16,'answers':128,'certificates':128,'edits':32}
    example=read(DEMO/'annotation_example.json');hero=groups[0]
    assert hero['id']==example['group_id']==HERO
    for q,e in zip(hero['questions'],example['questions']):
        assert e['original_answer']==hero['variants'][0]['answers'][q['id']] and type(e['original_answer']) is type(hero['variants'][0]['answers'][q['id']])
        assert e['edited_answer']==hero['variants'][2]['answers'][q['id']] and e['edit_relevant']==hero['variants'][2]['relevance'][q['id']]
    assert [q['edit_relevant'] for q in example['questions']]==[False,True]
    assert hero['variants'][2]['certificates'][hero['questions'][0]['id']]['path']==['VA','VQ','JM']
    local=DATA.exists()
    if local:
        assert sha(DATA/'manifest.json')==header['manifest_sha256']
        actual=read(DATA/'manifest.json');assert actual['counts']==header['counts']
        for ref in selection['source_files'].values():
            if 'release_path' in ref:assert actual['files'][ref['release_path']]==ref['sha256']
    for name in ['validation.json','split_isomorphism.json','export_boundary.json','reproducibility.json','archive_integrity.json']:assert read(DEMO/'reports'/name)['status']=='passed'
    visual=read(DEMO/'reports/agent_visual_summary.json');assert visual['human_reviews']==0 and visual['distinct_groups']==216
    assert read(DEMO/'reports/scope_closeout.json')['human_validation_occurred'] is False
    text=(DEMO/'gallery.html').read_text();assert text.count('<article id=')==16 and text.count('<img ')==64
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key not in ('src','href') or value.startswith('#'):continue
                assert not value.startswith(('http:','https:','//')),value
                assert (DEMO/value).is_file(),value
    Links().feed(text)
    result={'status':'passed','group_count':16,'png_count':64,'independent_demo_checks':dict(checked),'source_payload_copies_sha256_checked':len(selection['source_files']),'local_full_release_manifest_checked':local,'source_manifest_sha256':header['manifest_sha256'],'no_new_diagrams':True,'no_inference_or_paid_api':True,'human_validation':False,'links':'all local gallery links exist','demo_sizes':dict(sorted(Counter(g['coverage']['nodes'] for g in groups).items())),'demo_layouts':dict(Counter(g['coverage']['layout'] for g in groups)),'demo_styles':dict(Counter(g['coverage']['style'] for g in groups))}
    result['demo_tasks']=dict(tasks);result['demo_edit_operations']=dict(operations)
    for key in ('topology','connectivity','density_bin'):
        result['demo_'+key]=dict(Counter(g['coverage'][key] for g in groups))
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['extract','build','verify']);args=parser.parse_args()
    if args.action=='extract':extract()
    elif args.action=='build':render()
    else:verify()
