# Reproduction and local availability

The Git repository contains a self-contained instructor sample bundle, source,
tests, schemas and selected actual reports. It does not contain the complete
generated releases or a public download link. Full-release inputs remain on the
author's machine under `outputs/`. No model or paid API is needed for these steps.

## Environment

The recorded build used CPython 3.12.6, NetworkX 3.6.1, Pillow 12.3.0, PyYAML
6.0.3 and jsonschema 4.26.0. Use `.python-version`, `requirements.txt` and
`requirements-dev.txt`; the latter includes runtime and test requirements.
The exact font, FreeType, zlib and platform fingerprint is recorded in
[`environment.json`](../instructor_demo/reports/environment.json). Dependency
installation is separate from these offline checks; no installation or download
is performed by the commands below.

## Self-contained instructor demo

From the repository root, with the recorded dependencies already installed:

```sh
PYTHONPATH=. python3 scripts/instructor_demo.py build
PYTHONPATH=. python3 scripts/instructor_demo.py verify
python3 -m unittest discover -s tests -p 'test_instructor_demo.py' -v
python3 -m topodelta_qa --help
python3 -m topodelta_qa.release.build --help
```

Open `instructor_demo/gallery.html` in a local browser. It uses relative paths
and no server, JavaScript or external assets. The `build` action formats existing
saved samples; it does not generate new graphs. The extraction action requires
the full local release and refuses to overwrite an existing demo folder.

`verify` checks 101 copied source hashes, all 16 groups' answers/certificates and
edit deltas, gallery links and coverage. If the full local release is present,
it also checks its manifest; a fresh clone instead reports
`local_full_release_manifest_checked: false`. That is an explicit availability
limit, not a claim that the clone validated all 20,000 groups.

The small annotation example is a labeled original/edit projection. Complete
four-variant annotations and the canonical group schema are bundled. Original
SVG references are retained for provenance, but SVG/font assets are not bundled.

## Dataset regression suite

Run the dataset-focused checks, each with small disposable fixtures:

```sh
python3 -m unittest discover -s tests -p 'test_release*.py' -v
python3 -m unittest discover -s tests -p 'test_pilot.py' -v
python3 -m unittest discover -s tests -p 'test_phase1b.py' -v
python3 -m unittest discover -s tests -p 'test_dataset_extension.py' -v
python3 -m unittest discover -s tests -p 'test_instructor_demo.py' -v
```

Temporary fixture generation does not change the frozen dataset.
Test datasets use an explicitly public dummy identity key and disposable
historical fixtures; no private release key or full release is needed. Historical
Phase 2A/2B inference-harness tests are outside this dataset-only check set; some
also require excluded historical prepared bundles or the old inference mode.
They are not model experiments and are not reported here as current checks.

## Exact full release, local inputs required

The current sealed release is `outputs/topodelta_qa_v0.3.0-rc1`. Its manifest
contains 200,484 payload hashes; a complete second generation already matched
those hashes and manifest bytes without normalization. The original environment
and source snapshots remain in that release's `reproduction/` directory.

A public clone alone cannot reproduce its opaque IDs and exact acceptance trace:
it needs the original local evaluator identity key and the historical topology
blacklist. Keep them out of Git and out of inference workers. From the sealed
local release's `reproduction/REPRODUCE.md`, arrange a **fresh working directory**
with the frozen source, `configs/release_candidate.json`, the evaluator key at
`configs/evaluator_id_key.json`, and these historical inputs:

- `outputs/topodelta_qa_v0.2.0/gold/groups.jsonl` (the topology blacklist).
- `outputs/topodelta_qa_v0.2.0/manifest.json` (its recorded provenance).

The original complete reproduction sequence is:

```sh
python3 -m topodelta_qa.release.build --output outputs/repeat
python3 -m topodelta_qa.release.package prepare --dataset outputs/repeat
python3 -m topodelta_qa.release.verify --dataset outputs/repeat --output outputs/repeat/reports --expected 20000
python3 -m topodelta_qa.release.boundary_cli --dataset outputs/repeat
python3 -m topodelta_qa.release.package seal --dataset outputs/repeat
python3 -m topodelta_qa.release.package compare --dataset ORIGINAL_RELEASE --other outputs/repeat --output comparison.json
```

`ORIGINAL_RELEASE` is the absolute path to the existing sealed local release.
Use a fresh `outputs/repeat` path; sealed datasets cannot be overwritten. The
historical `prepare` command also creates blank review materials; it is recorded
here for faithful reproduction, **not an instruction to create new review
materials for this delivery**. None were created for repository preparation.
No full regeneration or dataset expansion was performed for the GitHub push.

The legacy CLI/evaluator operates on the historical 6–12-node pilot. It is
retained and tested separately; it must not be described as a release-candidate
baseline evaluator. See the actual [release report](RELEASE_CANDIDATE_REPORT.md)
for completed full-run commands and [status](../instructor_demo/STATUS.md) for
pending visual/browser checks and scope limitations.
