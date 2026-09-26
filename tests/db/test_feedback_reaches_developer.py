"""LOOP-01, LOOP-02 (Phase 9, plan 09-03): the feedback payload itself,
proved against a real ``drive()`` run.

    After a QA-FAIL bounce, the Developer's next attempt receives QA's
    structured issues from `verdict.json`. After a quality-gate FAIL bounce,
    the Developer's next attempt receives the gate's real per-command exit
    code and captured output from `quality_gate.json`. The Developer's first
    attempt of a run is unaffected either way -- neither optional input
    resolves before it has ever been produced.

Follows `tests/db/test_qa_bounce.py`'s idiom exactly: `start_run` + `drive`
against real PostgreSQL, an injected `WorkerRegistry` wrapping
`tests.support.fake_artifacts.AttemptAwareFourRoleWorker`, `cleanup_runs`
deleting every fixture row at teardown. Each scenario builds its config tree
with `config_root_factory` and then writes `DEVELOPMENT.yaml` with the *real
shipped* declarations -- `inputs: [design.md, constraints.json]` plus
`optional_inputs: [verdict.json, quality_gate.json]` -- proving the shipped
declaration works, not a test-only one, per this plan's own instruction.

Each scenario wraps the attempt-aware worker in a `_CapturingWorker` that
records every `RoleContext` the runner builds, in call order, and -- for the
Developer's bounced second attempt -- also rebuilds a fresh `RoleContext`
with a brand-new session at the exact moment the runner hands that context to
the worker (before QA's own second attempt has even been entered), proving
D-07's durability guarantee: a fresh process reconstructing the run right
then, from only what is already committed, resolves the identical
`RoleContext`.

The rebuild derives the run's worktree the same way a fresh process does --
by calling `ensure_worktree` with the `base_branch` / `working_branch` read
off the freshly loaded `RunState`, exactly as `_advance_once`
(runner.py:854-866) does -- rather than resolving artifacts against the
config repo root. The run tree and the role context always resolve against
the worktree, never against the config repo root: `worktree_path` places the
worktree at `<repo_root.parent>/dark-factory-runs/<run_id>/`, a SIBLING of
`repo_root`, never the same directory or an ancestor/descendant of it. Gaps
G-09-6 and G-09-7 (09-UAT.md) were exactly this: the rebuild passed the
stored `repo_root` instead, so every declared input read resolved against a
directory nothing was ever written into (see
`.planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md`). Do
not simplify this derivation back to a stored path -- that is the bug.
"""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.context.builder import RoleContext, build_role_context
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerCapabilities, WorkerResult
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.persistence.repositories import load_run_state
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import (
    QA_VERDICT_FAIL_FILES,
    AttemptAwareFourRoleWorker,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_QUALITY_GATE_BLOCK = "quality_gate:\n  commands: []\n"


def _write_four_role_tree(
    config_root_factory: Callable[..., Path],
    *,
    quality_gate_commands: list[str] | None = None,
) -> Path:
    """A `[BA, ARCHITECTURE, DEVELOPMENT, QA]` config tree carrying the same
    inputs/outputs contract `tests/db/test_qa_bounce.py` writes, except
    `DEVELOPMENT.yaml` additionally declares the shipped
    `optional_inputs: [verdict.json, quality_gate.json]` -- the plan's own
    instruction to prove the *shipped* declaration works, not a test-only
    shortcut.
    """
    root = config_root_factory(roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"))
    # (inputs, optional_inputs_line, outputs) per role.
    definitions: dict[str, tuple[str, str, str]] = {
        "BA": ("[]", "", "[requirements.md, acceptance_criteria.json]"),
        "ARCHITECTURE": (
            "[acceptance_criteria.json]",
            "",
            "[design.md, constraints.json]",
        ),
        "DEVELOPMENT": (
            "[design.md, constraints.json]",
            "optional_inputs: [verdict.json, quality_gate.json]\n",
            "[implementation_summary.json]",
        ),
        "QA": (
            "[acceptance_criteria.json, implementation_summary.json]",
            "",
            "[test_report.json, verdict.json]",
        ),
    }
    tools = {
        "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "DEVELOPMENT": (
            "[repo.read, repo.search, repo.write, repo.write_tests, "
            "shell.execute, artifacts.read, artifacts.write]"
        ),
        "QA": (
            "[repo.read, repo.search, repo.write_tests, shell.execute, "
            "artifacts.read, artifacts.write]"
        ),
    }
    for role, (inputs, optional_inputs_line, outputs) in definitions.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {tools[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"{optional_inputs_line}"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )

    config_path = root / ".dark-factory.yaml"
    original = config_path.read_text(encoding="utf-8")
    assert _QUALITY_GATE_BLOCK in original, (
        "config_root_factory no longer writes 'quality_gate:\\n  commands: []\\n'"
        " verbatim -- update this test's overwrite string to match"
    )
    commands = quality_gate_commands or []
    commands_yaml = "[" + ", ".join(json.dumps(c) for c in commands) + "]"
    patched = original.replace(
        _QUALITY_GATE_BLOCK, f"quality_gate:\n  commands: {commands_yaml}\n"
    )
    config_path.write_text(patched, encoding="utf-8")
    return root


class _CapturingWorker(CodingWorker):
    """Delegates to a real inner worker but records every `RoleContext` it is
    handed, in call order (mirrors `tests/db/test_four_role_pipeline.py`'s
    helper). Additionally, for every `(role, attempt)` pair in `rebuild_at`,
    opens a brand-new session at the exact moment the runner hands that
    context to the worker and calls `build_role_context` directly against
    it -- proving D-07's durability guarantee (see module docstring).
    """

    def __init__(
        self,
        inner: CodingWorker,
        captured: list[RoleContext],
        *,
        session_factory: SessionFactory,
        repo_root: Path,
        run_id: UUID,
        rebuild_at: set[tuple[str, int]],
        rebuilt: dict[tuple[str, int], RoleContext],
    ) -> None:
        self._inner = inner
        self._captured = captured
        self._session_factory = session_factory
        self._repo_root = repo_root
        self._run_id = run_id
        self._rebuild_at = rebuild_at
        self._rebuilt = rebuilt

    def _record_and_maybe_rebuild(self, context: object) -> None:
        assert isinstance(context, RoleContext)
        self._captured.append(context)
        key = (context.role, context.attempt)
        if key not in self._rebuild_at:
            return
        with self._session_factory() as fresh_session:
            fresh_state = load_run_state(fresh_session, self._run_id)
            assert fresh_state is not None
            role_def = next(
                r for r in fresh_state.workflow["roles"] if r["name"] == context.role
            )
            work_dir = ensure_worktree(
                self._repo_root,
                self._run_id,
                base_branch=fresh_state.base_branch,
                working_branch=fresh_state.working_branch,
            )
            self._rebuilt[key] = build_role_context(
                fresh_session, work_dir, self._run_id, fresh_state, role_def
            )

    def execute(self, context: object) -> WorkerResult:
        self._record_and_maybe_rebuild(context)
        return self._inner.execute(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        self._record_and_maybe_rebuild(context)
        return self._inner.resume(context, previous, answer)

    def capabilities(self) -> WorkerCapabilities:
        return self._inner.capabilities()


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(ArtifactReference).where(ArtifactReference.run_id.in_(ids))
            )
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _developer_contexts(captured: list[RoleContext]) -> list[RoleContext]:
    return [c for c in captured if c.role == "DEVELOPMENT"]


def test_qa_fail_delivers_structured_issues_to_developer_attempt_2(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """LOOP-01: a QA-FAIL bounce delivers QA's structured `verdict.json`
    issues to the Developer's next attempt -- absent on attempt 1, present
    (with the same severity/criterion id/description) on attempt 2 -- and the
    same content is independently reconstructable by a fresh process (D-07)."""
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails once then passes, developer must see why",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    inner_worker = AttemptAwareFourRoleWorker(
        run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
    )
    captured: list[RoleContext] = []
    rebuilt: dict[tuple[str, int], RoleContext] = {}
    worker = _CapturingWorker(
        inner_worker,
        captured,
        session_factory=real_session_factory,
        repo_root=root,
        run_id=run_id,
        rebuild_at={("DEVELOPMENT", 2)},
        rebuilt=rebuilt,
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    dev_contexts = _developer_contexts(captured)
    assert len(dev_contexts) == 2
    dev_attempt_1, dev_attempt_2 = dev_contexts
    assert dev_attempt_1.attempt == 1
    assert dev_attempt_2.attempt == 2

    # First-attempt-absent guarantee: exactly the two mandatory inputs, no
    # verdict.json entry, no exception raised anywhere along the way (the
    # run reached COMPLETED above, so nothing crashed).
    attempt_1_filenames = {i.filename for i in dev_attempt_1.inputs}
    assert attempt_1_filenames == {"design.md", "constraints.json"}

    verdict_inputs = [i for i in dev_attempt_2.inputs if i.filename == "verdict.json"]
    assert len(verdict_inputs) == 1
    verdict_input = verdict_inputs[0]
    assert verdict_input.produced_by == "QA"
    verdict_content = json.loads(verdict_input.content)
    assert verdict_content["issues"][0]["severity"] == "blocking"
    assert verdict_content["issues"][0]["description"] == "AC-1 is not met"
    assert verdict_content["criteria"][0]["criterion_id"] == "AC-1"

    # D-07: a fresh session, rebuilding the run state and calling
    # build_role_context directly for DEVELOPMENT at the exact moment the
    # runner itself did, resolves the identical RoleContext.inputs. A value
    # carried in memory across advance() calls could not survive that round
    # trip, so an equal result is the evidence.
    assert rebuilt[("DEVELOPMENT", 2)].inputs == dev_attempt_2.inputs


def test_gate_fail_delivers_real_command_output_to_developer_attempt_2(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """LOOP-02: a quality-gate FAIL bounce delivers the gate's real per-
    command exit code and captured output (`quality_gate.json`) to the
    Developer's next attempt -- absent on attempt 1, present (with the
    actual failing exit code and stderr) on attempt 2 -- and the same
    content is independently reconstructable by a fresh process (D-07)."""
    sentinel_name = "gate_ran_after_bounce.txt"
    sentinel_stderr_marker = "GATE_SAW_MISSING_MARKER_09_03"
    # Relative to cwd=work_dir (D-03): the sentinel lives under the
    # gitignored ``.dark-factory/runs/`` prefix -- see
    # AttemptAwareFourRoleWorker's docstring for why not the bare worktree
    # root -- at a run-id-independent path, since this command is fixed
    # into config before the run id exists.
    sentinel_rel_path = f".dark-factory/runs/{sentinel_name}"
    gate_script = (
        "import os, sys\n"
        f"if os.path.exists({sentinel_rel_path!r}):\n"
        "    sys.exit(0)\n"
        f"sys.stderr.write({sentinel_stderr_marker!r})\n"
        "sys.exit(1)\n"
    )
    gate_command = shlex.join([sys.executable, "-c", gate_script])

    root = _write_four_role_tree(
        config_root_factory, quality_gate_commands=[gate_command]
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:the gate fails once then passes, developer must see the real output",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    inner_worker = AttemptAwareFourRoleWorker(
        run_dir,
        attempt_files={},
        sentinel_writes={("DEVELOPMENT", 2): sentinel_name},
    )
    captured: list[RoleContext] = []
    rebuilt: dict[tuple[str, int], RoleContext] = {}
    worker = _CapturingWorker(
        inner_worker,
        captured,
        session_factory=real_session_factory,
        repo_root=root,
        run_id=run_id,
        rebuild_at={("DEVELOPMENT", 2)},
        rebuilt=rebuilt,
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    dev_contexts = _developer_contexts(captured)
    assert len(dev_contexts) == 2
    dev_attempt_1, dev_attempt_2 = dev_contexts
    assert dev_attempt_1.attempt == 1
    assert dev_attempt_2.attempt == 2

    # First-attempt-absent guarantee: exactly the two mandatory inputs on
    # attempt 1 -- neither verdict.json nor quality_gate.json has been
    # produced yet, no exception raised.
    attempt_1_filenames = {i.filename for i in dev_attempt_1.inputs}
    assert attempt_1_filenames == {"design.md", "constraints.json"}

    gate_inputs = [i for i in dev_attempt_2.inputs if i.filename == "quality_gate.json"]
    assert len(gate_inputs) == 1
    gate_input = gate_inputs[0]
    assert gate_input.produced_by == "quality_gate"
    assert gate_input.path == "verification/quality_gate.json"
    gate_content = json.loads(gate_input.content)
    matching_commands = [
        cmd
        for cmd in gate_content["commands"]
        if cmd["exit_code"] != 0 and sentinel_stderr_marker in cmd["stderr"]
    ]
    assert len(matching_commands) == 1

    # D-07: identical fresh-session rebuild proof as the QA-FAIL scenario.
    assert rebuilt[("DEVELOPMENT", 2)].inputs == dev_attempt_2.inputs
