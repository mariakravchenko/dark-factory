---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
reviewed: 2026-09-28T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - src/dark_factory/orchestrator/publish.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/webhook/app.py
  - tests/db/test_ask_posts_comment.py
  - tests/db/test_loop04_adjacency.py
  - tests/db/test_webhook_resolves_answer.py
  - tests/integration/test_artifact_cross_clone.py
  - tests/integration/test_artifact_scope_enforcement.py
  - tests/integration/test_real_pipeline_zero_config.py
  - tests/integration/test_redaction_interactions.py
  - tests/integration/test_role_reassignment_sc2.py
  - tests/support/fake_github.py
  - tests/support/shipped_config.py
  - tests/unit/test_clarification_comment.py
  - tests/unit/test_shipped_config_harness.py
  - tests/unit/test_webhook_signature.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 10: Code Review Report (Incremental Re-Review)

**Reviewed:** 2026-09-28T00:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

This is an incremental re-review scoped to everything that changed in the
listed files **since** the prior 10-REVIEW.md (commit `400d8bd`): five
review-fix commits (`cb2f325`..`f5fcacb` range covers the whole phase, but
the actual diff against `400d8bd..HEAD` is five commits — WR-01, WR-02,
WR-03, CR-01, CR-02) plus the two gap-closure test plans (10-07, 10-08) that
closed gap G-10-1 (a test-harness defect: four integration-test modules
copied the shipped `.dark-factory.yaml` verbatim into a throwaway repo,
where `quality_gate.commands: uv run pytest -q` and
`publishing.create_pr: true` cannot succeed, causing the QA→Developer bounce
loop to exhaust and the run to terminate FAILED for reasons unrelated to the
property under test).

Note: the `diff_base` supplied in this task's config
(`d1603b9f7e50922fe6366668a3d7603815180567^`) predates the prior review
commit and would have re-surfaced the entire Phase 10 diff, including
already-reviewed code. I instead diffed against `400d8bd` (the commit the
prior 10-REVIEW.md was written against), per this task's own stated intent
("everything that changed SINCE that review commit"), and reviewed that
narrower, accurate diff at standard depth, while still reading each listed
file in full for context.

**Verified independently:** `ruff check` and `mypy` (both configured at
project-strict settings) pass clean on every changed source file; all 32
unit-tier tests in the affected modules (`test_webhook_signature.py`,
`test_clarification_comment.py`, `test_shipped_config_harness.py`) pass. No
Docker was available in this environment to execute the db/integration
tiers, so those were verified by static reading only.

**Assessment:** The five review-fix commits are each narrowly scoped,
correctly close the gap they name, and are covered by new or updated tests
that fail without the fix (verified by reading the crash-window and
existence-check tests in `test_ask_posts_comment.py` and
`test_clarification_comment.py`). The `NULLS FIRST` change in
`repositories.py` is a no-op in PostgreSQL (DESC already defaults to NULLS
FIRST) and is documentation-only, not a behavior change — correctly
described as such in its own comment. No BLOCKER-severity defects were
found in this diff. Two WARNING-level design concerns and one INFO-level
test-robustness note are recorded below.

## Warnings

### WR-01: `build_app()` now performs eager, unconditional settings I/O at construction time, not just at first request

**File:** `src/dark_factory/webhook/app.py:135-153`
**Issue:** The WR-02 (10-REVIEW.md) fix added an unconditional
`_startup_settings = settings_factory()` call inside `build_app()` whenever
`authenticated_login is None` — i.e. on every production construction,
including the module-level singleton `app = build_app()` evaluated at
**import time** (line 245). Before this change, `settings_factory()` was
only ever invoked lazily, inside `_login_provider()`, the first time a real
request actually needed a `GitHubClient`, and inside `_handle_issue_comment`
per-request for the webhook secret. Now, merely `import
dark_factory.webhook.app` unconditionally constructs a real `Settings()` via
the default `get_settings`, which requires `DATABASE_URL` and
`DATABASE_URL_DIRECT` (both required, no defaults) to resolve without
raising a `pydantic.ValidationError`.

Concretely this means:
- Any tool, script, or future test that imports this module for a reason
  unrelated to the webhook receiver (e.g. static analysis, doc generation,
  a future CLI subcommand listing routes) now transitively requires a fully
  valid `Settings` — a new, undocumented import-time dependency the
  module's own docstring does not mention (it only documents this as
  "logs a loud ERROR... does not raise" for `GITHUB_TOKEN` /
  `GITHUB_WEBHOOK_SECRET`, not that `build_app()` construction itself now
  requires `DATABASE_URL`/`DATABASE_URL_DIRECT` to resolve at all).
- `tests/unit/test_webhook_signature.py` (nominally a unit test, no DB
  needed) now indirectly depends on this repository's `.env` (or the
  process environment) providing a fully valid `Settings` at collection
  time, purely because of the unrelated module-level `app = build_app()`
  statement at the bottom of `app.py` — this happened to pass in this
  environment only because a working `.env` is checked out locally, but the
  coupling itself is new and not exercised as a test (no test asserts that
  `import dark_factory.webhook.app` succeeds with a *minimal* environment).

This is a behavior/robustness regression relative to the pre-fix version,
introduced as a side effect of WR-02, not something WR-02 set out to change
(WR-02's stated goal was "log a loud ERROR... at `build_app()` startup," not
"require full `Settings` to construct at all successfully"). The failure
mode moved from "first webhook request in an environment nobody configured
DATABASE_URL for" to "the process cannot even import this module," which is
a materially different, wider blast radius than the fix's own scope
describes.

**Fix:** Gate the eager settings read behind a narrower try/except so a
`Settings`-construction failure degrades to the same loud-log-no-raise
posture WR-02 already promises for the two specific fields, rather than
letting an unrelated required-field validation error propagate out of
`build_app()`:
```python
if authenticated_login is None:
    try:
        _startup_settings = settings_factory()
    except Exception:
        _log.exception("webhook.build_app.settings_construction_failed")
    else:
        if _startup_settings.github_token is None:
            _log.error("webhook.build_app.missing_github_token", ...)
        if _startup_settings.github_webhook_secret is None:
            _log.error("webhook.build_app.missing_github_webhook_secret", ...)
```
Alternatively, document explicitly in the module/function docstring that
`build_app()` (and therefore importing this module) now requires a fully
resolvable `Settings` and is no longer import-safe without
`DATABASE_URL`/`DATABASE_URL_DIRECT` configured.

### WR-02: `_find_own_clarification_comment` / the publish existence check add an unconditional extra GitHub read whose failure mode is coupled to exact-string matching with no normalization

**File:** `src/dark_factory/orchestrator/runner.py:235-265`, `src/dark_factory/orchestrator/publish.py:184-193`
**Issue:** Not a logic bug in this diff (the matching semantics are
correctly implemented and tested — author identity + exact body equality),
but worth flagging as the idempotency mechanism now has a documented single
point of fragility: `comment.author == own_login` is a literal string
comparison against whatever `GitHubClient.authenticated_login()` returns
(outside this diff's scope). If the real GitHub API ever returns a
bot-account login with a different casing or a `[bot]` suffix than what a
freshly re-fetched issue's comment `author` field reports (a known GitHub
API quirk for GitHub App / bot identities), the existence check would
silently fail to adopt a genuinely-already-posted comment, causing a
duplicate post rather than a crash — the one failure mode all this
machinery exists to prevent, and one that would only surface after a real
crash-and-resume in production since none of the fakes here can exercise
that asymmetry. This is a latent risk carried by design (documented as
"never spoofable"), not a defect introduced by this diff, but it is not
covered by any test in the reviewed scope and is worth a tracked follow-up
(e.g. a case-insensitive or `[bot]`-suffix-tolerant comparison, verified
against a real GitHub App identity) rather than left implicit.

**Fix:** Add a unit test asserting the exact string
`client.authenticated_login()` is expected to return for the production
GitHub App/PAT identity this project uses matches the `author` field
`GitHubClient.fetch_issue`'s real (non-fake) comment parsing produces, or
normalize both sides (e.g. `.lower()`) before comparing if GitHub's API is
known to vary casing between the two endpoints.

## Info

### IN-01: The `redact(` AST guard only recognizes bare-name calls, not attribute or aliased-import calls

**File:** `tests/integration/test_redaction_interactions.py:299-401`
**Issue:** `_extract_redact_first_args` filters on
`isinstance(node.func, ast.Name) and node.func.id == "redact"`, so it will
silently stop detecting a `redact()` call site if `runner.py` is ever
refactored to `from dark_factory.events import redaction as _redaction`
followed by `_redaction.redact(...)`, or `import ... as _redact` followed by
`_redact(...)`. The test's own docstring frames this guard as the mechanism
that prevents a human-interaction question/answer from ever being
`redact()`-ed inside `runner.py` (which would be a structural violation of
the "redaction lives only in `_write_human_interaction`" rule) — a guard
that can be silently bypassed by an unrelated import-style refactor is
weaker than its own stated purpose. The test's self-detecting counterexample
(lines ~380-401) proves the *matching* logic works, but does not prove the
*call-shape coverage* is complete, since the counterexample also uses a bare
`redact(...)` call.
**Fix:** Either also match `ast.Attribute` nodes whose `.attr == "redact"`,
or add a second counterexample using the attribute-call shape
(`some_module.redact(spec.question, ...)`) and assert it is *also* detected
— consistent with the existing test's own "prove the guard would catch a
real violation" philosophy.

---

_Reviewed: 2026-09-28T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
