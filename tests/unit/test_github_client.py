"""Unit coverage for the one ``githubkit`` wrapper (D-03, Plan 10-01).

Exercises :class:`GitHubClient` against a hand-written stub standing in for
``githubkit.GitHub`` -- no network, no real SDK client. The stub mimics
just enough of the real 0.16.1 surface (``rest.issues.get``,
``rest.issues.list_comments`` + ``rest.paginate``,
``rest.issues.create_comment``, ``rest.pulls.create``, ``rest.pulls.list``)
to prove the wrapper's own call shape, credential handling and error
translation -- never a real network call.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from githubkit.exception import GitHubException

from dark_factory.config.settings import Settings
from dark_factory.github import GitHubApiError, MissingGitHubCredentialError
from dark_factory.github.client import GitHubClient

pytestmark = pytest.mark.unit

_FAKE_DB_URL = "postgresql+psycopg://fakeuser:fakepass@fake-host.example/darkfactory"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": _FAKE_DB_URL,
        "database_url_direct": _FAKE_DB_URL,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _label(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _user(login: str) -> SimpleNamespace:
    return SimpleNamespace(login=login)


def _comment(comment_id: int, author: str, body: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=comment_id, user=_user(author), body=body)


def _issue(
    number: int, title: str, body: str | None, labels: list[Any]
) -> SimpleNamespace:
    return SimpleNamespace(number=number, title=title, body=body, labels=labels)


def _pr(number: int, url: str) -> SimpleNamespace:
    return SimpleNamespace(number=number, html_url=url)


class _StubGitHubException(GitHubException):
    """Stands in for ``githubkit.exception.RequestFailed`` -- same public
    shape (``.response.status_code`` / ``.response.text``) without needing
    a real ``httpx`` request/response pair."""

    def __init__(self, *, status_code: int, text: str) -> None:
        super().__init__(f"stub request failed: {status_code}")
        self.response = SimpleNamespace(status_code=status_code, text=text)


class _StubResponse:
    def __init__(self, parsed_data: Any) -> None:
        self.parsed_data = parsed_data


class _StubIssuesClient:
    def __init__(
        self,
        *,
        issue: SimpleNamespace | None = None,
        comment_pages: list[list[SimpleNamespace]] | None = None,
        created_comment: SimpleNamespace | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._issue = issue
        self._comment_pages = comment_pages or []
        self._created_comment = created_comment
        self._raise_exc = raise_exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, owner: str, repo: str, issue_number: int) -> _StubResponse:
        self.calls.append(
            ("get", {"owner": owner, "repo": repo, "issue_number": issue_number})
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._issue is not None
        return _StubResponse(self._issue)

    def list_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        page: int | None = None,
        per_page: int | None = None,
        **_: Any,
    ) -> _StubResponse:
        self.calls.append(("list_comments", {"page": page}))
        page_index = (page or 1) - 1
        items = (
            self._comment_pages[page_index]
            if 0 <= page_index < len(self._comment_pages)
            else []
        )
        return _StubResponse(items)

    def create_comment(
        self, owner: str, repo: str, issue_number: int, *, body: str, **_: Any
    ) -> _StubResponse:
        self.calls.append(
            (
                "create_comment",
                {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue_number,
                    "body": body,
                },
            )
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._created_comment is not None
        return _StubResponse(self._created_comment)


class _StubPullsClient:
    def __init__(
        self,
        *,
        created_pr: SimpleNamespace | None = None,
        list_result: list[SimpleNamespace] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._created_pr = created_pr
        self._list_result = list_result if list_result is not None else []
        self._raise_exc = raise_exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
        **_: Any,
    ) -> _StubResponse:
        self.calls.append(
            (
                "create",
                {
                    "owner": owner,
                    "repo": repo,
                    "title": title,
                    "head": head,
                    "base": base,
                    "body": body,
                },
            )
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._created_pr is not None
        return _StubResponse(self._created_pr)

    def list(
        self,
        owner: str,
        repo: str,
        *,
        head: str | None = None,
        state: str | None = None,
        **_: Any,
    ) -> _StubResponse:
        self.calls.append(
            ("list", {"owner": owner, "repo": repo, "head": head, "state": state})
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        return _StubResponse(self._list_result)


class _StubRest:
    def __init__(self, issues: _StubIssuesClient, pulls: _StubPullsClient) -> None:
        self.issues = issues
        self.pulls = pulls

    def paginate(self, request_fn: Any, **kwargs: Any) -> Any:
        """Mirrors the real ``rest.paginate``'s page-by-page contract
        closely enough to prove the wrapper reads every page: calls
        ``request_fn`` with an increasing ``page=`` until a page comes back
        empty."""
        page = 1
        while True:
            response = request_fn(
                kwargs.get("owner"),
                kwargs.get("repo"),
                kwargs.get("issue_number"),
                page=page,
                per_page=100,
            )
            items = response.parsed_data
            if not items:
                return
            yield from items
            page += 1


def _make_stub_github(
    *, issues_client: _StubIssuesClient, pulls_client: _StubPullsClient
) -> type:
    class _StubGitHub:
        def __init__(
            self, token: str, *, timeout: float | None = None, **_: Any
        ) -> None:
            self.token = token
            self.timeout = timeout
            self.rest = _StubRest(issues_client, pulls_client)

    return _StubGitHub


def _patch_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issues_client: _StubIssuesClient | None = None,
    pulls_client: _StubPullsClient | None = None,
) -> None:
    monkeypatch.setattr(
        "dark_factory.github.client.GitHub",
        _make_stub_github(
            issues_client=issues_client or _StubIssuesClient(),
            pulls_client=pulls_client or _StubPullsClient(),
        ),
    )


# --------------------------------------------------------------------------- #
# from_settings / credential handling
# --------------------------------------------------------------------------- #


def test_from_settings_with_no_github_token_raises_missing_credential_error() -> None:
    with pytest.raises(MissingGitHubCredentialError):
        GitHubClient.from_settings(_settings(github_token=None))


def test_from_settings_with_a_token_builds_a_working_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = _issue(1, "T", "B", [])
    issues_client = _StubIssuesClient(issue=issue, comment_pages=[[]])
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient.from_settings(
        _settings(github_token="ghp_faketoken1234567890")
    )
    result = client.fetch_issue("o", "r", issue_number=1)

    assert result.number == 1


# --------------------------------------------------------------------------- #
# fetch_issue
# --------------------------------------------------------------------------- #


def test_fetch_issue_returns_title_body_labels_comments_in_api_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = _issue(152, "Title", "Body text", [_label("bug"), "enhancement"])
    comments = [_comment(1, "alice", "first"), _comment(2, "bob", "second")]
    issues_client = _StubIssuesClient(issue=issue, comment_pages=[comments])
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.fetch_issue("o", "r", issue_number=152)

    assert result.number == 152
    assert result.title == "Title"
    assert result.body == "Body text"
    assert result.labels == ["bug", "enhancement"]
    assert [c.author for c in result.comments] == ["alice", "bob"]
    assert [c.body for c in result.comments] == ["first", "second"]


def test_fetch_issue_reads_every_comment_across_two_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = _issue(152, "T", "B", [])
    page1 = [_comment(1, "a", "c1")]
    page2 = [_comment(2, "b", "c2")]
    issues_client = _StubIssuesClient(issue=issue, comment_pages=[page1, page2])
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.fetch_issue("o", "r", issue_number=152)

    assert [c.body for c in result.comments] == ["c1", "c2"]


def test_fetch_issue_maps_a_null_body_to_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = _issue(1, "T", None, [])
    issues_client = _StubIssuesClient(issue=issue, comment_pages=[[]])
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.fetch_issue("o", "r", issue_number=1)

    assert result.body == ""


def test_fetch_issue_for_a_missing_issue_raises_github_api_error_not_the_raw_sdk_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issues_client = _StubIssuesClient(
        raise_exc=_StubGitHubException(status_code=404, text="Not Found")
    )
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    with pytest.raises(GitHubApiError) as excinfo:
        client.fetch_issue("o", "r", issue_number=999)

    assert excinfo.value.status_code == 404


def test_api_error_message_omits_a_known_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "ghp_realfaketoken1234567890abcdef"
    issues_client = _StubIssuesClient(
        raise_exc=_StubGitHubException(
            status_code=401, text=f"Bad credentials: {token}"
        )
    )
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient.from_settings(_settings(github_token=token))
    with pytest.raises(GitHubApiError) as excinfo:
        client.fetch_issue("o", "r", issue_number=1)

    assert token not in str(excinfo.value)


# --------------------------------------------------------------------------- #
# create_comment
# --------------------------------------------------------------------------- #


def test_create_comment_returns_a_comment_carrying_the_posted_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _comment(42, "dark-factory", "hello")
    issues_client = _StubIssuesClient(created_comment=created)
    _patch_sdk(monkeypatch, issues_client=issues_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.create_comment("o", "r", issue_number=1, body="hello")

    assert result.id == 42
    assert result.body == "hello"


# --------------------------------------------------------------------------- #
# create_pull_request
# --------------------------------------------------------------------------- #


def test_create_pull_request_passes_title_head_base_body_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pr = _pr(7, "https://github.com/o/r/pull/7")
    pulls_client = _StubPullsClient(created_pr=pr)
    _patch_sdk(monkeypatch, pulls_client=pulls_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.create_pull_request(
        "o", "r", title="T", head="h", base="b", body="B"
    )

    assert result.number == 7
    assert result.url == "https://github.com/o/r/pull/7"
    assert pulls_client.calls[-1] == (
        "create",
        {
            "owner": "o",
            "repo": "r",
            "title": "T",
            "head": "h",
            "base": "b",
            "body": "B",
        },
    )


# --------------------------------------------------------------------------- #
# find_pull_request_for_branch
# --------------------------------------------------------------------------- #


def test_find_pull_request_for_branch_returns_the_scripted_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pr = _pr(9, "https://github.com/o/r/pull/9")
    pulls_client = _StubPullsClient(list_result=[pr])
    _patch_sdk(monkeypatch, pulls_client=pulls_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.find_pull_request_for_branch(
        "o", "r", head_branch="dark-factory/run-abc"
    )

    assert result is not None
    assert result.number == 9
    assert pulls_client.calls == [
        (
            "list",
            {
                "owner": "o",
                "repo": "r",
                "head": "o:dark-factory/run-abc",
                "state": "all",
            },
        )
    ]
    assert not any(name == "create" for name, _ in pulls_client.calls)


def test_find_pull_request_for_branch_returns_none_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pulls_client = _StubPullsClient(list_result=[])
    _patch_sdk(monkeypatch, pulls_client=pulls_client)

    client = GitHubClient(token="ghp_faketoken1234567890")
    result = client.find_pull_request_for_branch("o", "r", head_branch="no-match")

    assert result is None
