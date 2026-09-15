"""Unit proofs for ``dark_factory.git.diff``'s commit/diff primitives
(05-03 Task 2 & Task 4).

Against real ``git`` repositories built by :mod:`tests.support.git_repo`,
matching the discipline ``tests/unit/test_git_worktree.py`` and
``tests/unit/test_git_lifecycle.py`` already established -- a mock cannot
reproduce ``git``'s genuine exit-code and refusal behaviour, which
``commit_run_artifacts``'s empty-change-set detection and the force-add past
``.gitignore`` both depend on.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from dark_factory.git import GitCommandError
from dark_factory.git.client import run_git
from dark_factory.git.diff import (
    ARTIFACT_COMMIT_SUBJECT_PREFIX,
    MAX_DIFF_BYTES,
    collect_pr_diff,
    commit_run_artifacts,
    pr_changed_paths,
)
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.unit


def _write_run_artifact(
    worktree: Path, run_id: UUID, relative_path: str, content: str
) -> Path:
    path = worktree / ".dark-factory" / "runs" / str(run_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# commit_run_artifacts
# --------------------------------------------------------------------------- #


def test_commit_run_artifacts_happy_path_returns_the_new_commit_sha(
    tmp_path: Path,
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    _write_run_artifact(repo, run_id, "artifacts/BA/output.json", '{"ok": true}')

    sha = commit_run_artifacts(repo, run_id, role="BA")

    assert sha is not None
    subject = run_git(["log", "-1", "--format=%s"], cwd=repo).stdout.strip()
    assert subject == f"{ARTIFACT_COMMIT_SUBJECT_PREFIX} BA artifacts (run {run_id})"
    assert run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip() == sha


def test_commit_run_artifacts_force_adds_past_the_ignore_rule(tmp_path: Path) -> None:
    """A-05-08: the repository's own ``.gitignore`` excludes
    ``.dark-factory/runs/``, so the commit must succeed via ``-f`` rather
    than silently committing nothing."""
    repo = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    _write_run_artifact(repo, run_id, "artifacts/BA/output.json", '{"ok": true}')

    sha = commit_run_artifacts(repo, run_id, role="BA")

    assert sha is not None
    tracked = run_git(["ls-files"], cwd=repo).stdout
    assert f".dark-factory/runs/{run_id}/artifacts/BA/output.json" in tracked
    # The .gitignore pattern still matches this path -- proven with
    # --no-index, which evaluates the ignore rule independent of the index,
    # since a tracked path is (correctly) no longer reported as "ignored" by
    # a plain `git check-ignore`. The pair (tracked in ls-files + still
    # pattern-matched by check-ignore --no-index) is what proves the content
    # is tracked despite the ignore rule rather than because the rule was
    # weakened (D-11).
    ignored = run_git(
        ["check-ignore", "--no-index", f".dark-factory/runs/{run_id}/"],
        cwd=repo,
        check=False,
    )
    assert ignored.returncode == 0


def test_commit_run_artifacts_missing_directory_returns_none_with_no_git_effect(
    tmp_path: Path,
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    sha_before = run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    result = commit_run_artifacts(repo, run_id, role="BA")

    assert result is None
    assert run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip() == sha_before


def test_commit_run_artifacts_called_twice_with_no_new_content_is_idempotent(
    tmp_path: Path,
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    _write_run_artifact(repo, run_id, "artifacts/BA/output.json", '{"ok": true}')

    first = commit_run_artifacts(repo, run_id, role="BA")
    assert first is not None
    sha_after_first = run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    second = commit_run_artifacts(repo, run_id, role="BA")

    assert second is None
    assert run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip() == sha_after_first


def test_commit_run_artifacts_genuine_git_failure_propagates_as_git_command_error(
    tmp_path: Path,
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    run_id = uuid4()
    _write_run_artifact(repo, run_id, "artifacts/BA/output.json", '{"ok": true}')

    # A stale index.lock forces every git write in this repository to fail --
    # a genuine git-level failure distinct from the empty-change-set no-op,
    # proving the failure is never swallowed (ART-04's transparency
    # prohibition).
    lock = repo / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    try:
        with pytest.raises(GitCommandError):
            commit_run_artifacts(repo, run_id, role="BA")
    finally:
        lock.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# collect_pr_diff / pr_changed_paths
# --------------------------------------------------------------------------- #


def _repo_with_a_working_branch_work_commit(tmp_path: Path) -> tuple[Path, str]:
    repo = make_git_repo(tmp_path / "repo", base_branch="main")
    working_branch = "dark-factory/run-unit-test"
    run_git(["checkout", "-b", working_branch], cwd=repo)
    (repo / "work.txt").write_text("work content\n", encoding="utf-8")
    run_git(["add", "-A"], cwd=repo)
    run_git(["commit", "-m", "work commit"], cwd=repo)
    return repo, working_branch


def test_collect_pr_diff_excludes_every_dark_factory_path(tmp_path: Path) -> None:
    repo, working_branch = _repo_with_a_working_branch_work_commit(tmp_path)
    run_id = uuid4()
    _write_run_artifact(repo, run_id, "artifacts/BA/output.json", '{"ok": true}')
    assert commit_run_artifacts(repo, run_id, role="BA") is not None

    diff_text = collect_pr_diff(repo, base_branch="main", working_branch=working_branch)

    assert "work.txt" in diff_text
    assert ".dark-factory" not in diff_text


def test_pr_changed_paths_returns_names_only(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo", base_branch="main")
    working_branch = "dark-factory/run-unit-test-names"
    run_git(["checkout", "-b", working_branch], cwd=repo)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    run_git(["add", "-A"], cwd=repo)
    run_git(["commit", "-m", "two files"], cwd=repo)

    paths = pr_changed_paths(repo, base_branch="main", working_branch=working_branch)

    assert set(paths) == {"a.txt", "b.txt"}


def test_collect_pr_diff_truncates_at_the_cap_with_a_marker_line_naming_original_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    line = "a synthetic diff line of fixed content\n"
    oversized = line * ((MAX_DIFF_BYTES // len(line)) + 1000)
    original_size = len(oversized.encode("utf-8"))
    assert original_size > MAX_DIFF_BYTES

    def _fake_run_git(
        args: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
        timeout: int = 120,
        env_extra: object = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(args), returncode=0, stdout=oversized, stderr=""
        )

    monkeypatch.setattr("dark_factory.git.diff.run_git", _fake_run_git)

    result = collect_pr_diff(
        repo, base_branch="main", working_branch="dark-factory/run-oversized"
    )

    encoded = result.encode("utf-8")
    assert len(encoded) < original_size
    assert f"original size {original_size} bytes" in result
    assert "truncated" in result
