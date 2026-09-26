"""The ``dark_factory.github`` package -- the ONLY place in ``dark_factory``
that constructs a GitHub REST SDK client (D-03).

Mirrors ``dark_factory.git``'s structure and voice: nothing outside
``dark_factory/github/client.py`` imports the third-party GitHub SDK
directly (verified structurally: a grep for its package name across
``src/dark_factory`` returns exactly that one path), so a future GitHub
SDK swap stays a one-file change.

Error hierarchy:

* :class:`GitHubError` -- the base class for every failure this package
  raises.
* :class:`GitHubApiError` -- a GitHub REST call failed; carries
  ``status_code`` (the HTTP status, or ``None`` when the failure never
  reached a response) and ``endpoint`` (a short label naming the failed
  operation) as attributes alongside an already-redacted message -- every
  message here has passed through
  :func:`~dark_factory.events.redaction.redact` before it is raised, the
  same defense-in-depth :func:`~dark_factory.git.diff.push_working_branch`
  already applies, because a GitHub error response can echo request
  headers.
* :class:`MissingGitHubCredentialError` -- raised by
  :meth:`~dark_factory.github.client.GitHubClient.from_settings` when
  ``Settings.github_token`` is ``None`` at the point of use, mirroring
  ``anthropic_api_key``'s absence-as-typed-error precedent documented in
  ``config/settings.py``.

Declaring the whole hierarchy in one place keeps the package's error
surface legible to a caller from the start. The client module is imported
only after these are declared, so its own ``from dark_factory.github import
<ErrorClass>`` succeeds against this module's already-populated namespace
(mirrors ``dark_factory/git/__init__.py``'s import ordering) -- avoids a
circular-import problem, since the client module is the one that raises
these errors.
"""

from __future__ import annotations

__all__ = [
    "GitHubApiError",
    "GitHubClient",
    "GitHubComment",
    "GitHubError",
    "GitHubIssue",
    "GitHubPullRequest",
    "MissingGitHubCredentialError",
]


class GitHubError(RuntimeError):
    """Base class for every ``dark_factory.github`` failure."""


class GitHubApiError(GitHubError):
    """A GitHub REST call failed.

    Carries ``status_code`` and ``endpoint`` as attributes, in addition to
    a human-readable message that has already passed through
    :func:`~dark_factory.events.redaction.redact`.
    """

    def __init__(self, message: str, *, status_code: int | None, endpoint: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class MissingGitHubCredentialError(GitHubError):
    """Raised when ``Settings.github_token`` is ``None`` at the point of use."""


# Import the submodule after the error hierarchy is declared, so its own
# ``from dark_factory.github import <ErrorClass>`` succeeds against this
# module's already-populated namespace (mirrors dark_factory/git/__init__.py).
from dark_factory.github.client import (
    GitHubClient,
    GitHubComment,
    GitHubIssue,
    GitHubPullRequest,
)
