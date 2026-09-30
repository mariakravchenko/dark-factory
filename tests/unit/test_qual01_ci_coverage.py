"""'Covered' means 'CI ran it' -- the guard that keeps QUAL-01 honest.

    QUAL-01 (``.planning/REQUIREMENTS.md``): "Orchestration behavior is
    tested end-to-end with `FakeWorker` -- role transitions, artifact
    handoffs, pause/resume, QA rejection, Developer retries, quality-gate
    retries, failure limits, publishing -- with no external AI calls"

A coverage claim that cannot be traced to a command CI actually runs is a
claim about a file, not about behaviour. 11-CONTEXT.md D-05 turns the `db`
marker tier on in ``.github/workflows/ci.yml`` for the first time; D-07
deliberately chose no new consolidated orchestration test file over
rewriting the ~177 existing ``tests/db/`` tests that already prove QUAL-01's
eight scenarios -- which is exactly why the claim needs a map from the
requirement's own words to the modules that back them, rather than a single
file to point at.

This module is itself a source-and-config guard: no database, no
subprocess, no pytest-inside-pytest. It runs in the fast ``unit`` tier,
which CI has always selected, so it cannot be disabled by the same edit
that would disable the thing it guards (T-11-15).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DB_TESTS_DIR = _REPO_ROOT / "tests" / "db"
_CI_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The eight scenario nouns transcribed verbatim from QUAL-01's own wording
# (.planning/REQUIREMENTS.md). Adding a key here means QUAL-01's wording
# changed -- the requirement text is the thing to re-read first, not this
# constant.
_QUAL01_SCENARIO_NOUNS = frozenset(
    {
        "role transitions",
        "artifact handoffs",
        "pause/resume",
        "QA rejection",
        "Developer retries",
        "quality-gate retries",
        "failure limits",
        "publishing",
    }
)

# Source: 11-RESEARCH.md's "Phase Requirements -> Test Map" (under
# "Validation Architecture") -- the researcher's already-completed
# scenario-to-module audit. Every module below carries the `db` marker and
# already exists on disk (Phases 4-10); this map covers only that stable
# surface. Do NOT add tests/db/test_cross_machine_resume.py or
# tests/db/test_webhook_dispatches_resume.py here -- both are created by
# sibling plans in this same phase, and a guard whose green depends on
# another plan's completion order is a false failure waiting to happen.
_QUAL01_SCENARIOS: dict[str, tuple[str, ...]] = {
    "role transitions": (
        "test_four_role_pipeline.py",
        "test_transition_atomic.py",
    ),
    "artifact handoffs": ("test_artifact_handoff.py",),
    "pause/resume": (
        "test_pause_mechanism_generic.py",
        "test_resume_first_advance.py",
    ),
    "QA rejection": ("test_qa_bounce.py",),
    "Developer retries": ("test_feedback_reaches_developer.py",),
    "quality-gate retries": ("test_quality_gate_gates_the_run.py",),
    "failure limits": (
        "test_iteration_cap_exhaustion.py",
        "test_loop04_adjacency.py",
    ),
    "publishing": (
        "test_publish_step.py",
        "test_publish_idempotency.py",
    ),
}


def test_every_qual01_scenario_maps_to_a_module_that_exists() -> None:
    missing: list[str] = []
    for scenario, modules in _QUAL01_SCENARIOS.items():
        for module in modules:
            if not (_DB_TESTS_DIR / module).is_file():
                missing.append(f"{scenario!r} -> tests/db/{module} (not found)")
    assert not missing, (
        "QUAL-01 scenario map names a module that does not exist on disk:\n  "
        + "\n  ".join(missing)
    )


def _pytestmark_names_db(node: ast.AST) -> bool:
    """True if an assignment's value source-text mentions ``pytest.mark.db``.

    Handles both real forms in this tree: a bare ``pytest.mark.db`` and a
    list such as ``[pytest.mark.db, pytest.mark.usefixtures("...")]``.
    """
    dumped = ast.dump(node)
    return "id='pytest'" in dumped and "attr='db'" in dumped and "attr='mark'" in dumped


def _module_has_db_marker(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Name)]
        if not any(t.id == "pytestmark" for t in targets):
            continue
        if _pytestmark_names_db(node.value):
            return True
    return False


def test_every_mapped_module_carries_the_db_marker() -> None:
    offenders: list[str] = []
    seen: set[str] = set()
    for modules in _QUAL01_SCENARIOS.values():
        for module in modules:
            if module in seen:
                continue
            seen.add(module)
            path = _DB_TESTS_DIR / module
            if not path.is_file():
                # Reported by test_every_qual01_scenario_maps_to_a_module_that_exists.
                continue
            if not _module_has_db_marker(path):
                offenders.append(
                    f"tests/db/{module} has no module-level `pytestmark` "
                    "assignment naming pytest.mark.db"
                )
    assert not offenders, (
        "QUAL-01-mapped module(s) are not selected by `-m db` at all:\n  "
        + "\n  ".join(offenders)
    )


def test_the_scenario_keys_are_qual01s_own_words() -> None:
    assert set(_QUAL01_SCENARIOS) == _QUAL01_SCENARIO_NOUNS, (
        "The QUAL-01 scenario map's keys drifted from the requirement's own "
        "wording -- edit both the map and _QUAL01_SCENARIO_NOUNS together, "
        "in view of .planning/REQUIREMENTS.md's QUAL-01 text, so a scenario "
        "cannot be silently dropped from the map without also shrinking the "
        "claim of what QUAL-01 requires.\n"
        f"map keys:   {sorted(_QUAL01_SCENARIOS)}\n"
        f"QUAL-01 nouns: {sorted(_QUAL01_SCENARIO_NOUNS)}"
    )


def test_ci_runs_the_database_tier() -> None:
    workflow = yaml.safe_load(_CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["quality"]["steps"]
    run_strings = [step.get("run", "") for step in steps if "run" in step]

    selects_db = any(
        "-m" in run and "db" in run.split("-m", 1)[1] for run in run_strings
    )
    selects_integration = any("integration" in run for run in run_strings)

    assert selects_db, (
        "No step in .github/workflows/ci.yml's `quality` job invokes pytest "
        "with a marker selector naming `db` -- the FakeWorker orchestration "
        "suite QUAL-01 claims coverage for would silently never run in CI. "
        f"Steps' run strings: {run_strings!r}"
    )
    assert not selects_integration, (
        "A step in .github/workflows/ci.yml's `quality` job selects the "
        "`integration` marker -- that tier drives real agent CLIs whose "
        "credentials the hosted runner does not have (11-CONTEXT.md D-05). "
        f"Steps' run strings: {run_strings!r}"
    )
