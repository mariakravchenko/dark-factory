---
status: diagnosed
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-10-01T11:35:00Z
updated: 2026-10-02T00:00:00Z
---

## Current Test

[testing paused — blocked on external billing issue, see Test 2]

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
result: issue
reported: "test fsiled"
severity: blocker
ci_run: https://github.com/mariakravchenko/dark-factory/actions/runs/36850439597
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
result: blocked
blocked_by: third-party
reason: "Anthropic Console account's ANTHROPIC_API_KEY cannot currently make API calls ('Your credit balance is too low to access the Anthropic API', HTTP 400) despite the account showing a $5.97 balance. Confirmed via direct Messages API call (bypassing both the claude CLI and Dark Factory entirely) that this is Anthropic's own live billing answer, not a local cache/propagation issue: reproduced identically across two different API keys (original + freshly regenerated), across multiple retries spanning several minutes, with the user confirming same account, single default workspace, no multi-workspace spend-limit split. This blocks only the LOCAL run needed to reach a WAITING_HUMAN pause in this sandbox -- it is an external account/billing issue, unrelated to any phase 11 code or documentation."
progress_made: |
  Significant real progress before hitting this blocker:
  - Found and fixed the webhook receiver invocation itself needed `dark_factory.webhook.app:build_app --factory` (not `:app`) to match 11-06's factory refactor -- confirmed via a live GitHub webhook ping returning 200 OK.
  - Found and fixed a database mismatch: the local receiver's DATABASE_URL and app-new's GitHub Actions `DATABASE_URL` secret pointed at different Neon projects; realigned to the same `ep-holy-bread-ae7sz0rt` instance.
  - Pushed the actual G-11-2 fix to the real target repo (`mariakravchenko/app-new`, commit 4e82ee6): added the `npm install -g @anthropic-ai/claude-code` step to `resume.yml`, matching README's corrected reference block.
  - Confirmed the webhook mechanism itself works end-to-end: redelivered a real GitHub `issue_comment` webhook event and got a 200 response from the live receiver.
  - Confirmed `claude` CLI itself is healthy (works fine under the user's own logged-in session) -- the failure is specific to the `ANTHROPIC_API_KEY` env var the worker adapter injects per CLAUDE.md's credential-boundary design, whose account cannot currently bill.
  - Discovered a secondary, unrelated fact: issue #15 (the original test issue) can no longer produce a fresh `WAITING_HUMAN` pause, because `dark-factory run`'s github source reader folds the entire existing comment thread (including the already-posted answer) into the initial task body -- opened issue #16 as a clean replacement for future retries.
next_step: "Once the ANTHROPIC_API_KEY account issue is resolved (likely needs Anthropic support, since the discrepancy between displayed balance and live API billing enforcement could not be explained by key regeneration, workspace limits, or propagation delay), re-run: `dark-factory run github:16` from /Users/maryiakrauchanka/portfolio/app-new, wait for a WAITING_HUMAN pause, reply on the issue, then redeliver/wait for the webhook, and watch https://github.com/mariakravchenko/app-new/actions for the dispatched resume.yml run."

## Summary

total: 2
passed: 0
issues: 1
pending: 0
skipped: 0
blocked: 1

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
