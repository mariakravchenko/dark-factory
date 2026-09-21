---
phase: 08-copilot-hermes-worker-independence-proven
plan: 02
subsystem: workers
tags: [hermes-cli, subprocess-worker, cli-adapter, credential-boundary, native-tool-contract, tdd]

requires:
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "CopilotWorker's proven spawn/timeout/redact/NEEDS_INPUT pipeline (cli_runtime.py) and the mirror-then-diverge adapter-construction pattern (08-01) -- the literal structural template this plan extracts and reuses for the third runtime."
provides:
  - "HermesWorker, a real CodingWorker adapter registered as `hermes`, replacing the last _NotYetImplementedWorker placeholder (D-04) -- default_registry now resolves all four names to real workers"
  - "spawn_is_permitted() / UnenforceableGrantError -- the checkpoint's Option A spawn-admission rule: a role denied a NATIVE_TOOL_CONTRACT capability with no compensating post-hoc control is refused before anything is spawned; the two write capabilities are exempted because enforce_write_scope (ROLE-05) independently holds that boundary"
  - "role_worker_root() in tools/env.py -- the extracted formula build_worker_env already computed inline, now nameable so an adapter can place a non-XDG state directory (HERMES_HOME) inside the same disposable root"
  - "tests/support/fake_hermes_cli.py -- the faked-executable-on-PATH test harness for Hermes, mirroring fake_copilot_cli.py"
  - "tests/contract/test_coding_worker_contract.py now runs all four workers (FakeWorker, ClaudeCodeWorker, CopilotWorker, HermesWorker) against a shared fake-CLI fixture -- ROADMAP SC3, QUAL-02"
affects: [08-03-live-integration-suites, 08-04-role-reassignment-sc2]

actuals:
  tokens: 17330
  tasks: 2
  commits: 7

tech-stack:
  added: []
  patterns:
    - "Narrowed native-tool refusal rule: a module-level frozenset naming the write-compensated capabilities, checked with a subset-of-contract guard function so a renamed/removed NATIVE_TOOL_CONTRACT capability fails a unit test instead of silently widening or narrowing the compensated set."
    - "None-context exemption for spawn-admission: the shared CodingWorker contract suite's execute(None)/resume(None, ...) call shape is recognized explicitly and exempted from a check that would otherwise treat it as a genuine 'denied every capability' grant."

key-files:
  created:
    - src/dark_factory/workers/hermes.py
    - tests/support/fake_hermes_cli.py
    - tests/unit/test_hermes_worker.py
  modified:
    - src/dark_factory/tools/env.py
    - src/dark_factory/tools/native.py
    - src/dark_factory/workers/registry.py
    - tests/unit/test_native_tool_contract.py
    - tests/contract/test_coding_worker_contract.py
    - tests/unit/test_worker_registry_names.py

key-decisions:
  - "Selected Option A for the Hermes native-restriction-rule checkpoint -- narrowed NATIVE_TOOL_CONTRACT's Hermes absent_behaviour clause to distinguish two cases: for repo.write and repo.write_tests, denial is compensated after the fact by enforce_write_scope (ROLE-05), which reverts and fails any changed path outside the role's configured write_scope (including the zero-tolerance empty scope), so the adapter may spawn and let that control hold the boundary; for the other five capabilities (repo.read, repo.search, shell.execute, artifacts.read, artifacts.write) no post-hoc control exists, so the refusal stands and the adapter must not spawn. spawn_is_permitted() implements exactly that split. Rationale: the contract's underlying principle -- 'an adapter that cannot enforce a restriction natively must not claim that it can' -- is preserved; the amended prose still refuses to claim native enforcement, it just names the real, already-shipped control that holds the write boundary instead of pretending no control exists. This unblocks D-04's locked QA -> hermes assignment (08-04) without contradicting Phase 6 SC1 ('QA can write tests but cannot publish') or the deliberate 06-01 D-16 decision to withhold repo.write from QA. Options B (change the SC2 assignment) and C (grant QA repo.write) were rejected because each breaks a decision made deliberately and recorded."
  - "role_worker_root() extracted as a pure, behavior-preserving move ahead of any Hermes-specific code, so build_worker_env's existing test coverage doubles as the refactor's regression proof before HERMES_HOME isolation is layered on top."
  - "HermesWorker never adopts the CLI's own --resume flag: 08-RESEARCH.md Open Question 1 records that no fetched source confirms it completes headlessly when combined with --oneshot and -q, so adopting it could hang an attempt until the worker timeout. capabilities().native_resume stays False and resume() has a single context-reconstruction branch, mirroring CopilotWorker's identical judgment call."

patterns-established:
  - "Pattern: mirror-then-diverge adapter construction, third application -- HermesWorker copies CopilotWorker's proven spawn/timeout/redact/parse structure verbatim, changing only argv construction, the credential name (reused, not new), and the HERMES_HOME isolation step."

requirements-completed: [WORK-06]

coverage:
  - id: D1
    description: "HermesWorker spawns the hermes CLI non-interactively and normalizes COMPLETED/empty-output results, replacing the last registry placeholder"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_execute_returns_completed_with_summary_and_no_session_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_execute_empty_stdout_returns_completed_with_empty_summary"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_default_registry_returns_a_hermes_worker_instance"
        status: pass
    human_judgment: false
  - id: D2
    description: "The built argv begins with hermes/chat, contains -q/--oneshot/-Q/--ignore-user-config and the prompt, and never contains the interactive-terminal flag (--tui)"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_argv_contains_required_flags_and_prompt"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_argv_disjoint_from_forbidden_flags"
        status: pass
    human_judgment: false
  - id: D3
    description: "HERMES_HOME is isolated per role under the same disposable root as XDG_CONFIG_HOME, so Hermes state cannot travel between roles or reach the operator's real home directory"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_hermes_home_is_under_the_same_root_as_xdg_config_home"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_two_roles_observe_two_different_hermes_home_values"
        status: pass
    human_judgment: false
  - id: D4
    description: "Credential-bounded subprocess environment: ANTHROPIC_API_KEY reaches the child, DATABASE_URL/GITHUB_TOKEN never do, and a missing credential fails before spawning"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_subprocess_env_has_credential_and_lacks_infra_secrets"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_missing_credential_returns_failed_and_spawns_nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "spawn_is_permitted() implements the checkpoint's Option A rule: fully-granted roles and the shipped QA grant (denied only repo.write) are permitted; a role denied a non-compensated capability is refused before anything is spawned, naming the capability"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_spawn_is_permitted_returns_none_for_a_fully_granted_role"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_spawn_is_permitted_allows_the_shipped_qa_grant_list"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_a_denied_non_compensated_capability_produces_failed_and_spawns_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_a_none_context_is_exempted_from_spawn_admission"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every failure path (timeout with process-group kill, non-zero exit over three documented codes, missing binary) becomes a FAILED WorkerResult, never a raised exception"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_timeout_kills_process_group_and_persists_output"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_non_zero_exit_returns_failed_with_exit_code_and_stderr[1,2,75]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_missing_hermes_binary_returns_failed_without_raising"
        status: pass
    human_judgment: false
  - id: D7
    description: "resume() reconstructs context (no native session branch), NEEDS_INPUT marker variants parse correctly, and captured transcripts are redacted before persistence"
    requirement: "WORK-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_resume_reconstructs_context_no_resume_flag"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_needs_input_marker_produces_needs_input_with_question"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py#test_captured_output_is_redacted"
        status: pass
    human_judgment: false
  - id: D8
    description: "The shared CodingWorker contract suite passes for all four workers with no live binary and no live credential, including both credential env vars unset in the ambient environment"
    requirement: "WORK-06"
    verification:
      - kind: contract
        ref: "tests/contract/test_coding_worker_contract.py (WORKER_FACTORIES == 4, 26 parametrized tests)"
        status: pass
      - kind: contract
        ref: "env -u ANTHROPIC_API_KEY -u COPILOT_GITHUB_TOKEN uv run pytest -m contract -q tests/contract/test_coding_worker_contract.py"
        status: pass
    human_judgment: false

duration: 16min
completed: 2026-09-21
status: complete
---

# Phase 8 Plan 2: HermesWorker -- The Third Real Agent Runtime Summary

**`HermesWorker` spawns the real `hermes` CLI through the shared `cli_runtime.py` pipeline, reuses `Settings.anthropic_api_key` rather than inventing a new credential field, isolates `HERMES_HOME` per role, and implements a checkpoint-decided spawn-admission rule (`spawn_is_permitted`) so a role denied a capability with no compensating control can never be run -- completing the three-real-runtime set and emptying `WorkerRegistry` of placeholders.**

## Performance

- **Duration:** 16 min (active implementation and verification work; a provider rate limit paused the session between the implementation commits and this resume, with no new code required on resume -- see Issues Encountered)
- **Started:** 2026-09-21T15:53:30+03:00
- **Completed:** 2026-09-21T18:08:22+03:00 (wall-clock, includes the interruption pause)
- **Tasks:** 2 (plus one preparatory refactor commit)
- **Files modified:** 9

## Accomplishments
- `HermesWorker` (`src/dark_factory/workers/hermes.py`) is a real, working `CodingWorker` adapter: spawns `hermes chat --oneshot -Q --ignore-user-config -q "<prompt>"`, normalizes plain-text stdout into a `WorkerResult`, and never raises out of `execute()`/`resume()`.
- No new credential field was added: Hermes reuses `Settings.anthropic_api_key` because it is multi-provider and documents that key among its own recognised provider keys (08-RESEARCH.md Finding 1) -- `MissingWorkerCredentialError`'s message states this so a reader who expected a Hermes-specific field learns from the error itself why none exists.
- `HERMES_HOME` is isolated per role under the same disposable root `build_worker_env`'s `XDG_*` entries already use (`role_worker_root()`, extracted from `tools/env.py`), so the operator's real home-directory Hermes state is never read or written, and two roles never share state (08-RESEARCH.md Pitfall 3).
- The checkpoint's Option A decision is implemented exactly as specified: `spawn_is_permitted()` refuses to spawn for any capability whose denial has no post-hoc compensating control, while the two write capabilities (`repo.write`, `repo.write_tests`) are admitted because `enforce_write_scope` (ROLE-05) independently holds that boundary -- proven against both a fully-granted role and the shipped `QA.yaml` grant list (denied only `repo.write`).
- Every Hermes failure path (timeout + process-group kill, non-zero exit over three documented exit codes with no special-casing, missing binary, missing credential, a blocked spawn-admission check) returns `FAILED`, never an exception.
- `resume()` reconstructs context because `native_resume=False` is a documented judgment call, not a placeholder: 08-RESEARCH.md Open Question 1 records that no fetched source confirms the CLI's own `--resume` flag completes headlessly combined with `--oneshot`/`-q`, so adopting it was deliberately not attempted this phase.
- The shared `CodingWorker` contract suite now runs all four workers -- `FakeWorker`, `ClaudeCodeWorker`, `CopilotWorker`, `HermesWorker` -- with no live binary and no live credential, verified green even with both `ANTHROPIC_API_KEY` and `COPILOT_GITHUB_TOKEN` unset in the invoking environment (ROADMAP SC3, QUAL-02).

## Task Commits

Each task was committed atomically (TDD RED/GREEN per task, plus one preparatory refactor commit):

1. **Preparatory refactor: extract `role_worker_root()` and narrow the Hermes write-capability rule (checkpoint Option A)** - `dce352f` (refactor)
2. **Task 1: One role runs end to end through the real `hermes` CLI, state isolated per role** - `3542fc3` (test, RED) -> `fcc38cd` (feat, GREEN)
3. **Task 2: Every Hermes failure path becomes a FAILED result, contract suite runs all four workers** - `d4ee458` (test) -> `3991f70` (feat, GREEN)
4. **Alignment fix: timeout test literal matches the plan's stated 2-second acceptance criterion** - `4efabbf` (test)

**Plan metadata:** this SUMMARY commit (STATE/ROADMAP applied by the orchestrator after wave merge -- worktree mode)

_Note: Task 2's entire failure-path/resume/redaction/contract-suite-wiring matrix (timeout, three parametrized non-zero-exit codes, missing binary, three NEEDS_INPUT variants, resume, redaction, and `WORKER_FACTORIES` growing to all four workers) passed immediately against Task 1's implementation on first run -- a legitimate TDD outcome, since `HermesWorker` already mirrors `CopilotWorker`'s proven pipeline for every one of those paths (identical to 08-01 Task 2's own experience, noted in that plan's SUMMARY). The one genuine RED in that commit was `test_a_none_context_is_exempted_from_spawn_admission`: the contract suite's `execute(None)`/`resume(None, ...)` call shape degrades to an empty `tools=[]` grant, which Task 1's literal `spawn_is_permitted` call blocked -- `3991f70` made it GREEN by exempting a `None` context from the admission check explicitly, with its own pinning test._

## Files Created/Modified
- `src/dark_factory/workers/hermes.py` - `HermesWorker`, `MissingWorkerCredentialError`, `UnenforceableGrantError`, `spawn_is_permitted()`, module constants
- `src/dark_factory/tools/env.py` - `role_worker_root(role) -> Path` extracted from `build_worker_env`'s inline formula
- `src/dark_factory/tools/native.py` - Hermes `absent_behaviour` clauses narrowed for `repo.write`/`repo.write_tests` (checkpoint Option A); docstring records the conflict and the compensating control
- `src/dark_factory/workers/registry.py` - `"hermes"` now registers the real `HermesWorker` class; `_NotYetImplementedWorker` and its `NoReturn` import removed (no name in `default_registry` resolves to a placeholder any more)
- `tests/support/fake_hermes_cli.py` - faked `hermes` executable-on-PATH test harness
- `tests/unit/test_hermes_worker.py` - full behavior suite for `HermesWorker` (30 tests)
- `tests/unit/test_native_tool_contract.py` - `hermes.py` added to `_ALLOWED_CONSUMERS`
- `tests/contract/test_coding_worker_contract.py` - `HermesWorker` added to `WORKER_FACTORIES`; fixture extended to install all three fake CLIs in one temp `PATH` dir
- `tests/unit/test_worker_registry_names.py` - `hermes` placeholder test replaced with a real-adapter test (Rule 1 fix, see Deviations)

## Decisions Made

**Checkpoint decision: Option A (narrow the refusal rule to capabilities with no compensating control).**

`NATIVE_TOOL_CONTRACT` stated, for all seven capabilities, that Hermes "documents no per-tool native restriction flag" and that "the adapter must not spawn Hermes for a role denied this grant at all." Read literally, that rule admits Hermes only for a role holding every capability -- but `.dark-factory/roles/QA.yaml` deliberately withholds `repo.write` (Phase 6 SC1's "QA can write tests but cannot publish" half, D-16), so the literal rule would block D-04's locked `QA -> hermes` assignment (08-04) forever. This was a genuine conflict between a locked user decision and a published Phase-6 design contract, surfaced at a blocking checkpoint rather than silently resolved inside the adapter.

Selected Option A: amend `NATIVE_TOOL_CONTRACT`'s Hermes `absent_behaviour` clause so it distinguishes two cases. For `repo.write` and `repo.write_tests`, denial is compensated after the fact by `enforce_write_scope` (ROLE-05), which reverts and fails any changed path outside the role's configured `write_scope` -- including the zero-tolerance empty scope -- so the adapter may spawn and let that control hold the boundary. For the other five capabilities (`repo.read`, `repo.search`, `shell.execute`, `artifacts.read`, `artifacts.write`), no post-hoc control exists, so the refusal stands and the adapter must not spawn. `spawn_is_permitted()` implements exactly that split, with a module-level `_WRITE_COMPENSATED_CAPABILITIES` frozenset and a subset-of-contract guard test so a renamed or removed capability fails a unit test rather than silently widening or narrowing the compensated set.

Rationale: the contract's underlying principle -- "an adapter that cannot enforce a restriction natively must not claim that it can" -- is preserved. The amended prose still refuses to claim native enforcement; it just names the real, already-shipped control that holds the write boundary instead of pretending no control exists. Option B (change the SC2 assignment) was rejected because it contradicts locked decision D-04 and ROADMAP SC2's own literal example. Option C (grant QA `repo.write`) was rejected because it directly contradicts Phase 6 SC1 and the deliberate 06-01 D-16 decision.

**Other decisions:**
- `role_worker_root()` was extracted as its own preparatory, behavior-preserving commit before any Hermes-specific code, so `build_worker_env`'s existing test coverage (`test_worker_env.py`, `test_no_environ_copy.py`) doubles as the refactor's regression proof.
- `HermesWorker._resume()` never adopts the CLI's own `--resume` flag and has only a context-reconstruction branch: 08-RESEARCH.md Open Question 1 records no fetched source confirms it completes headlessly combined with `--oneshot -q`, so adopting it could hang an attempt until the worker timeout. This is named as the first thing a deferred live spike (D-02) should falsify.
- A `None` context (the shared contract suite's `execute(None)`/`resume(None, ...)` call shape) is explicitly exempted from `spawn_is_permitted`, because it is never a configured role -- only a real `RoleContext` with a genuinely empty `tools` list is a "denied every capability" grant the admission rule must block.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated a pre-existing test that asserted `hermes` still raised `NotImplementedError`**
- **Found during:** Task 1 full-suite verification (`pytest -m "unit or contract" -q`)
- **Issue:** `tests/unit/test_worker_registry_names.py`'s parametrized Phase-8-placeholder test asserted `hermes` still raised `NotImplementedError` naming "Phase 8" -- an assumption this plan's own registry change (`hermes` now resolves to a real adapter) directly invalidates.
- **Fix:** Removed the `hermes` case from that parametrization and added `test_hermes_resolves_to_a_real_adapter_not_a_placeholder`, mirroring the existing `claude-code`/`copilot` real-adapter tests exactly.
- **Files modified:** `tests/unit/test_worker_registry_names.py`
- **Verification:** Full `pytest -m "unit or contract" -q` green (582 passed, 1 skipped) after the fix.
- **Commit:** `fcc38cd` (part of Task 1's GREEN commit)

**2. [Rule 1 - Bug] Fixed a docstring naming a specific worker runtime outside `workers/`**
- **Found during:** Task 1 full-suite verification
- **Issue:** `role_worker_root()`'s initial docstring in `tools/env.py` named "Hermes" directly, violating `tests/unit/test_no_worker_name_leak.py`'s guard that no file outside `workers/` names a specific worker runtime (the tool layer must stay worker-agnostic).
- **Fix:** Rewrote the docstring to describe the mechanism generically (a role-scoped disposable root an adapter can point non-XDG state at) without naming Hermes.
- **Files modified:** `src/dark_factory/tools/env.py`
- **Verification:** `tests/unit/test_no_worker_name_leak.py` passes.
- **Commit:** `fcc38cd` (part of Task 1's GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 bugs -- one outdated test assumption directly caused by this plan's own registry change, one guard-test violation caught by an existing test)
**Impact on plan:** Both are necessary corrections directly triggered by this plan's own edits; no scope creep.

## Issues Encountered

A previous execution attempt at this exact plan completed all of Task 1 and Task 2 (6 commits, `dce352f` through `4efabbf`) before being cut off mid-session by a provider rate limit -- not a real failure, just an interruption before this SUMMARY.md was written. This resume verified the prior work was sound (re-ran every `<verify>` command from the plan, the full plan-level `<verification>` block, and all acceptance criteria for both tasks) and found it complete and correct with no code changes needed. The six prior commits were brought in via a clean fast-forward merge (`git merge --ff-only`) from a direct linear ancestor, with zero divergence.

## User Setup Required
None - no external service configuration required. (A live `hermes` binary and a real `ANTHROPIC_API_KEY` are needed only for the live-integration suite 08-03 will add; this plan's entire test surface runs against a faked executable, per D-02.)

## Next Phase Readiness
- `HermesWorker` is a complete, tested, registered adapter -- the three-real-runtime set is now complete and `default_registry` has no remaining placeholders (D-04).
- 08-03 (live integration suites, skip-guarded) and 08-04 (the SC2 role-reassignment proof, which needs `.dark-factory/roles/QA.yaml` reassigned to `worker: hermes`) can both proceed: `spawn_is_permitted()` already proves the shipped `QA.yaml` grant list is permitted under the checkpoint's Option A rule.
- `tests/contract/test_coding_worker_contract.py` now covers all four workers -- no adapter can silently drift from the shared contract without a future addition being caught by `test_all_four_workers_are_registered_in_the_contract_suite`.
- No blockers identified.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-21*

## Self-Check: PASSED

- All 3 `key-files.created` verified present on disk (`src/dark_factory/workers/hermes.py`, `tests/support/fake_hermes_cli.py`, `tests/unit/test_hermes_worker.py`).
- All 6 implementation commit hashes (`dce352f`, `3542fc3`, `fcc38cd`, `d4ee458`, `3991f70`, `4efabbf`) confirmed in `git log --oneline --all`.
- `pytest -m unit -q tests/unit/test_hermes_worker.py`: 30 passed.
- `pytest -m contract -q tests/contract/test_coding_worker_contract.py`: 26 passed (including with `ANTHROPIC_API_KEY`/`COPILOT_GITHUB_TOKEN` both unset).
- `pytest -m "unit or contract" -q` (full suite): 582 passed, 1 skipped (pre-existing, unrelated `mcp` optional-dependency skip).
- `uv run mypy src/dark_factory`: 0 new errors (2 pre-existing errors in an untouched module, `tools/mcp_transport.py`).
- `uv run ruff check .`: all checks passed.
- Plan-level acceptance criteria (both tasks) and the `<verification>` block re-passed in full.
