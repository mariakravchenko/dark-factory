"""The literal WORK-09 / ROADMAP SC2 proof (08-04 Task 3): reassigning the
shipped pipeline's roles across three real runtimes in configuration alone
-- ``ARCHITECTURE`` on Copilot, ``DEVELOPMENT`` on Claude Code, ``QA`` on
Hermes -- requires zero workflow-code change and the run still completes,
producing an identical role sequence and identical per-role artifact-type
sets to the same pipeline driven entirely on ``FakeWorker``.

Structured as a paired-run equality proof -- the shape this repository
already uses for "the same code ran" claims (the projected-remainder
pattern recorded for plan 02-06 in STATE.md): drive two throwaway git
checkouts of the *verbatim* shipped configuration set through the real CLI,
one carrying the shipped ``worker:`` values (``fake``/``copilot``/
``claude-code``/``hermes``), the other with every ``worker:`` line rewritten
to ``fake``. Everything the orchestrator produced is asserted identical
between the two runs -- terminal status, ordered completed-role list,
per-role artifact-type sets -- and the only asserted difference is the
persisted worker name each role execution recorded. The only thing edited
between the two configuration trees is the ``worker:`` line; asserting that
up front, before anything else, is what makes the rest of this test a proof
about configuration rather than a coincidence.

The negative case (no fake executables on ``PATH``) rules out a silent
fallback: a substitution bug -- an externally-assigned role quietly running
on a different worker when its configured binary is absent -- would look
exactly like a pass without it (T-08-23).

This test needs a reachable PostgreSQL 17, the same as
``tests/integration/test_real_pipeline_zero_config.py``, whose shipped-config
copy helper and CLI-subprocess runner it reuses rather than re-deriving.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.git.worktree import worktree_path
from dark_factory.persistence.models import ArtifactReference, RoleExecution, Run
from tests.integration.test_real_pipeline_zero_config import _run_cli_against_real_repo
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_copilot_cli import write_fake_copilot
from tests.support.fake_hermes_cli import write_fake_hermes
from tests.support.git_repo import git_commit_all, make_git_repo
from tests.support.shipped_config import copy_shipped_config_into

pytestmark = pytest.mark.integration

_ROLE_YAML_DIR = ".dark-factory/roles"
_WORKER_LINE_RE = re.compile(r"^worker:\s*(\S+)\s*$", re.MULTILINE)


def _install_external_runtime_fakes(
    fake_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Install all three fake CLI executables with ``declared_outputs=True``
    and both worker credentials -- identical to
    ``test_real_pipeline_zero_config._external_runtime_fakes``, duplicated
    (not imported) here because this module drives two separate throwaway
    checkouts through the same ``PATH``/credential environment in one test
    function, which does not fit that fixture's one-checkout-per-test shape.
    """
    write_fake_claude(
        fake_dir,
        stdout_payload=json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "session_id": "sess-08-04-sc2-development",
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


def _rewrite_all_workers_to_fake(config_root: Path) -> None:
    """In ``config_root``'s already-copied shipped role YAML set, rewrite
    every ``worker:`` value to ``fake`` with a single targeted line
    substitution per file -- never a YAML re-serialization, which could
    reformat comments/whitespace and defeat the line-level equality
    assertion in :func:`_role_yaml_diff_is_worker_lines_only`."""
    roles_dir = config_root / _ROLE_YAML_DIR
    for role_file in sorted(roles_dir.glob("*.yaml")):
        original = role_file.read_text("utf-8")
        rewritten = _WORKER_LINE_RE.sub("worker: fake", original, count=1)
        assert rewritten != original or "worker: fake" in original, (
            f"{role_file} has no worker: line to rewrite"
        )
        role_file.write_text(rewritten, "utf-8")


def _role_yaml_diff_is_worker_lines_only(
    three_runtime_root: Path, all_fake_root: Path
) -> None:
    """Assert the two role-YAML sets differ only on ``worker:`` lines --
    the assertion that makes the rest of this test a proof about
    configuration rather than a coincidence (must run first, must fail
    loudly)."""
    three_runtime_dir = three_runtime_root / _ROLE_YAML_DIR
    all_fake_dir = all_fake_root / _ROLE_YAML_DIR
    three_runtime_files = sorted(three_runtime_dir.glob("*.yaml"))
    all_fake_files = sorted(all_fake_dir.glob("*.yaml"))
    assert [p.name for p in three_runtime_files] == [p.name for p in all_fake_files]

    for three_runtime_file, all_fake_file in zip(
        three_runtime_files, all_fake_files, strict=True
    ):
        three_runtime_lines = three_runtime_file.read_text("utf-8").splitlines()
        all_fake_lines = all_fake_file.read_text("utf-8").splitlines()
        assert len(three_runtime_lines) == len(all_fake_lines), (
            f"{three_runtime_file.name}: line count differs between the two "
            "configuration trees"
        )
        for line_number, (three_runtime_line, all_fake_line) in enumerate(
            zip(three_runtime_lines, all_fake_lines, strict=True), start=1
        ):
            if three_runtime_line == all_fake_line:
                continue
            assert _WORKER_LINE_RE.match(three_runtime_line) and _WORKER_LINE_RE.match(
                all_fake_line
            ), (
                f"{three_runtime_file.name}:{line_number} differs but is not "
                f"a worker: line -- three-runtime={three_runtime_line!r}, "
                f"all-fake={all_fake_line!r}"
            )


def _run_and_collect(
    source: str, pg_url: str, engine: Engine, config_root: Path
) -> dict[str, object]:
    """Drive ``config_root``'s (already-copied) shipped configuration
    through the real CLI subprocess and collect the four dimensions this
    test compares: terminal status, ordered completed-role list, per-role
    artifact-type sets, and per-role persisted worker name."""
    proc = _run_cli_against_real_repo(source, pg_url, config_root)
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
        completed = [e for e in executions if e.status == "COMPLETED"]
        artifact_types_by_role = {}
        worker_by_role = {}
        for execution in completed:
            types = set(
                session.scalars(
                    select(ArtifactReference.type).where(
                        ArtifactReference.role_execution_id == execution.id
                    )
                )
            )
            artifact_types_by_role[execution.role] = types
            worker_by_role[execution.role] = execution.worker

        return {
            "run_id": run_id,
            "status": run.status.value,
            "completed_roles": [e.role for e in completed],
            "artifact_types_by_role": artifact_types_by_role,
            "worker_by_role": worker_by_role,
            "executions": executions,
        }


def test_reassigned_roles_reach_completed_identically_to_all_fake(
    pg_url: str, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WORK-09 / ROADMAP SC2: the shipped configuration, reassigned across
    three real runtimes, produces an orchestrator outcome identical to the
    same configuration run entirely on ``FakeWorker`` -- except for which
    worker name each role execution records.
    """
    three_runtime_root = copy_shipped_config_into(
        make_git_repo(tmp_path / "three-runtime-repo")
    )
    all_fake_root = copy_shipped_config_into(make_git_repo(tmp_path / "all-fake-repo"))
    _rewrite_all_workers_to_fake(all_fake_root)
    git_commit_all(all_fake_root, "rewrite worker: lines to fake for SC2 comparison")

    # This assertion is what makes the rest of the test a proof about
    # configuration rather than a coincidence -- it must come first and
    # must fail loudly. 10-07: the precondition still holds -- this compares
    # `.dark-factory/roles/*.yaml` between the two copied roots, which
    # `copy_shipped_config_into`'s neutralization never touches (it rewrites
    # only `.dark-factory.yaml`'s `quality_gate`/`publishing` keys), and both
    # roots are neutralized identically.
    _role_yaml_diff_is_worker_lines_only(three_runtime_root, all_fake_root)

    fake_dir = tmp_path / "sc2-fakebin"
    _install_external_runtime_fakes(fake_dir, monkeypatch)

    source = "text:add a health endpoint"
    three_runtime_result = _run_and_collect(source, pg_url, engine, three_runtime_root)
    all_fake_result = _run_and_collect(source, pg_url, engine, all_fake_root)

    try:
        # Everything the orchestrator produced is identical between the two
        # runs -- the only thing that differs is which runtime performed
        # the work, and the only thing that was edited between the two
        # configuration trees is a `worker:` field. That is WORK-09.
        assert three_runtime_result["status"] == "COMPLETED"
        assert all_fake_result["status"] == "COMPLETED"
        assert (
            three_runtime_result["completed_roles"]
            == all_fake_result["completed_roles"]
            == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]
        )
        assert (
            three_runtime_result["artifact_types_by_role"]
            == all_fake_result["artifact_types_by_role"]
        )

        # The fourth dimension differs in exactly the expected way.
        assert three_runtime_result["worker_by_role"] == {
            "BA": "fake",
            "ARCHITECTURE": "copilot",
            "DEVELOPMENT": "claude-code",
            "QA": "hermes",
        }
        assert all_fake_result["worker_by_role"] == {
            "BA": "fake",
            "ARCHITECTURE": "fake",
            "DEVELOPMENT": "fake",
            "QA": "fake",
        }
    finally:
        for result in (three_runtime_result, all_fake_result):
            run_id = result["run_id"]
            assert isinstance(run_id, UUID)
            root = (
                worktree_path(
                    three_runtime_root
                    if result is three_runtime_result
                    else all_fake_root,
                    run_id,
                )
                / ".dark-factory"
                / "runs"
                / str(run_id)
            )
            if root.is_dir():
                shutil.rmtree(root, ignore_errors=True)


def test_shipped_config_with_no_fake_binaries_fails_visibly_not_silently(
    pg_url: str, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-08-23: with the shipped configuration but no fake executables on
    ``PATH``, the run must not reach ``COMPLETED``, the first
    externally-assigned role's execution must be recorded ``FAILED``, and no
    role execution may record a worker other than the one its own
    configuration assigned -- ruling out a silent substitution to a
    different worker, which would otherwise look exactly like a pass.
    """
    config_root = copy_shipped_config_into(
        make_git_repo(tmp_path / "no-binaries-repo")
    )

    # No fake claude/copilot/hermes on PATH, and no worker credentials set --
    # ARCHITECTURE (the first externally-assigned role after BA) must fail
    # to spawn `copilot` at all.
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    proc = _run_cli_against_real_repo("text:add a health endpoint", pg_url, config_root)
    run_id = UUID(proc.stdout.splitlines()[0].strip())

    run_dir: Path | None = None
    try:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            assert run.status.value != "COMPLETED"

            executions = list(
                session.scalars(
                    select(RoleExecution)
                    .where(RoleExecution.run_id == run_id)
                    .order_by(RoleExecution.created_at)
                )
            )
            statuses_by_role = {e.role: e.status for e in executions}
            assert statuses_by_role.get("ARCHITECTURE") == "FAILED", (
                f"expected ARCHITECTURE FAILED, got {statuses_by_role}"
            )
            # 10-07 (G-10-1 masked-assertion finding): the terminal status
            # and exit code alone are not the proof -- an unrelated
            # terminal failure (e.g. gate exhaustion, which is exactly what
            # happened here before 10-07) would look identical. Bind the
            # persisted error and assert on its real content.
            #
            # Read via src/dark_factory/workers/copilot.py: the credential
            # check (`settings.copilot_github_token is None`) runs BEFORE
            # anything is spawned, so with COPILOT_GITHUB_TOKEN deleted
            # above and no `.env` reachable from this throwaway repo's cwd
            # (`Settings.model_config.env_file=".env"` is CWD-relative),
            # `CopilotWorker.execute()` raises `MissingWorkerCredentialError`
            # -- never reaching a `copilot`-binary spawn attempt at all. The
            # persisted error therefore names the missing credential, not a
            # process-not-found error; the assertion below is on the real
            # substring that message contains, not a guess.
            error_by_role = {e.role: e.error for e in executions}
            architecture_error = error_by_role["ARCHITECTURE"]
            assert architecture_error, "ARCHITECTURE execution has no persisted error"
            architecture_error_blob = json.dumps(architecture_error)
            assert "COPILOT_GITHUB_TOKEN" in architecture_error_blob
            assert "not configured" in architecture_error_blob

            expected_worker = {
                "BA": "fake",
                "ARCHITECTURE": "copilot",
                "DEVELOPMENT": "claude-code",
                "QA": "hermes",
            }
            for execution in executions:
                assert execution.worker == expected_worker[execution.role], (
                    f"{execution.role} recorded worker "
                    f"{execution.worker!r}, expected "
                    f"{expected_worker[execution.role]!r} -- a "
                    "substitution to a different worker would silently "
                    "pass without this assertion"
                )

        run_dir = (
            worktree_path(config_root, run_id) / ".dark-factory" / "runs" / str(run_id)
        )
    finally:
        if run_dir is not None and run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
