"""SC1 / ORCH-02 / ORCH-03: ``dark-factory run`` resolves its pipeline from the
cwd's ``.dark-factory.yaml`` and executes exactly that ordered role sequence.

Every case drives a *real* ``python -m dark_factory run`` subprocess whose
working directory is a throwaway ``.dark-factory/`` tree (the ``config_root`` /
``config_root_factory`` builders from 03-02). The config is resolved from the
process's cwd at run creation, persisted into ``runs.workflow``, and is the only
thing that decides the transition sequence.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    run_id_from_stdout,
    spawn,
)

pytestmark = pytest.mark.integration

_COMPLETED: dict[str, Any] = {
    "status": "COMPLETED",
    "summary": "role complete",
    "worker_session_id": "fake-sc1",
}
_GUARDED_DIRS = ("src/dark_factory/orchestrator", "src/dark_factory/workflows")


def _transition_lines(stdout: str) -> list[str]:
    """The ordered ``PREVIOUS → NEXT`` lines the CLI emits, one per state change."""
    return [line.strip() for line in stdout.splitlines() if " → " in line]


def _workflow_snapshot(engine: Engine, run_id: object) -> dict[str, object]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return dict(run.workflow)


def _rewrite_roles(root: Path, roles: list[str]) -> None:
    """Rewrite only ``workflow.roles`` in an existing ``.dark-factory.yaml`` tree,
    keeping every other key (and every role YAML / instruction file) untouched."""
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


def _run_roles(root: Path, pg_url: str, roles: list[str], source: str) -> list[str]:
    """Rewrite ``workflow.roles``, drive one fresh ``dark-factory run`` subprocess
    against ``root``, and return its ordered transition lines. The fake worker is
    scripted with one COMPLETED per role so every role finishes."""
    _rewrite_roles(root, roles)
    proc = spawn(
        ["run", source],
        child_env(pg_url, fake_script=[_COMPLETED] * len(roles)),
        cwd=root,
    )
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    run_id_from_stdout(proc.stdout)  # a run id really landed on stdout line 1
    return _transition_lines(proc.stdout)


def _guarded_tree_digest() -> str:
    h = hashlib.sha256()
    for rel in _GUARDED_DIRS:
        for path in sorted((REPO_ROOT / rel).rglob("*.py")):
            h.update(path.relative_to(REPO_ROOT).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def _guarded_worktree_diff() -> str:
    """``git diff --stat`` over the two guarded dirs, or a sentinel when ``git``
    is unavailable so the caller falls back to the digest check."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", "--", *_GUARDED_DIRS],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "\x00git-unavailable"
    return proc.stdout if proc.returncode == 0 else "\x00git-unavailable"


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


# --------------------------------------------------------------------------- #
# Task 2 -- SC1: reordering / shortening workflow.roles changes the executed
# transition sequence, with no source file edited to make it happen
# --------------------------------------------------------------------------- #


def test_reorder_and_shorten_workflow_roles_changes_the_executed_pipeline(
    config_root_factory: Callable[..., Path], pg_url: str
) -> None:
    root = config_root_factory(roles=("BA", "QA"))

    diff_before = _guarded_worktree_diff()
    digest_before = _guarded_tree_digest()

    two_role = _run_roles(root, pg_url, ["BA", "QA"], "text:sc1-two")
    assert two_role == ["CREATED → BA", "BA → QA", "QA → COMPLETED"]

    reordered = _run_roles(root, pg_url, ["QA", "BA"], "text:sc1-reordered")
    assert reordered == ["CREATED → QA", "QA → BA", "BA → COMPLETED"]
    assert reordered != two_role  # the executed sequence genuinely changed

    shortened = _run_roles(root, pg_url, ["BA"], "text:sc1-short")
    assert shortened == ["CREATED → BA", "BA → COMPLETED"]

    diff_after = _guarded_worktree_diff()
    digest_after = _guarded_tree_digest()

    if diff_before == "\x00git-unavailable" or diff_after == "\x00git-unavailable":
        assert digest_after == digest_before, (
            "a *.py file under orchestrator/ or workflows/ changed across the runs"
        )
    else:
        assert diff_before == diff_after == "", (
            "git diff --stat over orchestrator/ + workflows/ was non-empty: the "
            f"pipeline change touched source\nbefore={diff_before!r}\nafter={diff_after!r}"
        )
