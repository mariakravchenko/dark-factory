---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 06
subsystem: orchestrator
tags: [publishing, github, migration, event-catalog, mutation-path, postgresql]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "GitHubClient wrapper, FakeGitHubClient, RepositoryConfig.github_owner/github_repo, and the real _load_github loader (plan 10-01)"
provides:
  - "orchestrator/publish.py: PublishResult + run_publish_step -- commits, pushes and opens exactly one pull request via the injected GitHubClient, never re-raising GitHubError"
  - "The github_client_factory seam threaded through advance/drive/_advance_once/_run_current_role, called lazily only when publishing.create_pr is true"
  - "runs.published_commit_sha, human_interactions.clarification_comment_id/github_comment_id (migration 0006), and PublishFieldsWrite's patch-semantics keyword on apply_transition"
  - "EventType.PUBLISH_STARTED/PR_CREATED/PUBLISH_FAILED (D-07) -- the only durable trace a publish attempt ran"
  - "RunState.pr_number/pr_url/published_commit_sha/pending_clarification_comment_id"
  - "start_run wires the snapshot's repository block into load(), so dark-factory run github:<n> resolves end to end (INTAKE-03 wiring half)"
affects: [10-02, 10-03, 10-04, 10-05]

actuals:
  tokens: 23515
  tasks: 2
  commits: 5

tech-stack:
  added: []
  patterns:
    - "The publish step's own commit_run_artifacts call runs inside the terminal role's gate-PASS arm, before the generic per-role commit -- it is the commit that actually carries the role's artifacts plus the freshly written verification/quality_gate.json, labelled 'publish' rather than the role's own name; the later generic commit finds nothing new and no-ops."
    - "Publishing is gated solely on publishing.create_pr: when false, no client is ever constructed (github_client_factory is never called) and no PUBLISH_* event is emitted at all -- not merely a create_pr=false PublishResult."
    - "A repository config missing github_owner/github_repo/base_branch, or a client-construction failure (MissingGitHubCredentialError), folds into the same PublishResult.error / PUBLISH_FAILED shape as a create_pull_request failure -- never an uncaught exception into the orchestrator loop."

key-files:
  created:
    - src/dark_factory/orchestrator/publish.py
    - migrations/versions/0006_github_publishing_columns.py
    - tests/unit/test_mutations.py
    - tests/unit/test_publish_step_unit.py
    - tests/db/test_github_publishing_columns_schema.py
    - tests/db/test_publish_step.py
  modified:
    - src/dark_factory/events/catalog.py
    - src/dark_factory/persistence/models.py
    - src/dark_factory/persistence/mutations.py
    - src/dark_factory/persistence/repositories.py
    - src/dark_factory/orchestrator/runner.py
    - tests/unit/test_domain_enums.py
    - tests/unit/test_context_builder.py
    - tests/unit/test_persistence.py
    - tests/db/test_load_run_state.py
    - tests/conftest.py

key-decisions:
  - "Publish step placement: inside the terminal role's gate-PASS arm, before the generic commit_run_artifacts call -- so run_publish_step's own commit captures the role's artifacts plus quality_gate.json in one commit labelled 'publish', and the later generic call safely no-ops (nothing new to stage)."
  - "PR body template: 'Produced by Dark Factory.' plus 'Closes {owner}/{repo}#{issue_number}' when the metadata keys are present -- no run id, worktree path, worker name, branch name or credential. Plans 10-02/10-03 should reuse this template verbatim rather than re-deriving it."
  - "pending_clarification_comment_id is populated only while the human_interactions row is still WAITING; once ANSWERED it reads back None (the column itself is never cleared) -- the same single extended query pending_answer already used, disambiguated by status in Python rather than a second query."
  - "Rule 1 fix: tests/conftest.py's shared _write_config_tree now defaults publishing.create_pr to false, not PublishingConfig's own true default -- every other db test in this suite drives a run to COMPLETED with no repository/GITHUB_TOKEN configured, and this plan's new publish step would otherwise convert all of them into PUBLISH_FAILED/ROLE_FAILED. tests/db/test_publish_step.py explicitly overwrites the block back to true."
  - "_write_human_interaction needed both comment-id branches: clarification_comment_id assigned in ask mode (plan 10-03 will be its first real writer), github_comment_id assigned in answer mode only when supplied (plan 10-04 will be its first real writer) -- both landed here so neither later plan touches mutations.py."
  - "apply_transition's publish_fields patch landed as step 8 of 10 in the docstring's numbered order -- immediately after the status/current_role/current_step/lease-clear block (old step 7) and before counter_increments (renumbered from 8 to 9)."
  - "run_publish_step's final signature: run_publish_step(*, run_id: UUID, state: RunState, work_dir: Path, client: GitHubClient | None, create_pr: bool, known_secrets: Mapping[str, str]) -> PublishResult. client is Optional only because the create_pr=False early-return path never touches it; the caller's contract is to always pass a real client when create_pr is True."

patterns-established:
  - "A second FakeGitHubClient monkeypatched into dark_factory.input.loaders (mirroring tests/unit/test_load_github.py's own _StubClientFactory idiom) is how a db test drives a real github: locator end to end with no network call, distinct from the github_client_factory-injected fake that covers the publish step itself."

requirements-completed: [INTAKE-03, GIT-03, GIT-04]

coverage:
  - id: D1
    description: "EventType widened to exactly 19 members, adding PUBLISH_STARTED/PR_CREATED/PUBLISH_FAILED (D-07) and correcting the stale Phase 12 attribution sentence"
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py::test_event_type_has_exactly_nineteen_members_with_the_phase_two_five_six_nine_and_ten_types"
        status: pass
    human_judgment: false
  - id: D2
    description: "PublishFieldsWrite (frozen, extra=forbid, three optional fields) and apply_transition's publish_fields keyword apply patch semantics -- omitting a field leaves the existing runs column untouched"
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_mutations.py (7 tests: defaults, all-fields, frozen, unknown-keyword rejection, HumanInteractionWrite's two new fields)"
        status: pass
      - kind: integration
        ref: "tests/db/test_publish_step.py::test_happy_path_completes_with_one_pull_request_and_persisted_identifiers (real apply_transition against PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Migration 0006: runs.published_commit_sha (nullable String) and human_interactions.clarification_comment_id/github_comment_id (nullable BigInteger) -- including the GIT-04 64-bit precision edge"
    requirement: GIT-04
    verification:
      - kind: integration
        ref: "tests/db/test_github_publishing_columns_schema.py (7 tests against real PostgreSQL 18.6/Neon, incl. the 2^52 round-trip)"
        status: pass
      - kind: integration
        ref: "tests/db/test_migrations.py (alembic check reports no drift; downgrade/upgrade round-trips)"
        status: pass
    human_judgment: false
  - id: D4
    description: "RunState gains pr_number/pr_url/published_commit_sha (read straight off runs) and pending_clarification_comment_id (read from the same human_interactions row pending_answer already reaches, gated on WAITING status)"
    requirement: GIT-04
    verification:
      - kind: integration
        ref: "tests/db/test_load_run_state.py (9 tests: fresh-run all-None, verbatim column round-trip, WAITING-populates/ANSWERED-does-not for the comment id)"
        status: pass
    human_judgment: false
  - id: D5
    description: "orchestrator/publish.py::run_publish_step -- commits, pushes, opens one PR via the injected GitHubClient; never re-raises GitHubError; a missing repository config folds into the same error shape"
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_publish_step_unit.py (4 tests against a real throwaway git repo + FakeGitHubClient: happy path, PR body content/exclusions, create_pr=false no-op, GitHubApiError does not re-raise)"
        status: pass
      - kind: integration
        ref: "tests/db/test_publish_step.py (4 scenarios against real PostgreSQL + real git: happy path, create_pr=false, PR-creation failure, base-branch-untouched)"
        status: pass
    human_judgment: false
  - id: D6
    description: "github_client_factory seam threaded through advance/drive/_advance_once/_run_current_role; called lazily only when publishing.create_pr is true, so a run that publishes nothing never constructs a client"
    requirement: "GIT-05/GIT-06 enabler"
    verification:
      - kind: integration
        ref: "tests/db/test_publish_step.py::test_create_pr_false_completes_with_no_pull_request (factory raises AssertionError if ever called; run still completes)"
        status: pass
    human_judgment: false
  - id: D7
    description: "start_run passes the snapshot's repository block into load(), so dark-factory run github:<n> resolves a real GitHub-sourced run end to end (INTAKE-03 wiring half)"
    requirement: INTAKE-03
    verification:
      - kind: integration
        ref: "tests/db/test_publish_step.py::test_happy_path_completes_with_one_pull_request_and_persisted_identifiers (asserts runs.source_kind == 'github' after start_run(\"github:5\", ...))"
        status: pass
    human_judgment: false
  - id: D8
    description: "A create_pull_request failure keeps the run out of COMPLETED with a durable PUBLISH_FAILED event and runs.pr_number left NULL (T-10-32 prohibition: never report COMPLETED when the claimed PR does not exist)"
    requirement: GIT-03
    verification:
      - kind: integration
        ref: "tests/db/test_publish_step.py::test_pr_creation_failure_keeps_the_run_out_of_completed"
        status: pass
    human_judgment: false
  - id: D9
    description: "The configured base branch's tip SHA is unchanged across a full publishing run -- Dark Factory never writes to the base branch, only to the run's own working branch"
    requirement: GIT-03
    verification:
      - kind: integration
        ref: "tests/db/test_publish_step.py::test_the_base_branch_tip_is_unchanged_across_a_full_publishing_run"
        status: pass
    human_judgment: false
  - id: D10
    description: "Rule 1 regression fix: publishing.create_pr defaulting to true in the shared test config tree would have broken every pre-existing db-tier test reaching the terminal role with default config (no repository/GITHUB_TOKEN) -- fixed by flipping the shared default to false"
    verification:
      - kind: integration
        ref: "The 7 previously-at-risk db test modules (test_quality_gate_gates_the_run.py, test_artifact_commit_per_role.py, test_four_role_pipeline.py, test_artifact_persistence.py, test_artifact_schema_violation_fails_role.py, test_feedback_reaches_developer.py, test_qa_bounce.py -- 23 tests total) re-run against real PostgreSQL with zero per-test changes"
        status: pass
    human_judgment: false
  - id: D11
    description: "The full test suite (every db-tier file, plus the integration tier) is green"
    verification: []
    human_judgment: true
    rationale: "This session's PostgreSQL instance is a remote Neon database with no connection pooling in the test harness (NullPool, fresh connection per test) -- each db-tier test costs roughly 30-40s round trip over the network, making an exhaustive run of the whole tests/db/ tree (dozens of files, hundreds of tests) impractical within this dispatch (a partial run was killed after ~15 minutes covering only ~70 tests). Verified instead: the unit + contract tier in full (724 passed, no database involved), plus every new/modified db-tier file (20 tests: test_github_publishing_columns_schema.py, test_publish_step.py, the extended test_load_run_state.py) and every db-tier file independently identified as at risk from the publishing-default change (23 tests across 7 files) -- 47 db-tier tests total, all passing against real PostgreSQL 18.6 (Neon). A human with faster database access (a local PostgreSQL 17/18, or patience for a multi-hour remote run) should run the full `uv run pytest -q` before this plan is treated as fully proven against the entire existing suite."

duration: ~2h40min (across two dispatches: Task 1 to a precondition-blocked checkpoint on Task 2, then continuation with a supplied throwaway Neon connection string through Task 2's completion)
completed: 2026-09-27
status: complete
---

# Phase 10 Plan 06: Publish Step, Publish-Identifier Schema, and GitHub Client Factory Seam Summary

Turns plan 10-01's GitHub edge into a durable publish path: a terminal-role PASS verdict plus a PASS quality gate now commits, pushes, and opens exactly one pull request whose number, URL and commit SHA are persisted in the same transaction that completes the run, and `dark-factory run github:<n>` resolves end to end for the first time — proven against real PostgreSQL 18.6 (Neon) and a real throwaway git repository, with a `FakeGitHubClient` standing in for GitHub itself.

## Performance

- **Duration:** ~2h40min total (Task 1 ~1h40min including extensive read_first investigation and a genuine RED verification round-trip; Task 2 ~1h after a throwaway Neon connection string was supplied)
- **Started:** 2026-09-26 (session start)
- **Completed:** 2026-09-27T (session end)
- **Tasks:** 2/2
- **Files modified:** 16 (6 created, 10 modified)

## Accomplishments

- `orchestrator/publish.py` (new): `PublishResult` + `run_publish_step` — commits and pushes via the existing `dark_factory.git.diff` primitives, captures the pushed SHA, opens the PR through the injected `GitHubClient`, and never re-raises `GitHubError` (a redacted `PublishResult.error` instead, including a repository-config-missing case that would otherwise raise `AssertionError`/`TypeError`).
- `orchestrator/runner.py`: `GitHubClientFactory` / `default_github_client_factory` threaded through `advance`/`drive`/`_advance_once`/`_run_current_role` exactly like `tool_registry`, called lazily only when `publishing.create_pr` is true. `start_run` now passes the snapshot's `repository` block into `load()`, so a `github:` locator resolves. The terminal role's gate-PASS arm runs the publish step, appending `PUBLISH_STARTED` then `PR_CREATED`/`PUBLISH_FAILED` to the same `gate_events` list the Phase 9 gate already builds; a publish failure sets `Signal.ROLE_FAILED`.
- Migration `0006_github_publishing_columns.py`: `runs.published_commit_sha` (String, nullable) and `human_interactions.clarification_comment_id`/`github_comment_id` (BigInteger, nullable) — applied cleanly against real PostgreSQL 18.6 with `alembic check` reporting no drift.
- Three new `EventType` members (`PUBLISH_STARTED`, `PR_CREATED`, `PUBLISH_FAILED`, D-07) — the enum's count is pinned at exactly 19 by a unit test.
- `PublishFieldsWrite` (frozen, patch-semantics) and `apply_transition`'s new `publish_fields` keyword; `HumanInteractionWrite` gains `clarification_comment_id` (ask mode) / `github_comment_id` (answer mode).
- `RunState` gains `pr_number`, `pr_url`, `published_commit_sha`, `pending_clarification_comment_id` (the last populated only while the interaction row is still `WAITING`).
- Db-tier proof against real PostgreSQL (Neon): migration applies and round-trips with no drift; a real `github:`-sourced `drive()` run reaches `COMPLETED` having opened exactly one PR with all three identifiers persisted; `publishing.create_pr: false` completes with zero GitHub calls; a `create_pull_request` failure keeps the run out of `COMPLETED` with a durable `PUBLISH_FAILED` event; the base branch's tip is provably untouched.
- Fixed a Rule-1 regression this plan's own change would have introduced across roughly two dozen pre-existing db tests (see Deviations).

## Task Commits

1. **Task 1: End-to-end "a GitHub issue becomes one pull request" — one path only** (tracer, tdd) — `17e8c37` (test, RED — verified by temporarily removing the implementation and confirming `ImportError`/count-assertion failures), `cb2f325` (feat, GREEN)
2. **Task 2: Prove it against a real run — one issue, one migration, one pull request** (auto) — `eb600ec` (fix — `pending_clarification_comment_id` status gating + the `publishing.create_pr` test-default regression fix), `30c74ad` (test — the three db-tier proof files)

**Interim commit (between tasks, superseded by Task 2's completion):** `7489c5c` (docs — recorded the Task 2 precondition blocker before a database became available; the blocker is cleared in this plan's own metadata commit below)

**Plan metadata:** commit hash recorded after this file is written (see final `docs(10-06)` commit)

## Files Created/Modified

- `src/dark_factory/orchestrator/publish.py` — `PublishResult`, `run_publish_step`
- `src/dark_factory/orchestrator/runner.py` — `GitHubClientFactory`/`default_github_client_factory`, `start_run`'s `repository=` wiring, the terminal-role gate-PASS publish block, `publish_fields` on the final `apply_transition` call
- `migrations/versions/0006_github_publishing_columns.py` — the three new columns
- `src/dark_factory/events/catalog.py` — `PUBLISH_STARTED`/`PR_CREATED`/`PUBLISH_FAILED`
- `src/dark_factory/persistence/models.py` — `Run.published_commit_sha`, `HumanInteraction.clarification_comment_id`/`github_comment_id`
- `src/dark_factory/persistence/mutations.py` — `PublishFieldsWrite`, `apply_transition(publish_fields=...)`, `HumanInteractionWrite`'s two new fields
- `src/dark_factory/persistence/repositories.py` — `RunState`'s four new fields, `load_run_state`'s extended single query
- `tests/unit/test_mutations.py`, `tests/unit/test_publish_step_unit.py` — new unit coverage
- `tests/unit/test_domain_enums.py`, `tests/unit/test_context_builder.py`, `tests/unit/test_persistence.py` — updated for the widened schema
- `tests/db/test_github_publishing_columns_schema.py`, `tests/db/test_publish_step.py` — new db-tier coverage
- `tests/db/test_load_run_state.py` — extended
- `tests/conftest.py` — `_write_config_tree`'s `publishing.create_pr` default flipped to `false`

## Decisions Made

See `key-decisions` in frontmatter: publish-step placement inside the gate-PASS arm (before the generic per-role commit); the PR body template; `pending_clarification_comment_id`'s WAITING-only gating; the `publishing.create_pr` test-default flip; both `HumanInteractionWrite` comment-id branches landing in this plan; `apply_transition`'s step-8 patch ordering; `run_publish_step`'s final signature (`client: GitHubClient | None`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `pending_clarification_comment_id` leaked a stale value after the interaction was answered**
- **Found during:** Task 2, while writing `tests/db/test_load_run_state.py`'s new test for this field
- **Issue:** Task 1's `load_run_state` read `clarification_comment_id` unconditionally off the single `human_interactions` row bound to the latest attempt, with no status check — once a question was answered, the field would still report the (now-stale) comment id, even though "pending" no longer applies.
- **Fix:** Extended the single query to also select `status`, and only populate `pending_clarification_comment_id` when that status is `WAITING`. `pending_answer` is unaffected (it was already correctly gated by the column itself being `NULL` until answered).
- **Files modified:** `src/dark_factory/persistence/repositories.py`
- **Verification:** `tests/db/test_load_run_state.py::test_pending_clarification_comment_id_reads_from_a_waiting_row_but_not_an_answered_one` (real PostgreSQL)
- **Committed in:** `eb600ec`

**2. [Rule 1 - Bug] This plan's own publish step would have broken ~24 pre-existing db-tier tests**
- **Found during:** Task 2, while designing `tests/db/test_publish_step.py` and reasoning about the shared test config tree
- **Issue:** `tests/conftest.py`'s shared `_write_config_tree` (used by 15+ db test files via `config_root_factory`) wrote `publishing:\n  create_pr: true\n` — harmless before this plan (nothing read that field), but Task 1's new terminal-role gate-PASS block now attempts a real publish whenever `create_pr` is true. Every db test driving a four-role pipeline to `COMPLETED` with the shared tree's default config (no `repository.github_owner`/`github_repo`, no `GITHUB_TOKEN`) would fold into `PUBLISH_FAILED`/`ROLE_FAILED` and never reach `COMPLETED` — a regression this plan's own commits would have introduced into roughly two dozen unrelated tests. Confirmed via static analysis (7 files whose QA role declares a `verdict.json` output and whose test asserts `RunStatus.COMPLETED`).
- **Fix:** Flipped the shared tree's default to `publishing:\n  create_pr: false\n`. `tests/db/test_publish_step.py` (this plan's own new proof, the one file that actually needs publishing) explicitly overwrites the block back to `true` via the same build-then-overwrite idiom `test_quality_gate_gates_the_run.py` already established for its own `quality_gate.commands`/`retry` blocks.
- **Files modified:** `tests/conftest.py`
- **Verification:** All 7 previously-at-risk db test modules (23 tests: `test_quality_gate_gates_the_run.py`, `test_artifact_commit_per_role.py`, `test_four_role_pipeline.py`, `test_artifact_persistence.py`, `test_artifact_schema_violation_fails_role.py`, `test_feedback_reaches_developer.py`, `test_qa_bounce.py`) re-run against real PostgreSQL with zero per-test changes — all pass.
- **Committed in:** `eb600ec`

**3. [Rule 3 - Blocking] The shared `config_root_factory` config tree does not declare `verdict.json` as a QA output**
- **Found during:** Task 2, while writing `tests/db/test_publish_step.py`'s happy-path scenario
- **Issue:** `tests/conftest.py`'s `_write_config_tree` writes every role's `outputs:` as `[]`. Without a declared `verdict.json` output, `collect_role_artifacts` never produces a `verdict.json`-typed `ArtifactReferenceWrite`, so `orchestrator/runner.py`'s `verdict_write is not None` guard silently skips the entire verdict-fold/gate/publish block — the run reaches `COMPLETED` but never attempts to publish, which the first draft of this test's happy-path scenario discovered as a `pr_number is None` failure.
- **Fix:** `tests/db/test_publish_step.py`'s own `_write_github_four_role_tree` writes explicit per-role `.dark-factory/roles/*.yaml` files with real `inputs:`/`outputs:` declarations (mirroring `test_quality_gate_gates_the_run.py`'s own `_write_four_role_tree`), rather than relying on the shared factory's empty defaults.
- **Files modified:** `tests/db/test_publish_step.py` only (test-local fix, no production or shared-fixture change)
- **Verification:** All 4 scenarios in `tests/db/test_publish_step.py` pass against real PostgreSQL.
- **Committed in:** `30c74ad`

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 3 blocking issue).
**Impact on plan:** Deviation 1 is a correctness fix scoped entirely to this plan's own new field. Deviation 2 is a necessary compatibility fix that keeps ~24 pre-existing tests green after this plan's own change — no scope creep, the alternative would have been silently breaking the existing suite. Deviation 3 is test-local and does not touch production code or the shared fixture.

## Issues Encountered

**Task 2's precondition was genuinely unmet at the start of this dispatch.** No PostgreSQL 17 was reachable in the execution environment (no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) — verified read-only by invoking `tests/conftest.py`'s own `pg_url` fixture, which raised its own fail-loud `pytest.UsageError`. Per this project's precondition-gate discipline, execution halted at a `checkpoint:human-verify` after Task 1 completed, rather than skipping or faking the db-tier proof. A human then supplied a throwaway Neon PostgreSQL connection string (18.6, not 17 — `tests/conftest.py`'s docstring assumes 17, but nothing in the "external" probe rung enforces the major version, and everything ran correctly against 18.6), which is used only for this dispatch's `DARK_FACTORY_TEST_DATABASE_URL` and is never written to any file, committed, or echoed in this document.

**The full db-tier suite was not exhaustively re-run** — see coverage item D11's rationale. Each test's fresh connection to this session's remote Neon instance costs roughly 30-40 seconds round trip (`NullPool`, no connection reuse across tests), making a full `tests/db/` run (dozens of files) impractical within this dispatch (an unrestricted `pytest -q` run was killed after ~1.5 hours having completed only ~70 of an estimated many hundreds of tests). The unit + contract tier (724 tests, no database) plus every new/modified/at-risk db-tier file (47 tests across 12 files) were prioritized instead and all pass.

## User Setup Required

None for this plan specifically — `GITHUB_TOKEN` remains unconfigured in the shipped environment (carried forward from plan 10-01's own disclosed gap), which is expected: this plan's entire db-tier proof runs against `FakeGitHubClient`, by design, so no real GitHub credential or network call was ever needed here. A human with a configured `GITHUB_TOKEN` and a real target repository should eventually run a live end-to-end smoke (real `github:` issue → real pull request) before this path is trusted against a production repository — tracked as coverage item D11's broader sibling, not a new gap this plan introduces.

## Next Phase Readiness

Wave 3 (plans 10-02, 10-03, 10-04) can now build on: the `github_client_factory` seam (reused, not reinvented, for the existing-PR check and the clarification-comment post); `PublishFieldsWrite`/`apply_transition`'s patch semantics; both `HumanInteractionWrite` comment-id fields (already landed, ready for their first real writers); `RunState.pending_clarification_comment_id`; and the PR body template (`_pr_body` in `orchestrator/publish.py`), which plans 10-02/10-03 should reuse verbatim rather than re-deriving.

No blockers for wave 3. The one open item is coverage D11 (a full, unrestricted `pytest -q` against a faster PostgreSQL instance) — recommended before shipping, not before continuing to wave 3's own db-tier plans.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-27*

## Self-Check: PASSED

All 16 claimed created/modified files verified present on disk; all five claimed commit hashes (`17e8c37`, `cb2f325`, `7489c5c`, `eb600ec`, `30c74ad`) verified present in `git log`.
