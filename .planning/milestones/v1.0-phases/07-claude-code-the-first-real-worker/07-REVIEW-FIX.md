---
phase: 07-claude-code-the-first-real-worker
fixed_at: 2026-09-20T00:00:00Z
review_path: .planning/phases/07-claude-code-the-first-real-worker/07-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 7: Code Review Fix Report

**Fixed at:** 2026-09-20T00:00:00Z
**Source review:** .planning/phases/07-claude-code-the-first-real-worker/07-REVIEW.md

**Summary:**
- Findings in scope: 1 (the critical finding, CR-01 — also independently confirmed by
  `07-VERIFICATION.md` as the one phase-goal-blocking gap)
- Fixed: 1
- Skipped: 0

Scope note: this was a targeted fix of the phase-goal-blocking critical finding, applied
inline during `/gsd-execute-phase 7`'s verification gate rather than via a separate
`/gsd-code-review --fix` invocation. The review's 4 warnings and 2 info findings are
deliberately **not** in scope here — none of them block phase completion, and fixing them
was not necessary to close the verification gap. They remain open in `07-REVIEW.md` for a
future `/gsd-code-review 07 --fix` pass.

## Fixed Issues

### CR-01: `artifacts.read` is translated to an unscoped `Read` grant, not the documented path-scoped specifier

**Files modified:** `src/dark_factory/workers/claude_code.py`, `tests/unit/test_claude_code_worker.py`
**Commits:** `dd8fc1a` (RED — failing tests), `17559b2` (GREEN — fix)
**Applied fix:** Removed `"artifacts.read": ("Read",)` from `_TOOL_NAMES` (the bare-grant
table) and gave `allowed_tools_for()` a new `artifacts_read_glob` parameter, mirroring the
path-scoped treatment `artifacts.write` already had via its `Edit(<glob>/**)` specifier —
`artifacts.read` now produces `Read(<glob>/**)` instead. The read glob is deliberately
**run**-scoped (`.dark-factory/runs/<run_id>/artifacts`), not role-scoped like write's
`artifacts/<role>` glob, because a worker legitimately reads a *prior* role's artifact
output — narrowing read to the role's own subtree would have been a different, wrong bug.
`_base_argv()` (the shared argv builder both `_execute` and `_resume` go through) now
computes and passes this second glob alongside the existing write glob.
`_tool_names_cover_native_contract()`'s exemption set was updated to include
`"artifacts.read"` alongside `"artifacts.write"` so the completeness check stays accurate.

Added three tests: `test_allowed_tools_for_artifacts_read_with_no_glob_yields_nothing`
(deny-by-omission with no glob, replacing the old test that pinned the bug),
`test_allowed_tools_for_artifacts_read_is_path_scoped_not_bare` (unit-level path-scoping
assertion), and `test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv`
(argv-level integration test mirroring the existing `artifacts.write` one). Verified RED
first (all three failed against the pre-fix code, `dd8fc1a`), then GREEN after the fix
(`17559b2`).

Verified: `uv run pytest tests/unit/test_claude_code_worker.py -m unit -q` (50 passed), full
`uv run pytest -q -m "unit or contract"` (514 passed), `mypy --strict src/dark_factory` (0
errors), `ruff check .` (clean).

## Skipped Issues

None in scope. WR-01 through WR-04 and IN-01/IN-02 remain open in `07-REVIEW.md` — none of
them block the phase goal; see that report for detail if picked up in a future pass.

## Verification Notes

`07-VERIFICATION.md`'s single reported gap (score 15/16) was exactly this finding. Re-run
after this fix to confirm 16/16.
