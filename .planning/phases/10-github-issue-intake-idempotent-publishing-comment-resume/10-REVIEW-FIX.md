---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
fixed_at: 2026-09-27T15:43:57Z
review_path: .planning/phases/10-github-issue-intake-idempotent-publishing-comment-resume/10-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-09-27T15:43:57Z
**Source review:** .planning/phases/10-github-issue-intake-idempotent-publishing-comment-resume/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (critical + warning): 5
- Fixed: 5
- Skipped: 0

All work was performed in an isolated git worktree (`workflow.use_worktrees`
was not explicitly `false`, so the default isolation path ran) and fast-forwarded
onto `gsd/phase-01-walking-skeleton-one-durable-run` on cleanup. Verification ran
inside that worktree: `uv sync --all-extras --dev`, then `mypy`, `ruff check`,
`ruff format --check`, and `pytest -m "unit or contract"` (671 passed, excluding
five pre-existing slow subprocess-based worker-CLI test files unrelated to any of
these fixes and already excluded from this project's own default `test_command`
by marker scoping considerations for those specific files). **No PostgreSQL
instance was reachable in this environment**, so every `tests/db/*` scenario
below was verified by careful reading, `ast.parse`, `mypy --strict`-equivalent
type-checking, and cross-referencing the exact idioms `tests/db/test_publish_idempotency.py`
already proves against real PostgreSQL — but not executed against a live
database. This is called out per-finding below.

## Fixed Issues

### CR-01: Clarification-comment posting has no crash-safety net (duplicate GitHub comment on resume)

**Files modified:** `src/dark_factory/orchestrator/runner.py`, `tests/support/fake_github.py`, `tests/unit/test_clarification_comment.py`, `tests/db/test_ask_posts_comment.py`, `tests/db/test_webhook_resolves_answer.py`
**Commit:** `f5fcacb`
**Status:** fixed: requires human verification (db-tier crash-window proof not executed against real PostgreSQL in this environment)

**Applied fix:** Added `_find_own_clarification_comment` to `orchestrator/runner.py`,
mirroring `orchestrator/publish.py::run_publish_step`'s `find_pull_request_for_branch`
existence-check pattern (the precedent explicitly named in the task's additional
context). Before the `Signal.ROLE_NEEDS_INPUT` branch ever calls `create_comment`,
it now calls `client.fetch_issue(...)` + `client.authenticated_login()` and scans
the issue's existing comments for one whose author matches Dark Factory's own
identity **and** whose body exactly matches this attempt's question text. If
found, it is adopted (`clarification_comment_id` is set from the existing
comment's id) and `create_comment` is never called; only when nothing matches
does the original `create_comment` call run. This closes the crash window
between a successful `create_comment` call and the `apply_transition` commit
that persists `clarification_comment_id`: a process killed in that window now
resumes by adopting the already-posted comment instead of duplicate-posting.

`tests/support/fake_github.py`'s `FakeGitHubClient` gained an `authenticated_login()`
double (configurable via a new `login` constructor kwarg, defaulting to
`"dark-factory-bot"`) so tests can script the identity match. Every existing
ask-path `FakeGitHubClient()` instantiation across `tests/unit/test_clarification_comment.py`,
`tests/db/test_ask_posts_comment.py`, and `tests/db/test_webhook_resolves_answer.py`
was updated to script an issue (via a new `_scripted_issue()`/reused existing
helper) since the existence check now always calls `fetch_issue` first.

New tests added:
- `tests/unit/test_clarification_comment.py::test_an_already_posted_own_comment_is_adopted_without_a_second_post` — proves adoption skips `create_comment` entirely.
- `tests/unit/test_clarification_comment.py::test_a_comment_from_someone_else_with_the_same_text_is_not_adopted` — proves the author-identity match, not text alone, gates adoption.
- `tests/db/test_ask_posts_comment.py::test_crash_between_comment_creation_and_its_commit_yields_one_comment` — mirrors `tests/db/test_publish_idempotency.py`'s exact in-process crash-window technique (an `apply_transition` wrapper that raises only on the call carrying `human_interaction` with `mode="ask"`), proving a crash between `create_comment` succeeding and the commit resumes to exactly one comment total across both attempts, against real PostgreSQL.

Existing tests updated (not new assertions, only fixture scripting) so the
pre-existing call-count/call-log assertions still hold with the new
`fetch_issue`/`authenticated_login` calls in the log: `test_github_sourced_run_posts_one_comment_and_threads_the_id`,
`test_raising_create_comment_still_pauses_with_no_id_recorded`,
`test_no_scenario_ever_calls_a_comment_update_method` (its call-set assertion
was widened from `{"create_comment"}` to `{"fetch_issue", "authenticated_login",
"create_comment"}` -- the "never update/edit" structural guarantee itself is
unchanged), `test_the_happy_path_posts_one_comment_and_records_its_id`,
`test_re_entry_without_answering_posts_nothing_more`,
`test_a_failed_post_still_pauses_and_the_question_survives`,
`test_the_comment_body_carries_no_internal_state`, and the `waiting_run` fixture
in `test_webhook_resolves_answer.py`.

**Verification:** 13 unit tests in `test_clarification_comment.py` pass (11
pre-existing + 2 new). `mypy`, `ruff check`, `ruff format --check` clean on
`runner.py`. `ast.parse` clean on all three modified/new-content db-tier and
support files. The new db-tier crash-window test
(`test_crash_between_comment_creation_and_its_commit_yields_one_comment`) was
written to the exact same shape as the proven `test_publish_idempotency.py`
db-tier crash test but **could not be executed** (no reachable PostgreSQL in
this sandbox) -- a human should run
`uv run pytest tests/db/test_ask_posts_comment.py tests/db/test_webhook_resolves_answer.py -q`
against a real PostgreSQL 17 instance before this phase is treated as fully
proven.

### CR-02: Unhandled exception from `resolve_issue_comment`/`_login_provider` breaks the documented "log + fixed 500" contract

**Files modified:** `src/dark_factory/webhook/app.py`, `tests/unit/test_webhook_signature.py`
**Commit:** `d62c28f`
**Status:** fixed

**Applied fix:** Widened the `try` block around `resolve_issue_comment(...)` in
`_resolve_and_act` to include an `except Exception: _log.exception(...); return _SERVER_ERROR`
arm (mirroring the existing `submit_answer` exception-handling shape verbatim),
keeping the `finally: session.close()` unchanged. This now catches any
exception from `resolve_issue_comment` itself, and from `_login_provider()`'s
eager `GitHubClient` construction (most plausibly `MissingGitHubCredentialError`
when `GITHUB_TOKEN` is unset), which previously propagated unhandled and
bypassed both the module's own documented contract and its logging.

**New test:** `test_an_unexpected_exception_from_resolve_returns_a_generic_server_error`
scripts `resolve_issue_comment` to raise (via a new `resolve_raises` parameter
on the file's `_make_client` helper) and proves a 500 is returned with the
exception text never echoed, and that `submit_answer` is never reached.

**Verification:** 14 unit tests in `test_webhook_signature.py` pass (13
pre-existing + 1 new). `mypy`, `ruff check`, `ruff format --check` clean.

### WR-01: Production safety assertions are silently disabled under `python -O`

**Files modified:** `src/dark_factory/orchestrator/publish.py`
**Commit:** `31ebd05`
**Status:** fixed

**Applied fix:** Replaced both `assert client is not None` and
`assert state.working_branch == working_branch, ...` in `run_publish_step`
with explicit `if ...: raise RuntimeError(...)` blocks carrying the identical
message text, so both safety nets survive regardless of `-O`/`PYTHONOPTIMIZE=1`.
Updated the function's own docstring (which previously said "so this asserts")
to describe the `RuntimeError` and cite WR-01.

**Verification:** 13 unit tests across `test_publish_idempotency.py` and
`test_publish_step_unit.py` pass unchanged (neither scripts an
`AssertionError`-specific expectation for either guard, confirmed by grep
before the change). `mypy`, `ruff check`, `ruff format --check` clean.

### WR-02: `GITHUB_TOKEN` is documented as required for the webhook process but never validated at startup

**Files modified:** `src/dark_factory/webhook/app.py`, `tests/unit/test_webhook_signature.py`
**Commit:** `abc9e5b`
**Status:** fixed

**Applied fix:** `build_app()` now checks, only on the production path
(`authenticated_login is None`), whether `settings_factory().github_token`
and `settings_factory().github_webhook_secret` are set, and logs a loud
`structlog` `ERROR` (`webhook.build_app.missing_github_token` /
`webhook.build_app.missing_github_webhook_secret`) for each that is missing.
Deliberately does not raise -- `GITHUB_TOKEN` legitimately stays unconfigured
in environments that never run this receiver (per plan 10-02's own disclosed
gap), so refusing to construct the app at all would be a larger behavior
change than this fix is scoped to make. The check is skipped entirely when
`authenticated_login` is injected (the unit-tier's own seam), so no existing
test needed to start configuring `GITHUB_TOKEN`.

**New tests:** `test_missing_github_token_logs_loudly_at_construction`,
`test_missing_github_webhook_secret_logs_loudly_at_construction`,
`test_fully_configured_settings_log_no_startup_warning`,
`test_injected_authenticated_login_skips_the_startup_check` -- using this
project's own `real_log_sink()` helper (`tests/support/log_sink.py`), per its
"never `structlog.testing.capture_logs`" convention (it bypasses the real
processor chain).

**Verification:** 18 unit tests in `test_webhook_signature.py` pass (14 after
the CR-02 commit + 4 new). `mypy`, `ruff check`, `ruff format --check` clean.

### WR-03: `load_run_state`'s "unique by role_execution_id alone" claim relies on undocumented Postgres NULL-ordering behavior

**Files modified:** `src/dark_factory/persistence/repositories.py`
**Commit:** `612147b`
**Status:** fixed: requires human verification (db-tier query behavior not exercised against real PostgreSQL in this environment)

**Applied fix:** Added `.nulls_first()` to the `ORDER BY HumanInteraction.answered_at.desc()`
clause, making the previously-implicit reliance on PostgreSQL's default
DESC-ordering NULL placement explicit and immune to a future "NULLS LAST looks
more natural" edit. Rewrote the surrounding comment to state plainly that this
query is **not** actually guaranteed unique by `role_execution_id` alone (the
partial unique index only constrains one `WAITING` row per `run_id`, not per
`role_execution_id`), and that the explicit `NULLS FIRST` is what makes the
currently-open question win over an earlier answered one when more than one
row exists for the same attempt.

**Verification:** This is semantically a no-op on real PostgreSQL --
`NULLS FIRST` is already Postgres's own default for `DESC` ordering, so the
query's actual return value is unchanged; the fix only makes that behavior
syntactically explicit. `mypy`, `ruff check`, `ruff format --check` clean;
`sqlalchemy`'s `.nulls_first()` was confirmed to compile to
`... DESC NULLS FIRST` via a standalone interpreter check. The existing
db-tier coverage for this exact query path
(`tests/db/test_load_run_state.py::test_pending_clarification_comment_id_reads_from_a_waiting_row_but_not_an_answered_one`)
was not re-run against a live database in this environment (none was
reachable) -- a human should confirm it still passes before this phase is
treated as fully proven.

---

_Fixed: 2026-09-27T15:43:57Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
