---
status: partial
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-10-01T11:35:00Z
updated: 2026-10-01T12:20:00Z
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
  status: failed
  reason: "Real CI run (https://github.com/mariakravchenko/dark-factory/actions/runs/36850439597) failed with 12 tests raising pydantic_core.ValidationError (database_url/database_url_direct Field required) across tests/unit/test_clarification_comment.py, test_publish_idempotency.py, test_publish_step_unit.py, and test_webhook_signature.py — the identical error signature G-11-1 diagnosed, in modules 11-06's fix did not cover. This branch had never been pushed to CI before this run, so the gap was latent since whichever phase introduced each of these tests, invisible locally because every local run inherits this repo's git-ignored .env."
  severity: blocker
  test: 1
  artifacts: []
  missing: []
