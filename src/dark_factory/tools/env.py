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

import os
import tempfile
from pathlib import Path

from pydantic import SecretStr

__all__ = ["WORKER_ENV_ALLOWLIST", "build_worker_env"]

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
    temp ``XDG_*`` entries rooted at ``xdg_root`` (or a ``TMPDIR``-derived
    per-role path when ``xdg_root`` is omitted), so a worker's own
    config/cache writes land somewhere disposable rather than in the
    operator's home directory. Finally, when **both** ``env_var_name`` and
    ``value`` are supplied, exactly one additional key is set to
    ``value.get_secret_value()`` -- a named-but-unsupplied credential
    (either argument left ``None``) adds nothing at all.

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

    root = (
        xdg_root
        if xdg_root is not None
        else Path(tempfile.gettempdir()) / "dark-factory-worker-xdg" / role
    )
    env["XDG_CONFIG_HOME"] = str(root / "config")
    env["XDG_CACHE_HOME"] = str(root / "cache")
    env["XDG_DATA_HOME"] = str(root / "data")
    env["XDG_STATE_HOME"] = str(root / "state")

    if env_var_name is not None and value is not None:
        env[env_var_name] = value.get_secret_value()

    return env
