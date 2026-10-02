---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 08
subsystem: testing
tags: [settings, pydantic-settings, ast-guard, publish, idempotency, gap-closure]

requires:
  - phase: 10
    provides: run_publish_step's idempotency contract (GIT-04, D-06) and its existing known_secrets parameter precedent
provides:
  - run_publish_step with no settings import and no get_settings() call -- the push token arrives as an explicit, non-defaulted push_token parameter
  - runner.py's single call site threading the token from the gate_settings object it already holds
  - a named test proving the supplied push_token is the exact value push_working_branch receives
  - tests/unit/test_global_settings_reads_are_declared.py -- an 18-entry, bidirectionally-checked AST inventory of every remaining get_settings() call site under src/dark_factory/
affects: [11-09, 11-10]

actuals:
  tokens: 6771
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "AST scope-stack walk keyed by (relative-path, enclosing-function-qualname, per-scope occurrence counter) -- never a line number -- as the declared-inventory key for a process-global accessor"

key-files:
  created:
    - tests/unit/test_global_settings_reads_are_declared.py
  modified:
    - src/dark_factory/orchestrator/publish.py
    - src/dark_factory/orchestrator/runner.py
    - tests/unit/test_publish_idempotency.py
    - tests/unit/test_publish_step_unit.py
    - tests/db/test_publish_idempotency.py

key-decisions:
  - "The inventory key is (relative path, enclosing-function dotted qualname, 1-based per-scope occurrence counter), not bare (path, qualname). Under scope-tracking alone, orchestrator/runner.py's three get_settings() calls inside _run_current_role all share one qualname and collapse to a single set element (16 unique keys total, not 18). The plan's own <behavior>/<done> criteria state '18 entries across 12 modules' and '19 exist today' -- both exactly match raw call-site cardinality, and the plan's construction notes explicitly describe three *distinct* orchestrator/runner.py entries. An occurrence suffix is the only mechanism that satisfies the stated cardinality while still never embedding a raw line number (the suffix only shifts when a call is added/removed in that same enclosing scope -- itself the deliberate edit this guard exists to flag)."
  - "Reused tests/conftest.py's exact fake-GitHub-token shape (ghp_FAKE...) for every new greppable push-token constant across the three edited test files, per T-11-33's mitigation requirement, rather than inventing a new spelling."
  - "push_token is passed None (not a placeholder string) on every call site that provably does not reach the push -- the fast path, the create_pr=False early return, and the point-b 'already pushed, pr unrecorded' scenarios -- making the asymmetry self-documenting per the plan's own instruction."

patterns-established:
  - "Declared-inventory AST guards for a named process-global accessor key by (path, enclosing-scope qualname, per-scope occurrence), bidirectionally set-equal-checked against the real discovered set, with a positive control proving the collector is non-vacuous."

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "run_publish_step takes a required keyword-only push_token: str | None and contains neither a settings import nor a get_settings() call"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py (9 call sites) + tests/unit/test_publish_step_unit.py (4 call sites) + tests/db/test_publish_idempotency.py (1 call site), all updated to the new signature"
        status: pass
      - kind: unit
        ref: "grep 'from dark_factory.config.settings import get_settings' src/dark_factory/orchestrator/publish.py -- zero matches"
        status: pass
    human_judgment: false
  - id: D2
    description: "runner.py's one call site derives the token from the gate_settings object already in scope, adding no new get_settings() call"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_global_settings_reads_are_declared.py::test_declared_settings_reads_match_discovered_calls (orchestrator/runner.py's three remaining calls are unchanged at #1/#2/#3, no fourth appears)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The six publish unit tests G-11-3 names pass under an environment with both database variables absent and a working directory with no readable .env, with no settings mocking"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "env -u DATABASE_URL -u DATABASE_URL_DIRECT, cwd=fresh tempdir, pytest -m 'unit or contract' tests/unit/test_publish_idempotency.py tests/unit/test_publish_step_unit.py -- 14 passed"
        status: pass
    human_judgment: false
  - id: D4
    description: "One named test asserts the token passed as push_token is the token push_working_branch receives"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py::test_push_working_branch_receives_the_token_the_caller_supplied"
        status: pass
    human_judgment: false
  - id: D5
    description: "tests/unit/test_global_settings_reads_are_declared.py declares all 18 remaining call sites across 12 modules, compares both directions, carries a positive control, and names the publish module in no declared key"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_global_settings_reads_are_declared.py -- 5 tests, all pass (bidirectional equality, cardinality pin, no-publish-key, two positive controls)"
        status: pass
    human_judgment: false
  - id: D6
    description: "pytest -q -m 'unit or contract', mypy src/dark_factory, ruff check . and ruff format --check . are green (modulo pre-existing, unrelated findings documented below)"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "uv run pytest -q -m 'unit or contract' -- 835 passed, 1 skipped, 374 deselected, 1 pre-existing unrelated failure (see Deviations)"
        status: pass
      - kind: other
        ref: "uv run mypy src/dark_factory -- clean except pre-existing tools/mcp_transport.py import-not-found (unrelated, pre-existing at HEAD before this plan)"
        status: pass
      - kind: other
        ref: "uv run ruff check . -- all checks passed"
        status: pass
      - kind: other
        ref: "uv run ruff format --check . -- pre-existing 19-file formatting debt at HEAD before this plan (two of the touched files are among them, at lines this plan did not edit); no files this plan's own edits introduced are newly unformatted"
        status: pass
    human_judgment: true
    rationale: "'Green' required a judgment call distinguishing this plan's own changes from two pre-existing, unrelated conditions (a flaky worker-registry test and a repo-wide ruff-format debt) that predate this plan and are out of its file scope -- documented explicitly below rather than silently absorbed into 'pass'."

duration: ~70min (task-commits + implementation ~30min; verification wait ~40min: 4m25s full unit/contract tier, 3m isolate-rerun of the known outlier, 3m05s db-tier rerun)
completed: 2026-10-02
status: complete
---

# Phase 11 Plan 08: Push-Token Parameter Threading + Settings-Read Inventory Summary

**`run_publish_step`'s push token now arrives as a required keyword parameter sourced from the caller's already-held `Settings` object, and a new 18-entry AST-walked inventory makes every other process-global `get_settings()` read under `src/dark_factory/` a declared, bidirectionally-checked fact rather than an invisible landmine.**

## Performance
- **Duration:** ~70min (implementation/commits ~30min; verification wait ~40min)
- **Started:** 2026-10-02 (session start)
- **Completed:** 2026-10-02T08:11:00Z (commits), verification through ~2026-10-02T08:25:00Z
- **Tasks:** 2/2 completed
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- Removed the last hidden process-global settings read from `run_publish_step` (`orchestrator/publish.py`) -- it now takes a required, non-defaulted `push_token: str | None` keyword parameter, matching its existing `known_secrets` precedent, and contains no settings import at all.
- Wired the one production call site in `runner.py` to derive the token from the already-in-scope `gate_settings` object, using the identical `get_secret_value()`-if-not-`None` shape the artifact-commit branch already used a hundred lines earlier -- zero new `get_settings()` calls introduced.
- Added a new named test proving the token threading is a tested fact (`test_push_working_branch_receives_the_token_the_caller_supplied`), not an assumption.
- Built `tests/unit/test_global_settings_reads_are_declared.py`: an AST scope-stack walk over every `.py` file under `src/dark_factory/`, keyed by `(relative-path, enclosing-function-qualname, per-scope occurrence)`, asserting bidirectional set equality against an 18-entry declared inventory across 12 modules, with two positive controls proving the collector is non-vacuous and structurally distinguishes a call from a definition.
- Closed 6 of G-11-3's 12 reported CI failures (the `orchestrator/publish.py` production sink); the remaining 6 (logging.py's structlog sinks, `test_clarification_comment.py`'s `_run_current_role` sink, and the latent `tests/support/live_runtime.py` sibling) belong to plan 11-09, which runs in the same wave and shares no file with this plan.

## Task Commits
1. **Task 1: The push token arrives as a parameter, like every other settings-derived value this function takes** - `50ebbdc` (fix)
2. **Task 2: One declared inventory of every process-global settings read in the package** - `7e9a76d` (test)

## Files Created/Modified
- `src/dark_factory/orchestrator/publish.py` - `run_publish_step` gains a required `push_token: str | None` keyword-only parameter; the settings import and the three-line `get_settings()`/`get_secret_value()` block are deleted; the Stage-3 docstring paragraph now describes the parameter instead of a settings-attribute read.
- `src/dark_factory/orchestrator/runner.py` - the one `run_publish_step` call site passes `push_token=gate_settings.github_token.get_secret_value() if gate_settings.github_token is not None else None`; no new `get_settings()` call.
- `tests/unit/test_publish_idempotency.py` - all 9 `run_publish_step(` call sites updated with an explicit `push_token` (fake value on paths that push, `None` on paths that provably do not); `_install_git_spies` gained an optional `received_tokens` recording channel; new test `test_push_working_branch_receives_the_token_the_caller_supplied`; module docstring's opening sentence corrected to state the module constructs no `Settings` at all, not merely "no database".
- `tests/unit/test_publish_step_unit.py` - all 4 `run_publish_step(` call sites updated with an explicit `push_token`.
- `tests/db/test_publish_idempotency.py` - the single `run_publish_step(` call site updated with `push_token=None` (the fast-path scenario it drives never pushes).
- `tests/unit/test_global_settings_reads_are_declared.py` (new) - the AST collector, the 18-entry declared inventory grouped by category in the module docstring, the bidirectional-equality test, a cardinality pin, a no-publish-key assertion, and two positive controls.

## Decisions Made
See `key-decisions` in frontmatter. The most consequential one: the inventory key had to include a per-scope occurrence counter (not bare `path::qualname`) to make the discovered-set cardinality match the plan's own stated "18 entries / 19 exist today" -- under pure scope-tracking, `orchestrator/runner.py`'s three `_run_current_role` reads collapse to one key, yielding 16, not 18. This is documented in detail in the test module's own docstring and in `key-decisions` above, since it is a load-bearing interpretation of ambiguous plan prose rather than a literal transcription.

## Deviations from Plan

### Auto-fixed Issues

None - both tasks' production and test changes matched the plan's `<action>` steps exactly; no Rule 1/2/3 fixes were needed.

### Noted, not fixed (out of scope)

**1. [Scope boundary] Pre-existing, unrelated test failure: `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`**
- **Found during:** the phase-level `pytest -q -m "unit or contract"` verification run.
- **Issue:** this test asserts `ClaudeCodeWorker.execute({})` returns `FAILED` when no `ANTHROPIC_API_KEY` is configured. In this execution sandbox, a live `ANTHROPIC_API_KEY` is present (via `.env`), so the worker actually calls the real API and returns `COMPLETED`, failing the assertion.
- **Confirmed pre-existing:** reproduced identically with `git stash` applied (i.e. at the commit before this plan's changes) -- `1 failed` with the exact same traceback, before any of this plan's edits existed.
- **Why not fixed:** the file is not in this plan's `files_modified`, has nothing to do with settings reads, publish, or G-11-3, and is a Phase 7/8 environmental test-design gap (the test should inject a seam rather than depend on ambient credential absence). Fixing it is out of this plan's scope boundary.
- **Action:** noted here; not fixed; not filed to WINDOWS.md since it is an environment-specific sandbox condition (ambient `ANTHROPIC_API_KEY`), not a reproducible defect in the committed tree under CI's own unconfigured conditions.

**2. [Scope boundary] Pre-existing repo-wide `ruff format --check .` debt (19 files)**
- **Found during:** the phase-level `ruff format --check .` verification run.
- **Issue:** 19 files across the repository are not `ruff format`-clean, including `tests/unit/test_publish_idempotency.py` and `tests/db/test_publish_idempotency.py` (two files this plan edited).
- **Confirmed pre-existing:** reproduced identically with `git stash` applied -- both files were already unformatted at the exact same source lines (the pre-existing `_OrderedFakeGitHubClient`/`_HeadScopedFakeGitHubClient` `super().find_pull_request_for_branch(...)` lines and a pre-existing `_install_failing_git_spies` signature line this plan never touched) before any of this plan's edits existed.
- **Why not fixed:** reformatting 19 files (17 of which this plan never touched) is out of scope; the lines this plan's own edits added are themselves `ruff format`-clean (confirmed with a targeted `ruff format --check` on the new inventory file alone: "1 file already formatted").
- **Action:** noted here; not fixed; carried as a pre-existing repo-wide hardening item.

**Total deviations:** 0 auto-fixed, 2 pre-existing/out-of-scope conditions documented and left untouched. **Impact:** none on this plan's own deliverables; both conditions predate this plan and are reproducibly independent of its changes.

## Issues Encountered

None beyond the two pre-existing, out-of-scope conditions documented above.

## Exact 18 Inventory Keys (AST-discovered, for plan 11-10 and future reviewers to diff against)

```
cli.py::status#1
git/diff.py::push_working_branch#1
input/loaders.py::_load_github#1
logging.py::_configured_level#1
logging.py::_redaction_processor#1
orchestrator/lease.py::run_lease#1
orchestrator/runner.py::default_github_client_factory#1
orchestrator/runner.py::_run_current_role#1
orchestrator/runner.py::_run_current_role#2
orchestrator/runner.py::_run_current_role#3
persistence/engine.py::build_engine#1
persistence/mutations.py::_known_secrets#1
workers/claude_code.py::_base_argv#1
workers/claude_code.py::ClaudeCodeWorker._spawn_and_parse#1
workers/cli_runtime.py::scrub_log_in_place#1
workers/copilot.py::_base_argv#1
workers/copilot.py::CopilotWorker._spawn_and_parse#1
workers/hermes.py::HermesWorker._spawn_and_parse#1
```

12 modules: `cli.py`, `git/diff.py`, `input/loaders.py`, `logging.py`, `orchestrator/lease.py`, `orchestrator/runner.py`, `persistence/engine.py`, `persistence/mutations.py`, `workers/claude_code.py`, `workers/cli_runtime.py`, `workers/copilot.py`, `workers/hermes.py`.

## Measured Verification Facts

- **`run_publish_step` final signature:** `run_publish_step(*, run_id: UUID, state: RunState, work_dir: Path, client: GitHubClient | None, create_pr: bool, known_secrets: Mapping[str, str], push_token: str | None) -> PublishResult`.
- **Sanitized-environment run** (`env -u DATABASE_URL -u DATABASE_URL_DIRECT`, fresh tempdir cwd, no `.env`): `pytest -m "unit or contract" tests/unit/test_publish_idempotency.py tests/unit/test_publish_step_unit.py` -- **14 passed**, zero settings mocking of any kind.
- **Combined sanitized run** adding `tests/unit/test_global_settings_reads_are_declared.py`: **19 passed**.
- **Full local `unit or contract` tier:** `835 passed, 1 skipped, 374 deselected, 1 failed` in **265.03s**. The 1 failure is the pre-existing, unrelated `test_worker_registry_names.py` case documented above (confirmed pre-existing via `git stash`). Test count rose from the plan's own measured baseline of 830 passed by exactly +5 (this plan added 6 new tests: 5 in the new inventory module + 1 token-threading assertion; net +5 because the sanitized/mocking removal did not change prior pass/fail counts for the 6 previously-failing-under-CI-conditions tests, which already passed locally due to the repo's own `.env`).
- **The 183s `test_missing_claude_binary_returns_failed_without_raising` outlier:** **reproduced** in isolation at **179.56s** (plan's own baseline: 183s) -- pre-existing, unrelated, explicitly out of this plan's scope per the phase `<verification>` section's own instruction; not fixed here.
- **`db`-tier rung:** **reachable** in this execution sandbox (a `.env` with live Neon credentials is present). `pytest -q -m db tests/db/test_publish_idempotency.py` -- **4 passed in 184.89s** against real PostgreSQL, confirming the single updated `tests/db/` call site (the fast-path/point-c scenario) still passes against a real database.
- **Type/lint gates:** `mypy src/dark_factory` -- clean except the pre-existing, unrelated `tools/mcp_transport.py` `mcp.server` import-not-found (confirmed pre-existing via `git stash`; the optional `mcp` extra is simply not installed in this environment). `ruff check .` -- all checks passed. `ruff format --check .` -- pre-existing 19-file repo-wide debt (confirmed pre-existing via `git stash`); this plan's own new content (the inventory file, and every line this plan's edits touched in the five modified files) is itself format-clean.

## 12-to-6 Failure Accounting (G-11-3's 12 reported CI failures)

| # | Failing test | Sink | Closed by |
|---|---|---|---|
| 1 | `test_publish_idempotency.py::test_nothing_recorded_commits_pushes_checks_then_creates_in_order` | B (`publish.py:272`) | **this plan** |
| 2 | `test_publish_idempotency.py::test_existing_pr_on_a_different_head_branch_is_not_adopted` | B | **this plan** |
| 3 | `test_publish_idempotency.py::test_no_client_call_besides_find_or_create[point-a-nothing-recorded]` | B | **this plan** |
| 4 | `test_publish_step_unit.py::test_create_pr_true_returns_pushed_sha_and_pr_identifiers_from_one_call` | B | **this plan** |
| 5 | `test_publish_step_unit.py::test_pr_body_links_the_source_issue_and_carries_no_execution_scoped_data` | B | **this plan** |
| 6 | `test_publish_step_unit.py::test_create_pull_request_raising_github_api_error_does_not_re_raise` | B | **this plan** |
| 7 | `test_clarification_comment.py::test_raising_create_comment_still_pauses_with_no_id_recorded` | C (`runner.py:1685`, inside `_run_current_role`) | plan 11-09 |
| 8 | `test_webhook_signature.py::test_missing_github_token_logs_loudly_at_construction` | A (`logging.py:37`) | plan 11-09 |
| 9 | `test_webhook_signature.py::test_missing_github_webhook_secret_logs_loudly_at_construction` | A | plan 11-09 |
| 10 | `test_webhook_signature.py::test_fully_configured_settings_log_no_startup_warning` | A | plan 11-09 |
| 11 | `test_webhook_signature.py::test_missing_dispatch_github_token_logs_a_warning_not_an_error` | A | plan 11-09 |
| 12 | `test_webhook_signature.py::test_injected_authenticated_login_skips_the_startup_check` | A | plan 11-09 |

This plan closes exactly the 6 Sink-B failures (1-6). The remaining 6 (Sink A and Sink C) are `tests/support/log_sink.py`, `tests/support/live_runtime.py`, and `tests/unit/test_clarification_comment.py` -- all explicitly out of this plan's `<verification>` scope and owned by plan 11-09, which shares no file with this plan.

## Next Phase Readiness

Plan 11-09 can proceed independently -- it touches `tests/support/log_sink.py`, `tests/support/live_runtime.py`, and `tests/unit/test_clarification_comment.py`, none of which this plan touched. Plan 11-10 (the recurrence guard spanning both) can now build on:
- This plan's inventory module and its exact 18-key set (recorded above) as the static half of the recurrence guard.
- `orchestrator/runner.py`'s `_run_current_role` three-entry category, already flagged in the inventory's own module docstring as requiring a settings override via Idiom A or B for any unit test that drives one of its branches -- the exact gap plan 11-10's dynamic (child-process) guard is meant to catch empirically.

No blockers for 11-09 or 11-10. The two pre-existing out-of-scope conditions documented above (the worker-registry environmental test, and the repo-wide ruff-format debt) are carried forward as general hardening candidates, not phase blockers.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-10-02*
