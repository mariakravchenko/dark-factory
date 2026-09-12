"""``RoleContext`` + ``build_role_context`` -- the CTX-01..CTX-04 assembly.

**The CTX-02 invariant, in this module's own words:** context assembly is a
lookup over a fixed, small set of *named paths* -- a role's declared
``inputs`` (resolved through the persisted snapshot's ``outputs`` lists, never
a live directory read), the three D-02 baseline filenames, and a role's
declared ``examples`` -- and nothing here ever lists, globs or walks the
repository tree. ``tests/unit/test_no_tree_walk.py`` enforces this
mechanically over this package and ``dark_factory.artifacts``.

``build_role_context`` replaces the Phase 1 ``_build_context`` dict-building
body in ``orchestrator/runner.py``: it keeps every field that function
produced (``run_id``, ``role``, ``worker``, ``attempt``, ``task``, ``answer``)
and adds resolved prior-role artifact content, the baseline docs, and
examples. **No field on :class:`RoleContext` carries a prior role's**
``WorkerResult`` **-- summary, questions, metadata, or anything else** -- that
is the ORCH-04 boundary this whole phase exists to enforce: a role hands off
through artifact files only.

A role's ``role_def`` (as returned by ``orchestrator/runner._role_definition``)
may be the legacy Phase 1 / Phase 2 bare-string shape -- ``{"name": ..., "before":
[], "after": []}``, with no ``worker`` / ``instruction_text`` / ``tools`` /
``permissions`` / ``inputs`` / ``outputs`` / ``examples`` keys -- so every
lookup here is defensive (``.get(..., default)``), matching the same default
(``worker="fake"``) that :func:`~dark_factory.workflows.pipeline.pipeline_from_snapshot`
already applies to a bare-string entry.

``RoleContext.outputs`` carries the role's declared ``outputs`` filenames
verbatim (no content, no schema) -- the same list
:func:`~dark_factory.artifacts.validation.collect_role_artifacts` validates
a worker's reported artifacts against after the call returns. A worker
adapter may read it to know what it is expected to produce;
:class:`~dark_factory.workers.fake.FakeWorker`'s true zero-config default
uses it to synthesize schema-valid files for a pipeline whose roles declare
machine-artifact outputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.artifacts import ArtifactContractError, MissingArtifactContentError
from dark_factory.artifacts.paths import run_root
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.persistence.models import ArtifactReference, RoleExecution
from dark_factory.persistence.repositories import RunState

__all__ = [
    "BASELINE_DOC_FILENAMES",
    "ArtifactInput",
    "ExampleDoc",
    "RoleContext",
    "build_role_context",
]

BASELINE_DOC_FILENAMES: tuple[str, ...] = ("README.md", "AGENTS.md", "CLAUDE.md")
"""The fixed D-02 baseline -- not repeated per role, read the same way for
every role in the pipeline."""

# Mirrors config/loader.py's _MAX_INSTRUCTION_BYTES idiom for the same class of
# repo-controlled text read.
_MAX_SUPPLEMENTARY_DOC_BYTES = 64 * 1024


class ArtifactInput(BaseModel):
    """One resolved entry of a role's declared ``inputs`` -- a prior role's
    artifact file content, never its ``WorkerResult`` prose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    produced_by: str
    path: str
    content: str


class ExampleDoc(BaseModel):
    """One of a role's declared ``examples`` -- inert text, never imported,
    evaluated or executed (CTX-03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    content: str


class RoleContext(BaseModel):
    """Everything a worker adapter receives for one role attempt (CTX-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    role: str
    worker: str
    attempt: int
    task: dict[str, Any]
    answer: str | None
    instructions: str
    inputs: list[ArtifactInput] = Field(default_factory=list)
    baseline_docs: dict[str, str] = Field(default_factory=dict)
    examples: list[ExampleDoc] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    permissions: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    artifacts_dir: str


def _latest_completed_execution(
    session: Session, run_id: UUID, role: str
) -> RoleExecution | None:
    """The single most-recent **COMPLETED** ``role_executions`` row for
    ``(run_id, role)``, or ``None``.

    ``uq_role_exec_attempt`` makes ``attempt`` a total order within one role,
    so ``ORDER BY attempt DESC LIMIT 1`` needs no further tiebreaker. The
    ``status == "COMPLETED"`` filter is what makes CTX-04 hold *by
    construction* -- a failed or in-flight attempt is never a candidate --
    rather than by filtering the result afterwards.
    """
    return session.scalar(
        select(RoleExecution)
        .where(
            RoleExecution.run_id == run_id,
            RoleExecution.role == role,
            RoleExecution.status == "COMPLETED",
        )
        .order_by(RoleExecution.attempt.desc())
        .limit(1)
    )


def _producing_role(state: RunState, filename: str) -> str:
    """Resolve ``filename`` to the name of the role whose snapshot entry
    declares it as an ``outputs`` filename.

    Scans ``state.workflow["roles"]`` in memory -- the same data-lookup-by-
    value idiom as ``orchestrator/runner._role_definition`` -- never a query
    and never a branch on which role it is. A legacy bare-string entry
    declares no outputs and is skipped.
    """
    for entry in state.workflow["roles"]:
        if isinstance(entry, str):
            continue
        if filename in entry.get("outputs", []):
            name = entry.get("name")
            if isinstance(name, str):
                return name
    raise ArtifactContractError(
        f"no role in the run snapshot declares {filename!r} as an output"
    )


def _resolve_input(
    session: Session,
    repo_root: Path,
    run_id: UUID,
    state: RunState,
    filename: str,
) -> ArtifactInput:
    """Resolve one declared ``inputs`` filename to its producing role's
    artifact content (D-03)."""
    producing_role = _producing_role(state, filename)

    latest = _latest_completed_execution(session, run_id, producing_role)
    if latest is None:
        raise MissingArtifactContentError(
            f"input {filename!r} declares producing role {producing_role!r}, "
            f"which has no COMPLETED attempt for run {run_id}"
        )

    artifact_row = session.scalar(
        select(ArtifactReference).where(
            ArtifactReference.role_execution_id == latest.id,
            ArtifactReference.type == filename,
        )
    )
    if artifact_row is None:
        raise MissingArtifactContentError(
            f"input {filename!r}: role {producing_role!r}'s completed attempt "
            f"has no matching artifacts row"
        )

    content = read_artifact_text(run_root(repo_root, run_id), artifact_row.path)
    return ArtifactInput(
        filename=filename,
        produced_by=producing_role,
        path=artifact_row.path,
        content=content,
    )


def _read_supplementary_doc(resolved_root: Path, relative: str) -> str | None:
    """Read ``relative`` under ``resolved_root``, optionally and size-capped.

    Returns ``None`` when the path is absent or escapes the root -- callers
    skip it silently, exactly the ``config/loader.py`` ``is_relative_to`` /
    size-cap idiom, except a missing supplementary doc is not an error (a repo
    with no ``AGENTS.md`` must still run). A file over the cap still raises,
    matching T-04-02's "never silently truncate" rule.
    """
    from dark_factory.artifacts import ArtifactTooLargeError

    path = (resolved_root / relative).resolve()
    if not path.is_file() or not path.is_relative_to(resolved_root):
        return None
    text = path.read_text("utf-8")
    if len(text.encode("utf-8")) > _MAX_SUPPLEMENTARY_DOC_BYTES:
        raise ArtifactTooLargeError(
            f"{path}: exceeds {_MAX_SUPPLEMENTARY_DOC_BYTES} bytes"
        )
    return text


def _read_baseline_docs(resolved_root: Path) -> dict[str, str]:
    docs: dict[str, str] = {}
    for filename in BASELINE_DOC_FILENAMES:
        text = _read_supplementary_doc(resolved_root, filename)
        if text is not None:
            docs[filename] = text
    return docs


def _read_examples(resolved_root: Path, paths: list[str]) -> list[ExampleDoc]:
    examples: list[ExampleDoc] = []
    for relative in paths:
        text = _read_supplementary_doc(resolved_root, relative)
        if text is not None:
            examples.append(ExampleDoc(path=relative, content=text))
    return examples


def build_role_context(
    session: Session,
    repo_root: Path,
    run_id: UUID,
    state: RunState,
    role_def: Mapping[str, Any],
) -> RoleContext:
    """Assemble the frozen :class:`RoleContext` handed to ``worker.execute`` /
    ``worker.resume`` for the current role attempt.

    A pure read: no lock is taken and nothing is written, so two calls for the
    same run and attempt with no intervening commit return equal values
    (CTX-04, idempotency). ``role_def`` may be the legacy bare-string shape
    (see the module docstring); every field lookup below defaults exactly as
    the rest of the resume path already does for that shape.
    """
    attempt = state.latest_execution.attempt if state.latest_execution else 1
    role_name = role_def["name"]

    inputs = [
        _resolve_input(session, repo_root, run_id, state, filename)
        for filename in role_def.get("inputs", [])
    ]

    resolved_root = repo_root.resolve()
    baseline_docs = _read_baseline_docs(resolved_root)
    examples = _read_examples(resolved_root, list(role_def.get("examples", [])))

    constraints: dict[str, Any] = {}
    repository_constraints = state.workflow.get("repository")
    if repository_constraints:
        constraints["repository"] = repository_constraints
    quality_gate_constraints = state.workflow.get("quality_gate")
    if quality_gate_constraints:
        constraints["quality_gate"] = quality_gate_constraints

    return RoleContext(
        run_id=str(run_id),
        role=role_name,
        worker=role_def.get("worker", "fake"),
        attempt=attempt,
        task=state.normalized_task.model_dump(mode="json"),
        answer=state.pending_answer,
        instructions=role_def.get("instruction_text", ""),
        inputs=inputs,
        baseline_docs=baseline_docs,
        examples=examples,
        constraints=constraints,
        tools=list(role_def.get("tools", [])),
        permissions=dict(role_def.get("permissions", {})),
        outputs=list(role_def.get("outputs", [])),
        artifacts_dir=str(Path("artifacts") / role_name),
    )
