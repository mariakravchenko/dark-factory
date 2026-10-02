"""Unit coverage for GIT-04's idempotency contract (Phase 10, plan 10-02):
the three-way persisted-identifier fast path plus the GitHub-side
existing-PR safety net inside ``orchestrator/publish.py::run_publish_step``.

No database and no ``Settings`` construction: this module opens no
PostgreSQL connection and constructs no ``Settings`` object at all --
:class:`~dark_factory.persistence.repositories.RunState` is a frozen pydantic
model constructed directly, the git primitives (``commit_run_artifacts`` /
``push_working_branch`` / ``head_sha``) are monkeypatched with recording
spies rather than exercised against a real git repository (what plan
10-06's own ``tests/unit/test_publish_step_unit.py`` proves against a real
throwaway repo, this file assumes and instead proves the *decision* each
partial-completion point makes, fast and deterministically), and the push
token is passed as an explicit ``push_token`` keyword rather than read off a
settings object -- so this module needs no ``DATABASE_URL`` present in the
environment at all (a required URL string is not the same as a reachable
server). :class:`~tests.support.fake_github.FakeGitHubClient` (built
complete by plan 10-01) stands in for GitHub itself; call *order* is
asserted positionally, not just membership, because the claim under test is
that the existence check precedes the create.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import dark_factory.orchestrator.publish as publish_module
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.git.worktree import working_branch_name
from dark_factory.github import GitHubApiError
from dark_factory.github.client import GitHubPullRequest
from dark_factory.orchestrator.publish import PublishResult, run_publish_step
from dark_factory.persistence.repositories import RunState
from tests.support.fake_github import FakeGitHubClient

pytestmark = pytest.mark.unit

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 5
_BASE_BRANCH = "main"
_WORK_DIR = Path("/dark-factory-test/never-touched")
_COMMIT_SHA = "cafef00d" * 5  # a 40-character placeholder SHA
_KNOWN_SECRETS: dict[str, str] = {}
# Obviously-fake, greppable push token -- reuses tests/conftest.py's own
# fake-GitHub-token shape (``ghp_FAKE...``) rather than inventing a new
# spelling (T-11-33).
_FAKE_PUSH_TOKEN = "ghp_FAKEfakeFAKEfake2222222222222222222222"


def _run_state(
    run_id: UUID,
    *,
    working_branch: str,
    published_commit_sha: str | None = None,
    pr_number: int | None = None,
    pr_url: str | None = None,
) -> RunState:
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
        pr_number=pr_number,
        pr_url=pr_url,
        published_commit_sha=published_commit_sha,
        pending_clarification_comment_id=None,
    )


class _OrderedFakeGitHubClient(FakeGitHubClient):
    """:class:`FakeGitHubClient`'s exact scripted behaviour, plus recording
    each GitHub call's name into ``order`` -- a list shared with the git
    spies :func:`_install_git_spies` installs -- so a test can assert the
    *interleaved* ordering across git and GitHub calls, not just membership."""

    def __init__(self, *, order: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._order = order

    def find_pull_request_for_branch(
        self, owner: str, repo: str, *, head_branch: str
    ) -> GitHubPullRequest | None:
        self._order.append("find_pull_request_for_branch")
        return super().find_pull_request_for_branch(owner, repo, head_branch=head_branch)

    def create_pull_request(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> GitHubPullRequest:
        self._order.append("create_pull_request")
        return super().create_pull_request(
            owner, repo, title=title, head=head, base=base, body=body
        )


class _HeadScopedFakeGitHubClient(FakeGitHubClient):
    """A minimal double simulating GitHub's own server-side ``head=`` filter
    on ``pulls.list``: the scripted "existing" pull request is returned only
    when the requested ``head_branch`` matches ``scripted_head_branch`` -- a
    foreign branch (a pull request exists on the repository, but not on
    *this* run's deterministic working branch) returns ``None``, exactly as
    the real :class:`~dark_factory.github.client.GitHubClient`'s
    ``head=f"{owner}:{branch}"``-filtered call would. Kept local to this
    file (not an extension of the shared ``tests/support/fake_github.py``
    fixture, out of this plan's ``files_modified``) -- a minimal override is
    enough to prove the head-branch-equality rule."""

    def __init__(self, *, scripted_head_branch: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._scripted_head_branch = scripted_head_branch

    def find_pull_request_for_branch(
        self, owner: str, repo: str, *, head_branch: str
    ) -> GitHubPullRequest | None:
        if head_branch != self._scripted_head_branch:
            self.calls.append(
                (
                    "find_pull_request_for_branch",
                    {"owner": owner, "repo": repo, "head_branch": head_branch},
                )
            )
            self._maybe_raise("find_pull_request_for_branch")
            return None
        return super().find_pull_request_for_branch(owner, repo, head_branch=head_branch)


def _install_git_spies(
    monkeypatch: pytest.MonkeyPatch,
    order: list[str],
    *,
    commit_sha: str = _COMMIT_SHA,
    received_tokens: list[str | None] | None = None,
) -> None:
    """Replace the three git primitives ``publish.py`` calls with recording
    spies that touch no real filesystem or git repository -- ``commit``
    always finds "something new" (so the ordering scenario also exercises
    the push call), returning a fixed SHA.

    When ``received_tokens`` is supplied, ``_push``'s own ``token`` keyword
    is appended to it -- the channel a test reads back to prove the value
    supplied as ``run_publish_step``'s ``push_token`` is the exact value
    ``push_working_branch`` receives."""

    def _commit(work_dir: Path, run_id: UUID, *, role: str) -> str | None:
        order.append("commit_run_artifacts")
        return commit_sha

    def _push(work_dir: Path, *, working_branch: str, token: str | None) -> None:
        order.append("push_working_branch")
        if received_tokens is not None:
            received_tokens.append(token)

    def _head_sha(work_dir: Path) -> str:
        order.append("head_sha")
        return commit_sha

    monkeypatch.setattr(publish_module, "commit_run_artifacts", _commit)
    monkeypatch.setattr(publish_module, "push_working_branch", _push)
    monkeypatch.setattr(publish_module, "head_sha", _head_sha)


def _install_failing_git_spies(monkeypatch: pytest.MonkeyPatch, order: list[str]) -> None:
    """Like :func:`_install_git_spies`, but any call is a test failure --
    used to prove point (c) and point (b)'s "no second commit" claim without
    depending on the git spies' own return values."""

    def _fail_commit(work_dir: Path, run_id: UUID, *, role: str) -> str | None:
        order.append("commit_run_artifacts")
        raise AssertionError("commit_run_artifacts must not be called here")

    def _fail_push(work_dir: Path, *, working_branch: str, token: str | None) -> None:
        order.append("push_working_branch")
        raise AssertionError("push_working_branch must not be called here")

    def _fail_head_sha(work_dir: Path) -> str:
        order.append("head_sha")
        raise AssertionError("head_sha must not be called here")

    monkeypatch.setattr(publish_module, "commit_run_artifacts", _fail_commit)
    monkeypatch.setattr(publish_module, "push_working_branch", _fail_push)
    monkeypatch.setattr(publish_module, "head_sha", _fail_head_sha)


def test_all_three_identifiers_recorded_returns_them_with_no_client_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point (c): everything already recorded -- the fast path is free."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_failing_git_spies(monkeypatch, order)
    state = _run_state(
        run_id,
        working_branch=working_branch,
        published_commit_sha=_COMMIT_SHA,
        pr_number=99,
        pr_url="https://example.invalid/pr/99",
    )
    fake = _OrderedFakeGitHubClient(order=order)

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=None,  # fast path: no git command, no push
    )

    assert result == PublishResult(
        published_commit_sha=_COMMIT_SHA,
        pr_number=99,
        pr_url="https://example.invalid/pr/99",
        error=None,
        adopted_existing_pr=True,
    )
    assert fake.calls == []
    assert order == []


def test_pushed_but_unrecorded_pr_adopts_an_existing_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point (b): ``published_commit_sha`` set, ``pr_number`` NULL, and a
    matching pull request already exists on GitHub -- adopt it, no create,
    no second commit/push."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_failing_git_spies(monkeypatch, order)
    state = _run_state(
        run_id, working_branch=working_branch, published_commit_sha=_COMMIT_SHA
    )
    existing = GitHubPullRequest(number=99, url="https://example.invalid/pr/99")
    fake = _OrderedFakeGitHubClient(order=order, existing_pull_request=existing)

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=None,  # already pushed by an earlier attempt: no second push
    )

    assert result.pr_number == 99
    assert result.pr_url == "https://example.invalid/pr/99"
    assert result.adopted_existing_pr is True
    assert result.error is None
    find_calls = [c for c in fake.calls if c[0] == "find_pull_request_for_branch"]
    assert len(find_calls) == 1
    assert find_calls[0][1]["head_branch"] == working_branch
    assert [c[0] for c in fake.calls if c[0] == "create_pull_request"] == []
    assert order == ["find_pull_request_for_branch"]


def test_pushed_but_unrecorded_pr_creates_when_none_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point (b), no existing PR: the existence check runs, finds nothing,
    then exactly one create."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_failing_git_spies(monkeypatch, order)
    state = _run_state(
        run_id, working_branch=working_branch, published_commit_sha=_COMMIT_SHA
    )
    new_pr = GitHubPullRequest(number=7, url="https://example.invalid/pr/7")
    fake = _OrderedFakeGitHubClient(order=order, pull_request=new_pr)

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=None,  # already pushed by an earlier attempt: no second push
    )

    assert result.pr_number == 7
    assert result.adopted_existing_pr is False
    assert order == ["find_pull_request_for_branch", "create_pull_request"]


def test_nothing_recorded_commits_pushes_checks_then_creates_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point (a): nothing recorded -- commit, push, existence check, create,
    in that exact order."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_git_spies(monkeypatch, order)
    state = _run_state(run_id, working_branch=working_branch)
    new_pr = GitHubPullRequest(number=1, url="https://example.invalid/pr/1")
    fake = _OrderedFakeGitHubClient(order=order, pull_request=new_pr)

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert result.pr_number == 1
    assert result.published_commit_sha == _COMMIT_SHA
    assert result.adopted_existing_pr is False
    assert order == [
        "commit_run_artifacts",
        "push_working_branch",
        "head_sha",
        "find_pull_request_for_branch",
        "create_pull_request",
    ]


def test_push_working_branch_receives_the_token_the_caller_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one new assertion this task adds: the exact value passed as
    ``run_publish_step``'s ``push_token`` is the exact value
    ``push_working_branch`` receives as its ``token`` keyword. Before this
    task, the spy discarded the token and nothing proved the wire; breaking
    it now fails this test rather than silently pushing unauthenticated."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    received_tokens: list[str | None] = []
    _install_git_spies(monkeypatch, order, received_tokens=received_tokens)
    state = _run_state(run_id, working_branch=working_branch)
    new_pr = GitHubPullRequest(number=1, url="https://example.invalid/pr/1")
    fake = _OrderedFakeGitHubClient(order=order, pull_request=new_pr)

    run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert received_tokens == [_FAKE_PUSH_TOKEN]


def test_existing_pr_on_a_different_head_branch_is_not_adopted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The GIT-04 prohibition made mechanical: a pull request that exists
    somewhere on the repository, but not on this run's own deterministic
    working branch, is never adopted -- a create happens instead."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_git_spies(monkeypatch, order)
    state = _run_state(run_id, working_branch=working_branch)
    unrelated = GitHubPullRequest(number=555, url="https://example.invalid/pr/555")
    new_pr = GitHubPullRequest(number=8, url="https://example.invalid/pr/8")
    fake = _HeadScopedFakeGitHubClient(
        scripted_head_branch="some-completely-different-branch",
        existing_pull_request=unrelated,
        pull_request=new_pr,
    )

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert result.pr_number == 8
    assert result.pr_number != 555
    assert result.adopted_existing_pr is False
    create_calls = [c for c in fake.calls if c[0] == "create_pull_request"]
    assert len(create_calls) == 1


def test_create_pr_false_short_circuits_before_any_check_or_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    _install_failing_git_spies(monkeypatch, order)
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    state = _run_state(run_id, working_branch=working_branch)
    fake = _OrderedFakeGitHubClient(order=order)

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=None,
        create_pr=False,
        known_secrets=_KNOWN_SECRETS,
        push_token=None,  # create_pr=False early return: no push
    )

    assert result == PublishResult(
        published_commit_sha=None,
        pr_number=None,
        pr_url=None,
        error=None,
        adopted_existing_pr=False,
    )
    assert fake.calls == []
    assert order == []


def test_github_api_error_from_find_pull_request_does_not_fall_through_to_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable GitHub state must never be treated as "no PR exists"."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_failing_git_spies(monkeypatch, order)
    state = _run_state(
        run_id, working_branch=working_branch, published_commit_sha=_COMMIT_SHA
    )
    fake = _OrderedFakeGitHubClient(
        order=order,
        raises={
            "find_pull_request_for_branch": GitHubApiError(
                "service unavailable", status_code=503, endpoint="pulls.list"
            )
        },
    )

    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        push_token=None,  # already pushed by an earlier attempt: no second push
    )

    assert result.pr_number is None
    assert result.error
    assert "service unavailable" in result.error
    assert [c[0] for c in fake.calls if c[0] == "create_pull_request"] == []
    assert order == ["find_pull_request_for_branch"]


@pytest.mark.parametrize(
    "state_kwargs",
    [
        pytest.param({}, id="point-a-nothing-recorded"),
        pytest.param(
            {"published_commit_sha": _COMMIT_SHA}, id="point-b-pushed-unrecorded"
        ),
    ],
)
def test_no_client_call_besides_find_or_create(
    monkeypatch: pytest.MonkeyPatch, state_kwargs: dict[str, object]
) -> None:
    """Across every scenario that reaches Stage 3, the only client calls
    ``run_publish_step`` ever issues are ``find_pull_request_for_branch`` and
    ``create_pull_request`` -- never a comment, update, or merge call."""
    run_id = uuid4()
    working_branch = working_branch_name(run_id)
    order: list[str] = []
    _install_git_spies(monkeypatch, order)
    state = _run_state(run_id, working_branch=working_branch, **state_kwargs)  # type: ignore[arg-type]
    new_pr = GitHubPullRequest(number=3, url="https://example.invalid/pr/3")
    fake = _OrderedFakeGitHubClient(order=order, pull_request=new_pr)

    run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=_WORK_DIR,
        client=fake,
        create_pr=True,
        known_secrets=_KNOWN_SECRETS,
        # point-a actually pushes (nothing recorded); point-b does not
        # (already pushed by an earlier attempt) -- the fake token is
        # harmless on the path that never reads it.
        push_token=_FAKE_PUSH_TOKEN,
    )

    assert {name for name, _ in fake.calls} <= {
        "find_pull_request_for_branch",
        "create_pull_request",
    }
