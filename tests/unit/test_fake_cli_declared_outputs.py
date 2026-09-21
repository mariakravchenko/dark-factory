"""Unit coverage for 08-04 Task 1: promoted public helpers in
``dark_factory.workers.fake`` (:func:`synthesize_artifact_content`,
:func:`criterion_ids_from_text`) and the shared test-support fake-CLI
generator's ``declared_outputs`` mode (``tests/support/fake_cli.py``).

No live ``copilot`` binary and no live Copilot credential are ever used:
every declared-outputs test drives a fake ``copilot`` executable written by
``tests/support/fake_copilot_cli.py`` through the real
:class:`~dark_factory.workers.copilot.CopilotWorker`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.artifacts import (
    AcceptanceCriteriaDocument,
    AcceptanceCriterion,
    ConstraintsDocument,
    Verdict,
)
from dark_factory.workers import fake
from dark_factory.workers.cli_runtime import build_prompt
from dark_factory.workers.fake import criterion_ids_from_text, synthesize_artifact_content
from tests.support.fake_copilot_cli import fake_copilot_env, write_fake_copilot

pytestmark = pytest.mark.unit

_RUN_ID = "8f14e45f-ceea-467e-adde-3fb5b2c8de9c"


def _architecture_context(*, outputs: list[str]) -> RoleContext:
    return RoleContext(
        run_id=_RUN_ID,
        role="ARCHITECTURE",
        worker="copilot",
        attempt=1,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="Design the feature.",
        inputs=[],
        baseline_docs={},
        examples=[],
        constraints={},
        tools=[],
        permissions={},
        outputs=outputs,
        artifacts_dir="artifacts/ARCHITECTURE",
    )


@pytest.fixture
def repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo-shaped ``tmp_path`` subdirectory; ``monkeypatch.chdir()``s into
    it so the ``dark-factory-runs`` sibling-of-``cwd`` formula
    (``cli_runtime.resolve_dirs``) resolves under ``tmp_path``, not the real
    repo -- mirrors ``tests/unit/test_claude_code_worker.py::repo_dir``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    return repo


def _run_root_for(tmp_path: Path) -> Path:
    return tmp_path / "dark-factory-runs" / _RUN_ID / ".dark-factory" / "runs" / _RUN_ID


# --------------------------------------------------------------------------- #
# criterion_ids_from_text / synthesize_artifact_content: public promotion
# --------------------------------------------------------------------------- #


def test_synthesize_artifact_content_and_criterion_ids_from_text_are_public() -> None:
    assert "synthesize_artifact_content" in fake.__all__
    assert "criterion_ids_from_text" in fake.__all__
    assert callable(synthesize_artifact_content)
    assert callable(criterion_ids_from_text)


def test_criterion_ids_from_text_returns_ids_from_a_structural_document() -> None:
    blob = AcceptanceCriteriaDocument(
        criteria=[
            AcceptanceCriterion(id="AC-7", description="the first thing works"),
            AcceptanceCriterion(id="AC-8", description="the second thing works"),
        ]
    ).model_dump_json()

    assert criterion_ids_from_text(blob) == ("AC-7", "AC-8")


def test_criterion_ids_from_text_falls_back_to_textual_carrier_lines() -> None:
    assert criterion_ids_from_text("- Criterion AC-9 met") == ("AC-9",)


def test_criterion_ids_from_text_empty_string_matches_extract_criterion_ids_default() -> (
    None
):
    assert criterion_ids_from_text("") == fake._extract_criterion_ids(None)


def test_synthesize_artifact_content_verdict_json_validates_against_verdict_model() -> (
    None
):
    content = synthesize_artifact_content("verdict.json", ("AC-1",))
    Verdict.model_validate(json.loads(content))


def test_synthesize_artifact_content_markdown_fallback_carries_ids() -> None:
    content = synthesize_artifact_content("design.md", ("AC-1", "AC-2"))
    assert "- Criterion AC-1 met" in content
    assert "- Criterion AC-2 met" in content


def test_fake_worker_own_behaviour_is_unchanged() -> None:
    """FakeWorker's true no-script default still resolves through the
    (now-public) synthesis helper with identical output -- a regression
    guard alongside the full ``test_fake_worker_synthesis.py`` suite this
    plan's ``<verify>`` block also re-runs."""
    from dark_factory.domain.worker import WorkerResultStatus

    class _Context:
        role = "ARCHITECTURE"
        run_id = _RUN_ID
        outputs: list[str] = []
        inputs: list[object] = []

    result = fake.FakeWorker().execute(_Context())
    assert result.status == WorkerResultStatus.COMPLETED


# --------------------------------------------------------------------------- #
# tests/support/fake_cli.py's declared_outputs mode, via the real
# CopilotWorker so the generated script is exercised exactly as a real
# CLI-adapter spawn would exercise it (cwd, argv shape, run-root globbing).
# --------------------------------------------------------------------------- #


def test_declared_outputs_writes_both_files_with_synthesized_content(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(
        fake_dir, stdout_payload="design complete", declared_outputs=True
    )

    context = _architecture_context(outputs=["design.md", "constraints.json"])
    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(context)

    assert result.status.value == "COMPLETED"

    artifacts_dir = _run_root_for(tmp_path) / "artifacts" / "ARCHITECTURE"
    design_path = artifacts_dir / "design.md"
    constraints_path = artifacts_dir / "constraints.json"
    assert design_path.is_file()
    assert constraints_path.is_file()

    expected_ids = criterion_ids_from_text(build_prompt(context))
    assert design_path.read_text("utf-8") == synthesize_artifact_content(
        "design.md", expected_ids
    )
    for criterion_id in expected_ids:
        assert f"Criterion {criterion_id} met" in design_path.read_text("utf-8")

    ConstraintsDocument.model_validate_json(constraints_path.read_text("utf-8"))


def test_fake_without_declared_outputs_writes_no_artifact_file(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="design complete")

    context = _architecture_context(outputs=["design.md", "constraints.json"])
    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(context)

    assert result.status.value == "COMPLETED"
    artifacts_root = _run_root_for(tmp_path) / "artifacts"
    assert not artifacts_root.exists() or not any(artifacts_root.rglob("*"))


def test_declared_outputs_with_no_expected_outputs_heading_writes_nothing_and_exits_zero(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(
        fake_dir, stdout_payload="design complete", declared_outputs=True
    )

    # No declared outputs at all -> build_prompt emits no "## Expected
    # outputs" heading, so the generated script's declared-outputs step
    # finds no prompt element to parse.
    context = _architecture_context(outputs=[])
    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(context)

    assert result.status.value == "COMPLETED"
    artifacts_root = _run_root_for(tmp_path) / "artifacts"
    assert not artifacts_root.exists() or not any(artifacts_root.rglob("*"))
