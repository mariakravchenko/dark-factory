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
from tests.integration.test_real_pipeline_zero_config import _run_cli_against_real_repo
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_copilot_cli import write_fake_copilot
from tests.support.fake_hermes_cli import write_fake_hermes
from tests.support.git_repo import make_git_repo, read_committed
from tests.support.shipped_config import copy_shipped_config_into

pytestmark = pytest.mark.integration

# D-05 (phase-01 decision, `01-RESEARCH.md:18`; published source:
# `src/dark_factory/cli.py`'s own module docstring) maps a run's terminal status
# to a `dark-factory run` process exit code: `COMPLETED` and `WAITING_HUMAN` map
# to exit 0, every other terminal status maps to a nonzero exit. Hardcoded here
# rather than imported from the CLI's private `_CLEAN_FINALS`, mirroring the
# idiom `tests/integration/test_exit_codes.py` already uses.
_D05_SUCCESS_STATUSES = frozenset({"COMPLETED", "WAITING_HUMAN"})


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
    expected_exit: int,
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

    ``expected_exit`` is the caller's own stated expectation for the
    ``dark-factory run`` subprocess exit code -- keyword-only, with no
    default, so a future caller cannot silently inherit another caller's
    expectation (G-08-2). The two tamper callers below drive their run to
    terminal ``FAILED``, which D-05 maps to exit 1; the untampered positive
    control reaches ``COMPLETED``, which D-05 maps to exit 0. The harness
    cross-checks this expectation against the persisted terminal status it
    reads from the database, so it fails loudly if the CLI's D-05 exit
    mapping and the observed run status ever disagree.
    """
    config_root = copy_shipped_config_into(make_git_repo(tmp_path / f"{label}-repo"))
    fake_dir = tmp_path / f"{label}-fakebin"
    _install_fakes(
        fake_dir,
        monkeypatch,
        hermes_run_root_writes=hermes_run_root_writes,
        copilot_run_root_writes=copilot_run_root_writes,
    )

    proc = _run_cli_against_real_repo("text:add a health endpoint", pg_url, config_root)
    assert proc.returncode == expected_exit, (
        f"exit={proc.returncode} expected={expected_exit}\n{proc.stdout}\n{proc.stderr}"
    )
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
        assert (status_value in _D05_SUCCESS_STATUSES) == (expected_exit == 0), (
            f"the caller's expected exit code ({expected_exit}) and the persisted "
            f"terminal status ({status_value!r}) contradict D-05: exit 0 is "
            f"contracted only for {sorted(_D05_SUCCESS_STATUSES)}; every other "
            "terminal status maps to a nonzero exit"
        )

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
        expected_exit=1,
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
        status_by_role = result["status_by_role"]
        assert isinstance(status_by_role, dict)
        assert status_by_role["QA"] == "FAILED"
        # 10-07 (G-10-1 masked-assertion finding): the exit code alone is
        # not the proof -- an unrelated terminal failure (e.g. gate
        # exhaustion, which is exactly what happened here before 10-07)
        # produces the same exit code 1. The persisted error naming the
        # violating path is what distinguishes this case from any other
        # terminal failure.
        error_by_role = result["error_by_role"]
        assert isinstance(error_by_role, dict)
        error_blob = json.dumps(error_by_role["QA"])
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


def test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails(
    pg_url: str, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-01 end to end on Copilot: the shipped ``ARCHITECTURE`` role
    (``worker: copilot``) overwriting ``BA``'s committed
    ``acceptance_criteria.json`` leaves the run not ``COMPLETED``,
    ``ARCHITECTURE``'s execution ``FAILED``, no later role (``DEVELOPMENT``,
    ``QA``) reaching ``COMPLETED``, and ``BA``'s artifact restored to what
    ``BA`` committed. The control, the failure shape and the revert are the
    same on both runtimes (:func:`_drive_shipped_config` is the identical
    harness the Hermes case above uses), because neither the control nor
    the runner reads a worker name."""
    result = _drive_shipped_config(
        pg_url,
        engine,
        tmp_path,
        monkeypatch,
        label="copilot-tamper",
        expected_exit=1,
        copilot_run_root_writes={
            "artifacts/BA/acceptance_criteria.json": '{"criteria": []}'
        },
    )
    run_id = result["run_id"]
    config_root = result["config_root"]
    assert isinstance(run_id, UUID)
    assert isinstance(config_root, Path)

    try:
        assert result["status"] != "COMPLETED"
        status_by_role = result["status_by_role"]
        assert isinstance(status_by_role, dict)
        assert status_by_role["ARCHITECTURE"] == "FAILED"
        for role in ("DEVELOPMENT", "QA"):
            assert status_by_role.get(role) != "COMPLETED", (
                f"{role} reached COMPLETED after ARCHITECTURE FAILED -- the "
                "pipeline must stop at the failed role rather than "
                "continuing past it"
            )
        # 10-07 (G-10-1 masked-assertion finding): the exit code alone is
        # not the proof -- an unrelated terminal failure (e.g. gate
        # exhaustion, which is exactly what happened here before 10-07)
        # produces the same exit code 1. The persisted error naming the
        # violating path is what distinguishes this case from any other
        # terminal failure -- mirrors the Hermes case above.
        error_by_role = result["error_by_role"]
        assert isinstance(error_by_role, dict)
        error_blob = json.dumps(error_by_role["ARCHITECTURE"])
        assert "artifacts/BA/acceptance_criteria.json" in error_blob

        working_branch = working_branch_name(run_id)
        committed = read_committed(
            config_root,
            working_branch,
            f".dark-factory/runs/{run_id}/artifacts/BA/acceptance_criteria.json",
        )
        restored = (
            worktree_path(config_root, run_id)
            / ".dark-factory"
            / "runs"
            / str(run_id)
            / "artifacts"
            / "BA"
            / "acceptance_criteria.json"
        )
        assert restored.exists()
        assert restored.read_text("utf-8") == committed
    finally:
        _cleanup_run_dir(config_root, run_id)


def test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts(
    pg_url: str, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control: without this test, every assertion in both
    negative cases above would still pass if ``enforce_artifact_scope`` had
    been wired to fail every role unconditionally -- exactly the failure
    mode a security check added late is most likely to have. The identical
    harness with no tampering entry at all must still reach ``COMPLETED``
    with every role completed and every role's artifacts collected."""
    result = _drive_shipped_config(
        pg_url, engine, tmp_path, monkeypatch, label="no-tamper", expected_exit=0
    )
    run_id = result["run_id"]
    config_root = result["config_root"]
    assert isinstance(run_id, UUID)
    assert isinstance(config_root, Path)

    try:
        assert result["status"] == "COMPLETED"
        assert result["completed_roles"] == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]
        artifact_types_by_role = result["artifact_types_by_role"]
        assert isinstance(artifact_types_by_role, dict)
        for role in ("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"):
            assert artifact_types_by_role.get(role), (
                f"{role} completed with no collected artifacts"
            )
    finally:
        _cleanup_run_dir(config_root, run_id)
