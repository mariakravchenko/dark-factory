"""Unit coverage for the five D-10 machine-artifact models (Phase 4, 04-03 Task 1).

One named test per bullet in the task's ``<behavior>`` block: ``Verdict``'s
internal PASS/FAIL consistency and stable-id duplicate rejection, the shared
minimum-length / no-duplicate-id rules on ``AcceptanceCriteriaDocument``, the
frozen/extra-forbid boundary discipline on the three plain-container models,
and the ``MACHINE_ARTIFACT_MODELS`` dispatch table shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from dark_factory.artifacts.validation import MACHINE_ARTIFACT_MODELS
from dark_factory.domain.artifacts import (
    AcceptanceCriteriaDocument,
    ChangedFile,
    ConstraintsDocument,
    ImplementationSummary,
    TestReport,
    Verdict,
)
from dark_factory.domain.status import IssueSeverity, VerdictStatus

pytestmark = pytest.mark.unit

_ONE_PASS_CRITERION = {
    "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
    "issues": [],
    "status": "PASS",
}


def test_verdict_accepts_one_pass_criterion_no_issues_declared_pass() -> None:
    verdict = Verdict.model_validate(_ONE_PASS_CRITERION)
    assert verdict.status is VerdictStatus.PASS
    assert verdict.computed_status is VerdictStatus.PASS


def test_verdict_rejects_empty_criteria_list_naming_the_field() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Verdict.model_validate({"criteria": [], "issues": [], "status": "FAIL"})
    assert "criteria" in str(excinfo.value)


def test_verdict_rejects_duplicate_criterion_id_naming_the_id() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Verdict.model_validate(
            {
                "criteria": [
                    {"criterion_id": "AC-1", "result": "PASS", "notes": ""},
                    {"criterion_id": "AC-1", "result": "FAIL", "notes": ""},
                ],
                "issues": [],
                "status": "FAIL",
            }
        )
    assert "AC-1" in str(excinfo.value)


def test_verdict_rejects_declared_pass_with_a_fail_criterion() -> None:
    with pytest.raises(ValidationError):
        Verdict.model_validate(
            {
                "criteria": [{"criterion_id": "AC-1", "result": "FAIL", "notes": ""}],
                "issues": [],
                "status": "PASS",
            }
        )


def test_verdict_rejects_declared_pass_with_a_blocking_issue() -> None:
    with pytest.raises(ValidationError):
        Verdict.model_validate(
            {
                "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
                "issues": [{"severity": "blocking", "description": "broken build"}],
                "status": "PASS",
            }
        )


def test_verdict_accepts_declared_fail_with_a_fail_criterion() -> None:
    verdict = Verdict.model_validate(
        {
            "criteria": [{"criterion_id": "AC-1", "result": "FAIL", "notes": ""}],
            "issues": [],
            "status": "FAIL",
        }
    )
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.computed_status is VerdictStatus.FAIL


def test_verdict_accepts_declared_fail_with_only_a_blocking_issue() -> None:
    verdict = Verdict.model_validate(
        {
            "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
            "issues": [{"severity": "blocking", "description": "broken build"}],
            "status": "FAIL",
        }
    )
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.computed_status is VerdictStatus.FAIL
    assert verdict.issues[0].severity is IssueSeverity.blocking


def test_verdict_computed_status_is_order_independent_but_criteria_order_survives() -> (
    None
):
    forward = Verdict.model_validate(
        {
            "criteria": [
                {"criterion_id": "AC-1", "result": "PASS", "notes": ""},
                {"criterion_id": "AC-2", "result": "FAIL", "notes": ""},
            ],
            "issues": [],
            "status": "FAIL",
        }
    )
    reversed_doc = Verdict.model_validate(
        {
            "criteria": [
                {"criterion_id": "AC-2", "result": "FAIL", "notes": ""},
                {"criterion_id": "AC-1", "result": "PASS", "notes": ""},
            ],
            "issues": [],
            "status": "FAIL",
        }
    )
    assert forward.computed_status == reversed_doc.computed_status
    assert [c.criterion_id for c in forward.criteria] == ["AC-1", "AC-2"]
    assert [c.criterion_id for c in reversed_doc.criteria] == ["AC-2", "AC-1"]


def test_acceptance_criteria_document_rejects_empty_criteria_list() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCriteriaDocument.model_validate({"criteria": []})


def test_acceptance_criteria_document_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AcceptanceCriteriaDocument.model_validate(
            {
                "criteria": [
                    {"id": "AC-1", "description": "first"},
                    {"id": "AC-1", "description": "second"},
                ]
            }
        )
    assert "AC-1" in str(excinfo.value)


def test_acceptance_criteria_document_accepts_one_criterion() -> None:
    doc = AcceptanceCriteriaDocument.model_validate(
        {"criteria": [{"id": "AC-1", "description": "the thing works"}]}
    )
    assert doc.criteria[0].id == "AC-1"


@pytest.mark.parametrize(
    ("model", "valid_payload"),
    [
        (
            ConstraintsDocument,
            {"constraints": [{"id": "C-1", "description": "no new migration"}]},
        ),
        (ImplementationSummary, {"summary": "did the thing"}),
        (
            TestReport,
            {"cases": [{"name": "case one", "result": "PASS", "detail": ""}]},
        ),
    ],
)
def test_container_model_rejects_unknown_extra_key(
    model: type[BaseModel], valid_payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**valid_payload, "surprise_field": "nope"})


@pytest.mark.parametrize(
    ("model", "valid_payload"),
    [
        (
            ConstraintsDocument,
            {"constraints": [{"id": "C-1", "description": "no new migration"}]},
        ),
        (ImplementationSummary, {"summary": "did the thing"}),
        (
            TestReport,
            {"cases": [{"name": "case one", "result": "PASS", "detail": ""}]},
        ),
    ],
)
def test_container_model_raises_on_attribute_assignment_after_validation(
    model: type[BaseModel], valid_payload: dict[str, Any]
) -> None:
    instance = model.model_validate(valid_payload)
    with pytest.raises(ValidationError):
        setattr(instance, next(iter(valid_payload)), "mutated")


def test_implementation_summary_changed_files_and_tests_added_default_empty() -> None:
    summary = ImplementationSummary.model_validate({"summary": "did the thing"})
    assert summary.changed_files == []
    assert summary.tests_added == []


def test_implementation_summary_accepts_changed_files() -> None:
    summary = ImplementationSummary.model_validate(
        {
            "summary": "did the thing",
            "changed_files": [{"path": "a.py", "change": "modified"}],
            "tests_added": ["tests/test_a.py"],
        }
    )
    assert summary.changed_files == [ChangedFile(path="a.py", change="modified")]
    assert summary.tests_added == ["tests/test_a.py"]


def test_constraints_document_rejects_empty_constraints_list() -> None:
    with pytest.raises(ValidationError):
        ConstraintsDocument.model_validate({"constraints": []})


def test_test_report_rejects_empty_cases_list() -> None:
    with pytest.raises(ValidationError):
        TestReport.model_validate({"cases": []})


def test_machine_artifact_models_has_exactly_five_keys() -> None:
    assert set(MACHINE_ARTIFACT_MODELS) == {
        "acceptance_criteria.json",
        "constraints.json",
        "implementation_summary.json",
        "test_report.json",
        "verdict.json",
    }
    assert len(MACHINE_ARTIFACT_MODELS) == 5


def test_machine_artifact_models_names_no_markdown_file() -> None:
    assert not any(name.endswith(".md") for name in MACHINE_ARTIFACT_MODELS)
