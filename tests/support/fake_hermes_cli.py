"""A fake ``hermes`` executable for testing :class:`HermesWorker` with no
live Hermes Agent CLI and no live credential (08-RESEARCH.md D-02 "CLI
access & spike approach").

:func:`write_fake_hermes` is a thin wrapper over
:func:`tests.support.fake_cli.write_fake_cli` (08-04 Task 2) -- the shared
generator every fake-CLI module now delegates to, forwarding every keyword
including ``declared_outputs``. Prepending the returned directory to ``PATH``
(via :func:`fake_hermes_env`) is enough for
:func:`~dark_factory.tools.env.build_worker_env` to resolve the bare command
name ``"hermes"`` to the fake script -- ``build_worker_env`` copies ``PATH``
from the parent process verbatim, and ``subprocess.Popen`` resolves a bare
command name against the ``PATH`` it is given.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from tests.support.fake_cli import write_fake_cli

__all__ = ["fake_hermes_env", "write_fake_hermes"]


def write_fake_hermes(
    directory: Path,
    *,
    stdout_payload: str | bytes,
    exit_code: int = 0,
    sleep_seconds: float = 0.0,
    stderr_text: str = "",
    argv_log: Path | None = None,
    env_log: Path | None = None,
    declared_outputs: bool = False,
    run_root_writes: Mapping[str, str] | None = None,
) -> Path:
    """Write an executable ``hermes`` script to ``directory``; return
    ``directory`` (the caller prepends it to ``PATH`` via
    :func:`fake_hermes_env`). See :func:`~tests.support.fake_cli.write_fake_cli`
    for the generated script's exact behaviour.
    """
    return write_fake_cli(
        directory,
        "hermes",
        stdout_payload=stdout_payload,
        exit_code=exit_code,
        sleep_seconds=sleep_seconds,
        stderr_text=stderr_text,
        argv_log=argv_log,
        env_log=env_log,
        declared_outputs=declared_outputs,
        run_root_writes=run_root_writes,
    )


@contextlib.contextmanager
def fake_hermes_env(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    *,
    anthropic_api_key: str = "sk-ant-fake00000000000000000000000000000000",
    database_url: str = (
        "postgresql+psycopg://fakeuser:fakepass@fake-host.example/darkfactory"
    ),
    database_url_direct: str = (
        "postgresql+psycopg://fakeuser:fakepass@fake-direct.example/darkfactory"
    ),
) -> Iterator[None]:
    """Prepend ``directory`` to ``PATH``, set obviously-fake
    ``ANTHROPIC_API_KEY`` -- not a Hermes-specific name (08-RESEARCH.md
    Finding 1: Hermes reuses the same multi-provider credential Claude Code
    does) -- plus ``DATABASE_URL`` / ``DATABASE_URL_DIRECT``, and clear the
    ``get_settings()`` cache both before yielding and on teardown -- mirrors
    ``tests/support/fake_copilot_cli.py::fake_copilot_env``.
    """
    from dark_factory.config.settings import get_settings

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{existing_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_api_key)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL_DIRECT", database_url_direct)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
