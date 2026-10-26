---
phase: 05-isolated-workspace-git-lifecycle
fixed_at: 2026-09-15T16:22:36Z
review_path: .planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 4
skipped: 1
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-09-15T16:22:36Z
**Source review:** .planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (critical_warning): 5 (CR-01, CR-02, WR-01, WR-02, WR-03)
- Fixed: 4
- Skipped: 1 (environment limitation, not a code fix)

**Verification environment:** All fixes were made and verified inside an
isolated git worktree
(`.claude/worktrees/rf-05-73595-1789489020`, branch `gsd-reviewfix/05-73595`,
fast-forwarded onto `gsd/phase-01-walking-skeleton-one-durable-run` and torn
down after this report was written). `uv sync --all-extras --dev` was run
fresh in that worktree, so `uv run pytest -m unit -q`, `uv run mypy
src/dark_factory`, and `uv run ruff check .` all ran against the same
dependency set the main checkout resolves from `uv.lock` — the results below
are reproducible from the main checkout after the branch fast-forward.

## Fixed Issues

### CR-01: `ARTIFACT_EXCLUDE_PATHSPEC` excluded all of `.dark-factory/`, not just the gitignored `runs/` subtree

**Files modified:** `src/dark_factory/git/diff.py`
**Commit:** `46adf4a`
**Applied fix:** Narrowed `ARTIFACT_EXCLUDE_PATHSPEC` from
`":(exclude).dark-factory"` to `":(exclude).dark-factory/runs"`. This is the
single shared constant consumed by both cited call sites —
`git/scope.py`'s `attempt_changed_paths` (the write-scope change-scan) and
`git/diff.py`'s `collect_pr_diff`/`pr_changed_paths` (the PR-bound diff) —
so both now exclude exactly the ephemeral, gitignored per-run artifact tree
and nothing else. Tracked role config (`.dark-factory/roles/*.yaml`,
`.dark-factory/instructions/*.md`, `.dark-factory.yaml`) is now subject to
the same write-scope enforcement and PR-diff visibility as any other source
file, closing the blind spot the finding traced end-to-end (undetected
write-scope violation → swept into a misleadingly-labeled WIP-recovery
commit → pushed to `origin` → invisible in the PR diff). Verified against
`tests/integration/test_pr_diff_excludes_artifacts.py`'s existing
`".dark-factory" not in three_dot` assertion: that test's fixture only
touches `.dark-factory/runs/<run_id>/` (artifact commits), never
`.dark-factory/roles/*.yaml`, so the assertion still holds under the
narrowed pathspec — no test text needed to change.

### CR-02: `revert_paths` aborted mid-loop on a path-containment failure, leaving queued violations un-reverted

**Files modified:** `src/dark_factory/git/scope.py`
**Commit:** `dd10f43`
**Applied fix:** `revert_paths` now wraps the per-path `_resolve_in_worktree`
containment check in `try`/`except WriteScopeViolation`, collecting any
escaping paths into a list instead of letting the first one abort the loop.
Every non-escaping violation is still reverted (via the existing
`restore`/`rm --cached`+`clean` branching, unchanged). After the loop, if any
escapes were collected, a single `WriteScopeViolation` is raised naming all
of them. This delivers `enforce_write_scope`'s own docstring guarantee
("every violating path is reverted before the exception is raised") for
every path that resolves inside the worktree, while still failing loudly and
distinctly for paths that escape containment (reject-never-clamp preserved —
an escaping path is never "reverted" via a clamped/coerced path, it is
reported and the batch continues around it).

**Note (status: fixed, requires human verification):** this finding
described a logic/control-flow defect (early-exit vs. batch-processing
semantics), not a syntax error. Tier 1/2 verification (re-read + `mypy`/
`ruff`/unit tests) confirms the code is syntactically and type-correct and
that no existing test regressed, but no test in this repository currently
exercises the symlink-escape-plus-other-violations scenario the finding
describes (`grep` for `symlink`/`_resolve_in_worktree`/`revert_paths` across
`tests/` found no references). A human should confirm the corrected
control flow against that scenario directly — ideally by adding the
regression coverage WR-02 already calls for (a symlink-escape violation
alongside an ordinary one) once the integration suite is run against a
reachable database.

### WR-01: `git rm --cached` failure in `revert_paths`'s new-file branch was unconditionally swallowed

**Files modified:** `src/dark_factory/git/scope.py`
**Commit:** `c579243`
**Applied fix:** `revert_paths` now captures the `git rm --cached` result
and, on a non-zero exit whose stderr does not contain git's exact
"pathspec ... did not match any files" text (verified empirically against a
real `git rm --cached` invocation on an unstaged path), logs a
`write_scope.revert_rm_cached_unexpected_failure` structlog warning naming
the path, return code, and stderr before `git clean --force` still runs
immediately after (unchanged) — `git clean` is not itself what could resolve
an unexpected `rm --cached` failure, so it is still attempted either way, but
an operator now has a trail if this branch ever masks a real git-level
problem.

### WR-03: `_run_current_role`'s `write_scope` default duplicated D-14 polarity logic at a second call site

**Files modified:** `src/dark_factory/git/scope.py`,
`src/dark_factory/config/loader.py`, `src/dark_factory/orchestrator/runner.py`
**Commit:** `ba5bb09`
**Applied fix:** Introduced `dark_factory.git.scope.DEFAULT_WRITE_SCOPE`
(`tuple[str, ...] = ()`) as the single source of D-14's "missing/empty
write_scope means zero tolerance" default. `config/loader.py`'s
`RolePermissions.write_scope` `Field(default_factory=...)` and
`orchestrator/runner.py`'s `_run_current_role` fallback (for a legacy
bare-string snapshot entry with no `permissions` key) both now read this one
constant instead of each spelling out an independent `[]` literal, so a
future edit to the default cannot silently diverge between the two call
sites, as the finding warned.

## Skipped Issues

### WR-02: `tests/integration/test_write_scope_enforcement.py` has not been executed against a real database

**File:** `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md:48`,
`.planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md`
**Reason:** This is an environment/infrastructure limitation, not a source
defect this fixer can resolve by editing code. The sandbox this fixer ran in
has no reachable PostgreSQL 17 instance, so
`uv run pytest tests/integration/test_write_scope_enforcement.py -x` (and
every other `tests/integration/` / `tests/db/` module requiring the `engine`
fixture) could not be executed here — confirmed by running only
`uv run pytest -m unit -q`, which deliberately deselects the 292
integration/db-marked tests. The CR-01 and CR-02 fixes above were verified
via full-project `mypy`/`ruff` plus the complete unit suite (366 passed),
and CR-01's fix was additionally cross-checked by hand against
`tests/integration/test_pr_diff_excludes_artifacts.py`'s existing assertion
(see CR-01 above), but the integration suite itself still needs to be run
against a reachable PostgreSQL 17 before this phase is considered fully
verified, exactly as WR-02 recommends. This is unchanged from the review's
own assessment and is not something a code edit can close — it requires a
database-reachability handoff, as `05-VALIDATION.md` already tracks.

**Original issue:** Per the phase's own validation tracker, the row for
`tests/integration/test_write_scope_enforcement.py` is marked
"pending — DB-reachability handoff," meaning the `enforce_write_scope`
wiring in `orchestrator/runner.py` has never been run end-to-end against a
real PostgreSQL 17. The finding's suggested additional coverage — a role
writing to `.dark-factory/roles/*.yaml` (CR-01) and a symlink-escape
violation alongside an ordinary one (CR-02) — has also not yet been added,
since it would need to run against that same database to be validated.

---

_Fixed: 2026-09-15T16:22:36Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
