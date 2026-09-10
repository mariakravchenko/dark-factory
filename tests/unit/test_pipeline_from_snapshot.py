"""Unit coverage for pipeline_from_snapshot: both snapshot shapes and an N-node
transition() walk with no role-count assumption (Plan 03-01 Task 3, ORCH-02).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dark_factory.domain.signal import Signal
from dark_factory.domain.status import RunStatus
from dark_factory.orchestrator.lifecycle import transition
from dark_factory.workflows.pipeline import Pipeline, pipeline_from_snapshot

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _FakeState:
    status: RunStatus
    current_role: str | None
    current_step: int | None = None


def test_new_dict_shape_yields_ordered_nodes() -> None:
    pipeline = pipeline_from_snapshot(
        {"roles": [{"name": "BA", "worker": "fake"}, {"name": "QA", "worker": "fake"}]}
    )
    assert isinstance(pipeline, Pipeline)
    assert [n.name for n in pipeline.nodes] == ["BA", "QA"]
    assert [n.worker for n in pipeline.nodes] == ["fake", "fake"]


def test_legacy_bare_string_shape_defaults_worker_to_fake() -> None:
    pipeline = pipeline_from_snapshot({"roles": ["BA"]})
    assert len(pipeline.nodes) == 1
    assert pipeline.nodes[0].name == "BA"
    assert pipeline.nodes[0].worker == "fake"


def test_empty_roles_yields_a_zero_node_pipeline() -> None:
    # "at least one role" is the loader's rule, not the builder's.
    assert pipeline_from_snapshot({"roles": []}).nodes == ()


def test_missing_roles_key_raises_key_error() -> None:
    with pytest.raises(KeyError):
        pipeline_from_snapshot({})


def test_three_node_snapshot_drives_a_full_transition_walk() -> None:
    pipeline = pipeline_from_snapshot(
        {
            "roles": [
                {"name": "BA", "worker": "fake"},
                {"name": "ARCHITECTURE", "worker": "fake"},
                {"name": "DEVELOPMENT", "worker": "fake"},
            ]
        }
    )

    created = _FakeState(RunStatus.CREATED, None, None)
    assert transition(created, Signal.ENTER, pipeline) == (RunStatus.BA, "BA", 0)

    at_ba = _FakeState(RunStatus.BA, "BA", 0)
    assert transition(at_ba, Signal.ROLE_COMPLETED, pipeline) == (
        RunStatus.ARCHITECTURE,
        "ARCHITECTURE",
        1,
    )

    at_arch = _FakeState(RunStatus.ARCHITECTURE, "ARCHITECTURE", 1)
    assert transition(at_arch, Signal.ROLE_COMPLETED, pipeline) == (
        RunStatus.DEVELOPMENT,
        "DEVELOPMENT",
        2,
    )

    at_dev = _FakeState(RunStatus.DEVELOPMENT, "DEVELOPMENT", 2)
    assert transition(at_dev, Signal.ROLE_COMPLETED, pipeline) == (
        RunStatus.COMPLETED,
        "DEVELOPMENT",
        2,
    )
