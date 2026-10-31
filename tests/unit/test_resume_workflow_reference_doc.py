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

from tests.support.live_runtime import LIVE_RUNTIMES, LiveRuntime

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README_PATH = _REPO_ROOT / "README.md"

# These two sentinel strings and the README's own local -> CI handoff section
# (Task 1 of this plan) must agree -- either file changing alone, without the
# other, is the drift this guard exists to catch.
_SENTINEL_BEGIN = "<!-- resume-workflow-reference: begin -->"
_SENTINEL_END = "<!-- resume-workflow-reference: end -->"

# The "Finish a run in CI" section's own heading and the next top-level
# heading after it (11-07, G-11-2). Module-level constants beside the
# sentinels above for the same reason: a future README restructure that
# renames either heading must fail this guard loudly, here, rather than
# silently narrowing _ci_handoff_section()'s search region to the wrong text.
_CI_HANDOFF_SECTION_HEADING = "## Finish a run in CI — the local → CI handoff"
_CI_HANDOFF_SECTION_NEXT_HEADING = "## Configuration reference"

# The exact phrase Task 1's commented install-guidance step names itself with
# (its "- name:" line in the reference workflow). Chosen as the load-bearing
# substring for test_the_install_guidance_precedes_the_resume_step below --
# see that test's docstring for the full reasoning.
_INSTALL_GUIDANCE_SUBSTRING = "Install the worker runtime"

# The exact permissions mapping the reference workflow's job token must
# declare, in this order. YAML parses the hyphenated key `pull-requests` as
# a plain string key, so no normalisation is needed before comparing it
# against a parsed mapping.
_EXPECTED_PERMISSIONS: dict[str, str] = {
    "contents": "write",
    "issues": "write",
    "pull-requests": "write",
}


def _ci_handoff_section() -> str:
    """Return the text of the "Finish a run in CI" section, bounded by its
    own heading and the next top-level heading in README.md.

    Raises an ``AssertionError`` naming what it looked for and did not find,
    mirroring :func:`_extract_reference_workflow_yaml`'s existing refusal to
    return an empty string on a failed extraction -- a silently-empty
    section here would make the binary/credential assertions below pass
    against nothing (see test_the_ci_handoff_section_extractor_is_non_vacuous).
    """
    text = _README_PATH.read_text(encoding="utf-8")
    assert _CI_HANDOFF_SECTION_HEADING in text, (
        f"expected to find heading {_CI_HANDOFF_SECTION_HEADING!r} in README.md"
    )
    _, _, after_heading = text.partition(_CI_HANDOFF_SECTION_HEADING)
    assert _CI_HANDOFF_SECTION_NEXT_HEADING in after_heading, (
        f"expected to find heading {_CI_HANDOFF_SECTION_NEXT_HEADING!r} "
        "after the CI handoff section's own heading in README.md"
    )
    section, _, _ = after_heading.partition(_CI_HANDOFF_SECTION_NEXT_HEADING)
    return section


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
        "the exact name the documented 'gh workflow run resume.yml "
        f"-f run_id=<id>' command passes, found: {list(inputs)!r}"
    )
    run_id_input = inputs["run_id"]
    assert run_id_input.get("required") is True, (
        f"expected the run_id input to be marked required, got: {run_id_input!r}"
    )


def test_the_reference_workflow_declares_an_optional_answer_input() -> None:
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    trigger = _trigger_block(workflow)

    dispatch = trigger["workflow_dispatch"] or {}
    inputs = dispatch.get("inputs") or {}
    assert "answer" in inputs, (
        "expected an answer input under workflow_dispatch.inputs -- the "
        "documented 'gh workflow run resume.yml -f run_id=<id> -f "
        f"answer=<text>' command needs it declared, found: {list(inputs)!r}"
    )
    answer_input = inputs["answer"]
    assert answer_input.get("required") is False, (
        f"expected the answer input to be marked optional, got: {answer_input!r}"
    )
    assert answer_input.get("type") == "string", (
        f"expected the answer input's type to be 'string', got: {answer_input!r}"
    )


def test_the_reference_workflow_resumes_exactly_once() -> None:
    """D-03: the reference workflow binds ``inputs.run_id`` through the
    resume step's own ``env:`` block (the standard hardening against
    expression injection from a ``workflow_dispatch`` input) rather than
    interpolating ``${{ inputs.run_id }}`` directly into the ``run:`` text --
    so this guard reads the step's combined ``run`` + ``env`` text, not
    ``run`` alone, or it would reject the hardened shape it is meant to
    accept. The "exactly one step" count and the "not a literal id" intent
    are both unchanged."""
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    jobs = workflow.get("jobs") or {}
    assert jobs, "expected at least one job in the reference workflow"

    resume_steps: list[dict[str, Any]] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if isinstance(run, str) and "dark-factory resume" in run:
                resume_steps.append(step)

    assert len(resume_steps) == 1, (
        "expected exactly one step invoking 'dark-factory resume', found "
        f"{len(resume_steps)}: {resume_steps!r}"
    )
    (resume_step,) = resume_steps
    combined_text = str(resume_step.get("run", "")) + str(resume_step.get("env", {}))
    assert "inputs.run_id" in combined_text, (
        "expected the resume step's run text or env block to reference the "
        "workflow input expression (the 'inputs.' or 'github.event.inputs.' "
        f"form), not a literal id, got: {resume_step!r}"
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


def test_the_reference_workflow_grants_exactly_the_needed_permissions() -> None:
    """The job's token authority is bounded by exactly this `permissions:`
    mapping -- asserted as a whole-mapping equality, not a per-key
    containment loop, so this guard is bidirectional. A containment check
    would catch under-scoping (today's gap: `contents: write` alone) but
    would silently tolerate a later widening, which is the more dangerous
    direction for a credential-scoping block that a deployer copies verbatim
    into their own repository.

    The mapping is deliberately minimal: each scope corresponds to one of
    the job's own REST calls -- `contents` for the post-role push, `issues`
    for the clarification comment posted when a role reaches
    ROLE_NEEDS_INPUT, `pull-requests` for the PR opened after QA PASS plus
    Quality Gate PASS. The `actions` scope is absent by design: nothing in
    Dark Factory dispatches a workflow at all -- the dispatch is a human
    action (`gh workflow run resume.yml -f run_id=<id> -f answer=<text>`)
    outside any job's token, not a call this or any other job's credential
    needs to cover.
    """
    workflow = yaml.safe_load(_extract_reference_workflow_yaml())
    observed = workflow.get("permissions")
    assert observed == _EXPECTED_PERMISSIONS, (
        f"expected the reference workflow's permissions mapping to equal "
        f"{_EXPECTED_PERMISSIONS!r} exactly, got {observed!r}"
    )


def test_the_ci_handoff_section_extractor_is_non_vacuous() -> None:
    """A broken extractor that returned an empty (or whitespace-only) region
    would make the two parametrized tests below pass vacuously -- zero
    runtimes to check, trivially satisfied. This guards against that failure
    mode directly, the same way the existing jobs-emptiness checks above
    guard the YAML-based assertions."""
    section = _ci_handoff_section()
    assert section.strip(), (
        "expected the CI handoff section (bounded by "
        f"{_CI_HANDOFF_SECTION_HEADING!r} and "
        f"{_CI_HANDOFF_SECTION_NEXT_HEADING!r}) to be non-empty"
    )


@pytest.mark.parametrize(
    "runtime",
    LIVE_RUNTIMES.values(),
    ids=[runtime.worker_name for runtime in LIVE_RUNTIMES.values()],
)
def test_the_ci_handoff_section_names_every_worker_binary(runtime: LiveRuntime) -> None:
    """Derived from LIVE_RUNTIMES by parametrization (11-07, G-11-2, T-11-31):
    registering a fourth adapter there turns this into a failing case, named
    by its own worker, until README documents the new binary."""
    section = _ci_handoff_section()
    assert runtime.binary in section, (
        f"expected the worker-runtime binary {runtime.binary!r} (required by "
        f"the {runtime.worker_name!r} worker) to be named in README's "
        f"{_CI_HANDOFF_SECTION_HEADING!r} section -- a deployer assigning a "
        "role to this worker needs to know, at the copy-paste site, which "
        "binary must end up on PATH"
    )


@pytest.mark.parametrize(
    "runtime",
    LIVE_RUNTIMES.values(),
    ids=[runtime.worker_name for runtime in LIVE_RUNTIMES.values()],
)
def test_the_ci_handoff_section_names_every_worker_credential(
    runtime: LiveRuntime,
) -> None:
    """Distinct from the binary test above on purpose: live_runtime.py's own
    skip_reason() treats "binary absent" and "credential absent" as
    separately diagnosable preconditions, and collapsing the two checks into
    one is the exact mistake that produced G-11-2 (README named a credential
    but never a binary).

    Scoped to the worker's own table row, not the whole section: ``hermes``
    shares its credential (``ANTHROPIC_API_KEY``) with ``claude-code``, so a
    whole-section substring check would still pass if the ``hermes`` row were
    deleted outright -- the credential string would still be found via
    ``claude-code``'s row. Scoping to the row that names this worker closes
    that gap; the binary test already catches a deleted row via the binary
    name, which is unique per worker."""
    section = _ci_handoff_section()
    credential_env_var = runtime.credential_field.upper()
    worker_rows = [
        line for line in section.splitlines() if f"`{runtime.worker_name}`" in line
    ]
    assert worker_rows, (
        f"expected a table row naming the {runtime.worker_name!r} worker in "
        f"README's {_CI_HANDOFF_SECTION_HEADING!r} section"
    )
    assert any(credential_env_var in line for line in worker_rows), (
        f"expected the credential environment variable {credential_env_var!r} "
        f"(required by the {runtime.worker_name!r} worker) on its own row in "
        f"README's {_CI_HANDOFF_SECTION_HEADING!r} section"
    )


def test_the_install_guidance_precedes_the_resume_step() -> None:
    """Asserted on the raw extracted block text, not the parsed YAML, because
    the worker-runtime install guidance is a YAML comment and
    ``yaml.safe_load`` discards comments entirely -- parsing the block first
    would make the guidance invisible to this guard.

    The load-bearing substring this test keys on is
    ``_INSTALL_GUIDANCE_SUBSTRING`` (``"Install the worker runtime"``): the
    name Task 1 gives the commented-out install step in the reference
    workflow. It is matched as a substring of a line, not a whole-line
    equality, so ordinary rewording of the step's explanatory comments does
    not break this guard -- while deleting the step, or renaming it away
    from "worker runtime", does. The next editor of README should treat this
    phrase as load-bearing, the same way the module docstring already
    documents the sentinel strings as load-bearing.
    """
    raw = _extract_reference_workflow_yaml()
    lines = raw.splitlines()

    guidance_indices = [
        index for index, line in enumerate(lines) if _INSTALL_GUIDANCE_SUBSTRING in line
    ]
    assert guidance_indices, (
        f"expected a line containing {_INSTALL_GUIDANCE_SUBSTRING!r} in the "
        "reference workflow block (the commented worker-runtime install "
        "guidance)"
    )

    resume_indices = [
        index for index, line in enumerate(lines) if "dark-factory resume" in line
    ]
    assert resume_indices, (
        "expected a line invoking 'dark-factory resume' in the reference workflow block"
    )

    assert max(guidance_indices) < min(resume_indices), (
        "expected the worker-runtime install guidance (found at line(s) "
        f"{guidance_indices!r}) to precede the 'dark-factory resume' "
        f"invocation (found at line(s) {resume_indices!r})"
    )
