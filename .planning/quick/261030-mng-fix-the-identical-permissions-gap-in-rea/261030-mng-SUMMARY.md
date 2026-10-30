---
phase: quick
plan: 261030-mng
subsystem: docs
tags: [github-actions, permissions, resume-workflow, readme]

requires:
  - phase: quick-261030-mcz
    provides: the identically-fixed scripts/scaffold_target_repo.py templates (key order + verbatim YAML comment this plan copies)
provides:
  - README.md's resume-workflow-reference sentinel block now declares contents/issues/pull-requests write, matching the scaffold-generated workflows
affects: [readme, resume-workflow-doc]

actuals:
  tokens: 1159
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - tests/unit/test_resume_workflow_reference_doc.py
    - README.md

key-decisions:
  - "Guard asserts whole-mapping equality (not per-key containment) so a later over-widening (e.g. a stray actions: write) fails the same guard that catches today's under-scoping"
  - "New prose paragraph inserted between the pre-existing contents:write and fetch-depth:0 paragraphs, both left byte-identical; forward-references '### The dispatch credential' rather than re-explaining actions: write"

requirements-completed: [QUICK-MNG]

coverage:
  - id: D1
    description: "README's resume-workflow-reference sentinel block grants contents/issues/pull-requests write (matching the scaffold script's already-fixed templates)"
    requirement: "QUICK-MNG"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py#test_the_reference_workflow_grants_exactly_the_needed_permissions"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-10-30
status: complete
---

# Quick Task 261030-mng Summary

**Closed the README path's permissions gap: the hand-copyable resume.yml reference now grants `issues: write` and `pull-requests: write` alongside `contents: write`, with a bidirectional exact-mapping test guarding against both under- and over-scoping.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-30T14:24:06Z
- **Completed:** 2026-10-30T14:28:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `test_the_reference_workflow_grants_exactly_the_needed_permissions` — a whole-mapping equality assertion (not containment) that fails on under-scoping, over-scoping (including a stray `actions: write`), a `write-all` collapse, or an absent `permissions` key
- Extended the README's `resume-workflow-reference` sentinel block to declare `contents`, `issues`, and `pull-requests`, each `write`, with the same explanatory YAML comment the already-fixed `scripts/scaffold_target_repo.py` templates carry — so the two deployment paths (scaffold script vs. hand-copied README block) now read identically
- Added a new reasoning paragraph explaining the two added scopes (issues → `ROLE_NEEDS_INPUT`/`WAITING_HUMAN` clarification comment; pull-requests → the post-QA-PASS/Quality-Gate-PASS PR) and the deliberate `actions` omission, forward-referencing "The dispatch credential" subsection instead of duplicating it
- Confirmed the pre-existing `contents: write` / `persist-credentials` / `fetch-depth: 0` reasoning paragraphs are byte-identical before and after (verified via `git diff`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add an exact-mapping permissions guard to the reference-workflow doc test (RED)** - `f5863fa` (test)
2. **Task 2: Grant issues and pull-requests write inside the sentinel block and extend its reasoning prose (GREEN)** - `dadcfe1` (docs)

_Plan metadata commit deferred to the orchestrator per constraints._

## Files Created/Modified
- `tests/unit/test_resume_workflow_reference_doc.py` - Added `_EXPECTED_PERMISSIONS` module constant and `test_the_reference_workflow_grants_exactly_the_needed_permissions`
- `README.md` - Extended the sentinel block's `permissions:` key to three entries plus its explanatory comment; added one new reasoning paragraph

## Decisions Made
- Asserted the permissions mapping via whole-equality rather than per-key containment, matching the plan's explicit reasoning: containment would catch today's under-scoping but silently tolerate a later widening, which is the more dangerous direction for a credential block a deployer copies verbatim.
- Kept the new prose paragraph strictly additive — inserted between two existing paragraphs, neither of which was touched — to preserve every load-bearing phrase (`persist-credentials`, the two ordered failure modes, `fetch-depth: 0` / merge-base reasoning) verbatim.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' `<verify>` and `<done>` criteria were met without any Rule 1-4 fixes.

## Issues Encountered

None. The only operational wrinkle was tool-path isolation: Read/Edit/Write calls had to target the worktree-prefixed absolute path (`.../.claude/worktrees/agent-ad6b15d929a173d41/...`) rather than the bare repo-root path, per the sandbox's worktree-isolation guard. No production impact.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The README and `scripts/scaffold_target_repo.py` paths now agree on the permission scopes and explain them in the same words — 261030-mcz's unresolved finding (option (a)) is closed.
- `tests/unit/test_resume_workflow_reference_doc.py` is green at 14 passed (up from the 13-passed baseline); the new guard fails loudly on any future under- or over-scoping of this block.
- No blockers for subsequent work.

---
*Phase: quick*
*Completed: 2026-10-30*

## Self-Check: PASSED

- FOUND: tests/unit/test_resume_workflow_reference_doc.py
- FOUND: README.md
- FOUND: .planning/quick/261030-mng-fix-the-identical-permissions-gap-in-rea/261030-mng-SUMMARY.md
- FOUND: commit f5863fa
- FOUND: commit dadcfe1
