"""The single place Phase 2 spawns the orchestrator as a real operating-system
process.

Two real processes are the point. An in-process simulation shares module state, a
warm engine and an identity map, and can pass while the real thing fails --
single-owner execution is precisely a claim about what happens between two
processes that share only the database.

The child environment is built from an explicit allowlist, never
``os.environ.copy()`` (CLAUDE.md's credential boundary; ``tests/unit/
test_no_environ_copy.py`` guards the source tree). The provisioned PostgreSQL URL
crosses as ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` and nothing else the parent
process holds is passed through.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

__all__ = [
    "REPO_ROOT",
    "child_env",
    "popen",
    "run_id_from_stdout",
    "spawn",
    "wait_for",
]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Only what a child Python needs to import the package, resolve TLS roots and
# talk to PostgreSQL. Deliberately no wildcard copy of the parent environment.
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
    "PYENV_ROOT",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUNBUFFERED",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)


def child_env(
    pg_url: str,
    *,
    crash_after: str | None = None,
    fake_script: object | None = None,
    fake_sleep_ms: int | None = None,
    lease_ttl_seconds: int | None = None,
    lease_heartbeat_seconds: int | None = None,
) -> dict[str, str]:
    """Build a child environment from the allowlist plus the database URL and the
    named test knobs.

    The database URL is set under both the pooled (``DATABASE_URL``) and direct
    (``DATABASE_URL_DIRECT``) variable names. Each optional knob is added only
    when it is not ``None``. The lease knobs go in as the upper-cased ``Settings``
    field names so the child's ``Settings`` picks them up with no extra wiring;
    the fake worker's script goes in as JSON.
    """
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env["DATABASE_URL"] = pg_url
    env["DATABASE_URL_DIRECT"] = pg_url
    if crash_after is not None:
        env["DARK_FACTORY_CRASH_AFTER"] = crash_after
    if fake_script is not None:
        env["DARK_FACTORY_FAKE_SCRIPT"] = json.dumps(fake_script)
    if fake_sleep_ms is not None:
        env["DARK_FACTORY_FAKE_SLEEP_MS"] = str(fake_sleep_ms)
    if lease_ttl_seconds is not None:
        env["LEASE_TTL_SECONDS"] = str(lease_ttl_seconds)
    if lease_heartbeat_seconds is not None:
        env["LEASE_HEARTBEAT_SECONDS"] = str(lease_heartbeat_seconds)
    return env


def spawn(
    args: list[str], env: dict[str, str], *, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    """The blocking form: run ``python -m dark_factory <args>`` at the repo root,
    capture output, and wait for it to exit."""
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=timeout,
        check=False,
    )


def popen(args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    """The non-blocking form: start the same argument vector with piped output and
    return the :class:`subprocess.Popen` for the caller to manage.

    The race and heartbeat proofs need two children genuinely overlapping in
    time, which a blocking helper cannot express.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "dark_factory", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def run_id_from_stdout(text: str) -> UUID:
    """Parse the bare run id off stdout line 1 (D-01) and return it as a ``UUID``.

    Raise with the full captured output when the first line is not a run id, so a
    caller never silently proceeds on a crash banner.
    """
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    try:
        return UUID(first)
    except ValueError as exc:
        raise ValueError(f"expected a run id on stdout line 1, got:\n{text!r}") from exc


def wait_for(
    predicate: Callable[[], object],
    *,
    timeout: float,
    interval: float = 0.05,
) -> None:
    """Poll ``predicate`` until it returns truthy or ``timeout`` seconds elapse.

    Raise ``TimeoutError`` naming what was being waited for if it never becomes
    truthy. The race proofs need to wait until the first child is genuinely
    mid-step before starting the second; a fixed sleep would be flaky in both
    directions.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    label = getattr(predicate, "__name__", repr(predicate))
    raise TimeoutError(f"waited {timeout}s for {label} to become truthy")
