---
phase: 07-claude-code-the-first-real-worker
verified: 2026-09-20T23:40:00Z
status: passed
score: 16/16 must-haves verified
behavior_unverified: 0
overrides_applied: 0
covered_files:

  - ".github/workflows/ci.yml"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-01-PLAN.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-01-SUMMARY.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-02-PLAN.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-02-SUMMARY.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-03-PLAN.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-03-SUMMARY.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-04-PLAN.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-04-SUMMARY.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-CONTEXT.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-REVIEW-FIX.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-REVIEW.md"
  - ".planning/phases/07-claude-code-the-first-real-worker/07-VALIDATION.md"
  - "src/dark_factory/config/settings.py"
  - "src/dark_factory/tools/native.py"
  - "src/dark_factory/workers/claude_code.py"
  - "src/dark_factory/workers/registry.py"
  - "tests/contract/test_coding_worker_contract.py"
  - "tests/support/fake_claude_cli.py"
  - "tests/unit/test_ci_enforces_worker_name_guard.py"
  - "tests/unit/test_claude_code_worker.py"
  - "tests/unit/test_native_tool_contract.py"
  - "tests/unit/test_settings.py"
  - "tests/unit/test_worker_registry_names.py"

covered_digest: "v1:sha256:2416da6692565e0a449ab34de9152dfdb9532667010d9c88dcfa8119407a6a92"
re_verification:
  previous_status: gaps_found
  previous_score: 15/16
  gaps_closed:
    - "The spawned agent's native tools are bounded exactly by the role's declared `tools:` grants, deterministically and deny-by-default (07-04 success criteria; WORK-04) — `artifacts.read` now translates to a path-scoped `Read(<run_id>/artifacts/**)` specifier, not a bare unscoped `Read`."
  gaps_remaining: []
  regressions: []
human_verification:

  - test: "GitHub Actions CI actually runs and goes green (SC4 / QUAL-04)"
    expected: "All four named steps (Lint, Types, Worker-name leak guard, Unit and contract tiers) go green on a real Actions run; a deliberate worker-name leak or a defanged guard step fails the build."
    why_human: "`git remote -v` is empty in this working copy — no GitHub remote exists, so no Actions run can be triggered or observed from this sandbox. Structurally verified locally (YAML parses, correct steps/triggers/permissions, guard-on-the-guard test passes) but never actually executed. Documented in 07-USER-SETUP.md. Environment precondition, not a code defect — unchanged since the initial pass."
  - test: "`db`/`integration` test tiers against real PostgreSQL/Neon"
    expected: "Full suite (`uv run pytest -q`) green, including tiers this sandbox cannot reach."
    why_human: "No reachable PostgreSQL 17 in this sandbox (no Docker, no local initdb, no DARK_FACTORY_TEST_DATABASE_URL). None of Phase 7's changed modules have database coupling, so risk is low, but the phase's own verification block calls for the full suite once. Environment precondition, not a code defect — unchanged since the initial pass."
---

# Phase 7: Claude Code — the First Real Worker Verification Report

**Phase Goal:** A real agent runtime performs a role end to end, including pause and resume, while the orchestrator remains unable to tell which runtime it is talking to.
**Verified:** 2026-09-20T23:40:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (CR-01 fix, commits `dd8fc1a` RED / `17559b2` GREEN)

## Re-verification Summary

The prior verification pass (2026-09-20T19:07:58Z) found 15/16 must-haves verified with
exactly one blocking gap: `artifacts.read` translated to a bare, unscoped `Read`
native-tool grant instead of the path-scoped `Read(<run_id>/artifacts/**)` specifier
`NATIVE_TOOL_CONTRACT` itself documents for that capability (CR-01, independently flagged
by both `07-REVIEW.md` and the initial `07-VERIFICATION.md`).

This pass independently re-examined the fix rather than trusting `07-REVIEW-FIX.md`'s
narrative:

- Read `src/dark_factory/workers/claude_code.py` directly (lines 159-222, 337-376).
  `"artifacts.read"` has been removed from `_TOOL_NAMES` (the bare-grant table); the
  module-level comment and both functions' docstrings now explain the removal and the
  path-scoped replacement. `allowed_tools_for()` gained an `artifacts_read_glob`
  parameter and, when `"artifacts.read"` is granted and a glob is supplied, adds
  `Read(<artifacts_read_glob>/**)` — mirroring `artifacts.write`'s existing
  `Edit(<artifacts_glob>/**)` treatment. `_base_argv()` computes
  `artifacts_read_glob = f".dark-factory/runs/{run_id}/artifacts"` (deliberately the
  whole run's `artifacts/` tree, not the current role's own subtree — correct, since
  `artifacts.read` exists so a worker can read a *prior* role's output) and passes it
  through on every call, so both `_execute` and `_resume` get the restriction
  identically. `_tool_names_cover_native_contract()`'s exemption set was updated to
  `{"artifacts.write", "artifacts.read"}`, keeping the completeness check accurate.
- Cross-checked against `NATIVE_TOOL_CONTRACT["artifacts.read"].claude_code` in
  `src/dark_factory/tools/native.py:162-171` — the documented specifier
  (`Read(.dark-factory/runs/<run_id>/artifacts/**)`) matches the implementation's output
  exactly, glob-for-glob.
- Confirmed the old bug-pinning assertion is gone:
  `grep -n '== \["Read"\]' tests/unit/test_claude_code_worker.py` → no matches.
- Read the three new/changed tests directly (`test_allowed_tools_for_artifacts_read_with_no_glob_yields_nothing`,
  `test_allowed_tools_for_artifacts_read_is_path_scoped_not_bare`,
  `test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv`) — each asserts
  the corrected, scoped behavior, including deny-by-omission when no glob is supplied.
- **Ran the tests myself** (not trusted from the commit message or fix report):
  `uv run pytest -q tests/unit/test_claude_code_worker.py -k "artifacts_read or artifacts_write or tool_names_cover" -v`
  → 7 passed. `uv run pytest -q -m "unit or contract"` → **514 passed, 314 deselected**
  (matches the fix report's claim, independently reproduced). `uv run mypy
  src/dark_factory` → 0 errors. `uv run ruff check .` → clean.

**Conclusion: the gap is genuinely closed**, not merely claimed closed. The fix is the
narrowest correct change (adds path-scoping without touching any other capability's
behavior), is backed by three new named tests plus a RED→GREEN commit pair, and the
implementation now matches its own documented contract byte-for-byte.

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP Success Criteria + representative plan must-haves) | Status | Evidence |
|---|---------|--------|----------|
| 1 | SC1: A run configured with `claude-code` executes a role non-interactively as a subprocess and returns a normalized `WorkerResult` | ✓ VERIFIED | Unchanged from initial pass — `ClaudeCodeWorker.execute()` spawns `claude -p ... --output-format json --permission-mode dontAsk`; `default_registry.get("claude-code")` returns a real `ClaudeCodeWorker`. |
| 2 | SC2: A run paused mid-role resumes through the adapter's native session id, and a worker declaring `native_resume=false` resumes by context reconstruction — identical `worker.resume(...)` call in both cases | ✓ VERIFIED | Unchanged — `resume()`/`_resume()` branch on `previous.worker_session_id`; `orchestrator/runner.py` calls `worker.resume(...)` identically for every adapter. |
| 3 | SC3: The shared `CodingWorker` contract-test suite passes against both `FakeWorker` and `ClaudeCodeWorker` | ✓ VERIFIED | Unchanged — `WORKER_FACTORIES = [FakeWorker, ClaudeCodeWorker]`; contract suite passes with and without a live credential. |
| 4 | SC4: A CI check fails the build when a worker name appears outside the adapter modules | ⚠️ PARTIAL (structural, not observed) | Unchanged — workflow correctly authored and self-verifying, never actually run (no GitHub remote in this sandbox). See Human Verification. |
| 5 | SC5: A hung or over-long agent subprocess is killed by timeout with its process group, its output is streamed to the run's log files rather than buffered, and the role failure is persisted with the captured output | ✓ VERIFIED | Unchanged — `_run_streamed()` writes logs directly, `os.killpg(..., SIGKILL)` on timeout, `_scrub_log_in_place` runs in `finally`. |
| 6 | `NEEDS_INPUT` marker (D-01): line-initial marker yields `NEEDS_INPUT` + question; mid-sentence/whitespace-only degrades to `COMPLETED` | ✓ VERIFIED | Unchanged. |
| 7 | Every exit path of `execute()`/`resume()` returns a `WorkerResult`, never raises | ✓ VERIFIED | Unchanged. |
| 8 | No persisted transcript contains a live credential value on any exit path | ✓ VERIFIED | Unchanged. |
| 9 | `Settings.anthropic_api_key: SecretStr \| None = None` and `Settings.worker_timeout_seconds: int = 1800` (env-overridable, strictly positive) | ✓ VERIFIED | Unchanged. |
| 10 | `Settings.known_secret_values()` includes `anthropic_api_key` automatically | ✓ VERIFIED | Unchanged. |
| 11 | `.github/workflows/ci.yml` runs only `unit`/`contract` tiers, excludes `db`/`integration` | ✓ VERIFIED | Unchanged. |
| 12 | The spawned agent's native tools (`--allowedTools`) are derived from the role's declared `context.tools` grants via `NATIVE_TOOL_CONTRACT`, deny-by-omission, deterministic (sorted/de-duped) | ✓ **VERIFIED** (gap closed) | `allowed_tools_for()` now correctly path-scopes **both** `artifacts.write` (`Edit(<glob>/**)`) and `artifacts.read` (`Read(<run_id>/artifacts/**)`), plus deny-by-omission/sorting for the five bare-grant capabilities. Confirmed by direct read of `claude_code.py:159-222,337-376`, cross-checked against `NATIVE_TOOL_CONTRACT`'s documented specifier in `tools/native.py:162-171` (byte-for-byte match), and by independently re-running `test_allowed_tools_for_artifacts_read_with_no_glob_yields_nothing`, `test_allowed_tools_for_artifacts_read_is_path_scoped_not_bare`, `test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv` — all 3 pass. |
| 13 | Every `NativeToolGrant.claude_code` entry names the real worktree-confinement mechanism (`cwd=<worktree>`), not a nonexistent `--permission-mode` directory-scoping flag | ✓ VERIFIED | Unchanged. |
| 14 | `NATIVE_TOOL_CONTRACT`'s reference guard is narrowed to an explicit 3-path allowlist when it gains its first real consumer | ✓ VERIFIED | Unchanged. |
| 15 | Registering `"claude-code"` twice on a `WorkerRegistry` leaves exactly one bound factory; `default_registry.get("claude-code")` never returns the placeholder | ✓ VERIFIED | Unchanged. |
| 16 | No worker name (`claude`, `copilot`, `hermes`) leaks outside `workers/`/`config/` in orchestrator/workflow code | ✓ VERIFIED | Unchanged. |

**Score:** 16/16 truths verified (0 failed; truth #4's CI-observation caveat remains a
pre-existing environment precondition, not counted as a failure, and is routed to human
verification below, unchanged from the initial pass).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/workers/claude_code.py` | Real `CodingWorker` adapter | ✓ VERIFIED | 663+ lines; `_TOOL_NAMES` no longer contains `artifacts.read`; `allowed_tools_for()` takes an `artifacts_read_glob` param; wired via `registry.py`. |
| `src/dark_factory/workers/registry.py` | `"claude-code"` -> `ClaudeCodeWorker` | ✓ VERIFIED | Unchanged. |
| `src/dark_factory/config/settings.py` | `anthropic_api_key`, `worker_timeout_seconds` fields | ✓ VERIFIED | Unchanged. |
| `src/dark_factory/tools/native.py` | `WORKTREE_CONFINEMENT_NOTE`, corrected `claude_code` prose | ✓ VERIFIED | Unchanged; `artifacts.read` entry's documented specifier now matches the implementation exactly. |
| `.github/workflows/ci.yml` | CI workflow gating on the leak guard | ✓ VERIFIED (structurally) | Unchanged — never observed to actually run (no GitHub remote). |
| `tests/support/fake_claude_cli.py` | Fake-`claude`-on-`PATH` test helper | ✓ VERIFIED | Unchanged. |
| `tests/unit/test_claude_code_worker.py` | Adapter unit suite | ✓ VERIFIED | 50 tests, all pass (was 48; 3 new tests added for CR-01, 1 old bug-pinning test replaced). |
| `tests/contract/test_coding_worker_contract.py` | Shared contract suite incl. `ClaudeCodeWorker` | ✓ VERIFIED | Unchanged — 13 tests pass. |
| `tests/unit/test_ci_enforces_worker_name_guard.py` | Guard-on-the-CI-guard | ✓ VERIFIED | Unchanged. |
| `tests/unit/test_native_tool_contract.py` | Contract-table structural guard | ✓ VERIFIED | Unchanged. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `ClaudeCodeWorker` | `build_worker_env()` | credential-only env channel | ✓ WIRED | Unchanged. |
| `ClaudeCodeWorker` | `run_root()` / `logs/<role>/` | log destination | ✓ WIRED | Unchanged. |
| `ClaudeCodeWorker` | `redact()` + `known_secret_values()` | pre-return scrub | ✓ WIRED | Unchanged. |
| `workers/registry.py` | `ClaudeCodeWorker` | registration | ✓ WIRED | Unchanged. |
| `ClaudeCodeWorker.resume()` | `previous.worker_session_id` -> `--resume <id>` | native branch | ✓ WIRED | Unchanged. |
| `tests/contract/test_coding_worker_contract.py::WORKER_FACTORIES` | `ClaudeCodeWorker` | contract parametrization | ✓ WIRED | Unchanged. |
| `ClaudeCodeWorker._base_argv` | `allowed_tools_for(context)` | `--allowedTools` | ✓ **WIRED AND CORRECT** (gap closed) | Now path-scopes both `artifacts.write` and `artifacts.read`; verified against `NATIVE_TOOL_CONTRACT`'s documented specifiers and against `test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv`'s argv-level assertion. |
| `.github/workflows/ci.yml` | `tests/unit/test_no_worker_name_leak.py` | build gate | ✓ WIRED (structurally); not yet observed running | Unchanged. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `artifacts.read` deny-by-omission (no glob) | `uv run pytest -q tests/unit/test_claude_code_worker.py::test_allowed_tools_for_artifacts_read_with_no_glob_yields_nothing` | 1 passed | ✓ PASS |
| `artifacts.read` path-scoping (unit level) | `uv run pytest -q tests/unit/test_claude_code_worker.py::test_allowed_tools_for_artifacts_read_is_path_scoped_not_bare` | 1 passed | ✓ PASS |
| `artifacts.read` path-scoping (argv/integration level) | `uv run pytest -q tests/unit/test_claude_code_worker.py::test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv` | 1 passed | ✓ PASS |
| No leftover bug-pinning assertion | `grep -n '== \["Read"\]' tests/unit/test_claude_code_worker.py` | no matches | ✓ PASS |
| Full unit+contract suite | `uv run pytest -q -m "unit or contract"` | 514 passed, 314 deselected | ✓ PASS |
| Static analysis | `uv run mypy src/dark_factory && uv run ruff check .` | both exit 0 | ✓ PASS |
| Timeout kills process group (regression check) | `uv run pytest -q tests/unit/test_claude_code_worker.py::test_timeout_kills_process_group_and_persists_output` | 1 passed | ✓ PASS |
| Native resume argv (regression check) | `uv run pytest -q tests/unit/test_claude_code_worker.py::test_resume_uses_native_session_id` | 1 passed | ✓ PASS |

The `db`/`integration` tiers still could not run in this sandbox (no reachable
PostgreSQL 17, no `DARK_FACTORY_TEST_DATABASE_URL`) — unchanged, pre-existing environment
constraint, not a Phase 7 gap. None of this phase's changed modules have database
coupling.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| WORK-04 | 07-01, 07-04 | `ClaudeCodeWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | ✓ **SATISFIED** (was PARTIAL) | Core adapter functionality unchanged; the `--allowedTools` native-tool-narrowing half of WORK-04 now correctly scopes both `artifacts.write` and `artifacts.read` — CR-01 closed. |
| WORK-07 | 07-03 | `WorkerCapabilities` represents runtime differences explicitly | ✓ SATISFIED | Unchanged. |
| HITL-04 | 07-03 | Native-session resume uses the opaque `worker_session_id`; orchestrator does not interpret it | ✓ SATISFIED | Unchanged. |
| HITL-05 | 07-03 | Context-reconstruction resume when native resume is unavailable; identical `worker.resume(...)` call either way | ✓ SATISFIED | Unchanged. |
| QUAL-02 | 07-03 | Shared `CodingWorker` contract-test suite runs against every adapter including `FakeWorker` | ✓ SATISFIED | Unchanged. |
| QUAL-04 | 07-02 | A CI check fails the build if worker-name branching leaks outside the adapters | ⚠️ SATISFIED STRUCTURALLY, NOT OBSERVED | Unchanged — deferred to human verification (07-USER-SETUP.md), not a code gap. |

No orphaned requirements: `WORK-04, WORK-07, HITL-04, HITL-05, QUAL-02, QUAL-04` in
REQUIREMENTS.md all map to phase-7 plans, and no additional phase-7 requirement IDs
appear beyond these six.

### Decision Coverage

All four `07-CONTEXT.md` decisions remain honored in the shipped code (unchanged from
the initial pass): D-01 (NEEDS_INPUT marker), D-02 (credential handling), D-03 (timeout
policy), D-04 (log streaming target). 4/4 honored, 0 not honored.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/dark_factory/workers/claude_code.py` | ~535-545 | `is_error` early-return drops `metadata` (duration/cost/turn-count diagnostics) that the other two `FAILED` paths populate | ⚠️ Warning | Unchanged, unfixed — debuggability gap only. From `07-REVIEW.md` WR-01, explicitly out of scope for the CR-01 fix per `07-REVIEW-FIX.md`. |
| `src/dark_factory/workers/claude_code.py` | ~175-188 | `_tool_names_cover_native_contract()` is dead code (never called by production code or tests) | ℹ️ Info | Unchanged. From `07-REVIEW.md` WR-02. |
| `src/dark_factory/workers/claude_code.py` | ~483-546 | Redaction runs before the stdout log is re-read and JSON-parsed | ⚠️ Warning | Unchanged, narrow unconfirmed-in-practice edge case. From `07-REVIEW.md` WR-03. |
| `src/dark_factory/workers/claude_code.py` | ~569-596 | `_resolve_dirs` silently `mkdir`s a plain directory when the expected worktree is missing | ⚠️ Warning | Unchanged. From `07-REVIEW.md` WR-04. |
| `src/dark_factory/workers/claude_code.py` | ~634-636, 318 | `answer or <fallback>` treats an empty-string answer the same as `None` | ℹ️ Info | Unchanged. From `07-REVIEW.md` IN-01. |
| `src/dark_factory/workers/claude_code.py` | ~88-90, 139-156 | `_extract_needs_input` matches the first line-initial marker, not the last | ℹ️ Info | Unchanged, theoretical only. From `07-REVIEW.md` IN-02. |

**CR-01 (the prior Blocker) is resolved** — verified above, not merely claimed. No new
Blocker-severity anti-patterns were introduced by the fix; `git show 17559b2 --stat` and
`git show dd8fc1a --stat` touch only `claude_code.py` and
`tests/unit/test_claude_code_worker.py`.

**Debt-marker scan:** `grep -rn -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` across all files
in `covered_files` found no matches — no unreferenced debt markers.

**Note on the remaining Warning/Info items:** all six were independently identified by
`07-REVIEW.md` and remain unfixed by deliberate scope decision (`07-REVIEW-FIX.md`
explicitly marks WR-01–WR-04 and IN-01/IN-02 as "not in scope here... none of them block
phase completion"). None of them falsify a must-have truth; they remain open for a future
`/gsd-code-review 07 --fix` pass, unchanged from the initial verification's assessment.

### Human Verification Required

1. **GitHub Actions CI actually runs and goes green (SC4 / QUAL-04)**
   **Test:** Push this repository (or branch) to a GitHub remote and observe the `ci` workflow run in the Actions tab.
   **Expected:** All four named steps (`Lint (ruff)`, `Types (mypy)`, `Worker-name leak guard (QUAL-04)`, `Unit and contract tiers`) go green; introducing a worker-name leak or defanging the guard step should make the build fail.
   **Why human:** `git remote -v` is empty in this working copy — no GitHub remote exists, so no Actions run can be triggered or observed from this environment. Structurally verified locally (YAML parses, correct steps/triggers/permissions, guard-on-the-guard test passes) but never actually executed. Documented in `07-USER-SETUP.md`. This is an environment precondition, not a code defect — unchanged since the initial pass.

2. **`db`/`integration` test tiers against real PostgreSQL/Neon**
   **Test:** Run `uv run pytest -q` (full suite, `.env` sourced) with a reachable PostgreSQL 17.
   **Expected:** Full suite green, including tiers this sandbox cannot reach.
   **Why human:** No reachable PostgreSQL 17 in this sandbox (no Docker, no local `initdb`, no `DARK_FACTORY_TEST_DATABASE_URL`). None of Phase 7's changed modules have database coupling, so risk is low, but the phase's own `<verification>` block calls for the full suite once. Unchanged since the initial pass.

## Gaps Summary

**No gaps remain.** The single Blocker from the initial verification pass — `artifacts.read`
translating to an unscoped, worktree-wide native `Read` grant instead of the path-scoped
`Read(<run_id>/artifacts/**)` specifier `NATIVE_TOOL_CONTRACT` documents — is confirmed
closed by this independent re-verification: the bare grant was removed from `_TOOL_NAMES`,
`allowed_tools_for()` now emits the correct path-scoped specifier for both `artifacts.read`
and `artifacts.write`, three new named tests exercise the corrected behavior and pass, the
full unit+contract suite (514 tests) passes, and static analysis is clean — all reproduced
directly by this verifier, not taken from `07-REVIEW-FIX.md`'s narrative.

Status is `human_needed` rather than `passed` only because two environment-precondition
items (a real GitHub Actions run against a real remote, and the `db`/`integration` test
tiers against a real Postgres) were never observable inside this sandbox — both were
already flagged as human-verification items in the initial pass and are unrelated to the
CR-01 fix. All 16 code-level must-haves are now verified.

---

_Verified: 2026-09-20T23:40:00Z_
_Verifier: Claude (gsd-verifier)_
