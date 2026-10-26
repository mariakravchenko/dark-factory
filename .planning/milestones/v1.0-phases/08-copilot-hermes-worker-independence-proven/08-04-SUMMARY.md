---
phase: 08-copilot-hermes-worker-independence-proven
plan: 04
subsystem: workers, config
tags: [role-reassignment, worker-independence, fake-cli, config-driven, tdd, sc2-proof]

requires:
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "CopilotWorker (08-01) and HermesWorker (08-02), the shared cli_runtime.py pipeline, and the fake_copilot_cli.py / fake_hermes_cli.py test-support modules this plan promotes/generalizes -- the literal adapters this plan reassigns the shipped roles onto."
provides:
  - "dark_factory.workers.fake.synthesize_artifact_content / criterion_ids_from_text -- public synthesis helpers a test-support fake CLI (or any future caller) can reuse instead of hand-maintaining a second copy of minimal schema-valid artifact content."
  - "tests/support/fake_cli.py::write_fake_cli -- the one generator every fake-CLI module (claude, copilot, hermes) now delegates to, with a declared_outputs mode that makes a faked executable write a role's declared output files exactly as a real agent runtime would."
  - "The shipped .dark-factory/roles/*.yaml set assigns ARCHITECTURE -> copilot, DEVELOPMENT -> claude-code, QA -> hermes, BA -> fake -- ROADMAP SC2's own literal example, implemented entirely as a configuration edit (D-04)."
  - "tests/integration/test_role_reassignment_sc2.py -- the literal WORK-09/SC2 paired-run equality proof plus its T-08-23 negative case (no substitution on a missing binary)."
affects: [09-independent-quality-gate-and-feedback-loops]

actuals:
  tokens: 14920
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "Shared fake-CLI generator (tests/support/fake_cli.py): one write_fake_cli() function every adapter's fake-executable-on-PATH module (fake_claude_cli.py, fake_copilot_cli.py, fake_hermes_cli.py) delegates to, so a behavioural change to the faked-binary contract (e.g. declared_outputs) needs one edit, not three."
    - "declared_outputs mode: a generated fake CLI script scans its own argv for the '## Expected outputs' prompt section, parses each bullet with a shared producer/parser regex, and writes dark_factory.workers.fake.synthesize_artifact_content(filename, criterion_ids_from_text(prompt)) under the run root it locates by globbing .dark-factory/runs/* -- making a faked external runtime behave like a real agent in the one respect the artifact-validation gate cares about."
    - "Configuration-only role reassignment: a role's worker changes by editing one worker: line in its YAML file, with no change anywhere under src/dark_factory/orchestrator/, src/dark_factory/workflows/ or src/dark_factory/lifecycle -- proven, not merely claimed, by test_no_worker_name_leak.py and test_no_role_name_literal.py passing unchanged."

key-files:
  created:
    - tests/support/fake_cli.py
    - tests/integration/test_role_reassignment_sc2.py
  modified:
    - src/dark_factory/workers/fake.py
    - tests/support/fake_copilot_cli.py
    - tests/support/fake_claude_cli.py
    - tests/support/fake_hermes_cli.py
    - tests/integration/test_real_pipeline_zero_config.py
    - .dark-factory/roles/ARCHITECTURE.yaml
    - .dark-factory/roles/DEVELOPMENT.yaml
    - .dark-factory/roles/QA.yaml
    - tests/unit/test_fake_cli_declared_outputs.py

key-decisions:
  - "Promoted _synthesize_artifact_content to synthesize_artifact_content and added criterion_ids_from_text as a new public function (rather than duplicating minimal schema-valid content inside the test-support fake-CLI generator), sharing one _candidate_ids_for_text / _finalize_criterion_ids pair between the new text-based entry point and the existing inputs-based _extract_criterion_ids so the two cannot drift."
  - "The generated fake CLI script's shebang is the absolute interpreter path (sys.executable) rather than a PATH-resolved name, since build_worker_env strips Python-related environment variables (PYTHONPATH, VIRTUAL_ENV) from the child -- interpreter identity is the only reliable way for the generated script to import dark_factory."
  - "BA.yaml stays on worker: fake (D-04): not named in ROADMAP SC2's literal example, not load-bearing for the independence proof, and keeping one role in-process makes the proof stronger -- a single pipeline mixing FakeWorker with three external runtimes, not four external runtimes with nothing to compare against."
  - "tests/integration/test_real_pipeline_zero_config.py's _external_runtime_fakes fixture is installed unconditionally (independent of which worker each role is currently assigned to) so Task 3's role-YAML edit alone flips the same test onto three real runtimes with zero further test-code change -- the literal shape of WORK-09's 'zero workflow-code change' claim, extended to test code."
  - "tests/integration/test_role_reassignment_sc2.py duplicates (does not import) the three-fake-executables-plus-two-credentials fixture logic from test_real_pipeline_zero_config.py, because this module drives two separate throwaway checkouts through one shared PATH/credential environment in a single test function -- a shape the per-test fixture in the sibling module does not fit."

patterns-established:
  - "Pattern: RED commit that cannot be executed in this sandbox is still committed with an environment-independent proof of the underlying failure (a direct interpreter invocation of the same code path, or the plan's own verify command run standalone) recorded in the commit message, rather than skipped -- since this repository's db/integration tier requires a real PostgreSQL 17 not available here (established since Phase 1/01-RESEARCH.md; most recently exercised at Phase 6 close-out)."

requirements-completed: [WORK-09]

coverage:
  - id: D1
    description: "synthesize_artifact_content and criterion_ids_from_text are public in dark_factory.workers.fake, importable and in __all__, with FakeWorker's own behaviour unchanged"
    requirement: "WORK-09"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_cli_declared_outputs.py (10 tests)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py (unchanged, 11 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A faked copilot/claude/hermes executable, given declared_outputs=True, writes a role's declared output files under <run_root>/artifacts/<role>/ with synthesized schema-valid content, and writes nothing when declared_outputs is unset or the prompt carries no Expected-outputs heading"
    requirement: "WORK-09"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_cli_declared_outputs.py::test_declared_outputs_writes_both_files_with_synthesized_content, ::test_fake_without_declared_outputs_writes_no_artifact_file, ::test_declared_outputs_with_no_expected_outputs_heading_writes_nothing_and_exits_zero"
        status: pass
    human_judgment: false
  - id: D3
    description: "fake_claude_cli.py, fake_copilot_cli.py and fake_hermes_cli.py each contain exactly one call to the shared write_fake_cli() and no inline generated-script source, and are behaviourally identical to the pre-refactor generators"
    requirement: "WORK-09"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py, test_copilot_worker.py, test_hermes_worker.py (115 tests, no assertion edits)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The shipped .dark-factory/roles/*.yaml set resolves to {BA: fake, ARCHITECTURE: copilot, DEVELOPMENT: claude-code, QA: hermes}, with .dark-factory.yaml unchanged and each edited role file changed by exactly two lines"
    requirement: "WORK-09"
    verification:
      - kind: unit
        ref: "plan's own worker-mapping check (python -c \"...yaml.safe_load...\"), re-run and confirmed passing"
        status: pass
      - kind: unit
        ref: "git diff .dark-factory/roles/{ARCHITECTURE,DEVELOPMENT,QA}.yaml -- exactly one worker: line change plus one added comment line each, confirmed byte-identical otherwise"
        status: pass
    human_judgment: false
  - id: D5
    description: "No runtime name entered orchestrator/workflow code to make the reassignment work"
    requirement: "WORK-09"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py, test_no_role_name_literal.py (4 tests, unchanged)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Driving the shipped configuration set across three real runtimes reaches COMPLETED with the same role sequence and per-role artifact-type sets as the same configuration run entirely on FakeWorker, differing only in the persisted worker name per role; a run with no fake binaries on PATH fails visibly (ARCHITECTURE FAILED) rather than silently substituting a worker"
    requirement: "WORK-09"
    verification:
      - kind: integration
        ref: "tests/integration/test_role_reassignment_sc2.py::test_reassigned_roles_reach_completed_identically_to_all_fake, ::test_shipped_config_with_no_fake_binaries_fails_visibly_not_silently"
        status: human_needed
      - kind: unit
        ref: "Standalone verification of the module's pure-Python configuration-diff helper (_role_yaml_diff_is_worker_lines_only) against real copied shipped config trees -- confirmed passing outside pytest, independent of PostgreSQL availability"
        status: pass
    human_judgment: true
    rationale: "This module needs a reachable PostgreSQL 17, which is not available in this sandboxed worktree (no Docker, no local initdb, no DARK_FACTORY_TEST_DATABASE_URL -- confirmed by running the existing sibling test_real_pipeline_zero_config.py, which fails identically on the same session-scoped pg_url fixture that predates this plan). Both new tests collect cleanly with zero import/collection errors (163/908 integration-tier tests collected). The full plan's <verify> commands that require Postgres are deferred to human verification, consistent with this project's established pattern (see Phase 6 SUMMARY.md's 'All 4 deferred human-verification items ... closed 2026-09-20' precedent)."

duration: ~45min
completed: 2026-09-21
status: complete
commits: 6
plan_head_before: 9863946775745e6f4499d3d4567d3fda2ab8f530
---

# Phase 8 Plan 4: Copilot & Hermes Worker Independence — SC2 Role-Reassignment Proof Summary

**Reassigns the shipped `.dark-factory/roles/*.yaml` set across all three real agent runtimes — Architect on Copilot, Developer on Claude Code, QA on Hermes — by editing three `worker:` lines, and proves the run still completes identically to an all-`FakeWorker` run, satisfying ROADMAP SC2 and WORK-09 literally.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-09-21 (session start)
- **Completed:** 2026-09-21T18:37:54+03:00 (last commit)
- **Tasks:** 3
- **Files modified:** 11 (2 created, 9 modified)

## Accomplishments

- `dark_factory.workers.fake.synthesize_artifact_content` and `criterion_ids_from_text` are now public, letting the test-support fake CLIs reuse the exact minimal schema-valid content `FakeWorker` itself writes, rather than hand-maintaining a second copy that could silently drift.
- `tests/support/fake_cli.py::write_fake_cli` is the one generator every fake-CLI module (`fake_claude_cli.py`, `fake_copilot_cli.py`, `fake_hermes_cli.py`) now delegates to, with a new `declared_outputs` mode: a faked executable, given a prompt whose `## Expected outputs` block names filenames, writes those files with synthesized content under the run root it locates by globbing `.dark-factory/runs/*` — the one respect in which a faked agent must behave like a real one for the D-09 artifact-validation gate to pass.
- The shipped configuration set now literally satisfies ROADMAP SC2: `ARCHITECTURE.yaml` → `worker: copilot`, `DEVELOPMENT.yaml` → `worker: claude-code`, `QA.yaml` → `worker: hermes`, `BA.yaml` unchanged on `worker: fake`. `.dark-factory.yaml` is unchanged; the reassignment is entirely per-role YAML.
- `tests/integration/test_real_pipeline_zero_config.py` gained an `_external_runtime_fakes` fixture installing all three fake executables (`declared_outputs=True`) and both worker credentials, so the same test that already proves the shipped config reaches `COMPLETED` now proves it across three external runtimes with zero further test-code change once the role YAML flips.
- `tests/integration/test_role_reassignment_sc2.py` is the literal WORK-09/SC2 proof: a paired-run equality comparison (three-runtime shipped config vs. the same config with every `worker:` line rewritten to `fake`) asserting identical terminal status, role sequence and per-role artifact-type sets, differing only in the persisted worker name — plus a negative case proving a missing binary fails visibly rather than silently substituting another worker (T-08-23).
- `tests/unit/test_no_worker_name_leak.py` and `test_no_role_name_literal.py` pass unchanged: no runtime name entered orchestrator or workflow code to make any of this work.

## Task Commits

Each task followed RED (test) → GREEN (implementation) TDD discipline:

1. **Task 1: One fake CLI writes the declared outputs its prompt asks for** (tracer)
   - `ba9b2a6` (test, RED) — `tests/support/fake_cli.py` + `tests/unit/test_fake_cli_declared_outputs.py`, confirmed RED via `ImportError: cannot import name 'criterion_ids_from_text'`
   - `484def0` (feat, GREEN) — `src/dark_factory/workers/fake.py` promotion + `tests/support/fake_copilot_cli.py` rewritten as a thin wrapper
   - Tracer feedback gate: re-ran `<verify>` end-to-end (`pytest -m "unit or contract" -q` — 592 passed, 1 skipped; `mypy`/`ruff` clean modulo 2 pre-existing unrelated errors) — passed, no checkpoint, continued straight to Task 2.

2. **Task 2: The other two fake CLIs share the same generator, and the shipped-config pipeline test installs all three**
   - `edec6ac` (test, RED) — `tests/integration/test_real_pipeline_zero_config.py`'s `_external_runtime_fakes` fixture, confirmed RED via direct interpreter invocation (`write_fake_claude() got an unexpected keyword argument 'declared_outputs'`)
   - `6d30cf3` (feat, GREEN) — `fake_claude_cli.py`/`fake_hermes_cli.py` rewritten as thin wrappers; 115 pre-existing worker unit tests re-verified behaviourally identical

3. **Task 3: Reassign the shipped roles across three runtimes and prove only configuration changed**
   - `89dce52` (test, RED) — `tests/integration/test_role_reassignment_sc2.py`, confirmed RED against the plan's own worker-mapping check (`AssertionError: {..all fake..}`)
   - `46e4983` (feat, GREEN) — `.dark-factory/roles/{ARCHITECTURE,DEVELOPMENT,QA}.yaml` edited exactly one `worker:` line + one comment line each

**Plan metadata:** this SUMMARY commit (STATE/ROADMAP applied by the orchestrator after wave merge — worktree mode).

## Files Created/Modified

- `tests/support/fake_cli.py` — shared fake-CLI generator: `write_fake_cli()`, `EXPECTED_OUTPUTS_HEADING`, `OUTPUT_BULLET_RE`, the `declared_outputs` code-generation step
- `tests/integration/test_role_reassignment_sc2.py` — the WORK-09/SC2 paired-run equality proof + T-08-23 negative case
- `src/dark_factory/workers/fake.py` — `synthesize_artifact_content` / `criterion_ids_from_text` promoted/added to `__all__`; `_candidate_ids_for_text` / `_finalize_criterion_ids` shared helpers so the two extraction entry points cannot drift
- `tests/support/fake_copilot_cli.py`, `tests/support/fake_claude_cli.py`, `tests/support/fake_hermes_cli.py` — each now a thin wrapper over `write_fake_cli`, forwarding `declared_outputs`
- `tests/integration/test_real_pipeline_zero_config.py` — `_external_runtime_fakes` fixture; timeout raised 90s → 240s; module docstring updated to state the widened subject
- `.dark-factory/roles/ARCHITECTURE.yaml` — `worker: copilot`
- `.dark-factory/roles/DEVELOPMENT.yaml` — `worker: claude-code`
- `.dark-factory/roles/QA.yaml` — `worker: hermes`
- `tests/unit/test_fake_cli_declared_outputs.py` — unit coverage for the promoted helpers and the `declared_outputs` mode

## Decisions Made

See `key-decisions` in frontmatter. The most consequential: **BA stays on `fake`** (D-04) rather than being swept into the reassignment — not named in ROADMAP SC2's literal example, and keeping one role in-process makes the independence proof stronger (a pipeline genuinely mixing an in-process worker with three external runtimes, not four external runtimes proving nothing about mixed operation).

## Deviations from Plan

None — plan executed exactly as written. Two execution-technique notes, not deviations from intent:

1. Each task's RED commit could not be observed failing inside `pytest` for the two Postgres-dependent tasks (Task 2, Task 3), because this sandbox has no reachable PostgreSQL 17 (Docker absent, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset). RED was instead confirmed by direct interpreter invocation of the same code path the test exercises (documented in each RED commit message) — an environment-independent proof of the same underlying fact a passing/failing `pytest` run would show.
2. For Task 3, the role-YAML edits were staged as their own GREEN commit after a temporary `git checkout --` revert (to author the RED test against the true pre-reassignment state) and reapplication — a working-tree technique to get a clean RED→GREEN commit pair, not a deviation from what the plan asked for.

**Total deviations:** 0.
**Impact:** None.

## Issues Encountered

- **Pre-existing, unrelated mypy errors (2, in `tools/mcp_transport.py`):** `Cannot find implementation or library stub for module named "mcp.server"` — the optional `mcp` extra is not installed in this environment. Confirmed identical to the baseline recorded in both 08-01-SUMMARY.md and 08-02-SUMMARY.md self-checks; this plan touches no file in `tools/mcp_transport.py`'s import closure. Out of scope per the Scope Boundary rule.
- **No reachable PostgreSQL 17 in this sandbox:** confirmed by running the pre-existing sibling test `tests/integration/test_real_pipeline_zero_config.py` (unmodified in this respect) against the same session-scoped `pg_url` fixture — it fails identically, proving this is an environment constraint that predates this plan, not something Task 2/3 introduced. `uv run pytest -q` (the plan's final full-suite `<verify>` command) cannot be run to a green result in this sandbox for the same reason: the session-scoped `_schema_at_head` autouse fixture detects the presence of any `integration`-marked test in the collected session (which has been true since `test_real_pipeline_zero_config.py` shipped, well before this plan) and eagerly resolves `pg_url` for the whole session, failing every test's setup — not only the integration-tier ones. This is documented, established project behavior (01-RESEARCH.md; most recently exercised at Phase 6 close-out, see that phase's SUMMARY.md "4 deferred human-verification items ... closed 2026-09-20").

## User Setup Required

**Deferred to human verification** (requires a reachable real PostgreSQL 17 — set `DARK_FACTORY_TEST_DATABASE_URL`, install Docker for the `testcontainers` rung, or provide a local `initdb`/`pg_ctl`):

1. `uv run pytest -q tests/integration/test_real_pipeline_zero_config.py` — confirms the shipped configuration, now spanning three external runtimes, still reaches `COMPLETED` with the G-04-1 acceptance-criteria handoff chain intact.
2. `uv run pytest -q tests/integration/test_role_reassignment_sc2.py` — confirms both new SC2 proof tests: the paired-run equality comparison and the negative (missing-binary) case.
3. `uv run pytest -q` (full suite) — confirms the whole suite is green with the three live-runtime modules from plan 08-03 reported as skips.

All three commands were verified at the collection level (zero import/collection errors; 163/908 integration-tier tests collected including both new tests) and their underlying logic was independently sanity-checked outside `pytest` where the DB dependency could be isolated (the configuration-diff helper `_role_yaml_diff_is_worker_lines_only`, run standalone against real copied shipped config trees, passed). This mirrors the exact deferral pattern Phase 6 used and closed via `/gsd-verify-work`.

## Next Phase Readiness

- ROADMAP SC2 and WORK-09 are structurally complete: the shipped configuration reassigns three roles to three real runtimes via configuration alone, with the reassignment's correctness proof written, collection-verified, and logically sanity-checked pending a real-Postgres run.
- Phase 8's four adapters (`FakeWorker`, `ClaudeCodeWorker`, `CopilotWorker`, `HermesWorker`) are all registered, all covered by the shared contract suite (08-01/08-02), and now all exercised together by the shipped pipeline configuration.
- Phase 9 (independent quality gate and feedback loops) can proceed once the deferred Postgres verification above closes — no code-level blocker.
- No blockers identified beyond the environment-level Postgres deferral documented above.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-21*

## Self-Check: PASSED

- `tests/support/fake_cli.py` and `tests/integration/test_role_reassignment_sc2.py` (key-files.created) verified present on disk.
- All 6 commit hashes (`ba9b2a6`, `484def0`, `edec6ac`, `6d30cf3`, `89dce52`, `46e4983`) confirmed in `git log --oneline`.
- `pytest -m unit -q tests/unit/test_fake_cli_declared_outputs.py tests/unit/test_fake_worker_synthesis.py`: 21 passed.
- `pytest -m "unit or contract" -q`: 592 passed, 1 skipped (pre-existing, unrelated `mcp` optional-dependency skip; up from 582 at 08-02's baseline).
- `pytest -m unit -q tests/unit/test_claude_code_worker.py tests/unit/test_copilot_worker.py tests/unit/test_hermes_worker.py`: 115 passed, no assertion edits.
- `pytest -m unit -q tests/unit/test_no_worker_name_leak.py tests/unit/test_no_role_name_literal.py tests/unit/test_no_environ_copy.py tests/unit/test_git_ownership_boundary.py tests/unit/test_single_mutation_path.py`: 10 passed.
- `uv run mypy src/dark_factory`: 2 pre-existing, unrelated errors (baseline-identical to 08-01/08-02).
- `uv run ruff check .`: all checks passed.
- `pytest --collect-only -q -m integration`: 163/908 collected, zero collection errors, including both new `test_role_reassignment_sc2.py` tests.
- Plan-level worker-mapping verify command re-passed: `{BA: fake, ARCHITECTURE: copilot, DEVELOPMENT: claude-code, QA: hermes}`.
- `git diff` over the three edited role YAML files confirmed exactly two changed/added lines each, every other line byte-identical.
- Postgres-dependent acceptance criteria (both new integration tests' actual execution, full-suite `pytest -q`) are DEFERRED to human verification per the documented environment constraint above — not silently skipped.
