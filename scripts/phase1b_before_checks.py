"""Reproduce confirmed defects using only the snapshotted pre-fix verifier."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

source=Path('outputs/versions/phase1-v0.1.0/source').resolve();sys.path.insert(0,str(source))
import topodelta_qa.verify as legacy
assert Path(legacy.__file__).resolve().is_relative_to(source)
root=Path('outputs/versions/phase1-v0.1.0/dataset')
group=json.loads((root/'gold/groups.jsonl').read_text().splitlines()[0])
results=[]
for field in ['operation_count','directed_set_difference_count']:
    for malformed in [True,1.0]:
        altered=copy.deepcopy(group)
        v=next(v for v in altered['variants'] if v['edit'] and v['edit'][field]==1)
        v['edit'][field]=malformed
        legacy.validate_group(altered)
        results.append({'field':field,'malformed_value':malformed,'pre_fix_result':'accepted malformed integer field'})
with patch.object(legacy,'source_hashes',return_value={'unrelated_source_edit.py':'changed'}):
    try:legacy.validate_dataset(root)
    except ValueError as exc:message=str(exc)
    else:raise AssertionError('Expected old source gate to reject historical source mismatch')
report={'source_verifier':str(Path(legacy.__file__).relative_to(Path.cwd())), 'integer_count_defect':results,
        'source_gate_defect':{'intact_historical_dataset_rejected':True,'message':message},
        'note':'Deliberately malformed copies only. No dataset or snapshot file was altered.'}
Path('outputs/phase1b/pre_fix_confirmations.json').write_text(json.dumps(report,indent=2)+'\n')
print('Confirmed both defects against preserved pre-fix verifier')
