"""QUAL-04 / ROADMAP SC4: prove the CI wiring itself cannot silently rot.

``tests/unit/test_no_worker_name_leak.py`` is the worker-name leak guard.
SC4 is about a *build* failing when the guard trips, not a local pytest run
passing -- so this module structurally verifies ``.github/workflows/ci.yml``
still gates on that guard. If the leak-guard step is removed, renamed away,
or made non-blocking, this module fails.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

_LEAK_GUARD_PATH = "tests/unit/test_no_worker_name_leak.py"
# `db` is deliberately selected by CI as of Phase 11 (11-CONTEXT.md D-05,
# 11-04-PLAN.md) -- the FakeWorker orchestration suite (QUAL-01) now runs on
# the hosted runner's own Docker via testcontainers. `integration` stays
# excluded: it drives real agent CLIs whose credentials the hosted runner
# does not have, unrelated to database availability.
_EXCLUDED_MARKERS = ("integration",)


def _load() -> dict[str, Any]:
    assert _WORKFLOW.is_file(), f"CI workflow not found at {_WORKFLOW}"
    document = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{_WORKFLOW} did not parse to a mapping"
    return document


def _quality_steps(document: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = document.get("jobs", {})
    quality = jobs.get("quality", {})
    steps = quality.get("steps", [])
    assert isinstance(steps, list)
    return steps


def _offenders(document: dict[str, Any]) -> list[str]:
    """Return human-readable reasons the CI wiring no longer gates the build
    on the worker-name leak guard. Pure -- takes an already-parsed mapping,
    touches no filesystem, so the sanity test below can feed it a synthetic
    document."""
    offenders: list[str] = []

    triggers = document.get("on") or {}
    if not isinstance(triggers, dict) or "push" not in triggers:
        offenders.append("workflow is missing a 'push' trigger")
    if not isinstance(triggers, dict) or "pull_request" not in triggers:
        offenders.append("workflow is missing a 'pull_request' trigger")

    steps = _quality_steps(document)

    if not any(_LEAK_GUARD_PATH in step.get("run", "") for step in steps):
        offenders.append(f"no step in the quality job runs {_LEAK_GUARD_PATH!r}")

    for index, step in enumerate(steps):
        if step.get("continue-on-error"):
            name = step.get("name", f"step[{index}]")
            offenders.append(f"step {name!r} sets continue-on-error to a truthy value")

    for index, step in enumerate(steps):
        run = step.get("run", "")
        if "pytest" not in run or "-m" not in run:
            continue
        for marker in _EXCLUDED_MARKERS:
            if marker in run:
                name = step.get("name", f"step[{index}]")
                offenders.append(
                    f"step {name!r} pytest invocation selects excluded "
                    f"marker {marker!r} ({run!r})"
                )

    return offenders


def test_ci_workflow_gates_on_worker_name_guard() -> None:
    document = _load()
    offenders = _offenders(document)
    assert not offenders, "CI no longer gates on the worker-name guard:\n" + "\n".join(
        offenders
    )


def test_the_guard_detects_its_own_subject() -> None:
    """A guard that cannot detect its own subject proves nothing (mirrors
    ``tests/unit/test_git_ownership_boundary.py``'s stated rationale).
    Deep-copy the real workflow, remove the leak-guard step, and assert
    ``_offenders`` notices."""
    document = copy.deepcopy(_load())
    steps = _quality_steps(document)
    remaining = [step for step in steps if _LEAK_GUARD_PATH not in step.get("run", "")]
    assert len(remaining) < len(steps), "fixture did not actually drop a step"
    document["jobs"]["quality"]["steps"] = remaining

    offenders = _offenders(document)
    assert offenders, "removing the leak-guard step should produce offenders"
