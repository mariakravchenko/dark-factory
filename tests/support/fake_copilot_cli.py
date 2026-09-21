"""A fake ``copilot`` executable for testing :class:`CopilotWorker` with no
live GitHub Copilot CLI and no live Copilot credential (08-RESEARCH.md D-02
"CLI access & spike approach").

Mirrors ``tests/support/fake_claude_cli.py`` module-for-module:
:func:`write_fake_copilot` writes a small, self-contained Python script named
``copilot`` into a directory and marks it executable. Prepending that
directory to ``PATH`` (via :func:`fake_copilot_env`) is enough for
:func:`~dark_factory.tools.env.build_worker_env` to resolve the bare command
name ``"copilot"`` to the fake script -- ``build_worker_env`` copies ``PATH``
from the parent process verbatim, and ``subprocess.Popen`` resolves a bare
command name against the ``PATH`` it is given.

Every configuration value (``stdout_payload``, ``exit_code``,
``sleep_seconds``, ``stderr_text``, the log paths) is baked into the
generated script source as a Python literal via ``repr()``. It is
deliberately never read back from the child's own environment at run time,
for the same reason ``fake_claude_cli.py`` does not: a
``DARK_FACTORY_FAKE_*``-style env var would be stripped before the child
process ever saw it, because :func:`~dark_factory.tools.env.build_worker_env`
copies only ``WORKER_ENV_ALLOWLIST`` names.
"""

from __future__ import annotations

import contextlib
import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

__all__ = ["fake_copilot_env", "write_fake_copilot"]

_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def write_fake_copilot(
    directory: Path,
    *,
    stdout_payload: str | bytes,
    exit_code: int = 0,
    sleep_seconds: float = 0.0,
    stderr_text: str = "",
    argv_log: Path | None = None,
    env_log: Path | None = None,
) -> Path:
    """Write an executable ``copilot`` script to ``directory``; return
    ``directory`` (the caller prepends it to ``PATH`` via
    :func:`fake_copilot_env`).

    On invocation the generated script, in order:

    1. writes ``json.dumps(sys.argv)`` to ``argv_log`` when given;
    2. writes ``json.dumps(dict(os.environ))`` to ``env_log`` when given;
    3. sleeps for ``sleep_seconds`` when non-zero;
    4. writes ``stderr_text`` to stderr and flushes;
    5. writes ``stdout_payload`` to stdout (as raw bytes when
       ``stdout_payload`` is ``bytes``) and flushes;
    6. exits with ``exit_code``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / "copilot"
    script = f"""#!/usr/bin/env python3
import json
import os
import sys
import time

argv_log = {(str(argv_log) if argv_log is not None else None)!r}
env_log = {(str(env_log) if env_log is not None else None)!r}
sleep_seconds = {sleep_seconds!r}
stderr_text = {stderr_text!r}
stdout_payload = {stdout_payload!r}
exit_code = {exit_code!r}

if argv_log:
    with open(argv_log, "w", encoding="utf-8") as fh:
        json.dump(sys.argv, fh)
if env_log:
    with open(env_log, "w", encoding="utf-8") as fh:
        json.dump(dict(os.environ), fh)
if sleep_seconds:
    time.sleep(sleep_seconds)
if stderr_text:
    sys.stderr.write(stderr_text)
    sys.stderr.flush()
if isinstance(stdout_payload, bytes):
    sys.stdout.buffer.write(stdout_payload)
else:
    sys.stdout.write(stdout_payload)
sys.stdout.flush()
sys.exit(exit_code)
"""
    script_path.write_text(script, encoding="utf-8")
    mode = script_path.stat().st_mode
    script_path.chmod(mode | _EXEC_BITS)
    return directory


@contextlib.contextmanager
def fake_copilot_env(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    *,
    copilot_github_token: str = "github_pat_fake0000000000000000000000000000",
    database_url: str = (
        "postgresql+psycopg://fakeuser:fakepass@fake-host.example/darkfactory"
    ),
    database_url_direct: str = (
        "postgresql+psycopg://fakeuser:fakepass@fake-direct.example/darkfactory"
    ),
) -> Iterator[None]:
    """Prepend ``directory`` to ``PATH``, set obviously-fake
    ``COPILOT_GITHUB_TOKEN`` / ``DATABASE_URL`` / ``DATABASE_URL_DIRECT``
    values, and clear the ``get_settings()`` cache both before yielding and
    on teardown -- mirrors ``tests/support/fake_claude_cli.py::
    fake_claude_env``.
    """
    from dark_factory.config.settings import get_settings

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{existing_path}")
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", copilot_github_token)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL_DIRECT", database_url_direct)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
