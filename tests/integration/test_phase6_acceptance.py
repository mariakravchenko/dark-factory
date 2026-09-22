"""The Phase 6 acceptance gate.

Each of the five Phase 6 success criteria (``.planning/ROADMAP.md`` ->
"Phase 6: Tools, Permissions & the Credential Boundary" -> Success Criteria)
and each of the seven Phase 6 requirement ids (``.planning/REQUIREMENTS.md``:
TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, SEC-01, SEC-03) is mapped here,
by name, to the test file or files that prove it.

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

It is a **sibling** of ``tests/integration/test_phase5_acceptance.py``,
``tests/integration/test_phase4_acceptance.py``,
``tests/integration/test_phase3_acceptance.py``,
``tests/integration/test_phase2_acceptance.py`` and
``tests/integration/test_phase_acceptance.py``, not an extension of any of
them: each phase's gate asserts its own mapping is exactly that phase's
criteria and each should be independently readable.

The proof-file set below is drift-guarded against
``06-VALIDATION.md``'s Per-Task Verification Map (the Phase 2/3/4/5 gates'
own established pattern): a proof renamed in one place and not the other is
a failure here, not a silent divergence. Unlike the Phase 2-5 precedent's
one-directional "the validation doc names nothing the gate doesn't map"
check, this gate asserts full set **equality** in both directions -- a file
added to one document and not the other fails here either way.
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
        "A role invoking a capability it was not granted is denied by the "
        "registry (deny-by-default) and the denial is persisted as an "
        "event; BA and Architect cannot write source, Developer can write "
        "and shell, QA can write tests and shell but cannot publish.",
        (
            "tests/unit/test_tool_registry.py",
            "tests/db/test_capability_denied_fails_role.py",
        ),
    ),
    "SC2": (
        "Dumping a worker subprocess environment shows no `DATABASE_URL`, "
        "no `GITHUB_TOKEN`, and no unrelated key inherited from the Dark "
        "Factory process -- only the allowlisted minimum plus that "
        "worker's own credential.",
        (
            "tests/integration/test_worker_env_boundary.py",
            "tests/unit/test_worker_env.py",
        ),
    ),
    "SC3": (
        "A new capability is added to the `ToolRegistry` and granted to "
        "one role without editing any role executor.",
        ("tests/unit/test_tool_registry_extensibility.py",),
    ),
    "SC4": (
        "Grepping every role artifact, worker prompt, event payload, log "
        "and report for the known secret values returns zero occurrences.",
        (
            "tests/integration/test_capability_denial_no_secret_leak.py",
            "tests/integration/test_secret_redaction_e2e.py",
        ),
    ),
    "SC5": (
        "Tools are exposed to a compatible worker over the optional MCP "
        "transport, and removing MCP entirely leaves the orchestrator "
        "fully functional -- core code imports nothing from MCP.",
        (
            "tests/unit/test_mcp_adapter.py",
            "tests/unit/test_no_mcp_import_in_core.py",
        ),
    ),
}

# requirement id -> (REQUIREMENTS.md text verbatim, tuple of proof files
# relative to the repository root).
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    # A-06-01 (carried from 06-01-PLAN.md, D-04): this phase registers the
    # seven capabilities the shipped role YAMLs actually grant
    # (repo.read/search/write/write_tests, shell.execute,
    # artifacts.read/write). The `git.status/diff/history`,
    # `github.issue.read` and `github.comments.read` names this
    # requirement's text also enumerates are deferred to Phase 9/Phase 10,
    # which are what first need them -- so this mapping proves the
    # seven-capability claim the phase actually shipped, rather than
    # letting a partially-satisfied requirement look complete.
    "TOOL-01": (
        "A `ToolRegistry` provides the capability layer "
        "(`repo.read/search/write/write_tests`, `shell.execute`, "
        "`git.status/diff/history`, `github.issue.read`, "
        "`github.comments.read`, `artifacts.read/write`)",
        (
            "tests/unit/test_tool_registry.py",
            "tests/db/test_capability_denied_fails_role.py",
        ),
    ),
    "TOOL-02": (
        "New tools can be added to the registry without modifying every role executor",
        (
            "tests/unit/test_tool_registry_extensibility.py",
            "tests/unit/test_native_tool_contract.py",
        ),
    ),
    "TOOL-03": (
        "Each role receives only its explicitly configured tools; grants "
        "are deny-by-default (BA/Architect read-only on code; Developer "
        "write + shell; QA write_tests + shell, no publish)",
        (
            "tests/unit/test_tool_registry.py",
            "tests/unit/test_shell_execute.py",
        ),
    ),
    "TOOL-04": (
        "A worker's subprocess environment is built from an explicit "
        "allowlist; infrastructure credentials (`DATABASE_URL`, "
        "`GITHUB_TOKEN`, worker credentials) are never passed to a worker",
        (
            "tests/unit/test_worker_env.py",
            "tests/unit/test_no_environ_copy.py",
            "tests/integration/test_worker_env_boundary.py",
        ),
    ),
    "TOOL-05": (
        "MCP is supported as one optional transport adapter for exposing "
        "tools to compatible workers; the orchestrator has no internal "
        "dependency on MCP",
        (
            "tests/unit/test_mcp_adapter.py",
            "tests/unit/test_no_mcp_import_in_core.py",
        ),
    ),
    "SEC-01": (
        "`DATABASE_URL`, GitHub credentials, and worker credentials never "
        "appear in role artifacts, worker prompts, Neon event payloads, "
        "GitHub comments, logs, or test reports",
        (
            "tests/integration/test_capability_denial_no_secret_leak.py",
            "tests/integration/test_secret_redaction_e2e.py",
        ),
    ),
    "SEC-03": (
        "A worker subprocess does not inherit the full Dark Factory "
        "process environment; it receives only the minimum required for "
        "its role",
        (
            "tests/integration/test_worker_env_boundary.py",
            "tests/unit/test_shell_execute.py",
        ),
    ),
}

_PHASE_6_CRITERIA = {"SC1", "SC2", "SC3", "SC4", "SC5"}
_PHASE_6_REQUIREMENT_IDS = {
    "TOOL-01",
    "TOOL-02",
    "TOOL-03",
    "TOOL-04",
    "TOOL-05",
    "SEC-01",
    "SEC-03",
}

# Every proof file 06-VALIDATION.md's Per-Task Verification Map names,
# mirrored here so the acceptance gate and the validation strategy document
# cannot drift apart unnoticed (Phase 2/3/4/5 gates' established pattern).
_VALIDATION_PROOF_FILES: frozenset[str] = frozenset(
    {
        "tests/unit/test_tool_registry.py",
        "tests/db/test_capability_denied_fails_role.py",
        "tests/unit/test_tool_registry_extensibility.py",
        "tests/unit/test_native_tool_contract.py",
        "tests/unit/test_shell_execute.py",
        "tests/unit/test_worker_env.py",
        "tests/unit/test_no_environ_copy.py",
        "tests/integration/test_worker_env_boundary.py",
        "tests/unit/test_mcp_adapter.py",
        "tests/unit/test_no_mcp_import_in_core.py",
        "tests/integration/test_capability_denial_no_secret_leak.py",
        "tests/integration/test_secret_redaction_e2e.py",
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


def test_every_phase_6_success_criterion_is_mapped() -> None:
    assert set(SUCCESS_CRITERIA) == _PHASE_6_CRITERIA, (
        "the acceptance gate must map exactly the five Phase 6 success "
        f"criteria; got {sorted(SUCCESS_CRITERIA)}"
    )


def test_every_phase_6_requirement_id_is_mapped() -> None:
    assert set(REQUIREMENTS) == _PHASE_6_REQUIREMENT_IDS, (
        "the acceptance gate must map exactly the seven Phase 6 requirement "
        f"ids (TOOL-01..05, SEC-01, SEC-03); got {sorted(REQUIREMENTS)}"
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


def test_no_criterion_or_requirement_maps_to_an_empty_tuple() -> None:
    for criterion, (_text, proof_files) in SUCCESS_CRITERIA.items():
        assert proof_files, f"{criterion} maps to an empty proof tuple"
    for requirement, (_text, proof_files) in REQUIREMENTS.items():
        assert proof_files, f"{requirement} maps to an empty proof tuple"


def test_validation_strategy_and_gate_cannot_drift() -> None:
    mapped = _all_mapped_paths()
    only_in_validation = sorted(_VALIDATION_PROOF_FILES - mapped)
    only_in_gate = sorted(mapped - _VALIDATION_PROOF_FILES)
    assert not only_in_validation and not only_in_gate, (
        "06-VALIDATION.md's Per-Task Verification Map and this gate's "
        "proof-file mapping have drifted apart. "
        f"Named only in 06-VALIDATION.md: {only_in_validation}. "
        f"Mapped only in this gate: {only_in_gate}."
    )
