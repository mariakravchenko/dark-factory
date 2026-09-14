"""GIT-01 unit proofs: branch naming, idempotent worktree creation/reuse,
fail-loud failure modes, ``remove_worktree``, the ``git_env`` allowlist, and
``run_git``'s ``check=True``/``check=False`` split -- against real ``git``
repositories built by :mod:`tests.support.git_repo` (05-01 Task 3).

These tests touch no database and no network beyond the loopback filesystem
clones D-15's reconstruction proof builds -- fast, pure-function-adjacent
tests against real subprocess behaviour, matching the ``unit`` marker's own
definition.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from dark_factory.git import GitCommandError, WorktreePathError
from dark_factory.git.client import (
    GIT_ENV_ALLOWLIST,
    GIT_IDENTITY_ENV,
    git_env,
    run_git,
)
from dark_factory.git.worktree import (
    ensure_worktree,
    remove_worktree,
    working_branch_name,
    worktree_path,
)
from tests.support.git_repo import clone_repo, git_commit_all, make_git_repo

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# branch naming / sibling-path derivation
# --------------------------------------------------------------------------- #


def test_working_branch_name_is_deterministic_with_no_slugification() -> None:
    run_id = uuid4()
    assert working_branch_name(run_id) == f"dark-factory/run-{run_id}"


def test_two_distinct_run_ids_produce_two_distinct_branch_names() -> None:
    a, b = uuid4(), uuid4()
    assert working_branch_name(a) != working_branch_name(b)


def test_worktree_path_resolves_to_a_sibling_never_a_descendant(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_id = uuid4()
    target = worktree_path(repo_root, run_id)
    assert not target.is_relative_to(repo_root.resolve())
    assert target.parent.name == "dark-factory-runs"
    assert target.name == str(run_id)


# --------------------------------------------------------------------------- #
# first creation / idempotent reuse (RESEARCH Pitfall 4 -- the load-bearing test)
# --------------------------------------------------------------------------- #


def _porcelain_worktree_lines(repo_root: Path) -> list[str]:
    stdout = run_git(["worktree", "list", "--porcelain"], cwd=repo_root).stdout
    return [line for line in stdout.splitlines() if line.startswith("worktree ")]


def test_ensure_worktree_creates_the_directory_git_entry_and_branch(
    tmp_path: Path,
) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)

    target = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )

    assert target.is_dir()
    assert (target / ".git").exists()
    lines = _porcelain_worktree_lines(repo_root)
    assert any(str(target) in line for line in lines)
    assert (
        f"refs/heads/{branch}"
        in run_git(["worktree", "list", "--porcelain"], cwd=repo_root).stdout
    )


def test_ensure_worktree_second_call_reuses_without_a_second_worktree_add(
    tmp_path: Path,
) -> None:
    """The load-bearing idempotency proof: count worktree lines AND assert an
    unchanged branch HEAD SHA before/after the second call -- a test that
    merely asserts "returns a path" would pass even against an
    implementation that re-invokes ``git worktree add`` and swallows the
    error."""
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)

    first = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )
    lines_before = _porcelain_worktree_lines(repo_root)
    sha_before = run_git(["rev-parse", "HEAD"], cwd=first).stdout.strip()

    second = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )
    lines_after = _porcelain_worktree_lines(repo_root)
    sha_after = run_git(["rev-parse", "HEAD"], cwd=second).stdout.strip()

    assert second == first
    assert len(lines_after) == len(lines_before)
    assert sha_after == sha_before


# --------------------------------------------------------------------------- #
# fail-loud failure modes
# --------------------------------------------------------------------------- #


def test_ensure_worktree_invalid_base_branch_raises_and_leaves_no_directory(
    tmp_path: Path,
) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)

    with pytest.raises(GitCommandError) as excinfo:
        ensure_worktree(
            repo_root, run_id, base_branch="no-such-branch", working_branch=branch
        )
    assert "no-such-branch" in str(excinfo.value)
    # A partially-created worktree left behind would make the next call take
    # the idempotent early-return path and silently succeed against a
    # broken checkout.
    assert not worktree_path(repo_root, run_id).exists()


def test_ensure_worktree_none_working_branch_raises_naming_the_run_id(
    tmp_path: Path,
) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()

    with pytest.raises(WorktreePathError) as excinfo:
        ensure_worktree(repo_root, run_id, base_branch="main", working_branch=None)
    assert str(run_id) in str(excinfo.value)


def test_ensure_worktree_none_base_branch_on_first_creation_raises(
    tmp_path: Path,
) -> None:
    """A working_branch that exists nowhere yet (first-ever creation, Path 3)
    with no base_branch to create it from raises -- never silently falls
    back to a default branch name."""
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)

    with pytest.raises(WorktreePathError) as excinfo:
        ensure_worktree(repo_root, run_id, base_branch=None, working_branch=branch)
    assert str(run_id) in str(excinfo.value)
    assert not worktree_path(repo_root, run_id).exists()


# --------------------------------------------------------------------------- #
# remove_worktree
# --------------------------------------------------------------------------- #


def test_remove_worktree_returns_false_when_none_exists(tmp_path: Path) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    assert remove_worktree(repo_root, uuid4()) is False


def test_remove_worktree_refuses_a_dirty_tree_without_force(tmp_path: Path) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)
    target = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )
    (target / "dirty.txt").write_text("uncommitted", encoding="utf-8")

    with pytest.raises(GitCommandError):
        remove_worktree(repo_root, run_id)
    assert target.is_dir()

    # cleanup for the next test's disk hygiene
    remove_worktree(repo_root, run_id, force=True)


def test_remove_worktree_with_force_succeeds_on_a_dirty_tree(tmp_path: Path) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    branch = working_branch_name(run_id)
    target = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )
    (target / "dirty.txt").write_text("uncommitted", encoding="utf-8")

    assert remove_worktree(repo_root, run_id, force=True) is True
    assert not target.exists()


# --------------------------------------------------------------------------- #
# git_env allowlist
# --------------------------------------------------------------------------- #


def test_git_env_contains_only_allowlisted_names_plus_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fakefakefakefakefakefakefakefakefake")
    for name in GIT_ENV_ALLOWLIST:
        if name not in os.environ:
            monkeypatch.setenv(name, f"value-for-{name}")

    env = git_env()

    assert "DATABASE_URL" not in env
    assert "GITHUB_TOKEN" not in env
    for name in GIT_ENV_ALLOWLIST:
        assert env[name] == os.environ[name]
    for key, value in GIT_IDENTITY_ENV.items():
        assert env[key] == value


def test_git_env_omits_an_allowlisted_name_absent_from_the_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    assert "SSL_CERT_FILE" not in git_env()


# --------------------------------------------------------------------------- #
# run_git: check=True vs check=False
# --------------------------------------------------------------------------- #


def test_run_git_check_false_returns_completed_process_on_nonzero_exit(
    tmp_path: Path,
) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    # `git symbolic-ref -q HEAD` on an attached HEAD exits 0; a nonexistent
    # ref name exits non-zero without raising when check=False.
    result = run_git(
        ["show-ref", "--verify", "--quiet", "refs/heads/does-not-exist"],
        cwd=repo_root,
        check=False,
    )
    assert result.returncode != 0


def test_run_git_check_true_raises_git_command_error_with_returncode_and_stderr(
    tmp_path: Path,
) -> None:
    repo_root = make_git_repo(tmp_path / "repo")
    with pytest.raises(GitCommandError) as excinfo:
        run_git(["not-a-real-git-subcommand"], cwd=repo_root)
    assert excinfo.value.returncode != 0
    assert excinfo.value.stderr != ""


# --------------------------------------------------------------------------- #
# D-15: reconstruction from a second clone of a shared bare origin
# --------------------------------------------------------------------------- #


def test_ensure_worktree_reconstructs_from_origin_when_no_local_worktree_exists(
    tmp_path: Path,
) -> None:
    """Repo A creates the worktree fresh, commits, and pushes. Repo B -- a
    second, independent clone of the same origin with no local worktree,
    simulating a second ephemeral runner picking up the same run -- must
    reconstruct from the pushed commit, not fall through to a fresh ``-b``
    creation off ``base_branch``."""
    origin = make_git_repo(tmp_path / "origin")
    repo_a = clone_repo(origin, tmp_path / "repo-a")
    # Cloned BEFORE the branch is pushed to origin, so repo_b's own
    # remote-tracking refs do not already carry it -- ensure_worktree's
    # explicit `git fetch origin <branch>` is what must discover it.
    repo_b = clone_repo(origin, tmp_path / "repo-b")

    run_id = uuid4()
    branch = working_branch_name(run_id)

    work_dir_a = ensure_worktree(
        repo_a, run_id, base_branch="main", working_branch=branch
    )
    (work_dir_a / "new-file.txt").write_text("from repo A", encoding="utf-8")
    pushed_sha = git_commit_all(work_dir_a, "work from repo A")
    run_git(["push", "origin", branch], cwd=work_dir_a)

    work_dir_b = ensure_worktree(
        repo_b, run_id, base_branch="main", working_branch=branch
    )

    assert run_git(["rev-parse", "HEAD"], cwd=work_dir_b).stdout.strip() == pushed_sha
    assert len(_porcelain_worktree_lines(repo_b)) == 1


def test_ensure_worktree_falls_through_to_fresh_creation_when_branch_exists_nowhere(
    tmp_path: Path,
) -> None:
    """A working_branch that has no local ref, no origin remote at all, and
    therefore no remote-tracking ref either reaches Path 3 and creates
    successfully rather than raising -- "no remote configured" collapses to
    the same code path as "branch never pushed" (D-15)."""
    repo_root = make_git_repo(tmp_path / "repo")  # no origin remote configured
    run_id = uuid4()
    branch = working_branch_name(run_id)

    target = ensure_worktree(
        repo_root, run_id, base_branch="main", working_branch=branch
    )

    assert target.is_dir()
    assert (target / ".git").exists()
