---
phase: quick-261031-jmw
plan: 01
subsystem: infra
tags: [github-actions, workflow_dispatch, settings, uv, pyproject, redaction]

requires: []
provides:
  - "src/dark_factory/webhook/ deleted entirely (app.py, resolve.py, __init__.py)"
  - "Settings.github_webhook_secret and Settings.dispatch_github_token removed"
  - "GitHubClient.dispatch_workflow and GitHubClient.for_dispatch removed"
  - "persistence/repositories.py's GitHubPendingInteraction / github_pending_interaction removed (D-01)"
  - "pyproject.toml's webhook optional-dependencies extra removed; uv.lock relocked"
  - "tests/unit/test_package_import_needs_no_database.py (renamed from test_webhook_import_needs_no_database.py) rescues the G-11-1 package-wide import guard"
  - "resume.yml reference templates (README.md + scripts/scaffold_target_repo.py) carry an optional answer workflow_dispatch input, bound through env: per D-03"
  - "README, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, docs/GETTING-STARTED.md, docs/CONFIGURATION.md, .env.example document exactly one resume path: manual gh workflow run dispatch"
affects: [github-integration, ci-cd, deployment-docs]

actuals:
  tokens: 53490
  tasks: 7
  commits: 8
  plan_head_before: 51a4cb92f5717b1a76e04f1247451f23b1006293

tech-stack:
  added: []
  patterns:
    - "Repoint a stale named-module regression-test constant at surviving modules rather than deleting the regression test entirely, when the original named modules are deleted by the same removal (documented deviation, Task 4)."

key-files:
  created: []
  modified:
    - src/dark_factory/config/settings.py
    - src/dark_factory/github/client.py
    - src/dark_factory/persistence/repositories.py
    - src/dark_factory/orchestrator/answers.py
    - pyproject.toml
    - uv.lock
    - README.md
    - docs/ARCHITECTURE.md
    - docs/DEVELOPMENT.md
    - docs/GETTING-STARTED.md
    - docs/CONFIGURATION.md
    - .env.example
    - scripts/scaffold_target_repo.py
    - tests/unit/test_package_import_needs_no_database.py (renamed)
    - tests/unit/test_resume_workflow_reference_doc.py
    - tests/conftest.py
    - tests/db/test_clarification_comment_is_redacted.py

key-decisions:
  - "D-01 (Q1=A): removed github_pending_interaction()/GitHubPendingInteraction from persistence/repositories.py — zero remaining callers after Task 1, enforcing the one-mutation-path / no-dead-surface discipline."
  - "D-02 (Q2=A): kept submit_answer(..., github_comment_id=None), reworded its docstring to drop the webhook-receiver framing while preserving the durable-dedup-key explanation — the human_interactions.github_comment_id column stays writable."
  - "D-03 (Q3=A): mirrored the proven-live app-int resume-step shape (env: RUN_ID/RUN_ANSWER bindings plus a shell if) instead of interpolating ${{ inputs.* }} directly — the standard hardening against expression injection from a workflow_dispatch input."
  - "Deviation (Task 4, undocumented by the plan's own action text): repointed test_package_import_needs_no_database.py's _G11_1_MODULES constant at three still-existing modules (test_settings.py, test_github_ownership_boundary.py, test_clarification_comment_is_redacted.py) since all three original G-11-1 regression modules were deleted in Task 1 — required for the renamed module's 'three passing tests' done criteria."

requirements-completed: [GIT-06, TRIG-01]

coverage:
  - id: D1
    description: "src/dark_factory/webhook/ deleted; nothing under src/ or tests/ imports it"
    verification:
      - kind: unit
        ref: "tests/unit/test_package_import_needs_no_database.py::test_every_dark_factory_module_imports_with_no_database_configured"
        status: pass
    human_judgment: false
  - id: D2
    description: "Settings declares neither github_webhook_secret nor dispatch_github_token; known_secret_values() byte-identical"
    verification:
      - kind: unit
        ref: "tests/unit/test_settings.py (full module)"
        status: pass
    human_judgment: false
  - id: D3
    description: "GitHubClient exposes neither dispatch_workflow nor for_dispatch; authenticated_login and every other method survive unchanged"
    verification:
      - kind: unit
        ref: "tests/unit/test_github_ownership_boundary.py::test_githubkit_is_imported_only_from_the_named_allowed_modules"
        status: pass
    human_judgment: false
  - id: D4
    description: "webhook optional extra gone from pyproject.toml; uv.lock relocked and uv sync --all-extras --dev --frozen succeeds"
    verification:
      - kind: other
        ref: "uv sync --all-extras --dev --frozen"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both shipped resume.yml templates declare an optional answer input, bound through env: per D-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py::test_the_reference_workflow_declares_an_optional_answer_input"
        status: pass
      - kind: other
        ref: "uv run python -c '...RESUME_WORKFLOW_TEMPLATE parses, declares run_id+answer...'"
        status: pass
    human_judgment: false
  - id: D6
    description: "README + four docs files + .env.example + scaffold script document exactly one resume path, no tombstone naming the removed subsystem"
    verification:
      - kind: other
        ref: "Task 7 tree sweep (src/ tests/ docs/ scripts/ .github/ README.md .env.example pyproject.toml uv.lock)"
        status: pass
    human_judgment: false
  - id: D7
    description: "dark-factory resume --answer behaviour unchanged (CLI path, submit_answer preconditions, lease, expected_status guard)"
    verification:
      - kind: integration
        ref: "tests/db/test_pause_path_atomic.py, tests/db/test_cross_machine_resume.py, tests/db/test_pause_mechanism_generic.py, tests/integration/test_redaction_interactions.py (collect-only verified, no DB reachable in this worktree)"
        status: unknown
    human_judgment: true
    rationale: "No DATABASE_URL reachable in this worktree; db tier could only be collect-only verified (224/1242 tests collect with zero errors), not executed against real PostgreSQL. A human/CI run with a reachable Neon/Postgres instance should execute `uv run pytest -q -m db` before shipping to confirm these four modules still pass for real."

duration: 46min
completed: 2026-10-31
status: complete
---

# Phase quick-261031-jmw Plan 01: Remove the webhook receiver subsystem Summary

**Deleted the entire `src/dark_factory/webhook/` ASGI receiver, its two `Settings` credentials, `GitHubClient`'s dispatch methods, and the `webhook` optional-dependency extra — replacing the automatic webhook-triggered CI resume with a single documented manual path: a human (or any script) runs `gh workflow run resume.yml -f run_id=<id> -f answer=<text>`.**

## Performance

- **Duration:** 46 min
- **Started:** 2026-10-31T12:37:51Z
- **Completed:** 2026-10-31T13:23:45Z
- **Tasks:** 7
- **Files modified:** ~30 (plus `uv.lock` relock)

## Accomplishments

- Deleted `src/dark_factory/webhook/` (the ASGI app, HMAC verification, inbound issue-comment resolver) and its six dedicated test modules plus `tests/support/webhook_events.py`.
- Removed `Settings.github_webhook_secret` / `Settings.dispatch_github_token`, `GitHubClient.dispatch_workflow` / `GitHubClient.for_dispatch`, and `persistence/repositories.py`'s `GitHubPendingInteraction` / `github_pending_interaction()` (D-01) — zero remaining callers, confirmed by grep after each removal.
- Kept `submit_answer`'s `github_comment_id` parameter with a reworded docstring (D-02) — the durable `human_interactions.github_comment_id` column stays writable from the one surviving caller, the CLI's `resume --answer`.
- Dropped the `webhook` optional-dependencies extra and relocked `uv.lock` (removal-only diff); `starlette`/`uvicorn` survive in the lock only because the unrelated `mcp` extra transitively depends on both.
- Rescued (renamed + narrowed, not deleted) the G-11-1 package-wide import guard `tests/unit/test_package_import_needs_no_database.py`, repointing its historical three-module regression list at modules that still exist.
- Added an optional `answer` input to both shipped `resume.yml` reference templates (README.md's sentinel block and `scripts/scaffold_target_repo.py`'s `RESUME_WORKFLOW_TEMPLATE`), binding `run_id`/`answer` through the resume step's `env:` block per D-03 — modelled on the proven-live `app-int` workflow.
- Rewrote README, four `docs/` files, `.env.example`, and the scaffold script to document exactly one resume path, with zero tombstone sentences naming the removed receiver.
- Whole-tree sweep found zero genuine references to the removed subsystem outside `.planning/`; full unit+contract tier is 826 passed, 0 failed.

## Task Commits

1. **Task 1: Delete the subsystem and its eight test modules end-to-end, unit tier green** - `00d9764` (feat)
2. **Task 2: Retire the two now-caller-less orchestration surfaces (D-01, D-02)** - `75ab64d` (feat)
3. **Task 3: Strip the two credential fields, the two client methods, and rewire every Settings consumer** - `7e9a09e` (feat)
4. **Task 4: Drop the webhook extra, relock, and rescue the package-wide import guard** - `09d3322` + `19efffd` (feat) — see Deviations: a multi-path `git add` with one bad pathspec aborted silently, so the rename-only diff landed in `09d3322` and the actual content edits landed in a follow-up `19efffd`
5. **Task 5: Add the answer input to both shipped resume.yml templates and retarget the doc guard** - `710454f` (feat, tdd)
6. **Task 6: Rewrite the documented resume flow across README, four docs files, and both env templates** - `9355e55` (docs)
7. **Task 7: Whole-tree sweep and full gate run** - `69abd57` (test)

**Plan metadata:** pending (orchestrator-managed docs commit)

## Files Created/Modified

- `src/dark_factory/config/settings.py` — removed the two credential fields and their docstring paragraphs
- `src/dark_factory/github/client.py` — removed `for_dispatch`/`dispatch_workflow`; reworded `authenticated_login`'s docstring
- `src/dark_factory/persistence/repositories.py` — removed `GitHubPendingInteraction`/`github_pending_interaction` (D-01)
- `src/dark_factory/orchestrator/answers.py` — reworded `submit_answer`'s docstring (D-02)
- `pyproject.toml` / `uv.lock` — dropped the `webhook` extra; relocked
- `README.md` / `docs/ARCHITECTURE.md` / `docs/DEVELOPMENT.md` / `docs/GETTING-STARTED.md` / `docs/CONFIGURATION.md` / `.env.example` / `scripts/scaffold_target_repo.py` — documented one resume path
- `tests/unit/test_package_import_needs_no_database.py` (renamed from `test_webhook_import_needs_no_database.py`) — narrowed to 3 tests, `_G11_1_MODULES` repointed
- `tests/unit/test_resume_workflow_reference_doc.py` — added the `answer`-input test, widened the exactly-once-resume test, deleted the dispatch-credential test
- `tests/conftest.py` / `tests/db/test_clarification_comment_is_redacted.py` / `tests/db/test_run_report.py` / `tests/db/test_artifacts_show_reads_committed_content.py` — re-sourced the known-value-redaction literal onto `anthropic_api_key`
- Deleted entirely: `src/dark_factory/webhook/{__init__.py,app.py,resolve.py}`, `tests/unit/test_webhook_process_boundary.py`, `tests/unit/test_webhook_signature.py`, `tests/unit/test_webhook_resolve.py`, `tests/unit/test_dispatch_token_never_reaches_a_worker.py`, `tests/db/test_webhook_dispatches_resume.py`, `tests/db/test_webhook_resolves_answer.py`, `tests/support/webhook_events.py`

## Decisions Made

- D-01/D-02/D-03 were resolved as Q1=A, Q2=A, Q3=A by the developer before execution (recorded in the plan's `<decisions_resolved>`); each was implemented exactly as stated — see `key-decisions` in the frontmatter.
- The eight investigation findings in the plan materially changed the task descriptions' own picture of the work; two stood out during execution:
  - **Finding 7** — the `answer` workflow input did not exist anywhere in this repository (only in the hand-edited `app-int` copy); documenting the manual `gh workflow run ... -f answer=<text>` command without adding the input would have shipped a command that could not work. Task 5 added it to both templates.
  - **Finding 1** — the package-wide import guard (`test_webhook_import_needs_no_database.py`) was rescued (renamed + narrowed), not deleted, to preserve the G-11-1 regression coverage for the entire package, not just the webhook package.
- GIT-06 is deliberately retired by this removal. `.planning/milestones/v1.0-REQUIREMENTS.md` still records it Complete — that archived milestone artifact is a historical record this task does not rewrite (plan's explicit scope boundary).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — plan verify/scope conflict] Task 1's own `<verify>` gate could not pass without Task 4's work**
- **Found during:** Task 1
- **Issue:** Task 1's action text explicitly instructs "Do NOT delete `tests/unit/test_webhook_import_needs_no_database.py` in this task — Task 4 renames and narrows it," yet Task 1's own `<verify>` (`uv run pytest -q -m unit`) and `<done>` both require the full unit tier to pass. That file's `_G11_1_MODULES` constant names three test files Task 1 deletes, and one of its own tests imports `dark_factory.webhook.app` directly — both guaranteed to fail the moment the webhook package and its three named test modules are gone, which the plan's own Finding 1 explicitly anticipated and deferred to Task 4.
- **Fix:** Verified the only 3 failing tests after Task 1 were exactly the ones Finding 1 named as deferred (`test_g11_1_modules_collect_with_no_database_configured`, `test_webhook_app_module_exposes_only_the_build_app_factory`, and their cascading dependent in `test_unit_tier_needs_no_database.py`), confirmed 828-830 passed otherwise, and proceeded to Task 2 rather than halting the whole plan or doing Task 4's work early (which would have violated Task 1's explicit file-scope boundary). Fully resolved by Task 4 — full unit tier was 800/800 (later 826/826) passed with zero failures afterward.
- **Files modified:** none beyond Task 1's own scope
- **Verification:** `uv run pytest -q -m unit` after Task 4: 800 passed, 0 failed
- **Committed in:** `00d9764` (Task 1), resolved in `19efffd` (Task 4)

**2. [Rule 3 — blocking issue, auto-fixed] A failed multi-path `git add` silently split Task 4's commit in two**
- **Found during:** Task 4
- **Issue:** A `git add` call listing six paths (one of which did not exist — `git mv`'s source path, already gone) failed the whole command with "fatal: pathspec ... did not match any files," which aborted staging of every path in that call, not just the bad one. The subsequent `git commit` therefore captured only the already-staged `git mv` (a 100%-identical rename, 0 insertions/0 deletions) — all the actual content edits (docstring rewrite, `_G11_1_MODULES` repoint, deleted test, pyproject.toml, relocked uv.lock, and the two sibling test-file prose updates) were left unstaged.
- **Fix:** Staged and committed the remaining content changes in an immediate follow-up commit (`19efffd`) on the same task, with a commit message explaining the split.
- **Files modified:** none beyond Task 4's own scope
- **Verification:** `git status --short` clean after the follow-up commit; `git show --stat` on both commits together accounts for every Task 4 edit
- **Committed in:** `09d3322` (rename only) + `19efffd` (content)

**3. [Rule 1 — bug, auto-fixed] `_G11_1_MODULES` would have pointed at zero existing files**
- **Found during:** Task 4
- **Issue:** The plan's own Task 4 action text says to rename the file, delete one webhook-specific test, and "keep all three remaining tests unchanged" — but does not mention that `_G11_1_MODULES` (a tuple of three hardcoded file paths) names exactly the three test modules Task 1 deletes. Left as-is, `test_g11_1_modules_collect_with_no_database_configured` would fail permanently (`file or directory not found`), and the renamed module's own done criteria ("three passing tests") could not be satisfied.
- **Fix:** Repointed `_G11_1_MODULES` at three modules that still exist and still exercise real pytest collection against `dark_factory.config.settings` (`test_settings.py`, `test_github_ownership_boundary.py`, `test_clarification_comment_is_redacted.py`), documented inline as a deviation.
- **Files modified:** `tests/unit/test_package_import_needs_no_database.py`
- **Verification:** `uv run pytest -q tests/unit/test_package_import_needs_no_database.py` — 3 passed
- **Committed in:** `19efffd`

**4. [Rule 1 — bug, auto-fixed] Stale `dispatch_workflow` reference surfaced by Task 7's own sweep**
- **Found during:** Task 7
- **Issue:** `test_the_reference_workflow_declares_a_run_id_input`'s assertion message named "plan 11-01's `dispatch_workflow`" (a GitHubClient method deleted in Task 3) as the sender of the `run_id` input — stale after Task 5/6 moved that input's sender to a human `gh workflow run` command.
- **Fix:** Reworded the assertion message to cite the documented `gh workflow run resume.yml -f run_id=<id>` command instead.
- **Files modified:** `tests/unit/test_resume_workflow_reference_doc.py`
- **Verification:** `uv run pytest -q tests/unit/test_resume_workflow_reference_doc.py` — 14 passed; tree sweep re-run clean of this reference
- **Committed in:** `69abd57`

---

**Total deviations:** 4 (1 plan-verify-gate sequencing conflict, 1 git-add/commit-split, 2 bugs)
**Impact on plan:** All four were necessary to reach the plan's own stated done criteria without violating any task's explicit file-scope boundary. No scope creep — every fix stayed inside the file set the plan already named for that task (or, for #2, split an already-in-scope change across two commits rather than touching anything new).

## Issues Encountered

- No `DATABASE_URL` is reachable in this isolated worktree (no `.env` file present). Per the plan's own Task 7 instructions, ran `uv run pytest -q -m db --collect-only` as the documented substitute: 224/1242 db-tier tests collect with zero errors, including all 20 tests across the three Task-3-rewired modules (`test_clarification_comment_is_redacted.py`, `test_run_report.py`, `test_artifacts_show_reads_committed_content.py`). The db tier itself was **not executed** against a real PostgreSQL instance in this run — see coverage item D7 and the rationale there. A follow-up run with a reachable Neon/Postgres connection should execute `uv run pytest -q -m db` before this change ships to a production branch.

## User Setup Required

None — no external service configuration required. (This removal *reduces* required configuration: deployers no longer need to provision `DISPATCH_GITHUB_TOKEN` or `GITHUB_WEBHOOK_SECRET`, or host a separate webhook receiver process.)

## Next Phase Readiness

- The webhook receiver subsystem is fully removed with no remaining code, test, or documentation references outside `.planning/`'s historical record.
- The answer-submission capability (`human_interactions`, `submit_answer`, `dark-factory resume --answer`) is behaviourally unchanged and still covered by its existing db-tier test suite.
- Outstanding: the db tier should be executed against a real PostgreSQL instance (not just collect-only) before this removal ships, to close out coverage item D7 above.
- The separate, not-yet-started `GITHUB_TOKEN`-rename task (Finding 8) remains untouched and out of scope, as the plan specified.

---
*Phase: quick-261031-jmw*
*Completed: 2026-10-31*

## Self-Check: PASSED

All 17 files referenced in this SUMMARY were verified present on disk (including `src/dark_factory/webhook/` confirmed absent), and all 8 task/content commit hashes (`00d9764`, `75ab64d`, `7e9a09e`, `09d3322`, `19efffd`, `710454f`, `9355e55`, `69abd57`) were verified present in `git log --oneline --all`. No missing items.
