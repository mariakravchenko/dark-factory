"""The CR-02 regression suite: ``revert_paths``' escape-ordering guarantee,
its boundary neighbours, and the ``enforce_write_scope``-level proof that
production actually produces the escape-first ordering (G-05-2, D-13).

CR-02 changed ``revert_paths`` so a single escaping path (one that resolves
outside the worktree, e.g. a worker-created symlink) can no longer abort the
revert of every other violation queued behind it: the containment check
moved inside a per-path ``try``/``except`` that collects escapes and raises
once after the loop, rather than letting the first escape propagate and
short-circuit everything after it. That fix shipped as a Critical code-review
finding with zero executed coverage at any tier (05-REVIEW-FIX.md CR-02;
full investigation in ``.planning/debug/cr02-revert-ordering-test-gap.md``).

This file lives at the **unit tier**, not the DB-gated integration tier,
because it always could have: ``src/dark_factory/git/scope.py``'s own module
docstring states it performs no database access anywhere, and
``revert_paths(worktree, paths)`` takes a plain path and only shells out to
git. The coverage was previously reachable only through the run driver
(``tests/integration/test_write_scope_enforcement.py``, behind a real
Postgres engine fixture) by an accident of test partitioning -- "pure
functions to the unit tier, everything else to the full-pipeline integration
tier" left no obvious DB-free home for revert behaviour, and that accident is
what let CR-02 ship untested. ``tests/unit/test_git_lifecycle.py``,
``test_git_diff.py`` and ``test_git_worktree.py`` already establish the
DB-free unit-tier idiom this file follows: real git against a ``tmp_path``
repository via ``tests.support.git_repo.make_git_repo``, because the
behaviour under test is git's own exit codes and refusal semantics, which a
mock cannot reproduce.

Every case here calls ``revert_paths``/``enforce_write_scope`` directly with
an explicit list; none of them constructs a run, takes a database fixture,
or goes through the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from dark_factory.git import WriteScopeViolation
from dark_factory.git.client import run_git
from dark_factory.git.scope import revert_paths
from tests.support.git_repo import git_commit_all, make_git_repo

pytestmark = pytest.mark.unit

_ORIGINAL_APP_CONTENT = "print('original')\n"
_TAMPERED_APP_CONTENT = "print('tampered by a violation')\n"
_NEW_FILE_CONTENT = "# a role should not have written this\n"
_ESCAPE_TARGET_CONTENT = "content living outside the repository\n"


@dataclass(frozen=True)
class _Scenario:
    """A repository holding exactly the three violation shapes CR-02 cares
    about: a tracked violation with both an index entry and a working-tree
    change to undo, a newly-created violation with an index entry to clear
    before the file itself can be removed, and a target file for an
    escaping symlink -- kept outside ``repo`` but still under the pytest
    ``tmp_path`` sandbox, never a real path on the developer's machine."""

    repo: Path
    escape_target: Path


@pytest.fixture
def scenario(tmp_path: Path) -> _Scenario:
    repo = make_git_repo(tmp_path / "repo")

    # -- tracked violation: commit an original version, then overwrite and
    # stage the tampered content, so the restore branch has both an index
    # entry and a working-tree change to undo. ------------------------------
    app_path = repo / "src" / "app.py"
    app_path.parent.mkdir(parents=True, exist_ok=True)
    app_path.write_text(_ORIGINAL_APP_CONTENT, encoding="utf-8")
    git_commit_all(repo, "seed src/app.py")
    app_path.write_text(_TAMPERED_APP_CONTENT, encoding="utf-8")
    run_git(["add", "--", "src/app.py"], cwd=repo)

    # -- newly-created violation: stage it, so the other revert branch has
    # an index entry to clear before the file itself is removed -- staging
    # is what makes the `git rm --cached` step load-bearing rather than a
    # no-op. ------------------------------------------------------------------
    new_path = repo / "src" / "new.py"
    new_path.write_text(_NEW_FILE_CONTENT, encoding="utf-8")
    run_git(["add", "--", "src/new.py"], cwd=repo)

    # -- escape target: a directory outside the repository but still under
    # tmp_path, holding a file with known content. A symlink inside the
    # repository pointing at it is created per-test so each case controls
    # the symlink's name and its position in the explicit paths list. ------
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    escape_target = outside_dir / "secret.txt"
    escape_target.write_text(_ESCAPE_TARGET_CONTENT, encoding="utf-8")

    return _Scenario(repo=repo, escape_target=escape_target)


def _make_escape_symlink(scenario: _Scenario, name: str) -> Path:
    """Create a symlink inside ``scenario.repo`` at ``name`` pointing at
    ``scenario.escape_target``. The containment check resolves symlinks, so
    the resolved candidate lands outside the resolved repository root and
    the path is rejected. ``name`` is chosen by each test to control
    whether it sorts before or after the ``src/`` violations."""
    link = scenario.repo / name
    link.symlink_to(scenario.escape_target)
    return link


def _assert_in_repo_violations_reverted(repo: Path) -> None:
    """The tracked violation is restored from HEAD and unstaged; the
    newly-created violation is removed from disk and from the git index."""
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == (
        _ORIGINAL_APP_CONTENT
    )
    staged = run_git(["diff", "--cached", "--name-only"], cwd=repo).stdout
    assert "src/app.py" not in staged.splitlines()

    assert not (repo / "src" / "new.py").exists()
    cached = run_git(["ls-files", "--cached"], cwd=repo).stdout.splitlines()
    assert "src/new.py" not in cached


# --------------------------------------------------------------------------- #
# Task 1: revert_paths -- escape ordering and its boundary neighbours
# --------------------------------------------------------------------------- #


def test_escape_sorted_first_still_reverts_every_later_violation(
    scenario: _Scenario,
) -> None:
    """CR-02 regression proper. Before CR-02, `_resolve_in_worktree`'s raise
    propagated directly out of the loop on the first escaping path, aborting
    the revert of every violation still queued behind it. Placing the
    escaping symlink FIRST in the explicit list is exactly what makes that
    pre-CR-02 bug reachable: this test fails against a pre-CR-02
    implementation, where `src/app.py` would still hold the tampered content
    and `src/new.py` would still be on disk and staged after the raise."""
    _make_escape_symlink(scenario, "aa-escape")

    with pytest.raises(WriteScopeViolation):
        revert_paths(scenario.repo, ["aa-escape", "src/app.py", "src/new.py"])

    _assert_in_repo_violations_reverted(scenario.repo)


def test_the_escaping_path_itself_is_never_acted_upon(scenario: _Scenario) -> None:
    """The containment check rejects an escaping path, it never clamps and
    never deletes: an authorization control that reached outside the
    worktree to "clean up" would be a worse outcome than the violation it
    was correcting."""
    escape = _make_escape_symlink(scenario, "aa-escape")

    with pytest.raises(WriteScopeViolation):
        revert_paths(scenario.repo, ["aa-escape", "src/app.py", "src/new.py"])

    assert escape.is_symlink()
    assert scenario.escape_target.read_text(encoding="utf-8") == (
        _ESCAPE_TARGET_CONTENT
    )


def test_exactly_one_violation_is_raised_naming_the_escaping_path(
    scenario: _Scenario,
) -> None:
    _make_escape_symlink(scenario, "aa-escape")

    with pytest.raises(WriteScopeViolation) as excinfo:
        revert_paths(scenario.repo, ["aa-escape", "src/app.py", "src/new.py"])

    assert "aa-escape" in str(excinfo.value)


def test_escape_sorted_last_produces_the_identical_revert_outcome(
    scenario: _Scenario,
) -> None:
    """Together with the escape-first case, this pins the property that
    matters: the revert outcome does not depend on where the escape sits in
    the list."""
    _make_escape_symlink(scenario, "aa-escape")

    with pytest.raises(WriteScopeViolation):
        revert_paths(scenario.repo, ["src/app.py", "src/new.py", "aa-escape"])

    _assert_in_repo_violations_reverted(scenario.repo)


def test_escape_only_list_still_raises_without_touching_the_in_repo_files(
    scenario: _Scenario,
) -> None:
    """With nothing revertible in the list, `revert_paths` must still fail
    loudly rather than return quietly -- and the two in-repo files, which
    were never named in this call, are left exactly as the fixture staged
    them (not reverted, since neither was passed)."""
    _make_escape_symlink(scenario, "aa-escape")

    with pytest.raises(WriteScopeViolation):
        revert_paths(scenario.repo, ["aa-escape"])

    assert (scenario.repo / "src" / "app.py").read_text(encoding="utf-8") == (
        _TAMPERED_APP_CONTENT
    )
    assert (scenario.repo / "src" / "new.py").exists()


def test_multiple_escapes_are_all_named_in_the_single_raised_exception(
    scenario: _Scenario,
) -> None:
    """The fix collects escapes and raises once -- it does not raise on the
    first escape it meets. Two escaping symlinks plus one in-repository
    violation: the in-repository violation is still reverted, and the
    single raised exception names both escaping paths."""
    _make_escape_symlink(scenario, "aa-escape-one")
    _make_escape_symlink(scenario, "aa-escape-two")

    with pytest.raises(WriteScopeViolation) as excinfo:
        revert_paths(scenario.repo, ["aa-escape-one", "aa-escape-two", "src/app.py"])

    message = str(excinfo.value)
    assert "aa-escape-one" in message
    assert "aa-escape-two" in message

    assert (scenario.repo / "src" / "app.py").read_text(encoding="utf-8") == (
        _ORIGINAL_APP_CONTENT
    )
    staged = run_git(["diff", "--cached", "--name-only"], cwd=scenario.repo).stdout
    assert "src/app.py" not in staged.splitlines()
