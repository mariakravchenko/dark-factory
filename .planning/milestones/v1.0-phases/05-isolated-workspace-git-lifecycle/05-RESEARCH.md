# Phase 5: Isolated Workspace & Git Lifecycle - Research

**Researched:** 2026-09-14
**Domain:** Git plumbing via `subprocess` (worktrees, branches, diffs, commits), Postgres schema migration, `fnmatch`/`pathlib` path matching
**Confidence:** HIGH (git mechanics — all empirically verified against the installed `git 2.50.1` in this repo's environment; code-integration points — HIGH, read directly from source this session)

## Summary

This phase turns two permanent-looking no-op actions (`ensure_clean_worktree`, `collect_diff`) into the real git spine of every run, and enforces a per-role write boundary (`write_scope`). None of it needs a new dependency: the whole phase is `git` CLI calls through `subprocess` (per `CLAUDE.md`'s explicit "git via subprocess, NOT pygit2/GitPython-for-writes" constraint) plus one Alembic migration adding a single nullable column. Every git invocation pattern named in the phase brief was executed against a real throwaway repo this session (`git 2.50.1`, comfortably above the `>=2.40` floor) and the exact stdout/exit-code/error-text behavior is recorded below — this is not textbook git knowledge, it is this session's verified output.

The single most important non-obvious finding is a **control-flow gap in `orchestrator/runner.py`**: today, `_run_hooks("before")` inside `_run_current_role` is an unguarded `for` loop with no `try/except`, and every action returns `None`. D-06's detached-HEAD failure and D-08's "fail the role instead of proceeding" requirement mean a before-hook must now be able to (a) abort before the worker is ever called, and (b) get its outcome (a WIP-commit SHA, or a failure) persisted through the *one* mutation path — while the action itself is still forbidden from opening a `Session` (WR-01, enforced by `test_single_mutation_path.py`, verified this session). This shapes almost every other design choice in this phase and is covered in detail under **Architecture Patterns → Pattern 2**.

The second load-bearing finding **corrects an assumption in the phase brief**: `pathlib.PurePath.match()` is not a safe alternative to `fnmatch` for `write_scope` patterns — it is empirically *right-anchored / suffix-based* and pre-3.13 has no true recursive `**`, so `PurePath("tests/fixtures/src/evil.py").match("src/**")` returns `True` (a false-positive scope violation this project cannot afford for ROLE-05 enforcement, since it would let an out-of-scope file slip past write-scope checks or wrongly restrict a legitimate one, depending on which side of the check it's applied). `fnmatch.fnmatchcase()` is the correct, verified choice — see **Common Pitfalls → Pitfall 1**.

**Primary recommendation:** Build a small `src/dark_factory/git/` package (`client.py` subprocess wrapper, `worktree.py`, `lifecycle.py`, `diff.py`, `scope.py`) that performs all git reads/writes and raises typed exceptions for failure conditions; keep `actions/builtins.py`'s `ensure_clean_worktree`/`collect_diff` as thin dispatchers into that package (as their docstrings already promise); wire the persistence of `wip_commit_sha` and the detached-HEAD/write-scope failure paths through `orchestrator/runner.py`'s existing hook-and-`apply_transition` machinery, not through the action itself.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Branch + worktree creation/reuse | Orchestrator (API/Backend) | — | Deterministic git-CLI side effect Dark Factory owns outright (GIT-02); never agent-initiated |
| Detached-HEAD detection / WIP-commit recovery | Orchestrator (API/Backend) | Database/Storage (persists `wip_commit_sha`) | Git-level check lives in a new `git/` package; the DB write of the outcome lives in `persistence/mutations.py`, the one mutation path |
| Artifact-content durability commit | Orchestrator (API/Backend) | Database/Storage | Filesystem→git commit is a Dark Factory side effect; Neon still stores only `ArtifactReference` metadata, unchanged (ART-03) |
| PR-bound diff collection (`collect_diff`) | Orchestrator (API/Backend) | — | Pure git read (`git diff`); no DB, no network; consumed by later phases (9, 10) |
| Write-scope enforcement + revert | Orchestrator (API/Backend) | Database/Storage (persists violation as a `FAILED` role_execution) | Authorization boundary over the role's own diff; Dark Factory computes and enforces it, the worker never sees or controls it |
| Role's own file edits | Worker subprocess (external) | — | Out of scope for Dark Factory to prevent *while running* — enforcement is a post-hoc check on the resulting diff, not a live sandbox (that's a Phase 6/7 concern, TOOL-03/SEC-03) |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Working branch is named `dark-factory/run-{run_id}` — namespaced prefix groups all Dark Factory branches; the run's UUID guarantees uniqueness with no slugification or collision logic needed.
- **D-02:** The run's worktree is a real `git worktree add`, sibling to the main repo checkout (e.g. `../dark-factory-runs/{run_id}/`) — not nested inside `.dark-factory/runs/<id>/` inside the repo itself, since `git worktree` expects a path outside the tree it's a worktree of.
- **D-03:** The same worktree is reused across every role attempt and across a pause/resume cycle — it is not recreated on resume. This is required for WIP-commit recovery (D-05/D-06) to have something to recover from; recreating fresh on resume would silently discard anything not yet committed.
- **D-04:** Worktree cleanup (`git worktree remove`) happens automatically when a run reaches `COMPLETED`. A run that reaches `FAILED` keeps its worktree on disk for post-mortem debugging — no automatic cleanup on failure.
- **D-05:** An uncommitted-changes recovery is a plain `git commit` directly on the run's working branch (not a `git stash`), with a generated message such as `wip(dark-factory): recover uncommitted changes from <role> attempt N`. Simpler mental model than a stash object, no extra git-object garbage-collection risk.
- **D-06:** The recovery/detached-HEAD check lives inside the existing `ensure_clean_worktree` action (currently a permanent no-op per `src/dark_factory/actions/builtins.py`), invoked on every role entry — this phase is exactly the "later phase named in its own docstring" that action was written for. It becomes real: check for a detached HEAD (fail immediately if so) and check for dirty worktree state (WIP-commit if so), before the role's worker is invoked.
- **D-07:** The WIP commit SHA is persisted on a new `role_executions.wip_commit_sha` column — ties the recovered commit directly to the specific attempt that produced it, consistent with the existing per-attempt `RoleExecution` row pattern from Phases 1–2.
- **D-08:** A detached-HEAD entry fails the role using the exact same shape as Phase 4's schema-violation failure (D-09 in 04-CONTEXT.md): persists a `FAILED` `role_execution` + a `run_events` error entry, transitions the run to `FAILED` immediately. No new failure pathway — reuses the established pattern.
- **D-09:** Dark Factory commits `.dark-factory/runs/<run-id>/` artifact content to the working branch once per completed role (not per individual artifact file) — e.g. `chore(dark-factory): BA artifacts (run <id>)` right after `store_role_artifacts` writes the filesystem content for that role. One commit per role attempt, easy to bisect which role produced what.
- **D-10:** `collect_diff` (currently a no-op, becomes real this phase) computes the PR-bound diff against the base branch with a path exclusion for `.dark-factory/` — e.g. `git diff base...working -- . ':(exclude).dark-factory'`. Artifact-content commits and code commits can interleave freely on the working branch; the exclusion is a path filter at diff-computation time, not a history-restructuring or commit-tagging scheme.
- **D-11:** `.dark-factory/runs/<run-id>/` is fully tracked, committed content on the run's working branch (required for SC2 — a fresh clone must have it) but is gitignored on the base branch (e.g. `main`), so it never leaks into the repository's permanent history once a PR from the working branch is eventually merged.
- **D-12:** `write_scope` entries in role YAML are glob patterns (e.g. `write_scope: ["src/**"]` for Developer, `write_scope: ["tests/**"]` for QA), matched via `fnmatch`/`pathlib` globbing against each changed path in the role's diff — gitignore-style, familiar, and more expressive than a plain prefix match (can scope by extension or exclude a subdirectory).
- **D-13:** Enforcement runs immediately after a role's worker returns `COMPLETED`, before the attempt is accepted/transitioned: diff the attempt's changes, check every changed path against `write_scope`, revert any violating path, and fail the role if any violation was found. This is the same "before advancing" ordering as the D-09 (Phase 4) schema-violation check.
- **D-14:** An empty `write_scope: []` (BA and Architect's current placeholder value in every shipped role YAML) means **zero tolerance** — any change at all is a violation. This matches the stated ROLE-01/ROLE-02 intent ("read-only with respect to repository source code") rather than silently skipping enforcement for those roles.

### Claude's Discretion

- Exact revert mechanism for an out-of-scope path (`git checkout -- <path>` vs `git restore` vs a targeted patch reversal) — left to planning as long as the offending change does not survive into a commit.
- Exact commit-message trailer/format conventions beyond the illustrative examples above, as long as they're distinguishable in `git log` from a role's real work commits.
- Whether `ensure_clean_worktree`'s detached-HEAD/dirty-worktree checks run as one combined pass or two sequential checks — implementation detail, not a behavior difference.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. Real multi-machine transport (SSH, rsync, actual cross-machine orchestration) is Phase 11's concern; this phase only needs a fresh `git clone` + checkout to have the artifact content. Quality-gate diff *use* (Phase 9) and PR creation (Phase 10) are not this phase.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GIT-01 | Each run has an explicit working branch created from the configured base branch; all roles operate on the same run repository state | Verified `git worktree add -b <branch> <path> <base>` one-shot invocation (Architecture Patterns → Pattern 1); `Run.base_branch`/`working_branch` population point identified in `persistence/mutations.py::create_run` (currently unpopulated, confirmed by reading `models.py`) |
| GIT-02 | Dark Factory owns delivery actions (create branch, commit, push, create PR); agents never own commit/push/PR policy | All git mutation happens in the orchestrator's git package, never inside a worker adapter or role instructions; Common Pitfalls → Pitfall 6 (env allowlist for git subprocess calls) |
| ART-04 | Artifact content is available to a resuming process on a different machine | D-09/D-11 commit-to-working-branch mechanism verified end-to-end this session (Architecture Patterns → Pattern 3); `.gitignore` already excludes `.dark-factory/runs/` on the base branch (confirmed by reading the file) |
| ROLE-05 | A role's permitted file-write scope is enforced after execution using path rules from configuration | `fnmatch.fnmatchcase` vs `pathlib.PurePath.match` empirically compared (Common Pitfalls → Pitfall 1); revert-mechanism gap for untracked files verified (Pitfall 2); zero-tolerance polarity verified (Pitfall 3) |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `git` (CLI, via `subprocess`) | `>=2.40` (installed: `2.50.1`, verified `git --version` this session) | Worktree lifecycle, branch/commit/diff, detached-HEAD detection | Locked by `CLAUDE.md` ("git via subprocess CLI wrapper (NOT pygit2, GitPython optional for read-only porcelain only)"); every syntax used below was run against this exact version |
| `subprocess` (stdlib) | 3.12 | Invoke `git` with an explicit `args` list, never `shell=True` | Matches the existing worker-invocation convention (`CLAUDE.md`'s "Invoking the agent CLIs" table) and the credential-boundary discipline |
| `fnmatch` (stdlib) | 3.12 | `write_scope` glob matching (D-12) | `[VERIFIED: this session]` — see Common Pitfalls → Pitfall 1 for the empirical comparison against `pathlib.PurePath.match()` |
| `alembic` | `>=1.19,<2` (pinned in `pyproject.toml`, confirmed) | `role_executions.wip_commit_sha` migration | Existing project standard; follow the exact `op.add_column` pattern in `migrations/versions/0003_pause_resume_lease.py` (read this session) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib` (stdlib) | 3.12 | Path resolution/containment checks for diff-derived paths before revert | For containment guards only (mirror `artifacts/paths.py::resolve_under_run_root`, read this session) — **not** for `write_scope` glob matching (see Pitfall 1) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `fnmatch.fnmatchcase` for `write_scope` | `pathlib.PurePath.match()` | Empirically wrong for this use case pre-3.13 (right-anchored suffix matching, no true recursive `**`) — see Pitfall 1. Not a real alternative, listed here only because the phase brief hypothesized it as safe. |
| `fnmatch.fnmatchcase` for `write_scope` | A third-party gitignore-style matcher (`pathspec`, `wcmatch`) | Would be more expressive (negation, `!pattern`) but D-12 is a **locked decision** naming `fnmatch`/`pathlib`; introducing a new dependency for this is out of scope unless the planner reopens D-12 |
| `git commit` for WIP recovery (D-05) | `git stash` | Locked against by D-05 — stash objects are unreferenced by any branch and are GC-eligible; a plain commit on the working branch is permanent and inspectable in `git log` |
| Sibling worktree directory (D-02) | Worktree nested inside the repo tree | Locked against by D-02; git explicitly documents worktrees should not nest inside another worktree's tree |

**Installation:** None — this phase adds zero third-party dependencies. `git`, `subprocess`, `fnmatch`, `pathlib`, `alembic` are all either the OS `git` binary or already-vendored stdlib/project dependencies.

**Version verification:** `git --version` → `git version 2.50.1 (Apple Git-155)` (this session, this environment). `alembic` pin (`>=1.19,<2`) confirmed present in `pyproject.toml` (read this session) and matches the pattern used by `migrations/versions/0001`–`0004` (all read this session).

## Package Legitimacy Audit

**Not applicable this phase.** No new external packages are introduced — every capability in this phase is delivered through the OS `git` binary (already a hard project dependency per `CLAUDE.md`), Python stdlib (`subprocess`, `fnmatch`, `pathlib`), and the already-installed `alembic`. The Package Legitimacy Gate protocol was skipped for this reason; nothing to run `npm view`/`pip index versions` against.

## Architecture Patterns

### System Architecture Diagram

```
                         advance(run_id)  [orchestrator/runner.py]
                                │
                   ┌────────────┴─────────────┐
                   │  _advance_once            │
                   └────────────┬─────────────┘
                                │  (role K's role_executions row already exists)
                                ▼
                   ┌─────────────────────────────┐
                   │  _run_current_role            │
                   └────────────┬─────────────────┘
                                │
              ① before-hooks: ensure_clean_worktree
                                │
             ┌──────────────────┴───────────────────┐
             │  dark_factory.git package (subprocess) │
             │  ─────────────────────────────────────│
             │  worktree.ensure(...)  -- idempotent   │
             │    create-if-missing (D-02/D-03)       │
             │  lifecycle.check_head(...)             │
             │    -> DetachedHeadError  (D-06/D-08)   │
             │  lifecycle.wip_commit_if_dirty(...)    │
             │    -> commit SHA | None   (D-05/D-06)  │
             └──────────────────┬───────────────────┘
                                │
         DetachedHeadError? ──► YES ──► skip worker call entirely;
             │                          synthesize Signal.ROLE_FAILED
             │ NO (sha or None)         (same shape as D-09/Phase-4)
             ▼
         [worker.execute / worker.resume]   (unchanged, Phase 1-4 code)
                                │
              ② after: collect_role_artifacts (unchanged, D-09 Phase 4)
                                │
              ③ NEW: commit_role_artifacts (D-09) -- git commit
                    .dark-factory/runs/<id>/ once per completed role
                                │
              ④ NEW: enforce_write_scope (D-12/D-13/D-14)
                    diff attempt's changes -> fnmatch check -> revert
                    violations -> downgrade signal to ROLE_FAILED
                                │
                                ▼
              apply_transition(...)  [persistence/mutations.py]
              -- the ONE place that writes role_executions /
                 run_events / runs.status, incl. wip_commit_sha
```

A reader can trace the primary use case (a role attempt entering, running, and either advancing or failing) top-to-bottom: every git-level decision (worktree, HEAD state, dirty state, diff, scope) happens in the new `dark_factory.git` package with **no** DB access, and every DB write funnels back through the single `apply_transition` call already at the bottom of `_run_current_role`.

### Recommended Project Structure

```
src/dark_factory/git/
├── __init__.py
├── client.py        # _run_git(args, cwd) subprocess wrapper; GitError
├── worktree.py       # ensure_worktree(), remove_worktree() (D-01/D-02/D-03/D-04)
├── lifecycle.py       # DetachedHeadError, check_head(), wip_commit_if_dirty() (D-05/D-06/D-07/D-08)
├── diff.py            # collect_diff(), commit_paths() -- artifact + PR-bound diff (D-09/D-10/D-11)
└── scope.py            # write_scope matching + enforce_write_scope() + revert (D-12/D-13/D-14)
```

`actions/builtins.py`'s `ensure_clean_worktree`/`collect_diff` stay the registered names (D-06 explicitly frames this as "the existing `ensure_clean_worktree` action" becoming real, not being replaced by an unconditional runner.py call like `prepare_role_context`/`store_role_artifacts` were) — but their bodies become thin dispatchers into `dark_factory.git`, performing **only** git-level work, never opening a `Session` (this is enforced today by `test_single_mutation_path.py`, which AST-walks every module under `src/dark_factory/` except `persistence/mutations.py` for `RunEvent`/`RoleExecution`/`HumanInteraction`/`ArtifactReference` construction or `.status` assignment — read this session, still passes trivially for the actions package).

### Pattern 1: Idempotent worktree creation (`git worktree add`)

**What:** One-shot branch+worktree creation, safe to call on every role entry.
**Verified this session** (`git 2.50.1`, real throwaway repo):

```bash
# One-shot: creates the branch AND the worktree together. This is the
# correct invocation -- there is no need for a separate `git branch` +
# `git worktree add <path> <branch>` two-step.
git -C <main-repo> worktree add -b dark-factory/run-<run_id> \
    ../dark-factory-runs/<run_id> <base_branch>
# -> "Preparing worktree (new branch 'dark-factory/run-<run_id>')"
# -> "HEAD is now at <sha> <base_branch's last commit subject>"
# -> exit 0

# Missing parent directories in the target path are auto-created (verified:
# `../deeper/nested/path/nested1` was created with no prior `mkdir`).

# Re-invoking the SAME command a second time (simulating a naive
# "always create" call on every role entry) FAILS:
#   "fatal: a branch named 'dark-factory/run-<run_id>' already exists"
#   exit 255
# -- ensure_worktree() MUST check first, not call `add` unconditionally.
# The cheapest check: `git -C <main-repo> worktree list --porcelain` and
# grep for the target path, OR simply `Path(worktree_path).is_dir()`
# combined with `(worktree_path / ".git").exists()` (a worktree's `.git`
# is a file, not a directory, pointing at the main repo's
# `.git/worktrees/<name>/`).

# An invalid/missing base branch fails cleanly and immediately:
#   "fatal: invalid reference: <bad-base-branch>"
#   exit 128
```

**When to use:** Once per run, the first time `ensure_clean_worktree` fires for the run's first role attempt (see Pattern 2 for exactly where that is). Every later role entry (and every resume) must skip creation and go straight to the detached-HEAD/dirty checks.

**Cleanup (D-04), verified this session:**

```bash
# A worktree with uncommitted/untracked changes refuses removal:
git worktree remove ../dark-factory-runs/<run_id>
# -> "fatal: '<path>' contains modified or untracked files, use --force to delete it"
# -> exit 128

# --force removes it regardless:
git worktree remove --force ../dark-factory-runs/<run_id>
# -> exit 0; `.git/worktrees/<name>/` metadata is cleaned up automatically

# NOTE: by the time COMPLETED is reached, ensure_clean_worktree's dirty-check
# (Pattern 2) has already run on entry to every role INCLUDING the last one
# (QA) -- but there is no "next role entry" hook after the last role
# completes to catch anything QA's own worker left dirty *after* that
# check ran. The COMPLETED cleanup step must therefore run its own
# dirty-check-and-WIP-commit pass (reusing lifecycle.wip_commit_if_dirty)
# immediately before calling `git worktree remove`, or explicitly accept
# --force and document that a stray post-QA uncommitted edit is discarded.
# This is a genuine gap the plan must resolve -- see Open Questions.
```

**No worktree-level lock hazard on reuse, verified this session:** `.git/worktrees/<name>/` contains no `locked` file unless `git worktree lock` was explicitly invoked (a manual opt-in for removable-media worktrees) — sequential reuse of the same worktree path across separate process invocations (simulating a crash + resume by a new process) produced zero contention or error.

### Pattern 2: Detached-HEAD detection and WIP-commit recovery (D-05/D-06/D-07/D-08)

**Detached-HEAD detection, verified this session** — the cleanest check is `git symbolic-ref`, not string-matching `rev-parse`:

```bash
# Attached to a branch: exits 0, prints the ref
git symbolic-ref -q HEAD
# -> "refs/heads/dark-factory/run-<run_id>", exit 0

# Detached: exits 1, prints nothing (the -q suppresses the stderr message)
git symbolic-ref -q HEAD
# -> "", exit 1

# `git rev-parse --abbrev-ref HEAD` also works (prints literal "HEAD" when
# detached, the branch name when attached) but requires string comparison
# against the literal "HEAD" -- symbolic-ref's exit code is a cleaner
# boolean signal with no string-matching hazard (a branch could theoretically
# be misnamed "HEAD", however unlikely).
```

**Dirty-worktree detection (tracked + untracked), verified this session:**

```bash
git status --porcelain=v1 --untracked-files=all
# Empty stdout = clean. Any line = dirty (tracked modifications show as
# " M <path>"/"A  <path>"; untracked files show as "?? <path>", one line
# PER FILE with --untracked-files=all, vs. one line per untracked
# DIRECTORY with the default --untracked-files=normal -- use `all` if the
# WIP commit message should enumerate exactly what was recovered).
```

**WIP commit, verified this session:**

```bash
git add -A
git commit -m "wip(dark-factory): recover uncommitted changes from <role> attempt <N>"
# Stages tracked modifications AND untracked files together, then commits
# directly on the current (working) branch -- exactly D-05's "plain git
# commit ... not a stash". `git rev-parse HEAD` immediately after gives
# the new commit SHA to persist as `role_executions.wip_commit_sha`.
```

**The control-flow gap this creates in `orchestrator/runner.py` (read this session):**

Today, `_run_current_role`'s `_run_hooks("before")` closure (lines ~510-523) calls every configured before-action in a plain `for` loop with no `try/except`, and `ActionRegistry`'s callable type is `Callable[[ActionContext], None]` (read `actions/registry.py` this session) — actions cannot return a value or signal a differentiated outcome today. Two new requirements collide with that shape:

1. **D-08** requires a detached-HEAD entry to fail the role **before the worker is ever called**, using the *exact* shape `_run_current_role`'s existing post-worker `ArtifactError` catch already uses for Phase 4's D-09 schema-violation failure (`signal = Signal.ROLE_FAILED; outcome = {**outcome, "error": str(exc)}`, read `collect_role_artifacts`'s call site this session) — but that existing catch happens *after* `worker.execute`/`worker.resume` has already run and produced a `result`. A before-hook failure has no `result` yet.
2. **D-07** requires the WIP-commit SHA to reach `role_executions.wip_commit_sha` on the **current, already-inserted, still-`RUNNING`** attempt row — but nothing may write that column except `persistence/mutations.py` (the AST-guarded single mutation path, confirmed this session), and the action itself is exactly the kind of module `test_single_mutation_path.py` polices.

**Recommended shape** (grounded in the `_enter_role` precedent already in `runner.py`, which does a self-transition — `next_status == expected_status` — purely to get one more committed write in): treat the before-hook pass as fallible and give it two possible outcomes, handled entirely in `runner.py`, never inside the action:

- `ensure_clean_worktree`'s real body raises a typed `dark_factory.git.lifecycle.DetachedHeadError` (git-only, no DB) when `git symbolic-ref -q HEAD` exits 1. `_run_current_role` wraps the `_run_hooks("before")` call in a `try/except DetachedHeadError`; on catch, it **skips the worker call, the lease-loss check, and the after-hooks entirely**, synthesizes `signal = Signal.ROLE_FAILED` and an `outcome` dict carrying the error message, and falls straight into the existing `elif signal is Signal.ROLE_FAILED:` branch's event/status construction (D-08: "no new failure pathway").
- When the worktree is merely dirty (not detached), the action performs the WIP commit (a pure git write, no DB) and needs the resulting SHA persisted. Because the action cannot open a `Session`, the cleanest option is: `runner.py`, immediately after calling `_run_hooks("before")` successfully, does its own **read-only** `git rev-parse HEAD` against the worktree (no DB, allowed anywhere) and compares it to the attempt's previously-stored `wip_commit_sha` (`None` on a fresh attempt); if the SHA changed, `runner.py` issues one extra small `apply_transition` call — a self-transition exactly like `_enter_role`'s (`next_status == expected_status == state.status`) — that updates only `role_executions.wip_commit_sha` on the current row via a new optional field on `RoleExecutionWrite`.

**Pitfall inside that last step — read carefully before implementing `RoleExecutionWrite`'s update mode:** `_write_role_execution`'s `mode="update"` branch (`persistence/mutations.py`, read this session) is a **full overwrite, not a partial patch** — it unconditionally sets `row.status`, `row.worker_session_id`, `row.result`, `row.error` from whatever the caller supplied, defaulting to `None` for anything not explicitly passed. If `wip_commit_sha` is added the same way (a field that defaults to `None` and is blindly assigned), the **final** `RoleExecutionWrite(mode="update", ...)` call `_run_current_role` already makes after the worker completes (line ~632) would silently **null out** the `wip_commit_sha` set moments earlier by the mid-attempt update, because that later call site has no reason to know about it and would construct its `RoleExecutionWrite` without it. **Recommendation:** make `wip_commit_sha` write-once/sticky inside `_write_role_execution`'s update branch — `if spec.wip_commit_sha is not None: row.wip_commit_sha = spec.wip_commit_sha` (set, never clear) — so a later update call that doesn't mention it leaves the column untouched. This single-line asymmetry (compare-and-set instead of blind-set) is the difference between D-07 working and silently losing data on every attempt that both WIP-recovers *and* completes normally.

### Pattern 3: Artifact-content durability commit (D-09/D-10/D-11)

**Verified this session, full round trip:** a working branch with an interleaved artifact commit and a base branch that advances independently after the branch was cut:

```bash
# After store_role_artifacts / collect_role_artifacts writes filesystem
# content under .dark-factory/runs/<run_id>/ for the just-completed role:
git add -A -- .dark-factory/runs/<run_id>/
git commit -m "chore(dark-factory): <ROLE> artifacts (run <run_id>)"
```

No `ArtifactReference` schema change is needed for this — Neon already stores only metadata (`id, run_id, role_execution_id, type, path, checksum, metadata, created_at`, confirmed by reading `persistence/models.py`'s `ArtifactReference` docstring this session); the commit SHA of the artifact-commit does not need to be tracked in any column for ART-04 to be satisfied — a fresh `git clone` + checkout of the working branch has the content by definition once it is committed.

**The exclusion pathspec and `...` vs `..`, verified this session with a realistic scenario** (base branch gets an unrelated commit *after* the working branch was cut, plus an artifact commit on the working branch):

```bash
git diff <base>...<working> -- . ':(exclude).dark-factory'
```

- `...` (triple-dot / merge-base diff) is confirmed **correct** for a PR-bound diff: it correctly excluded the base branch's own unrelated post-branch-cut commit from the result, showing only the working branch's actual changes relative to their common ancestor — exactly what GitHub's own PR diff view computes.
- `..` (double-dot / direct tree diff) was verified to **incorrectly include** the base branch's unrelated commit as part of "the diff" (it showed the base's own README edit being "reverted" by the working branch, which is not a real change the working branch made) — confirming D-10's choice of `...` over `..` is the right one, not just a stylistic default.
- The `':(exclude).dark-factory'` magic pathspec correctly excluded all `.dark-factory/` content from the diff output in both the triple-dot and double-dot tests, even though `.dark-factory/runs/<id>/` had its own commit interleaved with the code commit — confirming D-10's "exclusion is a path filter at diff-computation time, not a history-restructuring scheme" works exactly as described. This syntax has been supported since Git 1.9 and is unaffected by the `>=2.40` floor.

### Pattern 4: Write-scope enforcement and revert (D-12/D-13/D-14)

**The check (D-14's zero-tolerance polarity, verified by hand-tracing, not just assumed):**

```python
import fnmatch

def is_out_of_scope(path: str, write_scope: list[str]) -> bool:
    """True iff `path` matches none of `write_scope`'s patterns.

    write_scope=[] means "matches none of zero patterns" == True for every
    path -- D-14's zero-tolerance requirement falls out of the empty-list
    case with NO special-case branch needed. Do not add
    `if not write_scope: return False` ("no restriction") -- that inverts
    D-14 (see Pitfall 3).
    """
    return not any(fnmatch.fnmatchcase(path, pattern) for pattern in write_scope)
```

**Revert mechanism, verified this session (the gap the phase brief left to discretion has a real, non-obvious edge case):**

```bash
# A path that exists in HEAD (an edited/staged tracked file): restore wipes
# both the staged and working-tree copy back to the last commit.
git restore --source=HEAD --staged --worktree -- <path>
# -> exit 0

# A path that does NOT exist in HEAD (a brand-new file the role created,
# whether staged or not) FAILS restore outright:
git restore --source=HEAD --staged --worktree -- <path>
# -> "error: pathspec '<path>' did not match any file(s) known to git"
# -> exit 1
# The correct handling for this case is `git clean -f -- <path>` (or a
# plain `Path.unlink()`), never `git restore`. Revert logic MUST branch on
# whether the path existed in HEAD before choosing the mechanism, or a
# violating new file will silently survive enforcement.
```

**Containment defense-in-depth:** before acting on any path reported by `git diff --name-only` (used to enumerate the attempt's changed files for the scope check), resolve it against the worktree root and reject anything that escapes — mirror `artifacts/paths.py::resolve_under_run_root`'s exact T-04-01 pattern (read this session: resolve, `is_relative_to(root)`, raise rather than silently clamp). In practice `git diff` inside a worktree Dark Factory itself created will never emit an escaping path, but the existing codebase treats this class of check as load-bearing everywhere a path crosses a trust boundary, and `write_scope` is exactly such a boundary (ROLE-05 is an authorization control).

**Config-time validation of `write_scope` (Established Patterns note in CONTEXT.md):** `fnmatch` patterns have no compile/validate step that can raise the way a regex does — `fnmatch.translate()` accepts essentially any string. "Malformed pattern" at config-load time (`config/loader.py`, which the docstring says should fail loudly like every other validator there) most plausibly means: an absolute pattern (leading `/`), a pattern containing `..` (escape attempt), or an empty string — not a glob-syntax error, because none exists in `fnmatch`. The planner should pick and document the exact malformed-pattern definition; it is not implied by D-12's text.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecting a detached HEAD | String-parsing `git status` output | `git symbolic-ref -q HEAD` exit code | One git call, one boolean signal, no output parsing (verified this session) |
| gitignore-style path matching | A hand-rolled glob-to-regex translator | `fnmatch.fnmatchcase()` (per the D-12 locked decision) | `fnmatch.translate()` already produces a fully-anchored regex (`(?s:src/.*)\Z`, confirmed this session); a hand-rolled translator would just be re-implementing it with more bug surface |
| Merge-base-aware diffing | Manually finding `git merge-base` then diffing two trees | `git diff base...working` (triple-dot) | Git already computes and caches the merge-base for this exact operator; verified this session it produces the correct PR-bound result with zero extra calls |

**Key insight:** Every operation this phase needs already has a single, direct git-CLI incantation with well-defined exit codes. The risk in this phase is not "missing library" — it's picking the *wrong* stdlib primitive (`pathlib.PurePath.match()` instead of `fnmatch`) or the *wrong* git diff operator (`..` instead of `...`), both of which look superficially reasonable and were only caught by executing them against real repos this session.

## Common Pitfalls

### Pitfall 1: `pathlib.PurePath.match()` is unsafe for `write_scope` — corrects the phase brief's hypothesis

**What goes wrong:** The phase brief hypothesized "`fnmatch` does NOT support `**` recursive glob the way `pathlib`'s `Path.glob`/`PurePath.match` do." Empirical testing this session found the **opposite** is the operationally dangerous case:

```
PurePath("src/app.py").match("src/**")                    -> True
PurePath("src/sub/deep.py").match("src/**")                -> False   (false negative!)
PurePath("other/src/app.py").match("src/**")                -> True   (false positive!)
PurePath("tests/fixtures/src/evil.py").match("src/**")       -> True   (false positive!)

fnmatch.fnmatchcase("src/app.py", "src/**")                 -> True
fnmatch.fnmatchcase("src/sub/deep.py", "src/**")             -> True   (correct)
fnmatch.fnmatchcase("other/src/app.py", "src/**")             -> False  (correct)
fnmatch.fnmatchcase("tests/fixtures/src/evil.py", "src/**")   -> False  (correct)
```

**Why it happens:** `PurePath.match()` (pre-Python 3.13; this project pins `>=3.12`, and `full_match()` — the 3.13 fix — does not exist on 3.12, confirmed by `AttributeError` this session) matches **right-anchored by path-component count**, not left-anchored against the whole path. A 2-component pattern (`"src", "**"`) matches against ANY path's *trailing* two components, regardless of what precedes them — so `tests/fixtures/src/evil.py` (trailing components `src`, `evil.py`) matches `src/**` even though it is nested three levels under `tests/`. It is also not a true recursive glob pre-3.13: a `**` component matches exactly one path segment, not "zero or more segments," so a file two levels below `src/` (`src/sub/deep.py`) is a **false negative**.

**How to avoid:** Use `fnmatch.fnmatchcase(path, pattern)` (not `pathlib` matching) for every `write_scope` check, exactly as `fnmatch.translate("src/**")` → `(?s:src/.*)\Z` implies (verified this session): fully left-anchored, `.*` already crosses `/` boundaries because `fnmatch` has no path-separator concept, so a single `*` and `**` behave identically under `fnmatch` — which happens to be exactly the "recursive" semantics `write_scope` patterns need. Use `fnmatchcase` (not plain `fnmatch.fnmatch`) to pin case-sensitivity independent of `os.path.normcase` platform differences (irrelevant on the project's Linux/macOS targets today, but removes any doubt).

**Warning signs:** A write-scope test suite that only exercises single-level and exactly-two-level paths will not catch either failure mode above — write test cases with 3+ path segments and with a decoy directory (e.g. `tests/fixtures/src/...`) specifically to catch a regression back to `pathlib` matching.

### Pitfall 2: `git restore` fails outright on untracked/new files

**What goes wrong:** A naive revert implementation that always calls `git restore --source=HEAD -- <path>` for every out-of-scope path will raise/fail (exit 1, "pathspec did not match any file(s) known to git") the moment the offending change is a **brand-new file** the role created (as opposed to an edit to an existing tracked file) — verified this session.

**Why it happens:** `git restore --source=HEAD` needs the path to exist in the source it's restoring from; a new untracked file has no HEAD version to restore to.

**How to avoid:** Branch the revert logic on whether the path exists in `HEAD` (`git cat-file -e HEAD:<path>` or check membership in `git ls-tree -r HEAD --name-only`). If it exists: `git restore --source=HEAD --staged --worktree -- <path>`. If it does not: `git clean -f -- <path>` (or delete the file directly and, if staged, `git restore --staged -- <path>` first — `clean` only touches untracked files, so an out-of-scope new file that was `git add`-ed needs its staged entry cleared too).

**Warning signs:** An enforcement test that only covers "role edited an existing out-of-scope file" will pass while "role created a new out-of-scope file" silently leaves the file on disk (and potentially staged) — write both cases explicitly.

### Pitfall 3: Zero-tolerance polarity inversion (D-14)

**What goes wrong:** The intuitive-but-wrong implementation treats an empty `write_scope: []` as "no restriction configured, allow everything" (`if not write_scope: return False  # no violation`). D-14 requires the **opposite**: empty means zero tolerance, every change is a violation.

**Why it happens:** Empty-list-means-unrestricted is a common convention elsewhere in software (e.g., "empty allowlist = no filtering"), and D-14 deliberately inverts it here to match ROLE-01/ROLE-02's "read-only with respect to repository source code" intent.

**How to avoid:** The natural `not any(fnmatchcase(path, p) for p in write_scope)` implementation shown in Pattern 4 gets this right automatically (an empty `write_scope` makes `any()` over an empty iterable `False`, so `not False` is `True` — a violation — for every path) **as long as no early-return special case for the empty list is added**. Do not add one.

**Warning signs:** A test asserting `write_scope=[]` + any changed path → PASS (no violation) is testing the wrong polarity; it should assert FAIL/violation.

### Pitfall 4: Re-invoking `git worktree add` on every role entry

**What goes wrong:** If `ensure_clean_worktree` (or whatever calls it) unconditionally calls `git worktree add -b <branch> <path> <base>` on every role entry rather than only once per run, every entry after the first fails with `fatal: a branch named '...' already exists` (exit 255, verified this session).

**Why it happens:** D-03 requires the worktree be created once and reused; "invoked on every role entry" (D-06) describes the *detached-HEAD/dirty checks*, not worktree creation itself.

**How to avoid:** `ensure_worktree()` must be idempotent — check for existence (`git worktree list --porcelain` or a plain path/`.git`-file existence check) before calling `add`, and skip creation entirely when the worktree already exists.

### Pitfall 5: Terminal-role dirty state has no "next entry" hook to catch it

**What goes wrong:** D-06's dirty-worktree check runs "on every role entry" — but the *last* role (QA in the current 4-role pipeline) has no subsequent role entry to trigger another check after its own worker call leaves the tree dirty. If `COMPLETED` cleanup (D-04) just calls `git worktree remove` (even with `--force`), any uncommitted change QA's own worker produced after its own entry-time check ran is silently discarded.

**Why it happens:** The entry-time check pattern (before the worker runs) has no symmetric exit-time check; D-04's cleanup step is a different code path entirely (triggered by reaching `COMPLETED`, not by a role entry).

**How to avoid:** The `COMPLETED` cleanup step should run the same dirty-check-and-WIP-commit pass (`lifecycle.wip_commit_if_dirty`) immediately before calling `git worktree remove`, not just `--force` through it. Flagged explicitly as an **Open Question** below since CONTEXT.md does not pin this down.

### Pitfall 6: Git subprocess calls should follow the same credential-boundary discipline as worker subprocess calls

**What goes wrong:** `CLAUDE.md`'s subprocess-invocation guidance ("Never `os.environ.copy()` when spawning workers... `role_env` is built from scratch") is written about worker adapters, but the git subprocess calls this phase introduces are the **first** non-worker subprocess spawns the orchestrator makes. If they use `env=None` (inherit-everything, the `subprocess` default) rather than an explicit minimal environment, they are not technically forbidden by any current test, but they diverge from the project's own stated posture.

**Why it happens:** `git` genuinely doesn't need `DATABASE_URL`/`GITHUB_TOKEN`, so it's easy to skip the allowlist discipline "since git doesn't use those anyway" and just inherit the parent environment.

**How to avoid:** Not a hard requirement this phase (SEC-03/TOOL-04 are formally Phase 6), but worth building `dark_factory.git.client._run_git()` with an explicit minimal `env` (`PATH`, `HOME`, `GIT_AUTHOR_*`/`GIT_COMMITTER_*` if needed for deterministic WIP-commit authorship) from day one rather than retrofitting it in Phase 6 — cheaper now than later, and consistent with the project's stated security posture.

## Code Examples

Every example below is verbatim from a real invocation against a throwaway repository this session (`git 2.50.1`), not from documentation or training memory.

### Create the run's branch + worktree (one shot)

```bash
git -C <main_repo_root> worktree add -b dark-factory/run-<run_id> \
    <sibling_dir>/<run_id> <base_branch>
```

### Detect detached HEAD (boolean via exit code)

```bash
git -C <worktree_path> symbolic-ref -q HEAD
# exit 0 = attached (stdout: refs/heads/<branch>); exit 1 = detached (no stdout)
```

### Detect dirty worktree (tracked + untracked)

```bash
git -C <worktree_path> status --porcelain=v1 --untracked-files=all
# empty stdout = clean
```

### WIP-commit recovery

```bash
git -C <worktree_path> add -A
git -C <worktree_path> commit -m "wip(dark-factory): recover uncommitted changes from <role> attempt <N>"
git -C <worktree_path> rev-parse HEAD   # -> the SHA to persist as role_executions.wip_commit_sha
```

### Commit artifact content once per completed role

```bash
git -C <worktree_path> add -A -- .dark-factory/runs/<run_id>/
git -C <worktree_path> commit -m "chore(dark-factory): <ROLE> artifacts (run <run_id>)"
```

### PR-bound diff, artifact-excluded

```bash
git -C <worktree_path> diff <base_branch>...<working_branch> -- . ':(exclude).dark-factory'
```

### List an attempt's changed files (for write-scope enforcement)

```bash
git -C <worktree_path> diff --name-only <base_branch>...<working_branch> -- . ':(exclude).dark-factory'
```

### Revert an out-of-scope tracked file

```bash
git -C <worktree_path> restore --source=HEAD --staged --worktree -- <path>
```

### Revert (remove) an out-of-scope new/untracked file

```bash
git -C <worktree_path> restore --staged -- <path>   # if it was staged; no-op/error-tolerant if not
git -C <worktree_path> clean -f -- <path>
```

### Alembic migration for `role_executions.wip_commit_sha` (mirrors `0003`'s `op.add_column` exactly)

```python
"""wip commit sha -- role_executions.wip_commit_sha

Revision ID: 0005_wip_commit_sha
Revises: 0004_artifacts
Create Date: 2026-09-14
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0005_wip_commit_sha"
down_revision: str | Sequence[str] | None = "0004_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "role_executions", sa.Column("wip_commit_sha", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("role_executions", "wip_commit_sha")
```

This is a direct structural match to `migrations/versions/0003_pause_resume_lease.py`'s `op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))` (read this session) — single nullable column, no server default, no backfill needed (NULL means "no WIP commit for this attempt," exactly analogous to NULL meaning "unclaimed" for the lease columns).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ensure_clean_worktree`/`collect_diff` should stay dispatched through `ActionRegistry` (opt-in via role YAML `before`/`after` lists), requiring all four shipped role YAMLs to be edited to add `before: [ensure_clean_worktree]` — rather than becoming unconditional `runner.py` calls like `build_role_context`/`collect_role_artifacts` did | Architecture Patterns → Pattern 2, Recommended Project Structure | If the planner instead chooses the unconditional-call pattern (mirroring WR-01's `prepare_role_context`/`store_role_artifacts` precedent), the wiring point moves from role YAML to `_advance_once`/`_run_current_role` directly and no role YAML edit is needed — this is a real fork in the design not fully pinned down by CONTEXT.md's D-06 wording, which names "the existing action" but doesn't say how it gets invoked |
| A2 | A new `wip_commit_sha` update to `role_executions` should be made "sticky" (compare-and-set, never blind-overwrite-to-None) inside `_write_role_execution`'s update branch | Architecture Patterns → Pattern 2 | If implemented as a blind overwrite instead, the WIP-commit SHA persisted mid-attempt would be silently nulled by the role's own completion/failure update moments later — a genuine, easy-to-miss data-loss bug, not just a style preference |
| A3 | "Malformed `write_scope` pattern" at config-load time means an absolute path, a `..` escape, or an empty string — not a glob-syntax error (since `fnmatch` has no such error class) | Architecture Patterns → Pattern 4 | If the planner's actual intent is different (e.g., only validating pattern non-emptiness per-role, or no validation at all beyond D-12's "gitignore-style"), a plan built on this assumption adds unnecessary or misaligned validation code |
| A4 | The `COMPLETED` cleanup step (D-04) should run one more dirty-check-and-WIP-commit pass before `git worktree remove`, rather than relying on `--force` to discard any trailing dirty state | Common Pitfalls → Pitfall 5 | If the planner instead accepts `--force`-and-discard as intentional (treating anything left dirty after the terminal role's own entry-check as not worth preserving), no extra pass is needed — but this contradicts the project's stated "durability... nothing lost" framing for D-05/D-06 |
| A5 | A new `EventType` member (e.g. `WIP_COMMIT_CREATED`) should be added for observability when a WIP recovery happens, rather than persisting `wip_commit_sha` with zero accompanying `run_events` row | Open Questions | If the planner decides a status-unchanged `apply_transition` call needs no event at all (technically legal per `apply_transition`'s guard, which only requires an event when `next_status != expected_status`), the column is set with no audit trail — workable but a departure from Phase 2's "declare exactly what you write" `EventType` catalog discipline |

## Open Questions

1. **Does `ensure_clean_worktree`/`collect_diff` stay an opt-in role-YAML hook, or become an unconditional `runner.py` call?**
   - What we know: D-06 explicitly frames it as "the existing `ensure_clean_worktree` action... invoked on every role entry," which reads as staying registry-dispatched (unlike `prepare_role_context`/`store_role_artifacts`, which were explicitly converted to unconditional calls in Phase 4 per the WR-01 precedent, confirmed by reading `builtins.py`'s docstring this session). But no shipped role YAML currently lists either name in `before:`/`after:` (confirmed by reading all four YAMLs this session).
   - What's unclear: If it stays opt-in, all four role YAMLs need a `before: [ensure_clean_worktree]` edit as part of this phase's plan (a config change, not just a code change) — CONTEXT.md doesn't explicitly call this out as a task.
   - Recommendation: Keep it action-registry-dispatched (matches D-06's literal wording) and make the role-YAML edit an explicit plan task; document the choice so a future reader isn't left guessing why `ensure_clean_worktree` "does nothing" if a role YAML omits it.

2. **Should the WIP-commit-recovery event get a new `EventType` member?**
   - What we know: `apply_transition` only *requires* an event when `next_status != expected_status` (read `mutations.py` this session) — a status-unchanged `wip_commit_sha` update is technically legal with `events=()`. The `EventType` catalog's own stated discipline (read `events/catalog.py`'s docstring this session) is "declare exactly what you're about to write, nothing more" — Phase 2 added exactly the four members it needed.
   - What's unclear: CONTEXT.md's decisions don't mention a new event type at all for the WIP-recovery case (only D-08's detached-HEAD failure explicitly says "no new failure pathway, reuses ROLE_FAILED/RUN_FAILED").
   - Recommendation: Add one new member (e.g. `WIP_COMMIT_CREATED`) for observability parity — a durability-and-observability project (per the Core Value statement) silently mutating a column with zero audit trail is a gap worth closing now rather than retrofitting in Phase 12.

3. **What exactly triggers cleanup on `COMPLETED` (D-04), and does it run the dirty-check pass first?**
   - What we know: D-04 says cleanup "happens automatically when a run reaches COMPLETED." The natural wiring point is the same `apply_transition` call in `_run_current_role` that sets `next_status = RunStatus.COMPLETED` for the pipeline's last role — but that call is a DB write, and `git worktree remove` is a git side effect; per the project's "actions never open a session" discipline, the cleanup call itself must happen OUTSIDE the DB transaction, either just before or just after `apply_transition` commits.
   - What's unclear: Before or after the commit? Before risks removing the worktree and then the DB write failing (leaving the DB claiming a still-live worktree that's gone); after risks the reverse (worktree lingers after the DB says COMPLETED, closeable only by a later sweep). Neither is disastrous but the ordering should be a deliberate choice, not an accident of code placement.
   - Recommendation: After the commit succeeds — a lingering worktree after a successfully-recorded `COMPLETED` is a harmless disk-space cleanup gap (recoverable by a future sweep/CLI command), while a removed worktree with a DB write that then fails would be a real (if narrow) data-loss window given `--force` discards uncommitted content.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `git` CLI | Every capability in this phase | ✓ | `2.50.1` (verified `git --version` this session; floor is `>=2.40` per `CLAUDE.md`) | — |
| `alembic` | `wip_commit_sha` migration | ✓ | `>=1.19,<2` (confirmed in `pyproject.toml` this session) | — |
| Python `fnmatch`/`pathlib`/`subprocess` | Everything else | ✓ | stdlib, Python 3.12.7 (verified `python3 --version` this session) | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.1.1` (confirmed pinned in `pyproject.toml`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` (read this session) |
| Quick run command | `uv run pytest -q -m unit` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GIT-01 | Working branch created from configured base, unique per run; every role shares the worktree | unit (real throwaway git repo, no DB) | `uv run pytest tests/unit/test_git_worktree.py -x` | ❌ Wave 0 |
| GIT-01 | Same worktree reused across pause/resume (D-03) | integration | `uv run pytest tests/integration/test_worktree_lifecycle.py -x` | ❌ Wave 0 |
| GIT-02 | No git mutation happens outside the orchestrator's git package (AST guard, mirrors `test_single_mutation_path.py`/`test_no_role_name_literal.py`) | unit | `uv run pytest tests/unit/test_git_ownership_boundary.py -x` | ❌ Wave 0 (recommended, not explicitly required by D-01..D-14) |
| ART-04 | A fresh `git clone` + checkout of the working branch has artifact content available | integration | `uv run pytest tests/integration/test_artifact_cross_clone.py -x` | ❌ Wave 0 |
| ROLE-05 | `write_scope` glob matching: positive, negative, deep-nesting, decoy-directory, zero-tolerance cases | unit | `uv run pytest tests/unit/test_write_scope.py -x` | ❌ Wave 0 |
| ROLE-05 | A violating diff is reverted (both tracked-edit and new-file cases) and the role fails with the D-09 failure shape | integration | `uv run pytest tests/integration/test_write_scope_enforcement.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -q -m unit`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/support/git_repo.py` — a new fixture factory for a throwaway real git repo (init, commit, branch), the git-equivalent of `tests/support/subprocess_runner.py`. No such fixture exists today (confirmed: `tests/support/` contains only `config.py`, `fake_artifacts.py`, `log_sink.py`, `subprocess_runner.py`, read this session).
- [ ] `tests/unit/test_git_worktree.py`, `tests/unit/test_write_scope.py` — new unit test files (git-repo-backed, no DB, no network — fast enough for the `unit` marker per the marker's own definition: "fast, pure-function tests with no database or I/O" — git subprocess calls against a local temp repo arguably stretch "no I/O" slightly but match the spirit far better than `db`/`integration`; confirm this classification with the planner if it's contentious).
- [ ] `tests/integration/test_worktree_lifecycle.py`, `tests/integration/test_artifact_cross_clone.py`, `tests/integration/test_write_scope_enforcement.py` — new integration test files exercising the full `advance()`/`drive()` loop against a real git repo.
- [ ] Migration `0005_wip_commit_sha` + a `tests/db/test_role_executions_wip_commit_sha_schema.py` sibling to the existing `tests/db/test_human_interactions_schema.py` (read this session as the established pattern for a schema-focused DB test).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V1 Architecture | yes | Git subprocess calls use an explicit `args` list, never `shell=True` (mirrors `CLAUDE.md`'s existing worker-invocation rule, read this session) |
| V4 Access Control | yes | `write_scope` enforcement (ROLE-05) is a post-hoc authorization boundary over a role's own diff — Dark Factory computes and enforces it; the worker never controls or bypasses it |
| V5 Input Validation | yes | `write_scope` glob patterns validated at config-load time (see Pattern 4's "malformed pattern" note); diff-derived paths containment-checked before revert (mirror `artifacts/paths.py::resolve_under_run_root`, T-04-01 pattern, read this session) |
| V12 File and Resources | yes | Worktree paths derived from `run_id` (a UUID, low injection risk) but still resolved/contained defensively before any destructive git operation (`worktree remove --force`, `clean -f`) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Command injection via `subprocess` | Tampering | Argument-list `Popen`/`subprocess.run(args, shell=False)`, never string-interpolated shell commands — no branch/run-id/path value is ever concatenated into a shell string |
| Path traversal via a crafted diff path or `write_scope` pattern | Tampering / Elevation of Privilege | Resolve every path under the worktree root and reject escapes before revert/delete, mirroring the existing `resolve_under_run_root` T-04-01 guard |
| Write-scope bypass via a path-matching false positive/negative (Pitfall 1) | Elevation of Privilege | `fnmatch.fnmatchcase`, not `pathlib.PurePath.match` — empirically verified this session; a plan that uses `pathlib` matching for write_scope reintroduces a real authorization bypass |
| Destructive git operation (`worktree remove --force`, `clean -f`) triggered on the wrong path | Tampering / Denial of Service | Every destructive call takes the worktree's own known, DB-derived path — never a path parsed from worker/agent output |

## Sources

### Primary (HIGH confidence — verified this session against the installed toolchain)

- `git 2.50.1` (Apple Git-155), executed this session: `git worktree add -b`, `git worktree remove [--force]`, `git symbolic-ref -q HEAD`, `git status --porcelain=v1 --untracked-files=all`, `git commit`, `git diff <base>...<working> -- . ':(exclude)...'` vs `..`, `git restore --source=HEAD --staged --worktree`, `git clean -f`, `git rev-parse --abbrev-ref HEAD`
- `python3 3.12.7`, executed this session: `fnmatch.fnmatch`/`fnmatch.fnmatchcase`/`fnmatch.translate` vs `pathlib.PurePath.match`/`PurePath.full_match` (confirmed absent on 3.12)
- This repo's own source, read in full this session: `src/dark_factory/actions/builtins.py`, `actions/__init__.py`, `actions/context.py`, `actions/registry.py`, `persistence/models.py`, `persistence/mutations.py`, `persistence/repositories.py`, `config/loader.py`, `config/repo_config.py`, `domain/artifacts.py`, `domain/worker.py`, `domain/signal.py`, `domain/status.py`, `orchestrator/runner.py`, `orchestrator/lease.py`, `orchestrator/lifecycle.py`, `artifacts/paths.py`, `artifacts/validation.py`, `events/catalog.py`, `.dark-factory.yaml`, `.dark-factory/roles/*.yaml`, `.gitignore`, `pyproject.toml`, `migrations/versions/0001`-`0004`, `tests/unit/test_single_mutation_path.py`, `tests/support/*`

### Secondary (MEDIUM confidence)

None used — every claim in this document was either read directly from the repository or verified by executing a real command this session.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, git version verified directly
- Architecture: HIGH — every integration point (action registry shape, mutation-path guard, `apply_transition`'s update semantics) read from source this session; the runner.py control-flow gap is a direct reading of the current code, not speculation
- Pitfalls: HIGH — every pitfall in this document was reproduced with a real command/script this session, not asserted from memory

**Research date:** 2026-09-14
**Valid until:** Stable — git plumbing and stdlib behavior do not drift; re-verify only if the project's `git` floor or Python floor changes, or if `RoleExecutionWrite`/`apply_transition`'s shape changes before this phase is planned
