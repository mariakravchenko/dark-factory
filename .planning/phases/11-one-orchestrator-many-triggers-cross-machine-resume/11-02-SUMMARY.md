---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 02
subsystem: github
tags: [githubkit, workflow_dispatch, webhook, structlog, capture_logs, fail-soft, dispatch-credential]

# Dependency graph
requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plan 11-01's dispatch success path in webhook/app.py's _resolve_and_act, GitHubClient.for_dispatch/dispatch_workflow, Settings.dispatch_github_token, build_app's dispatch_client_factory seam"
provides:
  - "webhook/app.py's dispatch block grown from one path to four: dispatched, skipped (repository_not_configured), skipped (dispatch_github_token_not_configured), failed"
  - "_DISPATCH_SKIP_REASON_REPOSITORY_NOT_CONFIGURED / _DISPATCH_SKIP_REASON_CREDENTIAL_NOT_CONFIGURED / _DISPATCH_SKIP_REASON_RUN_STATE_UNAVAILABLE -- module-level reason constants"
  - "webhook.dispatch.failed / webhook.dispatch.skipped -- the two new structured-log event names plan 11-05's operator docs cite verbatim"
  - "MissingGitHubCredentialError added to dark_factory.github.client.__all__ (mypy --strict explicit-export requirement)"
  - "six db-tier tests in tests/db/test_webhook_dispatches_resume.py covering all four dispatch outcomes plus the never-over-dispatch proof"
affects: [11-03, 11-04, 11-05]

# Actuals (#2632)
actuals:
  tokens: 6141
  tasks: 2
  commits: 2
plan_head_before: affd1ec6dc072d0f9176d412a41eaf29e33305d6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-soft on GitHubError after an already-committed mutation, written locally in webhook/app.py (orchestrator/runner.py's clarification-comment precedent is not importable across the webhook package's direct-import allowlist)"
    - "Three ordered guards before the fail-soft try/except: run_state_unavailable (mypy narrowing only) -> repository_not_configured (info) -> dispatch_github_token_not_configured (warning, via try/except MissingGitHubCredentialError around client construction) -- each guarded and ordered so MissingGitHubCredentialError (itself a GitHubError subclass) can never be misreported as a dispatch API failure"
    - "structlog.testing.capture_logs() for asserting a specific log record was emitted in a db-tier test -- distinct from this codebase's real-sink helper (tests/support/log_sink.py), which is reserved for redaction-processor proofs"

key-files:
  created: []
  modified:
    - src/dark_factory/webhook/app.py
    - src/dark_factory/github/client.py
    - tests/db/test_webhook_dispatches_resume.py

key-decisions:
  - "All four dispatch outcomes (Task 1's GitHubError fail-soft arm and Task 2's two skip guards) were written in one contiguous edit to webhook/app.py's dispatch block, since they share one code path and splitting the guards across two separate edits to the same ~90-line block would have meant rewriting the same lines twice. Task 1's commit therefore carries all of Task 2's production code too; Task 2's own commit is test-only. Both tasks' individual `<verify>` blocks pass regardless of which commit the code landed in."
  - "MissingGitHubCredentialError added to dark_factory.github.client.__all__ (mirroring 11-01's identical GitHubError re-export decision) -- mypy --strict's explicit-export rule flagged the new `from dark_factory.github.client import MissingGitHubCredentialError` in app.py; the class was already importable (module namespaces aren't gated by __all__) but not explicitly re-exported."
  - "test_a_run_without_repository_config_records_the_answer_and_skips_the_dispatch could not literally follow the plan's build recipe (config_root_factory(roles=(\"BA\",)) with no _write_github_ba_tree overwrite): src/dark_factory/input/loaders.py::_load_github validates github_owner/github_repo against snapshot[\"repository\"] -- the SAME mapping the run's persisted runs.workflow column stores -- and raises UnresolvableSourceError before start_run ever creates a row. A repository config missing at intake time is missing before there is a run to test the dispatch guard against; the plan's own must_haves describe a property of the persisted snapshot the dispatch guard reads, independent of how a run came to have it. Resolution: build the run through the normal github:-sourced path (owner/repo present, exactly like waiting_run), drive it to WAITING_HUMAN, then directly strip github_owner/github_repo from the already-persisted runs.workflow JSONB column before posting the webhook delivery -- proving the guard itself rather than a scenario the intake layer already refuses to create. Documented inline in the test's own docstring."
  - "test_the_answer_is_recorded_even_when_the_dispatch_call_raises (11-01) had to be fixed, not left alone: its own docstring said the fail-soft branch was plan 11-02's task, and once Task 1 landed, GitHubError no longer propagates -- the test's `pytest.raises(GitHubApiError)` assertion became false. Updated to assert response.status_code == 200 with the same durable-state assertions; the test's name and purpose (\"the answer is recorded even when the dispatch call raises\") remain accurate."

requirements-completed: [HITL-06]

coverage:
  - id: D1
    description: "A GitHubError raised by the dispatch_workflow call itself is caught, logged as webhook.dispatch.failed with the run id and the already-redacted exception message, and the delivery still answers 200 with the answer durably recorded, the role-execution row unchanged, and the runs count unchanged"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_a_dispatch_api_failure_still_answers_200_and_keeps_the_committed_answer"
        status: pass
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_the_answer_is_recorded_even_when_the_dispatch_call_raises"
        status: pass
    human_judgment: false
  - id: D2
    description: "A run whose persisted workflow[\"repository\"] lacks github_owner/github_repo/base_branch records the answer, answers 200, makes no dispatch call, and logs webhook.dispatch.skipped with reason=repository_not_configured"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_a_run_without_repository_config_records_the_answer_and_skips_the_dispatch"
        status: pass
    human_judgment: false
  - id: D3
    description: "A receiver process with no dispatch_github_token configured records the answer, answers 200, makes no dispatch call, and logs webhook.dispatch.skipped with reason=dispatch_github_token_not_configured -- exercising the real GitHubClient.for_dispatch production path, not an injected fake"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_a_receiver_without_a_dispatch_token_records_the_answer_and_skips_the_dispatch"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-02 (never over-dispatch): a delivery that resolves to UnresolvableComment (Dark Factory's own comment, an ignored action shape) or fails signature verification makes no dispatch call at all, for three independent shapes"
    requirement: HITL-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_dispatches_resume.py#test_an_ignored_or_unsigned_delivery_never_dispatches"
        status: pass
    human_judgment: false
  - id: D5
    description: "No regression: the full suite across every tier stays green, and Phase 10's webhook behaviour (tests/db/test_webhook_resolves_answer.py) is unchanged"
    verification:
      - kind: integration
        ref: "uv run pytest -q (full suite, all tiers) -- 1176 passed, 1 failed, 2 skipped"
        status: pass
    human_judgment: false
    rationale: "The single failure (tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder) is the exact pre-existing, unrelated failure 11-01-SUMMARY.md already documented and confirmed via git stash -- a real claude CLI on PATH in this sandbox breaks that test's own credential-gated assumption, unrelated to any file this plan touches. Marked pass at the plan level per that precedent; the failing test itself is not part of this plan's coverage."

duration: ~25min task-commits + several hours db-tier/full-suite verification wait against real remote Postgres (interrupted once by a session rate-limit reset mid-wait; resumed cleanly with no lost work since both task commits had already landed)
completed: 2026-09-29
status: complete
---

# Phase 11 Plan 02: GitHub workflow_dispatch failure surface -- fail soft on every degraded path Summary

**The webhook receiver's dispatch call now degrades safely and visibly on all three ways it can fail to fire -- a GitHub API error, an unconfigured repository, an unconfigured dispatch credential -- proved by six new db-tier tests against real PostgreSQL, with zero regression across the full 1176-test suite.**

## Performance

- **Duration:** ~25 min of actual task-commit work; the remainder of wall-clock time was spent waiting on db-tier and full-suite verification against a real remote Neon PostgreSQL branch (one full-suite run alone took ~1h31m), interrupted once mid-wait by a session rate-limit reset with no lost work.
- **Completed:** 2026-09-29
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `webhook/app.py`'s dispatch block grown from plan 11-01's single success path to four outcomes: dispatched, skipped (`repository_not_configured`), skipped (`dispatch_github_token_not_configured`), and failed (`GitHubError` caught, logged, delivery still answers 200).
- Three ordered guards ahead of the `try`/`except GitHubError`/`else` fail-soft block: `state is None` (mypy narrowing only, untested in practice), the repository-config gap (`_log.info`), and the missing-credential gap (`_log.warning`, via `try`/`except MissingGitHubCredentialError` around `_dispatch_provider()` -- ordered *before* the `GitHubError` arm since `MissingGitHubCredentialError` is itself a `GitHubError` subclass).
- Two new structured-log event names, each a module-level constant, not an inline literal: `webhook.dispatch.failed` (the API call raised) and `webhook.dispatch.skipped` (no call attempted, carrying a `reason` field with one of three distinct values).
- `MissingGitHubCredentialError` added to `dark_factory.github.client.__all__`, mirroring 11-01's `GitHubError` re-export decision -- mypy `--strict`'s explicit-export rule required it.
- Six db-tier tests in `tests/db/test_webhook_dispatches_resume.py` (up from 11-01's two), all passing against a real Neon PostgreSQL 17 test branch: the API-failure fail-soft path (with a `structlog.testing.capture_logs()` proof the failure was actually logged, not silently swallowed), the unconfigured-repository skip, the unconfigured-credential skip (exercising the real `GitHubClient.for_dispatch` production path, not an injected fake), and a parametrized never-over-dispatch proof across three ignored/unsigned delivery shapes.
- Module docstring extended with a seventh numbered route step describing the dispatch block's four outcomes.

## Task Commits

1. **Task 1: A GitHub outage never costs the human their answer** - `e9bb05d` (feat) -- also carries Task 2's two skip guards and the module docstring update, since all four dispatch outcomes share one contiguous code block (see Decisions Made).
2. **Task 2: An unconfigured deployment degrades visibly, not mysteriously** - `7dd56f6` (test) -- three new test functions plus a fix to the one 11-01 test whose assertion the Task 1 behavior change invalidated.

## Files Created/Modified

- `src/dark_factory/webhook/app.py` -- the dispatch block's four outcomes (dispatched/skipped-repository/skipped-credential/failed), three new module-level reason constants, the seventh docstring route step.
- `src/dark_factory/github/client.py` -- `MissingGitHubCredentialError` added to `__all__`.
- `tests/db/test_webhook_dispatches_resume.py` -- fixed `test_the_answer_is_recorded_even_when_the_dispatch_call_raises` for the new fail-soft behavior; added `test_a_dispatch_api_failure_still_answers_200_and_keeps_the_committed_answer`, `test_a_run_without_repository_config_records_the_answer_and_skips_the_dispatch`, `test_a_receiver_without_a_dispatch_token_records_the_answer_and_skips_the_dispatch`, and the parametrized `test_an_ignored_or_unsigned_delivery_never_dispatches`; added `_role_executions_count`/`_runs_count` helpers mirroring `test_webhook_resolves_answer.py`.

## Decisions Made

See `key-decisions` in the frontmatter for the full rationale on each of the four items below:

- All four dispatch outcomes written in one contiguous edit (Task 1's commit carries Task 2's production code too; Task 2's commit is test-only).
- `MissingGitHubCredentialError` re-exported from `dark_factory.github.client.__all__`.
- The repository-config test builds a normal `github:`-sourced run and strips the persisted `runs.workflow` JSONB column's `repository` block after reaching `WAITING_HUMAN`, rather than literally following the plan's "no `_write_github_ba_tree` overwrite" recipe -- that recipe cannot produce a run at all, since intake validates the identical fields before `start_run` creates a row.
- The pre-existing `test_the_answer_is_recorded_even_when_the_dispatch_call_raises` test was fixed (not left failing, not deleted) to assert the new 200-response behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - plan-internal inconsistency, resolved by judgment] The repository-config test's literal build recipe cannot produce a run to test against**
- **Found during:** Task 2, writing `test_a_run_without_repository_config_records_the_answer_and_skips_the_dispatch`
- **Issue:** The plan's `<action>` text says to build via `config_root_factory(roles=("BA",))` with no `_write_github_ba_tree` overwrite, keeping the default `repository: {base_branch: main}` (no owner/repo), while still using the `github:`-sourced intake path. But `src/dark_factory/input/loaders.py::_load_github` validates `github_owner`/`github_repo` against `snapshot["repository"]` -- the SAME mapping the run's persisted `workflow` column stores -- and raises `UnresolvableSourceError` before `start_run` creates any row. A config missing owner/repo fails intake entirely; there is no run left to drive to `WAITING_HUMAN` and then post a webhook against.
- **Fix:** Built the run through the normal `github:`-sourced path (owner/repo present, matching `waiting_run`'s own construction), drove it to `WAITING_HUMAN`, then directly stripped `github_owner`/`github_repo` from the already-persisted `runs.workflow` JSONB column via a plain ORM read-mutate-commit before posting the webhook delivery. This proves the dispatch guard itself -- the actual subject of HITL-06's degraded-config truth -- rather than a scenario the intake layer already refuses to create. Documented at length in the test's own docstring for a later reader.
- **Files modified:** `tests/db/test_webhook_dispatches_resume.py`
- **Verification:** Test passes against real PostgreSQL 17 (Neon test branch); `webhook.dispatch.skipped`/`repository_not_configured` captured exactly once.
- **Committed in:** `7dd56f6` (Task 2 commit)

**2. [Rule 1 - Bug, expected by the plan's own prior-summary note] Fixed the one 11-01 test Task 1's behavior change breaks**
- **Found during:** Task 1, running the plan's own `<verify>` db-tier command before adding the new detailed test
- **Issue:** `test_the_answer_is_recorded_even_when_the_dispatch_call_raises` (written in plan 11-01, whose own docstring explicitly said "the fail-soft branch ... is plan 11-02's task") asserted `pytest.raises(GitHubApiError)` around the webhook POST. Once Task 1 wraps the dispatch call in `try`/`except GitHubError`, the exception no longer propagates, and the test failed with "DID NOT RAISE GitHubApiError" -- confirmed live against real PostgreSQL before the fix.
- **Fix:** Updated the test to assert `response.status_code == 200` with the same durable-state assertions (interaction `ANSWERED`, answer text, run status). The test's name and purpose remain accurate -- the answer genuinely is still recorded when the dispatch call raises, it just no longer propagates that raise to the caller.
- **Files modified:** `tests/db/test_webhook_dispatches_resume.py`
- **Verification:** Test passes; confirmed failing before the fix (captured the exact `DID NOT RAISE` failure) and passing after.
- **Committed in:** `e9bb05d` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 -- one a plan-internal inconsistency between the literal build recipe and the actual intake-validation code, resolved by judgment and documented in the test's own docstring; one a genuine regression this plan's own behavior change caused, exactly as 11-01-SUMMARY.md's "Next Phase Readiness" section anticipated).
**Impact on plan:** Both were necessary for correctness / for the test to prove what it claims to prove. No scope creep -- no new production behavior beyond what the plan specified.

## Issues Encountered

- **`structlog.testing.capture_logs()` worked exactly as the plan specified**, with no caveats. Verified directly (outside the test suite) that a module-level `_log = structlog.get_logger(__name__)` created well before the context manager is entered still routes through `capture_logs()`'s temporary processor chain correctly -- structlog's lazy-proxy logger resolves the active configuration per call, not at bind time. This project's own `tests/unit/test_log_redaction.py` bans `structlog.testing.capture_logs` for its *own* purpose (proving the real redaction processor chain runs), which is a different concern from this plan's need (proving a specific event was emitted with specific fields, where the payload is already-redacted text with no processor work left to prove).
- **The `orchestrator/runner.py` fail-soft precedent was mirrored without any adaptation needed.** The shape (`try`/`except GitHubError`/`else`, log via `_log.warning` not `_log.exception`, still reach the success return) transferred directly; the only difference is `runner.py` folds its redacted failure text into an existing event payload (`QUESTION_CREATED`) because it has no dedicated failure event, while this plan introduces `webhook.dispatch.failed` as its own named event since there is no pre-existing payload to append to.
- **Db-tier and full-suite verification against the real Neon test branch took substantially longer wall-clock time than the actual code changes** -- individual db-tier runs of the target test files ran 100-400s each, and the full unrestricted suite (`uv run pytest -q`) took ~1h31m. A session rate-limit reset occurred mid-wait on one full-suite run; no work was lost since both task commits had already landed before the wait began. The coordinator re-ran the full suite after the reset and reported the final result (see below), which this summary treats as authoritative.
- **Full-suite result (coordinator-run, authoritative for this plan):** `uv run pytest -q` -- 1176 passed, 1 failed, 2 skipped in 1h31m16s. The 1 failure, `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, is the exact pre-existing, unrelated failure `11-01-SUMMARY.md` already documented and confirmed via `git stash` in that plan (a real `claude` CLI on `PATH` in this sandbox returns a real `COMPLETED` result where the test expects a credential-gated `FAILED`). Not touched by this plan; carried forward as the same accepted baseline. A separate, narrower isolated run of `tests/db/test_webhook_dispatches_resume.py` + `tests/db/test_webhook_resolves_answer.py`, executed *concurrently* with that full-suite run against the same shared external Neon branch, showed one transient failure (`test_ignored_action_shapes_change_nothing`, a `runs_count` off-by-one) from cross-run write contention on the same live database rows -- not a code defect. The same test passed cleanly inside the full, non-concurrent suite run; no code change was made for it.

## User Setup Required

None for this plan directly -- no new credential or configuration surface beyond what plan 11-01 already introduced (`DISPATCH_GITHUB_TOKEN`, documented in `.env.example`).

## Next Phase Readiness

- Plan 11-03 (the two-subprocess cross-machine proof) and plan 11-04 (CI tier enablement) can proceed independently -- this plan touched only `webhook/app.py`, `github/client.py`, and `tests/db/test_webhook_dispatches_resume.py`, none of which intersect those plans' `files_modified` per the phase's wave-safety note.
- Plan 11-05 (deployer-facing documentation) can cite `webhook.dispatch.failed` / `webhook.dispatch.skipped` and the three reason values (`repository_not_configured`, `dispatch_github_token_not_configured`, `run_state_unavailable`) verbatim -- all four are now shipped, tested, module-level constants.
- No blockers. The one full-suite failure is the same pre-existing, unrelated, sandbox-specific issue carried since plan 11-01; no phase-11 action item follows from it.

## Self-Check: PASSED

Both claimed files (`src/dark_factory/webhook/app.py`, `src/dark_factory/github/client.py`) and the modified test file found on disk with the expected content; both claimed commits (`e9bb05d`, `7dd56f6`) found in git history via `git log --oneline --all`.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-09-29*
