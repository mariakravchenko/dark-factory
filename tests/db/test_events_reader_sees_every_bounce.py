"""``read_events(..., event_types=[EventType.ROLE_BOUNCED])`` against a real
feedback-loop run (Plan 12-02, Task 2, OBS-03).

The transparency prohibition made mechanical: a run that looped must not
read back as a run that did not, and the ``--type`` filter must narrow the
view without rewriting the trail. This drives a real QA-verdict FAIL bounce
in-process -- the same ``AttemptAwareFourRoleWorker`` / ``QA_VERDICT_FAIL_FILES``
scenario ``tests/db/test_qa_bounce.py``'s
``test_qa_fail_then_pass_bounces_once_and_completes`` already proves at the
persistence layer -- then asserts the read path through ``read_events``:
filtering to ``ROLE_BOUNCED`` returns one row per bounce cycle the run
actually performed, and the unfiltered read still contains every one of
those same rows at the same ``seq`` values.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.events.catalog import EventType
from dark_factory.events.reader import read_events
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import (
    QA_VERDICT_FAIL_FILES,
    AttemptAwareFourRoleWorker,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# Same build-then-overwrite idiom as ``tests/db/test_qa_bounce.py`` --
# duplicated here (not imported) because that module's helper is private and
# this suite has no cross-db-module import convention.
_QUALITY_GATE_BLOCK = "quality_gate:\n  commands: []\n"
_RETRY_BLOCK = (
    "retry:\n  qa_developer_max_iterations: 3\n  quality_gate_max_iterations: 2\n"
)


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """The ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` config tree
    ``tests/db/test_four_role_pipeline.py`` writes, with default retry caps
    and no quality-gate commands -- the same tree
    ``tests/db/test_qa_bounce.py``'s scenario 1 uses."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"))
    definitions = {
        "BA": ("[]", "[requirements.md, acceptance_criteria.json]"),
        "ARCHITECTURE": (
            "[acceptance_criteria.json]",
            "[design.md, constraints.json]",
        ),
        "DEVELOPMENT": (
            "[design.md, constraints.json]",
            "[implementation_summary.json]",
        ),
        "QA": (
            "[acceptance_criteria.json, implementation_summary.json]",
            "[test_report.json, verdict.json]",
        ),
    }
    tools = {
        "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "DEVELOPMENT": (
            "[repo.read, repo.search, repo.write, repo.write_tests, "
            "shell.execute, artifacts.read, artifacts.write]"
        ),
        "QA": (
            "[repo.read, repo.search, repo.write_tests, shell.execute, "
            "artifacts.read, artifacts.write]"
        ),
    }
    for role, (inputs, outputs) in definitions.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {tools[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )

    config_path = root / ".dark-factory.yaml"
    original = config_path.read_text(encoding="utf-8")
    assert _QUALITY_GATE_BLOCK in original, (
        "config_root_factory no longer writes 'quality_gate:\\n  commands: []\\n'"
        " verbatim -- update this test's overwrite string to match"
    )
    patched = original.replace(_QUALITY_GATE_BLOCK, "quality_gate:\n  commands: []\n")
    assert _RETRY_BLOCK in patched, (
        "config_root_factory no longer writes the retry: block verbatim -- "
        "update this test's overwrite string to match"
    )
    config_path.write_text(patched, encoding="utf-8")
    return root


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(ArtifactReference).where(ArtifactReference.run_id.in_(ids))
            )
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def test_role_bounced_filter_matches_the_unfiltered_trail_at_the_same_seqs(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails once then passes, read back through read_events",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = AttemptAwareFourRoleWorker(
        run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    # The read path, not the persistence layer directly: read_events is the
    # one module permitted to query run_events for a read path.
    unfiltered = read_events(run_id, session_factory=real_session_factory)
    bounced_only = read_events(
        run_id,
        event_types=[EventType.ROLE_BOUNCED],
        session_factory=real_session_factory,
    )

    # The run actually looped once (same assertion test_qa_bounce.py makes
    # at the persistence layer) -- this is the proof the filter has
    # something real to narrow, not a vacuous "zero matches zero".
    assert len(bounced_only) == 1
    assert bounced_only[0].type == "ROLE_BOUNCED"
    assert bounced_only[0].payload["reason"] == "qa_verdict_fail"

    # The filter narrows the view; it never rewrites the trail. Every
    # ROLE_BOUNCED row the filtered read returns is present in the
    # unfiltered read at the identical seq, and the unfiltered read carries
    # strictly more (or equal) rows -- it never carries fewer.
    unfiltered_by_seq = {row.seq: row for row in unfiltered}
    for row in bounced_only:
        assert row.seq in unfiltered_by_seq
        assert unfiltered_by_seq[row.seq].type == row.type
        assert unfiltered_by_seq[row.seq].payload == row.payload
    assert len(unfiltered) >= len(bounced_only)

    # OBS-03 transparency: a run that looped must not read back as a run
    # that did not -- RUN_FAILED never appears, and at least one
    # ROLE_BOUNCED row survives the unfiltered read.
    unfiltered_types = [row.type for row in unfiltered]
    assert "ROLE_BOUNCED" in unfiltered_types
    assert "RUN_FAILED" not in unfiltered_types

    # json.dumps round-trip sanity: payload values straight off EventRow are
    # already JSON-primitive (no datetime/UUID leaking through unredacted).
    json.dumps(bounced_only[0].payload)
