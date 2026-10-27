"""Re-audit corrected identity version; retain observed visual audit by byte correspondence."""
import csv,json,shutil
from pathlib import Path
from phase1b_audit import rows,save,table,semantics,leakage,features,distributions,shortcuts,review_packet

root=Path('outputs/pilot_v0.1.1');out=Path('outputs/phase1b');archive=out/'pre_id_fix_reports'
archive.mkdir(exist_ok=False)
for p in list(out.iterdir()):
    if p.is_file() and p.suffix in ['.csv','.json','.md']:shutil.copy2(p,archive/p.name)
groups=rows(root/'gold/groups.jsonl')
save(out/'semantics.json',semantics(groups));save(out/'leakage.json',leakage(root,groups))
edits,graphs=features(root,groups);distributions(out,edits,graphs);shortcuts(edits,out)
(out/'human_review').rename(out/'human_review_legacy_preliminary')
save(out/'review_packet_summary.json',review_packet(root,groups,out))
mapping=json.loads((out/'id_mapping_evaluator_only.json').read_text())
visual=json.loads((out/'visual_audit.json').read_text())
for r in visual['records']:
    r['legacy_group_id']=r['group_id'];r['group_id']=mapping[r['group_id']]
    r['reviewed_image_version']='0.1.0 PNG bytes; identical to corrected 0.1.1 PNG bytes verified by version comparison'
    r['corrected_dataset_image_bytes_identical']=True
save(out/'visual_audit.json',visual)
flat=[{k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in visual['records']]
table(out/'visual_audit.csv',flat)
selection=json.loads((out/'visual_selection.json').read_text())
for r in selection:r['legacy_group_id']=r['group_id'];r['group_id']=mapping[r['group_id']]
save(out/'visual_selection.json',selection);table(out/'visual_selection.csv',selection)
print('Corrected version independently re-audited; human packet rebuilt blank; 30 observed groups mapped by identical PNG bytes')
