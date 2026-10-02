"""Unit coverage for ``orchestrator/publish.py::run_publish_step`` (Phase 10,
plan 10-06, GIT-03) -- against a real throwaway git repository (mirroring
``tests/unit/test_git_diff.py``'s discipline: a mock cannot reproduce
``git``'s genuine exit-code and refusal behaviour ``commit_run_artifacts``
depends on) and :class:`~tests.support.fake_github.FakeGitHubClient` (no
network, no real ``githubkit`` client -- built complete by plan 10-01 for
this plan to reuse unmodified).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.git.client import run_git
from dark_factory.git.worktree import working_branch_name
from dark_factory.github import GitHubApiError
from dark_factory.github.client import GitHubPullRequest
from dark_factory.orchestrator.publish import PublishResult, run_publish_step
from dark_factory.persistence.repositories import RunState
from tests.support.fake_github import FakeGitHubClient
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.unit

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 5
_BASE_BRANCH = "main"
# Obviously-fake, greppable push token -- reuses tests/conftest.py's own
# fake-GitHub-token shape (``ghp_FAKE...``) rather than inventing a new
# spelling (T-11-33).
_FAKE_PUSH_TOKEN = "ghp_FAKEfakeFAKEfake3333333333333333333333"


def _run_state(run_id: UUID, *, working_branch: str) -> RunState:
    return RunState(
        run_id=run_id,
        status=RunStatus.QA,
        current_role="QA",
        current_step=3,
        normalized_task=NormalizedTask(
            source_kind="github",
            source_ref=f"{_OWNER}/{_REPO}#{_ISSUE_NUMBER}",
            title="Fix the flaky retry logic",
            body="issue body",
            metadata={
                "owner": _OWNER,
                "repo": _REPO,
                "issue_number": _ISSUE_NUMBER,
                "labels": ["bug"],
                "comment_count": 2,
            },
        ),
        workflow={
            "roles": ["QA"],
            "repository": {
                "base_branch": _BASE_BRANCH,
                "github_owner": _OWNER,
                "github_repo": _REPO,
            },
        },
        qa_developer_iterations=0,
        quality_gate_iterations=0,
        latest_execution=None,
        pending_answer=None,
        base_branch=_BASE_BRANCH,
        working_branch=working_branch,
        pr_number=None,
        pr_url=None,
        published_commit_sha=None,
        pending_clarification_comment_id=None,
    )


def _repo_on_working_branch(tmp_path: Path, run_id: UUID) -> tuple[Path, str]:
    repo = make_git_repo(tmp_path / "repo", base_branch=_BASE_BRANCH)
    working_branch = working_branch_name(run_id)
    run_git(["checkout", "-b", working_branch], cwd=repo)
    artifact = (
        repo
        / ".dark-factory"
        / "runs"
        / str(run_id)
        / "artifacts"
        / "QA"
        / "verdict.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"status": "PASS"}', encoding="utf-8")
    return repo, working_branch


def test_create_pr_true_returns_pushed_sha_and_pr_identifiers_from_one_call(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    repo, working_branch = _repo_on_working_branch(tmp_path, run_id)
    state = _run_state(run_id, working_branch=working_branch)
    fake = FakeGitHubClient(
        pull_request=GitHubPullRequest(number=42, url="https://example.invalid/pr/42")
    )

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=repo,
        client=fake,
        create_pr=True,
        known_secrets={},
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert isinstance(result, PublishResult)
    assert result.error is None
    assert result.pr_number == 42
    assert result.pr_url == "https://example.invalid/pr/42"
    assert result.published_commit_sha is not None
    assert (
        result.published_commit_sha
        == run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    )

    pr_calls = [c for c in fake.calls if c[0] == "create_pull_request"]
    assert len(pr_calls) == 1
    _, kwargs = pr_calls[0]
    assert kwargs["base"] == _BASE_BRANCH
    assert kwargs["head"] == working_branch
    assert kwargs["title"] == state.normalized_task.title


def test_pr_body_links_the_source_issue_and_carries_no_execution_scoped_data(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    repo, working_branch = _repo_on_working_branch(tmp_path, run_id)
    state = _run_state(run_id, working_branch=working_branch)
    fake = FakeGitHubClient(
        pull_request=GitHubPullRequest(number=1, url="https://example.invalid/pr/1")
    )

    run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=repo,
        client=fake,
        create_pr=True,
        known_secrets={},
        push_token=_FAKE_PUSH_TOKEN,
    )

    _, kwargs = next(c for c in fake.calls if c[0] == "create_pull_request")
    body = kwargs["body"]
    assert f"{_OWNER}/{_REPO}#{_ISSUE_NUMBER}" in body
    assert str(run_id) not in body
    assert str(repo) not in body
    assert "worker" not in body.lower()
    assert working_branch not in body


def test_create_pr_false_makes_no_github_call_and_returns_an_all_none_success(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    repo, working_branch = _repo_on_working_branch(tmp_path, run_id)
    state = _run_state(run_id, working_branch=working_branch)
    fake = FakeGitHubClient()

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=repo,
        client=None,
        create_pr=False,
        known_secrets={},
        push_token=None,  # create_pr=False early return: no push
    )

    assert result == PublishResult(
        published_commit_sha=None, pr_number=None, pr_url=None, error=None
    )
    assert fake.calls == []


def test_create_pull_request_raising_github_api_error_does_not_re_raise(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    repo, working_branch = _repo_on_working_branch(tmp_path, run_id)
    state = _run_state(run_id, working_branch=working_branch)
    fake = FakeGitHubClient(
        raises={
            "create_pull_request": GitHubApiError(
                "boom", status_code=422, endpoint="pulls.create"
            )
        }
    )

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=repo,
        client=fake,
        create_pr=True,
        known_secrets={},
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert result.pr_number is None
    assert result.pr_url is None
    assert result.error
    assert "boom" in result.error
