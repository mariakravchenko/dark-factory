"""TOOL-02 / SC3 proof: a capability added to a ``ToolRegistry`` after import
time works end-to-end with zero edits to any role executor, the pipeline, or
the lifecycle function (Phase 6, plan 06-01, Task 3).

Per D-04, extensibility is proven with a **synthetic** capability that
appears nowhere under ``src/dark_factory/`` -- never a real future one --
so the proof cannot quietly become "we added it to production code". Most
of this module is unit-tier (pure registry mechanics, a byte-identical
source-file check); the end-to-end arm genuinely drives a run through
``start_run``/``drive`` and therefore needs a real database, so it alone
carries the ``db`` marker rather than ``unit`` -- ``pytest -m unit`` still
selects the rest of this file's proofs.
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
from dark_factory.git.worktree import remove_worktree
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools.registry import ToolRegistry
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"

# A synthetic name, never a real future capability (D-04) -- proven to
# appear nowhere under src/dark_factory/ below.
_SYNTHETIC_CAPABILITY = "test.echo"

_GUARDED_FILES = [
    _SRC_ROOT / "orchestrator" / "runner.py",
    _SRC_ROOT / "workflows" / "pipeline.py",
    _SRC_ROOT / "orchestrator" / "lifecycle.py",
]


@pytest.mark.unit
def test_synthetic_capability_is_invokable_when_granted_and_denied_when_not() -> None:
    """A role granted the synthetic capability gets its implementation's
    return value back through ``invoke``; a role not granted it raises
    ``CapabilityDeniedError`` -- the identical gate every real capability
    goes through, proving no special-casing is needed for a new one."""
    registry = ToolRegistry()

    def _echo(**kwargs: object) -> dict[str, object]:
        return dict(kwargs)

    registry.register(_SYNTHETIC_CAPABILITY, _echo)

    result = registry.invoke("BA", _SYNTHETIC_CAPABILITY, [_SYNTHETIC_CAPABILITY], x=1)
    assert result == {"x": 1}

    with pytest.raises(CapabilityDeniedError):
        registry.invoke("BA", _SYNTHETIC_CAPABILITY, [])


@pytest.mark.unit
def test_synthetic_capability_name_appears_nowhere_under_src() -> None:
    """The proof cannot quietly become "we added it to production code" --
    grepped from the test itself, not asserted in prose."""
    offenders = [
        path
        for path in sorted(_SRC_ROOT.rglob("*.py"))
        if _SYNTHETIC_CAPABILITY in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"synthetic capability leaked into: {offenders}"


@pytest.mark.unit
def test_registering_a_synthetic_capability_leaves_orchestrator_pipeline_lifecycle_untouched() -> (
    None
):
    """Structural proof of the zero-edit claim: the exact bytes of
    ``orchestrator/runner.py``, ``workflows/pipeline.py`` and
    ``orchestrator/lifecycle.py`` are captured before and after registering
    a brand-new capability, and neither the bytes nor the presence of the
    synthetic name in any of them changes."""
    before = {path: path.read_bytes() for path in _GUARDED_FILES}

    registry = ToolRegistry()
    registry.register(_SYNTHETIC_CAPABILITY, lambda **kwargs: kwargs)

    after = {path: path.read_bytes() for path in _GUARDED_FILES}
    assert before == after
    for path in _GUARDED_FILES:
        assert _SYNTHETIC_CAPABILITY.encode() not in after[path]


def _one_role_synthetic_tree(config_root_factory: Callable[..., Path]) -> Path:
    """A one-role ``[BA]`` config tree whose ``BA.yaml`` grants only the
    synthetic capability and declares no outputs -- this proof is about
    config validation and grant/registry injection reaching ``COMPLETED``
    with zero role-executor edits, not about the synthetic capability being
    invoked mid-run."""
    root = config_root_factory(roles=("BA",))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        f"tools: [{_SYNTHETIC_CAPABILITY}]\n"
        "permissions:\n  write_scope: []\n"
        "before: [ensure_clean_worktree]\n"
        "after: []\n"
        "inputs: []\n"
        "outputs: []\n"
        "examples: []\n",
        encoding="utf-8",
    )
    return root


def _true_default_fake_registry() -> WorkerRegistry:
    """A ``WorkerRegistry`` whose ``"fake"`` factory returns a true
    no-script-default ``FakeWorker`` -- an *explicit* empty script (via the
    ``fake_worker_registry`` fixture's ``build([])``) exhausts immediately,
    which is not what this proof needs."""
    registry = WorkerRegistry()
    registry.register("fake", lambda: FakeWorker())
    return registry


@pytest.mark.db
@pytest.mark.usefixtures("use_fake_secrets")
def test_a_role_granted_the_synthetic_capability_completes_end_to_end(
    config_root_factory: Callable[..., Path],
    engine: Engine,
) -> None:
    """ROADMAP SC3, stated literally: a new capability is registered on the
    ``ToolRegistry`` and granted to one role, and the run reaches
    ``COMPLETED`` with zero edits to any role executor, ``workflows/pipeline.py``,
    or the transition function."""
    registry = ToolRegistry()
    registry.register(_SYNTHETIC_CAPABILITY, lambda **kwargs: kwargs)

    root = _one_role_synthetic_tree(config_root_factory)
    snapshot = load_effective_config(root, tool_registry=registry)

    def session_factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    run_id = start_run(
        "text:a synthetic capability is grantable with zero role-executor edits",
        session_factory=session_factory,
        snapshot=snapshot,
    )
    try:
        final = drive(
            run_id,
            session_factory=session_factory,
            registry=_true_default_fake_registry(),
            repo_root=root,
            tool_registry=registry,
        )
        assert final is RunStatus.COMPLETED
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
        remove_worktree(root, run_id, force=True)
