"""CFG-04 runtime: ``_run_current_role`` invokes a role's configured before/after
actions through the ``ActionRegistry`` around the worker call.

The five built-ins are no-ops in Phase 3, so the observable effect of a hook is
"the named callable ran, in order". Each test here registers a *recording*
action on a fresh :class:`ActionRegistry`, injects it through the
``action_registry`` keyword seam that ``advance`` / ``drive`` now accept, and
asserts:

* the ``before`` names run, then the worker, then the ``after`` names
  (``test_before_then_worker_then_after``);
* a two-role snapshot whose roles name the *same* action produces a structurally
  identical :class:`ActionContext` for both -- projecting out only the role name,
  worker and role-definition -- so there is no per-role branch on the hook path
  (``test_two_roles_get_an_identical_context_remainder``);
* a brand-new action, registered and named from a role's ``after`` list, runs
  with no change to ``orchestrator/runner.py`` -- proving the pipeline accepts
  new actions from configuration alone (``test_a_newly_registered_action_runs``).

Real commits against real PostgreSQL; ``cleanup_runs`` deletes every fixture row
at teardown (the ``tests/db/test_pause_mechanism_generic.py`` idiom).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.actions.context import ActionContext
from dark_factory.actions.registry import ActionRegistry
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.orchestrator.runner import advance, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_SESSION_ID = "fake-role-hooks-001"


class _RecordingWorker(CodingWorker):
    """A worker that appends a marker to a shared list on every call and returns a
    fixed COMPLETED result. One ``advance`` step is exactly one worker call, so no
    script cursor is needed."""

    def __init__(self, log: list[str], marker: str = "worker") -> None:
        self._log = log
        self._marker = marker

    def _record(self) -> WorkerResult:
        self._log.append(self._marker)
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="recording worker done",
            worker_session_id=_SESSION_ID,
        )

    def execute(self, context: object) -> WorkerResult:
        return self._record()

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._record()

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )


def _worker_registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


def _recording_actions(log: list[str], names: tuple[str, ...]) -> ActionRegistry:
    registry = ActionRegistry()
    for name in names:
        registry.register(name, lambda _ctx, _name=name: log.append(_name))
    return registry


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
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def test_before_then_worker_then_after(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    log: list[str] = []
    worker = _RecordingWorker(log)
    actions = _recording_actions(log, ("rec_before", "rec_after"))
    snapshot: dict[str, Any] = {
        "roles": [
            {
                "name": "BA",
                "worker": "fake",
                "before": ["rec_before"],
                "after": ["rec_after"],
            }
        ]
    }

    run_id = start_run(
        "text:before then worker then after",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    assert (
        advance(
            run_id,
            session_factory=real_session_factory,
            registry=_worker_registry(worker),
            action_registry=actions,
        )
        is RunStatus.BA
    )
    assert (
        advance(
            run_id,
            session_factory=real_session_factory,
            registry=_worker_registry(worker),
            action_registry=actions,
        )
        is RunStatus.COMPLETED
    )

    assert log == ["rec_before", "worker", "rec_after"]


def test_two_roles_get_an_identical_context_remainder(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    seen: list[ActionContext] = []
    actions = ActionRegistry()
    actions.register("rec", lambda ctx: seen.append(ctx))
    worker = _RecordingWorker([])
    snapshot: dict[str, Any] = {
        "roles": [
            {"name": "BA", "worker": "fake", "before": ["rec"], "after": []},
            {"name": "ARCHITECTURE", "worker": "fake", "before": ["rec"], "after": []},
        ]
    }

    run_id = start_run(
        "text:two roles same hook",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    status = RunStatus.CREATED
    for _ in range(4):
        status = advance(
            run_id,
            session_factory=real_session_factory,
            registry=_worker_registry(worker),
            action_registry=actions,
        )
        if status is RunStatus.COMPLETED:
            break
    assert status is RunStatus.COMPLETED

    assert [c.role for c in seen] == ["BA", "ARCHITECTURE"]
    projected = {"role", "worker", "role_definition"}
    remainders = [
        {k: v for k, v in c.model_dump().items() if k not in projected} for c in seen
    ]
    assert remainders[0] == remainders[1]
    # the only fields that legitimately differ are the projected ones
    assert seen[0].role != seen[1].role
    assert seen[0].phase == seen[1].phase == "before"


def test_a_newly_registered_action_runs(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    """A brand-new action name, registered on the injected registry and referenced
    only from a role's ``after`` list, runs with zero change to the orchestrator."""
    fired: list[str] = []
    actions = ActionRegistry()
    actions.register("custom_hook", lambda ctx: fired.append(ctx.role))
    worker = _RecordingWorker([])
    snapshot: dict[str, Any] = {
        "roles": [
            {"name": "BA", "worker": "fake", "before": [], "after": ["custom_hook"]}
        ]
    }

    run_id = start_run(
        "text:brand new action from config",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    status = RunStatus.CREATED
    for _ in range(3):
        status = advance(
            run_id,
            session_factory=real_session_factory,
            registry=_worker_registry(worker),
            action_registry=actions,
        )
        if status is RunStatus.COMPLETED:
            break

    assert status is RunStatus.COMPLETED
    assert fired == ["BA"]


def test_legacy_bare_string_snapshot_invokes_no_hooks(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    """A legacy ``{"roles": ["BA"]}`` snapshot resolves to empty before/after
    lists -- the hook loops are a no-op, and a run still drives to COMPLETED."""
    calls: list[str] = []
    worker = _RecordingWorker(calls)
    actions = ActionRegistry()  # empty: any hook lookup would raise

    run_id = start_run(
        "text:legacy snapshot no hooks",
        session_factory=real_session_factory,
        snapshot={"roles": ["BA"]},
    )
    cleanup_runs.append(run_id)

    status = RunStatus.CREATED
    for _ in range(3):
        status = advance(
            run_id,
            session_factory=real_session_factory,
            registry=_worker_registry(worker),
            action_registry=actions,
        )
        if status is RunStatus.COMPLETED:
            break

    assert status is RunStatus.COMPLETED
    assert calls == ["worker"]
