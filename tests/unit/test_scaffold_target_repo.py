"""Regression guards for ``scripts/scaffold_target_repo.py`` (261031-cp4).

This script has never had a test module. It was added only after a real
``app-int`` CI run progressed through BA -> ARCHITECTURE -> DEVELOPMENT -> QA
and then died at the Quality Gate step with::

    FileNotFoundError: No such file or directory: 'uv'

A GitHub-hosted runner image ships no ``uv`` on PATH, and neither generated
workflow (``run.yml`` / ``resume.yml``) ever installed it, even though the
scaffold's own ``DEFAULT_QUALITY_GATE_COMMANDS`` invokes ``uv run`` by
default. These three tests prove the fix and pin the reasons it must hold.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.scaffold_target_repo import (
    DEFAULT_BASE_BRANCH,
    DEFAULT_INSTALL_SOURCE,
    DEFAULT_QUALITY_GATE_COMMANDS,
    GITIGNORE_CONTENT,
    GITIGNORE_RELATIVE_PATH,
    ROLE_ORDER,
    build_contents,
    render_dark_factory_yaml,
    render_resume_workflow,
    render_run_workflow,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_SETUP_UV_PINNED_REF_PATTERN = re.compile(r"^astral-sh/setup-uv@v\d+$")
_SETUP_UV_RAW_SCANNER = re.compile(r"astral-sh/setup-uv@\S+")

_INSTALL_DARK_FACTORY_STEP_NAME = "Install dark-factory"

# 261031-fta: the exact entry the generated .gitignore must carry so the
# lockfile every default `uv run` quality-gate command regenerates is never
# reported as a changed path by `git ls-files --others --exclude-standard`.
_UV_LOCK_GITIGNORE_ENTRY = "uv.lock"

# The workflow renderers only ever read `role_workers.values()`, but the
# full four-role dict is built anyway so this fixture matches what
# `build_contents` really passes at call time.
_ROLE_WORKERS: dict[str, str] = {role: "claude-code" for role in ROLE_ORDER}

_RENDERERS = (
    pytest.param(render_run_workflow, id="run.yml"),
    pytest.param(render_resume_workflow, id="resume.yml"),
)


def _gitignore_entries(text: str) -> set[str]:
    """Parse ``.gitignore``-shaped text into the set of its entries.

    Strips each line and drops empty lines and any line beginning with a
    hash. The hash filter exists for the *robustness of this helper only* --
    the template under test has no comment line (261031-fta decision 1
    forbids one, since `_gitignore_missing_entries()` prints every non-empty
    template line, comment included, to a deployer under its "NOTE: ..."
    message, where a prose line would misread as a path).

    Membership in the returned set is git-pattern semantics: a bare
    filename (no leading slash, no trailing slash, no glob) matches at any
    depth in the tree. That is why every assertion against this set below
    is exact membership, never a substring search -- a substring search
    would also match an unrelated `nested/uv.lock.bak`-style false positive.
    """
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _job_steps(rendered_text: str) -> list[dict[str, Any]]:
    """Parse rendered workflow YAML and return its single job's steps list.

    Both templates quote the trigger key (``"on":``), and the script's own
    ``parse_check`` already proves these templates ``yaml.safe_load``
    cleanly, so no pre-processing of the ``${{ ... }}`` expressions is
    needed here.
    """
    document = yaml.safe_load(rendered_text)
    assert isinstance(document, dict), "rendered workflow did not parse to a mapping"
    jobs = document["jobs"]
    assert len(jobs) == 1, f"expected exactly one job, got {list(jobs)}"
    (job,) = jobs.values()
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


@pytest.mark.parametrize("render_fn", _RENDERERS)
def test_install_uv_step_precedes_install_dark_factory_step(render_fn: Any) -> None:
    """261031-cp4: the live app-int Quality Gate failure (`FileNotFoundError:
    No such file or directory: 'uv'`) happened because a GitHub-hosted
    runner has no uv on PATH and neither generated workflow ever installed
    it. This asserts both the uv step's presence and its position as
    STRUCTURAL list indices from `yaml.safe_load`, never as a character
    offset in the raw template string -- so a future reordering that keeps
    both strings present still fails this test.
    """
    rendered = render_fn(
        install_source=DEFAULT_INSTALL_SOURCE, role_workers=_ROLE_WORKERS
    )
    steps = _job_steps(rendered)

    uv_step_indices = [
        index
        for index, step in enumerate(steps)
        if _SETUP_UV_PINNED_REF_PATTERN.match(str(step.get("uses", "")))
    ]
    install_step_indices = [
        index
        for index, step in enumerate(steps)
        if step.get("name") == _INSTALL_DARK_FACTORY_STEP_NAME
    ]

    assert len(uv_step_indices) == 1, (
        f"expected exactly one astral-sh/setup-uv@vN step, found indices "
        f"{uv_step_indices}"
    )
    assert len(install_step_indices) == 1, (
        f"expected exactly one '{_INSTALL_DARK_FACTORY_STEP_NAME}' step, "
        f"found indices {install_step_indices}"
    )
    assert uv_step_indices[0] < install_step_indices[0], (
        "the uv install step must precede the dark-factory install step so "
        "the Quality Gate's `uv run ...` commands find uv on PATH"
    )


@pytest.mark.parametrize("render_fn", _RENDERERS)
def test_setup_uv_ref_matches_this_repository_own_ci_workflow(render_fn: Any) -> None:
    """261031-cp4: the pin is `astral-sh/setup-uv@v6`, read from this
    repository's own `ci.yml` -- generating a scaffold that trusts an older
    (or newer) major than the project's own CI would be a new, unexplained
    inconsistency. This test ties the two together so they cannot drift
    apart silently.
    """
    assert _CI_WORKFLOW_PATH.is_file(), f"ci.yml not found at {_CI_WORKFLOW_PATH}"
    ci_text = _CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    ci_refs = sorted(set(_SETUP_UV_RAW_SCANNER.findall(ci_text)))
    assert len(ci_refs) == 1, (
        f"expected ci.yml to name exactly one distinct astral-sh/setup-uv "
        f"ref, found {ci_refs}"
    )
    (expected_ref,) = ci_refs

    rendered = render_fn(
        install_source=DEFAULT_INSTALL_SOURCE, role_workers=_ROLE_WORKERS
    )
    steps = _job_steps(rendered)
    rendered_refs = sorted(
        {
            str(step["uses"])
            for step in steps
            if _SETUP_UV_PINNED_REF_PATTERN.match(str(step.get("uses", "")))
        }
    )
    assert rendered_refs == [expected_ref], (
        f"generated workflow's setup-uv ref {rendered_refs} must equal "
        f"ci.yml's own ref {expected_ref!r}"
    )


def test_default_quality_gate_commands_are_the_recorded_reason_uv_is_installed() -> (
    None
):
    """261031-cp4: `DEFAULT_QUALITY_GATE_COMMANDS` invoking `uv run` is *why*
    the install step exists at all. Binding the two here means a future
    change that moves the generated gate off uv must land in this test too,
    forcing a conscious decision about the install step rather than leaving
    it as unexplained dead weight.
    """
    assert DEFAULT_QUALITY_GATE_COMMANDS, "quality gate commands must not be empty"
    for command in DEFAULT_QUALITY_GATE_COMMANDS:
        assert command.startswith("uv run "), (
            f"expected every default quality-gate command to start with "
            f"'uv run ', got {command!r}"
        )

    rendered_yaml = render_dark_factory_yaml(
        base_branch="main",
        github_owner="example-org",
        github_repo="example-repo",
        quality_gate_commands=DEFAULT_QUALITY_GATE_COMMANDS,
    )
    document = yaml.safe_load(rendered_yaml)
    assert document["quality_gate"]["commands"] == list(DEFAULT_QUALITY_GATE_COMMANDS)


def test_gitignore_content_ignores_uv_lock() -> None:
    """261031-fta: confirmed live against a real `app-int` CI run. The
    generated `.dark-factory.yaml`'s `quality_gate.commands` default to
    `DEFAULT_QUALITY_GATE_COMMANDS` -- `uv run pytest -q` / `uv run ruff
    check .` -- and QA's own test runs inside the role also invoke `uv
    run`. Every `uv run` invocation regenerates `uv.lock` in the worktree
    root. Without this entry, that regenerated file is untracked but not
    ignored, so `git/scope.py`'s `attempt_changed_paths()` (which runs
    `git ls-files --others --exclude-standard`) reports it as a changed
    path, and `enforce_write_scope()` fails any role whose `write_scope`
    does not cover the repository root -- QA's is `['tests/**']` -- with:

        wrote outside its configured write_scope ... ['uv.lock']

    This happens even when the role's own agent explicitly deleted
    `uv.lock` before finishing, because the WIP commit snapshot had already
    captured it as present. This is NOT a bug in `attempt_changed_paths()`:
    `--exclude-standard` already honors `.gitignore` -- confirmed by reading
    the source. The defect is entirely this content gap in the generated
    `.gitignore`, which this test closes by asserting the parsed template
    entries contain the exact line `uv.lock` (not `*.lock`, not a
    `nested/uv.lock` variant -- exact membership only).
    """
    entries = _gitignore_entries(GITIGNORE_CONTENT)
    assert _UV_LOCK_GITIGNORE_ENTRY in entries, sorted(entries)


def test_build_contents_gitignore_entry_carries_uv_lock() -> None:
    """261031-fta: `GITIGNORE_CONTENT` alone proves the constant; this test
    proves the wiring -- that the same constant actually reaches the
    mapping `build_contents()` returns under `GITIGNORE_RELATIVE_PATH`,
    which is the exact value `write_output_file` writes to disk for a real
    scaffold invocation. A future refactor that renders `.gitignore` from
    somewhere else still has to carry this entry to pass this test. Calling
    `build_contents(...)` here is working-directory-independent: it reads
    this repository's own four instruction files through a path resolved
    from the script's `__file__`, not the working directory, which is the
    same precedent the pre-existing `test_setup_uv_ref_matches_this_repository_own_ci_workflow`
    test already relies on for `ci.yml`.
    """
    contents = build_contents(
        base_branch=DEFAULT_BASE_BRANCH,
        github_owner="example-org",
        github_repo="example-repo",
        quality_gate_commands=DEFAULT_QUALITY_GATE_COMMANDS,
        role_workers=_ROLE_WORKERS,
        install_source=DEFAULT_INSTALL_SOURCE,
    )
    assert len(contents) == 13, sorted(contents)
    entries = _gitignore_entries(contents[GITIGNORE_RELATIVE_PATH])
    assert _UV_LOCK_GITIGNORE_ENTRY in entries, sorted(entries)
