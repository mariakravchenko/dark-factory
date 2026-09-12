"""The Phase 4 acceptance gate.

Each of the five Phase 4 success criteria (``.planning/ROADMAP.md`` -> "Phase
4: The Four-Role Pipeline & Artifact Handoffs" -> Success Criteria) and each
of the fifteen Phase 4 requirement ids (``.planning/REQUIREMENTS.md``:
ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04, ROLE-06, CTX-01, CTX-02, CTX-03,
CTX-04, ART-01, ART-02, ART-03, STATE-05, INTAKE-02) is mapped here, by name,
to the test file or files that prove it.

A criterion or requirement whose proof file silently disappeared during a
later refactor is exactly what this gate is for (threat T-04-18): a missing
file is a **failure**, never passed over, and the failure message names the
criterion or requirement id, not merely the path. A file emptied by a bad
merge -- present but carrying no ``def test_`` -- fails the same way. This
gate never opts out: a criterion with no reachable proof must fail, because
an assertion that never runs in an acceptance gate is indistinguishable from
success in a summary. The plan's grep guard enforces that this file contains
no opt-out call at all.

This gate only asserts the mapped proofs are **present and non-empty**. It
does not run them. The full suite passing across every marker tier -- run
separately as ``set -a; . ./.env; set +a; uv run pytest`` -- is what
establishes that the mapped proofs are actually green rather than merely
present.

It is a **sibling** of ``tests/integration/test_phase3_acceptance.py``,
``tests/integration/test_phase2_acceptance.py`` and
``tests/integration/test_phase_acceptance.py``, not an extension of any of
them: each phase's gate asserts its own mapping is exactly that phase's
criteria and each should be independently readable.
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
        "A run started from spec:./task.md executes all four roles in order "
        "on FakeWorker and produces requirements.md + acceptance_criteria.json, "
        "design.md + constraints.json, implementation_summary.json, and "
        "test_report.json + verdict.json under .dark-factory/runs/<run-id>/.",
        (
            "tests/integration/test_spec_source_starts_a_run.py",
            "tests/db/test_four_role_pipeline.py",
        ),
    ),
    "SC2": (
        "Every artifact has an ArtifactReference row in Neon while its "
        "content stays on the filesystem -- no artifact body is stored in "
        "the database.",
        ("tests/db/test_artifact_persistence.py",),
    ),
    "SC3": (
        "A role's context contains only the prior artifacts its "
        "configuration selects, plus repository document paths and any "
        "human answers -- never a dump of the repository source tree.",
        (
            "tests/unit/test_context_builder.py",
            "tests/unit/test_no_tree_walk.py",
        ),
    ),
    "SC4": (
        "A retried attempt's rebuilt context contains no artifact from the "
        "superseded attempt.",
        ("tests/db/test_context_builder_retry_isolation.py",),
    ),
    "SC5": (
        "A machine artifact that violates its JSON schema fails the role "
        "with a persisted error instead of advancing the run, and the "
        "transition after QA is decided by verdict.json, never by summary "
        "prose.",
        ("tests/db/test_artifact_schema_violation_fails_role.py",),
    ),
}

# requirement id -> (REQUIREMENTS.md text verbatim, tuple of proof files
# relative to the repository root). Proof files are taken from the 04-01,
# 04-02, 04-03 and 04-04 SUMMARY files' actually-delivered file names, not
# from 04-VALIDATION.md's Wave-0 forecast.
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "INTAKE-02": (
        "Operator can start a run from a spec file -- dark-factory run spec:./path.md",
        (
            "tests/unit/test_loaders.py",
            "tests/integration/test_spec_source_starts_a_run.py",
        ),
    ),
    "ORCH-04": (
        "Roles communicate through durable artifacts, not one shared agent "
        "conversation",
        (
            "tests/db/test_artifact_handoff.py",
            "tests/db/test_four_role_pipeline.py",
        ),
    ),
    "ROLE-01": (
        "The Business Analyst role makes the request implementation-ready "
        "and emits requirements.md and acceptance_criteria.json; it is "
        "read-only with respect to repository source code",
        (
            "tests/db/test_four_role_pipeline.py",
            "tests/unit/test_artifact_models.py",
        ),
    ),
    "ROLE-02": (
        "The Architect role consumes the task, BA output, and repository "
        "and emits design.md and constraints.json; it is read-only with "
        "respect to repository source code",
        ("tests/db/test_four_role_pipeline.py",),
    ),
    "ROLE-03": (
        "The Developer role implements the change, adds/updates tests, "
        "runs tests/lint/build, iterates on failures, and emits "
        "implementation_summary.json; it may modify production code and "
        "tests",
        ("tests/db/test_four_role_pipeline.py",),
    ),
    "ROLE-04": (
        "The QA role independently verifies each acceptance criterion and "
        "emits test_report.json and a machine-readable verdict.json; it may "
        "modify only tests, fixtures, and test utilities",
        ("tests/db/test_four_role_pipeline.py",),
    ),
    "ROLE-06": (
        "The QA verdict (pass/fail per criterion, issues with severity) is "
        "the machine input to the orchestrator's next decision; free-form "
        "prose alone never drives a transition",
        (
            "tests/db/test_artifact_schema_violation_fails_role.py",
            "tests/unit/test_artifact_models.py",
        ),
    ),
    "CTX-01": (
        "A ContextBuilder produces role-specific RoleContext (task, role "
        "instructions, relevant prior artifacts, README/AGENTS.md/CLAUDE.md, "
        "architecture docs, human answers, constraints, permitted "
        "capabilities)",
        ("tests/unit/test_context_builder.py",),
    ),
    "CTX-02": (
        "Context preparation does not copy the whole repository into the "
        "prompt; the agent inspects the repository itself",
        ("tests/unit/test_no_tree_walk.py",),
    ),
    "CTX-03": (
        "Optional few-shot examples referenced from role configuration are "
        "included as context only, never as application logic",
        ("tests/unit/test_context_builder.py",),
    ),
    "CTX-04": (
        "On a retry, the rebuilt context does not leak stale artifacts from "
        "a superseded attempt",
        ("tests/db/test_context_builder_retry_isolation.py",),
    ),
    "ART-01": (
        "Run artifacts are stored on the filesystem under "
        ".dark-factory/runs/<run-id>/ (input/, artifacts/<role>/, "
        "verification/, logs/)",
        (
            "tests/unit/test_artifact_paths.py",
            "tests/db/test_artifact_persistence.py",
        ),
    ),
    "ART-02": (
        "Machine-consumed decisions are emitted as structured JSON; human "
        "documentation may be Markdown; where orchestration depends on a "
        "result, the JSON contract is authoritative",
        (
            "tests/db/test_artifact_handoff.py",
            "tests/db/test_artifact_schema_violation_fails_role.py",
        ),
    ),
    "ART-03": (
        "Each artifact is recorded in Neon as an ArtifactReference (id, "
        "run_id, role_execution_id, type, path, metadata, created_at); Neon "
        "stores references, the filesystem stores content",
        ("tests/db/test_artifact_persistence.py",),
    ),
    "STATE-05": (
        "An artifacts table persists artifact metadata",
        ("tests/db/test_artifact_persistence.py",),
    ),
}

_PHASE_4_CRITERIA = {"SC1", "SC2", "SC3", "SC4", "SC5"}
_PHASE_4_REQUIREMENT_IDS = {
    "INTAKE-02",
    "ORCH-04",
    "ROLE-01",
    "ROLE-02",
    "ROLE-03",
    "ROLE-04",
    "ROLE-06",
    "CTX-01",
    "CTX-02",
    "CTX-03",
    "CTX-04",
    "ART-01",
    "ART-02",
    "ART-03",
    "STATE-05",
}

# Every per-requirement proof file 04-VALIDATION.md's verification map names.
# Held here verbatim so the acceptance gate and the validation strategy
# document cannot drift apart unnoticed (plan 04-04, key_links drift guard).
_VALIDATION_PROOF_FILES: frozenset[str] = frozenset(
    {
        "tests/unit/test_loaders.py",
        "tests/integration/test_spec_source_starts_a_run.py",
        "tests/db/test_four_role_pipeline.py",
        "tests/unit/test_context_builder.py",
        "tests/db/test_context_builder_retry_isolation.py",
        "tests/db/test_artifact_persistence.py",
        "tests/db/test_artifact_schema_violation_fails_role.py",
        "tests/db/test_artifact_handoff.py",
        "tests/unit/test_artifact_models.py",
        "tests/unit/test_no_tree_walk.py",
        "tests/unit/test_artifact_paths.py",
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


def test_every_phase_4_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == _PHASE_4_CRITERIA, (
        "the acceptance gate must map exactly the five Phase 4 success "
        f"criteria; got {sorted(SUCCESS_CRITERIA)}"
    )


def test_every_phase_4_requirement_id_is_mapped() -> None:
    assert set(REQUIREMENTS) == _PHASE_4_REQUIREMENT_IDS, (
        "the acceptance gate must map exactly the fifteen Phase 4 "
        "requirement ids (INTAKE-02, ORCH-04, ROLE-01..04, ROLE-06, "
        "CTX-01..04, ART-01..03, STATE-05); got "
        f"{sorted(REQUIREMENTS)}"
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
        "04-VALIDATION.md names these per-requirement proof files but the "
        "acceptance gate does not map them (the two documents have "
        "drifted): " + ", ".join(uncovered)
    )
