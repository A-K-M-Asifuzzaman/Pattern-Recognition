"""Streaming opaque-order public/gold exports and machine-readable schemas."""
import json
import sqlite3
from pathlib import Path

from .build import canonical, records, write
from .logic import question_text
from .sample import opaque

INSTRUCTIONS='An arrow points from tail to arrowhead. Labels are arbitrary identifiers. Crossings are not junctions without an explicit node. Follow directed edges; path lengths count edges. No executable flowchart semantics apply.'


def cases(group,key):
    original=group['variants'][0]
    for q in group['questions']:
        common={'group_id':group['id'],'split':group['split'],'question':question_text(q),
                'instructions':INSTRUCTIONS,'answer_format':"nonnegative integer or 'unreachable'" if q['task']=='shortest_path' else 'boolean'}
        for v in group['variants']:
            ident=opaque(key,'rc1-case',group['id'],q['id'],v['id'],'single')
            public={'id':ident,**common,'image':v['assets']['png']}
            gold={'id':ident,'group_id':group['id'],'question_id':q['id'],'variant_id':v['id'],'split':group['split'],
                  'answer':v['answers'][q['id']],'certificate':v['certificates'][q['id']]}
            yield 'single',public,gold
        for v in group['variants'][1:]:
            ident=opaque(key,'rc1-case',group['id'],q['id'],v['id'],'paired')
            public={'id':ident,**common,'images':[original['assets']['png'],v['assets']['png']],
                    'pair_instructions':'Answer independently for both ordered images. Identify added/deleted directed edges. Supply separate answer evidence for each image.'}
            gold={'id':ident,'group_id':group['id'],'question_id':q['id'],'variant_ids':[original['id'],v['id']],
                  'split':group['split'],'answers':[original['answers'][q['id']],v['answers'][q['id']]],
                  'certificates':[original['certificates'][q['id']],v['certificates'][q['id']]],
                  'pair_kind':'redraw' if v['role']=='redraw' else 'relevant_edit' if v['relevance'][q['id']] else 'irrelevant_edit',
                  'delta':{k:v['edit'][k] if v['edit'] else [] for k in ('added','deleted')}}
            yield 'paired',public,gold


def export(root):
    temporary=root/'exports.tmp.sqlite';assert not temporary.exists()
    key=json.loads((root/'gold/id_key.json').read_text())['key_hex']
    db=sqlite3.connect(temporary);db.execute('CREATE TABLE cases (id TEXT PRIMARY KEY, kind TEXT, public TEXT, gold TEXT)')
    counts={'single':0,'paired':0}
    for group in records(root):
        for kind,public,gold in cases(group,key):
            db.execute('INSERT INTO cases VALUES (?,?,?,?)',(public['id'],kind,canonical(public),canonical(gold)));counts[kind]+=1
    db.commit()
    for kind in counts:
        with (root/f'inference/{kind}.jsonl').open('w') as p,(root/f'gold/{kind}.jsonl').open('w') as g:
            for public,gold in db.execute('SELECT public,gold FROM cases WHERE kind=? ORDER BY id',(kind,)):
                p.write(public);g.write(gold)
    db.close();temporary.unlink()
    assert counts=={'single':8*len(list((root/'gold/records').glob('*.json'))),'paired':6*len(list((root/'gold/records').glob('*.json')))}
    (root/'inference/README.md').write_text('''# Image-only input boundary

Use single.jsonl and paired.jsonl as separate protocols. A single-image case
receives exactly its current PNG and question/instructions. A paired case receives
exactly its ordered two PNGs and question/instructions. Do not combine rows or
protocols as context. Case/group IDs, split and filenames are local routing data;
future image-only workers must receive decoded PNGs and allowlisted text only.
Gold, geometry, source SVG, font files, manifests, seed, reports and review keys
are evaluator material. SVG is provided for viewing/export, not model payloads.

All labels are arbitrary. Direction is tail to arrowhead. Crossings are not
junctions unless an explicit node exists; this release rejects edge crossings.
Reachability/direct-edge answers are booleans. Shortest paths are nonnegative
edge counts, or the literal string "unreachable". Negative reachability requires
a complete reachable-set certificate. A finite shortest path uses a real path
and feasible all-node distance potentials. Any valid alternative path is accepted.
Changed edges and answer-supporting evidence are distinct annotations.

This release contains no model predictions or human reviews. No inference is
authorized. Phase 2B remains cancelled. Public chronology is neutralized at final
packaging, but consumers should not supply filesystem metadata to future models.
''')
    return counts


def schemas(root):
    folder=root/'schemas';folder.mkdir()
    ident={'type':'string','pattern':'^[0-9a-f]{24}$'};label={'type':'string','pattern':'^[A-Z]{2}$'}
    edge={'type':'array','prefixItems':[label,label],'minItems':2,'maxItems':2}
    answer={'oneOf':[{'type':'boolean'},{'type':'integer','minimum':0},{'const':'unreachable'}]}
    cert={'type':'object','required':['kind'],'properties':{'kind':{'enum':['edge_claim','path','reachable_set','shortest_path']},
          'source':label,'target':label,'present':{'type':'boolean'},'path':{'type':'array','items':label,'minItems':2,'uniqueItems':True},
          'nodes':{'type':'array','items':label,'uniqueItems':True},'distances':{'type':'object','additionalProperties':{'type':['integer','null'],'minimum':0}}},'additionalProperties':False}
    graph={'type':'object','required':['nodes','edges'],'additionalProperties':False,'properties':{
        'nodes':{'type':'array','minItems':6,'maxItems':20,'uniqueItems':True,'items':label},
        'edges':{'type':'array','items':edge,'uniqueItems':True}}}
    q={'type':'object','required':['id','task','source','target'],'additionalProperties':False,
       'properties':{'id':ident,'task':{'enum':['reachability','shortest_path','direct_edge']},'source':label,'target':label}}
    variant={'type':'object','required':['id','role','graph','scene','answers','certificates','relevance','edit','geometry_checks','assets','asset_hashes'],
             'properties':{'id':ident,'role':{'enum':['original','redraw','edited']},'graph':graph,'scene':{'type':'object'},
                           'answers':{'type':'object','additionalProperties':answer},'certificates':{'type':'object','additionalProperties':cert},
                           'relevance':{'type':'object','additionalProperties':{'type':'boolean'}},'edit':{'type':['object','null']},
                           'geometry_checks':{'type':'object'},'assets':{'type':'object'},'asset_hashes':{'type':'object'},
                           'semantic_changed_edges':{'type':'object'},'answer_change_evidence':{'type':'object'},'pixel_change':{'type':'object'}},'additionalProperties':False}
    group={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'TopoDelta-QA RC group',
           'type':'object','required':['id','slot','trial','seed','split','generator_version','intent','questions','variants','coverage'],
           'properties':{'id':ident,'slot':{'type':'integer','minimum':0},'trial':{'type':'integer','minimum':0},'seed':{'type':'integer'},
                         'split':{'enum':['train','validation','test']},'generator_version':{'const':'0.3.0-rc1'},'intent':{'type':'object'},
                         'questions':{'type':'array','minItems':2,'maxItems':2,'items':q},'variants':{'type':'array','minItems':4,'maxItems':4,'items':variant},'coverage':{'type':'object'}},'additionalProperties':False}
    write(folder/'group.schema.json',group)
    for kind in ('single','paired'):
        props={'id':ident,'group_id':ident,'split':{'enum':['train','validation','test']},'question':{'type':'string'},
               'instructions':{'type':'string'},'answer_format':{'type':'string'}}
        path={'type':'string','pattern':'^images/[0-9a-f]{24}\\.png$'}
        if kind=='single':props['image']=path
        else:props.update(images={'type':'array','items':path,'minItems':2,'maxItems':2},pair_instructions={'type':'string'})
        write(folder/f'{kind}_inference.schema.json',{'$schema':group['$schema'],'type':'object','required':list(props),'properties':props,'additionalProperties':False})
        gold_props={'id':ident,'group_id':ident,'question_id':ident,'split':{'enum':['train','validation','test']}}
        if kind=='single':gold_props.update(variant_id=ident,answer=answer,certificate=cert)
        else:gold_props.update(variant_ids={'type':'array','items':ident,'minItems':2,'maxItems':2},
             answers={'type':'array','items':answer,'minItems':2,'maxItems':2},certificates={'type':'array','items':cert,'minItems':2,'maxItems':2},
             pair_kind={'enum':['redraw','relevant_edit','irrelevant_edit']},delta={'type':'object','required':['added','deleted'],
             'properties':{k:{'type':'array','items':edge,'uniqueItems':True} for k in ('added','deleted')},'additionalProperties':False})
        write(folder/f'{kind}_gold.schema.json',{'$schema':group['$schema'],'type':'object','required':list(gold_props),'properties':gold_props,'additionalProperties':False})
    write(folder/'annotation_definitions.schema.json',{'$schema':group['$schema'],'$defs':{'answer':answer,'certificate':cert,'directed_edge':edge,'graph':graph},
          'description':'Field shapes supplement independent executable checks: endpoints, exact deltas, certificate closure/potentials, geometry and relevance cannot be established by JSON Schema alone.'})
