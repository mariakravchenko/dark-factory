"""The credential boundary for a worker-adjacent subprocess (D-09, D-10,
D-11, TOOL-04, SEC-03).

Mirrors ``dark_factory.git.client``'s discipline for a second subprocess
family: the child environment is built by comprehension over an explicit
allowlist starting from an empty mapping, and the parent process
environment is never duplicated wholesale -- not a copy, not a spread, not
an exclusion-filter form (an exclusion list fails open for every credential
nobody thought to name). The concrete consequence, stated plainly:
no DATABASE_URL and no GITHUB_TOKEN set in the parent process ever
reaches a worker subprocess built through this module, even when both are
present in the parent process at the same time.

``tests/integration/test_worker_env_boundary.py`` is the cross-process
proof of that claim (D-10) -- it spawns a real operating-system process
with :func:`build_worker_env`'s output and asserts against what that
process reports about its own environment, because an in-process mapping
check cannot prove what a genuinely separate process actually receives.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

from dark_factory.tools import ToolError

__all__ = [
    "WORKER_ENV_ALLOWLIST",
    "InvalidShellCommandError",
    "ShellResult",
    "build_worker_env",
    "role_worker_root",
    "shell_execute",
]

# The names a worker subprocess genuinely needs to find its binary, resolve
# TLS roots, and use a temp directory -- and nothing else. Derived from
# ``dark_factory.git.client.GIT_ENV_ALLOWLIST`` (A-06-05) plus none of
# ``tests/support/subprocess_runner.py``'s Python-import names -- that
# harness list deliberately includes PYTHONPATH, PYTHONHOME and
# VIRTUAL_ENV so a child Python can import the package under test, and
# none of those belong in a worker's environment.
#
# In particular, and deliberately: no DATABASE_URL, no DATABASE_URL_DIRECT,
# no GITHUB_TOKEN, no name ending in _API_KEY.
WORKER_ENV_ALLOWLIST: tuple[str, ...] = (
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


def role_worker_root(role: str) -> Path:
    """The disposable per-role temp root :func:`build_worker_env` uses for
    its ``XDG_*`` entries when ``xdg_root`` is omitted (Plan 08-02).

    Exists so an adapter that needs to place a *non*-XDG state directory
    (for example Hermes's ``HERMES_HOME``, which does not follow the XDG
    specification) alongside the ``XDG_*`` entries can name the exact same
    disposable root instead of re-deriving the formula and risking drift.
    """
    return Path(tempfile.gettempdir()) / "dark-factory-worker-xdg" / role


def build_worker_env(
    role: str,
    *,
    env_var_name: str | None = None,
    value: SecretStr | None = None,
    xdg_root: Path | None = None,
) -> dict[str, str]:
    """Build the environment for a worker-adjacent subprocess (D-09).

    Additive from an empty mapping over :data:`WORKER_ENV_ALLOWLIST`: only
    allowlisted names *present in the parent process* are copied, one at a
    time -- an allowlisted name absent from the parent is absent from the
    result rather than present as an empty string. Layered on top are four
    temp ``XDG_*`` entries rooted at ``xdg_root`` (or :func:`role_worker_root`
    when ``xdg_root`` is omitted), so a worker's own config/cache writes
    land somewhere disposable rather than in the operator's home directory.
    Finally, when **both** ``env_var_name`` and ``value`` are supplied,
    exactly one additional key is set to ``value.get_secret_value()`` -- a
    named-but-unsupplied credential (either argument left ``None``) adds
    nothing at all.

    ``role`` participates only in the temp XDG path, so two roles never
    share a worker config directory; it is never branched on -- this
    project's no-role-name-branching discipline (CLAUDE.md "Role !=
    Worker").

    This is the only channel available for a credential to reach a worker
    subprocess (SEC-03): the base mapping is never constructed from the
    parent environment as a whole, in any form. See this module's docstring
    and ``tests/integration/test_worker_env_boundary.py`` for the
    cross-process proof that a spawned child sees no infrastructure
    credential it did not ask for.
    """
    env = {
        name: os.environ[name] for name in WORKER_ENV_ALLOWLIST if name in os.environ
    }

    root = xdg_root if xdg_root is not None else role_worker_root(role)
    env["XDG_CONFIG_HOME"] = str(root / "config")
    env["XDG_CACHE_HOME"] = str(root / "cache")
    env["XDG_DATA_HOME"] = str(root / "data")
    env["XDG_STATE_HOME"] = str(root / "state")

    if env_var_name is not None and value is not None:
        env[env_var_name] = value.get_secret_value()

    return env


class InvalidShellCommandError(ToolError, TypeError):
    """Raised by :func:`shell_execute` when ``command`` is a bare string (or
    any non-sequence, or an empty sequence, or a sequence containing a
    non-``str`` element) rather than a non-empty sequence of ``str``.

    A bare string would have to be split or handed to a shell to run at
    all -- accepting one here would silently reopen exactly the
    command-injection surface (threat T-06-02) this capability exists to
    close. Raised before anything is spawned.
    """


class ShellResult(BaseModel):
    """The frozen return shape of a :func:`shell_execute` invocation (D-11).

    ``exit_code`` is ``None`` exactly when ``timed_out`` is true -- a
    command that never finished has no exit code to report. A non-zero
    ``exit_code`` is never raised as an exception: a failing command is a
    *result* a caller inspects, the same distinction
    ``dark_factory.git.client.run_git(check=False)`` already draws.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


def shell_execute(
    *,
    command: Sequence[str],
    cwd: Path,
    role: str,
    timeout: int = 120,
    env_var_name: str | None = None,
    value: SecretStr | None = None,
) -> ShellResult:
    """Run ``command`` inside ``cwd`` with :func:`build_worker_env`'s
    credential-bounded environment and an enforced ``timeout`` (D-11).

    ``command`` crosses to :class:`subprocess.Popen` as an explicit
    argument sequence (``list(command)``), never joined into a string and
    never run through a shell -- a single argument containing a pipe, a
    semicolon or a redirection character reaches the child as inert data,
    not as shell syntax. A bare string, an empty sequence, or a sequence
    with a non-``str`` element raises :class:`InvalidShellCommandError`
    before anything is spawned, rather than being split or interpreted.

    ``cwd`` is always an explicit :class:`~pathlib.Path` supplied by the
    caller; this function never derives a working directory from
    ``Path.cwd()``.

    This function performs no permission decision of its own. The single
    place a role's ``tools:`` entry is checked is
    ``ToolRegistry.invoke()`` (threat T-06-14) -- a second check here would
    make it ambiguous which one is authoritative, so this function must
    never add one; invoking it directly, bypassing the registry, simply
    runs the command.

    The child is spawned with ``start_new_session=True`` so it heads its
    own process group; on :class:`subprocess.TimeoutExpired` the whole
    group is terminated via ``os.killpg(os.getpgid(proc.pid),
    signal.SIGKILL)`` rather than only the immediate child, so a
    timed-out command cannot leave a grandchild running (threat T-06-12).
    The result in that case carries ``timed_out=True``, ``exit_code=None``,
    and whatever partial output had already been captured -- never an
    unbounded wait and never a swallowed timeout.
    """
    if isinstance(command, str) or not isinstance(command, Sequence):
        raise InvalidShellCommandError(
            f"command must be a non-empty sequence of str, not "
            f"{type(command).__name__!r} (never a bare string -- it would "
            f"have to be split or shell-interpreted to run at all)"
        )
    command_list = list(command)
    if not command_list or not all(isinstance(part, str) for part in command_list):
        raise InvalidShellCommandError(
            "command must be a non-empty sequence of str"
        )

    env = build_worker_env(role, env_var_name=env_var_name, value=value)
    proc = subprocess.Popen(
        command_list,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # already exited between the timeout and the kill -> nothing to do
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return ShellResult(
            exit_code=None, stdout=stdout, stderr=stderr, timed_out=True
        )
    return ShellResult(
        exit_code=proc.returncode, stdout=stdout, stderr=stderr, timed_out=False
    )
