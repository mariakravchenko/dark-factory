"""The D-16 push proof: the token never appears in argv or a URL, the push
is retried a bounded number of times, and it is a silent no-op with no
token (05-03 Task 2).

Against a throwaway repository with a second local **bare** repository
standing in for ``origin``, mirroring the two-repository setup
``tests/unit/test_git_worktree.py`` already uses for the D-15 reconstruction
proof.

**Scope limit**, stated rather than papered over: a local ``file://``-style
remote does not itself demand HTTPS credentials, so these tests prove the
*plumbing* -- that the askpass script's env values are supplied correctly,
that the token is absent from every captured subprocess argument list and
from the remote URL, and that retry/no-token/failure behaviour is correct --
rather than proving real GitHub HTTPS auth end to end. A real-GitHub
verification belongs to an integration/smoke pass outside this repository's
own test suite.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import dark_factory.git.diff as diff_module
from dark_factory.git import GitCommandError, GitPushError
from dark_factory.git.client import run_git
from dark_factory.git.diff import GIT_PUSH_TOKEN_ENV_VAR, push_working_branch
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from tests.support.git_repo import git_commit_all, make_git_repo

pytestmark = pytest.mark.unit

_FAKE_DB_URL = "postgresql://df_fake_user:df_fake_pw_0123456789@fake-db.invalid:5432/df"
_FAKE_DB_URL_DIRECT = (
    "postgresql://df_fake_user:df_fake_pw_0123456789@fake-direct.invalid:5432/df"
)


def _origin_and_worktree(tmp_path: Path) -> tuple[Path, Path, str]:
    """A bare ``origin`` repository plus a real worktree of a fresh clone of
    it, on its own fresh working branch."""
    source = make_git_repo(tmp_path / "source")
    bare_origin = tmp_path / "origin.git"
    run_git(["clone", "-q", "--bare", str(source), str(bare_origin)], cwd=tmp_path)

    repo = tmp_path / "repo"
    run_git(["clone", "-q", str(bare_origin), str(repo)], cwd=tmp_path)

    run_id: UUID = uuid4()
    branch = working_branch_name(run_id)
    work_dir = ensure_worktree(repo, run_id, base_branch="main", working_branch=branch)
    return bare_origin, work_dir, branch


def test_happy_path_pushes_and_the_bare_origin_ref_matches_local_head(
    tmp_path: Path,
) -> None:
    bare_origin, work_dir, branch = _origin_and_worktree(tmp_path)
    (work_dir / "file.txt").write_text("content\n", encoding="utf-8")
    local_sha = git_commit_all(work_dir, "add file")

    push_working_branch(work_dir, working_branch=branch, token="fake-push-token-001")

    origin_sha = run_git(["rev-parse", branch], cwd=bare_origin).stdout.strip()
    assert origin_sha == local_sha


def test_token_never_appears_in_the_captured_run_git_argument_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_origin, work_dir, branch = _origin_and_worktree(tmp_path)
    (work_dir / "file.txt").write_text("content\n", encoding="utf-8")
    git_commit_all(work_dir, "add file")

    token = "fake-super-secret-push-token-999"
    real_run_git = diff_module.run_git
    captured: list[tuple[list[str], Mapping[str, str] | None]] = []

    def _spy(
        args: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
        timeout: int = 120,
        env_extra: Mapping[str, str] | None = None,
    ) -> object:
        captured.append((list(args), env_extra))
        return real_run_git(
            args, cwd=cwd, check=check, timeout=timeout, env_extra=env_extra
        )

    monkeypatch.setattr(diff_module, "run_git", _spy)

    push_working_branch(work_dir, working_branch=branch, token=token)

    push_calls = [call for call in captured if call[0][:1] == ["push"]]
    assert len(push_calls) == 1
    push_args, push_env_extra = push_calls[0]

    assert token not in push_args
    assert not any(token in arg for arg in push_args)
    assert "origin" in push_args
    # every arg naming the remote is the bare literal "origin", never a URL
    # with credentials embedded
    assert not any(arg.startswith(("http://", "https://")) for arg in push_args)

    assert push_env_extra is not None
    assert push_env_extra[GIT_PUSH_TOKEN_ENV_VAR] == token
    assert "GIT_ASKPASS" in push_env_extra

    origin_sha = run_git(["rev-parse", branch], cwd=bare_origin).stdout.strip()
    local_sha = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()
    assert origin_sha == local_sha


def test_none_token_is_a_silent_noop_with_no_run_git_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bare_origin, work_dir, branch = _origin_and_worktree(tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(diff_module, "run_git", lambda *a, **kw: calls.append((a, kw)))

    result = push_working_branch(work_dir, working_branch=branch, token=None)

    assert result is None
    assert calls == []


def test_no_origin_remote_is_a_silent_noop_with_no_run_git_push_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository with no ``origin`` configured at all (this whole test
    suite's own ``make_git_repo`` default) must not fail a role merely
    because a push token happens to be present in the environment -- D-16's
    reconstruction path has nothing to serve without a remote in the first
    place."""
    repo = make_git_repo(tmp_path / "repo")
    real_run_git = diff_module.run_git
    push_calls: list[object] = []

    def _spy(
        args: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
        timeout: int = 120,
        env_extra: Mapping[str, str] | None = None,
    ) -> object:
        if list(args)[:1] == ["push"]:
            push_calls.append(args)
        return real_run_git(
            args, cwd=cwd, check=check, timeout=timeout, env_extra=env_extra
        )

    monkeypatch.setattr(diff_module, "run_git", _spy)

    result = push_working_branch(
        repo, working_branch="dark-factory/run-no-origin", token="fake-push-token-003"
    )

    assert result is None
    assert push_calls == []


def test_transient_push_failure_is_retried_and_eventually_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_origin, work_dir, branch = _origin_and_worktree(tmp_path)
    (work_dir / "file.txt").write_text("content\n", encoding="utf-8")
    local_sha = git_commit_all(work_dir, "add file")

    real_run_git = diff_module.run_git
    attempts = {"push": 0}

    def _flaky(
        args: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
        timeout: int = 120,
        env_extra: Mapping[str, str] | None = None,
    ) -> object:
        if list(args)[:1] == ["push"]:
            attempts["push"] += 1
            if attempts["push"] < 3:
                raise GitCommandError(tuple(args), 1, "transient failure", cwd=cwd)
        return real_run_git(
            args, cwd=cwd, check=check, timeout=timeout, env_extra=env_extra
        )

    monkeypatch.setattr(diff_module, "run_git", _flaky)

    push_working_branch(work_dir, working_branch=branch, token="fake-push-token-002")

    assert attempts["push"] == 3
    origin_sha = run_git(["rev-parse", branch], cwd=bare_origin).stdout.strip()
    assert origin_sha == local_sha


def test_retry_exhaustion_raises_git_push_error_with_a_redacted_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", _FAKE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", _FAKE_DB_URL_DIRECT)
    token = "fake-push-token-abcdefghijklmno"
    monkeypatch.setenv("GITHUB_TOKEN", token)

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        _bare_origin, work_dir, branch = _origin_and_worktree(tmp_path)
        (work_dir / "file.txt").write_text("content\n", encoding="utf-8")
        git_commit_all(work_dir, "add file")

        real_run_git = diff_module.run_git
        attempts = {"push": 0}

        def _always_fails(
            args: Sequence[str],
            *,
            cwd: Path,
            check: bool = True,
            timeout: int = 120,
            env_extra: Mapping[str, str] | None = None,
        ) -> object:
            if list(args)[:1] == ["push"]:
                attempts["push"] += 1
                raise GitCommandError(
                    tuple(args), 1, f"push denied: bad credentials {token}", cwd=cwd
                )
            # non-push calls (e.g. the `remote get-url origin` preflight
            # check) pass through to the real implementation unchanged.
            return real_run_git(
                args, cwd=cwd, check=check, timeout=timeout, env_extra=env_extra
            )

        monkeypatch.setattr(diff_module, "run_git", _always_fails)

        with pytest.raises(GitPushError) as excinfo:
            push_working_branch(work_dir, working_branch=branch, token=token)

        assert attempts["push"] == 3
        assert token not in str(excinfo.value)
        assert "[redacted:github_token]" in str(excinfo.value)
    finally:
        get_settings.cache_clear()
