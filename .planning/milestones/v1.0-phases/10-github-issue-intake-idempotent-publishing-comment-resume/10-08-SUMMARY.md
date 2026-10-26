---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 08
subsystem: testing
tags: [test-only, gap-closure, loop-04, sec-01, redaction, db-tier]

requires:
  - phase: 09-independent-quality-gate-bounded-feedback-loops
    provides: "_bounce_or_fail adjacency branch and _EXHAUSTION_REASON_TO_COUNTER lookup this plan's test reads"
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "the two GitHub-path redact() call sites (plans 10-06/GIT-03, 10-03/GIT-05) the narrowed guard now allowlists"
provides:
  - "a committed, permanently-collected tests/db/test_loop04_adjacency.py proving LOOP-04's adjacency case behaviorally"
  - "a narrowed, self-falsifying SEC-01 redaction structural guard over runner.py"
affects: []

actuals:
  tokens: 3800
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "AST-based first-positional-argument extraction over a named call, mirroring tests/unit/test_single_mutation_path.py's structural-guard idiom (ast.parse + ast.walk + ast.unparse, not a token/regex scan)"
    - "self-falsifying structural guard: a narrowed allowlist assertion is paired with an inline counterexample proving the extraction helper is not silently vacuous"

key-files:
  created:
    - tests/db/test_loop04_adjacency.py
  modified:
    - tests/integration/test_redaction_interactions.py

key-decisions:
  - "Both call sites' extracted redact() argument unparse to the identical text 'str(exc)', so _RUNNER_PERMITTED_REDACT_ARGUMENTS is a one-entry allowlist with a docstring naming both call sites (plans 10-06/GIT-03, 10-03/GIT-05) rather than two distinguishable entries"
  - "The module and test docstrings' stale claim that 'the runner never scrubs' was corrected alongside the assertion rewrite (not explicitly listed in the plan's action items but directly contradicted by the fix being made) -- documented as a deviation"

patterns-established: []

requirements-completed: [LOOP-04, SEC-01]

coverage:
  - id: D1
    description: "LOOP-04 adjacency: the pipeline's only role is also its terminal role, so a FAIL verdict has no earlier role to bounce to -- the run ends FAILED with the adjacency reason on the ROLE_FAILED event and role-execution error column, no exhaustion counter on RUN_FAILED, zero ROLE_BOUNCED events, and qa_developer_iterations untouched"
    requirement: "LOOP-04"
    verification:
      - kind: unit
        ref: "uv run pytest -q --collect-only tests/db/test_loop04_adjacency.py"
        status: pass
      - kind: lint
        ref: "uv run ruff check ."
        status: pass
      - kind: manual
        ref: "uv run pytest -m db -q tests/db/test_loop04_adjacency.py"
        status: blocked
    human_judgment: true
    rationale: "The db-tier run that behaviorally proves the assertions (not just that the module parses/imports correctly) needs a reachable PostgreSQL 17, absent in this execution sandbox. The assertion logic was independently verified by reading the exact runner.py code paths it exercises and is expected to pass; a human with database access must run it once to confirm. Logged in WINDOWS.md as unrun-verify id 15."
  - id: D2
    description: "SEC-01 redaction structural guard narrowed from a blanket 'redact( never appears in runner.py' ban to a named allowlist of the two GitHub-path expressions runner.py is permitted to scrub, plus a no-human-interaction-field assertion, plus a self-detection assertion proving the extraction is not vacuous"
    requirement: "SEC-01"
    verification:
      - kind: unit
        ref: "uv run pytest -q --collect-only 'tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site'"
        status: pass
      - kind: lint
        ref: "uv run ruff check ."
        status: pass
      - kind: static
        ref: "uv run mypy src/dark_factory"
        status: pass
      - kind: unit
        ref: "uv run pytest -m 'unit or contract' -q --tb=short (808 passed, 364 deselected)"
        status: pass
      - kind: static
        ref: "standalone interpreter run of _extract_redact_first_args/_mentions_human_interaction_field against real runner.py source: both call sites extract to 'str(exc)', correctly allowlisted and correctly not flagged as human-interaction fields; counterexample 'spec.question' correctly extracted, correctly rejected by both checks"
        status: pass
      - kind: manual
        ref: "uv run pytest -m integration -q 'tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site'"
        status: blocked
    human_judgment: true
    rationale: "The test module carries pytestmark = pytest.mark.integration, and the session-scoped autouse _schema_at_head fixture forces PostgreSQL provisioning for any collected item bearing that marker regardless of whether the individual test requests db fixtures -- so this DB-free assertion still cannot execute under pytest without a reachable PostgreSQL. The extraction/allowlist/marker logic was independently proven correct via a standalone interpreter run against the real runner.py source (see verification above); a human with database access must run the pytest node once to confirm the full collection/fixture path. Logged in WINDOWS.md as unrun-verify id 16."

duration: 55min
completed: 2026-09-28
status: complete
---

# Phase 10 Plan 08: LOOP-04 Adjacency Proof + SEC-01 Redaction Guard Gap-Closure Summary

**Promoted the untracked LOOP-04 adjacency throwaway to a committed, correctly-targeted db-tier test, and narrowed the SEC-01 redaction structural guard from a blanket ban to a named, self-falsifying allowlist of exactly what `runner.py` is permitted to scrub.**

## Performance
- **Duration:** 55min
- **Started:** 2026-09-28T08:07:42Z (STATE.md last-updated timestamp at hand-off from plan 10-07)
- **Completed:** 2026-09-28T09:00:11Z
- **Tasks:** 2 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `tests/db/test_loop04_adjacency.py` is now a committed, permanently-collected regression test. It reads the adjacency reason from the `ROLE_FAILED` event payload and the `role_executions.error` column (the two places production actually persists it), and asserts the `RUN_FAILED` payload carries exactly `{"role": "QA"}` -- no `reason`/`counter`/`value`/`cap` key, because the adjacency reason is not one of the two exhaustion reasons `_EXHAUSTION_REASON_TO_COUNTER` maps. The untracked, `git clean`-vulnerable throwaway (`tests/db/test_manual_check_loop04_adjacency.py`) is deleted; STATE.md's Blocker on this item is closed.
- `tests/integration/test_redaction_interactions.py`'s structural guard no longer asserts `runner.py` never calls `redact(` at all. It now asserts an AST-extracted first-positional-argument allowlist (`_RUNNER_PERMITTED_REDACT_ARGUMENTS`, one entry: `"str(exc)"`, covering both Phase 10 GitHub-path call sites), asserts no extracted argument mentions a human-interaction question or answer, and proves itself non-vacuous by running the same extraction helper over an inline counterexample that scrubs `spec.question` and confirming both checks reject it.

## Task Commits
1. **Task 1: Promote the LOOP-04 adjacency proof to a committed test that reads the right event** - `d52655c` (test)
2. **Task 2: Narrow the redaction structural guard to the contract it claims to protect** - `cd7a375` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `tests/db/test_loop04_adjacency.py` - Permanent LOOP-04 adjacency regression test; carries the throwaway's scenario forward, fixed to read the `ROLE_FAILED` event and `role_executions.error` column instead of `RUN_FAILED`, with the redundant `quality_gate`/`retry` YAML append removed (duplicate keys the shared factory already writes) and all `print()` calls removed.
- `tests/integration/test_redaction_interactions.py` - `_extract_redact_first_args` (AST helper), `_RUNNER_PERMITTED_REDACT_ARGUMENTS` allowlist, `_mentions_human_interaction_field` check, and a self-detection counterexample assertion added to `test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site`; module and test docstrings corrected to state the accurate contract.

## Decisions Made
- Both of `runner.py`'s `redact()` call sites unparse to the identical expression text `"str(exc)"` (each scrubs a stringified `GitHubError`, just bound to the same local variable name at each site), so the allowlist is one entry with a docstring naming both call sites and the plans that added them (10-06/GIT-03, 10-03/GIT-05), rather than trying to force two textually-distinguishable entries where none exist.
- The module docstring's and the test's own docstring's stale claim that "the runner never scrubs on the pause path" was corrected in the same edit, not left contradicting the new assertion -- documented below as a deviation since the plan's action item named only "the test docstring" (singular) but the module docstring carried the identical stale claim.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the module-level docstring's stale "runner never scrubs" claim, not just the test's own docstring**
- **Found during:** Task 2
- **Issue:** The plan's action item explicitly named updating "the test docstring," but `tests/integration/test_redaction_interactions.py`'s module-level docstring (lines 17-23) carried the identical now-false claim ("No new scrubbing call was added on the pause path in the runner; the last test in this module asserts exactly that"). Leaving it unfixed would have the module's own top-of-file documentation contradict the assertion the same edit just made accurate.
- **Fix:** Rewrote the module docstring's closing paragraph to state that the runner scrubs two GitHub API failure strings (plans 10-06/10-03) before they enter persisted payloads, never a human-interaction question or answer, matching the corrected test docstring.
- **Files modified:** `tests/integration/test_redaction_interactions.py`
- **Verification:** `uv run ruff check .` clean; no assertion logic changed, docstring-only.
- **Commit:** `cd7a375`

**Total deviations:** 1 auto-fixed (1 Rule 1). **Impact:** Documentation-only correction with no behavioral or assertion change; keeps the file internally consistent.

## Issues Encountered
No PostgreSQL 17 reachable in this execution sandbox (Docker absent, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) -- the same constraint plan 10-07 carried forward in STATE.md. This blocks two of this plan's `<verify>` steps:

- Task 1's db-tier human-check (`uv run pytest -m db -q tests/db/test_loop04_adjacency.py`). Per the plan's own verification-section instruction ("If step 5 cannot run for lack of a database, say so explicitly... rather than reporting the plan verified on steps 1-4"), this is documented here as an unmet precondition, not a failure. Steps 1-4 of the plan's overall `<verification>` list (collect, lint, unit+contract, mypy) all pass.
- Task 2's `<verify>` pytest invocation of the narrowed guard. The plan's `<done>` states this node "runs without a database (it requests no fixtures)," but the module carries `pytestmark = pytest.mark.integration`, and `tests/conftest.py`'s session-scoped autouse `_schema_at_head` fixture forces PostgreSQL provisioning for **any** collected item bearing the `db`/`integration` marker, regardless of whether the individual test function itself requests a db fixture. So this test cannot run under `pytest` in this sandbox either, independent of the fix in this plan.

Both are logged in `.planning/WINDOWS.md` as `unrun-verify` (ids 15 and 16). In both cases the underlying logic was independently verified: Task 1 by careful reading of the exact `runner.py` code paths it exercises (`_bounce_or_fail`, the `ROLE_FAILED` event/payload construction, the `_EXHAUSTION_REASON_TO_COUNTER` lookup-miss arm); Task 2 by a standalone interpreter run of `_extract_redact_first_args`/`_mentions_human_interaction_field` against the real `runner.py` source (both call sites extract to `"str(exc)"`, correctly allowlisted; the inline counterexample `spec.question` correctly extracted and correctly rejected by both checks).

## User Setup Required
None - no external service configuration required. A human with a reachable PostgreSQL 17 should run the two blocked verification commands above and report the result (see WINDOWS.md ids 15/16).

## Next Phase Readiness
- Both G-10-1 test-defect gaps this plan targeted are closed: the LOOP-04 adjacency evidence is now durable (committed, not `git clean`-vulnerable) and correctly targeted at the events production actually writes; the SEC-01 redaction guard states and can prove the real contract instead of an over-broad token ban.
- `src/dark_factory/orchestrator/runner.py` and `src/dark_factory/persistence/mutations.py` are unchanged by this plan, matching the plan's success criteria.
- No blockers for subsequent Phase 10 plans or phase close-out beyond the pre-existing, already-tracked no-PostgreSQL-in-sandbox constraint.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-28*

## Self-Check: PASSED

- FOUND: `tests/db/test_loop04_adjacency.py`
- CONFIRMED GONE: `tests/db/test_manual_check_loop04_adjacency.py`
- FOUND: `.planning/phases/10-github-issue-intake-idempotent-publishing-comment-resume/10-08-SUMMARY.md`
- FOUND commit: `d52655c`
- FOUND commit: `cd7a375`
