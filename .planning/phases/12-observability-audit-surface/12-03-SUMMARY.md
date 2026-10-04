---
phase: 12-observability-audit-surface
plan: 03
subsystem: security
tags: [redaction, github, orchestrator, idempotency, pytest, sqlalchemy]

# Dependency graph
requires:
  - phase: 12-observability-audit-surface
    provides: "12-01's redact() / EventType catalog / apply_transition single-write-path, and the sibling persistence/mutations.py _write_human_interaction redaction precedent this plan mirrors for the GitHub comment path"
provides:
  - "src/dark_factory/orchestrator/runner.py's Signal.ROLE_NEEDS_INPUT branch now redacts the clarification-comment body (clarification_body -> redact(...) -> comment_body) before BOTH _find_own_clarification_comment and client.create_comment consume it"
  - "tests/integration/test_redaction_interactions.py::_RUNNER_PERMITTED_REDACT_ARGUMENTS widened to {str(exc), clarification_body}, with the question/answer-exclusivity assertion still enforced"
  - "tests/db/test_clarification_comment_is_redacted.py: db-tier proof against a recorded FakeGitHubClient.create_comment body (not redact() in isolation), covering exact-value and pattern-only credential shapes, idempotency across a crash/resume, and a run_events/role_executions regression anchor"
affects: [12-04-qa-verdict-events, 12-06-run-report]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 6370
  tasks: 2
  commits: 2

# Commit ledger (#3968) — measured, not narrated.
plan_head_before: ee557dd28967e652d95e32cde18dcc66f76ee623

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scrub-before-both-sinks: redact the assembled text once into a single binding (comment_body), then feed that same binding to both the idempotency existence-check and the external create_comment call — never redact only at the external call, or a resumed attempt compares raw text against an already-scrubbed posted comment and double-posts"
    - "Deliberate-widening allowlist discipline: tests/integration/test_redaction_interactions.py's _RUNNER_PERMITTED_REDACT_ARGUMENTS frozenset is widened by exactly one named entry per plan, with a comment bullet naming the plan/requirement/expression, while a separate assertion keeps enforcing that no redacted expression's text mentions 'question'/'answer' (exclusive to _write_human_interaction)"
    - "Proof-against-the-recorded-call, not against redact() in isolation: tests/db/test_clarification_comment_is_redacted.py drives real production code (drive()) and asserts over FakeGitHubClient.calls' recorded body, with a presence-then-absence pairing ([redacted: marker present AND planted literal absent) so the test cannot pass vacuously on an empty question list"

key-files:
  created:
    - tests/db/test_clarification_comment_is_redacted.py
  modified:
    - src/dark_factory/orchestrator/runner.py
    - tests/integration/test_redaction_interactions.py

key-decisions:
  - "Scrubbed the assembled clarification-comment text in one pass (clarification_body -> redact(...)) rather than per-question, per the plan's explicit instruction — redact is str-in/str-out and a list comprehension would risk a reader misreading it as per-element"
  - "No change to build_clarification_comment itself — its docstring's narrower promise (it only ever sees the question list) is preserved; redaction lives exactly once, at the call site that hands text to both the idempotency lookup and the external API"
  - "Task 2's test module plants two distinct credential shapes (an exact fake_settings-configured value and a pattern-only ghp_-prefixed literal with no matching setting) so the proof exercises both of redact()'s substitution modes, not just one"

requirements-completed: [OBS-01]

coverage:
  - id: D1
    description: "A GitHub-sourced run whose worker asks a credential-shaped question posts a clarification comment whose recorded body carries the redaction marker and neither planted literal"
    requirement: "OBS-01"
    verification:
      - kind: integration
        ref: "tests/db/test_clarification_comment_is_redacted.py::test_the_posted_comment_body_is_scrubbed_and_matches_the_persisted_question"
        status: pass
    human_judgment: false
  - id: D2
    description: "A crashed-then-resumed attempt adopts its own already-posted (scrubbed) comment instead of posting a duplicate, because the idempotency lookup and create_comment consume the same scrubbed binding"
    requirement: "OBS-01"
    verification:
      - kind: integration
        ref: "tests/db/test_clarification_comment_is_redacted.py::test_a_crashed_attempt_resumes_without_a_second_post_or_a_text_mismatch"
        status: pass
    human_judgment: false
  - id: D3
    description: "The redact-argument allowlist in tests/integration/test_redaction_interactions.py is widened to name the new clarification_body call site explicitly, while continuing to reject any expression mentioning a human-interaction question/answer field"
    requirement: "OBS-01"
    verification:
      - kind: integration
        ref: "tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site"
        status: pass
    human_judgment: false
  - id: D4
    description: "Neither planted credential literal reaches run_events.payload or role_executions.result/error for the run — the fix did not move the leak into a different column"
    requirement: "OBS-01"
    verification:
      - kind: integration
        ref: "tests/db/test_clarification_comment_is_redacted.py::test_the_planted_literals_never_reach_an_event_payload_or_role_execution_column"
        status: pass
    human_judgment: false

# Metrics
duration: resumed session (prior dispatch terminated by API rate limit; this session verified, fixed nothing, committed Task 2, and closed out)
completed: 2026-10-04
status: complete
---

# Phase 12 Plan 03: Clarification-Comment Redaction Summary

**Closed the one live `high`-severity credential-disclosure gap in the GitHub clarification-comment path: `runner.py`'s `ROLE_NEEDS_INPUT` branch now redacts the assembled comment body once, before both the idempotency lookup and `create_comment`, proven against a recorded `FakeGitHubClient` call rather than against `redact()` in isolation.**

## Performance

- **Started:** 2026-10-03T13:16:31Z (prior dispatch, Task 1 commit)
- **Completed:** 2026-10-04T05:07:57Z (this session: verification + Task 2 commit + close-out)
- **Tasks:** 2/2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `runner.py`'s `Signal.ROLE_NEEDS_INPUT` branch binds the raw assembled text to `clarification_body`, then redacts it once into `comment_body`, which both `_find_own_clarification_comment` and `client.create_comment` now consume — closing the gap where a GitHub issue comment (an external, non-revocable sink) could carry a credential that the sibling `human_interactions.question` DB write already scrubbed.
- `tests/integration/test_redaction_interactions.py`'s `_RUNNER_PERMITTED_REDACT_ARGUMENTS` widened by exactly one deliberately-named entry (`clarification_body`), with its question/answer-exclusivity guard still enforced and passing.
- `tests/db/test_clarification_comment_is_redacted.py` (new, 430 lines, 4 tests) proves the fix against a recorded `FakeGitHubClient.create_comment` body: exact-value and pattern-only credential shapes, a presence-then-absence assertion pairing (the `[redacted:` marker present, both planted literals absent), agreement between the posted body and the persisted `human_interactions.question`, a crash/resume idempotency proof that catches the "redacted only at `create_comment`, not before the lookup" wrong fix, and a regression anchor confirming neither literal reached `run_events.payload` or `role_executions.result`/`error`.

## Task Commits

Each task was committed atomically:

1. **Task 1: The clarification comment is scrubbed before it leaves the process** - `89a87f0` (fix) — committed in a prior dispatch session (2026-10-03), verified intact and unmodified in this session.
2. **Task 2: Prove it against a recorded GitHub call, not against `redact()` in isolation** - `f2bc32b` (test) — committed in this session.

**Plan metadata:** (this commit, below)

## Files Created/Modified

- `src/dark_factory/orchestrator/runner.py` - `Signal.ROLE_NEEDS_INPUT` branch: `clarification_body` bound from `build_clarification_comment(result.questions)`, then `comment_body = redact(clarification_body, known_secrets=get_settings().known_secret_values())`; both `_find_own_clarification_comment` and `client.create_comment` consume `comment_body`.
- `tests/integration/test_redaction_interactions.py` - `_RUNNER_PERMITTED_REDACT_ARGUMENTS` widened to `frozenset({"str(exc)", "clarification_body"})`, with a new comment bullet naming plan 12-03/OBS-01/the clarification-comment expression.
- `tests/db/test_clarification_comment_is_redacted.py` (new) - 4 db-tier tests proving the redaction against a recorded `FakeGitHubClient` call: the main scrub-and-agree proof, the crash/resume idempotency proof, the event/role-execution regression anchor, and a self-detection sanity test confirming `build_clarification_comment` itself would leak both planted literals absent the fix.

## Decisions Made

- Scrubbed the assembled clarification-comment text in one pass (`redact(clarification_body, ...)`) rather than per-question — `redact` is `str`-in/`str`-out, and scrubbing the joined text (including the `CLARIFICATION_COMMENT_PREFIX` header) in one call avoids a list-comprehension a future reader could misread as a per-element transform.
- Left `build_clarification_comment` completely unchanged — its docstring's narrower promise (it only ever receives the question list) is preserved; moving redaction inside it would have given the function two responsibilities.
- Task 2's test module plants two distinct credential shapes (an exact `fake_settings`-configured `whsec_...` value and a pattern-only `ghp_...` literal present in no setting) specifically so the proof exercises both of `redact()`'s modes — exact-value substitution and the compiled pattern table — rather than only one.
- No direct call to `redact()` anywhere in the new test module, by design: a unit test of `redact` proves `redact` works and proves nothing about whether the `ROLE_NEEDS_INPUT` call site actually calls it, which is precisely the gap 12-RESEARCH.md found and this plan closes.

## Deviations from Plan

None - plan executed exactly as written. (Task 1 was fully correct and complete as committed by the prior dispatch; Task 2's test file, written by the prior dispatch before it was interrupted, was verified correct and complete as-is and required no changes.)

One documentation-only discrepancy noted, not a deviation: the plan's `<read_first>`/`<verify>` sections for Task 2 reference `tests/db/test_clarification_comment.py` as existing scaffolding to follow, but no such file exists in this repository — the actual sibling scaffolding file (which the test module's own docstring correctly cites and follows) is `tests/db/test_ask_posts_comment.py`. This session's verification ran against the real file (`test_ask_posts_comment.py`) in place of the plan's stated path; both discovered a passing result, so no functional discrepancy arose.

## Issues Encountered

- **Prior-dispatch continuation:** this plan's execution was split across two dispatches. The first committed Task 1 (`89a87f0`) and wrote (but did not commit) Task 2's test file before being terminated mid-run by an API rate limit. This session verified both artifacts were correct as left (Task 1's code, Task 2's uncommitted test file), ran every verification command in the plan itself rather than trusting the prior dispatch's unfinished closing claim, found all of them passing, and committed Task 2 (`f2bc32b`).
- **Pre-existing, out-of-scope failures observed during full verification (not caused by this plan, not fixed, already recorded in `deferred-items.md` from phases 11/12-02):**
  - `uv run mypy src/dark_factory` — 2 pre-existing `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` (optional `mcp` extra not installed in this sandbox). Neither `runner.py` nor the new test file is implicated; both pass `mypy` cleanly when checked in isolation modulo the same pre-existing `FakeGitHubClient`-vs-`GitHubClient` typing pattern already present identically in `tests/db/test_ask_posts_comment.py` and `tests/db/test_publish_step.py` (the plan's own `mypy` verify command scopes to `src/dark_factory` only, so this is outside the formal gate).
  - `uv run ruff format --check .` — 19 pre-existing unformatted files, none of which this plan touches (confirmed: neither `runner.py` nor the new test file appears in the reformat list; both are already correctly formatted).
  - `uv run pytest -m "unit or contract"` — 1 pre-existing failure, `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, caused by a live `ANTHROPIC_API_KEY`/`claude` CLI being present in this sandbox (the test assumes no credential is configured). Unrelated to this plan's files; already documented in `deferred-items.md`.

All plan-scoped verification (the db-tier tests, the `test_redaction_interactions.py` integration suite, `test_secret_redaction_e2e.py`, `ruff check .`, `mypy`/`ruff format` on this plan's own touched files) passed cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- OBS-01's `high`-severity threat (T-12-08) is now mitigated and proven; the clarification-comment path and the `human_interactions.question` column are both scrubbed by the same `redact()` call pattern with the same known-secret set, and cannot disagree.
- `_RUNNER_PERMITTED_REDACT_ARGUMENTS`'s widening discipline is established and documented in-line for the next plan that needs to add a `redact()` call site in `runner.py`.
- No blockers for 12-04 or 12-06.

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-04*

## Self-Check: PASSED

- FOUND: src/dark_factory/orchestrator/runner.py
- FOUND: tests/db/test_clarification_comment_is_redacted.py
- FOUND: tests/integration/test_redaction_interactions.py
- FOUND: commit 89a87f0
- FOUND: commit f2bc32b
