---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
reviewed: 2026-09-30T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .env.example
  - .github/workflows/ci.yml
  - README.md
  - src/dark_factory/config/settings.py
  - src/dark_factory/github/client.py
  - src/dark_factory/webhook/app.py
  - tests/db/test_cross_machine_resume.py
  - tests/db/test_webhook_dispatches_resume.py
  - tests/support/fake_github.py
  - tests/unit/test_ci_enforces_worker_name_guard.py
  - tests/unit/test_dispatch_token_never_reaches_a_worker.py
  - tests/unit/test_qual01_ci_coverage.py
  - tests/unit/test_resume_workflow_reference_doc.py
  - tests/unit/test_settings.py
  - tests/unit/test_trigger_carries_no_lifecycle_logic.py
  - tests/unit/test_webhook_signature.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-09-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This phase adds the post-answer `workflow_dispatch` call to the webhook receiver
(`GitHubClient.for_dispatch`, `GitHubClient.dispatch_workflow`, the four-guard
dispatch block in `webhook/app.py`), turns on the `db` marker tier in CI, and adds
a cross-machine resume proof plus a battery of structural/doc-drift guard tests.
The credential-boundary discipline is solid and independently verified: the new
`dispatch_github_token` never reaches `WORKER_ENV_ALLOWLIST`, has exactly the two
expected readers (`github/client.py`, `webhook/app.py`), and is unwrapped from
`SecretStr` at exactly one frame (`GitHubClient.for_dispatch`). Signature
verification remains library-based (`githubkit.webhooks.verify`), fail-closed on
an unset secret, and precedes any parsing or session open. `ruff`, `mypy`, and
all reviewed `unit` tests pass clean.

The one substantive gap is in the new dispatch block itself: unlike every other
branch of `_resolve_and_act` (steps 4-6 of the module's own docstring), the new
step 7 dispatch logic has no catch-all exception handler, so a DB error reading
`load_run_state` or an unexpected (non-`GitHubError`) exception from
`dispatch_workflow` propagates unhandled instead of being logged and degrading
to `_OK`, as the module's own stated fail-soft philosophy for this step requires.
No data-loss risk (the answer has already committed by this point), but it is an
observability and consistency gap against the module's documented contract.

## Warnings

### WR-01: Dispatch block (step 7) has no catch-all exception handler, unlike every other step in the same function

**File:** `src/dark_factory/webhook/app.py:293-394`

**Issue:** The module's own docstring (lines 40-45) promises: "Any unexpected
exception is logged with the exception and returns a fixed 500, never echoed."
That promise is implemented for the `resolve_issue_comment` call (lines 244-257,
`except Exception: _log.exception(...); return _SERVER_ERROR`) and for
`submit_answer` (lines 281-285, same shape). It is **not** implemented for the
new dispatch block added by this phase:

- `state = load_run_state(dispatch_session, outcome.run_id)` (line 295) — a
  plain DB read with no exception handling at all. A transient `OperationalError`
  (connection drop, Neon pooler hiccup) propagates straight out of
  `_resolve_and_act`, through `run_in_threadpool`, and is handled only by
  Starlette's default `ServerErrorMiddleware` — never by this module's own
  `_log.exception(...)` + `_SERVER_ERROR` pattern used everywhere else.
- `dispatch_client = _dispatch_provider()` (line 346) only catches
  `MissingGitHubCredentialError`. Any other exception raised while
  constructing the client (e.g. a bug in `GitHubClient.__init__`, or in a
  test's injected `dispatch_client_factory`) is unhandled.
- `dispatch_client.dispatch_workflow(...)` (line 374) only catches
  `GitHubError`. `GitHubClient.dispatch_workflow` only translates
  `githubkit.exception.GitHubException` into `GitHubApiError`; any other
  exception type (e.g. an `httpx` transport error that `githubkit` does not
  wrap, or a `TypeError` from malformed `owner`/`repo`/`ref` values) is
  unhandled here too.

Since `submit_answer` has already committed by this point (per the module's own
design intent for Guard 4's fail-soft reasoning), the correct behavior for an
unexpected failure in this block is the same fail-soft shape Guard 4 already
uses for `GitHubError` — log and return `_OK` — not `_SERVER_ERROR` (which
would incorrectly signal to GitHub that the delivery needs retrying, even
though the answer already committed and a retry would just re-take the
`NotWaitingForHuman` branch and skip the dispatch anyway) and not an unhandled
exception that skips this module's own logging entirely.

This is untested: none of the six scenarios in
`tests/db/test_webhook_dispatches_resume.py` exercises `load_run_state` raising,
`_dispatch_provider()` raising something other than
`MissingGitHubCredentialError`, or `dispatch_workflow` raising a non-`GitHubError`
exception.

**Fix:**
```python
# Phase 11, D-01/D-02: after submit_answer has already committed, the
# entire dispatch step is fail-soft -- any unexpected failure here must
# never surface as anything but a logged, non-retryable 200 (the answer
# is already durable; a 500/503 here would only mislead GitHub into
# retrying a delivery that already fully applied).
try:
    dispatch_session = session_factory()
    try:
        state = load_run_state(dispatch_session, outcome.run_id)
    finally:
        dispatch_session.close()

    if state is None:
        _log.info("webhook.dispatch.skipped", run_id=str(outcome.run_id),
                   reason=_DISPATCH_SKIP_REASON_RUN_STATE_UNAVAILABLE)
        return _OK

    repository = state.workflow.get("repository") or {}
    owner = repository.get("github_owner")
    repo = repository.get("github_repo")
    base_branch = repository.get("base_branch")
    if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo
            and isinstance(base_branch, str) and base_branch):
        _log.info("webhook.dispatch.skipped", run_id=str(outcome.run_id),
                   reason=_DISPATCH_SKIP_REASON_REPOSITORY_NOT_CONFIGURED)
        return _OK

    try:
        dispatch_client = _dispatch_provider()
    except MissingGitHubCredentialError:
        _log.warning("webhook.dispatch.skipped", run_id=str(outcome.run_id),
                      reason=_DISPATCH_SKIP_REASON_CREDENTIAL_NOT_CONFIGURED)
        return _OK

    try:
        dispatch_client.dispatch_workflow(
            owner, repo, workflow_id=_RESUME_WORKFLOW_FILENAME,
            ref=base_branch, run_id=str(outcome.run_id),
        )
    except GitHubError as exc:
        _log.warning("webhook.dispatch.failed", run_id=str(outcome.run_id),
                      workflow=_RESUME_WORKFLOW_FILENAME, detail=str(exc))
    else:
        _log.info("webhook.dispatch.requested", run_id=str(outcome.run_id),
                   workflow=_RESUME_WORKFLOW_FILENAME)
except Exception:
    _log.exception("webhook.dispatch.unexpected_error", run_id=str(outcome.run_id))
return _OK
```
Add a `tests/db/` or `tests/unit/` case that forces `load_run_state` (or the
`dispatch_client_factory`) to raise a plain `Exception`, and asserts the route
still returns `200` with a `webhook.dispatch.unexpected_error` log entry, so
this fail-soft guarantee is pinned the same way Guard 4 already is.

### WR-02: `LEASE_HEARTBEAT_SECONDS` accepts non-positive values as long as it is less than the TTL

**File:** `src/dark_factory/config/settings.py:141-163`

**Issue:** `_lease_intervals_are_coherent` validates `lease_ttl_seconds > 0` and
`lease_heartbeat_seconds < lease_ttl_seconds`, but never checks
`lease_heartbeat_seconds > 0`. With the default `lease_ttl_seconds=900`, a
config of `LEASE_HEARTBEAT_SECONDS=0` or a negative value (e.g. `-5`) passes
validation cleanly (`0 < 900` and `-5 < 900` are both true), producing a
heartbeat interval that is meaningless for whatever scheduling primitive
consumes it downstream (a `sleep(0)` busy-loop, or a `sleep(-5)` that raises
`ValueError` at runtime deep inside a heartbeat thread instead of failing
loudly at settings-load time, which is exactly the failure mode this
validator's own docstring says it exists to prevent: "reject a typo'd ...
loudly rather than let it produce a mysteriously ... FAILED role" — that
reasoning is stated for `worker_timeout_seconds` but the same principle applies
here and is not applied to this field).

This field is unchanged by this phase's diff (pre-existing since Phase 2), but
is exercised directly by this phase's new `tests/db/test_cross_machine_resume.py`
and `tests/support/subprocess_runner.py::child_env`, which both pass
`lease_heartbeat_seconds`/`LEASE_HEARTBEAT_SECONDS` through to real subprocess
config, making this gap directly reachable from phase-11 code paths.

**Fix:**
```python
@model_validator(mode="after")
def _lease_intervals_are_coherent(self) -> Settings:
    if self.lease_ttl_seconds <= 0:
        raise ValueError(...)
    if self.lease_heartbeat_seconds <= 0:
        raise ValueError(
            f"lease_heartbeat_seconds must be strictly positive, got "
            f"{self.lease_heartbeat_seconds!r}"
        )
    if self.lease_heartbeat_seconds >= self.lease_ttl_seconds:
        raise ValueError(...)
    return self
```

## Info

### IN-01: `_dispatch_cache`/`_client_cache` single-element-list caches are not thread-safe under concurrent first requests

**File:** `src/dark_factory/webhook/app.py:178-180, 218-223`

**Issue:** `_dispatch_provider()` (and the pre-existing `_login_provider()`)
implements a lazy "build once, cache on first call" pattern using a plain
Python list as a mutable cell. `_resolve_and_act` runs off the event loop via
`run_in_threadpool`, which under a real ASGI server backs onto a real thread
pool — so two concurrent first requests hitting an empty `_dispatch_cache`
can both pass the `if not _dispatch_cache:` check before either appends,
resulting in two `GitHubClient` instances being constructed (one silently
discarded) rather than exactly one. This mirrors a pre-existing pattern
(`_client_cache`) not introduced by this phase, and the outcome is benign
(no data corruption, no leaked secret — just a redundant object
construction), so it is not blocking, but worth a one-line
`threading.Lock()` guard if this code is ever expected to run under a
multi-threaded ASGI deployment with meaningful concurrent first-request load.

**Fix:** Wrap the check-then-append with a `threading.Lock()` (module- or
build_app-scoped), or switch to `functools.lru_cache`-backed factories.

### IN-02: Guard 1's `run_state_unavailable` skip reason has zero test coverage by design

**File:** `src/dark_factory/webhook/app.py:299-310`

**Issue:** The comment at lines 299-303 explicitly documents that this branch
"cannot happen here in practice" and is "not independently tested." That is a
reasonable call (the branch exists only for mypy's benefit), but it does mean
`_DISPATCH_SKIP_REASON_RUN_STATE_UNAVAILABLE` is dead code from a coverage
standpoint — if `load_run_state` ever legitimately started returning `None`
here (e.g. a future concurrent-delete feature), this path would silently
start firing with no test pinning its shape. Not a functional defect today;
flagged only so a future reviewer does not mistake the constant's presence
for tested behavior.

**Fix:** No action required now; consider a lightweight unit test that
monkeypatches `load_run_state` to return `None` directly (bypassing the
"can't happen" constraint) purely to pin the log shape, mirroring how
`tests/unit/test_webhook_signature.py` already monkeypatches `load_run_state`
to `None` for unrelated reasons.

---

_Reviewed: 2026-09-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
