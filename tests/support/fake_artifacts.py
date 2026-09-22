"""Test-only helper: write scripted artifact files under a run root and return
the :class:`~dark_factory.domain.worker.ArtifactRef` list to embed in that
role's scripted :class:`~dark_factory.domain.worker.WorkerResult`.

Kept in ``tests/support/``, not shipped ``src/`` (04-RESEARCH assumption A3):
an *explicit* :class:`~dark_factory.workers.fake.FakeWorker` script never
writes files itself -- a db test writes the files a scripted result *claims*
to have produced, then hands the resulting refs to the ``FakeWorker`` script,
exactly as this module always has. (CR-01, 04-REVIEW: the *true no-script
default* -- no explicit ``script`` argument and no ``DARK_FACTORY_FAKE_SCRIPT``
-- is the one exception: it synthesizes and writes minimal schema-valid files
itself, in ``src/dark_factory/workers/fake.py``, so this repo's own shipped
``.dark-factory.yaml`` is driveable with no explicit script at all. That
in-``src/`` synthesis path is independent of, and does not reuse, the helpers
below.)

**G-08-2 follow-on defect (found while closing G-08-2, not part of it):**
:func:`four_role_script` writes all four roles' files *up front*, before the
run even starts -- harmless before plan 08-05, but plan 08-05's
``enforce_artifact_scope`` now runs after each role's own attempt and
expects the run's ``artifacts/`` tree to hold only that role's own
uncommitted writes (a prior role's files are already committed by then in a
real run). A front-loaded script violates that invariant: by the time BA's
own check runs, ARCHITECTURE/DEVELOPMENT/QA's not-yet-run files are already
sitting on disk and get flagged as BA writing outside its own subtree.
:class:`LazyFourRoleWorker` below -- lifted from the pattern
``tests/db/test_artifact_commit_per_role.py`` already used for exactly this
reason -- writes each role's files at ``execute()``/``resume()`` time
instead, matching what a real worker call does. Prefer it over
``four_role_script`` for any db test that drives a real four-role run
through :func:`~dark_factory.orchestrator.runner.drive` end to end.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from dark_factory.artifacts.store import write_artifact_text
from dark_factory.domain.worker import (
    ArtifactRef,
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.workers.base import CodingWorker

__all__ = [
    "LazyFourRoleWorker",
    "four_role_script",
    "write_role_artifacts",
]

# The same minimal, schema-valid-per-D-07 content `four_role_script` writes,
# keyed by role so `LazyFourRoleWorker` can write only the currently-executing
# role's files, from *inside* that role's own `execute()`/`resume()` call --
# see the module docstring's G-08-2 follow-on note.
_FOUR_ROLE_FILES: dict[str, dict[str, str]] = {
    "BA": {
        "requirements.md": (
            "# Requirements\n\n1. The system does the thing correctly.\n"
        ),
        "acceptance_criteria.json": json.dumps(
            {"criteria": [{"id": "AC-1", "description": "the thing works"}]}
        ),
    },
    "ARCHITECTURE": {
        "design.md": (
            "# Design\n\nImplement the thing in the existing service layer; "
            "no new component is needed.\n"
        ),
        "constraints.json": json.dumps(
            {"constraints": [{"id": "C-1", "description": "no new database migration"}]}
        ),
    },
    "DEVELOPMENT": {
        "implementation_summary.json": json.dumps(
            {
                "summary": "implemented the thing",
                "changed_files": [],
                "tests_added": [],
            }
        ),
    },
    "QA": {
        "test_report.json": json.dumps(
            {
                "cases": [
                    {
                        "name": "AC-1: the thing works",
                        "result": "PASS",
                        "detail": "reproduced manually",
                    }
                ]
            }
        ),
        "verdict.json": json.dumps(
            {
                "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
                "issues": [],
                "status": "PASS",
            }
        ),
    },
}


def write_role_artifacts(
    root: Path, role: str, files: dict[str, str]
) -> list[ArtifactRef]:
    """Write each ``{filename: content}`` entry under ``<root>/artifacts/<role>/``
    and return one :class:`ArtifactRef` per file, in ``files`` iteration order.
    """
    refs: list[ArtifactRef] = []
    for filename, content in files.items():
        path, digest = write_artifact_text(root, role, filename, content)
        refs.append(ArtifactRef(type=filename, path=path, checksum=digest))
    return refs


class LazyFourRoleWorker(CodingWorker):
    """The same ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` fixture content as
    :func:`four_role_script`, but written one role at a time, from *inside*
    that role's own ``execute()``/``resume()`` call -- see the module
    docstring's G-08-2 follow-on note for why this matters under plan
    08-05's ``enforce_artifact_scope``. A real worker call only ever writes
    its own role's files exactly when it runs; this fixture matches that
    timing instead of pre-staging the whole run tree upfront.
    """

    def __init__(self, run_root: Path) -> None:
        self._run_root = run_root

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role in _FOUR_ROLE_FILES, role
        refs = write_role_artifacts(self._run_root, role, _FOUR_ROLE_FILES[role])
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{role} completed",
            worker_session_id=f"fake-{role.lower()}-{uuid4()}",
            artifacts=refs,
        )

    def execute(self, context: object) -> WorkerResult:
        return self._record(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._record(context)

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )


def four_role_script(run_root: Path) -> list[WorkerResult]:
    """The single ordered ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` script a
    four-role db test hands to one :class:`~dark_factory.workers.fake.FakeWorker`
    (the registry-scoped-singleton note in ``workers/registry.py``'s docstring:
    one script cursor advances across the whole run, so four independently
    scripted workers cannot be dispatched between).

    Content is minimal but schema-valid per D-07: ``acceptance_criteria.json``
    carries an ``AC-1``-shaped id, and ``verdict.json`` references that same id
    with a declared status consistent with its criteria (D-04/D-05). Realistic
    task-aware prose is Phase 7's concern, not this one.
    """
    ba_refs = write_role_artifacts(
        run_root,
        "BA",
        {
            "requirements.md": (
                "# Requirements\n\n1. The system does the thing correctly.\n"
            ),
            "acceptance_criteria.json": json.dumps(
                {
                    "criteria": [
                        {"id": "AC-1", "description": "the thing works"},
                    ]
                }
            ),
        },
    )
    architecture_refs = write_role_artifacts(
        run_root,
        "ARCHITECTURE",
        {
            "design.md": (
                "# Design\n\nImplement the thing in the existing service layer; "
                "no new component is needed.\n"
            ),
            "constraints.json": json.dumps(
                {
                    "constraints": [
                        {"id": "C-1", "description": "no new database migration"},
                    ]
                }
            ),
        },
    )
    development_refs = write_role_artifacts(
        run_root,
        "DEVELOPMENT",
        {
            "implementation_summary.json": json.dumps(
                {
                    "summary": "implemented the thing",
                    "changed_files": [],
                    "tests_added": [],
                }
            ),
        },
    )
    qa_refs = write_role_artifacts(
        run_root,
        "QA",
        {
            "test_report.json": json.dumps(
                {
                    "cases": [
                        {
                            "name": "AC-1: the thing works",
                            "result": "PASS",
                            "detail": "reproduced manually",
                        }
                    ]
                }
            ),
            "verdict.json": json.dumps(
                {
                    "criteria": [
                        {"criterion_id": "AC-1", "result": "PASS", "notes": ""}
                    ],
                    "issues": [],
                    "status": "PASS",
                }
            ),
        },
    )

    return [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            worker_session_id=f"fake-ba-{uuid4()}",
            artifacts=ba_refs,
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="architecture design complete",
            worker_session_id=f"fake-architecture-{uuid4()}",
            artifacts=architecture_refs,
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="implementation complete",
            worker_session_id=f"fake-development-{uuid4()}",
            artifacts=development_refs,
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="QA verified every acceptance criterion",
            worker_session_id=f"fake-qa-{uuid4()}",
            artifacts=qa_refs,
        ),
    ]
