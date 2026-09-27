---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
reviewed: 2026-09-27T00:00:00Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - migrations/versions/0006_github_publishing_columns.py
  - pyproject.toml
  - src/dark_factory/config/repo_config.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/github/__init__.py
  - src/dark_factory/github/client.py
  - src/dark_factory/input/loaders.py
  - src/dark_factory/orchestrator/answers.py
  - src/dark_factory/orchestrator/publish.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/webhook/__init__.py
  - src/dark_factory/webhook/app.py
  - src/dark_factory/webhook/resolve.py
  - tests/conftest.py
  - tests/db/test_ask_posts_comment.py
  - tests/db/test_github_publishing_columns_schema.py
  - tests/db/test_human_interactions_schema.py
  - tests/db/test_load_run_state.py
  - tests/db/test_publish_idempotency.py
  - tests/db/test_publish_step.py
  - tests/db/test_webhook_resolves_answer.py
  - tests/integration/test_unsupported_source.py
  - tests/support/fake_github.py
  - tests/support/webhook_events.py
  - tests/unit/test_clarification_comment.py
  - tests/unit/test_context_builder.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_github_client.py
  - tests/unit/test_github_ownership_boundary.py
  - tests/unit/test_load_github.py
  - tests/unit/test_loaders.py
  - tests/unit/test_mutations.py
  - tests/unit/test_persistence.py
  - tests/unit/test_publish_idempotency.py
  - tests/unit/test_publish_step_unit.py
  - tests/unit/test_repo_config_schema.py
  - tests/unit/test_settings.py
  - tests/unit/test_webhook_process_boundary.py
  - tests/unit/test_webhook_resolve.py
  - tests/unit/test_webhook_signature.py
  - uv.lock
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-09-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 45
**Status:** issues_found

## Summary

Phase 10 (GitHub issue intake, idempotent publishing, comment-driven resume) is
implemented with unusually careful attention to the exact hazard the project's own
research called out for the *publish* side effect: `orchestrator/publish.py`
correctly treats "GitHub already has a PR, Neon does not know yet" as a real
crash window and closes it with a `find_pull_request_for_branch` existence check
before ever calling `create_pull_request` — proven end to end by
`tests/db/test_publish_idempotency.py`'s in-process crash simulation.

That same discipline was not carried over to the *other* GitHub side effect this
phase introduces: posting the clarification comment. `create_comment` (the
`ROLE_NEEDS_INPUT` branch in `orchestrator/runner.py`) has no analogous
"does GitHub already have this comment" safety net, so a process crash between a
successful `create_comment()` call and the transaction that persists
`clarification_comment_id` will duplicate-post the question on resume. This
directly contradicts the project's own stated idempotency contract (CLAUDE.md:
"External side effects (branch, push, PR, **GitHub comment**) must be
retry-safe via persisted identifiers") and is confirmed by the absence of any
test exercising this specific crash window (contrast
`tests/db/test_ask_posts_comment.py::test_re_entry_without_answering_posts_nothing_more`,
which only covers the *post-commit* retry, not the *pre-commit* crash).

A second, independent gap sits in `webhook/app.py`: the route's own docstring
promises that "any unexpected exception is logged … and returns a fixed 500,
never echoed," but the `try/except` in `_resolve_and_act` only wraps the
`submit_answer` call — not `resolve_issue_comment` (nor the eager
`_login_provider()` call that constructs a `GitHubClient` on every request). An
exception there (most plausibly `MissingGitHubCredentialError` on a deployment
that forgot `GITHUB_TOKEN`, which the module's own docstring lists as required
but `Settings` never validates at startup) propagates unhandled, bypasses
`_log.exception(...)`, and turns every inbound `issue_comment` delivery into a
silent, unlogged 500 — the opposite of the "durability and observability are
the same requirement" posture this project holds itself to elsewhere. This gap
is also untested: `tests/unit/test_webhook_signature.py` proves the
`submit_answer`-raises path is caught, but nothing proves the
`resolve_issue_comment`-raises path is.

Everything else reviewed — the schema migration, the redaction discipline in
`mutations.py`, the self-comment filter in `resolve.py`, the signature
verification ordering in `webhook/app.py`, the `githubkit` ownership-boundary
guard, and the extensive db-tier idempotency proofs — is solid and matches its
own documentation. The two findings below are both genuine, narrow, and
independently fixable without touching the surrounding design.

## Critical Issues

### CR-01: Clarification-comment posting has no crash-safety net (duplicate GitHub comment on resume)

**File:** `src/dark_factory/orchestrator/runner.py:1603-1649`
**Issue:**

Inside the `Signal.ROLE_NEEDS_INPUT` arm of `_run_current_role`, the
persisted-identifier check (`state.pending_clarification_comment_id`) only
protects the *post-commit* retry case — i.e. a run that is already
`WAITING_HUMAN` with the comment id already recorded
(`tests/db/test_ask_posts_comment.py::test_re_entry_without_answering_posts_nothing_more`
proves exactly this).

It does **not** protect the crash window between a successful
`github_client_factory().create_comment(...)` call (an external, non-idempotent
side effect — every call creates a brand-new GitHub comment) and the single
`apply_transition(...)` call at the bottom of the function that persists
`clarification_comment_id`. If the process is killed in that window (OOM, host
failure, `SIGKILL`, etc.), nothing has been committed: on the next `advance()`,
`state.status` is unchanged, `latest.status` is still `RUNNING` (not
`RESUMING`), so `worker.execute(context)` runs again from scratch. If the
worker deterministically produces the same `NEEDS_INPUT` questions again (a
very plausible case for a real coding agent given the same inputs), the
`clarification_comment_id is None` check is true again and `create_comment` is
called a second time — a genuine duplicate comment posted to the user-facing
GitHub issue.

Contrast this with `orchestrator/publish.py::run_publish_step`, which was
explicitly designed against the structurally identical hazard for
`create_pull_request` (10-RESEARCH.md Pitfall 1): it calls
`find_pull_request_for_branch` as a safety net *before* creating a PR, so a
crash in the equivalent window self-heals on resume by adopting the
already-created PR instead of creating a second one. No equivalent lookup
exists for `create_comment` (`GitHubClient` exposes no
"find an already-posted comment for this question" method at all — see
`src/dark_factory/github/client.py`), so the ask path has strictly weaker
crash-safety than the publish path it sits right next to in the same phase.

This also violates the project's own explicit idempotency constraint
(`.claude/CLAUDE.md`: "External side effects (branch, push, PR, **GitHub
comment**) must be retry-safe via persisted identifiers.").

**Fix:**

At minimum, document this as a known, accepted gap (narrower crash window than
publish, since a worker attempt takes the lease and most crashes here are rare
relative to the publish step's own window). Preferably, close it the same way
publish does: before posting, list recent comments on the issue via
`GitHubClient.fetch_issue`/`list_comments` and skip posting if a comment whose
body already matches `build_clarification_comment(result.questions)` exists
from Dark Factory's own identity (`authenticated_login()`), e.g.:

```python
if issue_ref is not None and clarification_comment_id is None:
    owner, repo, issue_number = issue_ref
    client = github_client_factory()
    try:
        existing = _find_own_clarification_comment(
            client, owner, repo, issue_number,
            body=build_clarification_comment(result.questions),
        )
        comment = existing or client.create_comment(
            owner, repo, issue_number=issue_number,
            body=build_clarification_comment(result.questions),
        )
    except GitHubError as exc:
        ...
    else:
        clarification_comment_id = comment.id
```

Whichever direction is chosen, add a db-tier test mirroring
`tests/db/test_publish_idempotency.py`'s in-process `apply_transition`-raises
technique, targeted at the `human_interaction=` (not `publish_fields=`) write,
to prove the crash window is (or is explicitly accepted to be) covered.

### CR-02: Unhandled exception from `resolve_issue_comment`/`_login_provider` breaks the documented "log + fixed 500" contract

**File:** `src/dark_factory/webhook/app.py:132-179`
**Issue:**

The route's own module docstring states as the security control's step 6:
"Any unexpected exception is logged with the exception and returns a fixed
500, never echoed." The implementation only delivers on this promise for the
`submit_answer` call:

```python
session = session_factory()
try:
    outcome = resolve_issue_comment(
        event, session=session, authenticated_login=_login_provider()
    )
finally:
    session.close()

if not isinstance(outcome, ResolvedAnswer):
    ...
try:
    submit_answer(...)
except (NotWaitingForHuman, NoPendingInteraction) as exc:
    ...
except LeaseNotAcquired:
    ...
except Exception:
    _log.exception("webhook.issue_comment.unexpected_error", ...)
    return _SERVER_ERROR
return _OK
```

`_login_provider()` is evaluated eagerly, as an argument to
`resolve_issue_comment(...)`, *inside* the `try/finally` that only guarantees
`session.close()` — not inside any exception handler. On first call in a
freshly built app, `_login_provider()` constructs a real `GitHubClient` via
`GitHubClient.from_settings(settings_factory())`, which raises
`MissingGitHubCredentialError` (a `GitHubError`, not caught anywhere in this
module) whenever `GITHUB_TOKEN` is unset. The module's own docstring lists
`GITHUB_TOKEN` as required environment for this process, but `Settings`
declares `github_token: SecretStr | None = None` and nothing validates its
presence at `build_app()`/startup time — so a misconfigured deployment does not
fail fast; it instead 500s, silently and unlogged, on the very first inbound
`issue_comment` delivery, and keeps doing so on every redelivery GitHub
retries.

More generally, *any* exception raised from `resolve_issue_comment` itself
(a bug in the JSONB accessor query in
`persistence/repositories.py::github_pending_interaction`, for example) has
the same fate: it propagates out of `_resolve_and_act`, through
`run_in_threadpool`, and is caught only by Starlette's own default
`ServerErrorMiddleware` — which does return a generic 500 (so no payload is
echoed), but bypasses `_log.exception(...)` entirely. For an unauthenticated,
internet-facing endpoint whose only mutation path this project otherwise
audits exhaustively, an entire class of failures becoming invisible to
operators is a genuine regression against this project's core "durability and
observability are the same requirement" value.

This is confirmed untested: `tests/unit/test_webhook_signature.py::test_an_unexpected_exception_returns_a_generic_server_error`
only scripts `submit_answer` to raise; no test scripts `resolve_issue_comment`
(or `_login_provider`) to raise.

**Fix:**

Widen the try/except to cover the whole post-verification, post-parse
sequence, mirroring the existing `except Exception` arm's logging shape:

```python
session = session_factory()
try:
    outcome = resolve_issue_comment(
        event, session=session, authenticated_login=_login_provider()
    )
except Exception:
    _log.exception("webhook.issue_comment.unexpected_error")
    return _SERVER_ERROR
finally:
    session.close()
```

Additionally, consider validating `github_webhook_secret` *and* `github_token`
at `build_app()` construction time (fail fast at process startup, not on the
first request) rather than deferring the `MissingGitHubCredentialError` to a
per-request code path.

## Warnings

### WR-01: Production safety assertions are silently disabled under `python -O`

**File:** `src/dark_factory/orchestrator/publish.py:235-242`
**Issue:**

```python
assert client is not None  # caller's contract: non-None whenever create_pr
...
assert state.working_branch == working_branch, (
    f"run {run_id}: persisted working_branch {state.working_branch!r} does "
    f"not match the deterministic working_branch_name {working_branch!r} -- "
    "refusing to publish onto a mismatched branch"
)
```

These are framed in the docstring as a deliberate runtime safety net ("a
mismatch is a programming error, not a recoverable state, so this asserts
rather than silently re-publishing onto a different branch") rather than as
pure mypy type-narrowing. Python's `assert` statement is compiled to a no-op
when the interpreter runs with `-O`/`PYTHONOPTIMIZE=1` (or the corresponding
`sys.flags.optimize` set via environment). If this process is ever deployed
under `-O` (not unusual for some production packaging setups seeking a small
startup-time win), both checks silently disappear: a run whose
`working_branch` column has drifted from `working_branch_name(run_id)` would
proceed to publish onto whatever branch is on disk instead of refusing, with
no error and no audit trail — precisely the outcome the docstring says this
code exists to prevent.

**Fix:** Replace both with explicit `raise RuntimeError(...)` (or a small
dedicated internal-invariant exception) so the safety net survives regardless
of interpreter optimization flags:

```python
if client is None:
    raise RuntimeError("run_publish_step: client is None but create_pr is True")
if state.working_branch != working_branch:
    raise RuntimeError(
        f"run {run_id}: persisted working_branch {state.working_branch!r} does "
        f"not match the deterministic working_branch_name {working_branch!r} -- "
        "refusing to publish onto a mismatched branch"
    )
```

### WR-02: `GITHUB_TOKEN` is documented as required for the webhook process but never validated at startup

**File:** `src/dark_factory/webhook/app.py:10-18`, `src/dark_factory/config/settings.py:100`
**Issue:**

The module docstring for the webhook receiver states it "needs
`DATABASE_URL`, `DATABASE_URL_DIRECT` … `GITHUB_TOKEN` … and
`GITHUB_WEBHOOK_SECRET`" in the environment, but `Settings.github_token` is
`SecretStr | None = None` and nothing in `build_app()` (or `app = build_app()`
at import time) checks that it is actually set before the app starts serving
traffic. This means a missing `GITHUB_TOKEN` is only discovered per-request,
at the moment `_login_provider()` first tries to construct a `GitHubClient` —
and, per CR-02, that failure is not even logged. A process that should refuse
to start (or at least log a loud startup warning) instead starts cleanly and
fails silently on real traffic.

**Fix:** Validate `settings_factory().github_token is not None` (and
`github_webhook_secret is not None`, which is already checked per-request but
could also be validated eagerly) inside `build_app()` when `authenticated_login`
is not injected, raising or logging loudly before the app is returned.

### WR-03: `load_run_state`'s "unique by role_execution_id alone" claim relies on undocumented Postgres NULL-ordering behavior

**File:** `src/dark_factory/persistence/repositories.py:186-221`
**Issue:**

The comment above the `pending_answer` / `pending_clarification_comment_id`
query states: "one ask ('ask' mode) inserts exactly one row per attempt … so
no status filter is needed in the WHERE clause to find the row: it is unique
by role_execution_id alone." Nothing in `_write_human_interaction` (in
`persistence/mutations.py`) actually enforces this: a role attempt that is
resumed (`RESUMING`) and then returns `Signal.ROLE_NEEDS_INPUT` a *second*
time within the same attempt will insert a *second* `human_interactions` row
bound to the same `role_execution_id` (the partial unique index
`uq_one_waiting_interaction_per_run` only constrains one `WAITING` row per
`run_id`, not per `role_execution_id`). In that scenario the query is not
actually unique by `role_execution_id` — it returns the correct row (the
currently-open `WAITING` one, or the most-recently-`ANSWERED` one) only
because `ORDER BY answered_at DESC` relies on PostgreSQL's *default* NULL
ordering (`NULLS FIRST` for `DESC`), which is implicit and database-specific
behavior, not stated in the code or the comment. This happens to be correct
today, but it is fragile: a reader who "fixes" this to `ORDER BY answered_at
DESC NULLS LAST` (a very natural-looking edit) would silently break the
already-open-question case, and the docstring's "unique by role_execution_id
alone" framing actively misleads a future maintainer into thinking no
ordering subtlety exists at all.

**Fix:** Either make the reliance explicit (`ORDER BY answered_at DESC NULLS
FIRST`, plus a corrected comment describing why NULLS-FIRST is required — "the
currently open question, if any, must win over any earlier answered one"), or
restore the previously-implied one-row-per-attempt invariant with an explicit
guard/constraint if that invariant is actually intended to hold.

## Info

### IN-01: Duplicate magic-number secret-length threshold

**File:** `src/dark_factory/github/client.py:122-126`, `src/dark_factory/config/settings.py:176`
**Issue:** `GitHubClient.__init__`'s fallback (`{token: "github_token"} if len(token) >= 8 else {}`)
duplicates the literal `8`-character minimum `Settings.known_secret_values()`
already encodes as its own redaction-coverage floor. If that threshold is ever
tuned in one place, the other silently diverges.
**Fix:** Export the threshold as a shared named constant (e.g.
`dark_factory.events.redaction.MIN_REDACTABLE_SECRET_LENGTH`) and import it in
both places.

---

_Reviewed: 2026-09-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
