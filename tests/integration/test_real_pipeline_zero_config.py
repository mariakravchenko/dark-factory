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
CLI against the *real* shipped ``.dark-factory.yaml`` set -- proving the gap
the 04-REVIEW found is closed, not routed around.

Since Phase 5 (GIT-01), ``advance``/``drive`` create a real git worktree
(``ensure_worktree``) as a *sibling* of the CLI's own ``cwd`` before running
any role -- driving this test's ``cwd`` straight at this repository's own
checkout (the pre-Phase-5 shape) would create a real ``dark-factory/run-<id>``
branch and a real sibling worktree directory next to the developer's own
checkout, an unacceptable side effect on a real working repository. This test
therefore copies the shipped config set (``.dark-factory.yaml``,
``.dark-factory/roles/``, ``.dark-factory/instructions/``) into a throwaway
``tmp_path`` repository built by ``make_git_repo`` and drives the CLI there
instead. The property under test -- "the shipped config resolves and drives
to ``COMPLETED`` with no scripted worker" -- is fully preserved, because the
config files copied in are the real, shipped ones; only the checkout they run
against changes. A future reader should not "restore" the old
drive-against-this-repo behaviour.

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
from dark_factory.git.client import run_git
from dark_factory.git.worktree import worktree_path
from dark_factory.persistence.models import ArtifactReference, RoleExecution, Run
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.integration

# tests/integration/test_real_pipeline_zero_config.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

_SHIPPED_CONFIG_PATHS: tuple[str, ...] = (
    ".dark-factory.yaml",
    ".dark-factory/roles",
    ".dark-factory/instructions",
)


def _copy_shipped_config_into(root: Path) -> Path:
    """Copy this repo's real shipped config set into ``root`` (already a real
    git repository) and commit it, so the CLI drives against the genuine
    ``.dark-factory.yaml`` / role / instruction files without touching the
    developer's own checkout."""
    for relative in _SHIPPED_CONFIG_PATHS:
        source = _REPO_ROOT / relative
        dest = root / relative
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", "shipped config"], cwd=root)
    return root


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
    source: str, pg_url: str, cwd: Path
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
        cwd=cwd,  # the shipped config set, copied into a throwaway git repo
        timeout=90,
        check=False,
    )


def test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script(
    pg_url: str, engine: Engine, tmp_path: Path
) -> None:
    config_root = _copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
    proc = _run_cli_against_real_repo("text:add a health endpoint", pg_url, config_root)

    run_dir: Path | None = None
    try:
        assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}"

        run_id = UUID(proc.stdout.splitlines()[0].strip())
        # GIT-01: the runner resolves the run tree inside the worktree
        # ensure_worktree creates as a sibling of config_root, not under
        # config_root itself.
        run_dir = (
            worktree_path(config_root, run_id) / ".dark-factory" / "runs" / str(run_id)
        )

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
        # Best-effort cleanup of the run tree inside the throwaway worktree.
        # Since Phase 5 (GIT-01) everything -- config_root, its sibling
        # worktree -- lives under this test's own tmp_path, so there is no
        # real-checkout pollution risk left to guard against here; this is
        # tidiness, not correctness.
        if run_dir is not None and run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
