"""Plan 12-06, OBS-01 / TRIG-03 / D-19: ``RunReport``'s contract, proved
against real PostgreSQL and real git.

Four properties, each load-bearing on its own:

* **Multi-attempt history (the OBS-01 boundary edge).** ``read_run_detail``
  returns every ``role_executions`` row, not the single latest one
  ``read_status`` reads -- a role that bounces and runs twice must appear
  twice, each with its own column-sourced ``attempt``.
* **Null markers, never omission (TRIG-03).** A run with no interactions, no
  artifacts, no PR and no gate result still carries every section key, with
  an explicit empty/``None`` value -- never a key that silently disappears.
* **Errors are never hidden.** A ``FAILED`` run's error text survives into
  both ``RunDetail.errors`` and the rendered report.
* **The report writes nothing, and the event log is not the control
  state.** Building the report touches no row; tampering the event log
  (insert a bogus row, delete every row) leaves the ``run`` and ``detail``
  sections unchanged -- the SC3 invariance proof
  (``tests/db/test_status_from_columns.py``), extended to the wider report.

Two fixtures carry the weight:

* ``completed_bounced_run`` (module-scoped) -- a real four-role pipeline
  where QA fails once and the terminal quality gate actually runs, driven
  exactly once and shared read-only by every test that needs multi-attempt
  history or a real committed gate file (mirrors
  ``tests/db/test_artifacts_show_reads_committed_content.py``'s module-scoped
  idiom, for the same reason: the drive itself is the expensive part).
* the one-role ``[BA]`` pipeline (``DEFAULT_TEST_SNAPSHOT`` +
  ``git_repo_root`` + ``advance_session_factory``) -- cheap, function-scoped,
  and structurally incapable of ever writing a quality-gate file (BA has no
  ``verdict.json`` output), which is exactly what the "no gate file yields
  None" and "every section renders even when empty" proofs need.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import RunReport
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.events.reader import read_events
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.observability.render import render_run_report
from dark_factory.observability.run_detail import read_quality_gate, read_run_detail
from dark_factory.observability.status import read_status
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence import mutations
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.config import DEFAULT_TEST_SNAPSHOT
from tests.support.fake_artifacts import (
    QA_VERDICT_FAIL_FILES,
    AttemptAwareFourRoleWorker,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]
RegistryBuilder = Callable[[list[WorkerResult]], Any]

# --------------------------------------------------------------------------- #
# shared report-building helper
# --------------------------------------------------------------------------- #


def _build_report(
    run_id: UUID, *, session_factory: SessionFactory, repo_root: Path
) -> RunReport:
    """Compose a :class:`RunReport` exactly the way ``cli.py``'s ``status``
    command does -- the four independent reads, meeting only in the DTO."""
    view = read_status(run_id, session_factory=session_factory)
    detail = read_run_detail(run_id, session_factory=session_factory)
    events = read_events(run_id, session_factory=session_factory)
    gate = read_quality_gate(repo_root, run_id, view.working_branch)
    return RunReport(run=view, detail=detail, quality_gate=gate, events=events)


def _table_counts(session_factory: SessionFactory, run_id: UUID) -> dict[str, int]:
    session = session_factory()
    try:
        return {
            "runs": session.scalar(
                select(func.count()).select_from(Run).where(Run.id == run_id)
            )
            or 0,
            "role_executions": session.scalar(
                select(func.count())
                .select_from(RoleExecution)
                .where(RoleExecution.run_id == run_id)
            )
            or 0,
            "artifacts": session.scalar(
                select(func.count())
                .select_from(ArtifactReference)
                .where(ArtifactReference.run_id == run_id)
            )
            or 0,
            "human_interactions": session.scalar(
                select(func.count())
                .select_from(HumanInteraction)
                .where(HumanInteraction.run_id == run_id)
            )
            or 0,
        }
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# the module-scoped bounced-and-gated run (expensive: driven exactly once)
# --------------------------------------------------------------------------- #

_FAKE_DB_URL = "postgresql+psycopg://df_fake_user:df_fake_pw_0123456789@fake.invalid:5432/df_fake_db"
_FAKE_DB_URL_DIRECT = "postgresql://df_fake_user:df_fake_pw_0123456789@fake-direct.invalid:5432/df_fake_db"
_FAKE_GITHUB_TOKEN = "ghp_FAKEfakeFAKEfake0000000000000000000000"
_FAKE_WEBHOOK_SECRET = "whsec_FAKEfakeFAKEfake0000000000000000"

_DEFINITIONS: dict[str, tuple[str, str]] = {
    "BA": ("[]", "[requirements.md, acceptance_criteria.json]"),
    "ARCHITECTURE": ("[acceptance_criteria.json]", "[design.md, constraints.json]"),
    "DEVELOPMENT": (
        "[design.md, constraints.json]",
        "[implementation_summary.json]",
    ),
    "QA": (
        "[acceptance_criteria.json, implementation_summary.json]",
        "[test_report.json, verdict.json]",
    ),
}
_TOOLS: dict[str, str] = {
    "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
    "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
    "DEVELOPMENT": (
        "[repo.read, repo.search, repo.write, repo.write_tests, "
        "shell.execute, artifacts.read, artifacts.write]"
    ),
    "QA": (
        "[repo.read, repo.search, repo.write_tests, shell.execute, "
        "artifacts.read, artifacts.write]"
    ),
}

# A real, hermetic, always-exits-0 command (no shell, no network) so the
# terminal role's quality gate genuinely runs and writes a non-trivial
# verification/quality_gate.json -- never an empty ``commands: []`` fold.
_GATE_COMMAND = shlex.join([sys.executable, "-c", "import sys; sys.exit(0)"])


def _write_bounce_and_gate_tree(root: Path) -> Path:
    """A real git-backed ``.dark-factory/`` tree for ``[BA, ARCHITECTURE,
    DEVELOPMENT, QA]`` with one configured, passing gate command -- a
    self-contained, module-local duplicate of
    ``tests/db/test_qa_bounce.py``'s ``_write_four_role_tree``, per this
    repo's established convention (12-02-SUMMARY.md) of a sibling copy
    rather than a cross-module import."""
    (root / ".dark-factory/roles").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory/instructions").mkdir(parents=True, exist_ok=True)
    commands_yaml = json.dumps([_GATE_COMMAND])
    (root / ".dark-factory.yaml").write_text(
        "version: 1\n"
        "repository:\n  base_branch: main\n"
        "workflow:\n  roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]\n"
        "roles_dir: .dark-factory/roles\n"
        f"quality_gate:\n  commands: {commands_yaml}\n"
        "retry:\n"
        "  qa_developer_max_iterations: 3\n"
        "  quality_gate_max_iterations: 2\n"
        "publishing:\n  create_pr: false\n",
        encoding="utf-8",
    )
    for role, (inputs, outputs) in _DEFINITIONS.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {_TOOLS[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )
        (root / f".dark-factory/instructions/{role.lower()}.md").write_text(
            f"# {role}\n\nScripted {role} instruction text for tests.\n",
            encoding="utf-8",
        )
    from tests.support.git_repo import make_git_repo

    return make_git_repo(root)


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


@contextmanager
def _fake_secrets_patched() -> Iterator[None]:
    fake_settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
        github_webhook_secret=_FAKE_WEBHOOK_SECRET,
    )
    from unittest.mock import patch

    with patch.object(mutations, "get_settings", lambda: fake_settings):
        yield


@dataclass(frozen=True)
class _BouncedRun:
    run_id: UUID
    repo_root: Path
    working_branch: str


@pytest.fixture(scope="module")
def _module_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture(scope="module")
def completed_bounced_run(
    tmp_path_factory: pytest.TempPathFactory,
    engine: Engine,
    _module_session_factory: SessionFactory,
) -> Iterator[_BouncedRun]:
    """Drive one real four-role run -- QA FAILs on attempt 1, PASSes on
    attempt 2, the terminal gate runs and passes -- exactly once, shared
    read-only by every test that needs multi-attempt history or a real
    committed gate file."""
    root = tmp_path_factory.mktemp("repo")
    root = _write_bounce_and_gate_tree(root)
    snapshot = load_effective_config(root)

    with _fake_secrets_patched():
        run_id = start_run(
            "text:qa bounces once, then the gate runs and passes",
            session_factory=_module_session_factory,
            snapshot=snapshot,
        )
        working_branch = working_branch_name(run_id)
        work_dir = ensure_worktree(
            root, run_id, base_branch="main", working_branch=working_branch
        )
        run_dir = run_root(work_dir, run_id)
        worker = AttemptAwareFourRoleWorker(
            run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
        )

        final = drive(
            run_id,
            session_factory=_module_session_factory,
            registry=_registry(worker),
            repo_root=root,
        )
        assert final is RunStatus.COMPLETED

    yield _BouncedRun(run_id=run_id, repo_root=root, working_branch=working_branch)

    with engine.begin() as conn:
        conn.execute(
            sa.delete(ArtifactReference).where(ArtifactReference.run_id == run_id)
        )
        conn.execute(sa.delete(RunEvent).where(RunEvent.run_id == run_id))
        conn.execute(
            sa.delete(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )
        conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id == run_id))
        conn.execute(sa.delete(Run).where(Run.id == run_id))


# --------------------------------------------------------------------------- #
# multi-attempt history -- the OBS-01 boundary edge
# --------------------------------------------------------------------------- #


def test_a_bounced_role_appears_twice_with_column_sourced_attempts(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
    engine: Engine,
) -> None:
    run = completed_bounced_run
    detail = read_run_detail(run.run_id, session_factory=_module_session_factory)

    dev_attempts = [row.attempt for row in detail.roles if row.role == "DEVELOPMENT"]
    qa_attempts = [row.attempt for row in detail.roles if row.role == "QA"]
    assert dev_attempts == [1, 2]
    assert qa_attempts == [1, 2]

    # The history is every attempt, not a deduplicated summary: the DTO list
    # length equals the real `role_executions` row count for this run.
    with Session(engine) as session:
        db_count = session.scalar(
            select(func.count())
            .select_from(RoleExecution)
            .where(RoleExecution.run_id == run.run_id)
        )
    assert db_count == len(detail.roles)
    assert db_count == 6  # BA(1) + ARCHITECTURE(1) + DEVELOPMENT(2) + QA(2)

    # Column-sourced, not a row count or a list position: cross-check each
    # bounced-role row's `attempt` field against the real column, fetched
    # independently (ordered by `id`, not by `attempt`) so a position-based
    # bug could not coincidentally agree.
    with Session(engine) as session:
        raw_qa = session.scalars(
            select(RoleExecution)
            .where(RoleExecution.run_id == run.run_id, RoleExecution.role == "QA")
            .order_by(RoleExecution.id)
        ).all()
    assert {row.attempt for row in raw_qa} == {1, 2}
    qa_rows_by_attempt = {row.attempt: row for row in detail.roles if row.role == "QA"}
    for raw_row in raw_qa:
        assert qa_rows_by_attempt[raw_row.attempt].attempt == raw_row.attempt
        assert qa_rows_by_attempt[raw_row.attempt].worker == raw_row.worker


def test_the_bounced_qa_attempt_one_row_renders_alongside_attempt_two(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
) -> None:
    """The role-attempt table in the rendered report carries both rows, not
    only the final one -- the same property as the DTO assertion above,
    proved against the actual text an operator reads."""
    run = completed_bounced_run
    report = _build_report(
        run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
    )
    text = render_run_report(report)

    qa_rows = [row for row in report.detail.roles if row.role == "QA"]
    assert len(qa_rows) == 2
    assert "QA" in text
    # Each attempt's own `created_at`, rendered at second precision, is a
    # unique-enough fingerprint per row to prove both are actually present
    # in the text (not just in the DTO the test built from).
    for row in qa_rows:
        assert row.created_at.isoformat(timespec="seconds") in text


# --------------------------------------------------------------------------- #
# quality-gate results
# --------------------------------------------------------------------------- #


def test_quality_gate_results_match_the_committed_file(
    completed_bounced_run: _BouncedRun,
) -> None:
    run = completed_bounced_run
    gate = read_quality_gate(run.repo_root, run.run_id, run.working_branch)

    assert gate is not None
    assert gate.status == "PASS"
    assert len(gate.commands) == 1
    (command_row,) = gate.commands
    assert command_row.exit_code == 0
    assert sys.executable in command_row.command


def test_quality_gate_view_appears_in_both_render_modes(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
) -> None:
    run = completed_bounced_run
    report = _build_report(
        run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
    )
    assert report.quality_gate is not None

    text = render_run_report(report)
    payload = json.loads(report.as_json())

    assert "quality_gate" in text
    assert payload["quality_gate"]["status"] == "PASS"
    assert payload["quality_gate"]["commands"][0]["exit_code"] == 0


# --------------------------------------------------------------------------- #
# the report performs no write; the event log is not the control state
# --------------------------------------------------------------------------- #


def test_report_performs_no_write(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
) -> None:
    run = completed_bounced_run
    before = _table_counts(_module_session_factory, run.run_id)

    for _ in range(3):
        _build_report(
            run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
        )

    after = _table_counts(_module_session_factory, run.run_id)
    assert after == before


def test_run_and_detail_sections_are_invariant_under_event_log_tampering(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
) -> None:
    run = completed_bounced_run
    baseline = _build_report(
        run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
    )
    counts_before = _table_counts(_module_session_factory, run.run_id)

    session = _module_session_factory()
    try:
        session.add(
            RunEvent(
                run_id=run.run_id, type="TOTALLY_BOGUS", payload={"injected": True}
            )
        )
        session.commit()
    finally:
        session.close()

    session = _module_session_factory()
    try:
        session.execute(sa.delete(RunEvent).where(RunEvent.run_id == run.run_id))
        session.commit()
    finally:
        session.close()

    tampered = _build_report(
        run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
    )

    # The run's reported position and detail are unaffected by vandalising
    # the append-only audit log -- SC3, extended from `read_status` to the
    # wider report. `events` legitimately differs: it is the one section
    # that displays the log, and the log is now empty.
    assert tampered.run == baseline.run
    assert tampered.detail == baseline.detail
    assert tampered.events != baseline.events
    assert tampered.events == []

    counts_after = _table_counts(_module_session_factory, run.run_id)
    assert counts_after == counts_before


# --------------------------------------------------------------------------- #
# the cheap one-role [BA] run -- null markers and "no gate file"
# --------------------------------------------------------------------------- #


def _completed_minimal_run(
    session_factory: SessionFactory,
    registry_builder: RegistryBuilder,
    repo_root: Path,
) -> UUID:
    run_id = start_run(
        "text:a minimal run with nothing but the required fields",
        session_factory=session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    registry = registry_builder(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="done",
                worker_session_id="fake-report-minimal",
            )
        ]
    )
    final = drive(
        run_id, session_factory=session_factory, registry=registry, repo_root=repo_root
    )
    assert final is RunStatus.COMPLETED
    return run_id


def test_empty_sections_render_with_explicit_null_markers_not_omission(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    git_repo_root: Path,
) -> None:
    run_id = _completed_minimal_run(
        advance_session_factory, fake_worker_registry, git_repo_root
    )
    report = _build_report(
        run_id, session_factory=advance_session_factory, repo_root=git_repo_root
    )

    assert report.detail.interactions == []
    assert report.detail.artifacts == []
    assert report.detail.errors == []
    assert report.detail.pr_number is None
    assert report.detail.pr_url is None
    assert report.quality_gate is None

    payload = json.loads(report.as_json())
    for key in RunReport.SECTION_KEYS:
        assert key in payload, (
            f"{key} missing from --json output -- omission, not a null marker"
        )
    assert payload["interactions"] == []
    assert payload["artifacts"] == []
    assert payload["errors"] == []
    assert payload["quality_gate"] is None
    assert payload["pr_number"] is None
    assert payload["pr_url"] is None
    assert payload["published_commit_sha"] is None

    text = render_run_report(report)
    for key in (
        "interactions",
        "artifacts",
        "quality_gate",
        "errors",
        "events",
        "roles",
    ):
        assert key in text, f"{key} section title missing from the rendered report"
    assert "pr_number" in text
    assert "pr_url" in text
    assert "published_commit_sha" in text


def test_quality_gate_is_none_for_a_run_whose_working_branch_has_no_gate_file(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    git_repo_root: Path,
) -> None:
    """Item 6 of the plan: ``working_branch`` is set (every run created
    through ``start_run`` persists one, GIT-01) but the one-role ``[BA]``
    pipeline never reaches the terminal-role gate branch at all (BA has no
    ``verdict.json`` output) -- so no ``verification/quality_gate.json`` is
    ever committed, and ``read_quality_gate`` must degrade to ``None``
    rather than raise."""
    run_id = _completed_minimal_run(
        advance_session_factory, fake_worker_registry, git_repo_root
    )
    view = read_status(run_id, session_factory=advance_session_factory)
    assert view.working_branch is not None

    gate = read_quality_gate(git_repo_root, run_id, view.working_branch)
    assert gate is None


# --------------------------------------------------------------------------- #
# a FAILED run never hides its error
# --------------------------------------------------------------------------- #


def test_a_failed_run_shows_its_error_text(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    git_repo_root: Path,
) -> None:
    run_id = start_run(
        "text:make this fail, loudly",
        session_factory=advance_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    registry = fake_worker_registry(
        [
            WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="analysis could not be completed",
                error="boom-detail-report-99",
            )
        ]
    )
    final = drive(
        run_id,
        session_factory=advance_session_factory,
        registry=registry,
        repo_root=git_repo_root,
    )
    assert final is RunStatus.FAILED

    detail = read_run_detail(run_id, session_factory=advance_session_factory)
    assert detail.errors, "a FAILED run must carry at least one error string"
    assert any("boom-detail-report-99" in error for error in detail.errors)

    report = _build_report(
        run_id, session_factory=advance_session_factory, repo_root=git_repo_root
    )
    text = render_run_report(report)
    assert "boom-detail-report-99" in text
    payload = json.loads(report.as_json())
    assert any("boom-detail-report-99" in error for error in payload["errors"])


# --------------------------------------------------------------------------- #
# precision: second-precision timestamps, never sub-second
# --------------------------------------------------------------------------- #


def test_rendered_timestamps_carry_second_precision_with_no_subsecond_component(
    completed_bounced_run: _BouncedRun,
    _module_session_factory: SessionFactory,
) -> None:
    run = completed_bounced_run
    report = _build_report(
        run.run_id, session_factory=_module_session_factory, repo_root=run.repo_root
    )
    text = render_run_report(report)

    # Every role-attempt row's own isoformat(timespec="seconds") rendering
    # is free of a fractional-second component; an over-precise reading
    # (microseconds) would not match this exact string.
    for row in report.detail.roles:
        rendered = row.created_at.isoformat(timespec="seconds")
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", rendered)
        assert rendered in text
        assert f"{rendered}." not in text  # no trailing fractional digits
