"""SC3 / CFG-05: a run paused on a ``NEEDS_INPUT`` script keeps executing the
role order from its **creation snapshot** after ``.dark-factory.yaml`` is
reordered mid-pause, and the resume path re-reads no config file.

The first process runs ``dark-factory run`` in a throwaway ``.dark-factory/``
tree whose ``workflow.roles`` is ``[BA, QA]`` and pauses ``WAITING_HUMAN`` on the
first role. The tree's ``.dark-factory.yaml`` is then rewritten to ``[QA, BA]``.
A brand-new process runs ``dark-factory resume <id> --answer`` -- and the
resumed run's transition lines continue ``BA -> QA -> COMPLETED`` (the snapshot
order), not the single ``BA -> COMPLETED`` the edited file would produce. The run
id is unchanged and no second ``runs`` row is created.

A structural guard (reusing the ``test_orchestrator_no_live_config_read`` import
walk) confirms neither the orchestrator nor the answer path can reach
``dark_factory.config.loader`` at all.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn
from tests.unit.test_orchestrator_no_live_config_read import (
    _loader_hits,
    _transitive_closure,
)

pytestmark = pytest.mark.integration

_QUESTION = "Which cluster should the health endpoint report on?"
_SESSION_ID = "fake-snapshot-survives-001"

_PAUSE_SCRIPT: list[dict[str, Any]] = [
    {
        "status": "NEEDS_INPUT",
        "questions": [_QUESTION],
        "worker_session_id": _SESSION_ID,
    }
]
_RESUME_SCRIPT: list[dict[str, Any]] = [
    {"status": "COMPLETED", "summary": "resumed BA", "worker_session_id": _SESSION_ID},
    {"status": "COMPLETED", "summary": "QA done", "worker_session_id": _SESSION_ID},
]


def _transition_lines(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if " → " in line]


def _rewrite_roles(root: Path, roles: list[str]) -> None:
    (root / ".dark-factory.yaml").write_text(
        "version: 1\n"
        "repository:\n  base_branch: main\n"
        f"workflow:\n  roles: [{', '.join(roles)}]\n"
        "roles_dir: .dark-factory/roles\n"
        "quality_gate:\n  commands: []\n"
        "retry:\n"
        "  qa_developer_max_iterations: 3\n"
        "  quality_gate_max_iterations: 2\n"
        "publishing:\n  create_pr: true\n",
        encoding="utf-8",
    )


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def test_resume_follows_the_creation_snapshot_not_the_edited_file(
    config_root_factory: Callable[..., Path], pg_url: str, engine: Engine
) -> None:
    root = config_root_factory(roles=("BA", "QA"))

    runs_before = _count_runs(engine)

    paused = spawn(
        ["run", "text:pause then edit config then resume"],
        child_env(pg_url, fake_script=_PAUSE_SCRIPT),
        cwd=root,
    )
    assert paused.returncode == 0, f"{paused.stdout}\n{paused.stderr}"
    assert _transition_lines(paused.stdout) == ["CREATED → BA", "BA → WAITING_HUMAN"]
    run_id = run_id_from_stdout(paused.stdout)

    # the config file is reordered while the run sits WAITING_HUMAN
    _rewrite_roles(root, ["QA", "BA"])

    resumed = spawn(
        ["resume", str(run_id), "--answer", "report on the primary cluster"],
        child_env(pg_url, fake_script=_RESUME_SCRIPT),
        cwd=root,
    )
    assert resumed.returncode == 0, f"{resumed.stdout}\n{resumed.stderr}"

    # snapshot order (BA then QA) wins; the edited [QA, BA] would have produced
    # the single line "BA → COMPLETED" because BA is last there.
    assert _transition_lines(resumed.stdout) == ["BA → QA", "QA → COMPLETED"]
    assert run_id_from_stdout(resumed.stdout) == run_id
    assert _count_runs(engine) == runs_before + 1  # exactly the one run, still one


def test_the_resume_path_can_never_reach_the_config_loader() -> None:
    """Structural half of SC3: the orchestrator and the answer path exclude
    ``dark_factory.config.loader`` from their transitive import closure, so a
    resume physically cannot re-read ``.dark-factory.yaml``."""
    for module in (
        "dark_factory.orchestrator.runner",
        "dark_factory.orchestrator.answers",
    ):
        offenders = _loader_hits(_transitive_closure(module))
        assert not offenders, (
            f"{module} transitively imports the config loader: {offenders}"
        )
