---
phase: 08-copilot-hermes-worker-independence-proven
plan: 03
subsystem: testing
tags: [pytest, skip-guarded-integration, worker-capabilities, quality-gate, quality-quality-assurance, cli-adapter]

requires:
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "CopilotWorker (08-01) and HermesWorker (08-02) -- the two adapters this plan's live suites drive alongside ClaudeCodeWorker (Phase 7); the fake-CLI argv-log mechanism (tests/support/fake_claude_cli.py / fake_copilot_cli.py / fake_hermes_cli.py) this plan's capability-behaviour proof reuses."
provides:
  - "tests/support/live_runtime.py -- the single shared definition of \"this runtime is available\" (LiveRuntime, LIVE_RUNTIMES, binary_missing/credential_missing/skip_reason), so the three live suites cannot drift on what \"absent\" means"
  - "tests/integration/test_claude_code_live.py / test_copilot_live.py / test_hermes_live.py -- three skip-guarded live integration suites (QUAL-03): collected in every environment, skipped with a named reason when the binary/credential is absent, driving the real binary end to end when both are present"
  - "tests/unit/test_every_real_adapter_has_a_live_suite.py -- a completeness guard enumerating default_registry (minus \"fake\") and asserting a live module exists per name, with a self-detection test against a synthetic worker name"
  - "src/dark_factory/workers/registry.py: WorkerRegistry.names() -- an additive accessor mirroring ToolRegistry.names(), so the completeness guard enumerates from the registry rather than a hand-maintained list"
  - "tests/unit/test_worker_capabilities_match_behaviour.py -- ROADMAP SC4 proof: each real adapter's native_resume/structured_output/non_interactive/emits_changed_files axes checked against observed argv/result, not a repeated literal"
affects: [09-independent-quality-gate]

actuals:
  tokens: 9327
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Skip-guarded live integration suite: module-level pytestmark = [pytest.mark.integration, pytest.mark.skipif(condition, reason=...)] evaluated once at import from a shared skip-condition helper, so the module is always collected and reports a named skip rather than disappearing from the suite."
    - "Observe-then-assert capability proof: read capabilities() first, then observe the adapter's actual argv/result, then assert the two agree -- never assert a declaration equals a repeated literal."
    - "Completeness guard enumerated from the registry, not a hand-maintained list: default_registry.names() minus the exempt set drives the QUAL-03 obligation, with a self-detection test proving the guard can fail on a real omission."

key-files:
  created:
    - tests/support/live_runtime.py
    - tests/integration/test_claude_code_live.py
    - tests/integration/test_copilot_live.py
    - tests/integration/test_hermes_live.py
    - tests/unit/test_every_real_adapter_has_a_live_suite.py
    - tests/unit/test_worker_capabilities_match_behaviour.py
  modified:
    - src/dark_factory/workers/registry.py

key-decisions:
  - "Task 1's skip_reason() checks the binary before the credential, so a half-configured environment's skip reason names only the one unmet precondition -- never a generic message and never both fields at once (Edge probe QUAL-03/adjacency)."
  - "credential_missing() reads through get_settings() rather than os.environ directly, so a credential supplied only via an operator's .env file still counts as configured -- matching how the adapter itself resolves the credential at spawn time."
  - "Added WorkerRegistry.names() (src/dark_factory/workers/registry.py) even though it is outside this plan's originally declared files_modified list -- the plan's own Task 2 action text explicitly authorizes this (\"If WorkerRegistry exposes no way to list its registered names, add a names() -> set[str] method\"), and the completeness guard's key_link (\"the registry is the source of truth\") is unsatisfiable without it. An additive, behaviour-preserving accessor mirroring ToolRegistry.names()'s exact shape; no other file in this wave touches registry.py."
  - "Task 3's non-interactive axis writes a bespoke, module-local fake-binary generator (_write_stdin_probe_binary) rather than extending the shared tests/support/fake_*_cli.py helpers, because this plan's files_modified list scopes Task 3 to test_worker_capabilities_match_behaviour.py alone -- probing the spawn's own stdin plumbing is specific to this one axis and belongs nowhere else."
  - "The session_id axis is deliberately NOT re-tested in test_worker_capabilities_match_behaviour.py for the three subprocess adapters -- tests/contract/test_coding_worker_contract.py::test_worker_session_id_matches_capability_declaration already pins it for all four workers (named explicitly in this plan's own read_first list). FakeWorker's session_id is still checked directly, per the plan's explicit instruction to handle FakeWorker separately."

patterns-established:
  - "Pattern: shared skip-condition helper as the one source of truth for a resource-availability check across N otherwise-independent test modules (tests/support/live_runtime.py) -- applicable to any future skip-guarded suite needing a consistent 'is X available' definition."

requirements-completed: [QUAL-03]

coverage:
  - id: D1
    description: "Each of the three real adapters (claude-code, copilot, hermes) has its own skip-guarded integration suite that collects in every environment and reports a named skip -- never a failure or an exclusion -- when its runtime's binary or credential is absent"
    requirement: "QUAL-03"
    verification:
      - kind: integration
        ref: "tests/integration/test_claude_code_live.py::test_claude_code_worker_executes_a_trivial_role_end_to_end (skipped, named reason)"
        status: pass
      - kind: integration
        ref: "tests/integration/test_copilot_live.py::test_copilot_worker_executes_a_trivial_role_end_to_end (skipped, named reason)"
        status: pass
      - kind: integration
        ref: "tests/integration/test_hermes_live.py::test_hermes_worker_executes_a_trivial_role_end_to_end (skipped, named reason)"
        status: pass
      - kind: other
        ref: "manual sandbox check of skip_reason() at binary-present/credential-absent and credential-present/binary-absent boundaries (see Deviations/Issues section for the exact commands run)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A guard fails when a worker registered in default_registry other than fake has no corresponding live integration module, proving the guard detects a real omission and not merely today's file layout"
    requirement: "QUAL-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_every_real_adapter_has_a_live_suite.py::test_every_real_adapter_has_a_live_suite"
        status: pass
      - kind: unit
        ref: "tests/unit/test_every_real_adapter_has_a_live_suite.py::test_the_guard_detects_a_reference_outside_the_allowed_set"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each real adapter's declared WorkerCapabilities (native_resume, structured_output, non_interactive, emits_changed_files) are checked against observed argv/result, never against a repeated literal (ROADMAP SC4)"
    requirement: "QUAL-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_worker_capabilities_match_behaviour.py (14 parametrized cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "pyproject.toml already registers the integration marker used by these modules -- running the default full suite produces no unregistered-marker error and no collection error from the three new modules"
    requirement: "QUAL-03"
    verification:
      - kind: unit
        ref: "uv run pytest -q --collect-only tests/integration/test_claude_code_live.py tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py (3 tests collected, no marker warning)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-21
status: complete
---

# Phase 8 Plan 3: Skip-Guarded Live Integration Suites & Capability Proof Summary

**Three skip-guarded live integration suites (one per real adapter) that collect everywhere and skip with a named reason when a runtime is absent, a registry-enumerated completeness guard so a fourth adapter cannot ship without one, and a unit suite pinning each adapter's declared `WorkerCapabilities` against its own observed argv and result.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-21T15:30 (approx, first file read)
- **Completed:** 2026-09-21T18:28:30+03:00
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- `tests/support/live_runtime.py` is the single shared definition of "this runtime is available": `LiveRuntime`, `LIVE_RUNTIMES` (`claude-code`/`copilot`/`hermes`), `binary_missing()`, `credential_missing()`, and `skip_reason()` -- the three live suites import from here instead of re-deriving their own skip condition.
- `tests/integration/test_claude_code_live.py`, `test_copilot_live.py`, `test_hermes_live.py` are collected in every environment (verified via `--collect-only`) and report `SKIPPED` with a reason naming both the runtime and the specific unmet precondition when the binary or credential is absent -- confirmed exactly matching QUAL-03's literal "skipped, not failed" wording, including at the binary-present/credential-absent and credential-present/binary-absent boundaries.
- `test_claude_code_live.py` closes the QUAL-03 gap Phase 7 left open: ROADMAP maps QUAL-03 to Phase 8 only, and `ClaudeCodeWorker` was previously proven only against a faked executable.
- `tests/unit/test_every_real_adapter_has_a_live_suite.py` enumerates `default_registry.names()` (minus `fake`) and asserts a non-empty live module exists per name; a self-detection test proves the guard fails on a synthetic worker name with no module, and a dedicated test pins that the Hermes live suite's grant list satisfies `spawn_is_permitted()` unconditionally (never hidden behind a skip).
- `tests/unit/test_worker_capabilities_match_behaviour.py` proves ROADMAP SC4: for the three subprocess adapters, `native_resume`, `structured_output`, and `non_interactive` are each checked against the adapter's actually-built argv (not a restated literal); `emits_changed_files` is checked for all four workers including `FakeWorker`, which is otherwise handled separately since it spawns nothing.

## Task Commits

Each task was committed atomically (test-only; see TDD Gate Compliance below for why no separate feat commit exists):

1. **Task 1: Copilot skip-guarded live suite** - `862018b` (test)
2. **Task 2: claude-code/hermes live suites + completeness guard** - `9ef52ba` (test)
3. **Task 3: WorkerCapabilities-match-behaviour proof** - `951fce7` (test)

**Plan metadata:** commit pending (this SUMMARY, applied by the orchestrator after wave merge -- worktree mode)

## TDD Gate Compliance

All three tasks carry `tdd="true"`, but every deliverable in this plan **is** test/test-support code with no corresponding production-source behavior change to red/green against (the adapters under test -- `ClaudeCodeWorker`, `CopilotWorker`, `HermesWorker` -- were fully implemented and behaviorally proven in Phases 7/08-01/08-02). There is consequently no `feat(08-03):`-prefixed commit in this plan's history -- only three `test(08-03):` commits (`862018b`, `9ef52ba`, `951fce7`), each of which passed on first run once written, because the behavior being asserted (the adapters' existing spawn/parse pipelines, and `WorkerRegistry`'s now-added `names()` accessor) was already correct at the time each test was written. This mirrors the identical, already-documented precedent in `08-01-SUMMARY.md` and `08-02-SUMMARY.md` ("tests passed immediately on first run -- a legitimate TDD outcome, not a suppressed RED") for the same underlying reason: mirror-then-diverge adapter construction across this phase means later plans frequently write tests against already-correct code. Each commit's message documents what the test module proves; no test was written to intentionally fail and then suppressed.

## Files Created/Modified
- `tests/support/live_runtime.py` - `LiveRuntime`, `LIVE_RUNTIMES`, `binary_missing()`, `credential_missing()`, `skip_reason()`
- `tests/integration/test_claude_code_live.py` - skip-guarded live suite for `ClaudeCodeWorker`, closing the Phase-7-left-open QUAL-03 gap
- `tests/integration/test_copilot_live.py` - skip-guarded live suite for `CopilotWorker`
- `tests/integration/test_hermes_live.py` - skip-guarded live suite for `HermesWorker`, plus `HERMES_LIVE_SPIKE_TOOLS` (exported grant list)
- `tests/unit/test_every_real_adapter_has_a_live_suite.py` - QUAL-03 completeness guard, enumerated from `default_registry`
- `tests/unit/test_worker_capabilities_match_behaviour.py` - ROADMAP SC4 proof, 14 parametrized cases
- `src/dark_factory/workers/registry.py` - added `WorkerRegistry.names()` (additive, mirrors `ToolRegistry.names()`)

## Decisions Made
- `skip_reason()` checks binary presence before credential presence, so a half-configured environment's message names only the one specific unmet precondition -- verified directly against both boundary cases in a manual sandbox check (see Deviations below).
- Kept the Hermes live suite's `spawn_is_permitted()` assertion out of `test_hermes_live.py` itself (its own `pytestmark` would have made that assertion skip along with everything else in the module) and placed it in the always-running guard module instead, importing the shared `HERMES_LIVE_SPIKE_TOOLS` constant rather than duplicating the grant list.
- `test_worker_capabilities_match_behaviour.py`'s non-interactive axis writes its own tiny stdin-probing fake binary locally rather than extending the shared `tests/support/fake_*_cli.py` helpers (which this plan's declared `files_modified` does not include) -- the probe is specific to this one axis.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `WorkerRegistry.names()` to `src/dark_factory/workers/registry.py`**
- **Found during:** Task 2 (writing the completeness guard)
- **Issue:** `tests/unit/test_every_real_adapter_has_a_live_suite.py` must enumerate live-suite obligations from `default_registry` per this plan's own `key_links` ("the registry is the source of truth for which adapters exist"), but `WorkerRegistry` exposed no accessor for its registered names -- only `ToolRegistry` (a different registry) had `names()`.
- **Fix:** Added `WorkerRegistry.names() -> frozenset[str]`, mirroring `ToolRegistry.names()`'s exact shape and docstring style; this is explicitly pre-authorized by Task 2's own `<action>` text ("If `WorkerRegistry` exposes no way to list its registered names, add a `names() -> set[str]` method"). `src/dark_factory/workers/registry.py` is outside this plan's originally declared `files_modified` list, but the addition is purely additive (a new method, zero behavioral change to any existing call site) and no other plan in this wave (08-04) touches the file.
- **Files modified:** `src/dark_factory/workers/registry.py`
- **Verification:** `uv run pytest -m "unit or contract" -q` green (601 passed, 1 skipped); `uv run mypy src/dark_factory` shows only the 2 pre-existing, unrelated `mcp_transport.py` errors also present in the 08-01/08-02 baseline.
- **Commit:** `9ef52ba` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical addition, explicitly pre-authorized by the plan's own task text)
**Impact on plan:** Necessary and anticipated by the plan itself; no scope creep beyond what Task 2's action text already contemplated.

## Issues Encountered

Task 1's acceptance criteria include two boundary conditions (binary-present/credential-unset, and credential-set/binary-absent) that are properties of `skip_reason()` rather than behaviors observable from a normal `pytest` run in this sandbox (both preconditions are absent here, so the suite only ever exercises the "neither present" branch through the collected tests). These were verified directly with a one-off Python script exercising `tests.support.live_runtime.skip_reason()` against a temporary fake-`copilot`-on-`PATH` directory and a monkeypatched `COPILOT_GITHUB_TOKEN`, confirming:
- binary present + credential unset -> message contains `copilot_github_token`, does not contain "not found on PATH"
- credential present + binary absent -> message contains `'copilot' not found on PATH`, does not contain `copilot_github_token` or `Settings.`

Both matched the acceptance criteria exactly. This is recorded as coverage `D1`'s `other`-kind verification entry above rather than left undocumented, since it is not otherwise captured by an automated test in this sandbox (no CI running with the real `copilot` binary would exercise these two specific boundary states either, absent a dedicated unit test of `live_runtime.py` itself, which this plan's `files_modified` scope did not include as a separate file).

## User Setup Required
None - no external service configuration required. A live `claude`/`copilot`/`hermes` binary and its corresponding credential (`ANTHROPIC_API_KEY` / `COPILOT_GITHUB_TOKEN` / `ANTHROPIC_API_KEY`) are needed only to exercise the non-skip branch of each live suite -- exactly what QUAL-03's skip-when-absent design defers, per D-02.

## Next Phase Readiness
- QUAL-03 is closed for all three real adapters, including the retroactive `claude-code` gap Phase 7 left open.
- ROADMAP SC4 (declared capabilities match observed behaviour) is proven for all three subprocess adapters plus `FakeWorker`'s observable axes.
- The three live suites will begin exercising their real-binary branch automatically -- with zero code change -- the day `claude`/`copilot`/`hermes` are installed with valid credentials in any environment running this suite (D-02's deferred live spike).
- `WorkerRegistry.names()` is now available for any future plan needing to enumerate registered worker names from the registry rather than a hand-maintained list.
- No blockers identified. 08-04 (role-reassignment SC2 proof) runs concurrently in a sibling worktree with no file overlap against this plan.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-21*

## Self-Check: PASSED

- All 6 `key-files.created` verified present on disk (`tests/support/live_runtime.py`, `tests/integration/test_claude_code_live.py`, `tests/integration/test_copilot_live.py`, `tests/integration/test_hermes_live.py`, `tests/unit/test_every_real_adapter_has_a_live_suite.py`, `tests/unit/test_worker_capabilities_match_behaviour.py`).
- All 3 task commit hashes (`862018b`, `9ef52ba`, `951fce7`) confirmed in `git log --oneline --all`.
- `uv run pytest -m "unit or contract" -q`: 601 passed, 1 skipped (pre-existing, unrelated `mcp` optional-dependency skip) -- up from 08-02's baseline of 582, consistent with 5 (guard module) + 14 (capability-behaviour module) new tests.
- `uv run pytest -q -rs tests/integration/test_claude_code_live.py tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py`: 3 skipped, 0 failed, 0 errored, each with a named reason.
- `uv run pytest -q --collect-only` on the three live modules: 3 tests collected (never zero, never excluded).
- `uv run mypy src/dark_factory`: 0 new errors (2 pre-existing errors in the untouched `tools/mcp_transport.py`, identical to the 08-01/08-02 baseline).
- `uv run ruff check .`: all checks passed.
- Plan-level acceptance criteria (all three tasks) and the `<verification>` block re-passed in full, including the manual boundary-condition check described under Issues Encountered.
