"""Branch naming and idempotent worktree lifecycle (GIT-01, D-01, D-02, D-03,
D-04, D-15).

Follows ``artifacts/paths.py``'s "compute the deterministic path, check
existence, only act if missing" idiom. Every function takes ``repo_root`` and
``run_id`` explicitly -- nothing here reads ``Path.cwd()``, opens a
``Session``, or touches configuration.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dark_factory.git.client import run_git
from dark_factory.git.errors import WorktreePathError

__all__ = [
    "WORKTREE_PARENT_DIRNAME",
    "ensure_worktree",
    "remove_worktree",
    "working_branch_name",
    "worktree_path",
]

WORKTREE_PARENT_DIRNAME = "dark-factory-runs"


def working_branch_name(run_id: UUID) -> str:
    """``dark-factory/run-<run_id>`` (D-01) -- a pure string function with no
    I/O, so ``persistence/mutations.py::create_run`` can call it inside its
    transaction. Two distinct run ids always produce two distinct names, with
    no slugification step."""
    return f"dark-factory/run-{run_id}"


def worktree_path(repo_root: Path, run_id: UUID) -> Path:
    """A sibling of ``repo_root`` (D-02): ``<repo_root's parent>/dark-factory-runs/<run_id>/``.

    Never a descendant of ``repo_root`` -- git refuses to nest a worktree
    inside the tree it is a worktree of.
    """
    return repo_root.resolve().parent / WORKTREE_PARENT_DIRNAME / str(run_id)


def ensure_worktree(
    repo_root: Path,
    run_id: UUID,
    *,
    base_branch: str | None,
    working_branch: str | None,
) -> Path:
    """Idempotently create-or-reuse the run's worktree; return its path.

    Raises :class:`~dark_factory.git.WorktreePathError` naming the run id
    when ``working_branch`` is ``None`` -- a run created before this phase,
    or a caller that skipped the persisted column -- never re-derives the
    name, because the persisted value is the identifier every later git
    effect is guarded by.

    Three paths, checked in this order (D-15):

    1. **same-disk reuse** -- the target already has a ``.git`` marker;
       return immediately with no git call at all (idempotency, RESEARCH
       Pitfall 4). A worktree's ``.git`` is a *file* pointing at
       ``<main>/.git/worktrees/<name>/``, so its presence is a sufficient,
       cheap existence marker.
    2. **reconstruction** -- no local worktree exists yet, but the branch may
       already carry commits from a different attempt of this same run (a
       local ref, or one fetched from ``origin``) -- the local->CI-handoff /
       ephemeral-runner case. Once a ref (local or remote-tracking) for
       ``working_branch`` is found, this always wins over path 3 -- creating
       a fresh ``-b`` branch under the same name once real history exists
       would silently fork a divergent history.
    3. **first-ever creation** -- the branch exists nowhere reachable; create
       the branch and the worktree together in one verified invocation.
    """
    if working_branch is None:
        raise WorktreePathError(
            f"run {run_id} has no persisted working_branch; refusing to "
            "re-derive a branch name"
        )

    target = worktree_path(repo_root, run_id)

    # Path 1 -- same-disk reuse.
    if target.is_dir() and (target / ".git").exists():
        return target

    # Path 2 -- reconstruction (D-15). A local ref already exists (same
    # disk, different worktree path -- e.g. an operator moved the sibling
    # directory)?
    local_ref = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{working_branch}"],
        cwd=repo_root,
        check=False,
    )
    if local_ref.returncode == 0:
        run_git(["worktree", "add", str(target), working_branch], cwd=repo_root)
        return target

    # Best-effort fetch: a network failure and "branch never pushed" both
    # surface as a non-zero exit and both mean the same thing here, so do
    # not branch on the fetch's own return code -- only on what it leaves
    # behind. A repository with no `origin` remote at all hits this same
    # non-zero-exit path and falls through to Path 3 exactly like any other
    # "branch not found" case.
    run_git(["fetch", "origin", working_branch], cwd=repo_root, check=False)
    remote_ref = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{working_branch}"],
        cwd=repo_root,
        check=False,
    )
    if remote_ref.returncode == 0:
        # `-B` (not `-b`) resets/creates the local branch at that start
        # point -- "reconstruct from the latest pushed checkpoint".
        run_git(
            [
                "worktree",
                "add",
                "-B",
                working_branch,
                str(target),
                f"refs/remotes/origin/{working_branch}",
            ],
            cwd=repo_root,
        )
        return target

    # Path 3 -- first-ever creation. The branch exists nowhere reachable.
    if base_branch is None:
        raise WorktreePathError(
            f"run {run_id} has no persisted base_branch; cannot create a "
            "fresh worktree with no known start point"
        )
    run_git(
        ["worktree", "add", "-b", working_branch, str(target), base_branch],
        cwd=repo_root,
    )
    return target


def remove_worktree(repo_root: Path, run_id: UUID, *, force: bool = False) -> bool:
    """Remove the run's worktree; return whether one existed to remove.

    Declared here now; plan 05-03 wires this to the ``COMPLETED`` transition
    (D-04).
    """
    target = worktree_path(repo_root, run_id)
    if not target.exists():
        return False
    run_git(
        ["worktree", "remove", *(["--force"] if force else []), str(target)],
        cwd=repo_root,
    )
    return True
