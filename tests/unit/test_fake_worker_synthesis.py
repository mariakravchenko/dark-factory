"""G-04-1: FakeWorker's zero-config synthesis must thread ``context.inputs``
into every artifact it writes, so a criterion id originates once (the BA
role, with no ``inputs``) and survives to every downstream artifact -- never
a second independent literal that only coincidentally matches (D-05).

Everything here drives the public ``FakeWorker().execute(context)`` entry
point with a real :class:`~dark_factory.context.builder.RoleContext` (and
real :class:`~dark_factory.context.builder.ArtifactInput` entries), under
``monkeypatch.chdir(tmp_path)`` so synthesis writes into a ``tmp_path``-rooted
run tree. No database, no subprocess -- the written files are read back
through their returned ``ArtifactRef.path`` under ``run_root(tmp_path,
run_id)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from dark_factory.artifacts.paths import run_root
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.context.builder import ArtifactInput, RoleContext
from dark_factory.domain.artifacts import (
    AcceptanceCriteriaDocument,
    AcceptanceCriterion,
    ConstraintsDocument,
    ImplementationSummary,
    TestReport,
    Verdict,
)
from dark_factory.domain.worker import ArtifactRef, WorkerResultStatus
from dark_factory.workers import fake as fake_module
from dark_factory.workers.fake import FakeWorker

pytestmark = pytest.mark.unit


def _context(
    *,
    role: str,
    run_id: str,
    inputs: list[ArtifactInput] | None = None,
    outputs: list[str],
) -> RoleContext:
    return RoleContext(
        run_id=run_id,
        role=role,
        worker="fake",
        attempt=1,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="",
        inputs=list(inputs or []),
        baseline_docs={},
        examples=[],
        constraints={},
        tools=[],
        permissions={},
        outputs=list(outputs),
        artifacts_dir=f"artifacts/{role}",
    )


def _input(*, filename: str, produced_by: str, content: str) -> ArtifactInput:
    return ArtifactInput(
        filename=filename,
        produced_by=produced_by,
        path=f"artifacts/{produced_by}/{filename}",
        content=content,
    )


def _read(tmp_path: Path, run_id: str, ref: ArtifactRef) -> str:
    root = run_root(tmp_path, uuid_from(run_id))
    return read_artifact_text(root, ref.path)


def uuid_from(run_id: str) -> Any:
    from uuid import UUID

    return UUID(run_id)


def _ref(result: Any, filename: str) -> ArtifactRef:
    for artifact in result.artifacts:
        if artifact.type == filename:
            return artifact
    raise AssertionError(f"no synthesized artifact named {filename!r}")


def _acceptance_criteria_json(ids: list[str]) -> str:
    return AcceptanceCriteriaDocument(
        criteria=[
            AcceptanceCriterion(id=cid, description=f"criterion {cid}") for cid in ids
        ]
    ).model_dump_json()


# --------------------------------------------------------------------------
# Origin role (BA): empty inputs, outputs requirements.md + acceptance_criteria.json
# --------------------------------------------------------------------------


def test_origin_role_synthesizes_id_from_module_constant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    context = _context(
        role="BA",
        run_id=run_id,
        inputs=[],
        outputs=["acceptance_criteria.json", "requirements.md"],
    )

    result = FakeWorker().execute(context)

    assert result.status is WorkerResultStatus.COMPLETED
    origin_id = fake_module._ORIGIN_CRITERION_IDS[0]

    ac_content = _read(tmp_path, run_id, _ref(result, "acceptance_criteria.json"))
    ac_doc = AcceptanceCriteriaDocument.model_validate_json(ac_content)
    assert [c.id for c in ac_doc.criteria] == [origin_id]

    requirements_content = _read(tmp_path, run_id, _ref(result, "requirements.md"))
    assert f"- Criterion {origin_id} met" in requirements_content


# --------------------------------------------------------------------------
# Structural extraction (ARCHITECTURE): inputs carries acceptance_criteria.json
# --------------------------------------------------------------------------


def test_structural_extraction_carries_ids_into_design_and_constraints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    ac_content = _acceptance_criteria_json(["AC-9", "AC-10"])
    context = _context(
        role="ARCHITECTURE",
        run_id=run_id,
        inputs=[
            _input(
                filename="acceptance_criteria.json",
                produced_by="BA",
                content=ac_content,
            )
        ],
        outputs=["design.md", "constraints.json"],
    )

    result = FakeWorker().execute(context)

    design_content = _read(tmp_path, run_id, _ref(result, "design.md"))
    assert "- Criterion AC-9 met" in design_content
    assert "- Criterion AC-10 met" in design_content

    constraints_content = _read(tmp_path, run_id, _ref(result, "constraints.json"))
    constraints_doc = ConstraintsDocument.model_validate_json(constraints_content)
    descriptions = " ".join(c.description for c in constraints_doc.constraints)
    assert "AC-9" in descriptions
    assert "AC-10" in descriptions


# --------------------------------------------------------------------------
# Markdown-hop extraction (DEVELOPMENT): inputs carries design.md + constraints.json,
# deliberately NOT acceptance_criteria.json
# --------------------------------------------------------------------------


def test_markdown_hop_extraction_survives_into_implementation_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    design_content = (
        "# design.md\n\nAuto-generated placeholder content.\n\n"
        "- Criterion AC-9 met\n- Criterion AC-10 met\n"
    )
    constraints_content = '{"constraints": [{"id": "C-1", "description": "d"}]}'
    context = _context(
        role="DEVELOPMENT",
        run_id=run_id,
        inputs=[
            _input(
                filename="design.md", produced_by="ARCHITECTURE", content=design_content
            ),
            _input(
                filename="constraints.json",
                produced_by="ARCHITECTURE",
                content=constraints_content,
            ),
        ],
        outputs=["implementation_summary.json"],
    )

    result = FakeWorker().execute(context)

    summary_content = _read(
        tmp_path, run_id, _ref(result, "implementation_summary.json")
    )
    summary_doc = ImplementationSummary.model_validate_json(summary_content)
    assert "AC-9" in summary_doc.summary
    assert "AC-10" in summary_doc.summary


# --------------------------------------------------------------------------
# Derived verdict (QA): inputs carries acceptance_criteria.json + implementation_summary.json
# --------------------------------------------------------------------------


def test_derived_verdict_matches_acceptance_criteria_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    ac_content = _acceptance_criteria_json(["AC-7", "AC-8"])
    impl_content = ImplementationSummary(summary="irrelevant").model_dump_json()
    context = _context(
        role="QA",
        run_id=run_id,
        inputs=[
            _input(
                filename="acceptance_criteria.json",
                produced_by="BA",
                content=ac_content,
            ),
            _input(
                filename="implementation_summary.json",
                produced_by="DEVELOPMENT",
                content=impl_content,
            ),
        ],
        outputs=["test_report.json", "verdict.json"],
    )

    result = FakeWorker().execute(context)

    verdict_content = _read(tmp_path, run_id, _ref(result, "verdict.json"))
    verdict_doc = Verdict.model_validate_json(verdict_content)
    assert [c.criterion_id for c in verdict_doc.criteria] == ["AC-7", "AC-8"]

    report_content = _read(tmp_path, run_id, _ref(result, "test_report.json"))
    report_doc = TestReport.model_validate_json(report_content)
    case_names = " ".join(c.name for c in report_doc.cases)
    assert "AC-7" in case_names
    assert "AC-8" in case_names


# --------------------------------------------------------------------------
# Falsification / rename-follows: the derivation proof
# --------------------------------------------------------------------------


def test_renaming_origin_id_moves_every_downstream_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    monkeypatch.setattr(fake_module, "_ORIGIN_CRITERION_IDS", ("origin-not-ac-shaped",))
    run_id = str(uuid4())

    worker = FakeWorker()

    # BA -- no inputs, so the substituted origin id is the only one available.
    ba_result = worker.execute(
        _context(
            role="BA",
            run_id=run_id,
            inputs=[],
            outputs=["acceptance_criteria.json", "requirements.md"],
        )
    )
    ac_content = _read(
        tmp_path, run_id, _ref(ba_result, "acceptance_criteria.json")
    )

    # ARCHITECTURE -- structural extraction from BA's output.
    architecture_result = worker.execute(
        _context(
            role="ARCHITECTURE",
            run_id=run_id,
            inputs=[
                _input(
                    filename="acceptance_criteria.json",
                    produced_by="BA",
                    content=ac_content,
                )
            ],
            outputs=["design.md", "constraints.json"],
        )
    )
    design_content = _read(
        tmp_path, run_id, _ref(architecture_result, "design.md")
    )
    constraints_content = _read(
        tmp_path, run_id, _ref(architecture_result, "constraints.json")
    )

    # DEVELOPMENT -- textual extraction through the Markdown hop.
    development_result = worker.execute(
        _context(
            role="DEVELOPMENT",
            run_id=run_id,
            inputs=[
                _input(
                    filename="design.md",
                    produced_by="ARCHITECTURE",
                    content=design_content,
                ),
                _input(
                    filename="constraints.json",
                    produced_by="ARCHITECTURE",
                    content=constraints_content,
                ),
            ],
            outputs=["implementation_summary.json"],
        )
    )
    impl_content = _read(
        tmp_path,
        run_id,
        _ref(development_result, "implementation_summary.json"),
    )

    # QA -- structural extraction from BA's own output, D-05 alignment.
    qa_result = worker.execute(
        _context(
            role="QA",
            run_id=run_id,
            inputs=[
                _input(
                    filename="acceptance_criteria.json",
                    produced_by="BA",
                    content=ac_content,
                ),
                _input(
                    filename="implementation_summary.json",
                    produced_by="DEVELOPMENT",
                    content=impl_content,
                ),
            ],
            outputs=["test_report.json", "verdict.json"],
        )
    )
    verdict_content = _read(tmp_path, run_id, _ref(qa_result, "verdict.json"))
    verdict_doc = Verdict.model_validate_json(verdict_content)

    assert verdict_doc.criteria[0].criterion_id == "origin-not-ac-shaped"


# --------------------------------------------------------------------------
# Bounded and defensive
# --------------------------------------------------------------------------


def test_extraction_is_capped_at_the_module_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    monkeypatch.setattr(fake_module, "_MAX_CRITERION_IDS", 2)
    run_id = str(uuid4())
    ac_content = _acceptance_criteria_json(["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"])
    context = _context(
        role="ARCHITECTURE",
        run_id=run_id,
        inputs=[
            _input(
                filename="acceptance_criteria.json",
                produced_by="BA",
                content=ac_content,
            )
        ],
        outputs=["constraints.json"],
    )

    result = FakeWorker().execute(context)

    constraints_content = _read(tmp_path, run_id, _ref(result, "constraints.json"))
    constraints_doc = ConstraintsDocument.model_validate_json(constraints_content)
    assert len(constraints_doc.constraints) == 2


def test_criterion_id_with_whitespace_contributes_no_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    ac_content = _acceptance_criteria_json(["AC 1 with a space"])
    context = _context(
        role="ARCHITECTURE",
        run_id=run_id,
        inputs=[
            _input(
                filename="acceptance_criteria.json",
                produced_by="BA",
                content=ac_content,
            )
        ],
        outputs=["constraints.json"],
    )

    result = FakeWorker().execute(context)

    constraints_content = _read(tmp_path, run_id, _ref(result, "constraints.json"))
    constraints_doc = ConstraintsDocument.model_validate_json(constraints_content)
    # The whitespace-containing id was rejected, so extraction fell through to
    # the origin-id fallback -- never the raw (invalid) candidate.
    origin_id = fake_module._ORIGIN_CRITERION_IDS[0]
    assert constraints_doc.constraints[0].description.endswith(origin_id)


def test_criterion_id_exceeding_length_limit_contributes_no_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    run_id = str(uuid4())
    too_long_id = "AC-" + ("x" * 65)
    ac_content = _acceptance_criteria_json([too_long_id])
    context = _context(
        role="ARCHITECTURE",
        run_id=run_id,
        inputs=[
            _input(
                filename="acceptance_criteria.json",
                produced_by="BA",
                content=ac_content,
            )
        ],
        outputs=["constraints.json"],
    )

    result = FakeWorker().execute(context)

    constraints_content = _read(tmp_path, run_id, _ref(result, "constraints.json"))
    constraints_doc = ConstraintsDocument.model_validate_json(constraints_content)
    origin_id = fake_module._ORIGIN_CRITERION_IDS[0]
    assert constraints_doc.constraints[0].description.endswith(origin_id)
    assert too_long_id not in constraints_content


def test_execute_none_still_returns_completed_with_no_artifacts() -> None:
    result = FakeWorker().execute(None)
    assert result.status is WorkerResultStatus.COMPLETED
    assert result.artifacts == []


def test_context_with_no_inputs_attribute_still_returns_completed() -> None:
    class _NoInputsContext:
        role = "BA"
        run_id = str(uuid4())
        outputs: list[str] = []

    result = FakeWorker().execute(_NoInputsContext())
    assert result.status is WorkerResultStatus.COMPLETED
    assert result.artifacts == []


# --------------------------------------------------------------------------
# D-08: extraction never branches on role
# --------------------------------------------------------------------------


def test_extraction_result_is_independent_of_role_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DARK_FACTORY_FAKE_SCRIPT", raising=False)
    ac_content = _acceptance_criteria_json(["AC-42"])

    for role in ("ARCHITECTURE", "QA", "SOME-OTHER-ROLE"):
        run_id = str(uuid4())
        context = _context(
            role=role,
            run_id=run_id,
            inputs=[
                _input(
                    filename="acceptance_criteria.json",
                    produced_by="BA",
                    content=ac_content,
                )
            ],
            outputs=["constraints.json"],
        )
        result = FakeWorker().execute(context)
        constraints_content = _read(
            tmp_path, run_id, _ref(result, "constraints.json")
        )
        constraints_doc = ConstraintsDocument.model_validate_json(constraints_content)
        assert "AC-42" in constraints_doc.constraints[0].description
