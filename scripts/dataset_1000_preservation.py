"""Assert frozen artifacts and retained assets; reconstruct attempted base sampling."""
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from PIL import Image

from topodelta_qa.dataset import base_graph, design_schedule, oid, read_jsonl
from topodelta_qa.schema import Config, Graph, OPERATIONS, TASKS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path('outputs/dataset_build_1000')
    dataset = Path('outputs/topodelta_qa_v0.2.0')
    parent = Path('outputs/pilot_v0.1.1')
    manifest = json.loads((dataset/'manifest.json').read_text())
    frozen = {}
    for name in ('pilot', 'pilot_v0.1.1', 'phase1b', 'phase2a', 'phase2b'):
        root = Path('outputs')/name
        inventory = json.loads((root/'manifest.json').read_text())['files']
        for path, expected in inventory.items():
            assert sha(root/path) == expected, (name, path)
        frozen[name] = {'files_checked': len(inventory), 'manifest_sha256': sha(root/'manifest.json')}
    assert frozen['pilot_v0.1.1']['manifest_sha256'] == 'd781309f095aa8f02b6f0ebb9fb33910075171b094c25ee1faadcbc98834d7d4'
    groups = read_jsonl(dataset/'gold/groups.jsonl')
    old = read_jsonl(parent/'gold/groups.jsonl')
    assert len(groups) == 1000 and len(old) == 120 and groups[:120] == old
    assets = masks = 0
    for group in old:
        for variant in group['variants']:
            for path in variant['assets'].values():
                assert sha(parent/'inference'/path) == sha(dataset/'inference'/path)
                assets += 1
            if variant['edit']:
                path = variant['pixel_diff']['path']
                assert sha(parent/path) == sha(dataset/path)
                masks += 1
    assert assets == 960 and masks == 240
    public_assets = list((dataset/'inference/images').iterdir())
    assert len(public_assets) == 8000 and all(p.stat().st_mtime == 0 for p in public_assets)
    pngs = [p for p in public_assets if p.suffix == '.png']
    assert len(pngs) == 4000
    for path in pngs:
        with Image.open(path) as image:
            assert not image.info, path
    snapshot = Path('outputs/phase2b_cancellation')
    cancellation = json.loads((snapshot/'CANCELLATION.json').read_text())
    for path, expected in cancellation['source_snapshot_sha256'].items():
        assert sha(snapshot/'source_before_dataset_only'/path) == expected
    preservation = {'status': 'passed', 'frozen_inventories': frozen,
                    'retained_groups_exact': 120, 'retained_png_svg_files_exact': assets,
                    'retained_pixel_masks_exact': masks, 'prechange_source_snapshot_files': 6}
    preservation['public_asset_mtimes_zero'] = len(public_assets)
    preservation['png_headers_without_metadata'] = len(pngs)
    (out/'preservation.json').write_text(json.dumps(preservation, indent=2, sort_keys=True)+'\n')

    accepted = {g['attempt']: g for g in groups}
    rejected = {r['attempt']: r['reason'] for r in read_jsonl(dataset/'reports/rejections.jsonl')}
    attempted = manifest['counts']['attempted']
    assert len(accepted) + len(rejected) == attempted and not accepted.keys() & rejected.keys()
    config = Config(**json.loads((dataset/'config.json').read_text()))
    parent_config = Config(**json.loads((parent/'config.json').read_text()))
    inherited_attempts = manifest['lineage']['inherited_attempts']
    records = []; accepted_index = 0
    for attempt in range(attempted):
        if attempt == inherited_attempts:
            accepted_index = 0
        schedule = parent_config if attempt < inherited_attempts else replace(config, groups=880)
        graph, _, _ = base_graph(random.Random(int(oid(config.seed, attempt), 16)), schedule)
        op = design_schedule(schedule, 'operations')[accepted_index]
        task = design_schedule(schedule, 'tasks')[accepted_index]
        passed = attempt in accepted
        if passed:
            assert graph == Graph.parse(accepted[attempt]['variants'][0]['graph'])
        records.append({'attempt': attempt, 'cohort': 'retained' if attempt < inherited_attempts else 'new',
                        'accepted': int(passed), 'reason': 'accepted' if passed else rejected[attempt],
                        'nodes': len(graph.nodes), 'base_edges': len(graph.edges),
                        'scheduled_operations': '+'.join(OPERATIONS[(op+i)%3] for i in range(2)),
                        'scheduled_tasks': '+'.join(TASKS[(task+i)%3] for i in range(2))})
        accepted_index += passed
    def table(path, records):
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    table(out/'attempted_base_samples.csv', records)
    summary = []
    for dimension in ('cohort', 'nodes', 'base_edges', 'scheduled_operations', 'scheduled_tasks'):
        buckets = defaultdict(list)
        for record in records:
            buckets[record[dimension]].append(record)
        for value, values in sorted(buckets.items(), key=lambda pair: str(pair[0])):
            count = sum(r['accepted'] for r in values)
            summary.append({'dimension': dimension, 'value': value, 'attempted': len(values), 'accepted': count,
                            'rejected': len(values)-count, 'acceptance_rate': count/len(values),
                            'attempted_fraction': len(values)/attempted, 'accepted_fraction': count/1000})
    table(out/'acceptance_distribution.csv', summary)
    reasons = Counter(r['reason'] for r in records if not r['accepted'])
    assert dict(reasons) == manifest['counts']['rejection_reasons']
    print(json.dumps({'preservation': preservation, 'attempts_reconstructed': len(records),
                      'rejection_reasons': dict(reasons)}, indent=2))


if __name__ == '__main__':
    main()
