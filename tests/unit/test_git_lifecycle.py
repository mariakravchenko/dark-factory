"""Unit coverage for ``dark_factory.git.lifecycle``'s five primitives (Plan
05-02 Task 2), real git against a ``tmp_path`` repository from
``tests.support.git_repo.make_git_repo`` -- a mock cannot reproduce the exit
codes and refusal behaviour these functions branch on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dark_factory.git import DetachedHeadError
from dark_factory.git.client import run_git
from dark_factory.git.lifecycle import (
    WIP_COMMIT_SUBJECT_PREFIX,
    assert_attached_head,
    dirty_paths,
    head_sha,
    is_dirty,
    wip_commit_if_dirty,
)
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_git_repo(tmp_path / "repo")


def test_head_sha_returns_the_current_commit_sha(repo: Path) -> None:
    sha = head_sha(repo)
    expected = run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    assert sha == expected
    assert len(sha) == 40


def test_assert_attached_head_returns_the_full_ref_name_on_a_branch(
    repo: Path,
) -> None:
    ref = assert_attached_head(repo)
    assert ref == "refs/heads/main"


def test_assert_attached_head_raises_and_names_the_path_when_detached(
    repo: Path,
) -> None:
    sha = head_sha(repo)
    run_git(["checkout", "-q", sha], cwd=repo)

    with pytest.raises(DetachedHeadError) as excinfo:
        assert_attached_head(repo)
    assert str(repo) in str(excinfo.value)
    assert sha in str(excinfo.value)


def test_dirty_paths_is_empty_on_a_freshly_made_repo(repo: Path) -> None:
    assert dirty_paths(repo) == []
    assert is_dirty(repo) is False


def test_dirty_paths_reports_a_modified_tracked_file(repo: Path) -> None:
    (repo / "README.md").write_text("modified\n", encoding="utf-8")
    paths = dirty_paths(repo)
    assert paths == ["README.md"]
    assert is_dirty(repo) is True


def test_dirty_paths_reports_one_entry_per_untracked_file_not_per_directory(
    repo: Path,
) -> None:
    """The porcelain default (``--untracked-files=normal``) collapses two new
    files inside one new directory into a single directory line; ``dirty_paths``
    must use ``--untracked-files=all`` so a recovery can report what it
    actually recovered, file by file."""
    new_dir = repo / "brand_new_dir"
    new_dir.mkdir()
    (new_dir / "a.txt").write_text("a\n", encoding="utf-8")
    (new_dir / "b.txt").write_text("b\n", encoding="utf-8")

    paths = dirty_paths(repo)
    assert "brand_new_dir/" not in paths
    assert "brand_new_dir/a.txt" in paths
    assert "brand_new_dir/b.txt" in paths
    assert len(paths) == 2


def test_wip_commit_if_dirty_returns_none_on_a_clean_worktree(repo: Path) -> None:
    assert wip_commit_if_dirty(repo, role="BA", attempt=1) is None


def test_wip_commit_if_dirty_commits_and_returns_the_new_sha(repo: Path) -> None:
    head_before = head_sha(repo)
    (repo / "README.md").write_text("dirtied\n", encoding="utf-8")
    (repo / "new_file.txt").write_text("new\n", encoding="utf-8")

    sha = wip_commit_if_dirty(repo, role="BA", attempt=2)

    assert sha is not None
    assert sha != head_before
    assert head_sha(repo) == sha
    assert dirty_paths(repo) == []

    subject = run_git(["log", "-1", "--format=%s"], cwd=repo).stdout.strip()
    assert subject.startswith(WIP_COMMIT_SUBJECT_PREFIX)
    assert "BA" in subject
    assert "attempt 2" in subject

    show = run_git(["show", "--stat", "--format=", sha], cwd=repo).stdout
    assert "README.md" in show
    assert "new_file.txt" in show


def test_wip_commit_if_dirty_is_idempotent_on_a_second_call(repo: Path) -> None:
    (repo / "README.md").write_text("dirtied again\n", encoding="utf-8")

    first_sha = wip_commit_if_dirty(repo, role="ARCHITECTURE", attempt=1)
    assert first_sha is not None

    second_sha = wip_commit_if_dirty(repo, role="ARCHITECTURE", attempt=1)
    # A return of None alone would also be produced by an implementation that
    # committed an empty tree and failed to notice -- assert HEAD is
    # genuinely unchanged too.
    assert second_sha is None
    assert head_sha(repo) == first_sha
