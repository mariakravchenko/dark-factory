---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
verified: 2026-10-03T08:10:00Z
status: passed
score: 18/18 must-haves verified
covered_files:
  - ".github/workflows/ci.yml"
  - ".planning/REQUIREMENTS.md"
  - ".planning/ROADMAP.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-01-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-01-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-02-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-02-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-03-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-03-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-04-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-04-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-06-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-06-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-07-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-07-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-08-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-08-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-09-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-09-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-10-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-10-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-REVIEW.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-SECURITY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-UAT.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-VALIDATION.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/deferred-items.md"
  - "README.md"
  - "src/dark_factory/orchestrator/publish.py"
  - "src/dark_factory/orchestrator/runner.py"
  - "src/dark_factory/webhook/__init__.py"
  - "src/dark_factory/webhook/app.py"
  - "src/dark_factory/workers/claude_code.py"
  - "tests/conftest.py"
  - "tests/db/test_publish_idempotency.py"
  - "tests/support/live_runtime.py"
  - "tests/support/log_sink.py"
  - "tests/unit/test_clarification_comment.py"
  - "tests/unit/test_claude_code_worker.py"
  - "tests/unit/test_global_settings_reads_are_declared.py"
  - "tests/unit/test_publish_idempotency.py"
  - "tests/unit/test_publish_step_unit.py"
  - "tests/unit/test_resume_workflow_reference_doc.py"
  - "tests/unit/test_unit_tier_needs_no_database.py"
  - "tests/unit/test_webhook_import_needs_no_database.py"
covered_digest: "v1:sha256:dbee8cf458244bb42b1c411290d9db5c4040ebe067576949ba76657ea6c96365"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: "12/14 (2026-10-02T13:05:00Z, after G-11-3 gap closure)"
  gaps_closed:
    - "Truth #13 (live CI quality job): real CI run 37011371774 independently re-queried via `gh run view` in this pass (not taken from SUMMARY/UAT claims) — quality job green, 3m23s."
    - "Truth #14 (live workflow_dispatch + resume backstop): real CI run 37103322812 independently re-queried via `gh run view`, `gh run view --log-failed`, a direct read-only query against the real Neon `role_executions` table, and `git`/`gh api` history on the target repo's run branch — all four independent sources corroborate the UAT.md narrative exactly (BA COMPLETED -> ARCHITECTURE COMPLETED with a fresh session id, confirming the G-11-5 fallback fired -> DEVELOPMENT FAILED on a legitimate write_scope guardrail, not an infra defect)."
    - "G-11-4 (db-tier DATABASE_URL propagation): `tests/conftest.py`'s `_database_url_env` autouse fixture read directly, confirmed only-when-absent, confirmed by the same live CI run's 205/205 db-tier pass."
    - "G-11-5 (cross-machine native-resume fallback): `src/dark_factory/workers/claude_code.py`'s `_is_session_not_found`/`_resume` diff read directly, confirmed scoped to the exact CLI failure signature with a negative-control test (`test_resume_does_not_fall_back_on_an_unrelated_native_failure`) proving it does not mask unrelated failures; confirmed fired in the real CI run (ARCHITECTURE's recorded session id changed between the laptop attempt and the CI-resumed attempt)."
    - "G-11-6 (reference resume.yml git-configuration, two parts): README.md's reference block read directly, confirmed `permissions: contents: write` + `fetch-depth: 0`; independently confirmed the real deployed `resume.yml` on the target repo's `main` branch carries the identical final configuration (not the broken intermediate `persist-credentials: false` attempt), and that an earlier run (37102999213) genuinely reproduced the `no merge base` failure this fix closes."
  gaps_remaining: []
  regressions: []
---

# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume Verification Report

**Phase Goal:** A run started on a laptop finishes in CI (and the reverse) through Neon alone, and the complete lifecycle is provable in CI without a single AI call.
**Verified:** 2026-10-03T08:10:00Z
**Status:** passed
**Re-verification:** Yes — this is the third verification pass. The 2026-10-02T13:05:00Z pass (`human_needed`, 12/14) left exactly two truths unresolved, both requiring live infrastructure a sandbox cannot produce. This session closed both for real (per 11-UAT.md and five further gaps — G-11-4, G-11-5, G-11-6 — discovered and fixed along the way). This pass independently re-derives that conclusion from primary sources (`gh run view`, a direct read-only Neon query, `gh api`/`git` history on the target repo), not from 11-UAT.md's or any SUMMARY's narrative.

## Goal Achievement

Every truth below marked "fresh" was independently reproduced in this verification pass against
live external systems (GitHub Actions on two separate repositories, the real Neon database) or by
direct source reads — never taken on 11-UAT.md's, a SUMMARY's, or the prior VERIFICATION.md's word.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | G-11-1 fix (carried forward): `dark_factory.webhook.app` imports with no `DATABASE_URL`/`DATABASE_URL_DIRECT` and no readable `.env` | ✓ VERIFIED | `git log --since=2026-10-02T13:05:00Z -- src/dark_factory/webhook/app.py` → no commits (unchanged). Fresh full-tier run (see #8) includes this guard, passing. |
| 2 | G-11-2 fix (carried forward): README's worker-runtime table + `resume.yml` doc-drift guard | ✓ VERIFIED | Fresh: `pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` → **13 passed** |
| 3 | SC2/TRIG-01 (carried forward): triggers carry zero lifecycle logic; one orchestration implementation | ✓ VERIFIED | Fresh: `grep -n "_WEBHOOK_DIRECT_ALLOWED\|advance\|drive" src/dark_factory/webhook/app.py` → only the docstring's own prohibition comment ("must never reference `advance` or `drive`"), no actual reference. Full-tier run (#8) includes `test_trigger_carries_no_lifecycle_logic.py`, passing. |
| 4 | **G-11-3 production sink closed (carried forward, regression-checked):** `publish.py` reads no process-global settings | ✓ VERIFIED | `git log --since=2026-10-02T13:05:00Z -- src/dark_factory/orchestrator/publish.py` → no commits. Fresh: `grep -n "get_settings" src/dark_factory/orchestrator/publish.py` → zero matches |
| 5 | **G-11-3 test-infrastructure sinks (carried forward, regression-checked)** | ✓ VERIFIED | `git log --since` empty for `tests/support/log_sink.py`, `tests/support/live_runtime.py`, `tests/unit/test_clarification_comment.py`. Full-tier run (#8) includes all three, passing |
| 6 | **G-11-3 recurrence guard (carried forward, regression-checked):** database-free child-process harness | ✓ VERIFIED | Fresh: `pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py` → **3 passed in 259.86s** (within a 14-test combined run, see below) |
| 7 | SC1/HITL-06 (carried forward): a run paused by one OS process is finished by another | ✓ VERIFIED | Regression-checked via #8's full-tier pass plus live cross-machine proof (#13/#14 below, a stronger real-infrastructure instance of the same claim) |
| 8 | Full project regression shows exactly the one documented pre-existing sandbox artifact and no new failures | ✓ VERIFIED | Fresh, run once in this pass: `uv run pytest -q -m "unit or contract"` (excluding the slow child-process guard, run separately) → **840 passed, 1 skipped, 1 failed, 374 deselected in 525.59s**. The one failure is `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, confirmed by its own traceback to be caused by a real Anthropic API call succeeding (`WorkerResultStatus.COMPLETED`) — the exact, independently-reproduced, documented sandbox-credential artifact (`deferred-items.md`), not a phase-11 regression. 840 = 838 (prior baseline) + 2 new G-11-5 tests, exactly as `fix_note` predicted. Combined with the separately-run 14-test guard suite (`test_webhook_import_needs_no_database.py` + `test_unit_tier_needs_no_database.py` + `test_qual01_ci_coverage.py` + `test_trigger_carries_no_lifecycle_logic.py` → **14 passed in 259.86s**), zero regressions found anywhere in this pass |
| 9 | No debt markers in any file this phase's gap-closure work touched | ✓ VERIFIED | Fresh: `grep -rn -E "TBD\|FIXME\|XXX"` across `claude_code.py`, `test_claude_code_worker.py`, `conftest.py`, `README.md` (the G-11-5/G-11-6 files, which have no formal code-review doc) → zero matches. `11-REVIEW.md` already covers the G-11-3 files (status: clean) |
| 10 | Code review found no BLOCKER/WARNING on the G-11-3 diff; the later G-11-5/G-11-6 diff (post-dating 11-REVIEW.md, confirmed by commit timestamps: review at 12:41, G-11-5 fix at 20:27 the same day) has no formal review doc | ✓ VERIFIED | `11-REVIEW.md`: `status: clean`, 0 critical/warning. This verifier independently read the full `git diff 9020a96..HEAD` (the G-11-4/5/6 diff, 637 insertions across 7 files) directly: `claude_code.py`'s fallback is narrowly scoped to one literal CLI error signature, has a dedicated negative-control test, and introduces no new credential or data-flow path; `conftest.py`'s fixture is only-when-absent and restores on teardown; no anti-patterns found |
| 11 | SC3 (mechanical half, carried forward): `FakeWorker` suite maps to `db`-marked modules; `ci.yml` selects `db` with no `services:`/secrets | ✓ VERIFIED | `git log --since=2026-10-02T13:05:00Z -- .github/workflows/ci.yml` → one commit (6652f0b, timeout-comment calibration only — `[ASSUMED]` → `MEASURED`, no selector change). Fresh diff read confirms no `-m` selector change |
| 12 | QUAL-01: the push-token fix is a genuine production contract improvement, not a test mock | ✓ VERIFIED (carried forward) | Unchanged since prior pass; `git log --since` empty for `publish.py`/`runner.py` |
| 13 | **SC3 (live-CI half, now closed):** `ci.yml`'s `quality` job runs green end-to-end on a real GitHub-hosted Actions runner, including both the `Unit and contract tiers` and `Database tier` steps | ✓ VERIFIED | **Independently re-queried in this pass**, not taken from 11-UAT.md: `gh run view 37011371774 --repo mariakravchenko/dark-factory` → `✓ quality in 3m23s`. Branch confirmed at `0` commits ahead/behind `origin` (pushed). This is the real run 11-UAT.md's Test 1 cites, confirmed still green from this verifier's own query |
| 14 | **Backstop (now closed):** a real `workflow_dispatch` against a live repository starts a real `resume.yml` run that advances a real run past BA, through a cross-machine native-resume fallback | ✓ VERIFIED | **Independently re-derived from four primary sources in this pass**, not taken from 11-UAT.md's narrative: (a) `gh run view 37103322812 --repo mariakravchenko/app-new` → job failed with "Process completed with exit code 1" (expected — `dark-factory resume` exits 1 on a terminal `FAILED` state, by design); (b) `gh run view --log-failed` shows the CLI's own output: `DEVELOPMENT → FAILED`, `terminal state: FAILED`, `last role: DEVELOPMENT`; (c) a direct read-only SQL query against the real Neon `role_executions` table for run `43321bac-c4fd-4bbe-a79e-4632859fc837` shows `BA COMPLETED` (session `94f392dc...`) → `ARCHITECTURE COMPLETED` (session `b2de4349...` — a **different** session id than BA's, confirming ARCHITECTURE's native `--resume` against the laptop-created session failed and the G-11-5 fallback produced a fresh one) → `DEVELOPMENT FAILED` with `error` text `"role DEVELOPMENT attempt 1 wrote outside its configured write_scope ... ['contact.html']"` — the exact legitimate guardrail 11-UAT.md describes, not an infra defect; (d) `gh api` + `git fetch` against `app-new`'s run branch shows real `ARCHITECTURE artifacts` (2f6a857, pushed 06:26:45Z) and `DEVELOPMENT artifacts` (9c4a5cf, pushed 06:32:13Z) commits, confirming real pushes happened. A prior run in the same sequence (37102999213, 06:25:22Z) independently reproduces the exact G-11-6b `fatal: main...dark-factory/run-...: no merge base` failure the fix note describes, confirming the gap this fix closes was real, not invented |
| 15 | **G-11-4 (new this session):** the `db` tier passes in CI with no pre-set `DATABASE_URL`/`DATABASE_URL_DIRECT` | ✓ VERIFIED | Direct read of `tests/conftest.py:199-248`'s `_database_url_env` autouse fixture: only-when-absent env supply (mirrors G-11-3's `log_sink.py` idiom), `get_settings.cache_clear()` on both set and teardown, restores exactly the keys it set. Confirmed live: CI run 37011371774's `Database tier` step passed 205/205, matching 11-06-SUMMARY.md's local baseline exactly |
| 16 | **G-11-5 (new this session):** `dark-factory resume` falls back to context reconstruction when a native `--resume <session_id>` fails because the session was created on a different machine, and does NOT fall back on any other native failure | ✓ VERIFIED | Direct read of `claude_code.py`'s `_is_session_not_found`/`_resume`: matches only the literal CLI substring `"No conversation found with session ID"`, retries once via the existing HITL-05 argv (no `--resume` element). Fresh: `pytest -m unit -q tests/unit/test_claude_code_worker.py -k resume` → **10 passed** (both the positive case `test_resume_falls_back_to_context_reconstruction_when_native_session_not_found` and the negative control `test_resume_does_not_fall_back_on_an_unrelated_native_failure`, which asserts exactly one call and no fallback on an unrelated CLI crash). Fired for real in production: see truth #14's session-id evidence |
| 17 | **G-11-6 (new this session):** the reference `resume.yml`'s git configuration (`permissions: contents: write`, `fetch-depth: 0`) supports both the role's own push and a later merge-base diff | ✓ VERIFIED | Direct read of `README.md:347-358` confirms both settings present with load-bearing-not-generous prose explaining why the more conservative-looking alternatives are wrong. Independently confirmed via `gh api repos/mariakravchenko/app-new/commits/...` that the real deployed `resume.yml` on `app-new`'s `main` branch carries the identical final configuration — not the intermediate, broken `persist-credentials: false` attempt (commit `890b109`, superseded by `1ab7784`) |
| 18 | `ruff check .` clean on the current tree; `mypy src/dark_factory` shows only the documented pre-existing 2-error baseline (mcp extra not installed) | ✓ VERIFIED | Fresh: `uv run ruff check .` → **All checks passed!**. Fresh: `uv run mypy src/dark_factory/workers/claude_code.py src/dark_factory/orchestrator/publish.py src/dark_factory/orchestrator/runner.py` → clean. Fresh: `uv run mypy src` → **2 errors, both `mcp.server` import-not-found** (the documented, pre-existing, optional-extra baseline) |

**Score:** 18/18 truths VERIFIED. Zero FAILED, zero PRESENT_BEHAVIOR_UNVERIFIED, zero insufficient_spec.

### Fresh commands run in this verification pass

| Command | Result |
|---|---|
| `gh run view 37011371774 --repo mariakravchenko/dark-factory` | `✓ quality in 3m23s` |
| `gh run view 37103322812 --repo mariakravchenko/app-new` + `--log-failed` | job failed as expected (terminal `FAILED` state exits 1); log shows `DEVELOPMENT → FAILED` |
| `gh run view 37102999213 --repo mariakravchenko/app-new --log-failed` | reproduces the historical G-11-6b `no merge base` failure (predates the `fetch-depth: 0` fix landing on this run) |
| Direct read-only SQL query, real Neon, `role_executions` for run `43321bac-...` | BA COMPLETED → ARCHITECTURE COMPLETED (new session id) → DEVELOPMENT FAILED (write_scope error text) |
| `gh api repos/mariakravchenko/app-new/commits/...` + local `git fetch` of the run branch | ARCHITECTURE/DEVELOPMENT artifact commits real, pushed at timestamps consistent with the CI run windows |
| `uv run pytest -q -m "unit or contract"` (full tier, run once) | **840 passed, 1 skipped, 1 failed, 374 deselected in 525.59s** — the 1 failure is the documented pre-existing sandbox-credential artifact |
| `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_unit_tier_needs_no_database.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_trigger_carries_no_lifecycle_logic.py` | **14 passed in 259.86s** |
| `pytest -m unit -q tests/unit/test_claude_code_worker.py -k resume` | **10 passed** (positive + negative-control G-11-5 cases) |
| `pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` | **13 passed** |
| `uv run ruff check .` | All checks passed |
| `uv run mypy src` | 2 errors, both pre-existing `mcp.server` import-not-found |
| `uv run mypy src/dark_factory/workers/claude_code.py src/dark_factory/orchestrator/publish.py src/dark_factory/orchestrator/runner.py` | clean |
| `git log --since=2026-10-02T13:05:00Z -- <carried-forward files>` | confirms each unchanged except `ci.yml` (timeout-comment calibration only, not a selector change) |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/workers/claude_code.py` | `_is_session_not_found` + fallback branch, scoped to one literal CLI signature | ✓ VERIFIED | Direct read; 10/10 resume-focused tests pass fresh |
| `tests/unit/test_claude_code_worker.py` | Positive + negative-control fallback tests | ✓ VERIFIED | Both present, both pass fresh |
| `tests/conftest.py` | `_database_url_env` autouse, only-when-absent, session-scoped | ✓ VERIFIED | Direct read; confirmed live in CI run 37011371774 |
| `README.md` | `permissions: contents: write` + `fetch-depth: 0` in the reference `resume.yml` block | ✓ VERIFIED | Direct read; confirmed deployed identically on a real target repo |
| `.github/workflows/ci.yml` | `[ASSUMED]` timeout comments replaced with `MEASURED` values from the real CI run | ✓ VERIFIED | Direct diff read; values match the independently re-queried CI run's actual durations |
| `src/dark_factory/orchestrator/publish.py` (carried forward) | No settings import; `push_token` required parameter | ✓ VERIFIED | Unchanged since prior pass, regression-confirmed |
| `src/dark_factory/webhook/app.py` (carried forward) | No module-level `build_app()` call; no `advance`/`drive` reference | ✓ VERIFIED | Unchanged since prior pass; fresh grep confirms the boundary holds |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `ClaudeCodeWorker._resume`'s native branch | HITL-05's `build_resume_prompt` context-reconstruction path | `_is_session_not_found(result)` guard | ✓ WIRED | Confirmed by direct read and by the 10-test resume suite, including the negative control |
| `resume.yml`'s `permissions: contents: write` | `actions/checkout@v4`'s ambient credential | checkout's own default `persist-credentials: true`, scoped by the job's `permissions` block | ✓ WIRED | Confirmed on the real deployed workflow on `app-new`'s `main` branch; confirmed working by the real push commits (2f6a857, 9c4a5cf) |
| `resume.yml`'s `fetch-depth: 0` | `collect_pr_diff`'s `git diff main...dark-factory/run-<id>` merge-base diff | full history fetched at checkout | ✓ WIRED | Confirmed by the contrast between run 37102999213 (shallow, failed with "no merge base") and run 37103322812 (full history, diff succeeded, reached DEVELOPMENT) |
| `tests/conftest.py`'s `_database_url_env` | `get_settings()` call sites reached by `db`-marked tests | `os.environ["DATABASE_URL"]`/`["DATABASE_URL_DIRECT"]`, only-when-absent | ✓ WIRED | Confirmed by direct read and by CI run 37011371774's 205/205 db-tier pass |
| All key links from plans 11-01 through 11-10 (carried forward, G-11-3 diff) | (unchanged) | — | ✓ WIRED | Previously independently re-verified (2026-10-02 pass); no commits since except the `ci.yml` comment-only calibration |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| HITL-06 | 11-01, 11-02, 11-03, 11-05, 11-07 | Run resumable on a different machine/process | ✓ SATISFIED | Truths #7, #14, #16 — mechanical proof (db-tier subprocess test) plus a real, live cross-machine resume against a real target repository, independently re-confirmed in this pass |
| TRIG-01 | 11-01, 11-03 | One orchestration implementation; zero lifecycle logic in triggers | ✓ SATISFIED | Truth #3 — webhook module confirmed to still carry no `advance`/`drive` reference |
| TRIG-04 | 11-03, 11-07 | Local→CI boundary crossed through Neon alone | ✓ SATISFIED | Truths #1, #2, #7, #14 — the live resume proof is now the strongest evidence for this requirement: a laptop-paused run was genuinely finished inside a GitHub Actions job through Neon alone |
| QUAL-01 | 11-04, 11-05, 11-06, 11-08, 11-09, 11-10 | `FakeWorker` suite tested end-to-end, runs green in CI with no `.env`/DB configured, no AI calls | ✓ SATISFIED | Truths #4, #5, #6, #8, #9, #11, #12, #13, #15 — mechanical proof plus the real live CI run (37011371774), both independently re-confirmed in this pass |

No orphaned requirements — REQUIREMENTS.md maps exactly TRIG-01, TRIG-04, HITL-06, QUAL-01 to Phase
11, all four marked `[x]` Complete, and all four are claimed in at least one of the phase's 10
plans' `requirements:` frontmatter (confirmed by grepping every plan file).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/dark_factory/webhook/app.py` | dispatch block (carried forward, unmodified this session) | No catch-all `except Exception` around the dispatch block | ⚠️ Warning | Carried forward unchanged from the 2026-09-30/10-01/10-02 reports (WR-01); file untouched since the prior pass. Does not block any must-have truth in this phase. |
| `src/dark_factory/config/settings.py` | 141-163 | `LEASE_HEARTBEAT_SECONDS` accepts non-positive values | ℹ️ Info | Pre-existing since Phase 2, unmodified; carried forward (WR-02), not phase-11 scope |
| 19 test files repo-wide (e.g. `tests/db/test_qa_bounce.py`) | various | `ruff format --check .` reports drift (collapsed multi-line string concatenation) | ℹ️ Info | Confirmed pre-existing and out of phase-11 scope: every drifted file traces (via `git log`) to phase 9 or earlier, is explicitly documented in `deferred-items.md` ("11-10: Pre-existing `ruff format` drift across 19 files"), and none of the files this phase's gap-closure plans touch are in the drifted set except the two already known at plan time. `ruff check .` (lint, not format) is fully clean. Not a phase-11 regression. |
| `tests/conftest.py:346` | 346 | mypy "Unused `type: ignore[call-arg]`" on `fake_settings`'s `_env_file=None` | ℹ️ Info | Confirmed pre-existing via `git log -L346,346` — traces to a Phase 1 commit (`afb2ed9`, 2026-09-08), far from the G-11-4 diff (lines 199-248). `mypy src/dark_factory` (the project's actual gated target per the stack doc) is unaffected — this is a `tests/` fixture file outside that scope. Not a phase-11 regression. |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any file this phase's work (through G-11-6) created or
modified. No `TODO`/`HACK`/`PLACEHOLDER` patterns found either (fresh grep, zero matches, across both
the G-11-3 file set and the G-11-5/G-11-6 file set).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Live CI run of the fixed `ci.yml` (SC3, real infra) | `gh run view 37011371774 --repo mariakravchenko/dark-factory` | `✓ quality in 3m23s` | ✓ PASS |
| Live cross-machine resume (HITL-06/TRIG-04 backstop, real infra) | `gh run view 37103322812` + `--log-failed` + direct Neon query + `gh api` commit history | ARCHITECTURE COMPLETED (new session, fallback fired) → DEVELOPMENT FAILED (legitimate write_scope guardrail) | ✓ PASS |
| G-11-5 fallback unit coverage | `pytest -m unit -q tests/unit/test_claude_code_worker.py -k resume` | 10 passed, including the negative control | ✓ PASS |
| G-11-4 db-tier env propagation (mechanical + live) | direct read of `conftest.py` + CI run 37011371774's db-tier step | 205/205 passed on real runner | ✓ PASS |
| G-11-3 carried-forward regression | `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_unit_tier_needs_no_database.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_trigger_carries_no_lifecycle_logic.py` | 14 passed | ✓ PASS |
| Full unit+contract regression (whole-workspace, run once) | `pytest -q -m "unit or contract"` | 840 passed, 1 skipped, 1 failed (documented pre-existing), 374 deselected | ✓ PASS |
| Lint | `ruff check .` | All checks passed | ✓ PASS |
| Type-check (project's gated scope) | `mypy src` | 2 pre-existing errors (mcp extra), unchanged baseline | ✓ PASS |

### Requirements/Decision Coverage

All four phase-11 requirement IDs (TRIG-01, TRIG-04, HITL-06, QUAL-01) are addressed by must-have
truths above, now with real-infrastructure evidence for the two that previously had only mechanical
(local/sandbox) proof. No CONTEXT.md decisions were abandoned by the G-11-4/5/6 fixes — each is a
narrow bugfix within an already-decided design (G-11-4 extends G-11-3's established only-when-absent
idiom; G-11-5 extends the already-decided HITL-05 fallback path to a new trigger condition; G-11-6
only corrects two `actions/checkout` defaults in deployer-facing documentation).

### Human Verification Required

None. Both items that were open at the prior (2026-10-02T13:05:00Z) verification pass — a real
GitHub Actions run of `ci.yml`'s `quality` job, and a real `workflow_dispatch` + `dark-factory
resume` against a real target repository — now have real, independently-reproduced evidence
gathered directly by this verifier (not taken from 11-UAT.md's or any SUMMARY's narrative): live
`gh run view`/`gh api` queries against two separate GitHub repositories, and a direct read-only SQL
query against the real Neon database backing the resumed run.

### Gaps Summary

None. This pass closes the two human-verification items the 2026-10-02T13:05:00Z VERIFICATION.md
left open, using evidence this verifier gathered independently rather than accepting 11-UAT.md's
account at face value:

- **Truth #13** (live CI quality job): confirmed directly via `gh run view 37011371774` — green,
  3m23s, matching the measured values now baked into `ci.yml`'s comments.
- **Truth #14** (live cross-machine resume backstop): confirmed via four independent sources — the
  GitHub Actions run itself, its failed-step log, a direct read of the real Neon `role_executions`
  table (which shows the exact session-id change that proves the G-11-5 fallback fired, and the
  exact write_scope error text that proves the DEVELOPMENT failure is a legitimate guardrail, not
  an infra defect), and `gh api`/`git` history on the target repository's run branch (which shows
  real, timestamped push commits for both the ARCHITECTURE and DEVELOPMENT roles). A prior run in
  the same sequence (37102999213) was also independently queried and found to reproduce the exact
  historical G-11-6b failure signature, confirming that gap was real before being fixed, not
  invented after the fact.

Three further gaps (G-11-4, G-11-5, G-11-6) were discovered and fixed in this session beyond the one
(G-11-3) the prior verification pass already knew about. All three are now independently confirmed:
G-11-4 and G-11-6 by the live CI evidence above, G-11-5 by both the live evidence and a dedicated
unit-test suite with a negative control. No `gaps:` condition (FAILED truth, MISSING/STUB artifact,
NOT_WIRED key link, or BLOCKER anti-pattern) is present anywhere in this phase as of this pass.

The phase goal — "a run started on a laptop finishes in CI (and the reverse) through Neon alone, and
the complete lifecycle is provable in CI without a single AI call" — is now demonstrated by real,
externally-verifiable evidence rather than mechanical/local proof alone: a real run, paused on a real
laptop-equivalent process, was genuinely finished inside a real GitHub Actions job, through Neon
alone, and the `FakeWorker`-driven half of that same claim (QUAL-01/SC3) runs green on a real
GitHub-hosted runner with no AI calls.

---

_Verified: 2026-10-03T08:10:00Z_
_Verifier: Claude (gsd-verifier)_
