"""Doc-drift guard for the README's ``resume.yml`` reference workflow (11-05).

``resume.yml`` is the one artifact of this phase that Dark Factory does not
ship, cannot enforce and does not execute (11-CONTEXT.md D-04) -- a deployer
copies the README's block into their own repository. The only thing standing
between that reference and silent rot is a check that it still parses and
still says what the dispatcher actually sends.

The second, more important reason this test exists: the ``if``-free
assertion below is the documentation half of this phase's "a trigger carries
zero lifecycle logic" invariant (mirrored in production code by
``tests/unit/test_trigger_carries_no_lifecycle_logic.py``). A reference
workflow that grew a branch on run state would teach every future deployer
to put orchestration in the trigger -- exactly the shape this phase exists
to rule out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README_PATH = _REPO_ROOT / "README.md"
_ENV_EXAMPLE_PATH = _REPO_ROOT / ".env.example"

# These two sentinel strings and the README's own local -> CI handoff section
# (Task 1 of this plan) must agree -- either file changing alone, without the
# other, is the drift this guard exists to catch.
_SENTINEL_BEGIN = "<!-- resume-workflow-reference: begin -->"
_SENTINEL_END = "<!-- resume-workflow-reference: end -->"

_DISPATCH_TOKEN_NAME = "DISPATCH_GITHUB_TOKEN"


def _extract_reference_workflow_yaml() -> str:
    """Return the fenced YAML block between the sentinel comments in
    README.md, stripped of the surrounding markdown fence lines.

    Raises an ``AssertionError`` naming the observed sentinel count when it
    is not exactly one of each, rather than returning an empty string that
    would make every downstream test fail confusingly for a reason unrelated
    to the workflow's own correctness.
    """
    text = _README_PATH.read_text(encoding="utf-8")
    begin_count = text.count(_SENTINEL_BEGIN)
    end_count = text.count(_SENTINEL_END)
    assert begin_count == 1 and end_count == 1, (
        f"expected exactly one {_SENTINEL_BEGIN!r} and one {_SENTINEL_END!r} "
        f"in README.md, found {begin_count} begin sentinel(s) and "
        f"{end_count} end sentinel(s)"
    )
    _, _, after_begin = text.partition(_SENTINEL_BEGIN)
    inner, _, _ = after_begin.partition(_SENTINEL_END)
    lines = inner.strip("\n").splitlines()
    assert lines and lines[0].strip().startswith("```"), (
        "expected a fenced code block immediately inside the sentinels, "
        f"got: {lines[:1]!r}"
    )
    assert lines[-1].strip().startswith("```"), (
        "expected the fenced code block to close immediately before the "
        f"end sentinel, got: {lines[-1:]!r}"
    )
    return "\n".join(lines[1:-1])


def _trigger_block(workflow: dict[Any, Any]) -> dict[str, Any]:
    """Return the workflow's trigger mapping, looked up under the string
    key ``"on"`` and then under the boolean key ``True``.

    YAML 1.1 parses a bare ``on:`` key as the boolean ``True`` -- this
    repository's own ``ci.yml`` quotes the key (``"on":``) to avoid it, and
    the reference workflow is written to do the same, but this lookup must
    tolerate both spellings or it fails for a reason unrelated to whether
    the workflow itself is correct.
    """
    if "on" in workflow:
        result = workflow["on"]
    elif True in workflow:
        result = workflow[True]
    else:
        raise AssertionError(
            f"workflow declares no trigger under 'on' or True: keys={list(workflow)!r}"
        )
    assert isinstance(result, dict), (
        f"expected the trigger block to be a mapping, got {type(result)!r}"
    )
    return result


def test_the_reference_workflow_parses_as_yaml() -> None:
    raw = _extract_reference_workflow_yaml()
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict), (
        f"expected the extracted block to parse as a mapping (a workflow), "
        f"got {type(parsed)!r}: {parsed!r}"
    )


def test_the_reference_workflow_declares_a_run_id_input() -> None:
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    trigger = _trigger_block(workflow)

    assert "workflow_dispatch" in trigger, (
        f"expected a workflow_dispatch trigger, found: {list(trigger)!r}"
    )
    dispatch = trigger["workflow_dispatch"] or {}
    inputs = dispatch.get("inputs") or {}
    assert "run_id" in inputs, (
        "expected a run_id input under workflow_dispatch.inputs -- this is "
        "the exact name plan 11-01's dispatch_workflow sends, found: "
        f"{list(inputs)!r}"
    )
    run_id_input = inputs["run_id"]
    assert run_id_input.get("required") is True, (
        f"expected the run_id input to be marked required, got: {run_id_input!r}"
    )


def test_the_reference_workflow_resumes_exactly_once() -> None:
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    jobs = workflow.get("jobs") or {}
    assert jobs, "expected at least one job in the reference workflow"

    resume_runs: list[str] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if isinstance(run, str) and "dark-factory resume" in run:
                resume_runs.append(run)

    assert len(resume_runs) == 1, (
        "expected exactly one step invoking 'dark-factory resume', found "
        f"{len(resume_runs)}: {resume_runs!r}"
    )
    (resume_run,) = resume_runs
    assert "inputs.run_id" in resume_run, (
        "expected the resume step's run value to reference the workflow "
        "input expression (the 'inputs.' or 'github.event.inputs.' form), "
        f"not a literal id, got: {resume_run!r}"
    )


def test_the_reference_workflow_carries_no_run_state_branch() -> None:
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    jobs = workflow.get("jobs") or {}
    # Guard against a broken extractor vacuously satisfying the emptiness
    # assertion below: a walk over zero jobs would trivially find zero `if`
    # keys and pass for the wrong reason.
    assert jobs, "expected at least one job in the reference workflow"

    branching: list[str] = []
    for job_name, job in jobs.items():
        if "if" in job:
            branching.append(f"job {job_name!r}")
        for index, step in enumerate(job.get("steps") or []):
            if "if" in step:
                branching.append(f"job {job_name!r} step {index}")

    assert not branching, (
        "the reference workflow is a trigger and must carry zero lifecycle "
        "logic -- a job or step that branches on 'if' has started deciding "
        "what happens next, and the only decider is advance(). Found: "
        f"{branching!r}"
    )


def test_the_dispatch_credential_is_named_consistently() -> None:
    readme_text = _README_PATH.read_text(encoding="utf-8")
    env_example_text = _ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert _DISPATCH_TOKEN_NAME in readme_text, (
        f"expected {_DISPATCH_TOKEN_NAME!r} to appear in README.md"
    )
    assert _DISPATCH_TOKEN_NAME in env_example_text, (
        f"expected {_DISPATCH_TOKEN_NAME!r} to appear in .env.example"
    )
