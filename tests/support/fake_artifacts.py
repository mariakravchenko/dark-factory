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
    "QA_VERDICT_FAIL_FILES",
    "AttemptAwareFourRoleWorker",
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


# Phase 9 (plan 09-01, Task 2): a FAIL-shaped variant of QA's own two
# output files, alongside (never replacing) `_FOUR_ROLE_FILES["QA"]` above --
# every other db test depends on that PASS default staying untouched. A
# scenario that needs "QA's own verdict FAILs" passes this dict as
# `LazyFourRoleWorker(..., qa_files=QA_VERDICT_FAIL_FILES)`.
QA_VERDICT_FAIL_FILES: dict[str, str] = {
    "test_report.json": json.dumps(
        {
            "cases": [
                {
                    "name": "AC-1: the thing works",
                    "result": "FAIL",
                    "detail": "reproduced the defect",
                }
            ]
        }
    ),
    "verdict.json": json.dumps(
        {
            "criteria": [
                {
                    "criterion_id": "AC-1",
                    "result": "FAIL",
                    "notes": "reproduced the defect",
                }
            ],
            "issues": [{"severity": "blocking", "description": "AC-1 is not met"}],
            "status": "FAIL",
        }
    ),
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

    def __init__(
        self, run_root: Path, *, qa_files: dict[str, str] | None = None
    ) -> None:
        self._run_root = run_root
        # Phase 9 (plan 09-01, Task 2): an optional per-run override for QA's
        # own two files -- e.g. `QA_VERDICT_FAIL_FILES` -- so a scenario can
        # drive a real FAIL verdict without touching `_FOUR_ROLE_FILES`'s
        # shared PASS default every other db test depends on.
        self._qa_files = qa_files

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role in _FOUR_ROLE_FILES, role
        files = (
            self._qa_files
            if role == "QA" and self._qa_files is not None
            else _FOUR_ROLE_FILES[role]
        )
        refs = write_role_artifacts(self._run_root, role, files)
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


class AttemptAwareFourRoleWorker(CodingWorker):
    """Like :class:`LazyFourRoleWorker` -- lazy, writes at ``execute()``/
    ``resume()`` time -- but its per-role content is selected by
    ``context.attempt``, which :class:`LazyFourRoleWorker`'s own ``_record``
    ignores entirely (it always returns ``_FOUR_ROLE_FILES[role]``, no matter
    which attempt this is). This is what makes "QA fails on attempt 1 and
    passes on attempt 2" -- or "the gate fails until the Developer's attempt
    2 creates a sentinel file" -- expressible for a Phase 9 bounce scenario.

    ``attempt_files`` maps ``(role, attempt) -> {filename: content}``; any
    ``(role, attempt)`` pair not present falls back to
    ``_FOUR_ROLE_FILES[role]`` (the same shared PASS-shaped default every
    other db test in this project depends on), so a scenario only needs to
    override the specific attempts it cares about.

    ``sentinel_writes`` optionally maps ``(role, attempt) -> filename``: a
    zero-byte file created at ``<worktree root>/.dark-factory/runs/<filename>``
    (a fixed, run-id-independent path -- the quality-gate command that checks
    for it is written into config before the run id exists) when that
    ``(role, attempt)`` executes. Deliberately placed under the gitignored
    ``.dark-factory/runs/`` prefix (A-05-15), not the bare worktree root: a
    write there would otherwise be flagged as an out-of-scope change by the
    writing role's own ``enforce_write_scope`` check (ROLE-05, D-14's
    zero-tolerance empty ``write_scope`` in these db-test fixtures) and
    reverted before ever reaching the gate. This is what a
    gate-FAIL-then-PASS scenario uses to make a gate command's exit code flip
    between the Developer's bounced attempts, without disturbing write-scope
    enforcement for either role.

    ``out_of_scope_writes`` (plan 09-04, gap CR-01) optionally maps
    ``(role, attempt) -> worktree-relative path``: a short, fixed-text file
    created at that path, resolved against ``worktree_root``, when that
    ``(role, attempt)`` executes. This is ``sentinel_writes``'s deliberate
    opposite: ``sentinel_writes`` targets the gitignored run tree so the
    write is invisible to ``attempt_changed_paths`` and never triggers
    enforcement, whereas ``out_of_scope_writes`` targets a tracked-visible
    worktree path *in order to* trigger ``enforce_write_scope`` -- which is
    what lets a test prove the ROLE-05 boundary actually holds on a bounce.
    """

    def __init__(
        self,
        run_root: Path,
        *,
        attempt_files: dict[tuple[str, int], dict[str, str]],
        sentinel_writes: dict[tuple[str, int], str] | None = None,
        out_of_scope_writes: dict[tuple[str, int], str] | None = None,
        worktree_root: Path | None = None,
    ) -> None:
        self._run_root = run_root
        self._attempt_files = attempt_files
        self._sentinel_writes = sentinel_writes or {}
        self._out_of_scope_writes = out_of_scope_writes or {}
        self._worktree_root = worktree_root
        if self._out_of_scope_writes and self._worktree_root is None:
            raise ValueError(
                "AttemptAwareFourRoleWorker: out_of_scope_writes was given "
                "without worktree_root -- both keyword names must be set "
                "together, or the planted write silently never lands and "
                "the regression test becomes a vacuous pass"
            )

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        attempt = getattr(context, "attempt", None)
        assert role in _FOUR_ROLE_FILES, role
        files = self._attempt_files.get((role, attempt), _FOUR_ROLE_FILES[role])
        refs = write_role_artifacts(self._run_root, role, files)
        sentinel_name = self._sentinel_writes.get((role, attempt))
        if sentinel_name is not None:
            # ``self._run_root`` is ``<worktree root>/.dark-factory/runs/<run_id>``
            # (see ``artifacts.paths.run_root``) -- one ``.parent`` hop back is
            # ``<worktree root>/.dark-factory/runs``, still inside the
            # gitignored prefix but independent of this specific run id.
            gitignored_runs_dir = self._run_root.parent
            (gitignored_runs_dir / sentinel_name).touch()
        out_of_scope_path = self._out_of_scope_writes.get((role, attempt))
        if out_of_scope_path is not None:
            assert self._worktree_root is not None  # enforced in __init__
            target = self._worktree_root / out_of_scope_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"planted by {role} attempt {attempt} -- out of write_scope\n",
                encoding="utf-8",
            )
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{role} completed (attempt {attempt})",
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


# Per-role summary text for four_role_script's WorkerResults, keyed the same
# way as _FOUR_ROLE_FILES so the two dicts can't drift out of role-order sync.
_FOUR_ROLE_SUMMARIES: dict[str, str] = {
    "BA": "BA analysis complete",
    "ARCHITECTURE": "architecture design complete",
    "DEVELOPMENT": "implementation complete",
    "QA": "QA verified every acceptance criterion",
}


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

    Built from the same ``_FOUR_ROLE_FILES`` content :class:`LazyFourRoleWorker`
    uses, so the two can never drift apart on what each role's files contain --
    only on *when* those files land on disk (all at once here vs. one role at a
    time there, per the module docstring's G-08-2 follow-on note).
    """
    return [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=_FOUR_ROLE_SUMMARIES[role],
            worker_session_id=f"fake-{role.lower()}-{uuid4()}",
            artifacts=write_role_artifacts(run_root, role, files),
        )
        for role, files in _FOUR_ROLE_FILES.items()
    ]
