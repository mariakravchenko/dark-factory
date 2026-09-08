"""The Phase 1 acceptance gate.

Each of the five Phase 1 success criteria (``.planning/ROADMAP.md`` -> "Phase 1:
Walking Skeleton — One Durable Run" -> Success Criteria) is mapped here to the
named test file or files that prove it. This gate asserts every mapped file
still exists and still carries test functions.

A criterion whose proof silently disappeared during a later refactor is exactly
what this gate is for (threat T-01-36): a missing file is a **failure**, never a
skip, and the failure message names the criterion, not just a path. The full
suite passing across every marker tier -- run separately as ``uv run pytest -q``
-- is what establishes that the mapped proofs are green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

# criterion id -> (verbatim-ish criterion text, tuple of proof files relative to repo root)
SUCCESS_CRITERIA: dict[str, tuple[str, tuple[str, ...]]] = {
    "SC1": (
        'dark-factory run text:"..." creates a run in Neon, drives it through one '
        "configured role using FakeWorker with zero external AI calls, and reaches "
        "a terminal state",
        ("tests/integration/test_walking_skeleton.py",),
    ),
    "SC2": (
        "killing the process mid-run and invoking the orchestrator again from a "
        "brand-new process with no in-memory carryover continues from the last "
        "committed step and reaches the same terminal state",
        ("tests/integration/test_fresh_process_resume.py",),
    ),
    "SC3": (
        "dark-factory status <run-id> reports run state, current role and attempt "
        "number read from state columns, never recomputed by folding the event log",
        (
            "tests/db/test_status_from_columns.py",
            "tests/unit/test_status_import_graph.py",
        ),
    ),
    "SC4": (
        "a crash injected between the sub-writes of a transition leaves a "
        "consistent, resumable run: no state change without its run_events row, "
        "and no event without its state change",
        (
            "tests/db/test_transition_atomic.py",
            "tests/db/test_state_event_pairing.py",
        ),
    ),
    "SC5": (
        "a task whose text contains a DATABASE_URL-shaped value shows redacted "
        "values in every persisted event payload and every log line",
        ("tests/integration/test_secret_redaction_e2e.py",),
    ),
}


def test_every_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == {"SC1", "SC2", "SC3", "SC4", "SC5"}, (
        "the acceptance gate must map exactly the five Phase 1 success criteria"
    )


@pytest.mark.parametrize("criterion", sorted(SUCCESS_CRITERIA))
def test_success_criterion_has_a_named_proof_that_exists(criterion: str) -> None:
    description, proof_files = SUCCESS_CRITERIA[criterion]

    assert proof_files, f"{criterion} ({description}): no proof file is mapped"

    for rel in proof_files:
        path = _REPO_ROOT / rel
        assert path.is_file(), (
            f"{criterion} ({description}): mapped proof {rel} is MISSING -- a "
            f"success-criterion proof has disappeared. This is a failure, not a skip."
        )
        source = path.read_text(encoding="utf-8")
        assert "def test_" in source, (
            f"{criterion} ({description}): {rel} exists but contains no test function"
        )
