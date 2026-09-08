"""Unit coverage for NormalizedTask and the WorkerResult contract (Plan 01-02 Task 2)."""

import pytest
from pydantic import ValidationError

from dark_factory.domain.task import NormalizedTask
from dark_factory.domain.worker import (
    ArtifactRef,
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)

pytestmark = pytest.mark.unit

# A body carrying a CJK ideograph, an emoji and a combining accent.
_MULTIBYTE_BODY = "文字 \U0001f680 café"


def test_worker_result_defaults_are_empty_lists_never_none() -> None:
    result = WorkerResult(status=WorkerResultStatus.COMPLETED)
    assert result.questions == []
    assert result.artifacts == []
    assert result.changed_files == []
    assert result.summary == ""
    assert result.worker_session_id is None
    assert result.metadata == {}
    assert result.error is None


def test_worker_result_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        WorkerResult(status=WorkerResultStatus.COMPLETED, nonsense="x")  # type: ignore[call-arg]


def test_worker_result_is_frozen() -> None:
    result = WorkerResult(status=WorkerResultStatus.COMPLETED)
    with pytest.raises(ValidationError):
        result.summary = "mutated"  # type: ignore[misc]


def test_worker_result_needs_input_with_empty_questions_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        WorkerResult(status=WorkerResultStatus.NEEDS_INPUT, questions=[])
    assert "questions" in str(excinfo.value)


def test_worker_result_needs_input_with_a_question_validates() -> None:
    result = WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT, questions=["which database?"]
    )
    assert result.questions == ["which database?"]


def test_worker_result_changed_files_order_survives_round_trip() -> None:
    original = WorkerResult(
        status=WorkerResultStatus.COMPLETED,
        changed_files=["z.py", "a.py", "m.py"],
        artifacts=[
            ArtifactRef(type="report", path="b.md"),
            ArtifactRef(type="report", path="a.md"),
        ],
    )
    restored = WorkerResult.model_validate(original.model_dump())
    assert restored.changed_files == ["z.py", "a.py", "m.py"]
    assert [a.path for a in restored.artifacts] == ["b.md", "a.md"]


def test_worker_capabilities_is_frozen_and_forbids_extras() -> None:
    caps = WorkerCapabilities()
    assert caps.native_resume is False
    assert caps.structured_output is True
    with pytest.raises(ValidationError):
        caps.native_resume = True  # type: ignore[misc]
    with pytest.raises(ValidationError):
        WorkerCapabilities(bogus=1)  # type: ignore[call-arg]


def test_normalized_task_required_and_optional_fields() -> None:
    task = NormalizedTask(source_kind="text", body="do the thing")
    assert task.source_kind == "text"
    assert task.body == "do the thing"
    assert task.source_ref is None
    assert task.title == ""
    assert task.metadata == {}


def test_normalized_task_exposes_the_expected_field_names() -> None:
    assert set(NormalizedTask.model_fields) == {
        "source_kind",
        "source_ref",
        "title",
        "body",
        "metadata",
    }


def test_normalized_task_multibyte_body_survives_json_round_trip() -> None:
    task = NormalizedTask(source_kind="text", body=_MULTIBYTE_BODY, title="t")
    restored = NormalizedTask.model_validate_json(task.model_dump_json())
    assert restored == task
    assert restored.body == _MULTIBYTE_BODY


def test_normalized_task_forbids_extras() -> None:
    with pytest.raises(ValidationError):
        NormalizedTask(source_kind="text", body="x", surprise=1)  # type: ignore[call-arg]
