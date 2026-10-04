"""WIP-recovery and detached-HEAD primitives (GIT-01, GIT-02, D-05, D-06, D-08).

No database access anywhere in this module -- every function takes an explicit
``worktree`` path and returns a plain value or raises a typed error from
``dark_factory.git``'s hierarchy. This is what lets ``actions/builtins.py``'s
``ensure_clean_worktree`` dispatch into these functions while staying git-only
(WR-01): nothing here opens a ``Session`` or constructs a lifecycle ORM row.
"""

from __future__ import annotations

from pathlib import Path

from dark_factory.git.client import run_git
from dark_factory.git.errors import DetachedHeadError

__all__ = [
    "WIP_COMMIT_SUBJECT_PREFIX",
    "assert_attached_head",
    "dirty_paths",
    "head_sha",
    "is_dirty",
    "wip_commit_if_dirty",
]

# A module constant so the recovery commit's subject is greppable from
# ``git log`` and cannot drift between the writer here and any test/tool that
# looks for it (e.g. ``tests/integration/test_worktree_lifecycle.py``).
WIP_COMMIT_SUBJECT_PREFIX = "wip(dark-factory):"


def head_sha(worktree: Path) -> str:
    """The worktree's current ``HEAD`` commit SHA, stripped."""
    return run_git(["rev-parse", "HEAD"], cwd=worktree).stdout.strip()


def assert_attached_head(worktree: Path) -> str:
    """Return the stripped ``refs/heads/<branch>`` name when ``HEAD`` is
    attached; raise :class:`~dark_factory.git.DetachedHeadError` naming the
    worktree path and the current ``HEAD`` SHA otherwise.

    Uses ``git symbolic-ref -q HEAD``'s exit code as the boolean signal --
    exit 0 means attached, any non-zero exit means detached -- rather than
    string-matching ``rev-parse --abbrev-ref HEAD`` output against the
    literal ``"HEAD"``, because a branch could in principle be named that.
    """
    result = run_git(["symbolic-ref", "-q", "HEAD"], cwd=worktree, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    sha = head_sha(worktree)
    raise DetachedHeadError(
        f"worktree {worktree} has a detached HEAD at {sha}; refusing to enter "
        "a role against a checkout the platform cannot reason about"
    )


def dirty_paths(worktree: Path) -> list[str]:
    """One entry per non-empty ``git status --porcelain=v1`` line, with the
    two-character status prefix stripped.

    ``--untracked-files=all`` (not the default ``normal``) is required so a
    new directory containing multiple untracked files is reported as one
    entry per file rather than a single directory line -- a recovery that
    reports "one file" when it actually committed two would be an invisible
    under-count.
    """
    result = run_git(
        ["status", "--porcelain=v1", "--untracked-files=all"], cwd=worktree
    )
    return [line[2:].strip() for line in result.stdout.splitlines() if line.strip()]


def is_dirty(worktree: Path) -> bool:
    """Whether the worktree has any modified, staged or untracked content."""
    return bool(dirty_paths(worktree))


# D-05: recovery is a plain commit on the branch already checked out --
# deliberately not the other git mechanism for setting aside uncommitted
# content, because that mechanism's object is referenced by no branch and is
# therefore garbage-collectable, which would make the recovery mechanism
# itself a data-loss path. GIT-01 prohibits discarding uncommitted content as
# a recovery strategy; this function never resets, cleans or checks out over
# the working tree -- it only adds and commits.
def wip_commit_if_dirty(worktree: Path, *, role: str, attempt: int) -> str | None:
    """Recover a dirty worktree onto its currently-checked-out branch with a
    plain commit; return the new commit's SHA, or ``None`` when the worktree
    was already clean (this is what makes repeated entry idempotent).

    ``git add -A`` then ``git commit`` -- staging with ``-A`` picks up
    tracked modifications, deletions and untracked files in one step, which
    is precisely the "nothing lost" contract. See the comment immediately
    above this function for why the recovery mechanism is a commit rather
    than the alternative git carries for setting aside changes.
    """
    if not is_dirty(worktree):
        return None
    run_git(["add", "-A"], cwd=worktree)
    run_git(
        [
            "commit",
            "-m",
            f"{WIP_COMMIT_SUBJECT_PREFIX} recover uncommitted changes from "
            f"{role} attempt {attempt}",
        ],
        cwd=worktree,
    )
    return head_sha(worktree)
