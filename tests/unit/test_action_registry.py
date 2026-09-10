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
    )


def test_builtin_action_resolves_to_a_callable_noop() -> None:
    fn = default_registry.get("collect_diff")
    assert callable(fn)
    assert fn(_context()) is None


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
            bogus="x",  # type: ignore[call-arg]
        )


def test_action_context_is_immutable() -> None:
    ctx = _context()
    with pytest.raises(ValidationError):
        ctx.role = "QA"
