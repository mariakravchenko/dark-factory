---
status: diagnosed
phase: 04-the-four-role-pipeline-artifact-handoffs
source: [04-VERIFICATION.md]
started: 2026-09-13T12:00:00Z
updated: 2026-09-13T13:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Fresh-eyes readability of a real run's artifact tree
expected: Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (requirements.md, acceptance_criteria.json, design.md, constraints.json, implementation_summary.json, test_report.json, verdict.json). A person who has never seen this codebase should be able to follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids line up across the files.
result: issue
reported: "Ran `uv run dark-factory run spec:./task.md` (run 032c33a3-1a41-4afa-9ed0-a7ece2d8f20b). acceptance_criteria.json has AC-1 and verdict.json references AC-1 back, but design.md and implementation_summary.json are generic 'Auto-generated placeholder content' / empty summary with zero mention of AC-1 or the spec content. A fresh-eyes reader cannot follow the handoff through design.md as required -- fix it."
severity: major

## Summary

total: 1
passed: 0
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-04-1
  truth: "A person who has never seen this codebase can follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids (AC-1, etc.) line up across the files."
  status: failed
  reason: "User reported: FakeWorker's zero-config default writes generic placeholder text for design.md ('Auto-generated placeholder content.') and implementation_summary.json (empty changed_files/tests_added, generic summary string) with no reference to the criterion ids (e.g. AC-1) that acceptance_criteria.json and verdict.json share. The handoff chain breaks at ARCHITECTURE and DEVELOPMENT -- only BA and QA carry the criterion id."
  severity: major
  test: 1
  root_cause: "FakeWorker's zero-config synthesis has no data path from a role's resolved upstream inputs to the content it writes. `_synthesize_artifact_content(filename) -> str` dispatches on filename alone and `_default_script(context)` reads only context.role/run_id/outputs -- never context.inputs, where build_role_context already deposits upstream artifact content. Consequences: any .md output falls through to the constant 'Auto-generated placeholder content.'; ImplementationSummary has no criterion field; and verdict.json's criterion_id='AC-1' is a second, independent hardcoded literal that only coincidentally matches acceptance_criteria.json's hardcoded id -- not a real handoff. In scope for Phase 4 per 04-VALIDATION.md's SC1/ART-01 (deferred to UAT, not out-of-scope) and D-05/D-07 in 04-CONTEXT.md (D-05 requires id-based not positional alignment; D-07's own accepted placeholder example is id-bearing, 'Criterion AC-1 met'). The spec-content half of the original report (design.md not reflecting task.md) is genuinely Phase 7 scope per D-07 and is NOT part of this gap."
  artifacts:
    - path: "src/dark_factory/workers/fake.py"
      issue: "_synthesize_artifact_content/_default_script never read context.inputs; .md outputs fall through to a fixed placeholder string (~line 146); verdict.json and acceptance_criteria.json each hardcode their own 'AC-1' literal independently (~lines 105, 132); ImplementationSummary is built with no criterion field (~line 115)"
  missing:
    - "Thread context.inputs into artifact synthesis (e.g. widen _synthesize_artifact_content to accept inputs) so ids from upstream artifacts are available when producing an output"
    - "Extract criterion ids generically from whatever input content a role received (e.g. scan for AC-n-shaped ids) rather than hardcoding"
    - "Emit an id-bearing placeholder for .md outputs in D-07's own style ('Criterion AC-1 met') instead of the current id-free constant"
    - "Derive verdict.json's criterion_id values from the acceptance-criteria input instead of a literal, so renaming BA's id moves the verdict id too (D-05 alignment)"
    - "Add a content-assertion regression guard to tests/integration/test_real_pipeline_zero_config.py (BA's ids appear in design.md and verdict.json) since the existing gate only checks exit code/status/role list/filenames"
  debug_session: ".planning/debug/fakeworker-placeholder-artifacts.md"
