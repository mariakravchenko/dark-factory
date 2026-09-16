---
phase: 05-isolated-workspace-git-lifecycle
reviewed: 2026-09-16T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/dark_factory/config/loader.py
  - src/dark_factory/git/diff.py
  - src/dark_factory/git/scope.py
  - src/dark_factory/orchestrator/runner.py
  - tests/integration/test_phase5_acceptance.py
  - tests/integration/test_write_scope_enforcement.py
  - tests/unit/test_write_scope_revert.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-09-16
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

This is an incremental re-review of the four production files touched by the four
fix commits (`46adf4a` CR-01, `dd10f43` CR-02, `c579243` WR-01, `ba5bb09` WR-03) that
landed after the prior 05-REVIEW.md round, plus the three test files added by the
two `--gaps-only` gap-closure plans (05-05, 05-06).

All four fixes were verified against the diff they claim to address and each one
correctly closes the finding it targets:

- **CR-01** (`git/diff.py`): `ARTIFACT_EXCLUDE_PATHSPEC` is now scoped to
  `.dark-factory/runs` (matching `.gitignore`'s own entry, confirmed byte-for-byte),
  no longer excluding the tracked `.dark-factory.yaml` / `.dark-factory/roles/*.yaml`
  / `.dark-factory/instructions/*.md` files from write-scope enforcement or the
  PR-bound diff. Verified the git pathspec semantics: `":(exclude).dark-factory/runs"`
  matches only `.dark-factory/runs` itself and its descendants (component-boundary
  matching), not sibling paths like a hypothetical `.dark-factory/runs-old/`.
- **CR-02** (`git/scope.py`): `revert_paths` now wraps the per-path containment
  check in `try`/`except`, collects escapes, and reverts every non-escaping
  violation before raising once at the end — matches the fix's own description and
  is directly exercised by the new `tests/unit/test_write_scope_revert.py` suite
  (escape-first, escape-last, escape-only, multiple-escapes cases all pass through
  the intended code path).
- **WR-01** (`git/scope.py`): unexpected `git rm --cached` failures (anything other
  than the "pathspec did not match any files" no-op case) are now logged via
  `structlog` before `git clean` still runs. The marker string was verified against
  real git output (`fatal: pathspec 'X' did not match any files`) — the substring
  match is correct.
- **WR-03** (`config/loader.py`, `git/scope.py`, `orchestrator/runner.py`): both the
  pydantic default and the legacy bare-string runner fallback now read the single
  `DEFAULT_WRITE_SCOPE = ()` constant instead of two independently-spelled `[]`
  literals. Verified pydantic v2 deep-copies `RolePermissions()` model-instance
  defaults per validated instance (tested directly), so the shared default is not
  an aliasing hazard.

The three test files (`test_phase5_acceptance.py`, `test_write_scope_enforcement.py`,
`test_write_scope_revert.py`) contain **no production-code changes** — confirmed via
`git diff` against the stated `diff_base`: the acceptance-gate change only adds a new
proof-file reference, the enforcement-suite change only swaps a worktree-filesystem
read for a working-branch read (with a supporting import), and the new revert-suite
file is wholly new unit tests exercising `revert_paths`/`enforce_write_scope`
directly. This matches the two gap-closure plans' "zero `src/` changes" claim.

Two new findings surfaced in this round that were not present (or not applicable) in
the prior review: an inconsistency in exception-handling breadth at the
`enforce_write_scope` call site relative to its sibling commit/push call site, and a
message/observability regression that is a direct, intentional-but-uncompensated-for
side effect of the CR-02 fix. Neither is a regression introduced by the fix commits
in the sense of "broke something that worked" — CR-02's own new test suite documents
the message-content tradeoff explicitly — but both are real, reachable-in-production
gaps worth recording.

## Warnings

### WR-04: `enforce_write_scope`'s call site catches only `WriteScopeViolation`, not the broader `GitError` its sibling commit/push call site catches

**File:** `src/dark_factory/orchestrator/runner.py:889-903`

**Issue:**

Immediately above this block, the artifact-commit/push sequence wraps
`commit_run_artifacts` and `push_working_branch` in `except GitError as exc:` — the
broad base class, so any unexpected git-level failure (not just the specific
violation type) is folded into the same `ROLE_FAILED`/`RUN_FAILED` shape:

```python
try:
    artifact_sha = commit_run_artifacts(work_dir, run_id, role=node.name)
    ...
except GitError as exc:
    signal = Signal.ROLE_FAILED
    ...
```

The write-scope block right after it narrows the catch to the specific subtype:

```python
try:
    enforce_write_scope(
        work_dir,
        write_scope=write_scope,
        role=node.name,
        attempt=latest.attempt,
    )
except WriteScopeViolation as exc:
    signal = Signal.ROLE_FAILED
    ...
```

`enforce_write_scope` calls `attempt_changed_paths` (two `run_git` calls, `check=True`
by default) and, on a violation, `revert_paths` (up to three more `run_git` calls per
path: `cat-file -e`, then either `restore` or `rm --cached` + `clean`, all
`check=True` except the tolerated `rm --cached` case). Any of these can raise
`GitCommandError` — a sibling of `WriteScopeViolation` under `GitError`, not a
subclass of it — for a reason unrelated to write-scope policy: a permission error on
`git restore`/`git clean`, a corrupted index entry, disk pressure, or any other
git-level failure during the revert of a legitimately-detected violation.

Because only `WriteScopeViolation` is caught here, such a `GitCommandError`
propagates uncaught out of `_run_current_role`, out of `_advance_once`, through
`with run_lease(...) as lease:` (which releases the lease cleanly in its `finally`,
per `orchestrator/lease.py`, so no lease is stranded) and out of `advance()`/`drive()`
to the CLI — crashing that call instead of cleanly failing the role the way every
other git-adjacent failure in this same function does. The role's
`role_executions` row is left `RUNNING` with no committed outcome; a subsequent
`advance()`/`drive()` call would re-enter `_run_current_role` for the same attempt
and retry from the top (before-hooks, worker call, everything), which is at least
recoverable, but it is a materially different (and less observable) failure path than
the `ROLE_FAILED`/`RUN_FAILED` audit trail every other checked failure in this
function produces.

**Fix:** Widen the catch to the same base class the adjacent block already uses,
consistent with this function's own stated pattern of "no new failure vocabulary":

```python
try:
    enforce_write_scope(
        work_dir,
        write_scope=write_scope,
        role=node.name,
        attempt=latest.attempt,
    )
except GitError as exc:
    signal = Signal.ROLE_FAILED
    outcome = {**outcome, "error": str(exc)}
    artifact_writes = []
```

(`GitError` is already imported at the top of this module for the before-hook
`DetachedHeadError` handling, so no new import is needed.)

### WR-05: an escape-triggered `WriteScopeViolation` loses the role/attempt/write-scope context every other violation's error message carries

**File:** `src/dark_factory/git/scope.py:165-247` (`revert_paths` /
`enforce_write_scope`), consumed at `src/dark_factory/orchestrator/runner.py:900-903`

**Issue:**

This is a direct, documented consequence of the CR-02 fix, not a regression it
introduced — but it was not called out as its own finding, and it is user-visible.

When `enforce_write_scope` finds violations and none of them escape the worktree, it
reverts them all and raises its own exception naming the role, the attempt, the
configured `write_scope` patterns, and the complete violation list:

```python
raise WriteScopeViolation(
    f"role {role} attempt {attempt} wrote outside its configured "
    f"write_scope {list(write_scope)!r}: {violations!r}"
)
```

But when at least one violation is a containment escape (e.g. a symlink), the
exception that actually reaches the caller is the one `revert_paths` raises instead
— `enforce_write_scope`'s own final `raise` is never reached, because `revert_paths`
already raised:

```python
raise WriteScopeViolation(
    f"write-scope paths escape worktree {worktree.resolve()}: {escapes!r}"
)
```

This message names only the escaping path(s) — no role name, no attempt number, no
`write_scope` patterns, and (if there were also non-escaping violations that were
correctly reverted) no mention that those existed at all. `test_write_scope_revert.py`'s
`test_enforce_write_scope_produces_the_escape_first_ordering_itself` documents this
exact behavior in its docstring ("the exception that surfaces to the caller comes
from the revert step ... not from `enforce_write_scope`'s own final raise"), so the
behavior is intentional at the `git/scope.py` level — but nothing in
`orchestrator/runner.py`'s consumption of it (`outcome = {**outcome, "error": str(exc)}`,
persisted verbatim to `role_executions.error`) compensates for the missing context. An
operator reading the failure audit trail for an escape-triggered failure sees a
qualitatively different, less informative message than for every other write-scope
failure, with no role or attempt correlation baked into the string itself (though it
is still recoverable from the row's own `role`/`attempt` columns).

**Fix:** Either have `revert_paths` accept and echo the `role`/`attempt` context (a
signature change reaching two call sites and every test that constructs the message),
or have `enforce_write_scope` catch `WriteScopeViolation` raised by `revert_paths` and
re-wrap it with the same `role {role} attempt {attempt} ...` prefix before
re-raising, e.g.:

```python
try:
    revert_paths(worktree, violations)
except WriteScopeViolation as exc:
    raise WriteScopeViolation(
        f"role {role} attempt {attempt} wrote outside its configured "
        f"write_scope {list(write_scope)!r}: {violations!r} "
        f"(revert failed: {exc})"
    ) from exc
raise WriteScopeViolation(
    f"role {role} attempt {attempt} wrote outside its configured "
    f"write_scope {list(write_scope)!r}: {violations!r}"
)
```

## Info

### IN-02: WR-01's new "unexpected `git rm --cached` failure" log branch has zero test coverage

**File:** `src/dark_factory/git/scope.py:233-241` (the
`_log.warning("write_scope.revert_rm_cached_unexpected_failure", ...)` branch)

**Issue:** The WR-01 fix added a structlog warning for the case where `git rm
--cached` fails with something other than the tolerated "pathspec did not match any
files" no-op. Searching the full test suite (`grep -rn
"revert_rm_cached_unexpected_failure"`) finds no test that exercises this branch —
neither `tests/unit/test_write_scope_revert.py` (the CR-02 regression suite added in
this same round) nor `tests/integration/test_write_scope_enforcement.py` constructs a
scenario where `git rm --cached` fails for a reason other than "not staged" (e.g. a
permission-denied path, or a corrupted index entry). This is exactly the same shape
of gap CR-02 itself shipped with ("a Critical finding with zero executed coverage at
any tier," per this file's own module docstring) — a defensive branch with no proof
it fires or that its log payload is well-formed.

**Fix:** Low priority given the branch is purely diagnostic (it does not change
control flow — `git clean` still runs unconditionally either way) — but consider a
unit test that makes `git rm --cached` fail for an unexpected reason (e.g. by
removing write permission on `.git/index` temporarily, or monkeypatching `run_git`
for this one call) and asserts the warning is emitted with the expected `path` /
`returncode` fields, so this branch is not carried forward untested indefinitely.

---

_Reviewed: 2026-09-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
