"""The one ``githubkit`` wrapper (D-03).

This is the only module in ``dark_factory`` that constructs a ``githubkit``
client. ``Settings.github_token`` is the only credential that ever reaches
it: the token is unwrapped from ``SecretStr`` at the single construction
frame (:meth:`GitHubClient.from_settings`) and never placed in an exception
message, log field or event payload. Every error message this module
raises passes through :func:`dark_factory.events.redaction.redact` before
it is raised -- the same defense-in-depth
:func:`~dark_factory.git.diff.push_working_branch` already applies,
because a GitHub error response can echo request headers.

Real ``githubkit`` 0.16.1 API surface (introspected against the installed
package -- 10-RESEARCH.md Assumptions A1/A2 confirmed correct, no
divergence from the researched OpenAPI-convention names):

* ``GitHub(token, timeout=...)`` -- the client constructor; ``token`` is a
  plain ``str`` accepted as the positional ``auth`` argument.
* ``gh.rest.issues.get(owner, repo, issue_number)`` ->
  ``Response[Issue]``; the parsed model is ``response.parsed_data``.
* ``gh.rest.issues.list_comments(owner, repo, issue_number, page=..., per_page=...)``
  -> ``Response[list[IssueComment]]``.
* ``gh.rest.paginate(gh.rest.issues.list_comments, owner=..., repo=..., issue_number=...)``
  -- the non-deprecated pagination helper (``GitHub.paginate`` itself is
  deprecated in 0.16.1 in favour of ``rest.paginate``); returns an
  iterator over every page's items, not just the first.
* ``gh.rest.issues.create_comment(owner, repo, issue_number, body=...)``
  -> ``Response[IssueComment]`` (keyword args merge directly into the
  request JSON body when ``data=`` is not given).
* ``gh.rest.pulls.create(owner, repo, title=..., head=..., base=..., body=...)``
  -> ``Response[PullRequest]``.
* ``gh.rest.pulls.list(owner, repo, head=f"{owner}:{branch}", state="all")``
  -> ``Response[list[PullRequestSimple]]``.
* ``gh.rest.users.get_authenticated()`` -> ``Response[PrivateUser | PublicUser]``;
  the parsed model's ``.login`` is the token's own identity (Phase 10, plan
  10-04, 10-RESEARCH.md Assumption A4/Pitfall 2).
* ``gh.rest.actions.create_workflow_dispatch(owner, repo, workflow_id, ref=...,
  inputs=...)`` -- confirmed present in the installed ``githubkit`` 0.16.1
  package (Phase 11, plan 11-01, 11-RESEARCH.md Pattern 1). Two verified
  facts: ``workflow_id`` accepts the workflow **file name** in place of a
  numeric id (the endpoint's own installed docstring says so -- this is why
  ``dispatch_workflow`` below can pass ``"resume.yml"`` directly); and an
  optional ``return_run_details`` parameter, added to the GitHub API on
  2026-02-19, would turn the default ``204 No Content`` response into a
  ``200 OK`` carrying the dispatched run's id and URL. Deliberately not
  requested here -- this phase has no dispatched-run observability
  requirement -- but named here as the hook a later observability phase
  (Phase 12) would use.
* Failures raise ``githubkit.exception.GitHubException`` subclasses (most
  commonly ``RequestFailed``), carrying ``.response.status_code`` and
  ``.response.text`` when the failure reached a real HTTP response.
* An issue's ``labels`` field is ``list[str | LabelObject]`` -- GitHub
  returns either a bare label name or an object carrying a ``.name``
  attribute depending on the endpoint/media type, so both shapes are
  normalized here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from githubkit import GitHub
from githubkit.exception import GitHubException
from pydantic import BaseModel, ConfigDict

from dark_factory.events.redaction import redact
from dark_factory.github import (
    GitHubApiError,
    GitHubError,
    MissingGitHubCredentialError,
)

if TYPE_CHECKING:
    from dark_factory.config.settings import Settings

__all__ = [
    "GitHubClient",
    "GitHubComment",
    "GitHubError",
    "GitHubIssue",
    "GitHubPullRequest",
]


class GitHubComment(BaseModel):
    """One comment on a GitHub issue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    author: str
    body: str


class GitHubIssue(BaseModel):
    """A GitHub issue, normalized to the fields Dark Factory needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    title: str
    body: str
    labels: list[str]
    comments: list[GitHubComment]


class GitHubPullRequest(BaseModel):
    """A GitHub pull request, normalized to the fields Dark Factory needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    url: str


def _label_name(label: Any) -> str:
    """A label arrives as either a bare string or an object carrying ``.name``."""
    if isinstance(label, str):
        return label
    name = getattr(label, "name", None)
    return name if isinstance(name, str) else str(label)


def _comment_author(user: Any) -> str:
    """A comment's ``user`` is ``SimpleUser | None`` -- fall back to a
    stable placeholder rather than raise when GitHub reports a
    deleted/ghost user."""
    login = getattr(user, "login", None)
    return login if isinstance(login, str) else "ghost"


class GitHubClient:
    """The one wrapper for GitHub's REST API this project uses."""

    def __init__(
        self,
        *,
        token: str,
        timeout: int = 30,
        known_secrets: dict[str, str] | None = None,
    ) -> None:
        self._token = token
        self._timeout = timeout
        self._known_secrets = (
            known_secrets
            if known_secrets is not None
            else ({token: "github_token"} if len(token) >= 8 else {})
        )
        self._client = GitHub(token, timeout=float(timeout))
        # A plain instance attribute, not a module-level cache (Phase 10,
        # plan 10-04): a module cache would be shared across every token and
        # every test in the process, which is exactly wrong once more than
        # one ``GitHubClient`` -- or more than one test -- exists.
        self._authenticated_login: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubClient:
        """Build a client from ``Settings.github_token`` -- the single
        frame where the token is unwrapped from ``SecretStr``."""
        if settings.github_token is None:
            raise MissingGitHubCredentialError(
                "GITHUB_TOKEN is not configured (Settings.github_token is None)"
            )
        return cls(
            token=settings.github_token.get_secret_value(),
            known_secrets=settings.known_secret_values(),
        )

    @classmethod
    def for_dispatch(cls, settings: Settings) -> GitHubClient:
        """Build a client from ``Settings.dispatch_github_token`` -- the
        single frame where *that* credential is unwrapped from
        ``SecretStr`` (Phase 11, D-03). Mirrors :meth:`from_settings`
        exactly, substituting the dispatch-only token; never built from
        ``settings.github_token``."""
        if settings.dispatch_github_token is None:
            raise MissingGitHubCredentialError(
                "DISPATCH_GITHUB_TOKEN is not configured "
                "(Settings.dispatch_github_token is None)"
            )
        return cls(
            token=settings.dispatch_github_token.get_secret_value(),
            known_secrets=settings.known_secret_values(),
        )

    def _raise_api_error(self, exc: Exception, *, endpoint: str) -> None:
        status_code: int | None = None
        detail = str(exc)
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
            text = getattr(response, "text", None)
            if isinstance(text, str) and text:
                detail = text
        message = redact(
            f"GitHub API call failed ({endpoint}): {detail}",
            known_secrets=self._known_secrets,
        )
        raise GitHubApiError(
            message, status_code=status_code, endpoint=endpoint
        ) from exc

    def fetch_issue(self, owner: str, repo: str, *, issue_number: int) -> GitHubIssue:
        """One issue read plus a fully paginated comment read.

        Uses the SDK's own ``rest.paginate`` helper rather than a
        hand-rolled page loop, so an issue with more than one page of
        comments is read whole. A null ``body`` maps to the empty string
        here; the loader, not this client, decides the title-fallback.
        """
        try:
            issue = self._client.rest.issues.get(owner, repo, issue_number).parsed_data
            # ``rest.paginate``'s return type parameter cannot be inferred
            # without a ``map_func`` (it resolves to ``Paginator[Never]``);
            # an explicit ``Any`` here is the only annotation mypy accepts,
            # and every attribute this wrapper reads off each page item is
            # already duck-typed through ``_comment_author``/``getattr``.
            comment_pages: Any = self._client.rest.paginate(
                self._client.rest.issues.list_comments,
                owner=owner,
                repo=repo,
                issue_number=issue_number,
            )
            comments: list[GitHubComment] = [
                GitHubComment(
                    id=comment.id,
                    author=_comment_author(comment.user),
                    body=comment.body or "",
                )
                for comment in comment_pages
            ]
        except GitHubException as exc:
            self._raise_api_error(
                exc, endpoint=f"issues.get {owner}/{repo}#{issue_number}"
            )
            raise  # pragma: no cover - _raise_api_error always raises
        return GitHubIssue(
            number=issue.number,
            title=issue.title,
            body=issue.body or "",
            labels=[_label_name(label) for label in issue.labels],
            comments=comments,
        )

    def create_comment(
        self, owner: str, repo: str, *, issue_number: int, body: str
    ) -> GitHubComment:
        try:
            response = self._client.rest.issues.create_comment(
                owner, repo, issue_number, body=body
            )
        except GitHubException as exc:
            self._raise_api_error(
                exc, endpoint=f"issues.create_comment {owner}/{repo}#{issue_number}"
            )
            raise  # pragma: no cover - _raise_api_error always raises
        comment = response.parsed_data
        return GitHubComment(
            id=comment.id,
            author=_comment_author(comment.user),
            body=comment.body or "",
        )

    def create_pull_request(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> GitHubPullRequest:
        try:
            response = self._client.rest.pulls.create(
                owner, repo, title=title, head=head, base=base, body=body
            )
        except GitHubException as exc:
            self._raise_api_error(exc, endpoint=f"pulls.create {owner}/{repo}")
            raise  # pragma: no cover - _raise_api_error always raises
        pr = response.parsed_data
        return GitHubPullRequest(number=pr.number, url=pr.html_url)

    def authenticated_login(self) -> str:
        """The login of the identity behind the configured token (Phase 10,
        GIT-06, 10-RESEARCH.md Pitfall 2/Assumption A4).

        Issues exactly one API call even when invoked repeatedly on the same
        client instance -- the result is cached on ``self`` after the first
        call. The webhook resolver (``dark_factory.webhook.resolve``) compares
        an inbound comment's commenter login against this value to filter out
        Dark Factory's own posted comments, so this must be genuinely stable
        for the lifetime of one client / one token.
        """
        if self._authenticated_login is None:
            try:
                user = self._client.rest.users.get_authenticated().parsed_data
            except GitHubException as exc:
                self._raise_api_error(exc, endpoint="users.get_authenticated")
                raise  # pragma: no cover - _raise_api_error always raises
            self._authenticated_login = user.login
        return self._authenticated_login

    def dispatch_workflow(
        self, owner: str, repo: str, *, workflow_id: str, ref: str, run_id: str
    ) -> None:
        """Trigger a ``workflow_dispatch`` run of ``workflow_id`` (a workflow
        file name, e.g. ``"resume.yml"``) on ``ref`` (Phase 11, D-01/D-04).

        Returns ``None`` on success -- the endpoint answers ``204 No
        Content`` by default, so there is no body to read; "did not raise"
        is the success signal, never ``response.parsed_data``.
        """
        try:
            self._client.rest.actions.create_workflow_dispatch(
                owner,
                repo,
                workflow_id,
                ref=ref,
                inputs={"run_id": run_id},
            )
        except GitHubException as exc:
            self._raise_api_error(
                exc,
                endpoint=f"actions.create_workflow_dispatch {owner}/{repo}/{workflow_id}",
            )
            raise  # pragma: no cover - _raise_api_error always raises

    def find_pull_request_for_branch(
        self, owner: str, repo: str, *, head_branch: str
    ) -> GitHubPullRequest | None:
        """A pure read -- issues no write of any kind."""
        try:
            response = self._client.rest.pulls.list(
                owner, repo, head=f"{owner}:{head_branch}", state="all"
            )
        except GitHubException as exc:
            self._raise_api_error(exc, endpoint=f"pulls.list {owner}/{repo}")
            raise  # pragma: no cover - _raise_api_error always raises
        matches = response.parsed_data
        if not matches:
            return None
        first = matches[0]
        return GitHubPullRequest(number=first.number, url=first.html_url)
