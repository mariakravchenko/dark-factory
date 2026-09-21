"""The end-to-end CR-01 proof: a role running on a real external adapter
that overwrites another role's artifact is reverted and fails -- on both
runtimes this phase added (plan 08-05, Tasks 1-2).

Drives the shipped ``.dark-factory/`` configuration through the real CLI
subprocess (``dark_factory run ...``), the same idiom
``tests/integration/test_role_reassignment_sc2.py`` and
``tests/integration/test_real_pipeline_zero_config.py`` already use, with
one adapter's fake executable given a ``run_root_writes`` entry that
overwrites a path inside a *different* role's artifact subtree.

This symmetry is the point: CR-01 was a per-adapter gap (Hermes had no
native narrowing mechanism at all; Copilot's native narrowing collapsed
onto the same unscoped tool names as the repository capabilities), and the
fix (``enforce_artifact_scope``, orchestrator-side and worker-agnostic) is
deliberately not per-adapter. A test that only covered one runtime would
leave the other's regression undetected -- both negative cases below route
through :func:`_drive_shipped_config`, the one shared harness, so the two
proofs are visibly the same proof on two runtimes rather than two
independently written tests that might diverge.

This module needs a reachable PostgreSQL 17, the same as
``test_real_pipeline_zero_config.py``, whose shipped-config copy helper and
CLI-subprocess runner it reuses rather than re-deriving.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.git.worktree import working_branch_name, worktree_path
from dark_factory.persistence.models import ArtifactReference, RoleExecution, Run
from tests.integration.test_real_pipeline_zero_config import (
    _copy_shipped_config_into,
    _run_cli_against_real_repo,
)
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_copilot_cli import write_fake_copilot
from tests.support.fake_hermes_cli import write_fake_hermes
from tests.support.git_repo import make_git_repo, read_committed

pytestmark = pytest.mark.integration


def _install_fakes(
    fake_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    hermes_run_root_writes: dict[str, str] | None = None,
    copilot_run_root_writes: dict[str, str] | None = None,
) -> None:
    """Install all three fake CLI executables with ``declared_outputs=True``
    and both worker credentials -- identical in shape to
    ``test_role_reassignment_sc2._install_external_runtime_fakes``, with the
    addition of an optional ``run_root_writes`` entry per externally-run
    adapter so a caller can make that adapter's real subprocess write into
    another role's artifact subtree."""
    write_fake_claude(
        fake_dir,
        stdout_payload=json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "session_id": "sess-08-05-development",
                "result": "implementation complete",
            }
        ),
        declared_outputs=True,
    )
    write_fake_copilot(
        fake_dir,
        stdout_payload="architecture design complete",
        declared_outputs=True,
        run_root_writes=copilot_run_root_writes,
    )
    write_fake_hermes(
        fake_dir,
        stdout_payload="QA verification complete",
        declared_outputs=True,
        run_root_writes=hermes_run_root_writes,
    )

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{fake_dir}{os.pathsep}{existing_path}")
    monkeypatch.setenv(
        "COPILOT_GITHUB_TOKEN", "github_pat_fake0000000000000000000000000000"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake0000000000000000000000000000")


def _drive_shipped_config(
    pg_url: str,
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    label: str,
    hermes_run_root_writes: dict[str, str] | None = None,
    copilot_run_root_writes: dict[str, str] | None = None,
) -> dict[str, object]:
    """Copy the shipped configuration into a throwaway repository, install
    all three fake CLIs (optionally tampering via one externally-run
    adapter's ``run_root_writes``), drive the run through the real CLI
    subprocess, and collect per-role status/error, the completed-role list
    and per-role artifact-type sets -- the one harness both the Hermes and
    Copilot negative proofs, and the positive control, all call with
    different tampering arguments (08-05 Task 2). Callers are responsible
    for cleaning up the returned run directory via :func:`_cleanup_run_dir`.
    """
    config_root = _copy_shipped_config_into(make_git_repo(tmp_path / f"{label}-repo"))
    fake_dir = tmp_path / f"{label}-fakebin"
    _install_fakes(
        fake_dir,
        monkeypatch,
        hermes_run_root_writes=hermes_run_root_writes,
        copilot_run_root_writes=copilot_run_root_writes,
    )

    proc = _run_cli_against_real_repo("text:add a health endpoint", pg_url, config_root)
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    run_id = UUID(proc.stdout.splitlines()[0].strip())

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        executions = list(
            session.scalars(
                select(RoleExecution)
                .where(RoleExecution.run_id == run_id)
                .order_by(RoleExecution.created_at)
            )
        )
        status_by_role = {e.role: e.status for e in executions}
        error_by_role = {e.role: e.error for e in executions}
        completed_roles = [e.role for e in executions if e.status == "COMPLETED"]
        artifact_types_by_role: dict[str, set[str]] = {}
        for execution in executions:
            if execution.status != "COMPLETED":
                continue
            types = set(
                session.scalars(
                    select(ArtifactReference.type).where(
                        ArtifactReference.role_execution_id == execution.id
                    )
                )
            )
            artifact_types_by_role[execution.role] = types
        status_value = run.status.value

    return {
        "run_id": run_id,
        "config_root": config_root,
        "status": status_value,
        "status_by_role": status_by_role,
        "error_by_role": error_by_role,
        "completed_roles": completed_roles,
        "artifact_types_by_role": artifact_types_by_role,
    }


def _cleanup_run_dir(config_root: Path, run_id: UUID) -> None:
    run_dir = (
        worktree_path(config_root, run_id) / ".dark-factory" / "runs" / str(run_id)
    )
    if run_dir.is_dir():
        shutil.rmtree(run_dir, ignore_errors=True)


def test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails(
    pg_url: str, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-01 end to end on Hermes: the shipped ``QA`` role (``worker:
    hermes``) overwriting ``ARCHITECTURE``'s committed ``design.md`` leaves
    the run not ``COMPLETED``, ``QA``'s execution ``FAILED`` naming the
    violating path, and ``design.md`` restored to what ``ARCHITECTURE``
    committed."""
    result = _drive_shipped_config(
        pg_url,
        engine,
        tmp_path,
        monkeypatch,
        label="hermes-tamper",
        hermes_run_root_writes={
            "artifacts/ARCHITECTURE/design.md": "QA overwrote this\n"
        },
    )
    run_id = result["run_id"]
    config_root = result["config_root"]
    assert isinstance(run_id, UUID)
    assert isinstance(config_root, Path)

    try:
        assert result["status"] != "COMPLETED"
        assert result["status_by_role"]["QA"] == "FAILED"
        error_blob = json.dumps(result["error_by_role"]["QA"])
        assert "artifacts/ARCHITECTURE/design.md" in error_blob

        working_branch = working_branch_name(run_id)
        committed = read_committed(
            config_root,
            working_branch,
            f".dark-factory/runs/{run_id}/artifacts/ARCHITECTURE/design.md",
        )
        restored = (
            worktree_path(config_root, run_id)
            / ".dark-factory"
            / "runs"
            / str(run_id)
            / "artifacts"
            / "ARCHITECTURE"
            / "design.md"
        )
        assert restored.exists()
        assert restored.read_text("utf-8") == committed
    finally:
        _cleanup_run_dir(config_root, run_id)
