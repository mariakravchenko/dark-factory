"""LOOP-04 adjacency regression test (permanent, db-tier).

The pipeline's only role is also its terminal role, so a FAIL verdict on that
role has no earlier role to bounce to. No other test in this suite drives a
one-role pipeline whose only role fails -- ``09-VERIFICATION.md`` classified
this truth as code-correct-by-inspection but behaviourally unproven, and
``STATE.md``'s Blocker entry recorded that the only behavioural evidence it
was ever proven lived in an untracked, ``git clean``-vulnerable throwaway
script (``tests/db/test_manual_check_loop04_adjacency.py``, since removed).
This file is that evidence, promoted to a committed, permanently-collected
test (Phase 10, gap-closure plan 10-08, gap G-10-1).

Two things this test asserts that a naive read of the transition table would
get wrong:

* The adjacency reason lands on the ``ROLE_FAILED`` event's ``error`` field
  and on the persisted ``role_executions.error`` column -- **not** on the
  ``RUN_FAILED`` payload. ``_bounce_or_fail`` (``runner.py``) returns
  ``Signal.ROLE_FAILED`` with the literal reason string
  ``"no_earlier_role_to_bounce_to"`` in ``outcome["error"]``; that string
  flows into the ``ROLE_FAILED`` event payload and the role-execution row's
  ``error`` column unconditionally.
* The ``RUN_FAILED`` payload carries **no** exhaustion counter for this
  reason. ``_EXHAUSTION_REASON_TO_COUNTER`` maps only the two counter-exhaustion
  reasons (``qa_developer_max_iterations_exhausted`` /
  ``quality_gate_max_iterations_exhausted``); the adjacency reason is not one
  of them. ``runner.py``'s own comment on the lookup miss states the payload
  "stays ``{"role": node.name}``" -- this test asserts exactly that shape, so
  a future reader cannot "fix" production to match the old, wrong
  expectation the throwaway script carried.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import QA_VERDICT_FAIL_FILES, write_role_artifacts

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

# The adjacency reason `_bounce_or_fail` returns when `bounce_target` is
# `None` -- see `src/dark_factory/orchestrator/runner.py`'s `_bounce_or_fail`
# docstring. Named here so both assertion sites below read from one source.
_ADJACENCY_REASON = "no_earlier_role_to_bounce_to"


class _FailingSoloRoleWorker(CodingWorker):
    """Writes a FAIL verdict.json for a one-role pipeline's only (terminal) role."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role is not None
        refs = write_role_artifacts(self._run_dir, role, QA_VERDICT_FAIL_FILES)
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{role} ran, verdict is FAIL",
            worker_session_id=f"fake-{role}",
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


def test_a_one_role_pipeline_fails_immediately_never_bounces(
    config_root_factory: Callable[..., Path],
    engine: Engine,
) -> None:
    """LOOP-04 (adjacency): the pipeline's only role is also its terminal
    role. Its FAIL verdict has nowhere to bounce to (previous_node returns
    None), so the run must end FAILED with the adjacency reason recorded on
    the ROLE_FAILED event and the role-execution error column, no exhaustion
    counter on RUN_FAILED, zero ROLE_BOUNCED events, and the
    qa_developer_iterations counter untouched."""
    root = config_root_factory(roles=("QA",))
    (root / ".dark-factory/roles/QA.yaml").write_text(
        "name: QA\n"
        "worker: fake\n"
        "instructions: ../instructions/qa.md\n"
        "tools: [repo.read, repo.search, artifacts.read, artifacts.write]\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: []\n"
        "outputs: [test_report.json, verdict.json]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    # `config_root_factory` (`tests/conftest.py::_write_config_tree`) already
    # writes matching `quality_gate.commands: []` and both retry caps --
    # appending a second block here would produce duplicate YAML keys that
    # resolve by last-wins, exactly the implicit-config behaviour G-10-1 was
    # caused by. Nothing in this scenario needs a different value.
    snapshot = load_effective_config(root)

    def session_factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    run_id = start_run(
        "text:one-role pipeline, QA fails immediately, nowhere to bounce",
        session_factory=session_factory,
        snapshot=snapshot,
    )
    try:
        from dark_factory.artifacts.paths import run_root
        from dark_factory.git.worktree import worktree_path

        work_dir = worktree_path(root, run_id)
        run_dir = run_root(work_dir, run_id)
        worker = _FailingSoloRoleWorker(run_dir)
        registry = WorkerRegistry()
        registry.register("fake", lambda: worker)

        final = drive(
            run_id,
            session_factory=session_factory,
            registry=registry,
            repo_root=root,
        )

        assert final is RunStatus.FAILED, (
            f"expected FAILED, got {final} -- adjacency case did not fail cleanly"
        )

        with Session(bind=engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            assert run.qa_developer_iterations == 0, (
                "counter moved despite no bounce ever occurring"
            )

            execution = session.scalars(
                sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
            ).one()
            assert execution.status == "FAILED"
            assert execution.error is not None, (
                "role-execution row has no persisted error -- the adjacency "
                "reason must be recorded there"
            )
            assert execution.error.get("error") == _ADJACENCY_REASON, (
                f"role-execution error column does not carry the adjacency "
                f"reason: {execution.error}"
            )

            events = list(
                session.scalars(
                    sa.select(RunEvent)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.seq)
                )
            )
            event_types = [e.type for e in events]
            assert "ROLE_BOUNCED" not in event_types, (
                "a ROLE_BOUNCED event was written despite there being no earlier "
                "role to bounce to"
            )

            role_failed = next((e for e in events if e.type == "ROLE_FAILED"), None)
            assert role_failed is not None, "no ROLE_FAILED event was written"
            assert role_failed.payload.get("error") == _ADJACENCY_REASON, (
                f"ROLE_FAILED event payload does not carry the adjacency "
                f"reason: {role_failed.payload}"
            )

            run_failed = next((e for e in events if e.type == "RUN_FAILED"), None)
            assert run_failed is not None, "no RUN_FAILED event was written"
            # `_EXHAUSTION_REASON_TO_COUNTER` maps only the two exhaustion
            # reasons; the adjacency reason is not one of them, so the lookup
            # in `runner.py`'s `ROLE_FAILED` arm simply misses and the
            # payload stays `{"role": node.name}` -- no `reason`, `counter`,
            # `value`, or `cap` key. This is deliberate (see `runner.py`'s
            # own comment on the lookup miss), not a gap to "fix".
            assert run_failed.payload == {"role": "QA"}, (
                f"RUN_FAILED payload carries unexpected keys for a "
                f"non-exhaustion failure reason: {run_failed.payload}"
            )
            for key in ("reason", "counter", "value", "cap"):
                assert key not in run_failed.payload, (
                    f"RUN_FAILED payload carries exhaustion key {key!r} for "
                    f"an adjacency failure, which is not an exhaustion "
                    f"reason: {run_failed.payload}"
                )
    finally:
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
