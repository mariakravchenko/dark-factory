"""SEC-01 / SC4 for this phase's new failure path: a capability denial.

ROADMAP SC4 says grep every artifact, worker prompt, persisted event payload,
structured log line and test report a run produced for a configured secret
and find nothing. Plan 03 (Phase 1) and Plan 08 (Phase 2) already proved this
for the *happy* audit surfaces -- ``run_events``, ``role_executions``, the
persisted task text, ``human_interactions``, and the real log sink. Phase 6
introduces exactly one new writer of both an ``error`` column and an event
payload: ``ToolRegistry.invoke()``'s deny-by-default gate
(``CAPABILITY_DENIED`` / ``CapabilityDeniedError``). This module is that new
writer's own sweep -- a sibling of
``tests/integration/test_secret_redaction_e2e.py``, not an extension of it,
because each phase's redaction proof should be independently readable and
this one walks a surface (the denial path) that phase does not touch.

This module additionally covers two surfaces neither Phase 1 nor Phase 2's
sweep walked at all: every file under a run's artifact tree, and the worker
prompt text assembled into ``RoleContext`` for the denied attempt -- both new
opportunities to leak once a role can be granted ``artifacts.read``/
``artifacts.write``/``repo.*``/``shell.execute``.

Per A-06-10, this sweep covers artifacts, worker prompts, persisted event
payloads, structured logs and (via the role_executions columns) test-report-
adjacent JSONB -- driven inside this test process. It does **not** cover
GitHub comments, which no phase writes production code for yet; that surface
joins the sweep in Phase 10.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import pytest
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.context.builder import RoleContext
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.git.worktree import worktree_path
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import RoleExecution, RunEvent
from dark_factory.tools import CapabilityDeniedError, default_registry
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import write_role_artifacts
from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Distinctive fake "live" configured secrets -- long enough to clear the
# eight-character floor in known_secret_values(), distinctive enough to grep
# for unambiguously. No real credential enters this test process.
# --------------------------------------------------------------------------- #

_LIVE_DB_PASSWORD = "denySUPERSECRETpw012345"
_FAKE_DB_URL = (
    f"postgresql+psycopg://denyuser:{_LIVE_DB_PASSWORD}"
    "@deny-fake-db.invalid:5432/denyfactory"
)
_FAKE_DB_URL_DIRECT = (
    f"postgresql+psycopg://denyuser:{_LIVE_DB_PASSWORD}"
    "@deny-fake-direct.invalid:5432/denyfactory"
)
_FAKE_GITHUB_TOKEN = "ghp_LIVEdenygithub00000000000000000000000000"

# The task text embeds the live configured DATABASE_URL value -- proving the
# scrub that ``create_run`` applies at persistence time is what
# ``build_role_context`` later reads back into the worker's prompt (the task
# field never reads a live directory or an un-redacted in-memory copy).
_TASK_BODY = f"a role invokes a capability it was not granted; live={_FAKE_DB_URL}"
_TASK_SOURCE = "text:" + _TASK_BODY

_ACCEPTANCE_CRITERIA = (
    '{"criteria": [{"id": "AC-1", "description": "the thing works"}]}'
)


def assert_no_known_secret(text: str, *, where: str, known: Mapping[str, str]) -> None:
    """The single definition of "clean" every sweep arm in this module goes
    through -- fails naming both the surface and which credential leaked."""
    for secret, label in known.items():
        assert secret not in text, f"known secret {label!r} leaked into {where}"


def _read_tree_text(root: Path) -> str:
    """Every file under ``root``, read as bytes and decoded permissively so a
    binary artifact cannot skip the check silently."""
    chunks: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            chunks.append(path.read_bytes().decode("utf-8", errors="replace"))
    return "\n".join(chunks)


@pytest.fixture
def capability_denial_secrets(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point every ``get_settings`` consumer on the run + log path at a
    ``Settings`` built from the distinctive fake live values above."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
    )
    from dark_factory import logging as df_logging
    from dark_factory.persistence import mutations

    monkeypatch.setattr(mutations, "get_settings", lambda: settings)
    monkeypatch.setattr(df_logging, "get_settings", lambda: settings)
    return settings


def _one_role_ba_tree(config_root_factory: Callable[..., Path], *, tools: str) -> Path:
    """A one-role ``[BA]`` config tree whose ``BA.yaml`` declares
    ``acceptance_criteria.json`` as its only output and carries ``tools``
    (a YAML flow-sequence literal, e.g. ``"[repo.read, repo.search]"``) --
    the same tree shape as ``tests/db/test_capability_denied_fails_role.py``,
    duplicated here (not imported) so this module stays independently
    readable as its own denial-path proof."""
    root = config_root_factory(roles=("BA",))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        f"tools: {tools}\n"
        "permissions:\n  write_scope: []\n"
        "before: [ensure_clean_worktree]\n"
        "after: []\n"
        "inputs: []\n"
        "outputs: [acceptance_criteria.json]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    return root


class _ContextCapturingWorker(CodingWorker):
    """A ``COMPLETED``-only worker that records every :class:`RoleContext` it
    receives (the assembled worker prompt) and writes
    ``acceptance_criteria.json`` into the precomputed run root -- mirrors
    ``tests/db/test_capability_denied_fails_role.py::_ArtifactWritingWorker``
    plus the context-capture this module's prompt-text sweep needs."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.contexts: list[RoleContext] = []

    def _record(self, context: object) -> WorkerResult:
        assert isinstance(context, RoleContext)
        self.contexts.append(context)
        refs = write_role_artifacts(
            self._run_dir,
            context.role,
            {"acceptance_criteria.json": _ACCEPTANCE_CRITERIA},
        )
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{context.role} done",
            worker_session_id=f"fake-{context.role}",
            artifacts=refs,
        )

    def execute(self, context: object) -> WorkerResult:
        return self._record(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._record(context)

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


class DeniedRun(NamedTuple):
    """Every surface this module sweeps, for one driven-to-``FAILED``,
    denied-capability run."""

    run_id: UUID
    final_status: RunStatus
    denial_payload: dict[str, str]
    event_payloads_text: str
    role_exec_result_text: str
    error_text: str
    artifact_tree_text: str
    prompt_text: str
    log_text: str


@pytest.fixture
def denied_run(
    config_root_factory: Callable[..., Path],
    advance_session_factory: Callable[[], Session],
    capability_denial_secrets: Settings,
) -> DeniedRun:
    root = _one_role_ba_tree(config_root_factory, tools="[repo.read, repo.search]")
    snapshot = load_effective_config(root)

    with real_log_sink() as buffer:
        run_id = start_run(
            _TASK_SOURCE,
            session_factory=advance_session_factory,
            snapshot=snapshot,
        )
        work_dir = worktree_path(root, run_id)
        run_dir = run_root(work_dir, run_id)
        worker = _ContextCapturingWorker(run_dir)

        final = drive(
            run_id,
            session_factory=advance_session_factory,
            registry=_registry(worker),
            repo_root=root,
        )
        # Actively exercise the log-redaction path with a line carrying every
        # secret this fixture configured -- proves the sink itself scrubs,
        # not merely that nothing happened to be logged (test_secret_
        # redaction_e2e.py's discipline).
        structlog.get_logger("capability-denial").info(
            "capability-denial-audit",
            db=_FAKE_DB_URL,
            gh=_FAKE_GITHUB_TOKEN,
        )
        log_text = buffer.getvalue()

    assert final is RunStatus.FAILED, "expected the denial to fail the run"
    assert "capability-denial-audit" in log_text, "the audit log line never arrived"

    session = advance_session_factory()
    try:
        events = list(
            session.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        )
        event_payloads_text = "\n".join(json.dumps(e.payload) for e in events)
        denial_events = [e for e in events if e.type == "CAPABILITY_DENIED"]
        assert len(denial_events) == 1, "expected exactly one CAPABILITY_DENIED event"
        denial_payload = dict(denial_events[0].payload)

        execution = session.scalars(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
        assert execution is not None
        role_exec_result_text = json.dumps(execution.result)
        error_text = json.dumps(execution.error)
    finally:
        session.close()

    artifact_tree_text = _read_tree_text(run_dir)
    prompt_text = "\n".join(
        json.dumps(context.model_dump(mode="json")) for context in worker.contexts
    )
    assert worker.contexts, "the worker never received a RoleContext to sweep"

    return DeniedRun(
        run_id=run_id,
        final_status=final,
        denial_payload=denial_payload,
        event_payloads_text=event_payloads_text,
        role_exec_result_text=role_exec_result_text,
        error_text=error_text,
        artifact_tree_text=artifact_tree_text,
        prompt_text=prompt_text,
        log_text=log_text,
    )


# --------------------------------------------------------------------------- #
# 1. The full-surface sweep.
# --------------------------------------------------------------------------- #


def test_the_full_surface_sweep_finds_no_known_secret(
    denied_run: DeniedRun, capability_denial_secrets: Settings
) -> None:
    known = capability_denial_secrets.known_secret_values()
    assert known, "the fixture configured no known secret values to sweep for"

    assert_no_known_secret(
        denied_run.artifact_tree_text, where="the run's artifact tree", known=known
    )
    assert_no_known_secret(
        denied_run.prompt_text,
        where="the assembled worker prompt (RoleContext)",
        known=known,
    )
    assert_no_known_secret(
        denied_run.event_payloads_text, where="run_events.payload", known=known
    )
    assert_no_known_secret(
        denied_run.role_exec_result_text,
        where="role_executions.result",
        known=known,
    )
    assert_no_known_secret(
        denied_run.error_text, where="role_executions.error", known=known
    )
    assert_no_known_secret(
        denied_run.log_text, where="the captured log buffer", known=known
    )


# --------------------------------------------------------------------------- #
# 2. The payload key-set equality (T-06-04).
# --------------------------------------------------------------------------- #


def test_the_capability_denied_payload_key_set_is_exactly_role_capability_reason(
    denied_run: DeniedRun,
) -> None:
    assert set(denied_run.denial_payload) == {"role", "capability", "reason"}
    assert denied_run.denial_payload["role"] == "BA"
    assert denied_run.denial_payload["capability"] == "artifacts.read"


# --------------------------------------------------------------------------- #
# 3. role_executions.error names who tried what, and nothing more (T-06-19).
# --------------------------------------------------------------------------- #


def test_role_executions_error_names_role_and_capability_with_no_secret(
    denied_run: DeniedRun, capability_denial_secrets: Settings
) -> None:
    assert "BA" in denied_run.error_text
    assert "artifacts.read" in denied_run.error_text
    assert_no_known_secret(
        denied_run.error_text,
        where="role_executions.error",
        known=capability_denial_secrets.known_secret_values(),
    )


# --------------------------------------------------------------------------- #
# 4. Control arm -- the sweep must be able to fail.
# --------------------------------------------------------------------------- #


def test_assert_no_known_secret_can_actually_fail() -> None:
    """Without this, a helper that stopped resolving ``known_secret_values()``
    would make the whole module pass by checking nothing."""
    known = {"totally-fake-known-secret-999": "test_secret"}
    with pytest.raises(AssertionError):
        assert_no_known_secret(
            "leaked value totally-fake-known-secret-999 right here",
            where="a deliberately poisoned string",
            known=known,
        )


# --------------------------------------------------------------------------- #
# 5. A denied shell.execute carries no fragment of the attempted command.
# --------------------------------------------------------------------------- #


def test_denied_shell_execute_carries_no_fragment_of_the_attempted_command() -> None:
    """The command line is the most plausible carrier of a secret into a
    denial record -- exactly why the payload shape excludes invocation
    arguments (T-06-04)."""
    secret_shaped_arg = "ghp_" + "SHOULDNOTLEAK".ljust(40, "0")
    command = ["echo", secret_shaped_arg, "--password=hunter2correct"]

    with pytest.raises(CapabilityDeniedError) as excinfo:
        default_registry.invoke(
            "BA",
            "shell.execute",
            ["repo.read"],
            command=command,
            cwd=Path("."),
            role="BA",
        )

    message = str(excinfo.value)
    assert secret_shaped_arg not in message
    assert "hunter2correct" not in message
    for part in command:
        assert part not in message


# --------------------------------------------------------------------------- #
# 6. Structural guard: `redact` is defined nowhere but redaction.py.
# --------------------------------------------------------------------------- #


def test_no_redaction_function_is_defined_outside_redaction_py() -> None:
    """SEC-01/SEC-02: a secret substituted by one pass and missed by another
    is worse than one pass everybody knows about -- the single
    ``redact()``/``scrub_known_values()`` call site is the only claim about
    coverage anyone can actually verify."""
    src_root = _REPO_ROOT / "src" / "dark_factory"
    redaction_file = src_root / "events" / "redaction.py"
    assert redaction_file.is_file()

    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        if path == redaction_file:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {
                "redact",
                "scrub_known_values",
            }:
                offenders.append(f"{path}:{node.name}")
    assert offenders == [], f"a second redaction mechanism was defined: {offenders}"
