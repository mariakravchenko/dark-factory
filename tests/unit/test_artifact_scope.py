"""``attempt_changed_artifact_paths`` / ``enforce_artifact_scope`` unit
proof (plan 08-05, CR-01, Tasks 1-2).

Real git on a throwaway repository (``make_git_repo``), no database -- the
same "real git, no Postgres" idiom ``tests/unit/test_write_scope_revert.py``
already established for this package's DB-free unit tier. A prior role's
artifact is force-added and committed the way
:func:`~dark_factory.git.diff.commit_run_artifacts` does; later mutations to
that tree are then asserted against the enumeration and enforcement
functions directly.

Mirrors ``tests/unit/test_write_scope.py``'s docstring instruction for this
project's scope matching: a path several segments below the allowed subtree
is in scope, and a decoy sibling subtree whose name merely starts with the
role's name is out of scope.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from dark_factory.artifacts.paths import ensure_run_tree, run_root
from dark_factory.git import ArtifactScopeViolation
from dark_factory.git.client import run_git
from dark_factory.git.scope import (
    ARTIFACTS_WRITE_CAPABILITY,
    attempt_changed_artifact_paths,
    enforce_artifact_scope,
)
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.unit


def _run_root(repo_root: Path, run_id: UUID) -> Path:
    root = run_root(repo_root, run_id)
    ensure_run_tree(root)
    return root


def _write_artifact(
    repo_root: Path, run_id: UUID, role: str, filename: str, content: str
) -> Path:
    path = _run_root(repo_root, run_id) / "artifacts" / role / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _commit_artifacts(repo_root: Path, run_id: UUID) -> None:
    """Force-add and commit the run's whole ``artifacts/`` subtree, the way
    :func:`~dark_factory.git.diff.commit_run_artifacts` commits the whole
    run tree -- so a "prior role's artifact" is genuinely tracked in
    ``HEAD`` by the time a later role's attempt runs, exactly as it is in
    production."""
    pathspec = f".dark-factory/runs/{run_id}/artifacts"
    run_git(["add", "-f", "--", pathspec], cwd=repo_root)
    run_git(["commit", "-m", f"artifacts (run {run_id})"], cwd=repo_root)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_git_repo(tmp_path / "repo")


@pytest.fixture
def run_id() -> UUID:
    return uuid4()


# --------------------------------------------------------------------------- #
# attempt_changed_artifact_paths
# --------------------------------------------------------------------------- #


def test_returns_empty_list_when_the_run_artifacts_directory_does_not_exist(
    repo: Path,
) -> None:
    missing_run_id = uuid4()
    assert attempt_changed_artifact_paths(repo, missing_run_id) == []


def test_returns_empty_list_when_nothing_under_artifacts_changed(
    repo: Path, run_id: UUID
) -> None:
    _write_artifact(repo, run_id, "QA", "test_report.json", "{}")
    _commit_artifacts(repo, run_id)
    assert attempt_changed_artifact_paths(repo, run_id) == []


def test_a_modified_prior_role_artifact_is_reported(repo: Path, run_id: UUID) -> None:
    path = _write_artifact(
        repo, run_id, "ARCHITECTURE", "design.md", "original design\n"
    )
    _commit_artifacts(repo, run_id)

    path.write_text("QA overwrote this\n", encoding="utf-8")

    changed = attempt_changed_artifact_paths(repo, run_id)
    assert f".dark-factory/runs/{run_id}/artifacts/ARCHITECTURE/design.md" in changed


def test_a_new_file_created_inside_a_prior_roles_subtree_is_reported(
    repo: Path, run_id: UUID
) -> None:
    _write_artifact(repo, run_id, "ARCHITECTURE", "design.md", "original design\n")
    _commit_artifacts(repo, run_id)

    _write_artifact(repo, run_id, "ARCHITECTURE", "injected.md", "foreign file\n")

    changed = attempt_changed_artifact_paths(repo, run_id)
    assert f".dark-factory/runs/{run_id}/artifacts/ARCHITECTURE/injected.md" in changed


def test_a_write_under_the_same_runs_verification_directory_is_not_reported(
    repo: Path, run_id: UUID
) -> None:
    root = _run_root(repo, run_id)
    (root / "verification" / "diff.patch").write_text("diff\n", encoding="utf-8")

    assert attempt_changed_artifact_paths(repo, run_id) == []


# --------------------------------------------------------------------------- #
# enforce_artifact_scope
# --------------------------------------------------------------------------- #


def test_returns_none_when_the_only_change_is_under_the_roles_own_subtree(
    repo: Path, run_id: UUID
) -> None:
    _write_artifact(repo, run_id, "QA", "test_report.json", "{}")

    assert (
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )
        is None
    )


def test_returns_none_for_a_path_several_levels_below_the_roles_own_subtree(
    repo: Path, run_id: UUID
) -> None:
    path = _run_root(repo, run_id) / "artifacts" / "QA" / "sub" / "deep" / "nested.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")

    assert (
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )
        is None
    )


def test_a_decoy_sibling_subtree_whose_name_merely_starts_with_the_role_is_out_of_scope(
    repo: Path, run_id: UUID
) -> None:
    """The false-positive case a right-anchored matcher gets wrong: ``QAX``
    is not ``QA``."""
    _write_artifact(repo, run_id, "QAX", "leaked.json", "{}")

    with pytest.raises(ArtifactScopeViolation):
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )


def test_no_artifacts_write_grant_is_zero_tolerance_for_the_roles_own_subtree(
    repo: Path, run_id: UUID
) -> None:
    """D-14's polarity, extended to the artifacts tree: an empty allowed
    pattern list means every path is a violation, including a role's own
    subtree, when the role holds no ``artifacts.write`` grant at all."""
    _write_artifact(repo, run_id, "QA", "test_report.json", "{}")

    with pytest.raises(ArtifactScopeViolation) as excinfo:
        enforce_artifact_scope(repo, run_id, role="QA", attempt=1, granted=[])
    assert "artifacts.write" in str(excinfo.value)


def test_a_modified_prior_role_artifact_is_restored_to_its_committed_bytes(
    repo: Path, run_id: UUID
) -> None:
    path = _write_artifact(
        repo, run_id, "ARCHITECTURE", "design.md", "original design\n"
    )
    _commit_artifacts(repo, run_id)

    path.write_text("QA tampered with this\n", encoding="utf-8")

    with pytest.raises(ArtifactScopeViolation):
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )

    assert path.read_text("utf-8") == "original design\n"


def test_a_role_created_file_in_another_roles_subtree_is_removed_from_disk(
    repo: Path, run_id: UUID
) -> None:
    _write_artifact(repo, run_id, "ARCHITECTURE", "design.md", "original design\n")
    _commit_artifacts(repo, run_id)

    injected = _write_artifact(
        repo, run_id, "ARCHITECTURE", "injected.md", "foreign file\n"
    )
    assert injected.exists()

    with pytest.raises(ArtifactScopeViolation):
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )

    assert not injected.exists()


def test_two_violating_paths_are_both_named_and_both_reverted(
    repo: Path, run_id: UUID
) -> None:
    architecture_path = _write_artifact(
        repo, run_id, "ARCHITECTURE", "design.md", "original design\n"
    )
    ba_path = _write_artifact(
        repo, run_id, "BA", "acceptance_criteria.json", '{"criteria": []}'
    )
    _commit_artifacts(repo, run_id)

    architecture_path.write_text("tampered\n", encoding="utf-8")
    ba_path.write_text("also tampered", encoding="utf-8")

    with pytest.raises(ArtifactScopeViolation) as excinfo:
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=3,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )

    message = str(excinfo.value)
    assert "QA" in message
    assert "3" in message
    assert f".dark-factory/runs/{run_id}/artifacts/ARCHITECTURE/design.md" in message
    assert (
        f".dark-factory/runs/{run_id}/artifacts/BA/acceptance_criteria.json" in message
    )
    assert architecture_path.read_text("utf-8") == "original design\n"
    assert ba_path.read_text("utf-8") == '{"criteria": []}'


# --------------------------------------------------------------------------- #
# Task 2 additions: the remaining boundary cases that do not need a database.
# --------------------------------------------------------------------------- #


def test_a_role_that_changes_nothing_under_the_artifacts_tree_is_a_no_op(
    repo: Path, run_id: UUID
) -> None:
    _write_artifact(repo, run_id, "QA", "test_report.json", "{}")
    _commit_artifacts(repo, run_id)

    assert (
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )
        is None
    )


def test_a_write_under_the_same_runs_logs_directory_is_not_reported(
    repo: Path, run_id: UUID
) -> None:
    root = _run_root(repo, run_id)
    log_path = root / "logs" / "QA" / "attempt-1.stdout.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("log line\n", encoding="utf-8")

    assert attempt_changed_artifact_paths(repo, run_id) == []


def test_a_write_under_the_same_runs_input_directory_is_not_reported(
    repo: Path, run_id: UUID
) -> None:
    root = _run_root(repo, run_id)
    input_path = root / "input" / "task.md"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text("task\n", encoding="utf-8")

    assert attempt_changed_artifact_paths(repo, run_id) == []


def test_a_deleted_prior_role_artifact_is_restored_from_head(
    repo: Path, run_id: UUID
) -> None:
    path = _write_artifact(
        repo, run_id, "ARCHITECTURE", "design.md", "original design\n"
    )
    _commit_artifacts(repo, run_id)

    path.unlink()
    assert not path.exists()

    with pytest.raises(ArtifactScopeViolation):
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )

    assert path.exists()
    assert path.read_text("utf-8") == "original design\n"


def test_a_write_into_both_the_roles_own_subtree_and_a_foreign_subtree_only_reverts_the_foreign_one(
    repo: Path, run_id: UUID
) -> None:
    """An enforcement mechanism must never be a worse outcome than the
    violation it corrects (the same property ``revert_paths``' docstring
    already claims for write scope): a role's own legitimate output must
    survive intact even when the same attempt also wrote a foreign path."""
    own_path = _write_artifact(repo, run_id, "QA", "test_report.json", "{}")
    foreign_path = _write_artifact(
        repo, run_id, "ARCHITECTURE", "injected.md", "foreign\n"
    )

    with pytest.raises(ArtifactScopeViolation):
        enforce_artifact_scope(
            repo,
            run_id,
            role="QA",
            attempt=1,
            granted=[ARTIFACTS_WRITE_CAPABILITY],
        )

    assert own_path.exists()
    assert own_path.read_text("utf-8") == "{}"
    assert not foreign_path.exists()
