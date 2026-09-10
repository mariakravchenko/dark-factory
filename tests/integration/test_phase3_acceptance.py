"""The Phase 3 acceptance gate.

Each of the four Phase 3 success criteria (``.planning/ROADMAP.md`` -> "Phase 3:
Configuration-Driven Pipeline" -> Success Criteria) and each of the eight Phase 3
requirement ids (``.planning/REQUIREMENTS.md``: ORCH-02, ORCH-03, CFG-01, CFG-02,
CFG-03, CFG-04, CFG-05, WORK-02) is mapped here, by name, to the test file or
files that prove it.

A criterion or requirement whose proof file silently disappeared during a later
refactor is exactly what this gate is for (threat T-03-14): a missing file is a
**failure**, never passed over, and the failure message names the criterion or
requirement id, not merely the path. A file emptied by a bad merge -- present but
carrying no ``def test_`` -- fails the same way. This gate never opts out: a
criterion with no reachable proof must fail, because an assertion that never runs
in an acceptance gate is indistinguishable from success in a summary. The plan's
grep guard enforces that this file contains no opt-out call at all.

This gate only asserts the mapped proofs are **present and non-empty**. It does
not run them. The full suite passing across every marker tier -- run separately
as ``set -a; . ./.env; set +a; uv run pytest`` -- is what establishes that the
mapped proofs are actually green rather than merely present.

It is a sibling of ``tests/integration/test_phase2_acceptance.py`` and
``tests/integration/test_phase_acceptance.py``, not an extension of either: each
phase's gate asserts its mapping is exactly that phase's criteria, and each
should be independently readable.
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
        "Shortening or reordering workflow.roles in .dark-factory.yaml changes "
        "the executed pipeline with no Python change and no orchestrator edit.",
        (
            "tests/integration/test_config_drives_pipeline.py",
            "tests/unit/test_no_role_name_literal.py",
        ),
    ),
    "SC2": (
        "A role's instructions, tools, permissions, before/after hooks, outputs "
        "and worker are read from .dark-factory/ role YAML and instruction "
        "Markdown; editing those files changes behaviour without touching source.",
        (
            "tests/integration/test_role_yaml_drives_behaviour.py",
            "tests/db/test_snapshot_roundtrip.py",
        ),
    ),
    "SC3": (
        "Editing .dark-factory.yaml while a run is paused and then resuming "
        "executes the configuration snapshot resolved at run creation, not the "
        "edited file.",
        (
            "tests/integration/test_snapshot_survives_edit.py",
            "tests/unit/test_orchestrator_no_live_config_read.py",
        ),
    ),
    "SC4": (
        "A before/after hook named in configuration resolves through the "
        "ActionRegistry, and an unknown action or worker name fails validation at "
        "run creation with a non-zero exit and no orphan run.",
        (
            "tests/db/test_bad_config_no_orphan_run.py",
            "tests/integration/test_config_error_exit_code.py",
            "tests/db/test_role_hooks_invoked.py",
        ),
    ),
}

# requirement id -> (REQUIREMENTS.md text verbatim, tuple of proof files relative
# to the repository root). Proof files are taken from 03-VALIDATION.md's
# per-requirement test map, adjusted to the file names the 03-01..03-04
# summaries record as actually delivered.
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ORCH-02": (
        "The orchestrator executes a configured ordered sequence of roles, not "
        "hardcoded role calls",
        (
            "tests/integration/test_config_drives_pipeline.py",
            "tests/unit/test_pipeline_from_snapshot.py",
        ),
    ),
    "ORCH-03": (
        "The role pipeline is defined in configuration (`workflow.roles`) and can "
        "be shortened or reordered without changing orchestrator code",
        (
            "tests/integration/test_config_drives_pipeline.py",
            "tests/unit/test_no_role_name_literal.py",
        ),
    ),
    "CFG-01": (
        "Repository behavior is configured in `.dark-factory.yaml` (version, "
        "`workflow.roles`, `repository.base_branch`, per-role definition files, "
        "`quality_gate.commands`, `retry` limits, `publishing.create_pr`)",
        (
            "tests/unit/test_repo_config_schema.py",
            "tests/integration/test_config_error_exit_code.py",
        ),
    ),
    "CFG-02": (
        "Role behavior lives in `.dark-factory/` files (role YAML, instruction "
        "Markdown, examples) and is editable without changing Python source",
        ("tests/integration/test_role_yaml_drives_behaviour.py",),
    ),
    "CFG-03": (
        "A role definition is fully configuration-driven — instructions, tools, "
        "permissions, before/after hooks, outputs, worker",
        (
            "tests/integration/test_role_yaml_drives_behaviour.py",
            "tests/unit/test_repo_config_schema.py",
        ),
    ),
    "CFG-04": (
        "An `ActionRegistry` exposes deterministic before/after actions "
        "referenced by configuration (`prepare_role_context`, "
        "`ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, "
        "`collect_test_results`, …) and accepts new actions without core changes",
        (
            "tests/unit/test_action_registry.py",
            "tests/db/test_role_hooks_invoked.py",
        ),
    ),
    "CFG-05": (
        "The configuration resolved at run creation is snapshotted and persisted, "
        "so a later resume is deterministic even if `.dark-factory.yaml` changed "
        "in between",
        (
            "tests/db/test_snapshot_roundtrip.py",
            "tests/integration/test_snapshot_survives_edit.py",
        ),
    ),
    "WORK-02": (
        "A `WorkerRegistry` maps `claude-code` / `copilot` / `hermes` to "
        "adapters; worker creation is centralized",
        ("tests/unit/test_worker_registry_names.py",),
    ),
}

_PHASE_3_CRITERIA = {"SC1", "SC2", "SC3", "SC4"}
_PHASE_3_REQUIREMENT_IDS = {
    "ORCH-02",
    "ORCH-03",
    "CFG-01",
    "CFG-02",
    "CFG-03",
    "CFG-04",
    "CFG-05",
    "WORK-02",
}

# Every per-requirement proof file 03-VALIDATION.md's verification map names.
# Held here verbatim so the acceptance gate and the validation strategy document
# cannot drift apart unnoticed (plan 03-04, key_links drift guard).
_VALIDATION_PROOF_FILES: frozenset[str] = frozenset(
    {
        "tests/integration/test_config_drives_pipeline.py",
        "tests/unit/test_no_role_name_literal.py",
        "tests/integration/test_role_yaml_drives_behaviour.py",
        "tests/db/test_snapshot_roundtrip.py",
        "tests/integration/test_snapshot_survives_edit.py",
        "tests/unit/test_orchestrator_no_live_config_read.py",
        "tests/db/test_bad_config_no_orphan_run.py",
        "tests/integration/test_config_error_exit_code.py",
        "tests/db/test_role_hooks_invoked.py",
        "tests/unit/test_action_registry.py",
        "tests/unit/test_worker_registry_names.py",
        "tests/unit/test_repo_config_schema.py",
        "tests/unit/test_pipeline_from_snapshot.py",
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


def test_every_phase_3_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == _PHASE_3_CRITERIA, (
        "the acceptance gate must map exactly the four Phase 3 success criteria; "
        f"got {sorted(SUCCESS_CRITERIA)}"
    )


def test_every_phase_3_requirement_id_is_mapped() -> None:
    assert set(REQUIREMENTS) == _PHASE_3_REQUIREMENT_IDS, (
        "the acceptance gate must map exactly the eight Phase 3 requirement ids "
        "(ORCH-02, ORCH-03, CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, WORK-02); "
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
        "03-VALIDATION.md names these per-requirement proof files but the "
        "acceptance gate does not map them (the two documents have drifted): "
        + ", ".join(uncovered)
    )
