"""CR-01 (04-REVIEW): the shipped ``.dark-factory.yaml`` must be driveable to
``COMPLETED`` by ``dark-factory run <source>`` with no
``DARK_FACTORY_FAKE_SCRIPT`` set.

Every other CLI-subprocess integration test in this suite deliberately routes
around this repo's own config tree with a throwaway one-role ``[BA]`` tree
(see the "the unscripted FakeWorker cannot satisfy" comments across this
package) because, before CR-01's fix, the shipped four-role pipeline's
BA step declared machine-artifact outputs the true-default (unscripted)
``FakeWorker`` reported no artifacts for, which failed the D-09 schema-
validation gate immediately. This is the one test in the suite that runs the
CLI against the *real* repo-root ``.dark-factory.yaml`` -- proving the gap the
04-REVIEW found is closed, not routed around.

This is also the G-04-1 regression guard for the artifact handoff chain
being legible: beyond the existence/attribution assertions above, it proves
BA's own emitted criterion ids actually appear in ``design.md``, in
``implementation_summary.json``'s summary, in ``test_report.json``'s case
names, and as ``verdict.json``'s ordered ``criterion_id`` list. Every
downstream comparison is made against BA's own emitted ids -- never a fixed
expected id -- because a test that hardcodes the id would reproduce the
exact defect it is guarding against (two coinciding literals, not a real
handoff). This content dimension is what the pre-existing existence-only
form of this test could never catch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.domain.artifacts import (
    AcceptanceCriteriaDocument,
    ImplementationSummary,
    TestReport,
    Verdict,
)
from dark_factory.persistence.models import ArtifactReference, RoleExecution, Run

pytestmark = pytest.mark.integration

# tests/integration/test_real_pipeline_zero_config.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_role_artifact(
    session: Session, run_dir: Path, role_execution_id: object, filename: str
) -> str:
    """Resolve ``filename`` through its ``ArtifactReference`` row for
    ``role_execution_id`` and read its content from disk.

    Going through the row (rather than hand-building
    ``run_dir / "artifacts" / role / filename``) keeps the assertion honest
    about the Neon-reference-plus-filesystem-content split and fails loudly
    if a row ever points somewhere the content is not.
    """
    row = session.scalar(
        select(ArtifactReference).where(
            ArtifactReference.role_execution_id == role_execution_id,
            ArtifactReference.type == filename,
        )
    )
    assert row is not None, f"no ArtifactReference row for {filename!r}"
    return (run_dir / row.path).read_text(encoding="utf-8")


def _run_cli_against_real_repo(
    source: str, pg_url: str
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)  # the true zero-config default
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", "run", source],
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,  # this repo's own .dark-factory.yaml, not a throwaway tree
        timeout=90,
        check=False,
    )


def test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script(
    pg_url: str, engine: Engine
) -> None:
    proc = _run_cli_against_real_repo("text:add a health endpoint", pg_url)

    run_dir: Path | None = None
    try:
        assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}"

        run_id = UUID(proc.stdout.splitlines()[0].strip())
        run_dir = _REPO_ROOT / ".dark-factory" / "runs" / str(run_id)

        with Session(engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            assert run.status.value == "COMPLETED"

            # Every one of the four shipped roles ran and completed --
            # BA -> ARCHITECTURE -> DEVELOPMENT -> QA (.dark-factory.yaml's
            # workflow.roles) -- each satisfying its own declared machine-
            # artifact outputs via FakeWorker's CR-01 synthesis, not just the
            # first role in the pipeline.
            executions = list(
                session.scalars(
                    select(RoleExecution)
                    .where(RoleExecution.run_id == run_id)
                    .order_by(RoleExecution.created_at)
                )
            )
            completed_roles = [
                execution.role
                for execution in executions
                if execution.status == "COMPLETED"
            ]
            assert completed_roles == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]

            # And each role's declared outputs actually landed as artifacts
            # rows -- the D-09 gate this whole fix exists to satisfy, not
            # merely a COMPLETED status with an empty artifact set.
            expected_outputs = {
                "BA": {"requirements.md", "acceptance_criteria.json"},
                "ARCHITECTURE": {"design.md", "constraints.json"},
                "DEVELOPMENT": {"implementation_summary.json"},
                "QA": {"test_report.json", "verdict.json"},
            }
            by_role = {execution.role: execution for execution in executions}
            for role, filenames in expected_outputs.items():
                artifact_types = set(
                    session.scalars(
                        select(ArtifactReference.type).where(
                            ArtifactReference.role_execution_id == by_role[role].id
                        )
                    )
                )
                assert artifact_types == filenames, role

            # G-04-1: the handoff chain itself. Every comparison below is
            # against BA's OWN emitted ids -- never a fixed expected value --
            # because a hardcoded id would reproduce the exact defect this
            # guard exists to catch (two independently coinciding literals,
            # not a real handoff).
            ba_content = _read_role_artifact(
                session, run_dir, by_role["BA"].id, "acceptance_criteria.json"
            )
            ba_ids = [
                criterion.id
                for criterion in AcceptanceCriteriaDocument.model_validate_json(
                    ba_content
                ).criteria
            ]
            assert ba_ids, "BA emitted zero acceptance criteria"

            design_content = _read_role_artifact(
                session, run_dir, by_role["ARCHITECTURE"].id, "design.md"
            )
            for criterion_id in ba_ids:
                assert criterion_id in design_content, (
                    f"design.md does not carry BA's criterion id {criterion_id!r} -- "
                    "the ARCHITECTURE -> design.md link in the handoff chain is broken"
                )

            implementation_summary_content = _read_role_artifact(
                session,
                run_dir,
                by_role["DEVELOPMENT"].id,
                "implementation_summary.json",
            )
            implementation_summary = ImplementationSummary.model_validate_json(
                implementation_summary_content
            )
            for criterion_id in ba_ids:
                assert criterion_id in implementation_summary.summary, (
                    "implementation_summary.json's summary does not name BA's "
                    f"criterion id {criterion_id!r} -- the design.md -> "
                    "DEVELOPMENT hop in the handoff chain is broken"
                )

            test_report_content = _read_role_artifact(
                session, run_dir, by_role["QA"].id, "test_report.json"
            )
            case_names = " ".join(
                case.name
                for case in TestReport.model_validate_json(test_report_content).cases
            )
            for criterion_id in ba_ids:
                assert criterion_id in case_names, (
                    "test_report.json's case names do not name BA's criterion "
                    f"id {criterion_id!r} -- the QA link in the handoff chain "
                    "is broken"
                )

            verdict_content = _read_role_artifact(
                session, run_dir, by_role["QA"].id, "verdict.json"
            )
            verdict_ids = [
                criterion.criterion_id
                for criterion in Verdict.model_validate_json(verdict_content).criteria
            ]
            assert verdict_ids == ba_ids, (
                "verdict.json's ordered criterion_id list does not equal BA's "
                f"ordered acceptance-criteria id list (D-05): got {verdict_ids!r}, "
                f"expected {ba_ids!r}"
            )
    finally:
        # Best-effort cleanup: .dark-factory/runs/ is gitignored (per-run
        # artifact content, not source), but there is no reason to leave a
        # real run tree behind in a developer's checkout after this test.
        if run_dir is not None and run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
