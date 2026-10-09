---
status: resolved
trigger: "UAT G-04-1: design.md and implementation_summary.json are generic placeholder content with no AC-1 cross-reference; fresh-eyes reader cannot follow the handoff chain"
created: 2026-09-13T00:00:00Z
updated: 2026-10-07T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED and FIXED -- the fix landed in commit cac5b2c (Plan 04-05), exactly the follow-up this diagnosis handed to plan-phase --gaps. This session's job was verification, not re-application.
test: fix-acceptance guardrail (5 signals) + two seeded mutants at the fix site + real on-disk run inspection
expecting: all applicable signals pass -> request human verification
next_action: NONE -- session closed. User answered the human-verify checkpoint "Confirmed fixed, accept empty arrays." Archived to resolved/ and appended to knowledge-base.md with the Prevention block.

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

- timestamp: phase-4-verify
  checked: "git log -- src/dark_factory/workers/fake.py"
  found: "commit cac5b2c 'feat(04-05): thread context.inputs into FakeWorker artifact synthesis' (+145/-13) already applied the recommended fix; 484def0 (08-04) later promoted the helpers to public API for the fake CLIs"
  implication: "the fix was owned and landed by plan-phase --gaps as the diagnosis directed -- this session verifies rather than re-applies. The debug file was stale, not the code."

- timestamp: phase-4-verify
  checked: "mutant M1 -- made _extract_criterion_ids ignore its inputs argument (reinstates the exact pre-fix defect), ran tests/unit/test_fake_worker_synthesis.py"
  found: "5 of 11 tests failed; failure message is the original symptom verbatim: assert 'AC-42' in 'constraint covering criterion AC-1'"
  implication: "signals 2+5 pass -- the bug returns on revert and the tests assert the root cause (derivation), not the symptom string"

- timestamp: phase-4-verify
  checked: "mutant M2 -- removed the Markdown carrier-line emission from synthesize_artifact_content (the design.md hop)"
  found: "2 tests failed; failure message is the reported symptom string verbatim: assert '- Criterion AC-9 met' in '# design.md\\n\\nAuto-generated placeholder content.\\n'"
  implication: "the subtler mutant is also killed -- the Markdown-hop mechanism specifically is covered, not just the JSON path"

- timestamp: phase-4-verify
  checked: "tests/integration/test_real_pipeline_zero_config.py (the gate that originally could not catch this)"
  found: "now asserts BA's emitted ids appear in design.md, in implementation_summary.summary, in test_report case names, and as verdict.json's ordered criterion_id list; 1 passed in 59s"
  implication: "the why-not-caught hole is closed -- the existence-only gate became a content gate. This is the recurrence guard."

- timestamp: phase-4-verify
  checked: "real on-disk run 258f9a42-9d8e-4da4-b4ad-e84f673144bd, all 7 artifacts"
  found: "every artifact carries AC-1: requirements.md and design.md both have '- Criterion AC-1 met'; constraints.json 'constraint covering criterion AC-1'; implementation_summary 'implementation summary covering AC-1'; test_report 'verifies criterion AC-1'; verdict criterion_id AC-1"
  implication: "the operator-facing symptom is resolved end to end, not just in unit fixtures"

- timestamp: phase-4-verify
  checked: "adjacent tier: uv run pytest -m 'unit or contract' (846 tests)"
  found: "845 passed, 1 skipped, 1 failed -- test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder. UNRELATED: it asserts ClaudeCodeWorker.execute({}) returns FAILED on an unconfigured machine, but settings.py:109 loads env_file='.env' and a .env here supplies ANTHROPIC_API_KEY, so the real claude CLI runs and returns COMPLETED. Still fails with ANTHROPIC_* stripped from the shell env (the credential comes from .env, not the shell). claude_code.py has no import relationship with fake.py."
  implication: "signal 4 passes -- this neighbor is not newly broken by the fix; it is a pre-existing environment-coupled test defect that needs its own session (the test must stub the CLI or override Settings rather than depend on the ambient absence of a credential)"

## Resolution

root_cause: "FakeWorker's zero-config artifact synthesis has no data path from a role's resolved upstream inputs to the content it writes. src/dark_factory/workers/fake.py:139 declares _synthesize_artifact_content(filename: str) -> str -- dispatch on filename alone -- and _default_script(context) (fake.py:149) reads only context.role / context.run_id / context.outputs, never context.inputs, which is exactly where build_role_context deposits the upstream artifact content. Three consequences: (a) any filename absent from the _synthesize_machine_artifact table -- all .md outputs -- returns the constant at fake.py:146; (b) ImplementationSummary is built with no criterion field at fake.py:115; (c) verdict.json's criterion_id='AC-1' (fake.py:132) is a hardcoded literal that merely coincides with acceptance_criteria.json's hardcoded id='AC-1' (fake.py:105), so even the one apparently-working link violates D-05's 'reference the same id ... stay aligned even if reordered' invariant."
fix: |
  Applied in commit cac5b2c (Plan 04-05) -- NOT re-applied by this session; this
  session verified it. The data path the diagnosis called for now exists:

  1. `_extract_criterion_ids(inputs)` reads `context.inputs` and extracts
     criterion ids via two strategies -- structural
     (`AcceptanceCriteriaDocument.model_validate_json`) then textual (the
     `^- Criterion (\S+) met$` carrier line) -- so the extraction dispatches on
     content shape only, never on `context.role` (keeps D-08/CTX-02).
  2. `_ORIGIN_CRITERION_IDS` is now the SINGLE place an id originates (the BA
     shape, which declares no inputs). The second independent literal is gone:
     `_synthesize_machine_artifact(filename, criterion_ids)` and
     `synthesize_artifact_content(filename, criterion_ids)` both take the id
     tuple, so verdict.json's `criterion_id` is derived, not coincidental --
     closing the D-05 violation.
  3. Markdown outputs now emit one `- Criterion <id> met` carrier line per id,
     which is what lets DEVELOPMENT (whose declared inputs are design.md +
     constraints.json, NOT acceptance_criteria.json) receive the ids through the
     Markdown hop -- the config constraint the diagnosis flagged, solved without
     a config change, exactly as the and_gate predicted.
  4. Bounded against upstream content injection: `_MAX_CRITERION_IDS=20`
     (T-04-21) and `_MAX_CRITERION_ID_LENGTH=64` + whitespace-free single token
     (T-04-19).

  Respects D-07: content is still non-task-aware placeholder prose (task-derived
  prose remains Phase 7's scope) but is now id-bearing, matching D-07's own
  worked example.

verification:
  target_test:    { result: pass, detail: "tests/unit/test_fake_worker_synthesis.py 11 passed; +10 in test_fake_cli_declared_outputs.py = 21 passed" }
  mutation_check:
    result: pass
    tool: "manual seeded mutants (no mutmut/cosmic-ray configured in this Python repo; Stryker is JS-only -- so the signal was run by hand rather than skipped)"
    mutant_killed: true
    detail: |
      M1: _extract_criterion_ids made to ignore `inputs` (reinstates the pre-fix
      defect) -> 5 tests failed, message = the original symptom
      ("assert 'AC-42' in 'constraint covering criterion AC-1'").
      M2 (subtler): Markdown carrier-line emission removed -> 2 tests failed,
      message = the reported symptom string
      ("assert '- Criterion AC-9 met' in '# design.md\n\nAuto-generated placeholder content.\n'").
      Both mutants killed by the driving test, so the tests assert the
      derivation mechanism, not a symptom string.
  no_op_deletion: { result: pass, deletion_justified_by_rca: false, detail: "diff is +145/-13 -- net additive; adds an extraction path rather than deleting/short-circuiting behavior. No weakened assertions; the integration gate gained assertions." }
  adjacent_tests:
    result: pass
    suites_run: ["unit tier", "contract tier", "tests/integration/test_real_pipeline_zero_config.py"]
    detail: "845 passed, 1 skipped, 1 failed. The single failure (test_claude_code_resolves_to_a_real_adapter_not_a_placeholder) is pre-existing and provably independent -- caused by .env supplying ANTHROPIC_API_KEY on this machine so the real claude CLI returns COMPLETED where the test expects a FAILED credential gate. No import relationship to fake.py. Reported separately, not fixed here."
  revert_and_reconfirm:
    result: pass
    bug_returned_on_revert: true
    fixed_on_reapply: true
    detail: "M1 is the revert (restores the exact pre-fix ignore-inputs behavior): bug returned with the original symptom message; `git checkout -- src/dark_factory/workers/fake.py` restored it and all 11 tests passed again. Verified tree clean after each mutant."
  static_analysis: { result: pass, detail: "mypy --strict clean on fake.py; ruff check clean on fake.py + the regression test" }
  end_to_end:
    result: pass
    detail: |
      Real on-disk run 258f9a42-9d8e-4da4-b4ad-e84f673144bd now shows the full
      chain carrying AC-1 across all 7 artifacts (design.md and
      requirements.md both carry '- Criterion AC-1 met'), and
      tests/integration/test_real_pipeline_zero_config.py drives the real
      orchestrator and asserts that chain. This is the signal the diagnosing
      session recorded as a blind spot ("did not execute a fresh end-to-end run
      -- no DB creds in this session") -- now closed.
  oracle_type: derived
  guardrail_verdict: accepted

residual_by_design: "implementation_summary.json still has changed_files: [] and tests_added: []. This is truthful rather than defective -- FakeWorker changes no files and adds no tests -- and D-07 keeps task-derived content in Phase 7's scope. Flagged for the user at the human-verify checkpoint rather than silently fixed."

human_verification:
  response: "Confirmed fixed, accept empty arrays."
  date: 2026-10-07
  dispositions:
    - "Fix CONFIRMED by the user. Handoff chain reads correctly to a fresh-eyes reader."
    - |
      ACCEPTED RESIDUAL (no further code change): implementation_summary.json's
      empty `changed_files: []` / `tests_added: []`. Rationale recorded by the
      user: FakeWorker genuinely changes no files and adds no tests, so the empty
      arrays are TRUTHFUL, not defective -- populating them would mean fabricating
      content. D-07 scopes task-derived content to Phase 7, where a real worker
      actually changes files and the arrays become meaningful. Deliberately
      accepted, not deferred-and-forgotten.
    - |
      CROSS-REFERENCE (not a duplicate): the credential-coupling finding recorded
      under the `adjacent_tests` signal --
      test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder
      failing because settings.py:109 loads env_file='.env' and a local .env
      supplies ANTHROPIC_API_KEY, so the real claude CLI runs and returns
      COMPLETED where the test expects a FAILED credential gate -- is ALREADY
      tracked in its own debug session, slug
      `claude-cli-test-spawns-real-binary-with-key-present` (opened concurrently
      from a different session). No duplicate session opened from here. It remains
      provably independent of this fix (no import relationship to fake.py).

prevention:
  blameless_5_whys:
    branch_code: |
      (CONFIRMED primary cause -- category: code)
      1. Why did design.md carry no criterion id? -> Synthesis returned a constant
         for any filename absent from the _synthesize_machine_artifact table, and
         all .md outputs were absent.
      2. Why a constant? -> _synthesize_artifact_content(filename: str) -> str had
         no parameter capable of carrying upstream content.
      3. Why no such parameter? -> The function was written to satisfy
         collect_role_artifacts -- file EXISTENCE and attribution -- not handoff
         legibility. CR-01's stated scope was "let the zero-config
         `dark-factory run` path reach COMPLETED".
      4. Why did the scope stop there? -> The code was promoted from
         tests/support/fake_artifacts.py into shipped src/dark_factory/workers/fake.py.
         In its original home it was a TEST FIXTURE, where D-07's "non-task-aware
         placeholder content is fine" genuinely applied. The promotion changed its
         AUDIENCE to operator-facing, where artifact legibility is a UAT criterion
         -- but the content bar was not re-derived for the new audience.
      5. ACTIONABLE CONDITION: a code move that changes an artifact's audience
         (test fixture -> shipped operator-facing default) carried no prompt to
         re-review the quality bar that the new audience requires. The decision
         record (D-07) and the code path silently diverged in scope.
    branch_process: |
      (category: process/gate -- why it survived two phases)
      1. Why wasn't it caught? -> tests/integration/test_real_pipeline_zero_config.py
         asserted exactly 4 things: returncode==0, status=='COMPLETED', the
         completed-role list, and artifact FILENAMES. Zero content assertions.
      2. Why no content assertions? -> It was built as an existence/attribution
         gate matching CR-01's goal.
      3. Why did no later gate add them? -> 04-VALIDATION.md:77 registered the
         exact failing truth as an in-scope SC1/ART-01 item and stated the
         limitation explicitly ("does not judge whether the on-disk layout reads
         well"), deferring it to /gsd-verify-work. The gap was KNOWN and tolerated,
         not overlooked.
      4. Why did the deferral not close itself? -> A "Deferred to /gsd-verify-work"
         item has no automated owner; it closes only when a human runs UAT and
         reads the files. UAT G-04-1 is precisely what found it -- the deferral
         worked, but slowly and only because a human looked.
      5. ACTIONABLE CONDITION: artifact-content quality had no executable gate at
         all; it depended on human inspection.
    branch_config_checked_not_causal: |
      (category: config -- branched and ruled out, per the and_gate)
      .dark-factory/roles/DEVELOPMENT.yaml declares inputs [design.md,
      constraints.json], excluding acceptance_criteria.json. NOT a cause -- the ids
      reach DEVELOPMENT through the design.md Markdown hop -- but it CONSTRAINED the
      fix design, which is exactly why the fix emits a `- Criterion <id> met`
      carrier line into Markdown rather than threading JSON only. Ruling this
      branch out is what kept the fix from growing an unnecessary config change.
    branch_data_checked_not_causal: |
      (category: data -- branched, and the source of the invisibility)
      acceptance_criteria.json's own id was itself a hardcoded literal
      (fake.py:105 id='AC-1'), matching verdict.json's independent literal
      (fake.py:132 criterion_id='AC-1'). So the data LOOKED correct on both ends.
      Not a cause, but the reason the D-05 violation was invisible: two identical
      literals in separate constructors are indistinguishable from a working data
      flow by inspection of the output alone.
    and_gate_outcome: "no -- the single code cause was sufficient and the fix confirmed it: one change (threading inputs) resolved all three symptoms. The config and data branches were checked and are non-causal."
  why_not_caught: |
    tests/integration/test_real_pipeline_zero_config.py -- the existing zero-config
    gate -- ran and PASSED throughout, because it asserted only exit code, run
    status, the completed-role list, and artifact FILENAMES, never file CONTENT.
    04-VALIDATION.md:77 recorded this limitation verbatim and deferred content
    legibility to /gsd-verify-work, so this was a known-and-tolerated gap rather
    than a missed one; it closed only when human UAT G-04-1 actually read the
    artifacts. Underlying: no executable gate existed for the CLASS "a synthesized
    artifact must reference its upstream role's identifiers" -- and because both
    ends of the one apparently-working link were hardcoded to the same literal, no
    output-inspection gate could have distinguished a real handoff from a
    coincidence either.
  recurrence_guard: |
    Three artifacts, all verified present and passing before being recorded here:

    1. CONTENT GATE (closes the why-not-caught hole directly):
       tests/integration/test_real_pipeline_zero_config.py -- upgraded from an
       existence gate to a content gate. Now asserts BA's emitted ids appear in
       design.md, in implementation_summary.summary, in test_report case names, and
       as verdict.json's ordered criterion_id list. Verified: 1 passed in 59s
       driving the real orchestrator.
    2. REGRESSION TEST, mutation-verified load-bearing:
       tests/unit/test_fake_worker_synthesis.py -- 11 tests including the
       falsification test. Proven to assert the DERIVATION mechanism rather than a
       symptom string by two seeded mutants: M1 (make _extract_criterion_ids ignore
       its `inputs` argument -- the exact pre-fix defect) killed by 5 failures
       carrying the original symptom message; M2 (remove the Markdown carrier-line
       emission, the subtler design.md-hop mutant) killed by 2 failures carrying
       the reported symptom string verbatim.
    3. STRUCTURAL GUARD (makes the bad state hard to represent):
       _ORIGIN_CRITERION_IDS in src/dark_factory/workers/fake.py is now the SINGLE
       place a criterion id originates. The second independent literal -- the thing
       that made the D-05 violation invisible -- is gone, so a future
       coincidental-match defect cannot be reintroduced without deleting the shared
       constant. Both synthesize entry points take the id tuple as a parameter, so
       the data path is now part of their signatures.

    NOT implemented (recommendation only, for the audience-change condition in
    branch_code step 5): when code is promoted from tests/support/ into shipped
    src/, re-derive the quality bar for its new audience -- a decision record
    written about test fixtures (D-07) does not automatically license the same
    content in an operator-facing default.

files_changed:
  - "src/dark_factory/workers/fake.py (commit cac5b2c -- input-aware synthesis; no changes by this session)"
  - "tests/unit/test_fake_worker_synthesis.py (commit 7e2b69a RED / cac5b2c GREEN -- 11 tests incl. the falsification test)"
  - "tests/integration/test_real_pipeline_zero_config.py (content assertions -- the recurrence guard)"
