# Status for the instructor demo

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
