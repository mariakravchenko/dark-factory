# Phase 5: Isolated Workspace & Git Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-14
**Phase:** 5-Isolated Workspace & Git Lifecycle
**Areas discussed:** Branch & worktree lifecycle, WIP-commit recovery & detached HEAD, Artifact durability — commit mechanics, Write-scope enforcement (ROLE-05)

---

## Branch & worktree lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| dark-factory/run-{run_id} | Namespaced prefix, run_id guarantees uniqueness | ✓ |
| df/{run_id} | Shorter prefix, same uniqueness guarantee | |
| Include role/task slug | More human-readable, needs safe slugification | |

**User's choice:** `dark-factory/run-{run_id}`

| Option | Description | Selected |
|--------|-------------|----------|
| Sibling to the repo, via git worktree add | True git worktree mechanism, no re-clone | ✓ |
| Nested under .dark-factory/runs/<id>/workspace | Unusual nesting inside the tree it's a worktree of | |

**User's choice:** Sibling to the repo, via `git worktree add`

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse the same worktree (default) | Persists between attempts, matches phase goal | ✓ (Claude's discretion) |
| Recreate fresh each resume from the branch | Would discard uncommitted state, conflicts with SC3 | |

**User's choice:** "Choose the best" — Claude selected reuse (required for WIP-commit recovery to have something to recover)

| Option | Description | Selected |
|--------|-------------|----------|
| On terminal state (COMPLETED/FAILED) | Cleans up regardless of outcome | |
| Never automatic — manual/operator cleanup only | No auto-deletion at all | |
| On COMPLETED only, kept on FAILED | Successful runs clean up, failures kept for debugging | ✓ (Claude's discretion) |

**User's choice:** "Choose the best" — Claude selected COMPLETED-only cleanup, FAILED kept for post-mortem

**Notes:** None beyond selections.

---

## WIP-commit recovery & detached HEAD

| Option | Description | Selected |
|--------|-------------|----------|
| Plain commit on the working branch | Regular commit, SHA is the persisted ref | ✓ (Claude's discretion) |
| git stash, ref recorded | Stash object, GC risk if unreferenced | |

**User's choice:** "Chose the best option" — Claude selected plain commit

| Option | Description | Selected |
|--------|-------------|----------|
| Inside ensure_clean_worktree, on every role entry | Reuses existing action hook named for this purpose | ✓ (Claude's discretion) |
| In the orchestrator runner, unconditionally | Matches WR-01 unconditional-call pattern instead | |

**User's choice:** "Chose the best option" — Claude selected the `ensure_clean_worktree` action

| Option | Description | Selected |
|--------|-------------|----------|
| New column on role_executions | wip_commit_sha, ties to specific attempt | ✓ (Claude's discretion) |
| A run_events entry only | No migration, but harder to query directly | |

**User's choice:** "Chose the best option" — Claude selected the new column

| Option | Description | Selected |
|--------|-------------|----------|
| Same as a schema-violation failure (D-09 pattern) | Reuses Phase 4's established failure shape | ✓ (Claude's discretion) |
| You decide | Left to planning | |

**User's choice:** "Chose the best option" — Claude selected reusing the D-09 pattern

---

## Artifact durability — commit mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| After each role completes | One commit per role attempt | ✓ (Claude's discretion) |
| Per-artifact, as each file is written | Finer granularity, more git overhead | |

**User's choice:** "Chose the best option" — Claude selected per-role commits

| Option | Description | Selected |
|--------|-------------|----------|
| collect_diff filters by path | Path-exclude .dark-factory/ at diff time | ✓ (Claude's discretion) |
| Separate commits, diff by commit range | Requires tagging/walking history | |

**User's choice:** "Chose the best option" — Claude selected path filtering

| Option | Description | Selected |
|--------|-------------|----------|
| Fully tracked on the working branch only | Committed on working branch, gitignored on base | ✓ (Claude's discretion) |
| You decide | Left to planning | |

**User's choice:** "Chose the best option" — Claude selected fully tracked on working branch, gitignored on base

---

## Write-scope enforcement (ROLE-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Glob patterns | Flexible, gitignore-style matching | ✓ (Claude's discretion) |
| Directory prefixes | Simpler but less expressive | |

**User's choice:** "Choose the best" — Claude selected glob patterns

| Option | Description | Selected |
|--------|-------------|----------|
| After every role attempt, before it's accepted as COMPLETED | Check before transition, matches D-09 ordering | ✓ (Claude's discretion) |
| You decide | Left to planning | |

**User's choice:** "Choose the best" — Claude selected enforcing before acceptance

| Option | Description | Selected |
|--------|-------------|----------|
| Zero tolerance — any change is a violation | Matches ROLE-01/ROLE-02 read-only intent | ✓ (Claude's discretion) |
| No restriction — skip enforcement | Would silently defeat read-only guarantee | |

**User's choice:** "Choose the best" — Claude selected zero tolerance for empty `write_scope`

---

## Claude's Discretion

- Reuse worktree across resume (not recreate)
- Worktree cleanup only on COMPLETED, kept on FAILED
- Plain git commit (not stash) for WIP recovery
- `ensure_clean_worktree` action as the enforcement point for WIP recovery/detached HEAD
- New `role_executions.wip_commit_sha` column
- Detached HEAD reuses Phase 4's D-09 failure shape
- Per-role (not per-artifact) commit granularity for artifact durability
- `collect_diff` path-excludes `.dark-factory/` rather than commit-range filtering
- `.dark-factory/` tracked on working branch, gitignored on base branch
- Glob-pattern `write_scope` format
- Write-scope enforcement runs before role acceptance
- Empty `write_scope` treated as zero tolerance

## Deferred Ideas

None — discussion stayed within phase scope. Cross-machine clone/transport orchestration was explicitly scoped to Phase 11, not raised as new scope by the user.
