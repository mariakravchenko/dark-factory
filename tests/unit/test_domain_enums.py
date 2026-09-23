"""Unit coverage for the domain enums: RunStatus, Signal, EventType (Plan 01-02 Task 1)."""

import enum
from types import SimpleNamespace

import pytest

from dark_factory.domain.signal import Signal, signal_from_result
from dark_factory.domain.status import STOP_STATUSES, TERMINAL_STATUSES, RunStatus
from dark_factory.domain.worker import WorkerResultStatus
from dark_factory.events.catalog import EventType

pytestmark = pytest.mark.unit

_EXPECTED_STATUS_MEMBERS = {
    "CREATED",
    "BA",
    "ARCHITECTURE",
    "DEVELOPMENT",
    "QA",
    "VERIFYING",
    "PUBLISHING",
    "COMPLETED",
    "WAITING_HUMAN",
    "FAILED",
}


def test_run_status_has_exactly_ten_members() -> None:
    assert len(list(RunStatus)) == 10
    assert {m.name for m in RunStatus} == _EXPECTED_STATUS_MEMBERS


def test_run_status_value_equals_name_for_every_member() -> None:
    assert all(member.value == member.name for member in RunStatus)


def test_run_status_is_str_enum() -> None:
    assert issubclass(RunStatus, enum.StrEnum)
    assert RunStatus.BA == "BA"


def test_terminal_statuses_is_completed_and_failed() -> None:
    expected = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})
    assert expected == TERMINAL_STATUSES
    assert isinstance(TERMINAL_STATUSES, frozenset)


def test_stop_statuses_adds_waiting_human_to_the_terminal_set() -> None:
    expected = frozenset(
        {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_HUMAN}
    )
    assert expected == STOP_STATUSES
    assert isinstance(STOP_STATUSES, frozenset)


def test_waiting_human_is_a_stop_but_never_a_terminal() -> None:
    assert RunStatus.WAITING_HUMAN in STOP_STATUSES
    assert RunStatus.WAITING_HUMAN not in TERMINAL_STATUSES


def test_terminal_statuses_is_a_strict_subset_of_stop_statuses() -> None:
    assert TERMINAL_STATUSES < STOP_STATUSES
    assert STOP_STATUSES is not TERMINAL_STATUSES


def test_signal_has_the_four_phase_one_members() -> None:
    assert {m.name for m in Signal} == {
        "ENTER",
        "ROLE_COMPLETED",
        "ROLE_FAILED",
        "ROLE_NEEDS_INPUT",
    }


@pytest.mark.parametrize(
    ("result_status", "expected_signal"),
    [
        (WorkerResultStatus.COMPLETED, Signal.ROLE_COMPLETED),
        (WorkerResultStatus.FAILED, Signal.ROLE_FAILED),
        (WorkerResultStatus.NEEDS_INPUT, Signal.ROLE_NEEDS_INPUT),
    ],
)
def test_signal_from_result_maps_worker_result_status(
    result_status: WorkerResultStatus, expected_signal: Signal
) -> None:
    result = SimpleNamespace(status=result_status)
    assert signal_from_result(result) is expected_signal  # type: ignore[arg-type]


def test_signal_from_result_reads_only_the_status_field() -> None:
    noisy = SimpleNamespace(
        status=WorkerResultStatus.COMPLETED,
        summary="ignore me",
        questions=["not looked at"],
        metadata={"anything": "goes"},
    )
    quiet = SimpleNamespace(status=WorkerResultStatus.COMPLETED)
    assert signal_from_result(noisy) is signal_from_result(quiet)  # type: ignore[arg-type]


def test_event_type_contains_the_six_phase_one_members() -> None:
    required = {
        "RUN_CREATED",
        "ROLE_STARTED",
        "ROLE_COMPLETED",
        "ROLE_FAILED",
        "RUN_COMPLETED",
        "RUN_FAILED",
    }
    assert required <= {m.name for m in EventType}


def test_event_type_has_exactly_fifteen_members_with_the_phase_two_five_six_and_nine_types() -> (
    None
):
    # Exactly the six Phase 1 members plus the four Phase 2 writes plus the one
    # Phase 5 write plus the one Phase 6 write plus the three Phase 9 writes --
    # the exact count is what stops a future contributor from pre-declaring the
    # Phase 12 members, which would advertise transitions that are never
    # emitted.
    assert len(list(EventType)) == 15
    phase_two = {
        "QUESTION_CREATED",
        "RUN_PAUSED",
        "HUMAN_ANSWER_RECEIVED",
        "RUN_RESUMED",
    }
    assert phase_two <= {m.name for m in EventType}
    phase_five = {"WIP_COMMIT_CREATED"}
    assert phase_five <= {m.name for m in EventType}
    phase_six = {"CAPABILITY_DENIED"}
    assert phase_six <= {m.name for m in EventType}
    phase_nine = {
        "QUALITY_GATE_STARTED",
        "QUALITY_GATE_PASSED",
        "QUALITY_GATE_FAILED",
    }
    assert phase_nine <= {m.name for m in EventType}


def test_event_type_value_equals_name_for_every_member() -> None:
    assert all(member.value == member.name for member in EventType)
    assert issubclass(EventType, enum.StrEnum)
