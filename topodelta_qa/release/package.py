"""Deterministic preparation, complete manifests, local chunk archives and replay comparison."""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import tarfile
from pathlib import Path

from PIL import ImageFont, features

from .build import canonical, records, write
from .drawing import RENDERER
from .exports import export, schemas
from .reports import report
from .review import human_packet


def file_sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def environment():
    return {'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),
            'dependencies':{n:importlib.metadata.version(n) for n in ('Pillow','networkx','PyYAML','jsonschema')},
            'freetype':features.version('freetype2'),'zlib':features.version('zlib'),
            'font_sha256':hashlib.sha256(ImageFont.load_default(size=26).path.getvalue()).hexdigest(),
            'font':'Pillow bundled subset Aileron Regular','renderer':RENDERER}


def font_names(blob):
    result={}
    for i in range(struct.unpack('>H',blob[4:6])[0]):
        tag,_,offset,_=struct.unpack('>4sIII',blob[12+i*16:28+i*16])
        if tag!=b'name':continue
        _,count,base=struct.unpack('>HHH',blob[offset:offset+6])
        for j in range(count):
            system,_,_,name,length,start=struct.unpack('>HHHHHH',blob[offset+6+j*12:offset+18+j*12])
            if name not in (0,1,2,8,9,11,13,14):continue
            data=blob[offset+base+start:offset+base+start+length]
            result[str(name)]=data.decode('utf-16-be' if system in (0,3) else 'mac_roman')
    return result


def provenance(root):
    work=Path.cwd();folder=root/'reproduction';folder.mkdir()
    source=folder/'source'
    for name in ('topodelta_qa/__init__.py','topodelta_qa/schema.py','topodelta_qa/render.py'):
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(work/name,target)
    for path in sorted((work/'topodelta_qa/release').glob('*.py')):
        target=source/'topodelta_qa/release'/path.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    for name in ('requirements.txt','.python-version','configs/release_candidate.json','tests/test_release_candidate.py','tests/test_release_packaging.py'):
        target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(work/name,target)
    history=folder/'historical_inputs';history.mkdir()
    shutil.copyfile(root/'gold/historical_blacklist.jsonl',history/'groups.jsonl')
    shutil.copyfile(work/'outputs/topodelta_qa_v0.2.0/manifest.json',history/'manifest.json')
    historical=json.loads((history/'manifest.json').read_text())
    assert file_sha(history/'groups.jsonl')==historical['files']['gold/groups.jsonl']
    write(folder/'environment.json',environment())
    licenses=root/'licenses';licenses.mkdir()
    inventory=[]
    for name in ('Pillow','networkx','PyYAML','jsonschema'):
        dist=importlib.metadata.distribution(name)
        candidates=[p for p in dist.files if '/licenses/' in str(p) and ('license' in str(p).lower() or 'copying' in str(p).lower())]
        assert candidates,name
        path=candidates[0];target=licenses/(name+'_LICENSE.txt');shutil.copyfile(dist.locate_file(path),target)
        inventory.append({'component':name,'version':dist.version,'source':'already installed distribution license file',
                          'license_text':target.relative_to(root).as_posix(),'sha256':file_sha(target),'redistributed':'license notice only; library itself is not bundled'})
    names=font_names((root/'inference/fonts/Aileron-Regular.ttf').read_bytes())
    write(licenses/'font_embedded_names.json',names)
    inventory += [{'component':'Aileron Regular subset','creator':names.get('9'),'embedded_copyright':names.get('0'),
                   'source':'Pillow ImageFont.load_default, bundled bytes; no font download',
                   'redistributed':'one TTF asset shared by SVGs',
                   'status':'Embedded font says No Rights Reserved.; standalone license terms were not retrieved. Author should confirm font redistribution provenance before external distribution.'},
                  {'component':'TopoDelta-QA generated diagrams/annotations and project code','status':'No license granted by this build. Dataset license proposal awaits author review.'},
                  {'component':'CPython','version':platform.python_version(),'redistributed':False,'license':'Python Software Foundation runtime; interpreter not bundled'}]
    write(licenses/'inventory.json',inventory)
    (licenses/'PROPOSED_DATASET_LICENSE.md').write_text('''# Proposed dataset license — author review required

Propose Creative Commons Attribution 4.0 International (CC BY 4.0) for the
synthetic diagrams and annotations, after the authors confirm ownership,
attribution wording and third-party font redistribution. This is a proposal,
not a grant or an approved license. The project code needs a separate explicit
author decision. Bundled notices retain their own terms. No external publication
or distribution has been performed. The font's embedded metadata is preserved
verbatim; the build does not infer complete legal terms from that short notice.
''')
    (folder/'REPRODUCE.md').write_text('''# Complete local reproduction

Use the recorded interpreter/dependency/font/FreeType/zlib environment, already
installed locally. No model or network dependency is needed. Work in a fresh
directory. Copy source/topodelta_qa here, configs/release_candidate.json into
configs/, and the release's evaluator-only gold/id_key.json into
configs/evaluator_id_key.json. Copy historical_inputs/groups.jsonl into
outputs/topodelta_qa_v0.2.0/gold/groups.jsonl and historical_inputs/manifest.json
into outputs/topodelta_qa_v0.2.0/manifest.json. Those historical files supply only
the frozen topology blacklist; historical PNGs are not needed for reproduction.

python3 -m topodelta_qa.release.build --output outputs/repeat
python3 -m topodelta_qa.release.package prepare --dataset outputs/repeat
python3 -m topodelta_qa.release.verify --dataset outputs/repeat --output outputs/repeat/reports --expected 20000
python3 -m topodelta_qa.release.boundary_cli --dataset outputs/repeat
python3 -m topodelta_qa.release.package seal --dataset outputs/repeat
python3 -m topodelta_qa.release.package compare --dataset ORIGINAL_RELEASE --other outputs/repeat --output comparison.json

The existing build can resume with --resume only while its manifest is absent
and generator/config hashes match. Runtime and wall-clock logs live outside the
deterministic release. Do not edit records to repair a failed byte comparison.
''')


def prepare(root):
    assert not (root/'manifest.json').exists(),'Sealed release cannot be overwritten'
    metadata=json.loads((root/'gold/build.json').read_text());count=len(list((root/'gold/records').glob('*.json')))
    assert count==metadata['config']['groups'],'Only a complete generation may be packaged'
    for path in ('inference/single.jsonl','gold/single.jsonl','schemas','reproduction','licenses','review/packet'):
        assert not (root/path).exists(),f'Preparation already started: preserve partial metadata before retrying: {path}'
    print('Exporting public and gold JSONL',flush=True);export(root);schemas(root)
    print('Computing coverage and acceptance tables',flush=True);result=report(root)
    print('Preparing blank human-review packet and separate key',flush=True);human_packet(root,root/'review/packet')
    provenance(root);return result


def neutralize_assets(root):
    marker=root/'reports/asset_metadata.json'
    if marker.exists():return
    original=root/'inference/images';ordered=root/'inference/images_ordered';assert not ordered.exists()
    ordered.mkdir()
    assert shutil.disk_usage(root).free>25*1024**3+sum(p.stat().st_size for p in original.iterdir())
    count=0
    for path in sorted(original.iterdir()):
        target=ordered/path.name;shutil.copyfile(path,target);os.utime(target,(0,0))
        assert file_sha(path)==file_sha(target);count+=1
    staging=root/'inference/images_generation_order';assert not staging.exists()
    original.rename(staging);ordered.rename(original);shutil.rmtree(staging)
    write(marker,{'files':count,'write_order':'globally sorted opaque filenames','mtime_epoch':0,
                 'reason':'Prevent per-group creation chronology from revealing original/redraw/edit roles. Future workers must still exclude all filesystem metadata.'})


def seal(root):
    assert not (root/'manifest.json').exists(),'Refusing to replace a sealed manifest'
    summary=json.loads((root/'reports/coverage_summary.json').read_text())
    for name in ('validation','split_isomorphism','export_boundary'):
        assert json.loads((root/f'reports/{name}.json').read_text())['status']=='passed',name
    neutralize_assets(root)
    (root/'DATASET_CARD.md').write_text(f'''# TopoDelta-QA research dataset release candidate

Version 0.3.0-rc1. Local deterministic synthetic graphs, algorithmic annotations.
{summary['groups']:,} independently seeded base graph groups, {summary['diagram_renderings']:,}
diagram renderings exported in both PNG and SVG ({summary['png_files']+summary['svg_files']:,} asset files),
{summary['single_qa_instances']:,} single-image QA instances and
{summary['original_variant_question_comparisons']:,} original–variant–question comparisons.
Each group has two questions and four related images; images/questions within a
group are not independent observations. Base topologies are distinct up to exact
isomorphism. Same-split descendant overlap is counted separately in the split audit.

## Coverage and selection

Node sizes 6–20; quotas 4,000 / 4,000 / 6,000 / 6,000 in bands 6–8 / 9–12 /
13–16 / 17–20. Splits: {json.dumps(summary['splits'],sort_keys=True)}.
No old group was moved into test. Historical graph variants are blacklisted
across every split. No historical group is retained: its 800-pixel canvas and
22-pixel text fail the new minimum 1152-pixel canvas and 26-pixel text requirements.
Old releases remain unchanged. No pristine layout/style holdout is claimed.

Four spatial families: grid, staggered layers, radial hub/ring, concentric rings.
Four neutral style families: plain box, gray rounded box, heavy frame, double frame.
Style streams are independent of semantic sampling; compatibility conditions
constrain layout/topology/density. See gold/build.json and reports/unmet_coverage_cells.csv.
This is not a fully balanced Cartesian product, uniform graph distribution or
natural diagram sample. Size quotas remove size-count imbalance while rejection
still biases topology and question choices within each cell.

Density bins use m/n: sparse [0.6,1.25), moderate [1.25,1.75]. Directed density
m/[n(n−1)] is also recorded. Difficulty is a structural proxy: maximum finite
directed shortest path 0–2 / 3–4 / 5–19, not measured human/model difficulty.
Alternative-route coverage means a direct edge also has another directed route
of at most four edges. Bottleneck coverage records weak undirected bridges.
Disconnected graphs contain an isolated distractor; irrelevant questions/edits
are nevertheless selected within the same original connected region.

## Annotation and evidence

Questions cover directed reachability, shortest-path edge count and direct-edge
presence. At least one identical edit changes exactly one of the two answers in
every group. Two edits apply independently to the original. One reversal records
one operation and two signed directed-edge differences. Relevance is recomputed
from answers. Geometry changes only for the declared edited edge(s).

NetworkX primary annotations are independently checked by raw JSON Floyd–Warshall
and structural certificates. Paths need not match a particular stored path.
Negative reachability/unreachable shortest paths require complete rooted closed
reachable sets. Finite shortest paths require a real path and matching feasible
distance potentials. Changed edges, answer evidence and answer-change evidence
are stored separately. All saved PNG/SVG primitives and pixel footprints were checked.

## Rendering and review limits

Canvases adapt to geometry. Text is 26 pixels and arrowheads 22 by 16 pixels at
native resolution. Native PNG lines are not supersampled; enlargement can show
stair steps. Nodes/labels are monochrome; color carries no graph meaning.
Crossings are non-junctions without explicit nodes and are rejected here.
Reciprocal and parallel connections are excluded. Layout diversity remains
template-based, straight, planar and synthetic. Redraws rotate the same embedding
and independently change neutral style; they do not change embedding family.

Agent visual audit records are supplied separately. They are not human validation.
The human packet contains 400 stratified groups plus all accepted groups flagged
by the documented clearance rule, blank review forms and a separate gold answer key.
No human reviews, adjudications or agreement measurements have occurred.

## Isolation, reproducibility and licensing

inference/ JSONLs reference PNG only and contain no answers, certificates, edit
labels, roles, graph structures or relevance. SVG source visibly encodes geometry
and must be excluded from future image-only workers. Gold, source, reports, IDs,
splits, timestamps and directory joins are also evaluator-only context. Do not
treat public group linkage as permission to combine single-image cases.

See reproduction/REPRODUCE.md, environment.json and SHA-256 manifest.json. Runtime
logs/timestamps stay outside deterministic content. Separate generation comparison
and archive-integrity evidence accompanies the release candidate.
See licenses/inventory.json and PROPOSED_DATASET_LICENSE.md: license adoption and
font redistribution provenance remain for author review. No license is granted
by this build. No external publication has occurred.

No paid API, model inference, training, model download or learned topology-delta
verifier was used. Size and automated checks do not establish novelty, superiority,
human readability/agreement or publication readiness.
''')
    files={p.relative_to(root).as_posix():file_sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
    assert not any(name.endswith(('.tmp','.sqlite')) for name in files)
    manifest={'dataset':'TopoDelta-QA','version':'0.3.0-rc1','status':'research dataset release candidate',
              'counts':{k:summary[k] for k in ('groups','diagram_renderings','png_files','svg_files','single_qa_instances','original_variant_question_comparisons')},
              'environment':environment(),'files':files,'human_validation':False,'model_inference':False,'external_publication':False}
    write(root/'manifest.json',manifest);return manifest


def verify_manifest(root):
    m=json.loads((root/'manifest.json').read_text());paths=list(root.rglob('*'));assert not any(p.is_symlink() for p in paths),'Symlinks are not release payloads'
    actual={p.relative_to(root).as_posix() for p in paths if p.is_file()}-{'manifest.json'}
    assert actual==set(m['files'])
    for name,digest in m['files'].items():assert file_sha(root/name)==digest,name
    return m


def compare(root,other,out):
    a=verify_manifest(root);b=verify_manifest(other)
    differences=[p for p in sorted(set(a['files'])|set(b['files'])) if a['files'].get(p)!=b['files'].get(p)]
    result={'status':'passed' if not differences and a==b else 'failed','first_manifest_sha256':file_sha(root/'manifest.json'),
            'second_manifest_sha256':file_sha(other/'manifest.json'),'payload_files_compared':len(a['files']),
            'canonical_manifests_equal':a==b,'manifest_bytes_equal':(root/'manifest.json').read_bytes()==(other/'manifest.json').read_bytes(),
            'differing_files':differences,'normalizations_applied':[],'complete_generations':2,
            'image_hashes_compared':sum(p.startswith('inference/images/') for p in a['files']),
            'annotation_records_compared':sum(p.startswith('gold/records/') for p in a['files'])}
    write(out,result);assert result['status']=='passed',result;return result


def archive(root,out):
    manifest=verify_manifest(root);out.mkdir(parents=True,exist_ok=False)
    members=set(manifest['files'])|{'manifest.json'};chunks={};assigned=set()
    for g in records(root):
        batch=g['slot']//1000;names={f'gold/records/{g["slot"]:05d}.json',f'gold/attempts/{g["slot"]:05d}.json'}
        names|={'inference/'+p for v in g['variants'] for p in v['assets'].values()}
        chunks.setdefault(f'groups_{batch:02d}.tar.gz',set()).update(names);assigned|=names
    chunks={'metadata_and_exports.tar.gz':members-assigned,**chunks};inventory=[]
    for filename,paths in chunks.items():
        assert shutil.disk_usage(out).free>25*1024**3
        path=out/filename
        with path.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=1,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.USTAR_FORMAT) as tar:
                for name in sorted(paths):
                    source=root/name;info=tarfile.TarInfo(name);info.size=source.stat().st_size;info.mode=0o644;info.mtime=info.uid=info.gid=0
                    with source.open('rb') as data:tar.addfile(info,data)
        inventory.append({'file':filename,'sha256':file_sha(path),'bytes':path.stat().st_size,'members':len(paths)})
        print(f'Archived {filename}: {len(paths)} files',flush=True)
    expected={**manifest['files'],'manifest.json':file_sha(root/'manifest.json')};seen=set()
    for item in inventory:
        assert file_sha(out/item['file'])==item['sha256']
        with tarfile.open(out/item['file'],'r|gz') as tar:
            count=0
            for member in tar:
                assert member.isfile() and member.name in expected and member.name not in seen
                assert not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
                stream=tar.extractfile(member);assert hashlib.file_digest(stream,'sha256').hexdigest()==expected[member.name]
                seen.add(member.name);count+=1
            assert count==item['members']
    assert seen==set(expected)
    result={'status':'passed','archives':inventory,'total_members_checked':len(seen),'every_archived_payload_sha256_verified':True,
            'safe_relative_file_members_only':True,'archive_bytes':sum(x['bytes'] for x in inventory)}
    write(out/'ARCHIVES.json',result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','seal','archives','compare','verify-manifest'))
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--other',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.action=='prepare':result=prepare(a.dataset)
    elif a.action=='seal':result=seal(a.dataset);result={k:v for k,v in result.items() if k!='files'}
    elif a.action=='archives':result=archive(a.dataset,a.output)
    elif a.action=='compare':result=compare(a.dataset,a.other,a.output)
    else:result=verify_manifest(a.dataset);result={'status':'passed','files':len(result['files'])}
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
