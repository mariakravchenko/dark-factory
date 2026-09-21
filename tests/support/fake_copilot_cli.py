"""A fake ``copilot`` executable for testing :class:`CopilotWorker` with no
live GitHub Copilot CLI and no live Copilot credential (08-RESEARCH.md D-02
"CLI access & spike approach").

:func:`write_fake_copilot` is a thin wrapper over
:func:`tests.support.fake_cli.write_fake_cli` (08-04 Task 1) -- the shared
generator every fake-CLI module now delegates to, forwarding every keyword
including ``declared_outputs``. Prepending the returned directory to ``PATH``
(via :func:`fake_copilot_env`) is enough for
:func:`~dark_factory.tools.env.build_worker_env` to resolve the bare command
name ``"copilot"`` to the fake script -- ``build_worker_env`` copies ``PATH``
from the parent process verbatim, and ``subprocess.Popen`` resolves a bare
command name against the ``PATH`` it is given.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.fake_cli import write_fake_cli

__all__ = ["fake_copilot_env", "write_fake_copilot"]


def write_fake_copilot(
    directory: Path,
    *,
    stdout_payload: str | bytes,
    exit_code: int = 0,
    sleep_seconds: float = 0.0,
    stderr_text: str = "",
    argv_log: Path | None = None,
    env_log: Path | None = None,
    declared_outputs: bool = False,
) -> Path:
    """Write an executable ``copilot`` script to ``directory``; return
    ``directory`` (the caller prepends it to ``PATH`` via
    :func:`fake_copilot_env`). See :func:`~tests.support.fake_cli.write_fake_cli`
    for the generated script's exact behaviour.
    """
    return write_fake_cli(
        directory,
        "copilot",
        stdout_payload=stdout_payload,
        exit_code=exit_code,
        sleep_seconds=sleep_seconds,
        stderr_text=stderr_text,
        argv_log=argv_log,
        env_log=env_log,
        declared_outputs=declared_outputs,
    )


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
