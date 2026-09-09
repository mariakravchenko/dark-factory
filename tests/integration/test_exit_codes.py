"""The D-05 exit-code contract, exercised across a real process boundary.

``0`` for COMPLETED, ``1`` for a persisted FAILED, ``2`` for a bad invocation
where nothing was persisted. The FAILED arm is driven across the boundary by
``DARK_FACTORY_FAKE_SCRIPT`` -- an in-process registry override does not reach a
child process, which is exactly why ``FakeWorker`` reads that variable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def _cli(
    args: list[str], pg_url: str, *, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
        check=False,
    )


def test_exit_0_on_the_happy_path(pg_url: str) -> None:
    proc = _cli(["run", "text:ship a health endpoint"], pg_url)
    assert proc.returncode == 0, proc.stdout
    UUID(proc.stdout.splitlines()[0].strip())  # run id still on line 1


def test_exit_1_when_the_worker_script_supplies_a_failed_result(pg_url: str) -> None:
    script = json.dumps(
        [{"status": "FAILED", "summary": "worker gave up", "error": "boom"}]
    )
    proc = _cli(
        ["run", "text:this one fails"],
        pg_url,
        extra_env={"DARK_FACTORY_FAKE_SCRIPT": script},
    )
    assert proc.returncode == 1, proc.stdout
    lines = proc.stdout.splitlines()
    UUID(lines[0].strip())  # a run was created -> id on line 1
    assert "BA → FAILED" in proc.stdout


def test_exit_2_on_an_unrecognised_prefix_with_nothing_on_stdout(pg_url: str) -> None:
    proc = _cli(["run", "notaprefix:hello"], pg_url)
    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert "notaprefix:hello" in proc.stderr


def test_orchestration_error_exits_2_with_a_diagnostic_not_a_traceback(
    pg_url: str,
) -> None:
    """An orchestration error -- the run could not be advanced and nothing new
    was persisted -- must surface as exit 2 with a one-line stderr diagnostic,
    never as a Typer traceback with exit 1 (which the D-05 contract reserves for
    a persisted FAILED).

    An empty fake script drives it: ``FakeWorker`` honours ``[]`` as a real
    (exhausted) script, so the first ``execute()`` raises ``ScriptExhaustedError``
    -- one of the ``_ORCHESTRATION_ERRORS``. (A scripted ``NEEDS_INPUT`` result
    is no longer an orchestration error since Phase 2 -- it is a clean pause that
    exits 0.)"""
    proc = _cli(
        ["run", "text:worker has nothing to say"],
        pg_url,
        extra_env={"DARK_FACTORY_FAKE_SCRIPT": json.dumps([])},
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    UUID(proc.stdout.splitlines()[0].strip())  # the run was still created
    assert "Traceback" not in proc.stderr
    assert "could not be advanced" in proc.stderr
