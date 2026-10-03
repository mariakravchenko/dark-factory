---
status: complete
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-10-01T11:35:00Z
updated: 2026-10-03T06:35:00Z
---

## Current Test

[testing complete — both tests PASSED. Test 1 on real CI (run 37011371774) after closing
G-11-3 and G-11-4 (db tier env propagation). Test 2 on a real GitHub Actions resume (run
37103322812) after closing G-11-5 (cross-machine session resume) and G-11-6 (reference
workflow git-configuration gaps, two parts). The Anthropic Console billing issue that
originally blocked Test 2 resolved externally before this session's retest.]

## Tests

### 1. A real GitHub Actions run of the fixed `ci.yml`'s `quality` job
expected: |
  Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job
  run to completion on a real GitHub-hosted runner. The `Unit and contract tiers` step passes
  (no longer exits 2 at collection), the `Database tier (FakeWorker orchestration suite,
  QUAL-01)` step is reached and its `pytest_report_header` reports the `testcontainers` rung,
  the ~205-test `db` tier passes, and both step/job durations sit inside their `[ASSUMED]`
  budgets (20/30 min). This is the exact scenario UAT test 1 originally ran and found broken
  (G-11-1): the branch carrying the fix commits has never been pushed, so no CI run has ever
  seen the corrected `webhook/app.py`.
result: pass
observed_2026_10_02_final: |
  CI run https://github.com/mariakravchenko/dark-factory/actions/runs/37011371774 — green,
  whole `quality` job in 3m23s. `Unit and contract tiers`: 849 passed, 0 failed, 73.24s
  (confirms G-11-3 closed on a real runner). `Database tier`: 205 passed, 0 failed, 69.30s
  (matches 11-06-SUMMARY.md's local 205-passed baseline exactly — confirms G-11-4 closed).
  Both step durations sit inside their `[ASSUMED]` budgets (20/30 min) with large margin;
  `ci.yml`'s two `[ASSUMED]` comments have been replaced with these measured values.
  This followed one intermediate run (36994498994) that caught G-11-4 (db tier failing with
  the same "Field required" signature as G-11-3, for a sibling reason: tests/conftest.py
  never propagated the testcontainers URL into DATABASE_URL env for production code reached
  by db-tier tests) — fixed in commit d66c959, re-pushed, and confirmed green above.
result_history: "issue"
reported: "test fsiled"
severity: blocker
ci_run: https://github.com/mariakravchenko/dark-factory/actions/runs/36994498994
observed_2026_10_02: |
  Re-ran after the G-11-3 fix (plans 11-08/09/10) landed and was pushed for the first time.
  Progress: the `Unit and contract tiers` step now PASSES (the literal G-11-3 failure is
  confirmed fixed on a real hosted runner — all 12 originally-failing tests green, plus
  lint/mypy/worker-name-leak guard all green). This is new evidence this truth is partially
  met.
  However, the `Database tier (FakeWorker orchestration suite, QUAL-01)` step — reached for
  the first time ever in CI, since it always aborted earlier before this fix — now fails:
  101 failed, 90 passed, 14 errors, all with the identical
  `pydantic_core.ValidationError: 2 validation errors for Settings (database_url,
  database_url_direct Field required)` signature. Root cause (confirmed by reading
  tests/conftest.py): the testcontainers-provisioned Postgres URL is yielded only through
  the `pg_url`/`engine` pytest fixtures for the test's OWN direct SQLAlchemy use — nothing
  in conftest.py ever writes it into `os.environ["DATABASE_URL"]`/`DATABASE_URL_DIRECT`, so
  any db-tier test that exercises production code calling `get_settings()` (e.g.
  `orchestrator.runner.advance`/`drive`/`start_run`) still needs that env var set, same as
  G-11-3's pattern — but this repo's local `.env` has always silently supplied one,
  masking the gap in the db tier exactly as it did in the unit/contract tier. This is a
  SIBLING gap, not G-11-3 itself: G-11-3's 3 gap-closure plans were explicitly scoped to
  the unit/contract tier only (`tests/db/test_publish_idempotency.py` was touched only to
  keep one call site compiling, nothing about this db-tier-wide env propagation gap).
  Logged as a new gap below (G-11-4) rather than reopening G-11-3.
  CI run: https://github.com/mariakravchenko/dark-factory/actions/runs/36994498994
observed: |
  Pushed the branch (first time ever — 16 commits, never previously on origin) and watched
  the real `quality` job run. The `Unit and contract tiers` step itself FAILED (not the
  collection-time crash G-11-1 originally reported — collection now succeeds, confirming
  11-06's fix works for the three originally-named modules). Instead, 12 tests across 4
  files failed at RUNTIME with the identical signature G-11-1 diagnosed —
  `pydantic_core.ValidationError: 2 validation errors for Settings` naming `database_url` /
  `database_url_direct` — because this is the first time this branch's test suite has ever
  run in an environment with no `.env` file to paper over a bare `Settings()` construction:
    - tests/unit/test_clarification_comment.py::test_raising_create_comment_still_pauses_with_no_id_recorded
      (via runner.py:1685 _run_current_role -> get_settings() -> Settings())
    - tests/unit/test_publish_idempotency.py (3 tests)
    - tests/unit/test_publish_step_unit.py (3 tests)
    - tests/unit/test_webhook_signature.py (5 tests — including tests G-11-1's own gap_context
      named as already-fixed: test_missing_github_token_logs_loudly_at_construction,
      test_missing_github_webhook_secret_logs_loudly_at_construction,
      test_fully_configured_settings_log_no_startup_warning,
      test_missing_dispatch_github_token_logs_a_warning_not_an_error,
      test_injected_authenticated_login_skips_the_startup_check)
  Because this step failed, the `Database tier (FakeWorker orchestration suite, QUAL-01)`
  step never ran (skipped) — so the second half of this test (db tier green, testcontainers
  rung, duration budgets) could not even be attempted. 828 passed / 12 failed / 374
  deselected in 36.81s.

### 2. A live `workflow_dispatch` + `dark-factory resume` against a real repository, with the worker runtime installed
expected: |
  Copy the corrected reference `resume.yml` block from README into a real target repository,
  follow the new "### The worker runtime" subsection to install the binary the repository's
  configured roles need, pause a real run on a GitHub issue, answer the clarifying comment,
  and watch the Actions tab. `dark-factory resume <run_id>` inside that job advances the run
  past BA instead of recording a `FAILED` role execution with an errno-2 "no such file or
  directory" error, and `dark-factory status <run_id>` confirms the run reached its next
  state. This is the exact live path UAT test 2 originally ran and found broken (G-11-2): no
  second live attempt against a real repository has been recorded since the README fix
  landed.
result: pass
observed_2026_10_03_final: |
  Full live chain confirmed, after fixing three real bugs this attempt uncovered in
  sequence (G-11-5, G-11-6 parts a/b -- see Gaps below):
  - `dark-factory run github:21` locally: CREATED -> BA -> ARCHITECTURE -> WAITING_HUMAN
    (BA completed and pushed locally; ARCHITECTURE paused with a clarifying question).
  - Replied on the issue; the receiver's own log showed `run.resumed` then
    `webhook.dispatch.requested workflow=resume.yml` -- the automatic laptop -> CI dispatch,
    confirmed working.
  - `dark-factory resume` inside a real GitHub Actions job (run 37103322812) advanced:
    ARCHITECTURE -> COMPLETED (pushed) -> DEVELOPMENT -> FAILED. The FAILED is a real,
    expected guardrail catching a scope mismatch in app-new's OWN config ("role DEVELOPMENT
    attempt 1 wrote outside its configured write_scope ['src/**', 'package.json',
    'supabase/migrations/**']: ['contact.html']") -- not an infra defect, not related to
    cross-machine resume, and outside this test's own claim.
  - `dark-factory status 43321bac-...` confirmed the run reached DEVELOPMENT (its next
    state past BA/ARCHITECTURE) before that unrelated scope guardrail stopped it -- exactly
    the literal claim this test exists to prove.
  This is the first real CI run that ever advanced a laptop-paused run this far. The three
  bugs found and fixed along the way (G-11-5 native-resume session locality; G-11-6a
  checkout credential scope; G-11-6b shallow-clone merge-base) are now also fixed in
  dark-factory's own README reference workflow, so a future deployer following the docs
  inherits all three fixes rather than rediscovering them.
severity: blocker
reason_historical_blocked: "Anthropic Console account's ANTHROPIC_API_KEY cannot currently make API calls ('Your credit balance is too low to access the Anthropic API', HTTP 400) despite the account showing a $5.97 balance. Confirmed via direct Messages API call (bypassing both the claude CLI and Dark Factory entirely) that this is Anthropic's own live billing answer, not a local cache/propagation issue: reproduced identically across two different API keys (original + freshly regenerated), across multiple retries spanning several minutes, with the user confirming same account, single default workspace, no multi-workspace spend-limit split. This blocks only the LOCAL run needed to reach a WAITING_HUMAN pause in this sandbox -- it is an external account/billing issue, unrelated to any phase 11 code or documentation."
progress_made: |
  Significant real progress before hitting the original billing blocker:
  - Found and fixed the webhook receiver invocation itself needed `dark_factory.webhook.app:build_app --factory` (not `:app`) to match 11-06's factory refactor -- confirmed via a live GitHub webhook ping returning 200 OK.
  - Found and fixed a database mismatch: the local receiver's DATABASE_URL and app-new's GitHub Actions `DATABASE_URL` secret pointed at different Neon projects; realigned to the same `ep-holy-bread-ae7sz0rt` instance.
  - Pushed the actual G-11-2 fix to the real target repo (`mariakravchenko/app-new`, commit 4e82ee6): added the `npm install -g @anthropic-ai/claude-code` step to `resume.yml`, matching README's corrected reference block.
  - Confirmed the webhook mechanism itself works end-to-end: redelivered a real GitHub `issue_comment` webhook event and got a 200 response from the live receiver.
  - Confirmed `claude` CLI itself is healthy (works fine under the user's own logged-in session) -- the failure is specific to the `ANTHROPIC_API_KEY` env var the worker adapter injects per CLAUDE.md's credential-boundary design, whose account cannot currently bill.
  - Discovered a secondary, unrelated fact: issue #15 (the original test issue) can no longer produce a fresh `WAITING_HUMAN` pause, because `dark-factory run`'s github source reader folds the entire existing comment thread (including the already-posted answer) into the initial task body -- opened issue #16 as a clean replacement for future retries.
observed_2026_10_02: |
  Billing issue resolved externally (confirmed via a direct Messages API call returning HTTP 200). Retried the full live path with a fresh issue (#18, replacing #16):
  - `dark-factory run github:18` reached `WAITING_HUMAN` on the first try -- but only after discovering app-new's own `.env` held a SEPARATE, stale/invalid ANTHROPIC_API_KEY (401 "API key is invalid", distinct from the earlier 400 billing error) -- the first attempt failed outright with that error before this was found and the key was synced to match the working one.
  - Posted a reply on issue #18 via `gh issue comment`.
  - The webhook -> workflow_dispatch chain WORKED END TO END: the local receiver's own logs show `run.resumed role=BA run_id=472dc760-...` followed by `webhook.dispatch.requested run_id=472dc760-... workflow=resume.yml`, and GitHub Actions genuinely ran `dark-factory resume "472dc760-..."` inside a real CI job -- this is the core G-11-2/HITL-06 claim, proven for the first time.
  - BUT that CI-side resume then failed: `claude exited 1: No conversation found with session ID: f3acabd4-...`. Root cause: Claude Code's own session transcripts are local-filesystem state on the machine that creates them -- never synced anywhere, not even through Neon. BA's original attempt ran on the laptop and recorded that session id; CI is a different, ephemeral machine that has never seen it. `ClaudeCodeWorker._resume`'s native branch (`--resume <session_id>`) assumed any recorded session id was reachable from anywhere, which this test disproves. Logged as a new gap (G-11-5) rather than folding into G-11-2 (a different symptom: G-11-2 was a missing binary; this is a missing session on an otherwise-correct binary).
  - Confirmed via code read: the actual files/branch state is NOT missing anything -- `ensure_worktree` (`src/dark_factory/git/worktree.py:46`) already has a dedicated "local->CI-handoff / ephemeral-runner" path that fetches the run's branch from `origin` when reconstructing on a new machine, and the existing HITL-05 context-reconstruction fallback (`build_resume_prompt`) already rebuilds a complete, self-sufficient prompt (task, prior summary, questions, answer) with no dependency on Claude's own session memory. Only Claude's own conversational memory of *how it was reasoning* during the first attempt is genuinely local-only and unrecoverable -- not any task/file state.
next_step: "G-11-5 is fixed (see Gaps below) -- re-run the live path once more: `dark-factory run github:<new-issue>` from /Users/maryiakrauchanka/portfolio/app-new, wait for WAITING_HUMAN, reply on the issue, wait for the webhook-dispatched resume.yml run, and confirm `dark-factory status <run_id>` shows the run actually advanced past BA this time."

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-11-3
  truth: "The `Unit and contract tiers` CI step passes with no `DATABASE_URL` configured — the same no-database constraint G-11-1 established, generalized to every test the unit/contract tier selects."
  status: resolved
  resolved_by: 11-08-PLAN.md, 11-09-PLAN.md, 11-10-PLAN.md
  resolved_at: 2026-10-02
  resolution_note: |
    All 5 `missing:` items below are now closed locally: 11-08 threaded push_token as a
    parameter (closes the publish.py sink) and added the declared settings-read inventory
    guard; 11-09 fixed real_log_sink (only-when-absent), the clarification-comment driver
    (all 3 _run_current_role reads), and credential_missing (unconstructible Settings ->
    absent, not a raise); 11-10 added the actual recurrence guard
    (test_unit_tier_needs_no_database.py) spawning a child process that proves the whole
    unit/contract tier is green with no DATABASE_URL and no .env. Sanitized full-tier run:
    835 passed, 1 skipped, 374 deselected, 0 of the original 12 failures remain (one
    unrelated pre-existing failure documented separately). NOT yet re-observed on a real
    GitHub-hosted runner — Test 1 below still requires a fresh push to close that loop; this
    branch has not been pushed since the last CI run that originally reported G-11-3.
  reason: "Real CI run (https://github.com/mariakravchenko/dark-factory/actions/runs/36850439597) failed with 12 tests raising pydantic_core.ValidationError (database_url/database_url_direct Field required) across tests/unit/test_clarification_comment.py, test_publish_idempotency.py, test_publish_step_unit.py, and test_webhook_signature.py — the identical error signature G-11-1 diagnosed, in modules 11-06's fix did not cover. This branch had never been pushed to CI before this run, so the gap was latent since whichever phase introduced each of these tests, invisible locally because every local run inherits this repo's git-ignored .env."
  severity: blocker
  test: 1
  root_cause: |
    A three-condition AND, confirmed 3/3 with control runs (removing any one condition makes
    all 12 failures vanish): (1) three production call sites invoke the process-global
    get_settings() on conditionally-taken branches that unit tests legitimately reach --
    src/dark_factory/logging.py:37/:28 (_configured_level / _redaction_processor, reached via
    tests/support/log_sink.py::real_log_sink -- 5 failures), src/dark_factory/orchestrator/
    publish.py:272 (the push-token read in run_publish_step, taken when the git spy returns a
    commit SHA and published_commit_sha is unset -- 6 failures), and
    src/dark_factory/orchestrator/runner.py:1685 (the except GitHubError fail-soft redaction
    in _run_current_role's NEEDS_INPUT arm -- 1 failure); (2) the four offending test files
    adopted neither of the two settings-override idioms already used at 14 other unit-tier
    sites (monkeypatch.setenv + get_settings.cache_clear(), or monkeypatch.setattr on
    get_settings itself); (3) Settings.model_config's env_file=".env" is CWD-relative, so this
    repo's git-ignored .env silently satisfies both required fields on every local run --
    purely the masking mechanism, not the defect. All four offending files are Phase 10
    (plans 10-02/03/04/06); three open with an explicit "No database:" docstring claim that is
    true about never opening a Postgres connection and wrong about Settings construction
    requiring a DATABASE_URL *string* to be present. 11-06's import-time guard
    (test_webhook_import_needs_no_database.py) could not have caught this: it proves an
    import-time property via pkgutil.walk_packages over the dark_factory package and never
    imports anything under tests/, so it cannot observe a call made during test *execution*.
    Two findings beyond the originally reported scope: runner.py:1415 is a fourth armed
    landmine on the same _run_current_role path test_clarification_comment.py already drives
    (survived only because the fake worker's commit_run_artifacts returns None); and
    tests/support/live_runtime.py:89's credential_missing() is a strictly worse sibling that
    raises the same ValidationError at *module import* for live-CLI integration tests when a
    worker binary is on PATH (Interrupted: N errors during collection, 0 tests run) -- CI
    escapes this only because the hosted runner lacks the agent CLIs, but any environment that
    installs them (ci.yml:56-60 contemplates this for a future phase) would hit it.
  artifacts:
    - path: src/dark_factory/orchestrator/publish.py
      issue: "run_publish_step's push-token read at line 272 calls get_settings() directly instead of using the settings-derived values the function's caller (runner.py:1340-1348) already computed and the function already threads through for known_secrets (used at :331, :358) -- the one call site violating the function's own existing contract"
    - path: src/dark_factory/orchestrator/runner.py
      issue: "_run_current_role has four existing injection seams but three un-injected get_settings() calls remain on conditionally-taken branches: line 1685 (the reported failure) and line 1415 (undiagnosed landmine on the same code path, armed whenever a worker's commit_run_artifacts returns non-None)"
    - path: src/dark_factory/logging.py
      issue: "_configured_level (line 37) and _redaction_processor (line 28) call get_settings() with no override seam; reached via tests/support/log_sink.py::real_log_sink, a shared test-support fixture used by 5 of the 12 failing tests"
    - path: tests/support/live_runtime.py
      issue: "credential_missing() (line 89) calls get_settings() at a point reached during module IMPORT for live-CLI integration tests (test_claude_code_live.py, test_copilot_live.py) -- strictly worse than a test-execution failure, since it would abort collection entirely (0 tests run) the moment a worker binary is on PATH, e.g. once CI provisions agent CLIs for a later phase"
  missing:
    - "Thread the already-available settings-derived push_token value into run_publish_step's token read at publish.py:272, removing that get_settings() call (closes 6 of 12 -- the only sink where the fix is a production design improvement, not just a test mock)"
    - "Add a settings-override seam (or apply Idiom B: monkeypatch.setattr(..., 'get_settings', ...)) covering BOTH runner.py:1685 and runner.py:1415 together -- a fix touching only :1685 leaves :1415 armed for the next test that exercises a worker whose commit_run_artifacts returns non-None"
    - "Fix tests/support/log_sink.py::real_log_sink once (not each of its 5 call sites) to supply a fake DATABASE_URL/DATABASE_URL_DIRECT via monkeypatch + get_settings.cache_clear() when they are absent -- never override when present, since tests/unit/test_log_redaction.py deliberately sets its own FAKE_LIVE_DB_URL and asserts it is scrubbed; an unconditional override would make those assertions vacuous"
    - "Fix tests/support/live_runtime.py's credential_missing() to check for a missing ANTHROPIC_API_KEY/credential field without triggering a full Settings() construction that also requires database_url -- or supply a database-free settings path for this specific probe"
    - "Add the actual G-11-3 deliverable: a runtime analogue of 11-06's import-time guard -- a child `pytest -m \"unit or contract\"` process spawned with cwd=tmp_path and an explicit env allowlist omitting DATABASE_URL/DATABASE_URL_DIRECT, reusing test_webhook_import_needs_no_database.py's _ENV_ALLOWLIST/_sanitized_env idiom, with a positive control mirroring that file's Test 4, so this defect class cannot return silently a third time"
  debug_session: .planning/debug/ci-unit-tier-settings-validation-g-11-3.md

- gap_id: G-11-4
  truth: "The `Database tier (FakeWorker orchestration suite, QUAL-01)` CI step passes when DATABASE_URL/DATABASE_URL_DIRECT are not pre-set in the environment (same no-stray-.env constraint G-11-1/G-11-3 established, now for the db tier's own provisioning path)."
  status: resolved
  resolved_by: "tests/conftest.py commit d66c959 (_database_url_env autouse fixture)"
  resolved_at: 2026-10-02
  resolution_note: |
    Added an autouse, db/integration-scoped session fixture that propagates the
    testcontainers-provisioned pg_url into os.environ["DATABASE_URL"]/["DATABASE_URL_DIRECT"]
    only when absent (same only-when-absent idiom as G-11-3's real_log_sink fix). Verified
    locally against a 12-test sanitized subset (was failing, now passing) and against the
    real CI run (37011371774): Database tier 205 passed, 0 failed, 69.30s -- matches
    11-06-SUMMARY.md's known-good baseline exactly.
  reason: "First-ever real CI run of this step (https://github.com/mariakravchenko/dark-factory/actions/runs/36994498994, 2026-10-02) — reached for the first time because G-11-3's fix let the prior `Unit and contract tiers` step pass — failed with 101 failed, 90 passed, 14 errors, all `pydantic_core.ValidationError: database_url / database_url_direct Field required`."
  severity: blocker
  test: 1
  root_cause: |
    tests/conftest.py's testcontainers-backed `pg_url`/`engine` fixtures yield a Postgres URL
    for a test's OWN direct SQLAlchemy use, but nothing writes that URL into
    os.environ["DATABASE_URL"]/["DATABASE_URL_DIRECT"]. Any db-tier test that drives
    production code calling get_settings() (orchestrator.runner.advance/drive/start_run, and
    transitively anything they call) still needs those two env vars set — identical defect
    class to G-11-1/G-11-3, just in the db tier's own harness instead of the unit/contract
    tier's test-support layer. This repository's git-ignored .env has, until this run,
    silently supplied values for every local db-tier run (the same masking mechanism G-11-3's
    root_cause already documented), so the gap was invisible locally and never previously
    reached in CI (every prior CI run aborted at an earlier step).
  artifacts:
    - path: tests/conftest.py
      issue: "pg_url/engine fixtures (session-scoped) never propagate the testcontainers-provisioned URL into os.environ['DATABASE_URL']/['DATABASE_URL_DIRECT'], so get_settings() calls reached by db-marked tests still require those vars from elsewhere"
  missing:
    - "Decide and implement the propagation mechanism: either an autouse db-scoped fixture that sets os.environ['DATABASE_URL']/['DATABASE_URL_DIRECT'] from the resolved pg_url before any db-marked test body runs (restoring on teardown), or audit whether orchestrator.runner's db-tier-reached call sites actually need get_settings().database_url at all versus just the SQLAlchemy engine/session already provided by fixtures"
    - "A sanitized-environment reproduction of the db tier (DATABASE_URL/DATABASE_URL_DIRECT absent, cwd with no .env, testcontainers rung) to confirm the fix and prevent recurrence, mirroring 11-10's unit/contract guard but for -m db"
  debug_session: null

- gap_id: G-11-5
  truth: "`dark-factory resume <run_id>` succeeds when the paused role's recorded worker_session_id was created on a DIFFERENT machine than the one performing the resume (the HITL-06 / phase-goal claim: a run started on a laptop finishes in CI)."
  status: resolved
  resolved_by: "src/dark_factory/workers/claude_code.py commit 457dbf5 (_resume fallback) + tests/unit/test_claude_code_worker.py commit 5192fd0"
  resolved_at: 2026-10-02
  reason: "Live attempt (dark-factory run 472dc760-8b4e-4473-b5ad-63b8247ba1fe, 2026-10-02, app-new#18): the webhook -> workflow_dispatch -> CI chain worked end to end (receiver logs show run.resumed then webhook.dispatch.requested; GitHub Actions genuinely ran dark-factory resume inside a real job), but that CI-side resume failed with `claude exited 1: No conversation found with session ID: f3acabd4-...`."
  severity: blocker
  test: 2
  root_cause: |
    Claude Code's own session transcripts are local-filesystem state on the machine that
    creates them -- never synced to Neon or anywhere else. `ClaudeCodeWorker._resume`'s
    native branch (HITL-04) calls `claude --resume <session_id>` whenever a previous
    attempt recorded a worker_session_id, with no check for whether that session is
    reachable from the current machine. A laptop-pause -> CI-resume hits this every time;
    same-machine resume never does.
    This is the identical constraint `07-COVERAGE.md` already named when it explicitly
    rejected Claude Code's `--continue` flag ("process-local state, incompatible with a
    durable orchestrator that resumes ... on a different machine") -- but that reasoning
    was never applied to `--resume <session-id>`, which has the same locality constraint,
    just addressed explicitly instead of implicitly. Confirmed genuinely new (not a known,
    accepted limitation) via a dedicated research pass over `.planning/`: no ADR, no
    PITFALLS.md entry, no accepted-limitation note connects the two. `HITL-06`'s own proof
    (`tests/db/test_cross_machine_resume.py`) uses `FakeWorker`, which never shells out to
    the real `claude` binary -- structurally incapable of catching this, which is why it
    went undetected until a real live attempt against a real `claude-code` worker.
  artifacts:
    - path: src/dark_factory/workers/claude_code.py
      issue: "_resume's native branch (HITL-04) had no fallback when claude --resume <session_id> fails because the session is unreachable from the current machine -- the failure propagated as a generic FAILED role execution with no retry"
  missing:
    - "A fallback from the native --resume attempt to the existing HITL-05 context-reconstruction path, specifically when (and only when) the failure is the CLI's own session-not-found signature -- never for any other native-resume failure, which must still surface unchanged"
  fix_note: |
    Implemented as: on `--resume` failure, check whether `WorkerResult.error` contains the
    CLI's literal "No conversation found with session ID" text; if so, retry once via the
    existing HITL-05 argv (no --resume element) instead of returning the native failure.
    Verified nothing else needed reconstructing: `ensure_worktree`
    (`src/dark_factory/git/worktree.py:46`) already has a dedicated path for "the local->CI-
    handoff / ephemeral-runner case" that fetches the run's branch from `origin`, and
    `build_resume_prompt` already assembles a complete, self-sufficient prompt (task, prior
    summary, questions, human answer) with no dependency on Claude's own session memory --
    only Claude's own reasoning-trace memory is genuinely unrecoverable, and the fallback
    never needed it.
    Unit-tested with a resume-aware fake `claude` binary whose behaviour depends on whether
    `--resume` is in argv (two sequential invocations, not a single fixed response) --
    proving both the fallback fires on the exact real-world signature and that it does NOT
    fire on an unrelated native failure (no masking of genuine bugs). Full regression:
    `pytest -q -m "unit or contract"` -> 840 passed (+2 from the new tests), 1 skipped, 374
    deselected, the one pre-existing unrelated failure unchanged. `mypy src/dark_factory`:
    clean (2 pre-existing unrelated errors, mcp extra not installed). `ruff check .` /
    `ruff format --check .`: clean.
    Re-confirmed live end-to-end on 2026-10-03 (run 43321bac-c4fd-4bbe-a79e-4632859fc837,
    CI run 37103322812): ARCHITECTURE's native --resume attempt against a session created
    on the laptop correctly fell back and completed, producing a fresh session id and
    pushing real work -- see Test 2's final observed_2026_10_03_final entry above.
  debug_session: null

- gap_id: G-11-6
  truth: "`dark-factory resume` inside a GitHub Actions job, dispatched from a laptop-paused run, completes a role (push included) and lets a later role's quality-gate diff collection succeed -- the full local->CI handoff, not just the resume call itself."
  status: resolved
  resolved_by: "app-new commits 0e583b6 + 0a21f48; dark-factory README.md commits 1ab7784 + 0670376"
  resolved_at: 2026-10-03
  reason: "Live attempts against app-new#20/#21 (2026-10-03) surfaced two further CI-only git-configuration gaps in the reference resume.yml, past G-11-5: a push-credential scope problem and a shallow-clone merge-base problem. Neither is a dark-factory code defect -- both are gaps in the reference resume.yml's own actions/checkout configuration, which every deployer copies verbatim."
  severity: blocker
  test: 2
  root_cause: |
    Part a (push credential scope): the reference resume.yml declared `permissions:
    contents: read`. `actions/checkout@v4`'s default (`persist-credentials: true`) writes
    git's own credential config from exactly that scope, and git consults that config for
    ANY later push before ever trying dark-factory's own GIT_ASKPASS-based push token --
    so the push used the wrong (read-only) credential and failed with "Write access to
    repository not granted", even though the custom push token itself was valid. A first
    attempted fix (`persist-credentials: false`) treated this as "remove the interfering
    credential" and broke something worse: `ensure_worktree`'s git-level branch
    reconstruction (fetching a run's branch when resuming on a machine that never created
    it) has NO credential channel of its own -- it relies entirely on whatever checkout
    configured. With no credential at all, that fetch failed silently, `ensure_worktree`
    fell through to creating an empty worktree off `main`, and the next role's
    `read_artifact_text` failed with `MissingArtifactContentError` -- a different, harder
    failure than the one being fixed. The correct fix is `permissions: contents: write`,
    which makes checkout's own default credential satisfy both halves at once.
    Part b (shallow clone): `actions/checkout@v4`'s other default, `fetch-depth: 1`, fetches
    only the tip of the default branch. Once a role actually completed (part a fixed) and a
    later role's quality-gate after-hook ran `collect_pr_diff`'s `git diff
    main...dark-factory/run-<id>` (a merge-base, triple-dot diff), the shallow clone had no
    shared ancestor to find at all, since `main` had moved on since the run branch forked
    from it: `fatal: main...dark-factory/run-<id>: no merge base`. `fetch-depth: 0` is the
    fix; any fixed shallow depth only relocates the same failure further out.
    Both gaps are specifically CI-only: a local resume on the machine that created the
    worktree never exercises checkout's credential config or a shallow clone at all, which
    is why neither surfaced until this phase's actual live CI resume attempt -- the same
    "invisible until proven live" pattern as G-11-1/G-11-3/G-11-4/G-11-5, just one layer
    further out (the reference workflow's own git plumbing, not dark-factory's own code).
  artifacts:
    - path: README.md
      issue: "the resume-workflow-reference block declared permissions: contents: read (too narrow for the push this job performs) and omitted fetch-depth entirely (defaulting to a shallow clone too thin for a later merge-base diff) -- every deployer following the docs verbatim would hit both"
  missing:
    - "permissions: contents: write on the reference workflow (closes the push-credential gap without the persist-credentials:false detour that breaks fetch instead)"
    - "fetch-depth: 0 on the reference workflow's checkout step (closes the shallow-clone merge-base gap)"
  fix_note: |
    Both fixes verified live: app-new#21 / run 43321bac-c4fd-4bbe-a79e-4632859fc837 advanced
    ARCHITECTURE -> COMPLETED (real push) -> DEVELOPMENT -> FAILED (an unrelated, legitimate
    write_scope guardrail, not a git-configuration failure) in CI run 37103322812. Applied
    to README.md's resume-workflow-reference block with matching prose explaining both
    failure modes and why the more conservative-looking read-only / persist-credentials:false
    combination is the wrong fix. `tests/unit/test_resume_workflow_reference_doc.py`: all 13
    cases green after each edit.
  debug_session: null

