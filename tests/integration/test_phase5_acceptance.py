"""The Phase 5 acceptance gate.

Each of the four Phase 5 success criteria (``.planning/ROADMAP.md`` ->
"Phase 5: Isolated Workspace & Git Lifecycle" -> Success Criteria) and each
of the four Phase 5 requirement ids (``.planning/REQUIREMENTS.md``: GIT-01,
GIT-02, ART-04, ROLE-05) is mapped here, by name, to the test file or files
that prove it.

A criterion or requirement whose proof file silently disappeared during a
later refactor is exactly what this gate is for: a missing file is a
**failure**, never passed over, and the failure message names the criterion
or requirement id, not merely the path. A file emptied by a bad merge --
present but carrying no ``def test_`` -- fails the same way. This gate never
opts out: a criterion with no reachable proof must fail, because an
assertion that never runs in an acceptance gate is indistinguishable from
success in a summary.

This gate only asserts the mapped proofs are **present and non-empty**. It
does not run them. The full suite passing across every marker tier -- run
separately as ``set -a; . ./.env; set +a; uv run pytest`` -- is what
establishes that the mapped proofs are actually green rather than merely
present.

It is a **sibling** of ``tests/integration/test_phase4_acceptance.py``,
``tests/integration/test_phase3_acceptance.py``,
``tests/integration/test_phase2_acceptance.py`` and
``tests/integration/test_phase_acceptance.py``, not an extension of any of
them: each phase's gate asserts its own mapping is exactly that phase's
criteria and each should be independently readable.

The proof-file set below is drift-guarded against
``05-VALIDATION.md``'s Per-Task Verification Map (the Phase 2/Phase 3 gates'
own established pattern): a proof renamed in one place and not the other is
a failure here, not a silent divergence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

# success-criterion id -> (roadmap text verbatim, tuple of proof files
# relative to the repository root)
SUCCESS_CRITERIA: dict[str, tuple[str, tuple[str, ...]]] = {
    "SC1": (
        "A run creates a working branch from the configured base branch, "
        "named so it is unique to the run id, and every role executes "
        "against that same worktree.",
        (
            "tests/db/test_run_owns_a_worktree.py",
            "tests/unit/test_git_worktree.py",
        ),
    ),
    "SC2": (
        "A process on a different machine, given only the run id and a "
        "fresh clone, has the run's artifact content available to rebuild "
        "context and continue.",
        (
            "tests/integration/test_artifact_cross_clone.py",
            "tests/db/test_artifact_commit_per_role.py",
        ),
    ),
    "SC3": (
        "A role that finishes with uncommitted changes is recovered on "
        "next entry -- changes WIP-committed to a persisted ref, worktree "
        "clean, nothing lost -- and an entry on a detached HEAD fails the "
        "role with a persisted event instead of proceeding.",
        (
            "tests/db/test_wip_commit_recovery.py",
            "tests/db/test_detached_head_fails_role.py",
            "tests/integration/test_worktree_lifecycle.py",
        ),
    ),
    "SC4": (
        "A role whose diff touches paths outside its configured write "
        "scope (QA touching production code) fails the role; the "
        "out-of-scope edit is reverted and the violation is logged.",
        (
            "tests/integration/test_write_scope_enforcement.py",
            "tests/unit/test_write_scope.py",
        ),
    ),
}

# requirement id -> (REQUIREMENTS.md text verbatim, tuple of proof files
# relative to the repository root).
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "GIT-01": (
        "Each run has an explicit working branch created from the "
        "configured base branch; all roles operate on the same run "
        "repository state",
        (
            "tests/unit/test_git_worktree.py",
            "tests/db/test_run_owns_a_worktree.py",
            "tests/integration/test_worktree_lifecycle.py",
        ),
    ),
    "GIT-02": (
        "Dark Factory owns delivery actions (create branch, commit, push, "
        "create PR); agents never own commit/push/PR policy",
        (
            "tests/unit/test_git_ownership_boundary.py",
            "tests/db/test_artifact_commit_per_role.py",
        ),
    ),
    "ART-04": (
        "Artifact content is available to a resuming process on a "
        "different machine (durability strategy for cross-machine resume)",
        ("tests/integration/test_artifact_cross_clone.py",),
    ),
    "ROLE-05": (
        "A role's permitted file-write scope is enforced after execution "
        "(e.g. QA's diff must not touch production code) using path rules "
        "from configuration",
        (
            "tests/integration/test_write_scope_enforcement.py",
            "tests/unit/test_write_scope.py",
        ),
    ),
}

_PHASE_5_CRITERIA = {"SC1", "SC2", "SC3", "SC4"}
_PHASE_5_REQUIREMENT_IDS = {"GIT-01", "GIT-02", "ART-04", "ROLE-05"}

# Every per-requirement proof file 05-VALIDATION.md's verification map names.
# Held here verbatim so the acceptance gate and the validation strategy
# document cannot drift apart unnoticed (Phase 2/Phase 3 gates' established
# drift-guard pattern).
_VALIDATION_PROOF_FILES: frozenset[str] = frozenset(
    {
        "tests/unit/test_git_worktree.py",
        "tests/integration/test_worktree_lifecycle.py",
        "tests/unit/test_git_ownership_boundary.py",
        "tests/integration/test_artifact_cross_clone.py",
        "tests/unit/test_write_scope.py",
        "tests/integration/test_write_scope_enforcement.py",
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
            f"has disappeared. This is a failure, not a pass."
        )
        source = path.read_text(encoding="utf-8")
        assert source.strip(), f"{label} ({description}): {rel} exists but is empty"
        assert "def test_" in source, (
            f"{label} ({description}): {rel} exists but contains no test function"
        )


def test_every_phase_5_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == _PHASE_5_CRITERIA, (
        "the acceptance gate must map exactly the four Phase 5 success "
        f"criteria; got {sorted(SUCCESS_CRITERIA)}"
    )


def test_every_phase_5_requirement_id_is_mapped() -> None:
    assert set(REQUIREMENTS) == _PHASE_5_REQUIREMENT_IDS, (
        "the acceptance gate must map exactly the four Phase 5 requirement "
        f"ids (GIT-01, GIT-02, ART-04, ROLE-05); got {sorted(REQUIREMENTS)}"
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
        "05-VALIDATION.md names these per-requirement proof files but the "
        "acceptance gate does not map them (the two documents have "
        "drifted): " + ", ".join(uncovered)
    )
