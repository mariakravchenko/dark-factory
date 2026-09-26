"""Source loaders -- normalize every origin to one :class:`NormalizedTask` (INTAKE-05).

Once :func:`load` returns, nothing downstream knows or cares where the task came
from. ``text:`` (Phase 1), ``spec:`` (Phase 4) and ``github:`` (Phase 10) are all
real loaders now.

Loader selection is a ``{SourceKind: loader}`` mapping, not a chain of
conditionals on the kind: adding a kind without a matching loader fails at import
time (the key-set assertion in the tests), never silently at runtime.

``load``'s ``repository`` keyword (Phase 10, 10-RESEARCH.md Pattern 1) is the one
new piece of dispatch surface this phase adds: it carries the calling run's
repo-config ``repository:`` mapping (``github_owner`` / ``github_repo``, D-04) so
``_load_github`` can validate it before any network call. It is optional and
keyword-only so ``_load_text`` and ``_load_spec``'s existing call sites and tests
need no change -- both loaders accept and ignore it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from dark_factory.config.settings import get_settings
from dark_factory.domain.task import NormalizedTask
from dark_factory.github import GitHubClient, GitHubError
from dark_factory.input.resolver import SourceKind, UnresolvableSourceError

__all__ = ["load"]

_TITLE_MAX_LEN = 120

# A locator is a positive decimal integer with no leading zero -- "0", "-1",
# "1.5", "007" and "abc" are all refused. D-04: owner/repo come from config
# only, never from the locator, so this is the entire locator-side surface a
# crafted string could ever try to abuse.
_POSITIVE_INTEGER_LOCATOR = re.compile(r"[1-9][0-9]*")


class SourceNotSupportedError(NotImplementedError):
    """Raised by a loader for a source kind whose implementation lands in a later phase.

    No loader in this module raises it any longer -- ``text:``, ``spec:``
    and ``github:`` are all real -- but the class stays declared and
    exported: ``cli.run``'s exception tuple and
    ``tests/integration/test_unsupported_source.py`` still reference it,
    and it is retained for a future source kind.
    """


class _Loader(Protocol):
    def __call__(
        self, locator: str, *, repository: Mapping[str, Any] | None = None
    ) -> NormalizedTask: ...


def _load_text(
    locator: str, *, repository: Mapping[str, Any] | None = None
) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a plain-text task body.

    Surrounding double quotes and outer whitespace are stripped so
    ``run text:"do the thing"`` and ``run text:do the thing`` produce the same
    task. An empty or whitespace-only body is refused with
    :class:`UnresolvableSourceError` -- the CLI turns that into exit 2 with
    nothing persisted. ``repository`` is accepted and ignored -- this loader
    has no use for repo config.
    """
    body = locator.strip().strip('"')
    if not body:
        raise UnresolvableSourceError("text: task body is empty")
    title = body.splitlines()[0][:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="text",
        source_ref=None,
        title=title,
        body=body,
        metadata={},
    )


def _strip_heading_marker(first_line: str) -> str:
    """Strip a leading Markdown heading marker (``#``, ``##``, ...) and the
    whitespace around it, so ``"# Ship a health endpoint"`` and
    ``"Ship a health endpoint"`` produce the same title."""
    stripped = first_line.lstrip()
    while stripped.startswith("#"):
        stripped = stripped[1:]
    return stripped.strip()


def _load_spec(
    locator: str, *, repository: Mapping[str, Any] | None = None
) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a Markdown spec file on disk.

    Mirrors :func:`_load_text`'s shape: the locator's outer whitespace and
    surrounding double quotes are stripped before it is treated as a path. A
    relative locator resolves against the current working directory; ``~``
    expands. A locator naming a non-file, or a file whose body is empty or
    whitespace-only, is refused with :class:`UnresolvableSourceError` naming the
    resolved path -- the CLI already maps that to exit 2 with nothing persisted.
    ``repository`` is accepted and ignored -- this loader has no use for repo
    config.
    """
    raw_path = locator.strip().strip('"')
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()

    if not resolved.is_file():
        raise UnresolvableSourceError(f"spec: file not found: {resolved}")

    body = resolved.read_text(encoding="utf-8").strip()
    if not body:
        raise UnresolvableSourceError(f"spec: file is empty: {resolved}")

    first_line = body.splitlines()[0]
    title = _strip_heading_marker(first_line)[:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="spec",
        source_ref=str(resolved),
        title=title,
        body=body,
        metadata={},
    )


def _load_github(
    locator: str, *, repository: Mapping[str, Any] | None = None
) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a GitHub issue (INTAKE-03).

    Validate first, fetch second -- mirrors :func:`_load_spec`'s shape.
    Refuses a locator that is not a positive decimal integer, and refuses a
    ``repository`` mapping that is ``None`` or lacks a non-empty
    ``github_owner`` / ``github_repo``, before any network call is made
    (D-04: owner and repo come from config, never from the CLI locator, so
    a crafted locator can never redirect the fetch at another repository).

    ``source_ref`` / ``metadata`` follow the Task 2 decision (option A1):
    ``source_ref = "{owner}/{repo}#{issue_number}"`` and
    ``metadata = {"owner", "repo", "issue_number", "labels",
    "comment_count"}``. ``title`` is the issue title, stripped of a leading
    heading marker and sliced to ``_TITLE_MAX_LEN`` by code point. ``body``
    is the issue body (falling back to the title when the issue body is
    null or empty, so ``NormalizedTask.body`` is never the empty string)
    followed by each comment, each introduced by a delimiter line naming
    the comment's author and id so a role reading the task can tell the
    original request from a follow-up. Every value here is issue-sourced
    text carried as data -- no key or value in the built task is derived
    *from* the issue's content, only from its identity (owner/repo/number)
    and structure (labels/comment count).
    """
    raw = locator.strip().strip('"')
    if not _POSITIVE_INTEGER_LOCATOR.fullmatch(raw):
        raise UnresolvableSourceError(
            f"github: locator is not a positive integer: {locator!r}"
        )
    issue_number = int(raw)

    if repository is None:
        raise UnresolvableSourceError(
            "github: no repository configuration is available "
            "(github_owner/github_repo are not set)"
        )
    owner = repository.get("github_owner")
    repo = repository.get("github_repo")
    missing = [
        name
        for name, value in (("github_owner", owner), ("github_repo", repo))
        if not value
    ]
    if missing:
        raise UnresolvableSourceError(
            f"github: repository config is missing: {', '.join(missing)}"
        )
    assert isinstance(owner, str)  # narrowed by the `missing` check above
    assert isinstance(repo, str)

    try:
        client = GitHubClient.from_settings(get_settings())
        issue = client.fetch_issue(owner, repo, issue_number=issue_number)
    except GitHubError as exc:
        raise UnresolvableSourceError(f"github: {exc}") from exc

    title = _strip_heading_marker(issue.title)[:_TITLE_MAX_LEN]
    base_body = issue.body if issue.body else issue.title
    segments = [base_body]
    for comment in issue.comments:
        segments.append(
            f"\n\n--- comment by {comment.author} (id={comment.id}) ---\n{comment.body}"
        )
    body = "".join(segments)

    source_ref = f"{owner}/{repo}#{issue_number}"
    metadata: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
        "labels": issue.labels,
        "comment_count": len(issue.comments),
    }
    return NormalizedTask(
        source_kind="github",
        source_ref=source_ref,
        title=title,
        body=body,
        metadata=metadata,
    )


_LOADERS: dict[SourceKind, _Loader] = {
    SourceKind.TEXT: _load_text,
    SourceKind.SPEC: _load_spec,
    SourceKind.GITHUB: _load_github,
}


def load(
    kind: SourceKind, locator: str, *, repository: Mapping[str, Any] | None = None
) -> NormalizedTask:
    """Dispatch to the loader registered for ``kind`` and return its task."""
    return _LOADERS[kind](locator, repository=repository)
