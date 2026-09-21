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

**08-04 (Task 2):** after Task 3's reassignment, driving the shipped
configuration set exercises three external agent runtimes (Copilot for
ARCHITECTURE, Claude Code for DEVELOPMENT, Hermes for QA) rather than only
``FakeWorker`` -- the test's own subject changes in exactly this one way,
stated here rather than glossed over. The ``_external_runtime_fakes``
fixture below installs all three fake CLI executables with
``declared_outputs=True`` and both worker credentials into the environment
``_run_cli_against_real_repo`` spawns the CLI subprocess from, so this test
now proves the shipped configuration set resolves and drives to
``COMPLETED`` across three runtimes with no explicit worker script, and that
the acceptance-criteria handoff chain (see the G-04-1 paragraph above)
survives the hop through those external runtimes. No assertion changed for
this: the test still exercises ``FakeWorker`` alone until Task 3's role-YAML
edit lands, at which point the same fixture -- installed here, unchanged --
becomes load-bearing with zero further edits to this file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
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
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_copilot_cli import write_fake_copilot
from tests.support.fake_hermes_cli import write_fake_hermes
from tests.support.git_repo import make_git_repo, run_artifact_text

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
    session: Session,
    config_root: Path,
    run_id: UUID,
    working_branch: str,
    role_execution_id: object,
    filename: str,
) -> str:
    """Resolve ``filename`` through its ``ArtifactReference`` row for
    ``role_execution_id`` and read its content through the working branch.

    Going through the row (rather than hand-building
    ``artifacts/<role>/<filename>``) keeps the assertion honest about the
    Neon-reference-plus-git-content split and fails loudly if a row ever
    points somewhere the content is not. 05-03 (D-04): this run reaches
    ``COMPLETED``, so its worktree is removed by cleanup by the time this is
    called -- ``run_artifact_text`` reads through ``config_root``'s
    ``working_branch`` ref instead of a now-gone disk path.
    """
    row = session.scalar(
        select(ArtifactReference).where(
            ArtifactReference.role_execution_id == role_execution_id,
            ArtifactReference.type == filename,
        )
    )
    assert row is not None, f"no ArtifactReference row for {filename!r}"
    return run_artifact_text(config_root, run_id, working_branch, row.path)


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
        # 08-04 Task 2: after Task 3's reassignment this run spawns three
        # additional CLI subprocesses (Copilot, Claude Code, Hermes) on top
        # of BA's in-process FakeWorker step. A generous upper bound on a
        # cold start across four role attempts, not a timing assertion.
        timeout=240,
        check=False,
    )


@pytest.fixture
def _external_runtime_fakes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Install all three fake CLI executables -- ``claude``, ``copilot``,
    ``hermes`` -- with ``declared_outputs=True`` in one directory, prepend it
    to ``PATH``, and set both worker credentials to obviously-fake values
    (08-04 Task 2).

    :func:`_run_cli_against_real_repo` builds the child environment from
    ``os.environ`` at call time, so every value ``monkeypatch.setenv`` sets
    here reaches the CLI subprocess directly and, through
    :func:`~dark_factory.tools.env.build_worker_env`'s ``PATH`` entry,
    reaches each adapter's own spawn in turn.

    This fixture is installed unconditionally, independent of which worker
    each shipped role is currently assigned to: until Task 3 reassigns
    ``ARCHITECTURE``/``DEVELOPMENT``/``QA`` away from ``fake``, none of these
    three fakes are ever invoked (``FakeWorker`` runs in-process and spawns
    nothing) -- installing them here in advance is what lets Task 3's
    role-YAML edit alone flip this test onto three real runtimes with no
    further edit to this file (WORK-09's "zero workflow/test-code change").
    """
    fake_dir = tmp_path / "external-runtime-fakebin"
    # ClaudeCodeWorker parses a single JSON object off stdout (--output-format
    # json); the other two adapters parse plain text. Only the Claude Code
    # payload needs a `result` field to make it through `_spawn_and_parse`
    # cleanly, and it deliberately carries no NEEDS_INPUT marker.
    write_fake_claude(
        fake_dir,
        stdout_payload=json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "session_id": "sess-08-04-development",
                "result": "implementation complete",
            }
        ),
        declared_outputs=True,
    )
    write_fake_copilot(
        fake_dir, stdout_payload="architecture design complete", declared_outputs=True
    )
    write_fake_hermes(
        fake_dir, stdout_payload="QA verification complete", declared_outputs=True
    )

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{fake_dir}{os.pathsep}{existing_path}")
    monkeypatch.setenv(
        "COPILOT_GITHUB_TOKEN", "github_pat_fake0000000000000000000000000000"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake0000000000000000000000000000")
    yield fake_dir


def test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script(
    pg_url: str,
    engine: Engine,
    tmp_path: Path,
    _external_runtime_fakes: Path,
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
            working_branch = run.working_branch
            assert working_branch is not None

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
                session,
                config_root,
                run_id,
                working_branch,
                by_role["BA"].id,
                "acceptance_criteria.json",
            )
            ba_ids = [
                criterion.id
                for criterion in AcceptanceCriteriaDocument.model_validate_json(
                    ba_content
                ).criteria
            ]
            assert ba_ids, "BA emitted zero acceptance criteria"

            design_content = _read_role_artifact(
                session,
                config_root,
                run_id,
                working_branch,
                by_role["ARCHITECTURE"].id,
                "design.md",
            )
            for criterion_id in ba_ids:
                assert criterion_id in design_content, (
                    f"design.md does not carry BA's criterion id {criterion_id!r} -- "
                    "the ARCHITECTURE -> design.md link in the handoff chain is broken"
                )

            implementation_summary_content = _read_role_artifact(
                session,
                config_root,
                run_id,
                working_branch,
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
                session,
                config_root,
                run_id,
                working_branch,
                by_role["QA"].id,
                "test_report.json",
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
                session,
                config_root,
                run_id,
                working_branch,
                by_role["QA"].id,
                "verdict.json",
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
