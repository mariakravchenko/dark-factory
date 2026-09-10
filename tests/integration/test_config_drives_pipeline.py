"""SC1 / ORCH-02 / ORCH-03: ``dark-factory run`` resolves its pipeline from the
cwd's ``.dark-factory.yaml`` and executes exactly that ordered role sequence.

Every case drives a *real* ``python -m dark_factory run`` subprocess whose
working directory is a throwaway ``.dark-factory/`` tree (the ``config_root`` /
``config_root_factory`` builders from 03-02). The config is resolved from the
process's cwd at run creation, persisted into ``runs.workflow``, and is the only
thing that decides the transition sequence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn

pytestmark = pytest.mark.integration


def _transition_lines(stdout: str) -> list[str]:
    """The ordered ``PREVIOUS → NEXT`` lines the CLI emits, one per state change."""
    return [line.strip() for line in stdout.splitlines() if " → " in line]


def _workflow_snapshot(engine: Engine, run_id: object) -> dict[str, object]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return dict(run.workflow)


# --------------------------------------------------------------------------- #
# Task 1 -- the tracer: one real run resolves its pipeline from config and runs
# --------------------------------------------------------------------------- #


def test_run_resolves_pipeline_from_config(
    config_root: Path, pg_url: str, engine: Engine
) -> None:
    proc = spawn(["run", "text:tracer"], child_env(pg_url), cwd=config_root)

    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"

    run_id = run_id_from_stdout(proc.stdout)
    assert _transition_lines(proc.stdout) == ["CREATED → BA", "BA → COMPLETED"]

    snapshot = _workflow_snapshot(engine, run_id)
    roles = snapshot["roles"]
    assert isinstance(roles, list) and roles
    assert roles[0]["name"] == "BA"
    assert roles[0]["worker"] == "fake"
    assert roles[0]["instruction_text"].strip() != ""
