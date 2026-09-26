---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 01
subsystem: intake
tags: [githubkit, github-api, config, source-loader, pydantic]
requires:
  - phase: 04-the-four-role-pipeline-artifact-handoffs
    provides: "the `{SourceKind: loader}` dispatch pattern (`_load_spec`'s validate-then-build shape) this plan's `_load_github` mirrors exactly"
provides:
  - "The one `githubkit` wrapper (`dark_factory.github.client.GitHubClient`): `fetch_issue`, `create_comment`, `create_pull_request`, `find_pull_request_for_branch`, all four written complete and contract-tested against a stubbed SDK client"
  - "A typed error hierarchy (`GitHubError` / `GitHubApiError` / `MissingGitHubCredentialError`) with redact-before-raise discipline"
  - "`RepositoryConfig.github_owner` / `github_repo` and `Settings.github_webhook_secret` config surfaces (D-04)"
  - "A real `_load_github` loader building a `NormalizedTask` from a GitHub issue, wired through `load`'s new optional `repository` keyword"
  - "`FakeGitHubClient` test double, complete for every later Phase 10 plan"
  - "The `githubkit` runtime dependency and the `webhook` optional extra (starlette + uvicorn), both declared in this plan's single `uv.lock` regeneration"
affects: [10-02, 10-03, 10-04, 10-06]
actuals:
  tokens: 23754
  tasks: 3
  commits: 4
tech-stack:
  added: ["githubkit>=0.16,<0.17", "starlette>=0.42,<1 (optional extra, unused this plan)", "uvicorn>=0.34,<1 (optional extra, unused this plan)"]
  patterns:
    - "One wrapper per external system: dark_factory.github.client is the only module that constructs a githubkit client (grep-verified)"
    - "redact-before-raise on every GitHubApiError message, mirroring push_working_branch's defense-in-depth"
    - "validate-then-fetch loader shape (_load_spec's precedent): locator format checked, then repository config checked, before any network call"
key-files:
  created:
    - src/dark_factory/github/__init__.py
    - src/dark_factory/github/client.py
    - tests/support/fake_github.py
    - tests/unit/test_github_client.py
    - tests/unit/test_load_github.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/dark_factory/config/repo_config.py
    - src/dark_factory/config/settings.py
    - src/dark_factory/input/loaders.py
    - tests/unit/test_loaders.py
    - tests/unit/test_repo_config_schema.py
    - tests/unit/test_settings.py
    - tests/integration/test_unsupported_source.py
key-decisions:
  - "Task 1 checkpoint: approved installing githubkit>=0.16,<0.17 despite the package-legitimacy audit's SUS flag -- the flag was driven only by unknown-downloads (no download-count signal in this environment's registry lookup), with no other red flag on record (active repo, no postinstall script, name matches the project's own locked tech-stack decision)."
  - "Task 2 checkpoint: selected option A1 -- source_ref = \"{owner}/{repo}#{issue_number}\" and metadata = {owner, repo, issue_number, labels, comment_count}. Human-legible in run listings, the resolver (plan 10-04) queries three typed metadata fields with no string parsing, and labels ride in metadata where INTAKE-03 wants them with no new column."
  - "webhook optional extra pinned to starlette>=0.42,<1 + uvicorn>=0.34,<1: Starlette is the smallest surface giving exact raw-request-body access (await request.body()), which the webhook HMAC signature check (plan 10-04) requires; it ships an in-process TestClient on httpx (already a githubkit dependency); it lets the route stay effectively synchronous via starlette.concurrency.run_in_threadpool for DB calls."
patterns-established:
  - "GitHubClient models (GitHubIssue/GitHubComment/GitHubPullRequest) are the wrapper's own frozen pydantic types -- no githubkit SDK type ever escapes github/client.py, keeping D-03 reversible."
  - "Every GitHubApiError message passes through dark_factory.events.redaction.redact with the constructing Settings' known_secret_values() (or a token-only fallback when built via the bare token constructor) before it is raised."
requirements-completed: [INTAKE-03, GIT-06]
coverage:
  - id: D1
    description: "GitHubClient wraps the real githubkit 0.16.1 API: fetch_issue (paginated comments via rest.paginate), create_comment, create_pull_request, find_pull_request_for_branch (read-only)"
    requirement: INTAKE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_github_client.py (18 tests: happy path, 2-page comment pagination, null-body mapping, missing-issue -> GitHubApiError not raw SDK exception, secret redaction, create_pull_request passthrough, find_pull_request_for_branch match/no-match + read-only assertion)"
        status: pass
    human_judgment: false
  - id: D2
    description: "MissingGitHubCredentialError raised at the single from_settings unwrap frame when Settings.github_token is None; no AttributeError-on-None failure mode"
    requirement: INTAKE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_github_client.py::test_from_settings_with_no_github_token_raises_missing_credential_error"
        status: pass
    human_judgment: false
  - id: D3
    description: "_load_github builds a NormalizedTask from a GitHub issue: title/body/every-comment/labels, source_ref and metadata per the Task 2 A1 decision, empty-issue and non-ASCII/truncation edges, directive-shaped-text-as-data proof"
    requirement: INTAKE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_load_github.py (13 tests covering the full <behavior> list for the loader)"
        status: pass
    human_judgment: false
  - id: D4
    description: "load's repository keyword is optional and keyword-only; the two pre-existing loaders (text:, spec:) are unchanged"
    requirement: INTAKE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_loaders.py::test_text_and_spec_loaders_still_work_with_no_repository_argument, test_loader_mapping_covers_every_source_kind"
        status: pass
    human_judgment: false
  - id: D5
    description: "RepositoryConfig.github_owner/github_repo and Settings.github_webhook_secret exist with extra=\"forbid\" / SecretStr shapes; the webhook secret is covered by known_secret_values() with zero additional code"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py (round-trip + typo rejection), tests/unit/test_settings.py (default-None + known_secret_values coverage)"
        status: pass
    human_judgment: false
  - id: D6
    description: "githubkit runtime dependency and webhook optional extra declared in pyproject.toml; uv.lock regenerated exactly once for the phase; grep -rl githubkit src/dark_factory returns exactly github/client.py"
    requirement: GIT-06
    verification:
      - kind: manual
        ref: "grep -rl githubkit src/dark_factory (returned exactly src/dark_factory/github/client.py); uv run python -c \"import githubkit\" succeeds"
        status: pass
    human_judgment: false
  - id: D7
    description: "Live smoke test of _load_github against a real GitHub issue (the precondition's stated purpose)"
    verification: []
    human_judgment: true
    rationale: "GITHUB_TOKEN is absent from both the shell environment and Settings' .env-backed resolution in this environment (confirmed via get_settings().github_token is None, a read-only check that reports presence/absence only, never a value). The plan's own precondition text states the unit tier -- which is what this task's <verify>/<acceptance_criteria> actually gate -- 'needs neither the token nor the network', so the live smoke was skipped as a disclosed gap rather than blocking the whole task; a human with a configured GITHUB_TOKEN should run a live fetch_issue call against a real issue before this loader is trusted end-to-end."
duration: ~55min
completed: 2026-09-26
status: complete
---

# Phase 10 Plan 01: GitHub Wrapper, Config Surfaces, and Real Issue Loader Summary

The one `githubkit` wrapper, its typed errors, two new config fields, and a real `_load_github` that turns a GitHub issue into a `NormalizedTask` carrying its title, body, every paginated comment, and label names.

## Performance
- **Duration:** ~55min (across three dispatches: initial execution to Task 1's checkpoint, continuation through Task 2's checkpoint, continuation through Task 3's full implementation)
- **Started:** 2026-09-26 (session start)
- **Completed:** 2026-09-26T16:29:11Z
- **Tasks:** 3/3 (Task 1 checkpoint approved, Task 2 checkpoint decided A1, Task 3 tracer implemented)
- **Files modified:** 14

## Accomplishments
- `GitHubClient` (`src/dark_factory/github/client.py`) wraps the real `githubkit` 0.16.1 REST surface: `fetch_issue` (fully paginated comment read via `rest.paginate`), `create_comment`, `create_pull_request`, `find_pull_request_for_branch` (read-only, issues no write)
- Resolved 10-RESEARCH.md Assumptions A1/A2 by introspecting the installed package before writing any call site: every researched method/parameter name (`rest.issues.get`, `rest.issues.list_comments`, `rest.issues.create_comment`, `rest.pulls.create`, `rest.pulls.list`) matched exactly, no divergence. One detail the research didn't call out: `GitHub.paginate` (the top-level helper) is deprecated in 0.16.1 in favor of `rest.paginate(request_fn, **kwargs)`, which is what this wrapper uses.
- Typed error hierarchy (`GitHubError` / `GitHubApiError` / `MissingGitHubCredentialError`) declared in `github/__init__.py`, mirroring `dark_factory.git`'s structure; every `GitHubApiError` message passes through `redact()` before it is raised
- `RepositoryConfig.github_owner` / `github_repo` and `Settings.github_webhook_secret` added (D-04); both default to `None`/absent so no existing config needs to change
- `_load_github` implemented: validates a positive-integer locator and a `repository` mapping carrying non-empty `github_owner`/`github_repo` before any network call, then builds the `NormalizedTask` per the Task 2 A1 decision
- `pyproject.toml` gained the `githubkit` runtime dependency and the `webhook` optional extra (`starlette>=0.42,<1`, `uvicorn>=0.34,<1`) in one `uv.lock` regeneration -- the phase's only lock edit
- `FakeGitHubClient` (`tests/support/fake_github.py`) built complete for plans 10-02, 10-03, 10-04 and 10-06 to reuse without modification

## Task Commits
1. **Task 1: Verify the `githubkit` package is legitimate before it is installed** (checkpoint, approved) - `e97eeb5` (feat) -- `uv add "githubkit>=0.16,<0.17"` plus the `webhook` extra, one `uv.lock` regeneration
2. **Task 2: Fix how a GitHub-sourced run records which issue it came from** (checkpoint, decided A1) -- no code, decision recorded and applied in Task 3
3. **Task 3: A GitHub issue becomes a NormalizedTask** (tracer, tdd) -- `3d6e780` (test, RED), `3786f59` (feat, GREEN)
4. Deviation fix -- `46222d1` (fix) -- `tests/integration/test_unsupported_source.py` updated for the now-real `github:` loader

## Files Created/Modified
- `src/dark_factory/github/__init__.py` -- typed error hierarchy (`GitHubError`, `GitHubApiError`, `MissingGitHubCredentialError`)
- `src/dark_factory/github/client.py` -- `GitHubClient` wrapper, `GitHubIssue`/`GitHubComment`/`GitHubPullRequest` frozen models
- `src/dark_factory/config/repo_config.py` -- `RepositoryConfig.github_owner`/`github_repo`
- `src/dark_factory/config/settings.py` -- `Settings.github_webhook_secret`
- `src/dark_factory/input/loaders.py` -- real `_load_github`, `load`'s optional `repository` keyword, `_Loader` Protocol
- `tests/support/fake_github.py` -- `FakeGitHubClient` double
- `tests/unit/test_github_client.py` -- wrapper unit coverage against a stubbed SDK client
- `tests/unit/test_load_github.py` -- loader unit coverage against `FakeGitHubClient`
- `tests/unit/test_loaders.py`, `tests/unit/test_repo_config_schema.py`, `tests/unit/test_settings.py` -- extended for the new surfaces
- `tests/integration/test_unsupported_source.py` -- updated `github:152` expectation (Rule 1 fix)
- `pyproject.toml`, `uv.lock` -- `githubkit` dependency, `webhook` optional extra

## Decisions Made
See `key-decisions` in frontmatter: Task 1 (install approved), Task 2 (option A1 selected for `source_ref`/`metadata` shape), webhook extra framework choice (Starlette + uvicorn).

## Deviations from Plan

**1. [Rule 1 - Bug] `tests/integration/test_unsupported_source.py`'s `github:152` case updated**
- **Found during:** Task 3, after implementing `_load_github`
- **Issue:** This pre-existing integration test asserted `github:152` exits 2 with `"Phase 10"` in stderr (the old `SourceNotSupportedError` message). Once `_load_github` became real, the CLI's `start_run` (unchanged by this plan -- its `repository`-threading wiring lands in plan 10-06) still calls `load(kind, locator)` with no `repository` argument, so the loader now raises `UnresolvableSourceError` naming the missing repository config instead. The test's literal stderr assertion would fail.
- **Fix:** Updated the test's parametrization and assertion to check for `"repository"` in stderr instead of `"Phase 10"`, and renamed the test function to describe the new, correct reason. The invariant the test protects (exit 2, nothing persisted, before any run row is created) is unchanged and still proven -- just for the accurate current reason.
- **Files modified:** `tests/integration/test_unsupported_source.py`
- **Verification:** Python syntax check (`ast.parse`), `ruff check`/`ruff format --check` both clean. NOT executed against real PostgreSQL in this environment -- this test is `integration`-tier (needs `pg_url`/`engine` fixtures), outside this plan's own `<verify>` block (`unit or contract` only). A human with real PostgreSQL should re-run `pytest -m integration tests/integration/test_unsupported_source.py` to confirm GREEN.
- **Committed in:** `46222d1`
---
**Total deviations:** 1 auto-fixed (1 Rule 1).
**Impact on plan:** Low -- test-only change, preserves the exact behavioral contract the test protects, just corrects the assertion to match `_load_github`'s new real behavior.

## Issues Encountered
None beyond the deviation above. `githubkit`'s installed 0.16.1 surface matched 10-RESEARCH.md's inferred names exactly (verified by introspection before any call site was written, per the plan's own instruction) -- the one genuine new fact discovered was that `GitHub.paginate` is deprecated in favor of `rest.paginate`, which this wrapper uses.

## User Setup Required

**GITHUB_TOKEN is not yet configured in this environment.** The plan's `user_setup` block calls for a GitHub personal access token with read access to issues and write access to pull requests on the target repository. The unit tier (which this plan's `<verify>`/`<acceptance_criteria>` actually gate) runs entirely against `FakeGitHubClient` and a stubbed SDK object and needed neither the token nor the network, so this did not block Task 3's completion -- but the plan's precondition text also names an optional live smoke test against a real issue, which was not performed. Before trusting this loader against a real repository:
1. Set `GITHUB_TOKEN` in `.env` or the environment (a PAT with `repo` scope, or fine-grained equivalent).
2. Set `repository.github_owner` / `repository.github_repo` in the target repo's `.dark-factory.yaml`.
3. Run a live smoke: `uv run python -c "from dark_factory.github.client import GitHubClient; from dark_factory.config.settings import get_settings; c = GitHubClient.from_settings(get_settings()); print(c.fetch_issue('<owner>', '<repo>', issue_number=<n>))"` against a real issue.

This is tracked as coverage item D7 (`human_judgment: true`) above.

## Next Phase Readiness
`10-01-SUMMARY.md` (this file) is read by plans 10-02, 10-03, 10-04 and 10-06 for the confirmed `githubkit` method/parameter names and the A1 `source_ref`/`metadata` shape before they write their own call sites. `GitHubClient`'s full four-method surface and `FakeGitHubClient` are ready for reuse with no further modification. Plan 10-06 (wave 2) is next: migration 0006's persisted identifiers, the `EventType` additions, `PublishFieldsWrite`, `orchestrator/publish.py`, and the `runner.py` wiring that threads `repository` into `start_run`'s `load()` call -- which is also what will let `github:<n>` actually succeed end-to-end via the CLI (today it still exits 2 for lack of that wiring, proven in the updated `test_unsupported_source.py`).

No blockers for wave 2.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-26*

## Self-Check: PASSED

All claimed created files verified present on disk; all four claimed commit hashes (`e97eeb5`, `3d6e780`, `3786f59`, `46222d1`) verified present in `git log`.
