"""Unit coverage for the pure transition function (ORCH-01, ORCH-05).

``transition`` needs no database and no mocks: it reads three fields off the run
state and is otherwise a pure function of ``(state, signal, pipeline)``. The
state is a tiny local stand-in here -- this test imports nothing from
``dark_factory.persistence`` and uses no database fixture.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from dark_factory.domain.signal import Signal
from dark_factory.domain.status import RunStatus
from dark_factory.orchestrator.lifecycle import IllegalTransitionError, transition
from dark_factory.workflows.pipeline import (
    Pipeline,
    RoleNode,
    pipeline_from_snapshot,
    previous_node,
)

pytestmark = pytest.mark.unit

_ONE_ROLE = Pipeline(nodes=(RoleNode(name="BA", worker="fake"),))
_TWO_ROLE = Pipeline(
    nodes=(
        RoleNode(name="BA", worker="fake"),
        RoleNode(name="ARCHITECTURE", worker="fake"),
    )
)
_SNAPSHOT_THREE = pipeline_from_snapshot(
    {
        "roles": [
            {"name": "BA", "worker": "fake"},
            {"name": "ARCHITECTURE", "worker": "fake"},
            {"name": "DEVELOPMENT", "worker": "fake"},
        ]
    }
)

_LIFECYCLE_SRC = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dark_factory"
    / "orchestrator"
    / "lifecycle.py"
)


@dataclass(frozen=True)
class _FakeState:
    """The read-only slice of run state ``transition`` consumes."""

    status: RunStatus
    current_role: str | None
    current_step: int | None = None


@pytest.mark.parametrize(
    ("status", "current_role", "current_step", "signal", "pipeline", "expected"),
    [
        (
            RunStatus.CREATED,
            None,
            None,
            Signal.ENTER,
            _ONE_ROLE,
            (RunStatus.BA, "BA", 0),
        ),
        (
            RunStatus.BA,
            "BA",
            0,
            Signal.ROLE_COMPLETED,
            _ONE_ROLE,
            (RunStatus.COMPLETED, "BA", 0),
        ),
        (
            RunStatus.BA,
            "BA",
            0,
            Signal.ROLE_FAILED,
            _ONE_ROLE,
            (RunStatus.FAILED, "BA", 0),
        ),
        (
            RunStatus.BA,
            "BA",
            0,
            Signal.ROLE_COMPLETED,
            _TWO_ROLE,
            (RunStatus.ARCHITECTURE, "ARCHITECTURE", 1),
        ),
        (
            RunStatus.BA,
            "BA",
            0,
            Signal.ROLE_NEEDS_INPUT,
            _ONE_ROLE,
            (RunStatus.WAITING_HUMAN, "BA", 0),
        ),
        (
            RunStatus.ARCHITECTURE,
            "ARCHITECTURE",
            1,
            Signal.ROLE_NEEDS_INPUT,
            _TWO_ROLE,
            (RunStatus.WAITING_HUMAN, "ARCHITECTURE", 1),
        ),
        # ROLE_BOUNCED: a mid-pipeline node moves back to the node before it.
        (
            RunStatus.ARCHITECTURE,
            "ARCHITECTURE",
            1,
            Signal.ROLE_BOUNCED,
            _SNAPSHOT_THREE,
            (RunStatus.BA, "BA", 0),
        ),
        # ROLE_BOUNCED: the last node of a multi-node pipeline moves back one.
        (
            RunStatus.DEVELOPMENT,
            "DEVELOPMENT",
            2,
            Signal.ROLE_BOUNCED,
            _SNAPSHOT_THREE,
            (RunStatus.ARCHITECTURE, "ARCHITECTURE", 1),
        ),
    ],
)
def test_legal_transitions_produce_documented_next_state(
    status: RunStatus,
    current_role: str | None,
    current_step: int | None,
    signal: Signal,
    pipeline: Pipeline,
    expected: tuple[RunStatus, str | None, int | None],
) -> None:
    state = _FakeState(status, current_role, current_step)
    assert transition(state, signal, pipeline) == expected


@pytest.mark.parametrize(
    ("status", "current_role", "signal", "pipeline"),
    [
        (RunStatus.BA, "BA", Signal.ENTER, _ONE_ROLE),
        (RunStatus.CREATED, None, Signal.ROLE_COMPLETED, _ONE_ROLE),
        (RunStatus.CREATED, None, Signal.ROLE_FAILED, _ONE_ROLE),
        (RunStatus.COMPLETED, "BA", Signal.ROLE_COMPLETED, _ONE_ROLE),
        (RunStatus.FAILED, "BA", Signal.ROLE_FAILED, _ONE_ROLE),
        (RunStatus.ARCHITECTURE, "ARCHITECTURE", Signal.ROLE_COMPLETED, _ONE_ROLE),
        # WAITING_HUMAN is a stop, not a terminal: it is reachable, but leaving
        # it is submit_answer's job, never the pure function's. Every signal
        # applied to it is illegal here.
        (RunStatus.WAITING_HUMAN, "BA", Signal.ENTER, _ONE_ROLE),
        (RunStatus.WAITING_HUMAN, "BA", Signal.ROLE_COMPLETED, _ONE_ROLE),
        (RunStatus.WAITING_HUMAN, "BA", Signal.ROLE_FAILED, _ONE_ROLE),
        (RunStatus.WAITING_HUMAN, "BA", Signal.ROLE_NEEDS_INPUT, _ONE_ROLE),
        # ROLE_BOUNCED: the pipeline's first node has no earlier role to bounce to.
        (RunStatus.BA, "BA", Signal.ROLE_BOUNCED, _SNAPSHOT_THREE),
        # ROLE_BOUNCED: a TERMINAL_STATUSES status raises on the existing
        # terminal guard, before the new arm is ever reached.
        (RunStatus.COMPLETED, "BA", Signal.ROLE_BOUNCED, _ONE_ROLE),
        (RunStatus.FAILED, "BA", Signal.ROLE_BOUNCED, _ONE_ROLE),
        # ROLE_BOUNCED: WAITING_HUMAN raises on the existing WAITING_HUMAN guard.
        (RunStatus.WAITING_HUMAN, "BA", Signal.ROLE_BOUNCED, _ONE_ROLE),
    ],
)
def test_illegal_pairs_raise(
    status: RunStatus,
    current_role: str | None,
    signal: Signal,
    pipeline: Pipeline,
) -> None:
    state = _FakeState(status, current_role, 0)
    with pytest.raises(IllegalTransitionError):
        transition(state, signal, pipeline)


@pytest.mark.parametrize(
    "signal", [Signal.ROLE_COMPLETED, Signal.ROLE_FAILED, Signal.ROLE_NEEDS_INPUT]
)
def test_transition_is_pure_and_repeatable(signal: Signal) -> None:
    state = _FakeState(RunStatus.BA, "BA", 0)
    pipeline_nodes = _ONE_ROLE.nodes

    first = transition(state, signal, _ONE_ROLE)
    second = transition(state, signal, _ONE_ROLE)

    assert first == second
    assert state == _FakeState(RunStatus.BA, "BA", 0)  # arguments unmutated
    assert _ONE_ROLE.nodes is pipeline_nodes


@pytest.mark.parametrize(
    ("current_role", "current_step", "expected"),
    [
        ("BA", 0, (RunStatus.ARCHITECTURE, "ARCHITECTURE", 1)),
        ("ARCHITECTURE", 1, (RunStatus.DEVELOPMENT, "DEVELOPMENT", 2)),
        ("DEVELOPMENT", 2, (RunStatus.COMPLETED, "DEVELOPMENT", 2)),
    ],
)
def test_snapshot_built_pipeline_walks_identically_to_a_hand_built_one(
    current_role: str,
    current_step: int,
    expected: tuple[RunStatus, str | None, int | None],
) -> None:
    """The pure transition function walks an N-node snapshot-built pipeline the
    same way it walks a hand-built ``Pipeline`` -- no role-count assumption."""
    state = _FakeState(RunStatus(current_role), current_role, current_step)
    assert transition(state, Signal.ROLE_COMPLETED, _SNAPSHOT_THREE) == expected


def test_previous_node_returns_none_for_the_first_node() -> None:
    assert previous_node(_SNAPSHOT_THREE, "BA") is None


def test_previous_node_returns_the_preceding_node_mid_pipeline() -> None:
    assert previous_node(_SNAPSHOT_THREE, "DEVELOPMENT") == RoleNode(
        name="ARCHITECTURE", worker="fake"
    )


def test_lifecycle_module_has_no_persistence_import_and_no_session() -> None:
    tree = ast.parse(_LIFECYCLE_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert not node.module.startswith("dark_factory.persistence"), node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("dark_factory.persistence")
        if isinstance(node, ast.Name):
            assert node.id != "Session"
        if isinstance(node, ast.Attribute):
            assert node.attr != "Session"
