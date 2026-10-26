---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 01
subsystem: github
tags: [githubkit, workflow_dispatch, webhook, starlette, secretstr, dispatch-credential]

# Dependency graph
requires:
  - phase: 10-github-integration-and-human-in-the-loop
    provides: "the webhook receiver (webhook/app.py), submit_answer, GitHubClient, the run's persisted workflow[\"repository\"] snapshot"
provides:
  - "GitHubClient.dispatch_workflow / GitHubClient.for_dispatch — a real workflow_dispatch call, credentialed separately from github_token"
  - "Settings.dispatch_github_token — the third, purpose-scoped SecretStr credential"
  - "build_app(..., dispatch_client_factory=...) injection seam"
  - "the success-path dispatch call wired into the webhook receiver's _resolve_and_act, after submit_answer commits"
affects: [11-02, 11-03, 11-05]

# Actuals (#2632)
actuals:
  tokens: 10539
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One SecretStr Settings field per credential purpose, extended a third time (dispatch_github_token, after github_token/github_webhook_secret/copilot_github_token)"
    - "GitHubClient.for_dispatch mirrors from_settings line-for-line, substituting the credential field"
    - "dispatch_workflow clones create_comment's try/except GitHubException/_raise_api_error shape; treats 204-No-Content 'did not raise' as success, never reads .parsed_data"
    - "build_app's dispatch_client_factory keyword extends the existing authenticated_login test-injection seam"

key-files:
  created:
    - tests/db/test_webhook_dispatches_resume.py
    - tests/unit/test_dispatch_token_never_reaches_a_worker.py
  modified:
    - src/dark_factory/config/settings.py
    - src/dark_factory/github/client.py
    - src/dark_factory/webhook/app.py
    - tests/support/fake_github.py
    - tests/unit/test_settings.py
    - tests/unit/test_webhook_signature.py
    - .env.example

key-decisions:
  - "GitHubError re-exported from dark_factory.github.client (added to that module's __all__) rather than importing it from the bare dark_factory.github package, keeping the webhook package's _WEBHOOK_DIRECT_ALLOWED import allowlist unwidened"
  - "The one-reader AST guard's expected set has TWO entries (dark_factory/github/client.py AND dark_factory/webhook/app.py), not the single entry the plan's Task 2 action text literally states — webhook/app.py legitimately reads .dispatch_github_token for its own startup diagnostic (instructed by Task 1), which the plan's own docstring guidance for this exact guard anticipates ('a future phase that legitimately adds a second reader updates the constant deliberately')"
  - "Only the dispatch success path is wired into _resolve_and_act this plan — no try/except around GitHubError, no unconfigured-token/-repository handling beyond the plain isinstance-narrowing skip. Fail-soft handling is explicitly plan 11-02's task per this plan's own <action> text"

requirements-completed: [HITL-06, TRIG-01]

coverage:
  - id: D1
    description: "A resolvable issue_comment reply causes exactly one workflow_dispatch call on the run's own target repository, carrying only the run id, after submit_answer has already committed"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_a_resolvable_reply_dispatches_the_resume_workflow"
        status: pass
    human_judgment: false
  - id: D2
    description: "The answer stays durably recorded even when the dispatch call itself raises (ordering: durable mutation first, side effect second)"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_the_answer_is_recorded_even_when_the_dispatch_call_raises"
        status: pass
    human_judgment: false
  - id: D3
    description: "Settings.dispatch_github_token is a distinct SecretStr credential, covered by known_secret_values() with zero special-case code, and never reaches a worker subprocess"
    requirement: TRIG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_settings.py#test_dispatch_github_token_defaults_to_none"
        status: pass
      - kind: unit
        ref: "tests/unit/test_dispatch_token_never_reaches_a_worker.py#test_worker_env_allowlist_has_no_dispatch_github_token_member"
        status: pass
    human_judgment: false
  - id: D4
    description: "The webhook package's module boundary (never references advance/drive, direct-import allowlist unwidened) survives the new dispatch code"
    requirement: TRIG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_process_boundary.py#test_webhook_packages_direct_imports_stay_inside_the_named_allowlist"
        status: pass
    human_judgment: false
  - id: D5
    description: "A real workflow_dispatch against a live GitHub repository with a real fine-grained PAT starts a real Actions run of resume.yml"
    verification: []
    human_judgment: true
    rationale: "must_haves.truths marks this verification tier 'backstop' — it requires a live GitHub repository, a real fine-grained PAT, and a deployed resume.yml (plan 11-05's deliverable). No automated proxy for a live third-party API side effect exists at this plan's scope."

duration: ~65min
completed: 2026-09-29
status: complete
---

# Phase 11 Plan 01: GitHub workflow_dispatch after a webhook answer Summary

**A resolvable GitHub issue_comment reply now triggers a real `workflow_dispatch` on the run's own target repository, credentialed by a new dispatch-only `Settings.dispatch_github_token`, proved end-to-end against real PostgreSQL.**

## Performance

- **Duration:** ~65 min
- **Completed:** 2026-09-29
- **Tasks:** 2
- **Files modified:** 9 (2 created, 7 modified)

## Accomplishments

- `GitHubClient.for_dispatch(settings)` / `GitHubClient.dispatch_workflow(owner, repo, *, workflow_id, ref, run_id)` — a new, real production GitHub Actions capability, credentialed separately from every existing GitHub credential on `Settings`.
- The webhook receiver's `_resolve_and_act` now dispatches `resume.yml` on the run's persisted `workflow["repository"]` snapshot immediately after `submit_answer` commits — carrying exactly one input, `run_id`, and nothing else (privacy prohibition, T-11-03).
- `Settings.dispatch_github_token`: a third, purpose-scoped `SecretStr` credential, covered by `known_secret_values()`'s existing generic walk with zero special-case code, and structurally proven absent from every worker-facing environment.
- Confirmed against the installed `githubkit` 0.16.1 package (not just docs): `gh.rest.actions.create_workflow_dispatch(owner, repo, workflow_id, *, ref=..., inputs=... via **kwargs)` — `workflow_id: Union[int, str]` genuinely accepts a workflow file name, and the endpoint answers `204 No Content` by default (confirmed via `inspect.signature` + the endpoint's own installed docstring). Matches 11-RESEARCH.md Pattern 1 exactly, no correction needed.
- Both `tests/db/test_webhook_dispatches_resume.py` tests pass against a real PostgreSQL 17 (a Neon test branch, reachable via `DARK_FACTORY_TEST_DATABASE_URL`): the happy-path whole-dict-equality dispatch assertion, and the ordering proof (durable mutation survives a raising dispatch call).

## Task Commits

1. **Task 1: End-to-end "an answer dispatches the resume" — one path only** - `56f5ebe` (feat)
2. **Task 2: The dispatch credential is documented, redacted, and structurally unable to reach a worker** - `a870ddd` (docs — test-and-doc-only content; see Deviations for the exact mislabel)

## Files Created/Modified

- `src/dark_factory/config/settings.py` — `dispatch_github_token: SecretStr | None = None` + docstring paragraph (D-03).
- `src/dark_factory/github/client.py` — `for_dispatch` classmethod, `dispatch_workflow` method, `GitHubError` added to `__all__` for the webhook package's re-export path, module docstring extended with the `create_workflow_dispatch` surface entry.
- `src/dark_factory/webhook/app.py` — `build_app(..., dispatch_client_factory=...)`, `_dispatch_provider()` closure, third (`warning`-level) startup check, and the dispatch call site in `_resolve_and_act` immediately before `return _OK`.
- `tests/support/fake_github.py` — `FakeGitHubClient.dispatch_workflow`, the fifth scripted method.
- `tests/db/test_webhook_dispatches_resume.py` (new) — the two required db-tier tests; a local `fake_settings` override (this module's own, not `tests/conftest.py`'s) adds `dispatch_github_token`.
- `tests/unit/test_settings.py` — three new tests mirroring `github_webhook_secret`'s block, plus the `_set_env` default-clear entry.
- `tests/unit/test_dispatch_token_never_reaches_a_worker.py` (new) — `WORKER_ENV_ALLOWLIST` membership + source-scan + exact-set AST reader guard.
- `tests/unit/test_webhook_signature.py` — fixed a regression this plan's own change caused (see Deviations), added one new WR-02-style startup-warning test.
- `.env.example` — `DISPATCH_GITHUB_TOKEN` entry with fine-grained-PAT guidance.

## Decisions Made

- **`GitHubError` re-export route:** added to `dark_factory.github.client.__all__` rather than importing `dark_factory.github` (the bare package) into `webhook/app.py` — keeps `_WEBHOOK_DIRECT_ALLOWED` unwidened, exactly as 11-RESEARCH.md's Anti-Patterns section flagged. No alternative import route was needed; the module already imported `GitHubClient` from `dark_factory.github.client` and `GitHubError` slotted into the same statement.
- **`dispatch_client_factory` seam shape:** a fourth `build_app` keyword-only parameter, mirroring `authenticated_login`'s "test-injection seam extends the production default" idiom exactly — a one-element-list-per-built-app cache (`_dispatch_cache`), lazily populated via `GitHubClient.for_dispatch(settings_factory())` on the production path, bypassed entirely when the keyword is supplied.
- **Fixture shape for the db test's injected fake:** rather than a shared `fake_dispatch_client`/`webhook_client` fixture pair (which would force both tests to mutate one shared `FakeGitHubClient`'s private `_raises` dict), the module uses a plain function, `_build_webhook_client(...)`, so each test constructs its own differently-scripted `FakeGitHubClient` — the happy-path fake and the raising fake never share state.
- **Task 1 wires only the dispatch success path**, per the plan's own explicit instruction — no `try`/`except GitHubError`, no handling of an unconfigured repository beyond the plain `isinstance`-narrowing skip that already exists in `orchestrator/publish.py`'s analogous code. The db-tier "raises" test therefore expects `_post(...)` itself to raise (via `pytest.raises(GitHubApiError)`), asserting only that the already-committed answer state survives — exactly matching the plan's stated intent that "the response-code half of the fail-soft contract is plan 11-02's."

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a regression in `tests/unit/test_webhook_signature.py` caused by adding the third startup check**
- **Found during:** Task 1, running the plan's own `<verification>`-listed full `unit or contract` sweep
- **Issue:** `build_app`'s new startup-check block reads `_startup_settings.dispatch_github_token`. That module's `_FakeSettings` test double predates this field and has no such attribute, so every test that calls `build_app()` with no injected `authenticated_login` (the four WR-02 startup-check tests) raised `AttributeError` instead of exercising the intended behavior. Separately, `test_a_resolvable_delivery_calls_submit_answer_exactly_once` uses a `_DummySession` double with only `.close()`; the new dispatch block's own `load_run_state(dispatch_session, ...)` call needs `.get()`, which that double doesn't implement.
- **Fix:** Added a `dispatch_github_token` parameter to `_FakeSettings.__init__` (default-configured, mirroring the existing `github_token` default-configured shape so no pre-existing test needed to change); added `monkeypatch.setattr(app_module, "load_run_state", lambda *a, **k: None)` as a default in `_make_client`, so this module's fixtures — which predate the dispatch read and don't implement a real `Session` — take the dispatch block's "repository not configured" skip branch rather than needing a real `Session.get()`.
- **Files modified:** `tests/unit/test_webhook_signature.py`
- **Verification:** All 19 tests in that file pass (18 pre-existing + 1 new); the plan's full `uv run pytest -m "unit or contract" -q` sweep is green apart from one confirmed-pre-existing, unrelated failure (see Issues Encountered).
- **Committed in:** `56f5ebe` (Task 1 commit — the regression was caused by Task 1's own change, so the fix rides the same commit)

**2. [Rule 2 - Missing coverage, minor] Added a startup-warning test for the new dispatch-token check**
- **Found during:** the same regression fix above
- **Issue:** The three pre-existing WR-02 tests cover `github_token`/`github_webhook_secret` missing/present at startup, but nothing proved the new `webhook.build_app.missing_dispatch_github_token` warning actually fires.
- **Fix:** Added `test_missing_dispatch_github_token_logs_a_warning_not_an_error`, mirroring the existing three tests' shape exactly.
- **Files modified:** `tests/unit/test_webhook_signature.py`
- **Verification:** Passes; confirmed the message is present with `dispatch_github_token=None` and absent otherwise.
- **Committed in:** `56f5ebe`

**3. [Rule 1 — plan-internal inconsistency, resolved by judgment] The one-reader AST guard's expected set has two entries, not the plan's literal one**
- **Found during:** Task 2, writing `tests/unit/test_dispatch_token_never_reaches_a_worker.py`
- **Issue:** The plan's Task 2 `<action>` text says: "Assert that the resulting set is exactly `{"dark_factory/github/client.py"}`." But Task 1's own `<action>` text (same plan) explicitly requires `build_app`'s startup-check block to read `_startup_settings.dispatch_github_token` — a second, genuine attribute-access reader. The literal one-entry assertion would therefore be false on landing and the guard would immediately fail against the plan's own Task 1 output.
- **Fix:** Encoded `_EXPECTED_READERS` as a two-entry frozenset (`dark_factory/github/client.py`, `dark_factory/webhook/app.py`), with a full docstring explanation of why the second entry is legitimate (the receiver's own startup diagnostic, not a worker-facing surface, not the credential-unwrapping frame D-03 actually cares about). This follows the plan's own guidance for this exact guard almost verbatim: "a future phase that legitimately adds a second reader updates the constant deliberately rather than deleting the test" — Task 1, in the same plan, is that future addition.
- **Files modified:** `tests/unit/test_dispatch_token_never_reaches_a_worker.py`
- **Verification:** `test_exactly_the_named_modules_read_dispatch_github_token` passes; a synthetic check confirms it would fail loudly if a third module started reading the field.
- **Committed in:** `a870ddd` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 — one a genuine regression, one a plan-internal inconsistency resolved by judgment and fully documented; 1 Rule 2 — minor coverage addition)
**Impact on plan:** All three were necessary for correctness (the regression) or for the guard to be non-vacuously true on landing (the reader-set fix). No scope creep — no new production behavior beyond what the plan specified.

## Issues Encountered

- **Pre-existing, unrelated test failure confirmed via `git stash`:** `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this execution sandbox both before and after every change in this plan — a real `claude` CLI is genuinely on `PATH` and returns a real `COMPLETED` result where the test expects a credential-gated `FAILED` (no `ANTHROPIC_API_KEY` configured). Confirmed unrelated to this plan by stashing all changes and re-running the same test in isolation: identical failure. Out of scope per the executor's scope-boundary rule; not touched.
- **Db-tier precondition initially unmet:** this sandbox had no reachable PostgreSQL 17 (no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) when Task 1's work began. Per the executor's precondition protocol, execution halted with a `checkpoint:human-verify` before any commit, once implementation and all non-db verification (mypy, ruff, unit-tier tests) were complete. The coordinator then set `DARK_FACTORY_TEST_DATABASE_URL` to a dedicated Neon test branch; re-verifying `uv run pytest -m db -q tests/db/test_pg_available.py` passed (1 passed), and execution resumed to completion with no further code changes needed.

## User Setup Required

None for this plan directly — `DISPATCH_GITHUB_TOKEN` is documented in `.env.example` and this plan's own `user_setup` frontmatter names the exact fine-grained-PAT scope a deployer needs. The `resume.yml` reference workflow content itself (the other half of a working end-to-end setup) is plan 11-05's deliverable, not yet written.

## Next Phase Readiness

- Plan 11-02 can now add the three degraded branches (unconfigured repository, unconfigured dispatch token, `GitHubError` from the call) directly into the success-path structure this plan left in place in `_resolve_and_act` — no restructuring needed, per this plan's own design intent.
- Plan 11-05 can write `resume.yml`'s reference content and the deployer-facing README section citing this plan's exact credential/permission requirements.
- No blockers. The db-tier precondition that stalled this plan mid-execution is now resolved for the remainder of Phase 11 (the Neon test branch connection remains set via `DARK_FACTORY_TEST_DATABASE_URL`), so plans 11-02/11-03/11-04 should not need to re-discover it.

## Self-Check: PASSED

All 9 claimed files found on disk; both claimed commits (`56f5ebe`, `a870ddd`) found in git history.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-09-29*
