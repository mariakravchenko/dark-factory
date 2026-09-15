---
phase: 05-isolated-workspace-git-lifecycle
reviewed: 2026-09-15T00:00:00Z
depth: standard
files_reviewed: 49
files_reviewed_list:
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/BA.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - .gitignore
  - .planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md
  - .planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md
  - migrations/versions/0005_wip_commit_sha.py
  - src/dark_factory/actions/builtins.py
  - src/dark_factory/actions/context.py
  - src/dark_factory/config/loader.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/events/redaction.py
  - src/dark_factory/git/__init__.py
  - src/dark_factory/git/client.py
  - src/dark_factory/git/diff.py
  - src/dark_factory/git/lifecycle.py
  - src/dark_factory/git/scope.py
  - src/dark_factory/git/worktree.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/workers/fake.py
  - tests/conftest.py
  - tests/db/test_artifact_commit_per_role.py
  - tests/db/test_artifact_handoff.py
  - tests/db/test_artifact_persistence.py
  - tests/db/test_artifact_schema_violation_fails_role.py
  - tests/db/test_detached_head_fails_role.py
  - tests/db/test_four_role_pipeline.py
  - tests/db/test_role_executions_wip_commit_sha_schema.py
  - tests/db/test_run_owns_a_worktree.py
  - tests/db/test_wip_commit_recovery.py
  - tests/integration/test_artifact_cross_clone.py
  - tests/integration/test_phase5_acceptance.py
  - tests/integration/test_pr_diff_excludes_artifacts.py
  - tests/integration/test_real_pipeline_zero_config.py
  - tests/integration/test_worktree_lifecycle.py
  - tests/integration/test_write_scope_enforcement.py
  - tests/support/config.py
  - tests/support/git_repo.py
  - tests/unit/test_action_registry.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_git_diff.py
  - tests/unit/test_git_lifecycle.py
  - tests/unit/test_git_ownership_boundary.py
  - tests/unit/test_git_push.py
  - tests/unit/test_git_worktree.py
  - tests/unit/test_persistence.py
  - tests/unit/test_redaction.py
  - tests/unit/test_write_scope.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-09-15
**Depth:** standard
**Files Reviewed:** 51 (49 source/test files + 2 planning docs)
**Status:** issues_found

## Summary

Phase 5 is unusually well-documented (every function's docstring states the invariant
it upholds), which made it possible to hold the code to its *own* stated contracts
rather than an external standard — both Critical findings below are places where the
code violates an invariant its own docstring asserts.

The most serious finding (CR-01) is a write-scope/PR-diff blind spot: the single
pathspec constant `ARTIFACT_EXCLUDE_PATHSPEC` (`:(exclude).dark-factory`) is shared
between `enforce_write_scope`'s change-scan and `collect_pr_diff`/`pr_changed_paths`,
and it excludes the *entire* `.dark-factory/` tree — not just the gitignored
`.dark-factory/runs/` subtree the design actually intends to carve out. Because
`.dark-factory/roles/*.yaml`, `.dark-factory/instructions/*.md` and
`.dark-factory.yaml` are ordinary tracked source files (per this repo's own
`.gitignore` comment), a role restricted by `write_scope` can silently rewrite another
role's permissions/instructions and have that change swept into a later role's
WIP-recovery commit (`git add -A`) and pushed to `origin` — invisible to write-scope
enforcement, invisible to the PR-bound diff a human or the future quality gate would
review, and with no audit event. This is exactly the trust-boundary the ROLE-05/D-12
work in this phase exists to police.

The second finding (CR-02) is in the revert mechanism itself: `revert_paths` calls
the path-containment guard (`_resolve_in_worktree`) inside the per-path loop with no
`try`/`except`. If any one violating path is (or resolves through a symlink to) an
escape from the worktree, the `WriteScopeViolation` it raises propagates immediately
and aborts the loop — silently skipping the revert of every violation that was still
queued after it. This directly contradicts `enforce_write_scope`'s own docstring
("this never short-circuits... every violating path is reverted... before the
exception is raised") and `revert_paths`'s own docstring ("never destroy a role's
legitimate work... must never be a worse outcome than the violation it corrects" —
here the mirror failure: it can *leave* violations uncorrected while still reporting
the role FAILED).

Also worth flagging for the human record: `tests/integration/test_write_scope_enforcement.py`
— the integration suite proving CR-01/CR-02's blast radius in practice — is authored
but, per `05-VALIDATION.md` and `deferred-items.md`, has never actually been executed
against a real PostgreSQL 17 in this plan's sandbox. Both Critical findings below are
in code paths that test file was written to exercise, so its still-pending execution
should be treated as high priority, not routine.

## Critical Issues

### CR-01: `ARTIFACT_EXCLUDE_PATHSPEC` excludes all of `.dark-factory/`, not just the gitignored `runs/` subtree — a write-scope and PR-diff blind spot for tracked role config

**File:** `src/dark_factory/git/diff.py:50` (constant), consumed at
`src/dark_factory/git/scope.py:99-113` (`attempt_changed_paths`) and
`src/dark_factory/git/diff.py:171-180`, `src/dark_factory/git/diff.py:205-215`
(`collect_pr_diff` / `pr_changed_paths`)

**Issue:**

`ARTIFACT_EXCLUDE_PATHSPEC = ":(exclude).dark-factory"` is a single constant reused
at every call site that needs to keep "Dark Factory's own machinery" out of
write-scope enforcement and out of the PR-bound diff (per the module docstrings and
`tests/integration/test_pr_diff_excludes_artifacts.py`, which asserts
`".dark-factory" not in three_dot` as an explicit contract). But the only thing that
actually needs excluding — per this repo's own `.gitignore` (`.gitignore:31`,
`.dark-factory/runs/`) and its accompanying comment ("The config set —
`.dark-factory.yaml`, `.dark-factory/roles/`, `.dark-factory/instructions/` — stays
tracked source") — is the ephemeral per-run artifact tree
`.dark-factory/runs/<run_id>/`. The pathspec instead blankets the whole
`.dark-factory/` directory, including the tracked role-permission and
instruction files that `config/loader.py` reads at run creation.

Trace the exploit path:

1. A role (e.g. DEVELOPMENT, `write_scope: ["src/**"]`) writes/modifies
   `.dark-factory/roles/QA.yaml` from inside its own `execute()` — trivially reachable
   for any real coding-agent worker with `repo.write` (DEVELOPMENT already has it).
2. `enforce_write_scope` (`git/scope.py:189-214`) calls `attempt_changed_paths`
   (`git/scope.py:72-116`), which runs both its git invocations with
   `ARTIFACT_EXCLUDE_PATHSPEC` — so the modified `.dark-factory/roles/QA.yaml` is
   **never even returned** as a changed path. `is_out_of_scope` never sees it, so it
   is not reverted and does not fail the role.
3. `commit_run_artifacts` (`git/diff.py:80-142`) only force-adds
   `.dark-factory/runs/<run_id>` — it never stages the tampered file either, so it
   stays dirty and uncommitted in the worktree after this role's step.
4. The *next* role's `before:` hook, `ensure_clean_worktree` →
   `wip_commit_if_dirty` (`git/lifecycle.py:85-108`), runs `git add -A` with **no
   pathspec restriction at all** — it silently absorbs the tampered
   `.dark-factory/roles/QA.yaml` into a `wip(dark-factory): recover uncommitted
   changes from <next-role> attempt <n>` commit, misattributing an unauthorized
   config change to an innocuous "recovery."
5. When that next role itself completes, `push_working_branch`
   (`git/diff.py:219-311`) pushes the *whole* `working_branch` ref to `origin` —
   carrying the WIP commit (and the tampered config inside it) with it.
6. `collect_pr_diff` / `pr_changed_paths` exclude `.dark-factory` with the same
   constant, so the tampering never shows up in the PR-bound diff a human reviewer
   or a future quality gate would read (`git/diff.py:145-217`).

Net effect: a role whose `write_scope` is supposed to confine it to `src/**` (or to
nothing, for BA/ARCHITECTURE) can rewrite another role's `write_scope`,
`tools`, or instruction text, have it committed under a misleading "WIP recovery"
message, pushed to `origin`, and never appear anywhere the enforcement mechanism or
the PR diff would surface it. This defeats the entire ROLE-05/D-12/D-13/D-14
authorization boundary this phase built, for exactly the class of file
(`.dark-factory/roles/*.yaml`) that boundary exists to protect.

(The current in-flight run itself is not compromised by this — `RunState.workflow`
is a snapshot taken once at `create_run` and never re-read from disk — but the
*published git history* is, which matters the moment a human merges the PR, or a
later run reconstructs a worktree from this same branch per D-15.)

**Fix:** Scope the exclusion to exactly the ignored subtree, not the whole config
directory:

```python
# src/dark_factory/git/diff.py
ARTIFACT_EXCLUDE_PATHSPEC = ":(exclude).dark-factory/runs"
```

This keeps every existing guarantee (Dark Factory's own per-run artifact content
stays out of write-scope enforcement and out of the PR diff) while making tracked
role config, instructions, and `.dark-factory.yaml` itself subject to the same
write-scope enforcement and PR-diff visibility as any other source file — which is
what `.gitignore`'s own comment already says the intended boundary is. After this
change, an edit to `.dark-factory/roles/*.yaml` by a role with a non-matching
`write_scope` (i.e. every shipped role, since none of them declare `.dark-factory/**`
in `write_scope`) is caught, reverted, and fails the role, exactly like any other
out-of-scope write — and a *legitimate* edit to `.dark-factory/roles/*.yaml` (if a
future role is ever intentionally granted that scope) becomes visible in the PR diff
for human review, which is the behavior this whole phase is trying to guarantee.

---

### CR-02: `revert_paths` aborts mid-loop on a path-containment failure, leaving queued violations un-reverted

**File:** `src/dark_factory/git/scope.py:142-186` (`revert_paths`), specifically
the unguarded `_resolve_in_worktree` call at `src/dark_factory/git/scope.py:173`

**Issue:**

```python
def revert_paths(worktree: Path, paths: Sequence[str]) -> None:
    for path in paths:
        _resolve_in_worktree(worktree, path)          # <-- raises WriteScopeViolation, uncaught
        in_head = run_git(["cat-file", "-e", f"HEAD:{path}"], cwd=worktree, check=False)
        if in_head.returncode == 0:
            run_git(["restore", "--source=HEAD", "--staged", "--worktree", "--", path], cwd=worktree)
        else:
            run_git(["rm", "--cached", "--force", "--quiet", "--", path], cwd=worktree, check=False)
            run_git(["clean", "--force", "--", path], cwd=worktree)
```

`_resolve_in_worktree` (`git/scope.py:119-139`) is the path-containment guard the
review was specifically asked to check — and it is correct in isolation: a path that
resolves (following symlinks, since `Path.resolve()` follows them) outside the
worktree raises `WriteScopeViolation` naming the escape. The bug is in how
`revert_paths` uses it: the call sits **inside** the `for path in paths:` loop with
no `try`/`except` around it, so the very first path in the (sorted) violation list
whose resolution escapes the worktree — e.g. a worker-created symlink
(`ln -s /etc/passwd tests/evil`) that `git status`/`git ls-files --others` reports as
a changed path — raises immediately and unwinds out of `revert_paths` entirely.

`enforce_write_scope` (`git/scope.py:189-214`) calls `attempt_changed_paths` once,
computes the **complete** sorted `violations` list, and only then calls
`revert_paths(worktree, violations)` — its own docstring states plainly: "Every
changed path is checked — this never short-circuits on the first violation... When
any violation exists, every violating path is reverted **before** the exception is
raised: the caller must never be able to accept a failure that left an out-of-scope
change on disk." That promise is only honored for violations that sort
alphabetically *before* the escaping path. Every violation after it in the sorted
list is never passed to `git restore` / `git rm` / `git clean` at all — the role
still ends up `ROLE_FAILED` / `RUN_FAILED` (since the exception, now re-raised as
`WriteScopeViolation` from `_resolve_in_worktree`, is still caught by
`orchestrator/runner.py`'s `except WriteScopeViolation` at `orchestrator/runner.py:894`),
but the worktree is left holding one or more un-reverted out-of-scope changes that
the failure report implies were cleaned up.

This is exploitable predictably: since `violations` is lexicographically sorted
(`git/scope.py:207`), an attacker who controls multiple out-of-scope filenames can
choose one whose name sorts early and that escapes containment (a symlink), forcing
every alphabetically-later violation to survive uncorrected on disk while the role
still reports "reverted and failed."

**Fix:** Make the loop resilient to a single path's containment failure instead of
letting it abort the whole batch — either skip only the escaping path (logging it)
while still reverting every other queued violation, or collect containment failures
separately and raise once after every revertible path has been processed:

```python
def revert_paths(worktree: Path, paths: Sequence[str]) -> None:
    escapes: list[str] = []
    for path in paths:
        try:
            _resolve_in_worktree(worktree, path)
        except WriteScopeViolation:
            escapes.append(path)
            continue
        in_head = run_git(["cat-file", "-e", f"HEAD:{path}"], cwd=worktree, check=False)
        if in_head.returncode == 0:
            run_git(
                ["restore", "--source=HEAD", "--staged", "--worktree", "--", path],
                cwd=worktree,
            )
        else:
            run_git(["rm", "--cached", "--force", "--quiet", "--", path], cwd=worktree, check=False)
            run_git(["clean", "--force", "--", path], cwd=worktree)
    if escapes:
        raise WriteScopeViolation(
            f"write-scope paths escape worktree {worktree.resolve()}: {escapes!r}"
        )
```

This preserves the "every non-escaping violation is reverted before any exception
propagates" guarantee the docstrings already promise, and still fails loudly (a path
that resolves outside the worktree is itself worth surfacing distinctly) without
silently leaving other, perfectly revertible violations behind.

## Warnings

### WR-01: `git rm --cached` failure in `revert_paths`'s new-file branch is unconditionally swallowed before `git clean` still runs

**File:** `src/dark_factory/git/scope.py:180-186`

**Issue:** For a path absent from `HEAD`, `revert_paths` runs
`git rm --cached --force --quiet -- path` with `check=False`, documented as
tolerating "a path that was never staged" as a no-op-shaped failure. But `check=False`
also swallows any *other* reason that command could fail (permission error, a
corrupted index entry, an unexpected git-level conflict) with identical silence, and
`git clean --force -- path` is then attempted unconditionally regardless of why the
first command failed. If the real failure reason was something `git clean` cannot
itself resolve, the loop proceeds as though cleanup succeeded.

**Fix:** At minimum, distinguish the expected "not staged" case from an unexpected
failure by checking `in_head.returncode` semantics more precisely, or capture and
log `stderr` on a non-zero, non-"pathspec did not match" exit so an operator has a
trail if this branch ever masks a real git-level problem.

### WR-02: `tests/integration/test_write_scope_enforcement.py` — the test suite proving CR-01/CR-02's real-world blast radius — has not been executed against a real database

**File:** `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md:48`,
`.planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md`

**Issue:** Per the phase's own validation tracker, the row for
`tests/integration/test_write_scope_enforcement.py` is marked "⬜ pending —
DB-reachability handoff," meaning the newly-landed `enforce_write_scope` wiring in
`orchestrator/runner.py` (the last piece of this phase, called out explicitly as
"not yet reviewed" in this review's brief) has never actually been run end-to-end
against a real PostgreSQL 17. The test file itself (read during this review) is
well-constructed and would very likely have caught neither CR-01 nor CR-02 as
written (it does not touch `.dark-factory/roles/*.yaml` or symlink escapes), but its
un-executed status means even the behaviors it *does* claim to prove (tracked-edit
revert, new-file revert, zero-tolerance empty scope, cross-role isolation, artifact
survives a scope failure) are unverified in this sandbox.

**Fix:** Run `uv run pytest tests/integration/test_write_scope_enforcement.py -x`
against a reachable PostgreSQL 17 before this phase is considered done, and add
regression coverage for CR-01 (a role writing to `.dark-factory/roles/*.yaml`) and
CR-02 (a symlink-escape violation alongside an ordinary one) once fixed.

### WR-03: `_run_current_role`'s `write_scope` default duplicates D-14 polarity logic at a second call site with no shared helper

**File:** `src/dark_factory/orchestrator/runner.py:886`

**Issue:** `write_scope = (role_def.get("permissions") or {}).get("write_scope", [])`
re-derives, inline in the orchestrator, the same "missing/empty means zero
tolerance" default that `RolePermissions.write_scope` already encodes as a pydantic
`default_factory=list` in `config/loader.py:70`. Both call sites currently agree
(empty list either way), so this is not a live bug, but a future refactor that
changes the default in one place (e.g. to make an *absent* `permissions` key mean
something other than zero tolerance) would silently diverge from the other, and
nothing enforces the two stay in sync — the D-14 invariant this phase treats as
"the load-bearing fact a future reader must not miss" is currently expressed twice,
independently.

**Fix:** Low priority; consider having `_role_definition`'s bare-string fallback (or
a shared constant) be the single source of the `[]` default, so a future edit to one
cannot silently diverge from the other.

## Info

### IN-01: `dirty_paths` is public API with no production caller

**File:** `src/dark_factory/git/lifecycle.py:57-70`

**Issue:** `dirty_paths` is exported from the package (`git/__init__.py`) and
covered by unit tests, but nothing under `src/dark_factory/` outside
`lifecycle.py` itself (`is_dirty` calls it) currently consumes it. Not a defect —
it is reasonable public surface for a git-primitives module — just noting it as
currently untethered to any production call site, should a future reviewer wonder
why it exists.

**Fix:** None required; keep as-is or note its intended future consumer (e.g. a
richer WIP-recovery audit payload) in the docstring if one is already planned.

---

_Reviewed: 2026-09-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
