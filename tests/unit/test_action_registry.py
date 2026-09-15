"""Unit coverage for ActionRegistry, the five built-ins, and ActionContext (Plan 03-01 Task 1, CFG-04)."""

import uuid
from typing import Literal

import pytest
from pydantic import ValidationError

from dark_factory.actions import (
    ActionContext,
    ActionRegistry,
    UnknownActionError,
    default_registry,
)

pytestmark = pytest.mark.unit

_BUILTIN_NAMES = (
    "prepare_role_context",
    "ensure_clean_worktree",
    "collect_diff",
    "store_role_artifacts",
    "collect_test_results",
)


def _context(phase: Literal["before", "after"] = "before") -> ActionContext:
    return ActionContext(
        run_id=uuid.uuid4(),
        role="BA",
        worker="fake",
        attempt=1,
        phase=phase,
        task={"kind": "text"},
        answer=None,
        role_definition={"name": "BA", "worker": "fake"},
        worktree="/tmp/dark-factory-runs/fake-run",
        run_root="/tmp/dark-factory-runs/fake-run/.dark-factory/runs/fake-run",
        base_branch="main",
        working_branch="dark-factory/run-fake-run",
    )


def test_collect_diff_is_a_noop_with_no_branch_identity() -> None:
    """05-03 (D-10): ``collect_diff`` is real since plan 05-03, but it still
    no-ops -- writing nothing, calling no git subprocess -- for a context
    whose ``base_branch``/``working_branch`` are both ``None``: a legacy run
    predating persisted branch identity has nothing to diff, and a hook is
    not the place to fail a run for that gap."""
    fn = default_registry.get("collect_diff")
    assert callable(fn)
    ctx = _context(phase="after").model_copy(
        update={"base_branch": None, "working_branch": None}
    )
    assert fn(ctx) is None


def test_unknown_action_name_raises_and_is_not_a_member() -> None:
    with pytest.raises(UnknownActionError):
        default_registry.get("nope")
    assert "nope" not in default_registry


def test_all_five_builtins_are_registered() -> None:
    for name in _BUILTIN_NAMES:
        assert name in default_registry


def test_a_newly_registered_action_is_usable_with_no_core_change() -> None:
    reg = ActionRegistry()

    def custom(ctx: ActionContext) -> None:
        return None

    assert "custom" not in reg
    reg.register("custom", custom)
    assert "custom" in reg
    assert reg.get("custom") is custom


def test_action_context_rejects_an_unknown_constructor_key() -> None:
    with pytest.raises(ValidationError):
        ActionContext(
            run_id=uuid.uuid4(),
            role="BA",
            worker="fake",
            attempt=1,
            phase="before",
            task={},
            answer=None,
            role_definition={},
            worktree="/tmp/dark-factory-runs/fake-run",
            run_root="/tmp/dark-factory-runs/fake-run/.dark-factory/runs/fake-run",
            base_branch="main",
            working_branch="dark-factory/run-fake-run",
            bogus="x",  # type: ignore[call-arg]
        )


def test_action_context_is_immutable() -> None:
    ctx = _context()
    with pytest.raises(ValidationError):
        ctx.role = "QA"
