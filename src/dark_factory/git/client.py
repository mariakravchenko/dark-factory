"""The one subprocess wrapper for the ``git`` binary (GIT-02, T-05-01, T-05-04,
T-05-10, T-05-11).

Mirrors ``tests/support/subprocess_runner.py``'s discipline: ``git`` is
invoked by name, resolved from ``PATH`` -- every call here is
``subprocess.run(["git", *args], ...)``, an explicit argument list, never an
interpolated command string and never invoked through a shell. No
repo-controlled value ever selects the executable (T-05-01).

The child environment is built by comprehension over an explicit allowlist;
the parent process environment is never duplicated wholesale (T-05-04) --
this is precisely how a database URL or a GitHub token would reach a
subprocess that has no business seeing one.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from dark_factory.git import GitCommandError

__all__ = ["GIT_ENV_ALLOWLIST", "GIT_IDENTITY_ENV", "git_env", "run_git"]

# The names git genuinely needs to find its binary, its cert bundle and a
# temp directory -- and nothing else. In particular: no DATABASE_URL, no
# DATABASE_URL_DIRECT, no GITHUB_TOKEN, no name ending in _API_KEY.
GIT_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "SYSTEMROOT",
)

# Pinned so every commit Dark Factory writes is deterministic and
# attributable regardless of the operator's personal git config (T-05-11):
# GIT_CONFIG_NOSYSTEM keeps a system-wide config from overriding the pinned
# identity; GIT_TERMINAL_PROMPT=0 guarantees a git subprocess can never block
# waiting on a terminal (T-05-10).
GIT_IDENTITY_ENV: dict[str, str] = {
    "GIT_AUTHOR_NAME": "Dark Factory",
    "GIT_COMMITTER_NAME": "Dark Factory",
    "GIT_AUTHOR_EMAIL": "dark-factory@invalid",
    "GIT_COMMITTER_EMAIL": "dark-factory@invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def git_env() -> dict[str, str]:
    """The child environment for a ``git`` subprocess: the allowlisted parent
    values plus the pinned identity variables.

    Built by comprehension over :data:`GIT_ENV_ALLOWLIST` -- the parent
    process environment is never duplicated wholesale (T-05-04), so a
    database URL or a GitHub token set in the parent process never reaches
    this mapping even when both are present.
    """
    return {
        name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ
    } | GIT_IDENTITY_ENV


def run_git(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in ``cwd`` with the explicit env allowlist.

    ``git`` is invoked by name from ``PATH`` -- ``["git", *args]``, never a
    shell string (T-05-01). Every invocation carries an explicit ``timeout``
    so a git subprocess can neither block on a credential prompt (also
    guaranteed by ``GIT_TERMINAL_PROMPT=0``) nor hang indefinitely (T-05-10);
    exceeding it surfaces as ``subprocess.TimeoutExpired``.

    Returns the completed process when ``check`` is false, so a caller can
    inspect an expected non-zero exit (``git symbolic-ref -q HEAD`` exiting
    1, ``git show-ref --verify --quiet`` exiting 1) without a raise. Raises
    :class:`~dark_factory.git.GitCommandError` when ``check`` is true and the
    exit code is non-zero.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=git_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitCommandError(tuple(args), result.returncode, result.stderr, cwd=cwd)
    return result
