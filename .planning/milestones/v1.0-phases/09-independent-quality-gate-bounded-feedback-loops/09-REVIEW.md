---
phase: 09-independent-quality-gate-bounded-feedback-loops
reviewed: 2026-09-26T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tests/db/test_feedback_reaches_developer.py
  - tests/unit/test_role_context_rebuild_uses_the_worktree.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-09-26T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Incremental review scoped to gap-closure plan 09-06 (commit range `0be6272..HEAD`). The
only substantive change is the fix in `tests/db/test_feedback_reaches_developer.py`'s
`_CapturingWorker._record_and_maybe_rebuild`: it now derives the run's worktree via
`ensure_worktree(self._repo_root, self._run_id, base_branch=fresh_state.base_branch,
working_branch=fresh_state.working_branch)` and passes the resulting `work_dir` to
`build_role_context`, instead of passing the stored config repo root directly. I traced
this against the production call site it claims to mirror
(`src/dark_factory/orchestrator/runner.py`, the `_advance_once` block that calls
`ensure_worktree` then `build_role_context(context_session, work_dir, run_id, state,
role_def)`) and confirmed the argument order, keyword names, and `RunState` field names
(`base_branch`, `working_branch`) all match exactly. `worktree_path` (`src/dark_factory/git/worktree.py:37-43`)
confirms the worktree is indeed a sibling of `repo_root`, corroborating the bug the fix
addresses (G-09-6/G-09-7: reading `design.md` etc. against a directory nothing was ever
written into). `ensure_worktree` is documented and implemented as idempotent
("create-or-reuse"), so the second call inside the rebuild (the worktree was already
created earlier in each test body) is a safe same-disk-reuse no-op, not a duplicate-creation
race.

The new `tests/unit/test_role_context_rebuild_uses_the_worktree.py` is a DB-free AST guard
that asserts this structurally: exactly one `ensure_worktree` call inside
`_record_and_maybe_rebuild`, exactly one `build_role_context` call in the whole module, and
that call's root argument must be the local bound from `ensure_worktree`'s return value,
never `self._repo_root`. The AST-walking logic (`_calls_named`, `_find_function`,
`_ensure_worktree_bound_name`) is internally consistent: `ast.walk` returns the same node
objects on repeated traversals of one parsed tree, so the `is call` identity check used to
locate the binding assignment is valid, and the guard mirrors the existing
`test_write_scope_guard_covers_bounce.py` idiom already used elsewhere in this codebase.

No security issues, no dead code, no unhandled edge cases that risk incorrect production
behavior were found — this is test-only code and the fix is narrowly and correctly scoped.
One pre-existing minor robustness note is recorded below as Info.

## Info

### IN-01: Unguarded `next()` can raise a bare `StopIteration` instead of a diagnosable `AssertionError`

**File:** `tests/db/test_feedback_reaches_developer.py:200-202`
**Issue:** Inside the touched function `_record_and_maybe_rebuild`, the role-definition
lookup

```python
role_def = next(
    r for r in fresh_state.workflow["roles"] if r["name"] == context.role
)
```

has no default. If a future refactor ever passes a `context.role` that isn't present in
`fresh_state.workflow["roles"]` (e.g., a renamed role in one of the four-role fixtures, or
a rebuild triggered for a role not present in that particular config tree), this raises a
bare `StopIteration` rather than a message naming what was being looked for — the least
diagnosable failure mode in the file, and notably less friendly than the neighboring
`_ensure_worktree_bound_name`/`_find_function` helpers added by this same gap-closure plan
in the sibling AST-guard file, which both raise explicit `AssertionError`s naming the
missing thing. This doesn't affect current test reliability (the four-role fixtures always
declare `context.role` in `workflow["roles"]`), so it is not a functional bug today, just a
latent maintainability gap directly adjacent to code this plan just hardened.
**Fix:**
```python
role_def = next(
    (r for r in fresh_state.workflow["roles"] if r["name"] == context.role),
    None,
)
assert role_def is not None, (
    f"no role definition named {context.role!r} in this run's persisted "
    "workflow -- rebuild_at key mismatch?"
)
```

---

_Reviewed: 2026-09-26T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
