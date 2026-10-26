# Phase 5: Isolated Workspace & Git Lifecycle - Context

**Gathered:** 2026-09-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Every run creates an explicit working branch off the configured base branch, unique to the run id, and gets a real isolated `git worktree` that every role in the pipeline executes against — the same worktree, reused across pause/resume, not re-cloned per attempt. Dark Factory owns all git actions (branch creation, WIP recovery, diff collection); agents never own commit/push/PR policy. Artifact content written under `.dark-factory/runs/<run-id>/` becomes durable across machines by being committed to the run's working branch (resolves Open Decision 1), while staying excluded from the diff that will eventually become the PR. A role that leaves uncommitted changes is recovered (WIP-committed) on next entry rather than losing work; a role that somehow enters on a detached HEAD fails loudly instead of proceeding. A role's diff is checked against its configured `write_scope` after every attempt, with out-of-scope changes reverted and logged (ROLE-05).

Out of scope for this phase: real multi-machine transport (SSH, rsync, actual "another machine" orchestration) — the requirement is that a fresh `git clone` + checkout of the working branch has the artifact content available, not that Dark Factory performs the cross-machine hop itself (that's Phase 11's cross-process/cross-machine resume). Quality-gate diff *use* (Phase 9) and actual PR creation (Phase 10) are not this phase — this phase only makes `collect_diff` produce a clean, artifact-excluded diff.

</domain>

<decisions>
## Implementation Decisions

### Branch & worktree lifecycle
- **D-01:** Working branch is named `dark-factory/run-{run_id}` — namespaced prefix groups all Dark Factory branches; the run's UUID guarantees uniqueness with no slugification or collision logic needed.
- **D-02:** The run's worktree is a real `git worktree add`, sibling to the main repo checkout (e.g. `../dark-factory-runs/{run_id}/`) — not nested inside `.dark-factory/runs/<id>/` inside the repo itself, since `git worktree` expects a path outside the tree it's a worktree of.
- **D-03:** The same worktree is reused across every role attempt and across a pause/resume cycle — it is not recreated on resume. This is required for WIP-commit recovery (D-05/D-06) to have something to recover from; recreating fresh on resume would silently discard anything not yet committed.
- **D-04:** Worktree cleanup (`git worktree remove`) happens automatically when a run reaches `COMPLETED`. A run that reaches `FAILED` keeps its worktree on disk for post-mortem debugging — no automatic cleanup on failure.
- **D-15 (added after initial discussion, before execution):** `ensure_worktree` has a third path, not just "reuse local dir" vs. "create fresh with `-b`": when no local worktree exists AND the working branch already has commits reachable from `origin` (a prior role attempt advanced this same run on a *different* ephemeral disk — the local→CI handoff case named in the project's Core Value statement), it reconstructs the worktree from that branch instead of erroring or silently creating a divergent branch. Mechanism, verified against a real repo: check `refs/heads/<branch>` locally first (same-disk-but-different-path case), else best-effort `git fetch origin <branch>` (a network failure or a branch that was never pushed both surface as the same non-zero exit — no special-casing needed) then check `refs/remotes/origin/<branch>`; if found, `git worktree add -B <branch> <target> refs/remotes/origin/<branch>`. Only when the branch is unreachable both locally and via `origin` does it fall through to the original create-fresh `-b` path. This does not weaken D-03 — "same worktree reused, not recreated" — because it only ever fires when no local worktree exists yet; it never recreates or resets a worktree that is already there.

### WIP-commit recovery & detached HEAD
- **D-05:** An uncommitted-changes recovery is a plain `git commit` directly on the run's working branch (not a `git stash`), with a generated message such as `wip(dark-factory): recover uncommitted changes from <role> attempt N`. Simpler mental model than a stash object, no extra git-object garbage-collection risk.
- **D-06:** The recovery/detached-HEAD check lives inside the existing `ensure_clean_worktree` action (currently a permanent no-op per `src/dark_factory/actions/builtins.py`), invoked on every role entry — this phase is exactly the "later phase named in its own docstring" that action was written for. It becomes real: check for a detached HEAD (fail immediately if so) and check for dirty worktree state (WIP-commit if so), before the role's worker is invoked.
- **D-07:** The WIP commit SHA is persisted on a new `role_executions.wip_commit_sha` column — ties the recovered commit directly to the specific attempt that produced it, consistent with the existing per-attempt `RoleExecution` row pattern from Phases 1–2.
- **D-08:** A detached-HEAD entry fails the role using the exact same shape as Phase 4's schema-violation failure (D-09 in 04-CONTEXT.md): persists a `FAILED` `role_execution` + a `run_events` error entry, transitions the run to `FAILED` immediately. No new failure pathway — reuses the established pattern.

### Artifact durability — commit mechanics (resolves Open Decision 1)
- **D-09:** Dark Factory commits `.dark-factory/runs/<run-id>/` artifact content to the working branch once per completed role (not per individual artifact file) — e.g. `chore(dark-factory): BA artifacts (run <id>)` right after `store_role_artifacts` writes the filesystem content for that role. One commit per role attempt, easy to bisect which role produced what.
- **D-10:** `collect_diff` (currently a no-op, becomes real this phase) computes the PR-bound diff against the base branch with a path exclusion for `.dark-factory/` — e.g. `git diff base...working -- . ':(exclude).dark-factory'`. Artifact-content commits and code commits can interleave freely on the working branch; the exclusion is a path filter at diff-computation time, not a history-restructuring or commit-tagging scheme.
- **D-11:** `.dark-factory/runs/<run-id>/` is fully tracked, committed content on the run's working branch (required for SC2 — a fresh clone must have it) but is gitignored on the base branch (e.g. `main`), so it never leaks into the repository's permanent history once a PR from the working branch is eventually merged.
- **D-16 (added after initial discussion, before execution — closes a real durability gap found while implementing D-15).** D-09's artifact commit is `git push`ed to `origin` immediately after it is made — not deferred until Phase 10's publish step. Without this, D-09/D-11's "durable... by being committed to the run's working branch" is only true while the disk that made the commit survives; on an ephemeral CI runner (ordinary GitHub-Actions-style execution, ordinary — not exotic — per the project's own Core Value statement naming "a local→CI handoff... after a crash" as headline durability), that disk is destroyed the moment the job ends, and nothing was ever pushed. A retry on a fresh runner would then find nothing via D-15's reconstruction path and silently restart the run's git history from scratch, discarding every already-completed role's work. Mechanics:
  - **Auth:** the push uses `Settings.github_token` (already loaded, previously only used for redaction registration — see `settings.py`). The orchestrator (`runner.py`) reads it and passes the raw value into the git package as a parameter; the git package itself stays config-ignorant, matching its existing "explicit paths and plain values in, explicit paths and plain values out" discipline.
  - **Credential handling:** the token is supplied to `git push` via `GIT_ASKPASS` (a short-lived helper script reading the token from a dedicated environment variable), never embedded in the remote URL and never passed as a subprocess argument — an argv-embedded or URL-embedded token is visible to any co-resident process via `ps` and tends to get echoed back verbatim in git's own failure messages. The dedicated env var is scoped to the push call only, not added to `git_env()`'s general allowlist, so no other git invocation carries it.
  - **Retry:** wrapped in a bounded `tenacity` retry (already a project dependency, and CLAUDE.md's own stack guidance names `git push` explicitly as something tenacity should wrap) — a transient network failure should not fail an otherwise-successful role.
  - **Failure after retries exhausted:** folds into the *same* `except GitError` block that already catches `commit_run_artifacts` failures (05-03 Task 2's existing wiring) — no new failure vocabulary, no new `EventType` member, consistent with that task's own explicit "do not add a new event type" rule for git errors at this exact point. A push that never recovers is treated exactly like a commit that never happened: the role fails loudly.
  - **No push if no token configured:** a repository/environment with no `GITHUB_TOKEN` set (e.g. plain local development against a repo with no configured push credentials) skips the push silently and keeps the local commit — this is not a regression, since push simply didn't exist before D-16, and CI environments are expected to always have the token configured.
  - **What this does NOT cover, left explicit rather than silently assumed:** mid-role uncommitted work (before a WIP-commit or artifact-commit ever happens) is still only as durable as the disk it's on — D-16 only pushes committed content, and a role that crashes before committing anything has nothing yet to push. Extending push to the WIP-commit path (05-02) as well is a natural follow-on, deliberately left out of this addition's scope rather than expanded further without a separate decision.
  - **Exposure-timing consequence, explicitly confirmed (not just inferred from D-09/D-11's existing rating).** Pushing per-role means a run's git history is visible on GitHub before the pipeline finishes — including for a run that later fails QA or the Quality Gate and never reaches Phase 10. Confirmed acceptable: the branch is namespaced (`dark-factory/run-*`) and never touches `main`, so nothing merges without review regardless of when it became readable — this only changes *when* work-in-progress becomes visible, not what can be merged without a gate.

### Write-scope enforcement (ROLE-05)
- **D-12:** `write_scope` entries in role YAML are glob patterns (e.g. `write_scope: ["src/**"]` for Developer, `write_scope: ["tests/**"]` for QA), matched via `fnmatch`/`pathlib` globbing against each changed path in the role's diff — gitignore-style, familiar, and more expressive than a plain prefix match (can scope by extension or exclude a subdirectory).
- **D-13:** Enforcement runs immediately after a role's worker returns `COMPLETED`, before the attempt is accepted/transitioned: diff the attempt's changes, check every changed path against `write_scope`, revert any violating path, and fail the role if any violation was found. This is the same "before advancing" ordering as the D-09 (Phase 4) schema-violation check.
- **D-14:** An empty `write_scope: []` (BA and Architect's current placeholder value in every shipped role YAML) means **zero tolerance** — any change at all is a violation. This matches the stated ROLE-01/ROLE-02 intent ("read-only with respect to repository source code") rather than silently skipping enforcement for those roles.

### Claude's Discretion
- Exact revert mechanism for an out-of-scope path (`git checkout -- <path>` vs `git restore` vs a targeted patch reversal) — left to planning as long as the offending change does not survive into a commit.
- Exact commit-message trailer/format conventions beyond the illustrative examples above, as long as they're distinguishable in `git log` from a role's real work commits.
- Whether `ensure_clean_worktree`'s detached-HEAD/dirty-worktree checks run as one combined pass or two sequential checks — implementation detail, not a behavior difference.
- **Known, accepted limitation of D-15's reconstruction path:** if `git fetch origin <branch>` fails for a *transient* reason (network blip) while the branch genuinely has unpushed-visibility commits on `origin`, `ensure_worktree` cannot distinguish that from "branch never existed" and falls through to creating a fresh branch with the same name — a local/remote divergence. This is not silent forever: a later `git push` of that branch is rejected by git's own non-fast-forward check, surfacing the problem rather than losing history outright. Deemed acceptable for this phase (rare transient-failure-during-reconstruction window, self-detecting via push rejection); not deferred to Phase 11 silently — recorded here so a future reader doesn't mistake it for an oversight.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — GIT-01, GIT-02, ART-04, ROLE-05 (this phase's full requirement set)
- `.planning/ROADMAP.md` §"Phase 5: Isolated Workspace & Git Lifecycle" — goal, success criteria, invariants ("agents never own commit/push/PR policy"; "git effects are guarded by persisted identifiers before acting"), and the Open Decision 1 resolution note

### Existing domain/config contracts this phase extends
- `src/dark_factory/actions/builtins.py` — `ensure_clean_worktree` and `collect_diff`, both currently permanent no-ops with docstrings naming this exact phase as where they become real (D-06, D-10); read the module docstring's WR-01 explanation of which actions are permanent no-ops vs. real hooks before changing either
- `src/dark_factory/actions/__init__.py` — where `ensure_clean_worktree`/`collect_diff` are registered in `default_registry`
- `src/dark_factory/persistence/models.py` — `Run.base_branch` / `Run.working_branch` columns, present since Phase 1 (0001 migration) but unused until now (D-20 in 01-CONTEXT.md); this phase adds `role_executions.wip_commit_sha` (D-07) via a new Alembic revision
- `src/dark_factory/config/loader.py` — `RolePermissions.write_scope: list[str]` (currently `default_factory=list`, docstring says "stored in the snapshot, enforced in Phase 5") — this phase implements the enforcement (D-12–D-14)
- `.dark-factory/roles/*.yaml` — all four shipped role YAMLs currently declare `write_scope: []`; BA/ARCHITECTURE keep zero-tolerance (D-14), DEVELOPMENT/QA need real glob patterns added (D-12)
- `.dark-factory/config.yaml` / `.dark-factory.yaml` — `repository.base_branch: main`, the base every run's working branch is created from
- `src/dark_factory/domain/artifacts.py` — docstring notes `changed_files` stays empty in Phase 4 "until there is no git worktree until [Phase 5]" — this phase is expected to populate it
- `src/dark_factory/orchestrator/lease.py` — docstring flags a coordination point for "agent subprocesses on a shared worktree" landing at Phase 7; Phase 5's worktree design should not foreclose that
- `.planning/phases/01-walking-skeleton-one-durable-run/01-CONTEXT.md` D-20/D-21 — the original recorded intent this phase now implements: `base_branch`/`working_branch` columns exist for this reason; artifact durability's leading option (commit to `.dark-factory/`, excluded from published diff) was recorded here and is now locked by D-09–D-11 above
- `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-CONTEXT.md` D-09 — the schema-violation failure shape reused by D-08 (detached HEAD) and D-13 (write-scope enforcement)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ensure_clean_worktree` / `collect_diff` action stubs (`actions/builtins.py`) — already registered in `default_registry`, already invoked wherever role YAML names them; this phase fills in their bodies rather than wiring new hook points.
- `Run.base_branch` / `Run.working_branch` columns — already exist and are already rendered in `dark-factory status` output (`observability/status.py`) and `domain/views.py`; this phase is the first to populate them with real values.
- `RoleExecution` per-attempt row pattern (established Phases 1–2) — D-07's `wip_commit_sha` column is a natural sibling addition, following the same pattern Phase 4 used for `inputs`/context scoping.
- The D-09 (Phase 4) schema-violation failure shape — reused verbatim by both D-08 (detached HEAD) and D-13 (write-scope violation): persisted `FAILED` `role_execution` + `run_events` error entry + immediate `FAILED` transition. No new failure pathway needed anywhere in this phase.

### Established Patterns
- Config validation fails loudly with typed errors before any run/row is created (`config/loader.py`) — `write_scope` glob validation (D-12) should follow the same fail-loud convention at config-load time for malformed patterns, not silently at diff time.
- `frozen=True, extra="forbid"` on every pydantic boundary model — any new domain model this phase introduces (if any) should match.
- Actions that touch mutation-path state are forbidden from opening a database session (WR-01 constraint enforced by `tests/unit/test_single_mutation_path.py`) — `ensure_clean_worktree` and `collect_diff` must stay read/git-only; any persistence of `wip_commit_sha` or a run-event must happen in `orchestrator/runner.py`'s mutation path, not inside the action itself.

### Integration Points
- `orchestrator/runner.py` — the unconditional per-role call sites (mirroring `build_role_context`/`collect_role_artifacts`) are where worktree creation, WIP-recovery invocation, and write-scope enforcement likely get wired in, per the WR-01 precedent that mutation-adjacent steps aren't role-YAML-configurable hooks.
- `src/dark_factory/domain/artifacts.py` — `changed_files` on `WorkerResult`/artifact models needs real content once `collect_diff` is real.

</code_context>

<specifics>
## Specific Ideas

No particular branch-naming or commit-message text was specified beyond what's captured in the decisions above (D-01, D-05, D-09) — user deferred exact string formats to Claude's discretion within the stated conventions.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Cross-machine clone/transport orchestration was explicitly noted as Phase 11's concern, not raised as a new capability by the user.

### Reviewed Todos (not folded)
None — `.planning/todos/` had zero matches for Phase 5 (`todo.match-phase` returned `todo_count: 0`).

</deferred>

---

*Phase: 5-Isolated Workspace & Git Lifecycle*
*Context gathered: 2026-09-14*
