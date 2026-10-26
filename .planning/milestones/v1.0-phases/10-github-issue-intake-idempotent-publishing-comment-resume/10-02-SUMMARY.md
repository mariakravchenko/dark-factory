---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 02
subsystem: orchestrator
tags: [publishing, github, idempotency, crash-recovery, postgresql]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "GitHubClient.find_pull_request_for_branch, FakeGitHubClient (plan 10-01); orchestrator/publish.py's run_publish_step, RunState.pr_number/pr_url/published_commit_sha, PublishFieldsWrite/apply_transition's publish_fields keyword, github_client_factory seam (plan 10-06)"
provides:
  - "orchestrator/publish.py::run_publish_step -- a Stage 2 three-way persisted-identifier fast path (zero git/GitHub calls once published_commit_sha and pr_number are both recorded) plus a Stage 3 GitHub-side existence check (find_pull_request_for_branch, head-branch-scoped) before every create_pull_request"
  - "PublishResult.adopted_existing_pr: bool -- distinguishes a pull request created by this attempt from one adopted from a prior attempt"
  - "tests/unit/test_publish_idempotency.py -- 9 pure-tier tests covering all three partial-completion points, head-branch-equality adoption, and the GitHub-error safety-net path"
  - "tests/db/test_publish_idempotency.py -- real drive()+PostgreSQL proof that the crash-between-pulls.create-and-its-commit window yields exactly one pull request"
affects: [10-03, 10-04, 10-05]

actuals:
  tokens: 14576
  tasks: 2
  commits: 3
  plan_head_before: 2f397d4dbfe033854595ccb0291e400116371739

tech-stack:
  added: []
  patterns:
    - "Idempotency-by-external-consultation: a persisted identifier alone (a NULL pr_number) can only mean 'not recorded', never 'not created'. run_publish_step's Stage 3 asks GitHub itself (a pure, head-branch-scoped read) before every create -- the same principle Phase 5's WIP-recovery commit already applies to git's own state, now applied to GitHub's."
    - "Crash-window db tests reproduce the interruption in-process by monkeypatching the module-level apply_transition symbol the orchestrator calls, gated on a kwarg predicate (publish_fields is not None) rather than a global always-raise -- so only the exact terminal transition under test is interrupted, and every earlier role's own transition in the same drive() call proceeds normally."

key-files:
  created:
    - tests/unit/test_publish_idempotency.py
    - tests/db/test_publish_idempotency.py
  modified:
    - src/dark_factory/orchestrator/publish.py

key-decisions:
  - "Stage 2 (fast path) and Stage 3 (GitHub-side safety net) are sequential, not merged: Stage 2 is checked and returned first whenever both published_commit_sha and pr_number are set, making every ordinary retry free (no git command, no GitHub call); Stage 3 -- commit/push only what is missing, then find_pull_request_for_branch, then create only if nothing was found -- runs only on the narrow 'Neon says no PR yet' branch."
  - "state.working_branch is asserted equal to working_branch_name(run_id) at the top of the create_pr=True path -- a mismatch is a programming error (never a recoverable runtime state), so it raises rather than silently publishing onto the wrong branch."
  - "adopted_existing_pr is a plain declared PublishResult field (not a computed_field folding other fields), because it records an observation about what happened (created now vs. found already existing) rather than a derivable fact -- mirrors PublishResult's existing 'no folded success flag' posture."
  - "orchestrator/runner.py was deliberately left untouched (not added to files_modified) -- adopted_existing_pr is exposed on PublishResult only; whether it belongs in the PR_CREATED event payload is left to plan 10-05/Phase 12, and runner.py is plan 10-03's file in the same wave."
  - "Head-branch-equality adoption is proven with a local, file-scoped test double (_HeadScopedFakeGitHubClient in both test files) rather than extending the shared tests/support/fake_github.py -- that file is out of this plan's files_modified, and the real GitHubClient's own head=owner:branch server-side filter is what production code actually relies on (it never re-checks the returned PR's head itself)."
  - "The db-tier 'plain retry with everything recorded' scenario seeds its RunState via a direct self-transition apply_transition(...,publish_fields=...) call against a one-role [QA] pipeline, then calls run_publish_step directly -- cheaper and just as real a Postgres round-trip as a full four-role drive(), since Stage 2 never touches work_dir or git."

requirements-completed: [GIT-04]

coverage:
  - id: D1
    description: "PublishResult gains adopted_existing_pr: bool = False, and run_publish_step's Stage 2 fast path returns all three persisted identifiers verbatim with an empty client call log whenever published_commit_sha and pr_number are both already set"
    requirement: GIT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py::test_all_three_identifiers_recorded_returns_them_with_no_client_calls"
        status: pass
      - kind: integration
        ref: "tests/db/test_publish_idempotency.py::test_a_run_with_all_three_identifiers_recorded_reenters_with_an_empty_call_log (real load_run_state against PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Stage 3's GitHub-side existence check (find_pull_request_for_branch, head-branch-scoped) runs before every create_pull_request whenever pr_number is NULL; adopting a match issues no second commit/push and no create call"
    requirement: GIT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py::test_pushed_but_unrecorded_pr_adopts_an_existing_pull_request, ::test_nothing_recorded_commits_pushes_checks_then_creates_in_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "A run interrupted after the fake pulls.create call succeeded but before apply_transition committed its identifier -- reproduced in-process against real PostgreSQL -- resumes to COMPLETED with exactly one pull request total across both attempts"
    requirement: GIT-04
    verification:
      - kind: integration
        ref: "tests/db/test_publish_idempotency.py::test_crash_between_pull_request_creation_and_its_commit_yields_one_pull_request (real PostgreSQL 18.6/Neon)"
        status: pass
    human_judgment: false
  - id: D4
    description: "An existing pull request scripted on a different head branch is never adopted -- the resumed attempt creates its own instead (2 create_pull_request calls total; the adopted number is never the unrelated PR's)"
    requirement: GIT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py::test_existing_pr_on_a_different_head_branch_is_not_adopted"
        status: pass
      - kind: integration
        ref: "tests/db/test_publish_idempotency.py::test_adoption_is_head_branch_scoped"
        status: pass
    human_judgment: false
  - id: D5
    description: "A GitHubError from find_pull_request_for_branch returns a failed PublishResult and never falls through into create_pull_request; the resumed, adopting attempt issues no pull-request-mutating call of any kind"
    requirement: GIT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_idempotency.py::test_github_api_error_from_find_pull_request_does_not_fall_through_to_create"
        status: pass
      - kind: integration
        ref: "tests/db/test_publish_idempotency.py::test_the_resumed_attempt_issues_no_pull_request_mutating_call"
        status: pass
    human_judgment: false
  - id: D6
    description: "The full unit+contract tier (733 tests) and the targeted db-tier regression set (test_publish_step.py, test_publish_idempotency.py, test_wip_commit_recovery.py -- 10 tests) are green against real PostgreSQL 18.6 (Neon); a full unrestricted tests/db/ + tests/integration/ run was not attempted in this session"
    verification: []
    human_judgment: true
    rationale: "This session's PostgreSQL instance is a remote Neon database with no connection pooling in the test harness (NullPool, fresh connection per test, ~30-40s round trip per db-tier test observed) -- tests/db/ alone holds 40 files and tests/integration/ another 36; an exhaustive run was impractical within this dispatch, matching plan 10-06's own documented D11 rationale for the identical constraint. Verified instead: unit+contract in full (733 passed), this plan's own two new files (test_publish_idempotency.py: 9 unit + 4 db, all passing), and every db-tier file this plan's change could plausibly regress (test_publish_step.py's own 4 publish-step scenarios, test_wip_commit_recovery.py's 2 crash/resume-adjacent scenarios) -- 10 db-tier tests total, all passing against real PostgreSQL 18.6. Unlike plan 10-06, this plan touched no shared test fixture (tests/conftest.py was not modified), so the regression surface for other db-tier files is narrow: a grep confirms PublishResult is constructed in exactly two other places (orchestrator/runner.py's GitHubError-on-construction-failure branch and tests/unit/test_publish_step_unit.py's own equality assertion), both via keyword args that omit adopted_existing_pr and therefore pick up its default unchanged. A human with faster database access should still run the full `uv run pytest -q` before this plan is treated as fully proven against the entire existing suite, carrying forward 10-06's own open D11 item rather than duplicating it."

duration: ~55min (across two dispatches: Task 1 to a precondition-blocked checkpoint, then continuation with a supplied throwaway Neon connection string through Task 2's completion)
completed: 2026-09-27
status: complete
---

# Phase 10 Plan 02: Idempotent Publishing — the Three-Way Check and the GitHub Existence Net Summary

**`run_publish_step` now closes the crash window a database flag alone cannot close: a Stage 2 fast path returns a fully-recorded pull request for free, and a Stage 3 GitHub-side `find_pull_request_for_branch` existence check runs before every `create_pull_request` whenever `pr_number` is still NULL — proven against real PostgreSQL 18.6 (Neon) that a run interrupted between the fake `pulls.create` call and its DB commit resumes to exactly one pull request, never two.**

## Performance

- **Duration:** ~55min total (Task 1 complete in the first dispatch; Task 2 was precondition-blocked at a checkpoint, then completed in a continuation dispatch once a throwaway Neon connection string was supplied)
- **Started:** 2026-09-27 (session start)
- **Completed:** 2026-09-27
- **Tasks:** 2/2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- `orchestrator/publish.py::run_publish_step` restructured into an explicit three-stage decision: Stage 1 (the unchanged `create_pr` gate), Stage 2 (the three-way persisted-identifier fast path — zero git/GitHub calls once `published_commit_sha` and `pr_number` are both set), Stage 3 (act, with `client.find_pull_request_for_branch` as the crash-safety net before every `create_pull_request`).
- `PublishResult.adopted_existing_pr: bool` — new field distinguishing "created now" from "found already existing," so a caller (or a future event payload) can tell the two apart without a second GitHub call.
- A `GitHubError` from the existence check returns a failed result and never falls through into `create_pull_request` — an unreadable GitHub state is never treated as proof no pull request exists.
- `tests/unit/test_publish_idempotency.py` (new, 9 tests, no database): all three partial-completion points (nothing recorded / pushed-but-unrecorded / fully recorded), the head-branch-equality adoption rule (via a local, file-scoped `_HeadScopedFakeGitHubClient` double), positional call-order assertions (existence check strictly precedes create), and the GitHub-error safety-net path.
- `tests/db/test_publish_idempotency.py` (new, 4 tests, real PostgreSQL 18.6/Neon): the crash window reproduced in-process (a targeted `apply_transition` wrapper that raises only on the call carrying a non-`None` `publish_fields`) proves exactly one pull request survives a crash-and-resume; a fully-recorded run re-enters with an empty GitHub client call log; adoption is proven head-branch-scoped; the resumed, adopting attempt is proven to issue no pull-request-mutating call.

## Task Commits

1. **Task 1: Check before acting — the three persisted identifiers, then GitHub itself** (auto, tdd) — `05405bd` (feat)
2. **Task 2: Prove the crash window against a real run — one pull request, not two** (auto) — `ef0a704` (docs — recorded the precondition blocker before a database became available), `659b353` (test — the four db-tier scenarios)

**Plan metadata:** commit hash recorded after this file is written (see final `docs(10-02)` commit)

## Files Created/Modified

- `src/dark_factory/orchestrator/publish.py` — `run_publish_step`'s three-stage restructure, `PublishResult.adopted_existing_pr`, expanded module/function docstrings naming the ordering and the three partial-completion points
- `tests/unit/test_publish_idempotency.py` — pure-tier proof, `_OrderedFakeGitHubClient`/`_HeadScopedFakeGitHubClient` local test doubles, git-primitive spies
- `tests/db/test_publish_idempotency.py` — real `drive()` + real PostgreSQL proof, the in-process crash-window reproduction, `_HeadScopedFakeGitHubClient`

## Decisions Made

See `key-decisions` in frontmatter: Stage 2/Stage 3 sequencing and the "free on retry" property; the `working_branch` mismatch assertion; `adopted_existing_pr` as a plain declared field; `runner.py` left untouched per the plan's wave-safety instruction; the local (not shared-fixture) head-scoped test double; the direct-self-transition seeding idiom for the "plain retry" db scenario.

## Deviations from Plan

None — plan executed exactly as written. The plan's own `<flagged_assumptions>` section had already resolved every open question before this dispatch (the `githubkit` call shape was confirmed in plan 10-01; the two prohibitions were authored descriptor-less and are covered above by tests rather than an unwired check).

## Issues Encountered

**Task 2's precondition was genuinely unmet at the start of the first dispatch.** No PostgreSQL was reachable (no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) — verified read-only. Execution halted at a `checkpoint:human-verify` after Task 1 completed, per this project's precondition-gate discipline, mirroring plan 10-06's own identical situation earlier in this phase. A human then supplied the same throwaway Neon PostgreSQL connection string plan 10-06 used, confirmed already at migration head (`alembic current` → `0006_github_publishing_columns (head)`) before any test ran. The connection string was used only as a command-scoped environment variable, never written to any file, test, or this document.

**A full unrestricted `tests/db/` + `tests/integration/` run was not attempted** — see coverage item D6's rationale. This carries forward, rather than duplicates, plan 10-06's own open D11 item.

## User Setup Required

None for this plan specifically. `GITHUB_TOKEN` remains unconfigured in the shipped environment (carried forward from plan 10-01's disclosed gap) — this plan's entire proof runs against `FakeGitHubClient`, by design.

## Next Phase Readiness

Plan 10-03 (clarification-comment idempotency) and plan 10-04 (answering-comment dedup, same wave) can proceed with no blockers from this plan: `orchestrator/runner.py` was left untouched, so there is no merge conflict surface. `PublishResult.adopted_existing_pr` is available for plan 10-05 or Phase 12 to fold into the `PR_CREATED` event payload if desired — deliberately left undone here per the plan's own instruction.

The one open item is coverage D6 (a full, unrestricted `pytest -q` against a faster PostgreSQL instance) — recommended before shipping, carried forward alongside plan 10-06's own identical open item, not a new gap this plan introduces.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-27*

## Self-Check: PASSED

All 4 claimed created/modified files verified present on disk; all three claimed commit hashes (`05405bd`, `ef0a704`, `659b353`) verified present in `git log`.
