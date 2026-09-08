"""SC1 end-to-end proof: a text task typed at the CLI becomes a durable run in
PostgreSQL, is driven through the BA role by ``FakeWorker`` with no external
call, and reaches ``COMPLETED`` across two committed steps.

The CLI is invoked as a real subprocess (``python -m dark_factory``) against the
provisioned PostgreSQL 17. The child's ``DATABASE_URL`` / ``DATABASE_URL_DIRECT``
are taken from the ``pg_url`` fixture so no connection string is hardcoded and
none is ever printed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = pytest.mark.integration

# CJK ideographs + an emoji + a base letter followed by U+0301 COMBINING ACUTE
# ACCENT (so "café" is five code points, not the precomposed "café").
_MULTIBYTE_BODY = "日本語 \U0001f389 café"


def _run_cli(source: str, pg_url: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)  # want the default COMPLETED script
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", "run", source],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
        check=False,
    )


def test_run_text_task_reaches_completed_end_to_end(
    pg_url: str, engine: Engine
) -> None:
    proc = _run_cli("text:add a health endpoint", pg_url)

    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}"

    lines = proc.stdout.splitlines()
    run_id = UUID(lines[0].strip())  # D-01: bare run id on line 1

    assert "CREATED → BA" in proc.stdout
    assert "BA → COMPLETED" in proc.stdout
    assert proc.stdout.index("CREATED → BA") < proc.stdout.index("BA → COMPLETED")

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        assert run.current_role == "BA"

        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        (execution,) = execs
        assert execution.role == "BA"
        assert execution.worker == "fake"
        assert execution.attempt == 1
        assert execution.status == "COMPLETED"

        event_types = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert event_types == [
            "RUN_CREATED",
            "ROLE_STARTED",
            "ROLE_COMPLETED",
            "RUN_COMPLETED",
        ]


def test_multibyte_task_body_round_trips_through_normalized_task(
    pg_url: str, engine: Engine
) -> None:
    proc = _run_cli("text:" + _MULTIBYTE_BODY, pg_url)

    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}"
    run_id = UUID(proc.stdout.splitlines()[0].strip())

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.normalized_task["body"] == _MULTIBYTE_BODY
