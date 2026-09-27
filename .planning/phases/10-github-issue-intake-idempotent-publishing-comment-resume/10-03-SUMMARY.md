---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 03
subsystem: orchestrator
tags: [github, human-in-the-loop, clarification, postgresql, redaction]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "GitHubClient.create_comment + FakeGitHubClient (plan 10-01); the github_client_factory seam threaded through advance/drive/_advance_once/_run_current_role, HumanInteractionWrite.clarification_comment_id, and RunState.pending_clarification_comment_id (plan 10-06)"
provides:
  - "orchestrator/runner.py: CLARIFICATION_COMMENT_PREFIX + build_clarification_comment(questions) -- a pure function taking only the question list, so no run id / role-execution id / worker name / worktree path / branch name is ever in scope to leak"
  - "_run_current_role's Signal.ROLE_NEEDS_INPUT branch: a GitHub-sourced run posts the question as a fresh comment via github_client_factory().create_comment(...) and threads the returned id into the same HumanInteractionWrite the branch already builds, so the question and its comment id commit together in one apply_transition call"
  - "_github_issue_ref(state): structural GitHub-sourcedness check (source_kind + owner/repo/issue_number metadata), mirroring publish.py's _pr_body defensive style"
  - "D-05 idempotency: state.pending_clarification_comment_id already set skips the post entirely -- zero GitHub calls"
  - "Fail-soft posture: a GitHubError from create_comment is caught, never propagated -- clarification_comment_id stays NULL, the redacted failure text rides the existing QUESTION_CREATED payload, and the run still reaches WAITING_HUMAN with its question intact"
affects: [10-04]

actuals:
  tokens: 9959
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "build_clarification_comment takes exactly one parameter (the question list) as the enforcement mechanism for the no-internal-state prohibition -- a parameter a function does not receive is a value it structurally cannot leak, so the privacy guarantee is checkable by inspecting the signature rather than auditing every call site."
    - "A GitHub-sourced ROLE_NEEDS_INPUT reuses the existing QUESTION_CREATED event for a failed comment post rather than declaring a new EventType member -- events/catalog.py's own rule is that a member is declared by the phase that genuinely writes it, and this phase already claimed its three (PUBLISH_STARTED/PR_CREATED/PUBLISH_FAILED) in plan 10-06."

key-files:
  created:
    - tests/unit/test_clarification_comment.py
    - tests/db/test_ask_posts_comment.py
  modified:
    - src/dark_factory/orchestrator/runner.py
    - tests/db/test_human_interactions_schema.py

key-decisions:
  - "CLARIFICATION_COMMENT_PREFIX = '**Dark Factory needs your input to continue this task.**' -- a fixed, human-legible marker naming Dark Factory as the asker (D-08, T-10-14), kept as a module constant rather than an f-string built at the call site so plan 10-04's self-comment filter can reference it if needed."
  - "The pending interaction's clarification_comment_id is made visible to the ROLE_NEEDS_INPUT branch via RunState.pending_clarification_comment_id -- the field plan 10-06 already added and populated (gated on the interaction still being WAITING); no new RunState field or repositories.py change was needed or made."
  - "A failed comment post is recorded by adding a clarification_comment_error key to the existing QUESTION_CREATED event's payload, not a new EventType member -- reuses the phase's already-claimed event vocabulary and keeps the pause/QUESTION_CREATED/RUN_PAUSED shape byte-identical to the success path."
  - "GitHub-sourcedness is decided structurally via a new _github_issue_ref(state) helper (source_kind == SourceKind.GITHUB AND owner/repo/issue_number all present in task metadata) rather than a bare string comparison inline, mirroring publish.py's _pr_body precedent and keeping the two call sites unable to drift independently."

patterns-established:
  - "The 'is this run GitHub-sourced with a usable identity?' check now has two independent call sites (publish.py's _pr_body, runner.py's _github_issue_ref) that read the identical owner/repo/issue_number metadata triple defensively -- a future third call site should extract a shared helper rather than a third independent re-derivation."

requirements-completed: [GIT-05]

coverage:
  - id: D1
    description: "A GitHub-sourced run reaching ROLE_NEEDS_INPUT posts the question as a fresh comment on the source issue and the run still reaches RunStatus.WAITING_HUMAN"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_github_sourced_run_posts_one_comment_and_threads_the_id"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_the_happy_path_posts_one_comment_and_records_its_id (real PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The comment body is CLARIFICATION_COMMENT_PREFIX plus the newline-join of the questions, with no other interpolated value and no escaping/normalization/truncation of the question text (Markdown, emoji, CJK all pass through verbatim)"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_body_starts_with_the_fixed_prefix_and_ends_with_the_newline_join, ::test_body_preserves_emoji_cjk_and_markdown_verbatim, ::test_body_takes_only_the_question_list, ::test_body_never_contains_run_role_worker_worktree_or_branch_values"
        status: pass
    human_judgment: false
  - id: D3
    description: "The posted comment's GitHub id is persisted as human_interactions.clarification_comment_id in the same apply_transition call that inserts the WAITING row"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_github_sourced_run_posts_one_comment_and_threads_the_id"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_the_happy_path_posts_one_comment_and_records_its_id"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-05 idempotency: a re-entered attempt whose pending interaction already carries a clarification_comment_id issues zero GitHub calls; a re-driven WAITING_HUMAN run posts no second comment"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_pending_comment_id_already_set_skips_the_post"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_re_entry_without_answering_posts_nothing_more"
        status: pass
    human_judgment: false
  - id: D5
    description: "Each ROLE_NEEDS_INPUT posts a fresh comment and never edits a prior one -- no comment-update/edit call is ever issued"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_no_scenario_ever_calls_a_comment_update_method"
        status: pass
    human_judgment: false
  - id: D6
    description: "A non-GitHub run (text:/spec:) reaching ROLE_NEEDS_INPUT behaves exactly as before -- no GitHub client constructed, no comment attempted, existing pause path unchanged"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_text_sourced_run_never_calls_the_client_factory"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_a_non_github_run_is_untouched"
        status: pass
    human_judgment: false
  - id: D7
    description: "A failed comment post does not silently swallow the question -- the run still pauses at WAITING_HUMAN with its human_interactions row intact, clarification_comment_id left NULL, and a later submit_answer still resumes it"
    requirement: GIT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_raising_create_comment_still_pauses_with_no_id_recorded"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_a_failed_post_still_pauses_and_the_question_survives"
        status: pass
    human_judgment: false
  - id: D8
    description: "No Dark Factory internal state (run id, role-execution id, worker name, worktree/artifact path, branch name, persisted identifier, credential) ever reaches the public comment body -- T-10-12 made mechanical"
    verification:
      - kind: unit
        ref: "tests/unit/test_clarification_comment.py::test_body_never_contains_run_role_worker_worktree_or_branch_values"
        status: pass
      - kind: integration
        ref: "tests/db/test_ask_posts_comment.py::test_the_comment_body_carries_no_internal_state"
        status: pass
    human_judgment: false
  - id: D9
    description: "Regression: the pre-existing pause path, the structural guards, and the human_interactions schema proof all stay green after this plan's change"
    verification:
      - kind: integration
        ref: "tests/db/test_pause_path_atomic.py, tests/db/test_pause_mechanism_generic.py, tests/db/test_human_interactions_schema.py, tests/db/test_state_event_pairing.py, tests/integration/test_pause_exit_zero.py, tests/integration/test_resume_with_answer.py -- all passing against real PostgreSQL 18.6 (Neon)"
        status: pass
      - kind: unit
        ref: "Full unit+contract suite (742 tests) plus the five structural guards (test_no_role_name_literal.py, test_single_mutation_path.py, test_orchestrator_no_live_config_read.py, test_no_environ_copy.py, test_no_worker_name_leak.py)"
        status: pass
    human_judgment: false

duration: ~2h across two dispatches (Task 1 implementation to a Task 2 precondition-blocked checkpoint, then continuation with a supplied throwaway Neon connection string through Task 2's completion)
completed: 2026-09-27
status: complete
---

# Phase 10 Plan 03: GitHub Clarification-Comment Posting Summary

A GitHub-sourced run now gets a voice on its own issue: when a role raises `ROLE_NEEDS_INPUT`, `orchestrator/runner.py` posts the question as a fresh, machine-attributed comment via `GitHubClient.create_comment`, threads the returned comment id into the same `apply_transition` call that opens the `WAITING` `human_interactions` row, skips the post entirely on a re-entered attempt, and fails soft (never silent) on a GitHub outage -- all proven both at the unit tier (a real throwaway git worktree, `FakeGitHubClient`, a monkeypatched `apply_transition` spy) and against real PostgreSQL 18.6 (Neon).

## Performance

- **Duration:** ~2h across two dispatches (Task 1 to a Task 2 precondition-blocked checkpoint; continuation completed Task 2 once a throwaway Neon connection string was supplied)
- **Started:** 2026-09-27 (session start)
- **Completed:** 2026-09-27
- **Tasks:** 2/2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `CLARIFICATION_COMMENT_PREFIX` + `build_clarification_comment(questions)` (new, `orchestrator/runner.py`): a pure function taking **only** the question list -- the body is the prefix, a blank line, then the exact newline-join of `questions`, so the posted comment and the persisted `human_interactions.question` can never disagree, and no internal-state value is ever in scope to leak (T-10-12).
- `_github_issue_ref(state)` (new, `orchestrator/runner.py`): structural GitHub-sourcedness check reading `source_kind` + the `owner`/`repo`/`issue_number` metadata triple, mirroring `publish.py`'s `_pr_body` defensive style.
- `_run_current_role`'s `Signal.ROLE_NEEDS_INPUT` branch extended: a GitHub-sourced run whose pending interaction has no recorded `clarification_comment_id` calls `github_client_factory().create_comment(...)` and threads the returned id into the same `HumanInteractionWrite(mode="ask", ...)` the branch already builds -- one `apply_transition` call, one commit, question and comment id can never disagree.
- D-05 idempotency: `state.pending_clarification_comment_id` (the `RunState` field plan 10-06 already added) gates the post -- already-set skips it entirely, zero GitHub calls.
- Fail-soft: a `GitHubError` from `create_comment` is caught, never propagated. `clarification_comment_id` stays `NULL`, the `QUESTION_CREATED`/`RUN_PAUSED` events and the `ask` write are unchanged, and the redacted failure text rides the existing `QUESTION_CREATED` payload under a new `clarification_comment_error` key -- no new `EventType` member.
- 9 new unit tests (`tests/unit/test_clarification_comment.py`) and 5 new db-tier tests against real PostgreSQL (`tests/db/test_ask_posts_comment.py`) cover every `must_haves.truths` line and every listed behavior.
- Fixed a pre-existing, unrelated stale-assertion bug discovered while re-running this plan's own named regression suite (see Deviations).

## Task Commits

1. **Task 1: Ask on the issue -- post once, record the id, still pause** (auto, tdd) -- `ebd83d7` (test, RED -- verified by temporarily stashing the implementation and confirming `ImportError` on `CLARIFICATION_COMMENT_PREFIX`), `dc4d36b` (feat, GREEN)
2. **Task 2: Prove it against a real run -- one comment, still WAITING_HUMAN** (auto) -- `19945f8` (test -- the db-tier proof file), `c0ed636` (fix -- the Rule 1 regression fix to a pre-existing stale test)

**Interim checkpoint (between the two dispatches):** Task 2's db-tier precondition (no reachable PostgreSQL 17 in the first dispatch's environment -- no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) was genuinely unmet; execution paused at a `checkpoint:human-verify` after Task 1 completed and committed, per this project's precondition-gate discipline. A human then supplied a throwaway Neon PostgreSQL connection string (the same one already used for plans 10-02/10-06 in this phase) for this continuation dispatch only; it was never written to any file, committed, or echoed in this document.

**Plan metadata:** commit hash recorded after this file is written (see the final `docs(10-03)` commit).

## Files Created/Modified

- `src/dark_factory/orchestrator/runner.py` -- `CLARIFICATION_COMMENT_PREFIX`, `build_clarification_comment`, `_github_issue_ref`, the extended `Signal.ROLE_NEEDS_INPUT` branch
- `tests/unit/test_clarification_comment.py` (new) -- 9 unit tests over the body template and the branch's decision logic
- `tests/db/test_ask_posts_comment.py` (new) -- 5 db-tier tests against real PostgreSQL
- `tests/db/test_human_interactions_schema.py` -- widened the column-count assertion from 8 to 10 (Rule 1 fix, unrelated to this plan's own feature)

## Decisions Made

See `key-decisions` in frontmatter: the exact `CLARIFICATION_COMMENT_PREFIX` text; `RunState.pending_clarification_comment_id` as the existing field reused (no `repositories.py` change); reusing `QUESTION_CREATED`'s payload for a failed-post marker rather than a new `EventType`; `_github_issue_ref` as the structural GitHub-sourcedness check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_human_interactions_schema.py` asserted a stale 8-column shape after migration 0006 had already added two columns**
- **Found during:** Task 2, while running this plan's own named regression file (`tests/db/test_human_interactions_schema.py`) against real PostgreSQL as part of the `<verification>` block
- **Issue:** Plan 10-06's migration `0006_github_publishing_columns` added `human_interactions.clarification_comment_id`/`github_comment_id` (nullable `BigInteger`) weeks before this dispatch, but `tests/db/test_human_interactions_schema.py`'s `_INTERACTION_COLUMNS` set and its nullability assertion were never updated to match -- this file was not in plan 10-06's own `files_modified` list and its db-tier suite was not exhaustively re-run at that time (documented in `10-06-SUMMARY.md`'s coverage item D11). The gap surfaced only now because this plan's own regression check is the first time this specific file ran against a real database since `0006` landed.
- **Fix:** Widened `_INTERACTION_COLUMNS` to the current ten columns and added `clarification_comment_id`/`github_comment_id` to the nullable-column assertion list; renamed the test from "eight declared columns" to "ten declared columns" and updated the module docstring accordingly. No production code changed -- this is a test-only correction to a stale invariant.
- **Files modified:** `tests/db/test_human_interactions_schema.py`
- **Verification:** `tests/db/test_human_interactions_schema.py` -- 12/12 passed against real PostgreSQL 18.6 (Neon)
- **Committed in:** `c0ed636`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug, pre-existing and unrelated to this plan's own feature work).
**Impact on plan:** Zero scope creep -- the fix is a single test file's stale assertion, discovered only because this plan's own `<verification>` block names that file as a regression check. Left unfixed, it would have falsely reported this plan's own schema-touching regression suite as broken forever.

## Issues Encountered

**Task 2's db-tier precondition was genuinely unmet in the first dispatch** -- no PostgreSQL reachable (no Docker, no local `initdb` 17, `DARK_FACTORY_TEST_DATABASE_URL` unset), verified read-only via `docker info`, `which initdb`, and the environment variable. Execution halted at a `checkpoint:human-verify` after Task 1's two commits landed, per this project's precondition-gate discipline (matching the identical situation plans 10-02 and 10-06 hit earlier in this same phase). A human then supplied the same throwaway Neon connection string already used for those two plans; `alembic current` was verified against it (`0006_github_publishing_columns (head)`) before running any test, per the coordinator's explicit instruction rather than assuming migration state.

**The full `pytest -q` suite was not exhaustively re-run** (following the same reasoning `10-06-SUMMARY.md`'s coverage item D11 documented): each test's connection to this session's remote Neon instance costs roughly 20-40 seconds round trip. Prioritized instead: the plan's own new db-tier file (5/5), every named regression file from the plan's `<verification>` block (`test_pause_path_atomic.py`, `test_pause_mechanism_generic.py`, `test_human_interactions_schema.py`, `test_state_event_pairing.py`, `test_pause_exit_zero.py`, `test_resume_with_answer.py` -- all passing), and the full unit+contract tier (742 tests, no database). A human with faster database access should run the full `uv run pytest -q` before this phase is treated as fully proven against the entire existing suite -- the same open item `10-06-SUMMARY.md` already carries forward.

## User Setup Required

None for this plan specifically -- `GITHUB_TOKEN` remains unconfigured in the shipped environment (carried forward from plan 10-01's disclosed gap), which is expected: this plan's entire db-tier proof runs against `FakeGitHubClient`, by design.

## Next Phase Readiness

Plan 10-04 (the inbound half of the resume loop -- receiving a reply comment, resolving it to this interaction, and resuming the same `RoleExecution`) can now build on: `clarification_comment_id` as a genuinely populated, real value on a `WAITING` interaction (not just a schema column); `CLARIFICATION_COMMENT_PREFIX` as the fixed marker its own self-comment filter can reference to recognize (and skip) Dark Factory's own comments; and the confirmed fact that `RunState.pending_clarification_comment_id` reads back `None` once an interaction is `ANSWERED` (already proven by plan 10-06, unchanged here).

No blockers for plan 10-04. The one open item is the same D11-style full-suite gap plan 10-06 already carries (a full, unrestricted `pytest -q` against a faster PostgreSQL instance) -- recommended before shipping, not before continuing to the next plan.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-27*

## Self-Check: PASSED

All 4 claimed created/modified files verified present on disk; all four claimed commit hashes (`ebd83d7`, `dc4d36b`, `19945f8`, `c0ed636`) verified present in `git log`.
