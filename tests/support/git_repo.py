"""A throwaway real-git-repo fixture factory for the unit/db/integration
tiers (05-01 Task 1).

The git tier is exercised against real repositories because a mock cannot
reproduce the exit codes and refusal behaviour the production code branches
on -- ``ensure_worktree``'s three-path dispatch, ``run_git``'s
``check=True``/``check=False`` distinction, and ``git worktree add``'s own
idempotency refusal all depend on git's genuine subprocess behaviour. Every
helper here shells out through :func:`dark_factory.git.client.run_git`, so
the test tier and the production tier share one invocation discipline.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from dark_factory.git import committed as _committed
from dark_factory.git.client import run_git

__all__ = [
    "clone_repo",
    "git_commit_all",
    "make_git_repo",
    "read_committed",
    "run_artifact_text",
]


def make_git_repo(
    root: Path,
    *,
    base_branch: str = "main",
    gitignore: Sequence[str] = (".dark-factory/runs/",),
) -> Path:
    """Initialise a real git repository at ``root`` with one commit on
    ``base_branch``, a ``.gitignore`` and a minimal ``README.md``; return
    ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    run_git(["init", "-q", "-b", base_branch], cwd=root)
    run_git(["config", "user.email", "dark-factory-tests@invalid"], cwd=root)
    run_git(["config", "user.name", "Dark Factory Tests"], cwd=root)
    (root / ".gitignore").write_text("\n".join(gitignore) + "\n", encoding="utf-8")
    (root / "README.md").write_text("# throwaway test repository\n", encoding="utf-8")
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", "init"], cwd=root)
    return root


def git_commit_all(root: Path, message: str) -> str:
    """Stage everything under ``root`` and commit; return the new ``HEAD``
    SHA."""
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", message], cwd=root)
    return run_git(["rev-parse", "HEAD"], cwd=root).stdout.strip()


def read_committed(repo_root: Path, branch: str, relative_path: str) -> str:
    """Delegates to :func:`dark_factory.git.committed.read_committed` -- the
    canonical production implementation; this is a test-helper re-export,
    not a second copy."""
    return _committed.read_committed(repo_root, branch, relative_path)


def clone_repo(source: Path, dest: Path, *, branch: str | None = None) -> Path:
    """``git clone`` (optionally ``--branch``) ``source`` into ``dest``;
    return ``dest``. Declared here now; plan 05-03's fresh-clone proof
    consumes it."""
    args = ["clone", "-q"]
    if branch is not None:
        args += ["--branch", branch]
    args += [str(source), str(dest)]
    run_git(args, cwd=dest.parent)
    return dest


def run_artifact_text(
    repo_root: Path, run_id: UUID, working_branch: str, relative_path: str
) -> str:
    """Delegates to :func:`dark_factory.git.committed.run_artifact_text` --
    the canonical production implementation; this is a test-helper
    re-export, not a second copy."""
    return _committed.run_artifact_text(
        repo_root, run_id, working_branch, relative_path
    )
