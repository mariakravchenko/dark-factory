"""The Phase 2 acceptance gate.

Each of the five Phase 2 success criteria (``.planning/ROADMAP.md`` -> "Phase 2:
Pause, Resume & Single-Owner Execution" -> Success Criteria) and each of the six
Phase 2 requirement ids (``.planning/REQUIREMENTS.md``: STATE-04, HITL-01,
HITL-02, HITL-03, HITL-07, HITL-08) is mapped here, by name, to the test file or
files that prove it.

A criterion or a requirement whose proof file silently disappeared during a
later refactor is exactly what this gate is for (threat T-02-38): a missing file
is a **failure**, never a skip, and the failure message names the criterion or
the requirement id, not merely the path. A file emptied by a bad merge --
present but carrying no ``def test_`` -- fails the same way. This gate never
skips: a criterion with no reachable proof must fail, because a skipped
assertion in an acceptance gate is indistinguishable from success in a summary.
The plan's grep guard enforces that this file contains no skip call at all.

This gate only asserts the mapped proofs are **present and non-empty**. It does
not run them. The full suite passing across every marker tier -- run separately
as ``set -a; . ./.env; set +a; uv run pytest`` -- is what establishes that the
mapped proofs are actually green rather than merely present.

It is a sibling of ``tests/integration/test_phase_acceptance.py`` (the Phase 1
gate), not an extension of it: that file asserts its mapping is exactly the five
Phase 1 criteria, and each phase's gate should be independently readable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

# success-criterion id -> (roadmap text close to verbatim, tuple of proof files
# relative to the repository root)
SUCCESS_CRITERIA: dict[str, tuple[str, tuple[str, ...]]] = {
    "SC1": (
        "A role returning NEEDS_INPUT leaves the run WAITING_HUMAN with the "
        "question, the worker result, the worker session id and the current role "
        "persisted; the process exits 0 holding no open database transaction.",
        (
            "tests/integration/test_pause_exit_zero.py",
            "tests/db/test_pause_path_atomic.py",
            "tests/integration/test_no_txn_across_worker.py",
        ),
    ),
    "SC2": (
        'dark-factory resume <run-id> --answer "..." from a brand-new process '
        "continues the same role execution and attempt -- it never creates a new "
        "run and needs nothing from the original process.",
        ("tests/integration/test_resume_with_answer.py",),
    ),
    "SC3": (
        "Two processes racing advance on the same run: one executes, the other "
        "exits cleanly without changing status and without duplicating work.",
        (
            "tests/integration/test_single_owner_race.py",
            "tests/db/test_lease_claim_atomic.py",
        ),
    ),
    "SC4": (
        "A process killed while owning a run loses its lease by database-clock "
        "expiry, and the next process claims the run and continues from the last "
        "committed step.",
        ("tests/integration/test_lease_expiry_reclaim.py",),
    ),
    "SC5": (
        "A role step that runs longer than the lease TTL is not falsely stolen "
        "-- the owner heartbeats the lease while the step is in flight.",
        (
            "tests/integration/test_heartbeat_slow_step.py",
            "tests/db/test_lease_lost_aborts_step.py",
        ),
    ),
}

# requirement id -> (REQUIREMENTS.md text verbatim, tuple of proof files relative
# to the repository root). Proof files are taken from 02-VALIDATION.md's
# per-requirement test map, adjusted to the file names the 02-01..02-06
# summaries record as actually delivered.
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "STATE-04": (
        "A human_interactions table persists questions, answers, and status "
        "(WAITING | ANSWERED | CANCELLED)",
        (
            "tests/db/test_human_interactions_schema.py",
            "tests/integration/test_redaction_interactions.py",
        ),
    ),
    "HITL-01": (
        "Any role can ask the human for clarification through one identical mechanism",
        ("tests/db/test_pause_mechanism_generic.py",),
    ),
    "HITL-02": (
        "On a worker NEEDS_INPUT result the orchestrator stores the result and "
        "worker session, creates a human interaction, persists WAITING_HUMAN, "
        "and releases the execution so the process can terminate safely",
        (
            "tests/db/test_pause_path_atomic.py",
            "tests/integration/test_pause_exit_zero.py",
        ),
    ),
    "HITL-03": (
        "Operator can resume a paused run locally -- dark-factory resume "
        '<run-id> --answer "..." -- from a brand-new process with no in-memory '
        "state from the original run",
        ("tests/integration/test_resume_with_answer.py",),
    ),
    "HITL-07": (
        "Two processes cannot execute the same run simultaneously; single-owner "
        "execution is enforced with PostgreSQL transactions / row locking / "
        "conditional updates and no separate distributed-lock service",
        (
            "tests/integration/test_single_owner_race.py",
            "tests/db/test_lease_claim_atomic.py",
        ),
    ),
    "HITL-08": (
        "A database transaction is never held open across a worker subprocess "
        "call; ownership is held by a lease with database-clock expiry",
        ("tests/integration/test_no_txn_across_worker.py",),
    ),
}

_PHASE_2_CRITERIA = {"SC1", "SC2", "SC3", "SC4", "SC5"}
_PHASE_2_REQUIREMENT_IDS = {
    "STATE-04",
    "HITL-01",
    "HITL-02",
    "HITL-03",
    "HITL-07",
    "HITL-08",
}

# Every proof file 02-VALIDATION.md's per-requirement test map names as a new
# Wave-0 file. Held here verbatim so the acceptance gate and the validation
# strategy document cannot drift apart unnoticed (plan 02-07, behavior item 7).
_VALIDATION_PROOF_FILES: frozenset[str] = frozenset(
    {
        "tests/db/test_human_interactions_schema.py",
        "tests/db/test_pause_mechanism_generic.py",
        "tests/db/test_pause_path_atomic.py",
        "tests/integration/test_pause_exit_zero.py",
        "tests/integration/test_resume_with_answer.py",
        "tests/integration/test_single_owner_race.py",
        "tests/db/test_lease_claim_atomic.py",
        "tests/integration/test_no_txn_across_worker.py",
        "tests/integration/test_lease_expiry_reclaim.py",
        "tests/integration/test_heartbeat_slow_step.py",
        "tests/db/test_lease_lost_aborts_step.py",
        "tests/integration/test_redaction_interactions.py",
    }
)


def _all_mapped_paths() -> set[str]:
    paths: set[str] = set()
    for _text, proof_files in SUCCESS_CRITERIA.values():
        paths.update(proof_files)
    for _text, proof_files in REQUIREMENTS.values():
        paths.update(proof_files)
    return paths


def _assert_proofs_exist(
    label: str, description: str, proof_files: tuple[str, ...]
) -> None:
    assert proof_files, f"{label} ({description}): no proof file is mapped"
    for rel in proof_files:
        path = _REPO_ROOT / rel
        assert path.is_file(), (
            f"{label} ({description}): mapped proof {rel} is MISSING -- a proof "
            f"has disappeared. This is a failure, not a skip."
        )
        source = path.read_text(encoding="utf-8")
        assert source.strip(), f"{label} ({description}): {rel} exists but is empty"
        assert "def test_" in source, (
            f"{label} ({description}): {rel} exists but contains no test function"
        )


def test_every_phase_2_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == _PHASE_2_CRITERIA, (
        "the acceptance gate must map exactly the five Phase 2 success criteria; "
        f"got {sorted(SUCCESS_CRITERIA)}"
    )


def test_every_phase_2_requirement_id_is_mapped() -> None:
    assert set(REQUIREMENTS) == _PHASE_2_REQUIREMENT_IDS, (
        "the acceptance gate must map exactly the six Phase 2 requirement ids "
        "(STATE-04, HITL-01, HITL-02, HITL-03, HITL-07, HITL-08); "
        f"got {sorted(REQUIREMENTS)}"
    )


@pytest.mark.parametrize("criterion", sorted(SUCCESS_CRITERIA))
def test_success_criterion_has_named_proofs_that_exist(criterion: str) -> None:
    description, proof_files = SUCCESS_CRITERIA[criterion]
    _assert_proofs_exist(criterion, description, proof_files)


@pytest.mark.parametrize("requirement", sorted(REQUIREMENTS))
def test_requirement_has_named_proofs_that_exist(requirement: str) -> None:
    description, proof_files = REQUIREMENTS[requirement]
    _assert_proofs_exist(requirement, description, proof_files)


def test_no_mapped_proof_path_is_missing() -> None:
    missing = sorted(
        rel for rel in _all_mapped_paths() if not (_REPO_ROOT / rel).is_file()
    )
    assert not missing, (
        "acceptance-gate proof files that no longer exist on disk: "
        + ", ".join(missing)
    )


def test_validation_strategy_and_gate_cannot_drift() -> None:
    uncovered = sorted(_VALIDATION_PROOF_FILES - _all_mapped_paths())
    assert not uncovered, (
        "02-VALIDATION.md names these per-requirement proof files but the "
        "acceptance gate does not map them (the two documents have drifted): "
        + ", ".join(uncovered)
    )
