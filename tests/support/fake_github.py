"""Hand-written test double for
:class:`dark_factory.github.client.GitHubClient` (Plan 10-01) -- scripted
responses and a call log, no network and no real ``githubkit`` client
(mirrors ``tests/support/fake_cli.py``'s idiom: this project prefers
hand-written fakes at the unit and db tiers over a stub HTTP server).

Built complete in this plan so plans 10-02, 10-03, 10-04 and 10-06 can use
it without modifying this file.
"""

from __future__ import annotations

from dark_factory.github.client import GitHubComment, GitHubIssue, GitHubPullRequest

__all__ = ["FakeGitHubClient"]


class FakeGitHubClient:
    """A scripted double implementing :class:`GitHubClient`'s exact
    five-method surface.

    ``issue`` is either a single scripted :class:`GitHubIssue` returned on
    every :meth:`fetch_issue` call, or a list of them consumed in order
    (the last entry repeats once exhausted) -- useful for a scenario that
    calls :meth:`fetch_issue` more than once and wants the second call to
    see updated content. ``raises`` maps a method name to an exception
    instance raised instead of returning, letting a test script a single
    method's failure without affecting the others. ``calls`` records every
    invocation as ``(method_name, kwargs)`` so a test can assert exactly
    which calls happened and with what arguments.

    ``login`` (CR-01, 10-REVIEW.md) is the fixed identity
    :meth:`authenticated_login` returns -- mirrors
    :meth:`~dark_factory.github.client.GitHubClient.authenticated_login`'s
    real, cached-on-the-instance shape without a real API call. Defaults to
    ``"dark-factory-bot"``, a value distinct from :meth:`create_comment`'s
    own hardcoded ``author="dark-factory"`` fixture value, so a test that
    scripts an "already posted by us" comment must say so explicitly
    (``author=<the same login>``) rather than accidentally match.
    """

    def __init__(
        self,
        *,
        issue: GitHubIssue | list[GitHubIssue] | None = None,
        pull_request: GitHubPullRequest | None = None,
        existing_pull_request: GitHubPullRequest | None = None,
        login: str = "dark-factory-bot",
        raises: dict[str, Exception] | None = None,
    ) -> None:
        self._issues: list[GitHubIssue] = (
            issue if isinstance(issue, list) else ([issue] if issue is not None else [])
        )
        self._issue_index = 0
        self._pull_request = pull_request
        self._existing_pull_request = existing_pull_request
        self._login = login
        self._raises = raises or {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _maybe_raise(self, method_name: str) -> None:
        exc = self._raises.get(method_name)
        if exc is not None:
            raise exc

    def fetch_issue(self, owner: str, repo: str, *, issue_number: int) -> GitHubIssue:
        self.calls.append(
            (
                "fetch_issue",
                {"owner": owner, "repo": repo, "issue_number": issue_number},
            )
        )
        self._maybe_raise("fetch_issue")
        if not self._issues:
            raise LookupError("FakeGitHubClient: no scripted issue configured")
        index = min(self._issue_index, len(self._issues) - 1)
        self._issue_index += 1
        return self._issues[index]

    def create_comment(
        self, owner: str, repo: str, *, issue_number: int, body: str
    ) -> GitHubComment:
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
        self._maybe_raise("create_comment")
        return GitHubComment(id=1, author="dark-factory", body=body)

    def create_pull_request(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> GitHubPullRequest:
        self.calls.append(
            (
                "create_pull_request",
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
        self._maybe_raise("create_pull_request")
        if self._pull_request is None:
            raise LookupError("FakeGitHubClient: no scripted pull_request configured")
        return self._pull_request

    def authenticated_login(self) -> str:
        self.calls.append(("authenticated_login", {}))
        self._maybe_raise("authenticated_login")
        return self._login

    def find_pull_request_for_branch(
        self, owner: str, repo: str, *, head_branch: str
    ) -> GitHubPullRequest | None:
        self.calls.append(
            (
                "find_pull_request_for_branch",
                {"owner": owner, "repo": repo, "head_branch": head_branch},
            )
        )
        self._maybe_raise("find_pull_request_for_branch")
        return self._existing_pull_request
