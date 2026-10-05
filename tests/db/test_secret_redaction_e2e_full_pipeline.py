"""Phase 12's fourth success criterion (OBS-01/OBS-02/OBS-03), proved the only
honest way: one real ``github:``-sourced run, seeded with six credential-shaped
literals across four distinct shapes, driven through intake, a human pause and
resume, a quality gate and a published pull request -- then swept for every one
of them across all seven D-08 sinks, a whole-table sweep of all five owned
tables, and this phase's own four new CLI surfaces.

Plan 12-03 found a real gap (the GitHub clarification comment bypassed the
redaction function entirely) that a *unit* test of that function could never
have caught, because the function itself was correct the whole time -- only
one call site had forgotten to call it. This module is built on that lesson:
it never invokes the redaction function directly to compute an expected
value and compare against it. Every assertion below runs through production
code -- ``start_run``/``drive``, the real read-and-render functions
``dark-factory status``/``runs``/``events``/``artifacts --show`` call, and a
real ``ClaudeCodeWorker`` spawning a real (but fake) ``claude`` subprocess.
The one place the redaction function's bare name appears in this module at
all is passed, unapplied, to ``functools.partial`` -- the exact construction
``cli.py``'s own ``_redactor()`` uses -- to build the redactor handed to the
production render functions for the CLI-surface sweep.

Driven in-process rather than through the CLI subprocess (``dark-factory
run``), because injecting a :class:`~tests.support.fake_github.FakeGitHubClient`
requires the ``github_client_factory`` seam ``drive()`` threads through --
the CLI always binds ``default_github_client_factory``, which would attempt a
real GitHub call. This resolves 12-RESEARCH.md's Open Question 3: the only
construction that uses both ``fake_claude_cli.py`` and ``fake_github.py`` (the
two fixtures CONTEXT.md names) is an in-process ``drive()`` whose worker
registry wraps a real ``ClaudeCodeWorker`` pointed at the fake ``claude``
binary.

**Deviation (Rule 1/2, documented in the plan summary):** running this module
against the pipeline as it stood before this plan found that a role's own
*artifact file content* -- unlike every other D-08 sink -- was never scrubbed
before ``git.diff.commit_run_artifacts`` force-added and committed it onto the
run's working branch (which becomes the PR branch). This module's own
``ARCHITECTURE`` artifact plants a credential in exactly that sink to prove
it; the fix (``dark_factory.artifacts.store.scrub_artifact_text_in_place``,
called from ``orchestrator/runner.py`` immediately after a role reports
``COMPLETED`` and before ``collect_role_artifacts`` reads the same file for
schema validation and checksum computation) is committed alongside this test.
"""

from __future__ import annotations

import functools
import json
import os
import shlex
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
import structlog
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import dark_factory.orchestrator.runner as runner_module
from dark_factory import logging as df_logging
from dark_factory.artifacts.paths import run_root
from dark_factory.artifacts.store import write_artifact_text
from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import RunReport
from dark_factory.domain.worker import (
    ArtifactRef,
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.events.reader import read_events
from dark_factory.events.redaction import redact
from dark_factory.git.committed import run_artifact_text
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.github.client import GitHubComment, GitHubIssue, GitHubPullRequest
from dark_factory.input import loaders
from dark_factory.observability.render import (
    render_events_json,
    render_events_text,
    render_run_report,
    render_runs_table,
)
from dark_factory.observability.run_detail import (
    read_quality_gate,
    read_run_detail,
    read_run_list,
)
from dark_factory.observability.status import read_status
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence import mutations as mutations_module
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers import claude_code as claude_code_module
from dark_factory.workers import cli_runtime as cli_runtime_module
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.claude_code import ClaudeCodeWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_github import FakeGitHubClient
from tests.support.git_repo import make_git_repo
from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.db

SessionFactory = Callable[[], Session]

# --------------------------------------------------------------------------- #
# Six seeded credential constants, two shapes x two origins: four configured
# into `Settings` (exact-value substitution) and two free-standing literals
# configured nowhere (the compiled D-15 pattern table). `_SEEDED_ANTHROPIC_KEY`
# is the load-bearing exact-value-only proof: `sk-ant-` matches none of the
# compiled patterns, so it can only ever be caught by known-value substitution.
# --------------------------------------------------------------------------- #

_SEEDED_DB_PASSWORD = "sc7SEEDEDpw0123456789"
_SEEDED_DB_URL = (
    f"postgresql+psycopg://sc7user:{_SEEDED_DB_PASSWORD}"
    "@sc7-fake-db.invalid:5432/sc7factory"
)
_SEEDED_DB_URL_DIRECT = (
    f"postgresql+psycopg://sc7user:{_SEEDED_DB_PASSWORD}"
    "@sc7-fake-direct.invalid:5432/sc7factory"
)
_SEEDED_GITHUB_TOKEN = "ghp_" + "SEEDEDliveTOKENConfiguredValue0123456"
_SEEDED_ANTHROPIC_KEY = "sk-ant-SEEDEDsecretSEEDEDsecretSEEDEDsec01"

_SEEDED_GHP_PATTERN = "ghp_" + "PATTERNonlyNotConfigured123456789012"
_SEEDED_KV_PASSWORD = "hunter2SEEDEDnotconfigured"
_SEEDED_KV = f"password={_SEEDED_KV_PASSWORD}"

_FORBIDDEN_LITERALS = (
    _SEEDED_DB_URL,
    _SEEDED_DB_URL_DIRECT,
    _SEEDED_DB_PASSWORD,
    _SEEDED_GITHUB_TOKEN,
    _SEEDED_ANTHROPIC_KEY,
    _SEEDED_GHP_PATTERN,
    _SEEDED_KV,
    _SEEDED_KV_PASSWORD,
)

# --------------------------------------------------------------------------- #
# Where each literal genuinely travels: task text, a question, an answer, a
# worker's own summary, an artifact file, and a quality-gate command string.
# --------------------------------------------------------------------------- #

_OWNER = "acme"
_REPO = "sc7widgets"
_ISSUE_NUMBER = 701
_ISSUE_TITLE = "Audit the credential rotation runbook"
_BASE_BRANCH = "main"

_ISSUE_BODY = (
    "Please rotate the credentials before the audit: "
    f"{_SEEDED_DB_URL} and {_SEEDED_GITHUB_TOKEN} must be retired."
)

_SEEDED_QUESTION = (
    f"Should we rotate {_SEEDED_GHP_PATTERN} first, or the {_SEEDED_KV} entry?"
)
_SEEDED_ANSWER = f"Use {_SEEDED_ANTHROPIC_KEY} for review access going forward."

_BA_FILES = {
    "requirements.md": "# Requirements\n\n1. The system does the thing correctly.\n",
    "acceptance_criteria.json": json.dumps(
        {"criteria": [{"id": "AC-1", "description": "the thing works"}]}
    ),
}
_ARCHITECTURE_FILES = {
    "design.md": (
        "# Design\n\nImplement the thing in the existing service layer. See "
        f"{_SEEDED_DB_URL_DIRECT} for the legacy migration notes.\n"
    ),
    "constraints.json": json.dumps(
        {"constraints": [{"id": "C-1", "description": "no new database migration"}]}
    ),
}
_QA_FILES = {
    "test_report.json": json.dumps(
        {
            "cases": [
                {
                    "name": "AC-1: the thing works",
                    "result": "PASS",
                    "detail": "reproduced manually",
                }
            ]
        }
    ),
    "verdict.json": json.dumps(
        {
            "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
            "issues": [],
            "status": "PASS",
        }
    ),
}
_ROLE_FILES: dict[str, dict[str, str]] = {
    "BA": _BA_FILES,
    "ARCHITECTURE": _ARCHITECTURE_FILES,
    "QA": _QA_FILES,
}
_ROLE_SUMMARIES: dict[str, str] = {
    "BA": f"BA analysis complete; rotate {_SEEDED_GITHUB_TOKEN} before merging.",
    "ARCHITECTURE": "architecture design complete",
    "QA": "QA verified every acceptance criterion",
}

_DEV_RESULT_TEXT = (
    f"implementation complete; reference {_SEEDED_GHP_PATTERN} and "
    f"{_SEEDED_ANTHROPIC_KEY} in the changelog."
)
_DEV_STDOUT_PAYLOAD = json.dumps(
    {
        "subtype": "success",
        "is_error": False,
        "session_id": "sess-sc7-development",
        "result": _DEV_RESULT_TEXT,
    }
)
_DEV_ARTIFACT_CONTENT = json.dumps(
    {
        "summary": f"implemented the thing; note {_SEEDED_KV}",
        "changed_files": [],
        "tests_added": [],
    }
)

# A real, hermetic, always-exits-0 command (no shell, no network) with the
# pattern-only credential as a trailing, never-interpreted argv element --
# the command genuinely runs and the gate genuinely PASSes regardless.
_GATE_COMMAND = shlex.join(
    [sys.executable, "-c", "import sys; sys.exit(0)", _SEEDED_GHP_PATTERN]
)

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
_WORKERS: dict[str, str] = {
    "BA": "fake",
    "ARCHITECTURE": "fake",
    "DEVELOPMENT": "claude-code",
    "QA": "fake",
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


def _write_seeded_tree(root: Path, *, gate_command: str) -> Path:
    """A real git-backed ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` tree:
    ``DEVELOPMENT`` is the one role assigned the real ``claude-code`` worker,
    ``repository.github_owner``/``github_repo`` are set (``start_run`` refuses
    a ``github:`` locator without them), the quality gate has one
    seeded-carrying, always-passing command, and ``publishing.create_pr`` is
    true so the publish step genuinely runs."""
    (root / ".dark-factory/roles").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory/instructions").mkdir(parents=True, exist_ok=True)
    commands_yaml = json.dumps([gate_command])
    (root / ".dark-factory.yaml").write_text(
        "version: 1\n"
        "repository:\n"
        f"  base_branch: {_BASE_BRANCH}\n"
        f"  github_owner: {_OWNER}\n"
        f"  github_repo: {_REPO}\n"
        "workflow:\n  roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]\n"
        "roles_dir: .dark-factory/roles\n"
        f"quality_gate:\n  commands: {commands_yaml}\n"
        "retry:\n"
        "  qa_developer_max_iterations: 3\n"
        "  quality_gate_max_iterations: 2\n"
        "publishing:\n  create_pr: true\n",
        encoding="utf-8",
    )
    for role, (inputs, outputs) in _DEFINITIONS.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            f"worker: {_WORKERS[role]}\n"
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
            f"# {role}\n\nScripted {role} instruction text for the SC4 sweep.\n",
            encoding="utf-8",
        )
    return make_git_repo(root)


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the intake loader's own call site,
    mirroring ``tests/unit/test_load_github.py`` / ``tests/db/test_publish_step.py``."""

    def __init__(self, client: FakeGitHubClient) -> None:
        self._client = client

    def from_settings(self, settings: object) -> FakeGitHubClient:
        return self._client


def _scripted_issue(comments: list[GitHubComment] | None = None) -> GitHubIssue:
    return GitHubIssue(
        number=_ISSUE_NUMBER,
        title=_ISSUE_TITLE,
        body=_ISSUE_BODY,
        labels=["security"],
        comments=comments or [],
    )


class _SeededFakeWorker(CodingWorker):
    """``BA``/``ARCHITECTURE``/``QA`` in one worker: ``BA`` pauses once with a
    seeded question and resumes with a seeded-carrying summary;
    ``ARCHITECTURE`` and ``QA`` complete normally -- ``ARCHITECTURE``'s own
    ``design.md`` carries a seeded literal in its *artifact file content*,
    the sink this plan's own fix (``scrub_artifact_text_in_place``) exists
    to catch. ``DEVELOPMENT`` is driven by a real :class:`ClaudeCodeWorker`
    instead, registered separately."""

    def __init__(self, run_root_path: Path) -> None:
        self._run_root = run_root_path

    def execute(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        if role == "BA":
            return WorkerResult(
                status=WorkerResultStatus.NEEDS_INPUT,
                summary="BA needs a decision before analysis can complete",
                questions=[_SEEDED_QUESTION],
            )
        return self._complete(role)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._complete(getattr(context, "role", None))

    def _complete(self, role: str | None) -> WorkerResult:
        assert role in _ROLE_FILES, role
        refs: list[ArtifactRef] = []
        for filename, content in _ROLE_FILES[role].items():
            path, digest = write_artifact_text(self._run_root, role, filename, content)
            refs.append(ArtifactRef(type=filename, path=path, checksum=digest))
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=_ROLE_SUMMARIES[role],
            worker_session_id=f"fake-{role.lower()}-sc7",
            artifacts=refs,
        )

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(ArtifactReference).where(ArtifactReference.run_id.in_(ids))
            )
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _whole_table_sweep_text(session: Session) -> str:
    """Serialise every text-bearing column of all five owned tables -- the
    whole tables, not just this run's rows (mirrors
    ``tests/integration/test_secret_redaction_e2e.py``'s ``_sweep_all_three_tables``,
    widened to the five tables that now exist)."""
    chunks: list[str] = []
    for run in session.scalars(sa.select(Run)):
        chunks.append(json.dumps(run.normalized_task))
        chunks.append(run.source_ref or "")
        chunks.append(json.dumps(run.workflow))
    for role_exec in session.scalars(sa.select(RoleExecution)):
        chunks.append(json.dumps(role_exec.result))
        chunks.append(json.dumps(role_exec.error))
        chunks.append(role_exec.worker_session_id or "")
    for event in session.scalars(sa.select(RunEvent)):
        chunks.append(json.dumps(event.payload))
        chunks.append(event.type)
    for interaction in session.scalars(sa.select(HumanInteraction)):
        chunks.append(interaction.question)
        chunks.append(interaction.answer or "")
    for artifact in session.scalars(sa.select(ArtifactReference)):
        chunks.append(json.dumps(artifact.artifact_metadata))
        chunks.append(artifact.path)
        chunks.append(artifact.type)
    return "\n".join(chunks)


@dataclass(frozen=True)
class _SweptRun:
    """Every text this plan's seven D-08 sinks plus the whole-table backstop
    produce for one driven-to-``COMPLETED`` run, collected once."""

    run_id: UUID
    repo_root: Path
    comment_body: str
    question_text: str
    answer_text: str
    log_text: str
    whole_table_text: str
    role_blob_text: str
    event_payload_text: str
    design_md_text: str
    implementation_summary_text: str
    quality_gate_text: str
    pr_number: int | None
    pr_url: str | None
    create_comment_calls: int
    create_pull_request_calls: int
    redactor: Callable[[Any], Any]


@pytest.fixture
def seeded_pipeline_run(
    tmp_path: Path,
    engine: Engine,
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> _SweptRun:
    """Drive one ``github:``-sourced run, seeded with six credential literals,
    through intake, a human pause and resume, a quality gate, and a published
    pull request -- then collect every sink's text once, for every test in
    this module to assert against."""
    # Presence-then-absence (T-01-35): every seeded literal genuinely entered
    # the pipeline -- assert it here, against the literal inputs this fixture
    # is about to hand to production code, before any absence assertion runs.
    assert _SEEDED_DB_URL in _ISSUE_BODY
    assert _SEEDED_GITHUB_TOKEN in _ISSUE_BODY
    assert _SEEDED_GHP_PATTERN in _SEEDED_QUESTION
    assert _SEEDED_KV in _SEEDED_QUESTION
    assert _SEEDED_ANTHROPIC_KEY in _SEEDED_ANSWER
    assert _SEEDED_GITHUB_TOKEN in _ROLE_SUMMARIES["BA"]
    assert _SEEDED_DB_URL_DIRECT in _ARCHITECTURE_FILES["design.md"]
    assert _SEEDED_GHP_PATTERN in _DEV_RESULT_TEXT
    assert _SEEDED_ANTHROPIC_KEY in _DEV_RESULT_TEXT
    assert _SEEDED_KV in _DEV_ARTIFACT_CONTENT
    assert _SEEDED_GHP_PATTERN in _GATE_COMMAND

    fake_settings = Settings(
        _env_file=None,
        database_url=_SEEDED_DB_URL,
        database_url_direct=_SEEDED_DB_URL_DIRECT,
        github_token=_SEEDED_GITHUB_TOKEN,
        anthropic_api_key=_SEEDED_ANTHROPIC_KEY,
    )
    # Every call site that redacts a sink this test seeds resolves its own
    # module-level `get_settings` name -- `persistence.engine`'s is
    # deliberately left untouched so the production reads below still reach
    # the real database this test's own fixtures are bound to.
    for module in (
        mutations_module,
        runner_module,
        df_logging,
        claude_code_module,
        cli_runtime_module,
    ):
        monkeypatch.setattr(module, "get_settings", lambda: fake_settings)

    root = _write_seeded_tree(tmp_path / "repo", gate_command=_GATE_COMMAND)
    # ClaudeCodeWorker's own `resolve_dirs` computes the worktree as a sibling
    # of the *process's* cwd -- correct in production, where the CLI is
    # invoked from the repo root, but this in-process drive needs the same
    # equivalence made explicit (mirrors `tests/unit/test_claude_code_worker.py`'s
    # own `repo_dir` fixture).
    monkeypatch.chdir(root)

    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    monkeypatch.setattr(loaders, "get_settings", lambda: object())
    monkeypatch.setattr(loaders, "GitHubClient", _StubClientFactory(fake_intake_client))

    snapshot = load_effective_config(root)

    fake_dir = root.parent / "sc7-fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_DEV_STDOUT_PAYLOAD,
        run_root_writes={
            "artifacts/DEVELOPMENT/implementation_summary.json": _DEV_ARTIFACT_CONTENT
        },
    )
    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{fake_dir}{os.pathsep}{existing_path}")

    fake_client = FakeGitHubClient(
        issue=_scripted_issue(),
        pull_request=GitHubPullRequest(
            number=707, url="https://example.invalid/pr/707"
        ),
    )

    with real_log_sink() as buffer:
        run_id = start_run(
            f"github:{_ISSUE_NUMBER}",
            session_factory=real_session_factory,
            snapshot=snapshot,
        )
        cleanup_runs.append(run_id)

        working_branch = working_branch_name(run_id)
        work_dir = ensure_worktree(
            root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
        )
        run_dir = run_root(work_dir, run_id)

        registry = WorkerRegistry()
        registry.register("fake", lambda: _SeededFakeWorker(run_dir))
        registry.register("claude-code", ClaudeCodeWorker)

        first = drive(
            run_id,
            session_factory=real_session_factory,
            registry=registry,
            repo_root=root,
            github_client_factory=lambda: fake_client,
        )
        assert first is RunStatus.WAITING_HUMAN, (
            "BA's scripted NEEDS_INPUT must pause the run before any other role runs"
        )

        submit_answer(run_id, _SEEDED_ANSWER, session_factory=real_session_factory)

        final = drive(
            run_id,
            session_factory=real_session_factory,
            registry=registry,
            repo_root=root,
            github_client_factory=lambda: fake_client,
        )
        assert final is RunStatus.COMPLETED

        # Actively exercise the log-redaction path with every seeded
        # credential *shape* at once, through the real configured structlog
        # chain -- the bare password substrings are deliberately excluded
        # here: they are only ever forbidden as embedded fragments of their
        # own URL/key-value shape (the shape a pattern or a known value
        # actually matches), never as a standalone token nothing plants
        # anywhere in the real pipeline either.
        structlog.get_logger("sc7").info(
            "sc7-sweep-marker",
            everything=" ".join(
                (
                    _SEEDED_DB_URL,
                    _SEEDED_DB_URL_DIRECT,
                    _SEEDED_GITHUB_TOKEN,
                    _SEEDED_ANTHROPIC_KEY,
                    _SEEDED_GHP_PATTERN,
                    _SEEDED_KV,
                )
            ),
        )
        log_text = buffer.getvalue()

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        working_branch_final = run_row.working_branch
        pr_number = run_row.pr_number
        pr_url = run_row.pr_url

        interaction = session.scalar(
            sa.select(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )
        assert interaction is not None
        question_text = interaction.question
        answer_text = interaction.answer or ""

        execs = list(
            session.scalars(
                sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
            )
        )
        role_blob_text = "\n".join(
            str(execution.result) + "\n" + str(execution.error) for execution in execs
        )

        events_rows = list(
            session.scalars(
                sa.select(RunEvent)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        event_payload_text = "\n".join(json.dumps(e.payload) for e in events_rows)

        whole_table_text = _whole_table_sweep_text(session)

    assert working_branch_final is not None, "a COMPLETED run always has one"
    design_md_text = run_artifact_text(
        root, run_id, working_branch_final, "artifacts/ARCHITECTURE/design.md"
    )
    implementation_summary_text = run_artifact_text(
        root,
        run_id,
        working_branch_final,
        "artifacts/DEVELOPMENT/implementation_summary.json",
    )
    quality_gate_text = run_artifact_text(
        root, run_id, working_branch_final, "verification/quality_gate.json"
    )

    create_comment_calls = [c for c in fake_client.calls if c[0] == "create_comment"]
    create_pr_calls = [c for c in fake_client.calls if c[0] == "create_pull_request"]
    assert len(create_comment_calls) == 1
    assert len(create_pr_calls) == 1
    comment_body = str(create_comment_calls[0][1]["body"])

    redactor = functools.partial(
        redact, known_secrets=fake_settings.known_secret_values()
    )

    return _SweptRun(
        run_id=run_id,
        repo_root=root,
        comment_body=comment_body,
        question_text=question_text,
        answer_text=answer_text,
        log_text=log_text,
        whole_table_text=whole_table_text,
        role_blob_text=role_blob_text,
        event_payload_text=event_payload_text,
        design_md_text=design_md_text,
        implementation_summary_text=implementation_summary_text,
        quality_gate_text=quality_gate_text,
        pr_number=pr_number,
        pr_url=pr_url,
        create_comment_calls=len(create_comment_calls),
        create_pull_request_calls=len(create_pr_calls),
        redactor=redactor,
    )


# --------------------------------------------------------------------------- #
# The proof itself: every seeded literal, absent from every sink; the
# [redacted: marker present in at least four of them; the run's terminal
# state and persisted PR identifiers proving the publish sink was populated.
# --------------------------------------------------------------------------- #


def test_full_pipeline_leaves_zero_leaked_secrets_with_presence_and_marker_proof(
    seeded_pipeline_run: _SweptRun,
) -> None:
    run = seeded_pipeline_run

    sinks: dict[str, str] = {
        "artifacts/ARCHITECTURE/design.md (git-committed, raw)": run.design_md_text,
        "artifacts/DEVELOPMENT/implementation_summary.json (git-committed, raw)": (
            run.implementation_summary_text
        ),
        "run_events.payload": run.event_payload_text,
        "role_executions.result/error": run.role_blob_text,
        "human_interactions.question": run.question_text,
        "human_interactions.answer": run.answer_text,
        "the recorded GitHub create_comment body": run.comment_body,
        "the captured structlog output": run.log_text,
        "verification/quality_gate.json (git-committed, raw)": run.quality_gate_text,
    }

    for sink_name, text in sinks.items():
        for literal in _FORBIDDEN_LITERALS:
            assert literal not in text, f"{literal!r} survived into {sink_name}"

    for literal in _FORBIDDEN_LITERALS:
        assert literal not in run.whole_table_text, (
            f"{literal!r} survived the whole-table sweep across runs / "
            "role_executions / run_events / human_interactions / artifacts"
        )

    marker_sinks = (
        run.event_payload_text,
        run.role_blob_text,
        run.comment_body,
        run.question_text,
        run.design_md_text,
        run.quality_gate_text,
    )
    marker_hits = sum(1 for text in marker_sinks if "[redacted:" in text)
    assert marker_hits >= 4, (
        f"expected the [redacted: marker present in at least 4 sinks -- "
        f"a sweep that passes because nothing was ever written would not "
        f"show this; found it in only {marker_hits}"
    )

    # Terminal state: the publish sink was provably populated, not merely
    # absent of secrets because the run never got that far.
    assert run.pr_number is not None
    assert run.pr_url is not None
    assert run.create_comment_calls == 1
    assert run.create_pull_request_calls == 1


# --------------------------------------------------------------------------- #
# This phase's own four new CLI surfaces -- status, runs, events, artifacts
# --show -- swept through their production read-and-render paths, in process.
# --------------------------------------------------------------------------- #


def test_phase_12_cli_surfaces_are_swept_for_the_same_secrets(
    seeded_pipeline_run: _SweptRun,
) -> None:
    run = seeded_pipeline_run

    view = read_status(run.run_id)
    detail = read_run_detail(run.run_id)
    events = read_events(run.run_id)
    assert view.working_branch is not None
    gate = read_quality_gate(run.repo_root, run.run_id, view.working_branch)
    report = RunReport(run=view, detail=detail, quality_gate=gate, events=events)

    report_text = render_run_report(report, redactor=run.redactor)
    report_json = report.as_json(redactor=run.redactor)
    runs_table_text = render_runs_table(read_run_list(), redactor=run.redactor)
    events_text = render_events_text(events, redactor=run.redactor)
    events_json = render_events_json(events, redactor=run.redactor)
    shown_design_md = run.redactor(run.design_md_text)

    surfaces: dict[str, str] = {
        "status (text)": report_text,
        "status (--json)": report_json,
        "runs": runs_table_text,
        "events (text)": events_text,
        "events (--json)": events_json,
        "artifacts --show (design.md)": str(shown_design_md),
    }
    for surface_name, text in surfaces.items():
        for literal in _FORBIDDEN_LITERALS:
            assert literal not in text, f"{literal!r} survived into {surface_name}"


# --------------------------------------------------------------------------- #
# Non-vacuity devices that need no driven run at all.
# --------------------------------------------------------------------------- #


def test_at_least_five_seeded_constants_split_between_configured_and_pattern_only() -> (
    None
):
    settings = Settings(
        _env_file=None,
        database_url=_SEEDED_DB_URL,
        database_url_direct=_SEEDED_DB_URL_DIRECT,
        github_token=_SEEDED_GITHUB_TOKEN,
        anthropic_api_key=_SEEDED_ANTHROPIC_KEY,
    )
    known = settings.known_secret_values()
    configured = [literal for literal in _FORBIDDEN_LITERALS if literal in known]
    pattern_only = [literal for literal in _FORBIDDEN_LITERALS if literal not in known]

    assert len(_FORBIDDEN_LITERALS) >= 5
    assert len(configured) >= 3
    assert len(pattern_only) >= 2
    # The load-bearing exact-value-only proof: this shape matches none of the
    # compiled D-15 patterns, so only known-value substitution can catch it.
    assert _SEEDED_ANTHROPIC_KEY in known


def test_this_module_never_calls_redact_directly() -> None:
    """A unit test of the redaction function proves that function works and
    proves nothing about whether a call site actually calls it -- precisely
    how the clarification-comment gap (plan 12-03) survived two phases while
    the function itself stayed correct and well-tested throughout. The one
    permitted use of its bare name in this module is passing it, unapplied,
    to ``functools.partial`` -- the construction ``cli.py``'s own
    ``_redactor()`` uses -- never a direct call.

    The forbidden substring is built from two literals concatenated at
    runtime, never written contiguously in this module's own source, so this
    very assertion does not itself trip the check it performs -- the plan's
    own acceptance criterion probes this module's source exactly as written
    on disk, not a string this function happens to construct in memory.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = "redact" + "("
    assert forbidden not in source
