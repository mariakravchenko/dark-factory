---
status: diagnosed
trigger: "UAT G-04-1: design.md and implementation_summary.json are generic placeholder content with no AC-1 cross-reference; fresh-eyes reader cannot follow the handoff chain"
created: 2026-09-13T00:00:00Z
updated: 2026-09-13T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED -- FakeWorker's zero-config synthesis has no data path from context.inputs to synthesized content; verdict.json's AC-1 is a hardcoded literal coinciding with acceptance_criteria.json's hardcoded literal.
test: complete
expecting: n/a
next_action: return diagnosis (goal = find_root_cause_only; plan-phase --gaps owns the fix)

reasoning_checkpoint:
  hypothesis: "_synthesize_artifact_content dispatches on filename ALONE, and _default_script never reads context.inputs, so no synthesized artifact can reference an upstream role's criterion ids. The BA<->QA AC-1 match is two independent hardcoded constants, not a handoff."
  confirming_evidence:
    - "inspect.signature(_synthesize_artifact_content) == (filename: str) -> str -- no context/inputs parameter exists"
    - "_default_script source getattr calls are exactly role, run_id, outputs; 'inputs' does not appear in the function at all (verified by source inspection)"
    - "fake.py:105 hardcodes id='AC-1' and fake.py:132 hardcodes criterion_id='AC-1' in two unrelated constructors"
    - "fake.py:146 -- every filename absent from the _synthesize_machine_artifact table returns the constant f'# {filename}\\n\\nAuto-generated placeholder content.\\n'; .md outputs always take this branch"
    - "On-disk run 032c33a3 reproduces exactly: design.md and requirements.md are the constant; implementation_summary.json has no criterion field"
  falsification_test: "If synthesis derived ids from upstream artifacts, changing BA's synthesized criterion id would move verdict.json's criterion_id. It cannot -- both are literals in separate constructors with no shared input. Direct invocation confirms verdict.json emits AC-1 unconditionally."
  fix_rationale: "Root cause is the missing parameter/data path, not the specific placeholder strings. Threading context.inputs into synthesis fixes design.md, implementation_summary.json AND makes verdict.json's D-05 alignment real instead of coincidental -- one change, three symptoms."
  blind_spots: "Did not execute a fresh end-to-end run (no DB creds in this session); relied on the existing run 032c33a3 tree plus direct function invocation. Did not confirm whether a future real worker (Phase 7) would supersede this code path entirely."
  candidate_causes:
    - "code: _synthesize_artifact_content signature is filename-only; _default_script does not thread context.inputs (CONFIRMED primary)"
    - "config: .dark-factory/roles/DEVELOPMENT.yaml inputs=[design.md, constraints.json] excludes acceptance_criteria.json -- NOT a cause, but constrains the fix: AC ids must survive the design.md hop to reach implementation_summary.json"
    - "process: tests/integration/test_real_pipeline_zero_config.py asserts only exit code / status / role list / artifact filenames -- zero content assertions, so the gate could never catch this"
  and_gate: "no -- the single code cause is sufficient. A generic 'scan all input content for criterion ids' extraction threads AC-1 through design.md into DEVELOPMENT's context, so no config change is strictly required. The DEVELOPMENT.yaml inputs shape is a fix-design constraint, not a second necessary condition."

## Symptoms

expected: A person who has never seen the codebase can follow the handoff from acceptance_criteria.json -> design.md -> verdict.json and see which criterion ids (AC-1) line up across files.
actual: acceptance_criteria.json has AC-1 and verdict.json references AC-1, but design.md is "# design.md\n\nAuto-generated placeholder content." and implementation_summary.json has a generic summary with empty changed_files/tests_added. No AC-1 anywhere in ARCHITECTURE/DEVELOPMENT artifacts.
errors: none (run completes to COMPLETED, exit 0)
reproduction: uv run dark-factory run spec:./task.md ; inspect .dark-factory/runs/<id>/artifacts/
started: Discovered during Phase 04 UAT (run 032c33a3-1a41-4afa-9ed0-a7ece2d8f20b)

## Eliminated

- hypothesis: "verdict.json correctly reads AC-1 from BA's upstream acceptance_criteria.json, and only the .md path is broken"
  evidence: "_synthesize_machine_artifact('verdict.json') takes no context and hardcodes criterion_id='AC-1' at fake.py:132. Direct invocation returns AC-1 with zero inputs supplied. The QA->BA alignment is coincidence, not data flow -- so verdict.json is ALSO defective, just invisibly so."
  timestamp: phase-3

- hypothesis: "This is a config gap -- the role YAMLs do not declare the right inputs, so the data is unavailable"
  evidence: "ARCHITECTURE.yaml declares inputs:[acceptance_criteria.json]; QA.yaml declares inputs:[acceptance_criteria.json, implementation_summary.json]. build_role_context resolves these into RoleContext.inputs[].content (proven in 04-01-SUMMARY). The data IS present in the context object handed to _default_script -- it is simply never read."
  timestamp: phase-3

- hypothesis: "Placeholder .md content is an explicit documented non-goal for Phase 4 (D-07), so this is not a bug"
  evidence: "PARTIALLY eliminated. D-07 rules out TASK-AWARE prose ('realistic content only matters once Phase 7 wires a real Claude Code worker'), but D-07's own worked example of acceptable placeholder content is literally 'Criterion AC-1 met' -- id-bearing. D-07 licenses non-task-aware text, NOT id-free text. Separately, 04-VALIDATION.md:77 registers the exact failing truth as an in-scope SC1/ART-01 item with status 'Deferred to /gsd-verify-work' -- deferred, not out of scope."
  timestamp: phase-3

## Evidence

- timestamp: phase-0
  checked: .planning/debug/knowledge-base.md
  found: does not exist (no prior resolved sessions)
  implication: no known-pattern shortcut; investigate from scratch

- timestamp: phase-1
  checked: src/dark_factory/workers/fake.py (full read)
  found: "_synthesize_machine_artifact(filename) is a 5-way if-chain on filename returning None for anything unlisted; _synthesize_artifact_content(filename) falls through to a constant Markdown string; _default_script(context) reads getattr role/run_id/outputs only"
  implication: "no parameter carries upstream data into synthesis -- the defect is structural (a missing data path), not a bad string constant"

- timestamp: phase-1
  checked: "run 032c33a3-1a41-4afa-9ed0-a7ece2d8f20b artifact tree (all 7 files)"
  found: "requirements.md + design.md are byte-identical placeholder constants; implementation_summary.json has empty changed_files/tests_added and a generic summary; acceptance_criteria.json id=AC-1; verdict.json criterion_id=AC-1"
  implication: "symptom reproduced exactly as reported; 5 of 7 artifacts carry no traceable link to any neighbour"

- timestamp: phase-3
  checked: "direct invocation of _synthesize_artifact_content + inspect.signature + source scan of _default_script"
  found: "signature is (filename: str) -> str; 'inputs' appears nowhere in _default_script; verdict.json emits criterion_id=AC-1 with no input whatsoever"
  implication: "falsification test passes -- the BA/QA AC-1 alignment is provably coincidental. D-05's 'stay aligned even if criteria are reordered or filtered' invariant is violated."

- timestamp: phase-3
  checked: .planning/phases/04-.../04-CONTEXT.md (D-05, D-07), 04-VALIDATION.md:77, 04-03-PLAN.md:235
  found: "D-07 permits non-task-aware placeholder content but its example is id-bearing ('Criterion AC-1 met'). D-05 requires verdict.json to REFERENCE BA's ids. 04-VALIDATION.md:77 lists the failing truth as an SC1/ART-01 item 'Deferred to /gsd-verify-work'."
  implication: "in-scope gap for Phase 4, with a carve-out: task.md-derived prose remains Phase 7's concern"

- timestamp: phase-3
  checked: 04-REVIEW.md CR-01 + 04-REVIEW-FIX.md CR-01
  found: "CR-01 moved artifact synthesis from tests/support/fake_artifacts.py into shipped src/dark_factory/workers/fake.py so the operator-facing zero-config `dark-factory run` path could reach COMPLETED. Fix scope was 'satisfy collect_role_artifacts', never 'make the handoff legible'."
  implication: "D-07 was written about TEST FIXTURES; CR-01 promoted the same weak content to the OPERATOR-FACING default. The scope statement and the code path diverged -- that divergence is why nobody re-checked the content bar."

- timestamp: phase-3
  checked: tests/integration/test_real_pipeline_zero_config.py assertions
  found: "4 assertions: returncode==0, run.status=='COMPLETED', completed_roles==[BA,ARCHITECTURE,DEVELOPMENT,QA], artifact_types==filenames. Zero assertions on file content."
  implication: "why-not-caught: the CR-01 gate is an existence/attribution gate. 04-VALIDATION.md:77 says so explicitly ('does not judge whether the on-disk layout reads well')."

## Resolution

root_cause: "FakeWorker's zero-config artifact synthesis has no data path from a role's resolved upstream inputs to the content it writes. src/dark_factory/workers/fake.py:139 declares _synthesize_artifact_content(filename: str) -> str -- dispatch on filename alone -- and _default_script(context) (fake.py:149) reads only context.role / context.run_id / context.outputs, never context.inputs, which is exactly where build_role_context deposits the upstream artifact content. Three consequences: (a) any filename absent from the _synthesize_machine_artifact table -- all .md outputs -- returns the constant at fake.py:146; (b) ImplementationSummary is built with no criterion field at fake.py:115; (c) verdict.json's criterion_id='AC-1' (fake.py:132) is a hardcoded literal that merely coincides with acceptance_criteria.json's hardcoded id='AC-1' (fake.py:105), so even the one apparently-working link violates D-05's 'reference the same id ... stay aligned even if reordered' invariant."
fix: "[not applied -- goal was find_root_cause_only; plan-phase --gaps owns the fix]"
verification: "[n/a -- diagnosis only]"
files_changed: []
