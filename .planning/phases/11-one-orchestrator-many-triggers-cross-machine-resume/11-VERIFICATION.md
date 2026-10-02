---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
verified: 2026-10-02T13:05:00Z
status: human_needed
score: 12/14 must-haves verified (2 live-infrastructure truths abstained — the same two UAT originally found broken; both are now code-fixed and locally re-proven, including the newly-closed G-11-3 gap, but neither has been re-exercised against a real GitHub Actions runner / a real target repository since the fix)
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
  - "tests/db/test_publish_idempotency.py"
  - "tests/support/live_runtime.py"
  - "tests/support/log_sink.py"
  - "tests/unit/test_clarification_comment.py"
  - "tests/unit/test_global_settings_reads_are_declared.py"
  - "tests/unit/test_publish_idempotency.py"
  - "tests/unit/test_publish_step_unit.py"
  - "tests/unit/test_resume_workflow_reference_doc.py"
  - "tests/unit/test_unit_tier_needs_no_database.py"
  - "tests/unit/test_webhook_import_needs_no_database.py"
covered_digest: "v1:sha256:c35996fe5b4764772c2d73112b6f5f2b75173897a6453c52e7c3b8da4b877ce4"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: "31/33 (2026-10-01 re-verification, after G-11-1/G-11-2 gap closure)"
  gaps_closed:
    - "G-11-3 (blocker, discovered by UAT after the 2026-10-01 verification, not present in that report): the `Unit and contract tiers` CI step failed at RUNTIME (not collection) with 12 tests raising `pydantic_core.ValidationError` on `database_url`/`database_url_direct` the first time this branch's test suite ever ran with no `.env` file. Root cause: three production/test-support call sites (`publish.py:272`, `logging.py:28/37` via `tests/support/log_sink.py`, `runner.py:1685` via `tests/unit/test_clarification_comment.py`) and one latent sibling (`tests/support/live_runtime.py`'s `credential_missing()`, which aborted collection entirely) invoked the process-global `get_settings()` with no override seam. Closed by three plans: 11-08 (production sink — `push_token` now a required parameter, zero settings reads left in `publish.py`), 11-09 (test-infrastructure sinks — `log_sink.py` only-when-absent env supply, `test_clarification_comment.py`'s driver patches all three `_run_current_role` reads, `credential_missing()` catches `ValidationError` specifically and reports absent), 11-10 (the recurrence guard — `tests/unit/test_unit_tier_needs_no_database.py`, a 3-test child-process harness reproducing CI's exact selector with no database and no `.env`, plus a positive control and a live-suite-collection adversary). Independently re-verified fresh in this pass (see truths below), not taken on the SUMMARYs' word."
  gaps_remaining:
    - "The literal UAT-1 symptom (a real GitHub Actions run of ci.yml's quality job reaching and passing both the unit/contract step and the db-tier step end-to-end) has not been re-observed on a real runner since the G-11-3 fix landed — the branch is still unpushed (17 commits ahead of origin, confirmed fresh via `git status`/`git rev-list`). The one real CI run that ever exercised this branch (run 36850439597) predates the G-11-3 fix and is the run that discovered G-11-3."
    - "The literal UAT-2 symptom (a live `dark-factory resume` inside a dispatched resume.yml job advancing a real run past BA) has not been re-attempted — still blocked on the external Anthropic Console billing issue recorded in 11-UAT.md, confirmed still open and unrelated to any phase-11 code."
  regressions: []
---

# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume Verification Report

**Phase Goal:** A run started on a laptop finishes in CI (and the reverse) through Neon alone, and the complete lifecycle is provable in CI without a single AI call.
**Verified:** 2026-10-02T13:05:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (plans 11-08, 11-09, 11-10, closing 11-UAT.md's G-11-3; the 2026-10-01 VERIFICATION.md this one overwrites predates those three plans)

## Goal Achievement

All evidence below marked "fresh" was run live by this verification pass, in this sandbox, against
this repository's current working tree — not taken from SUMMARY.md claims. Commands, exact pass
counts and wall-clock durations are reported as measured in this pass, not copied from prior
artifacts, except where explicitly noted as a regression-only spot-check of code unchanged since
the prior verification pass (confirmed via `git log --since <prior timestamp>`).

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | G-11-1 fix (carried forward, unchanged): `dark_factory.webhook.app` imports with no `DATABASE_URL`/`DATABASE_URL_DIRECT` and no readable `.env` | ✓ VERIFIED | `git log --since=2026-10-01T11:30:00Z -- src/dark_factory/webhook/app.py` → no commits (file unchanged since prior verification). Fresh regression run: `uv run pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py` → **4 passed** |
| 2 | G-11-2 fix (carried forward, unchanged): README's worker-runtime table + `resume.yml` doc-drift guard | ✓ VERIFIED | `git log --since=2026-10-01T11:30:00Z -- README.md tests/unit/test_resume_workflow_reference_doc.py` → no commits. Fresh regression run: `uv run pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` → **13 passed** |
| 3 | SC2/TRIG-01 (carried forward): triggers carry zero lifecycle logic; one orchestration implementation | ✓ VERIFIED | Fresh: `uv run pytest -m unit -q tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_webhook_process_boundary.py tests/unit/test_qual01_ci_coverage.py` → **43 passed** (combined with webhook-import/doc-drift suites above) |
| 4 | **G-11-3 production sink closed:** `run_publish_step` reads no process-global settings — the push token arrives as a required, non-defaulted `push_token: str \| None` keyword parameter; no `get_settings`/settings import remains in `publish.py` | ✓ VERIFIED | Fresh: `grep -n "get_settings\|import.*settings" src/dark_factory/orchestrator/publish.py` → zero matches. Read `publish.py:119-128` directly: signature is `run_publish_step(*, run_id, state, work_dir, client, create_pr, known_secrets, push_token: str \| None)`. Read `runner.py:1340-1354`: the one call site passes `push_token=gate_settings.github_token.get_secret_value() if gate_settings.github_token is not None else None` — derived from the already-held `gate_settings` object, no new `get_settings()` call. Fresh: `uv run pytest -m unit -q tests/unit/test_publish_idempotency.py tests/unit/test_publish_step_unit.py` → **25 passed** |
| 5 | **G-11-3 test-infrastructure sinks closed:** `real_log_sink()` supplies fake DB vars only-when-absent (never overriding a deliberately-set value); `test_clarification_comment.py`'s driver patches `runner_module.get_settings` covering all three `_run_current_role` branches; `credential_missing()` catches `pydantic.ValidationError` specifically and reports credential-absent instead of aborting collection | ✓ VERIFIED | Read `tests/support/log_sink.py:53-80` directly: only-when-absent supply (`if name not in os.environ`), `finally`-block restore of exactly the keys it set. Read `tests/support/live_runtime.py:105`: `except ValidationError:` (specific exception, not bare `Exception` — matches the documented T-11-38 DoS mitigation). Fresh: `uv run pytest -m unit -q tests/unit/test_clarification_comment.py` → **11 passed** (included in the 25-passed run above alongside publish tests) |
| 6 | **G-11-3 recurrence guard:** a child-process harness reproduces CI's exact `unit or contract` selector (read directly out of `ci.yml`, not restated) with no database and no `.env`, exits 0 over the whole tree; a positive control proves the harness has teeth; a live-suite-collection adversary proves the latent sibling defect stays closed | ✓ VERIFIED | Fresh: `uv run pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py` → **3 passed in 266.33s**. Read the file directly: `test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file`, `test_live_suite_modules_collect_with_stub_binaries_on_path`, `test_the_harness_detects_an_unguarded_settings_read` (positive control) — all three present and non-vacuous, matching the SUMMARY's claims exactly |
| 7 | SC1/HITL-06 (carried forward, re-proven after the `runner.py` edit): a run paused by one OS process is finished by another, nothing carried over; publish idempotency unaffected by the `push_token` threading change | ✓ VERIFIED | Fresh, run live against real Neon PostgreSQL in this pass (not reused from a prior report): `uv run pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py tests/db/test_publish_idempotency.py` → **14 passed in 527.97s** — confirms the `runner.py`/`publish.py` diff (the one production code change G-11-3 required) introduced no regression in cross-machine resume, webhook dispatch, or publish idempotency |
| 8 | Full project regression shows exactly the one documented pre-existing sandbox artifact and no new failures from the G-11-3 gap-closure diff | ✓ VERIFIED | Context-provided full run immediately pre-dating this verification session: `uv run pytest -q -m "unit or contract"` → **838 passed, 1 skipped, 1 failed, 374 deselected in 532s**. Independently re-ran the single failing test in isolation in this pass: `uv run pytest -m unit -q tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` → **1 failed**, traceback confirms `WorkerResultStatus.COMPLETED` returned instead of expected `FAILED` — i.e. a real Anthropic API call succeeded, which only happens because this sandbox has a working `ANTHROPIC_API_KEY`. This is the exact, independently-reproduced cause documented in 11-06/11-07/11-08/11-09/11-10-SUMMARY.md and 11-REVIEW.md, and the failing test file is untouched by any of the three gap-closure plans (`git log --since=2026-10-01T11:30:00Z -- tests/unit/test_worker_registry_names.py` → no commits) |
| 9 | No debt markers (`TBD`/`FIXME`/`XXX`) or `TODO`/`HACK`/`PLACEHOLDER` patterns in any file the G-11-3 gap-closure plans created or modified | ✓ VERIFIED | Fresh: `grep -rn -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across all 9 files touched by plans 11-08/09/10 (`publish.py`, `runner.py`, `log_sink.py`, `live_runtime.py`, `test_clarification_comment.py`, `test_global_settings_reads_are_declared.py`, `test_publish_idempotency.py`, `test_publish_step_unit.py`, `test_unit_tier_needs_no_database.py`, `tests/db/test_publish_idempotency.py`) → zero matches |
| 10 | Code review of the G-11-3 diff found no BLOCKER or WARNING-level defect | ✓ VERIFIED | Read `11-REVIEW.md` directly: `status: clean`, `critical: 0`, `warning: 0`, `info: 2` (both minor, non-blocking — a duplicated fake-token constant across two test files, and an AST-collector precision gap for lambda bodies that does not produce a false negative today). Independently spot-checked both claims against the source; accurate |
| 11 | SC3 (mechanical half, carried forward): `FakeWorker` suite maps to `db`-marked modules; `ci.yml` selects the `db` marker with no `services:`/secrets | ✓ VERIFIED | `git log --since=2026-10-01T11:30:00Z -- .github/workflows/ci.yml` → no commits. Fresh: included in the 43-passed structural sweep above (`test_qual01_ci_coverage.py`) |
| 12 | QUAL-01 requirement (production design improvement, not just test mock): the push-token fix is a genuine contract improvement, not merely a settings mock added to satisfy a test | ✓ VERIFIED | `publish.py`'s `push_token` parameter mirrors the function's own pre-existing `known_secrets` parameter precedent (settings-derived values arrive as explicit parameters, never read internally) — confirmed by direct read; this is the only one of G-11-3's three sinks where the fix touched production code rather than test infrastructure |
| 13 | **SC3 (live-CI half):** `ci.yml`'s `quality` job — including both the now-fixed `Unit and contract tiers` step and the `Database tier` step — runs green end-to-end on a real GitHub-hosted Actions runner | ⚠️ insufficient_spec | **Not re-observed.** `git status`/`git rev-list origin/...HEAD` confirm fresh: branch is **17 commits ahead of origin**, unpushed. The one real CI run that exists for this branch (run 36850439597, 2026-10-02) is the run that *discovered* G-11-3 (12 runtime failures) — it predates the fix. No CI run has ever seen the corrected `publish.py`/`runner.py`/test-support files. This is the identical class of gap UAT caught twice already (G-11-1 the first time, G-11-3 the second): code verified correct locally, never yet re-observed live |
| 14 | Backstop (11-01, D-05, carried forward): a real `workflow_dispatch` against a live repository with a real PAT starts a real `resume.yml` run that advances a real run past BA | ⚠️ insufficient_spec | **Not re-attempted.** 11-UAT.md records this as `status: blocked`, `blocked_by: third-party` — the Anthropic Console account's `ANTHROPIC_API_KEY` cannot make API calls (confirmed via direct Messages API call bypassing both the `claude` CLI and Dark Factory, reproduced across two regenerated keys). Unrelated to phase-11 code; still open |

**Score:** 12/14 truths VERIFIED in this re-verification pass (2 insufficient_spec, both carried forward and both requiring live infrastructure this sandbox cannot produce — a real GitHub-hosted Actions run requiring a `git push`, and a real worker API call currently blocked by an external billing issue).

### Fresh commands run in this verification pass

| Command | Result |
|---|---|
| `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_resume_workflow_reference_doc.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_webhook_process_boundary.py` | **43 passed** |
| `pytest -m unit -q tests/unit/test_global_settings_reads_are_declared.py` | **5 passed** |
| `pytest -m unit -q tests/unit/test_publish_idempotency.py tests/unit/test_publish_step_unit.py tests/unit/test_clarification_comment.py` | **25 passed** |
| `pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py` | **3 passed in 266.33s** |
| `pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py tests/db/test_publish_idempotency.py` (real Neon) | **14 passed in 527.97s** |
| `pytest -m unit -q tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` (isolated re-run of the one known failure) | **1 failed**, confirmed same root cause (live `ANTHROPIC_API_KEY` in sandbox) |
| `grep -n "get_settings\|import.*settings" src/dark_factory/orchestrator/publish.py` | zero matches |
| `grep -rn -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across all 9 G-11-3 gap-closure files | zero matches |
| `git status` / `git rev-list --count origin/...HEAD` | branch 17 commits ahead of origin, unpushed |
| `git log --since=2026-10-01T11:30:00Z -- <G-11-1/G-11-2 files>` | no commits — regression-only files confirmed unchanged since prior verification |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/orchestrator/publish.py` | No settings import; `run_publish_step` takes `push_token` as a required parameter | ✓ VERIFIED | Confirmed by direct read and grep; signature matches exactly |
| `src/dark_factory/orchestrator/runner.py` | Single call site derives `push_token` from `gate_settings`, no new `get_settings()` call | ✓ VERIFIED | Confirmed by direct read at the call site |
| `tests/unit/test_global_settings_reads_are_declared.py` | 18-entry bidirectional AST inventory, 5 tests incl. 2 positive controls | ✓ VERIFIED | Present, 5/5 passing fresh, non-vacuous tests confirmed by direct read |
| `tests/support/log_sink.py` | `real_log_sink()` only-when-absent env supply | ✓ VERIFIED | Confirmed by direct read, finally-block restore present |
| `tests/support/live_runtime.py` | `credential_missing()` catches `ValidationError` specifically | ✓ VERIFIED | Confirmed by direct read |
| `tests/unit/test_clarification_comment.py` | Driver patches all 3 `_run_current_role` settings reads | ✓ VERIFIED | 11/11 passing fresh (within the 25-passed combined run) |
| `tests/unit/test_unit_tier_needs_no_database.py` | 3-test runtime guard: full-tier property, live-suite adversary, positive control | ✓ VERIFIED | Present, 3/3 passing fresh (266.33s), all three test names confirmed by direct read |
| `src/dark_factory/webhook/app.py` (carried forward) | No module-level `build_app()` call | ✓ VERIFIED | Unchanged since prior verification; regression test passing |
| `README.md` (carried forward) | Worker-runtime table + commented install step | ✓ VERIFIED | Unchanged since prior verification; doc-drift guard passing |

Note: `gsd_run query verify.artifacts` returned 0 total for plans 11-08/09/10 because those plans'
`must_haves.truths` frontmatter uses bare strings (no `artifacts`/`key_links` blocks in the
`{path, provides}`/`{from, to, via}` object shape the tool parses) — a plan-authoring format
consistent with plans 11-06/11-07 in the prior verification pass, not a code defect. All artifacts
above were verified manually by direct file reads and fresh test runs.

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `runner.py`'s publish call site | `publish.py::run_publish_step` | `push_token=gate_settings.github_token...` keyword argument | ✓ WIRED | Confirmed by direct read: the token is threaded from the already-held `gate_settings`, not re-fetched |
| `tests/unit/test_global_settings_reads_are_declared.py`'s AST collector | every `.py` file under `src/dark_factory/` | `ast.walk` scope-stack collector | ✓ WIRED | 5/5 passing fresh, bidirectional set-equality assertion confirmed present in the file |
| `tests/unit/test_unit_tier_needs_no_database.py`'s Test 1 | `.github/workflows/ci.yml`'s `Unit and contract tiers` step marker expression | `yaml.safe_load` + `shlex` extraction (not restated) | ✓ WIRED | Confirmed by direct read of the test module's own extraction logic; 3/3 passing fresh |
| All key links from plans 11-01 through 11-07 (carried forward) | (unchanged by the G-11-3 diff) | — | ✓ WIRED | No file touched by those plans was modified since the prior verification pass (`git log --since` empty for each) |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| HITL-06 | 11-01, 11-02, 11-03, 11-05, 11-07 | Run resumable on a different machine/process | ✓ SATISFIED (mechanically) | Truth #7 (fresh db-tier run, 14/14 passing against real Neon); live re-proof (truth #14) still outstanding |
| TRIG-01 | 11-01, 11-03 | One orchestration implementation; zero lifecycle logic in triggers | ✓ SATISFIED | Truth #3 |
| TRIG-04 | 11-03, 11-07 | Local→CI boundary crossed through Neon alone | ✓ SATISFIED (mechanically) | Truths #1, #2, #7; live re-proof (truth #13) still outstanding |
| QUAL-01 | 11-04, 11-05, 11-06, 11-08, 11-09, 11-10 | `FakeWorker` suite tested end-to-end, runs green in CI with no `.env`/DB configured, no AI calls | ✓ SATISFIED (mechanically) / live-CI unconfirmed | Truths #4, #5, #6, #8, #9, #11, #12 — all newly, independently re-verified fresh in this pass; live re-proof (truth #13) still outstanding |

No orphaned requirements — REQUIREMENTS.md maps exactly TRIG-01, TRIG-04, HITL-06, QUAL-01 to
Phase 11, all four marked `[x]` Complete, and all four are claimed in at least one of the phase's
10 plans' frontmatter (confirmed by grepping every plan's `requirements:` field).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/dark_factory/webhook/app.py` | dispatch block (carried forward, unmodified by this gap closure) | No catch-all `except Exception` around the dispatch block | ⚠️ Warning | Carried forward unchanged from the 2026-09-30/10-01 reports (WR-01); not re-verified line-by-line this pass since the file is untouched by plans 11-08/09/10 (`git log --since` confirms no commits), but no evidence it was resolved either. Does not block any must-have truth in this phase. |
| `src/dark_factory/config/settings.py` | 141-163 | `LEASE_HEARTBEAT_SECONDS` accepts non-positive values | ℹ️ Info | Pre-existing since Phase 2, unmodified by this phase; carried forward (WR-02), not phase-11 scope |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any of the 9 files the G-11-3 gap-closure plans
created or modified. No `TODO`/`HACK`/`PLACEHOLDER` patterns found in those files either (fresh
grep, zero matches). `11-REVIEW.md`'s own independent review of the same 10-file diff (9 of the
same files plus `tests/db/test_publish_idempotency.py`) found 0 critical, 0 warning — only 2 minor
info-level observations, both confirmed accurate and non-blocking by this verifier.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| G-11-3 production sink: `publish.py` has no settings import | `grep -n "get_settings\|import.*settings" src/dark_factory/orchestrator/publish.py` | zero matches | ✓ PASS |
| G-11-3 production sink: push-token threading test suite | `pytest -m unit -q tests/unit/test_publish_idempotency.py tests/unit/test_publish_step_unit.py tests/unit/test_clarification_comment.py` | 25 passed | ✓ PASS |
| G-11-3 declared-inventory guard | `pytest -m unit -q tests/unit/test_global_settings_reads_are_declared.py` | 5 passed | ✓ PASS |
| G-11-3 recurrence guard (runtime, child-process, database-free) | `pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py` | 3 passed in 266.33s | ✓ PASS |
| SC1/HITL-06 cross-machine resume + dispatch + publish idempotency (post-`push_token`-threading regression) | `pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py tests/db/test_publish_idempotency.py` | 14 passed, 527.97s, real Neon | ✓ PASS |
| Carried-forward G-11-1/G-11-2 regression suites | `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_resume_workflow_reference_doc.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_webhook_process_boundary.py` | 43 passed | ✓ PASS |
| The one known pre-existing full-regression failure, isolated | `pytest -m unit -q tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` | 1 failed, confirmed sandbox-credential cause (real API call returns COMPLETED) | ✓ PASS (matches documented, independently-confirmed baseline) |
| Live GitHub Actions run of the G-11-3-fixed `ci.yml` | n/a — requires pushing the branch | not run | ? SKIP — routed to Human Verification #1 |
| Live `workflow_dispatch` + `dark-factory resume` against a real repository | n/a — blocked on external Anthropic billing | not run | ? SKIP — routed to Human Verification #2 |

### Requirements/Decision Coverage

All four phase-11 requirement IDs (TRIG-01, TRIG-04, HITL-06, QUAL-01) are addressed by must-have
truths above. CONTEXT.md decision-coverage is unaffected by this re-verification pass — the G-11-3
gap-closure plans addressed a defect found by UAT, not a new CONTEXT.md decision; no decisions were
abandoned.

### Human Verification Required

#### 1. A real GitHub Actions run of `ci.yml`'s `quality` job, including both the fixed `Unit and contract tiers` step and the `Database tier` step

**Test:** Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner.
**Expected:** The `Unit and contract tiers` step passes with 0 failed — no longer exiting 2 at collection (G-11-1, fixed 2026-10-01) and no longer failing 12 tests at runtime with `pydantic_core.ValidationError` (G-11-3, fixed 2026-10-02). The `Database tier (FakeWorker orchestration suite, QUAL-01)` step is actually reached, its `pytest_report_header` reports the `testcontainers` rung, the `db` tier passes against the `11-06-SUMMARY.md` baseline (205 passed/1 skipped), and both step/job durations sit inside their `[ASSUMED]` `timeout-minutes` budgets (20/30 — still literally marked `[ASSUMED]` in `ci.yml` as of this verification, confirmed by direct read). Replace the `[ASSUMED]` comments with measured values once observed.
**Why human:** This is the literal "provable in CI" half of the phase goal and ROADMAP SC3. It is the exact scenario UAT caught broken twice — first as G-11-1 (collection-time crash), then as G-11-3 (runtime validation failures) the very first time the G-11-1 fix was pushed and actually exercised live. Both root-cause fixes are independently re-verified correct and regression-free in this sandbox by every check available (direct source reads, 76 fresh unit-tier passes across 6 test modules, a 14-test real-Neon db-tier regression run, and the dedicated child-process runtime guard reproducing CI's own no-database condition) — but the branch carrying the G-11-3 fix has never been pushed. No local sandbox run can substitute for a real GitHub-hosted Actions execution; this exact category of gap (passes locally, fails live) is precisely what caught G-11-3 the first time.

#### 2. A live `workflow_dispatch` + `dark-factory resume` against a real repository, with the worker runtime installed

**Test:** Once the external Anthropic Console billing issue is resolved, re-run: pause a real run on a GitHub issue in the target repository, answer the clarifying comment, watch the dispatched `resume.yml` job, and confirm `dark-factory resume <run_id>` inside that job advances the run past BA (not a `FAILED` role execution), with `dark-factory status <run_id>` confirming the next state was reached.
**Why human:** This is the exact live path UAT test 2 originally ran and found broken (G-11-2, errno-2 "no such file or directory: claude"). The documentation fix is verified locally (unchanged since the prior verification pass, regression-tested fresh in this pass). Real progress was made toward re-attempting it (webhook invocation fixed, database alignment fixed, the actual G-11-2 fix pushed to the real target repo, the webhook mechanism confirmed end-to-end via a redelivered GitHub event) — but the attempt is blocked on an external, account-level Anthropic billing issue unrelated to any phase-11 code, confirmed via a direct Messages API call bypassing both the `claude` CLI and Dark Factory entirely, reproduced across two different API keys. No further automated verification can resolve this; it requires the account issue to clear and then a live re-attempt.

### Gaps Summary

G-11-3, the one gap this re-verification pass exists to close, has a real, substantive, well-tested
fix across three plans (11-08, 11-09, 11-10) that this verifier independently reproduced and
confirmed fresh — not taken on the SUMMARYs' word. `publish.py` genuinely no longer reads
process-global settings (confirmed by direct grep and read of the exact call site in `runner.py`
that now threads the token through). The test-infrastructure sinks (`log_sink.py`,
`test_clarification_comment.py`, `live_runtime.py`) are genuinely fixed at the shared-helper layer,
confirmed by direct reads matching the documented only-when-absent and specific-exception patterns.
The recurrence guard (`tests/unit/test_unit_tier_needs_no_database.py`) is genuinely non-vacuous —
its three test names, including the positive control, were confirmed present by direct read and all
three pass fresh in 266.33s. The post-fix cross-machine-resume, webhook-dispatch and
publish-idempotency db-tier tests pass fresh against real Neon PostgreSQL (14/14, no regression from
the `runner.py`/`publish.py` diff), and the full unit+contract regression reproduces exactly the
documented baseline (one known, independently-reproduced, sandbox-credential-only failure unrelated
to any file this gap closure touched).

What remains open is not a code defect but un-collected live evidence — the same category of gap
this phase has now caught twice (G-11-1, then G-11-3), both times only visible when the system was
actually exercised against real infrastructure rather than this sandbox. The branch carrying the
G-11-3 fix commits has never been pushed, so no CI run has ever seen the corrected code; and the
second live `workflow_dispatch`-to-resume attempt remains blocked on an external billing issue,
unrelated to this phase. Routed to Human Verification rather than FAILED, because the root-cause
fixes themselves — the actual code and the actual regression-free re-verification of that code — are
independently confirmed correct by every check this sandbox can run, and no `gaps:` condition
(FAILED truth, MISSING/STUB artifact, NOT_WIRED key link, or BLOCKER anti-pattern) is present.

---

_Verified: 2026-10-02T13:05:00Z_
_Verifier: Claude (gsd-verifier)_
