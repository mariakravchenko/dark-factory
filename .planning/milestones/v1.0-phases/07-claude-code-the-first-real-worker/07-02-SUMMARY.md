---
phase: 07-claude-code-the-first-real-worker
plan: 02
subsystem: ci
tags: [github-actions, ci, uv, ruff, mypy, pytest, quality-gate]

requires:
  - phase: 06-tool-execution-and-capability-boundaries
    provides: a stable src/dark_factory tree with lint/type/unit tiers already green
provides:
  - .github/workflows/ci.yml, a GitHub Actions `quality` job that fails the build on lint, type, worker-name leak, or unit/contract test failures
  - tests/unit/test_ci_enforces_worker_name_guard.py, a structural guard-on-the-guard so the CI wiring cannot be silently defanged
affects: [08-copilot-and-hermes-worker-independence]

actuals:
  tokens: 1446
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "GitHub Actions workflow authored and structurally verified via `yaml.safe_load` before any GitHub remote exists (precondition deferred to user_setup, not blocking)"
    - "Structural CI-wiring guard follows the repo's established 'AST/parse-based structural guard as a unit test' style (module constant path, pure `_offenders(document) -> list[str]` helper, a sanity test proving the guard detects its own subject)"

key-files:
  created:
    - .github/workflows/ci.yml
    - tests/unit/test_ci_enforces_worker_name_guard.py
    - .planning/phases/07-claude-code-the-first-real-worker/07-USER-SETUP.md
  modified: []

key-decisions:
  - "Quoted the `on:` workflow key as `\"on\":` in YAML — PyYAML (YAML 1.1) parses a bare `on:` key as the boolean `True`, which would make `document['on']` raise `KeyError` in both the plan's own verify command and the Task 2 structural guard. Quoting is the standard GitHub Actions workaround and is fully equivalent for GitHub's own YAML parser."
  - "TDD RED anchor was the guard's self-detection sanity test, not the main assertion — a stub `_offenders()` that always returns `[]` still passes the main 'no offenders' assertion trivially (an already-compliant workflow), so the meaningful failing assertion for RED was `test_the_guard_detects_its_own_subject` (which requires the stub to actually report a removed step)."

requirements-completed: [QUAL-04]

coverage:
  - id: D1
    description: "A CI workflow exists (.github/workflows/ci.yml) whose failure is a build failure, gating on lint, mypy, the worker-name leak guard, and the unit/contract test tiers"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ci_enforces_worker_name_guard.py::test_ci_workflow_gates_on_worker_name_guard"
        status: pass
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py"
        status: pass
      - kind: other
        ref: "uv run python -c \"yaml.safe_load(...)\" structural assertions (plan Task 1 <verify>)"
        status: pass
    human_judgment: true
    rationale: "The workflow is authored and structurally verified locally (YAML parses, four named steps present, all plan-level and task-level <verify> commands green), but no GitHub Actions run has actually executed yet -- git remote -v is empty for this working copy (07-RESEARCH.md's documented gap). A human must push to a GitHub remote (see 07-USER-SETUP.md) before an actual build can be observed to pass or fail."
  - id: D2
    description: "The CI wiring cannot be silently removed -- deleting or defanging the leak-guard step, a trigger, or the marker exclusion is caught by the local test suite"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ci_enforces_worker_name_guard.py::test_the_guard_detects_its_own_subject"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-20
status: complete
---

# Phase 07 Plan 02: CI Pipeline + Guard-on-the-Guard Summary

**First GitHub Actions workflow in the repo (`quality` job: ruff, mypy, worker-name leak guard, unit/contract tests) plus a structural unit test proving the leak-guard wiring itself cannot be silently removed.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-20T18:06:53Z
- **Completed:** 2026-09-20T18:12:07Z
- **Tasks:** 2
- **Files modified:** 2 (created)

## Accomplishments
- `.github/workflows/ci.yml`: a `quality` job on `ubuntu-latest` (15 min timeout) that installs `uv`, pins Python 3.12, runs `uv sync --all-extras --dev --frozen`, then four separately-named blocking steps — `Lint (ruff)`, `Types (mypy)`, `Worker-name leak guard (QUAL-04)`, and `Unit and contract tiers` — triggered on both `push` and `pull_request`, with `permissions: contents: read` and a `cancel-in-progress` concurrency group.
- `tests/unit/test_ci_enforces_worker_name_guard.py`: a pure `_offenders(document: dict) -> list[str]` helper plus two tests — one asserting the real workflow has no offenses, and a sanity test (`test_the_guard_detects_its_own_subject`) that deep-copies the loaded workflow, drops the leak-guard step, and asserts the helper reports it — proving the guard can actually detect its own subject.
- `07-USER-SETUP.md`: documents the one manual step remaining — creating a GitHub remote and pushing, so the authored-and-locally-verified workflow can actually execute for the first time.

## Task Commits

Each task was committed atomically (Task 2 used the full RED → GREEN TDD cycle; no REFACTOR commit was needed):

1. **Task 1: A CI build exists, and it runs the worker-name leak guard** - `a6f1f06` (feat)
2. **Task 2 RED: failing test for CI leak-guard wiring detection** - `1a51947` (test)
3. **Task 2 GREEN: implement CI wiring guard-on-the-guard** - `77c2a9a` (feat)

## Files Created/Modified
- `.github/workflows/ci.yml` - The repo's first CI pipeline: lint, types, worker-name leak guard, unit/contract tests.
- `tests/unit/test_ci_enforces_worker_name_guard.py` - Structural proof that the CI wiring gates on the leak guard and cannot be silently defanged.
- `.planning/phases/07-claude-code-the-first-real-worker/07-USER-SETUP.md` - The one remaining manual step (create GitHub remote, push, confirm Actions runs).

## Decisions Made
- Quoted `"on":` instead of bare `on:` in the workflow YAML — PyYAML (YAML 1.1 spec) parses a bare `on` key as the boolean `True`, which breaks `document['on']` lookups in both the plan's own verify command and the Task 2 structural guard. GitHub's own workflow parser treats the quoted and unquoted forms identically, so this has zero effect on the workflow's actual behavior on GitHub Actions.
- For the TDD RED phase, the meaningful failing assertion was the guard's self-detection sanity test rather than the "workflow has no offenders" main test — a stub implementation that always returns an empty offender list trivially satisfies "the already-compliant real workflow has no offenders," so RED had to target the assertion that actually exercises the guard's detection logic (removing the leak-guard step and expecting a non-empty result).

## Deviations from Plan

None - plan executed exactly as written. The YAML key-quoting choice was an implementation detail necessary to satisfy the plan's own stated acceptance criteria (`document['on']` must resolve to a mapping containing both trigger keys) against PyYAML's YAML 1.1 parsing behavior — not a deviation from the plan's intent.

## Issues Encountered
None.

## User Setup Required

**External service (GitHub) requires manual configuration.** See [07-USER-SETUP.md](./07-USER-SETUP.md) for:
- Creating the GitHub repository and adding it as `origin`
- Pushing the current branch so GitHub Actions can execute the workflow for the first time
- Confirming the `ci` workflow appears and its four steps go green in the Actions tab

## Next Phase Readiness
- ROADMAP SC4 is now structurally satisfied: the worker-name leak guard is a named, blocking CI step, and its removal is caught by a local test.
- No blockers for continuing to 07-03 (Claude Code resume/capabilities) or 07-04. The actual GitHub Actions run itself remains pending human setup (07-USER-SETUP.md) — this does not block further phase execution, only the "observed green build" human check deferred to `/gsd-verify-work`.

---
*Phase: 07-claude-code-the-first-real-worker*
*Completed: 2026-09-20*

## Self-Check: PASSED

- FOUND: `.github/workflows/ci.yml`
- FOUND: `tests/unit/test_ci_enforces_worker_name_guard.py`
- FOUND: `.planning/phases/07-claude-code-the-first-real-worker/07-02-SUMMARY.md`
- FOUND commit: `a6f1f06` (Task 1)
- FOUND commit: `1a51947` (Task 2 RED)
- FOUND commit: `77c2a9a` (Task 2 GREEN)
