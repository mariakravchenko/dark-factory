"""SC2: a process killed at a committed intermediate step is picked up by a
brand-new, independent process that shares only the database, and it reaches the
same terminal state -- same run id, same attempt number, no second run.

Two real operating-system processes are the whole point. An in-process
simulation would share module state, a warm engine and an identity map and could
pass while the real thing failed; the claim under test is specifically that
*nothing* carries over from the dead process.

The first process is armed with ``DARK_FACTORY_CRASH_AFTER=CREATED_BA`` -- the
test-only hook in ``orchestrator/runner.py`` that calls ``os._exit`` the instant
that transition commits, a faithful stand-in for a power loss. The second
process's environment does not contain that variable.

The child environment is built from an explicit allowlist, never
``os.environ.copy()`` (CLAUDE.md's credential boundary). The provisioned
PostgreSQL URL is passed through as ``DATABASE_URL`` / ``DATABASE_URL_DIRECT``
and is never printed or written anywhere this test keeps.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    run_id_from_stdout,
    spawn,
)

pytestmark = pytest.mark.integration

_RUNNER_SRC = REPO_ROOT / "src" / "dark_factory" / "orchestrator" / "runner.py"

_CRASH_AT_FIRST_TRANSITION = "CREATED_BA"


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def test_killed_after_first_commit_then_resumed_by_a_separate_process(
    pg_url: str,
    engine: Engine,
    force_lease_expiry: Callable[[UUID], None],
) -> None:
    # -- first process: dies the instant CREATED -> BA commits --
    p1 = spawn(
        ["run", "text:carry nothing between processes"],
        child_env(pg_url, crash_after=_CRASH_AT_FIRST_TRANSITION),
    )
    assert p1.returncode != 0, (
        f"expected a non-zero crash exit, got {p1.returncode}\n"
        f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    )
    assert "TimeoutExpired" not in (p1.stdout + p1.stderr)
    # D-01: the bare run id is on stdout line 1, flushed before the crash.
    run_id = run_id_from_stdout(p1.stdout)

    runs_before_resume = _count_runs(engine)

    # -- the committed intermediate state left by the dead process --
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "BA"
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        assert execs[0].attempt == 1
        assert execs[0].status == "RUNNING"
        assert execs[0].result is None
        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert events == ["RUN_CREATED", "ROLE_STARTED"]

    # The hard-killed first process (os._exit) never ran run_lease.__exit__, so
    # its single-owner lease is still held with a ~TTL-in-the-future expiry
    # (Phase 2). SC4 says an expired lease is reclaimable; forcing the expiry
    # here with a server-clock UPDATE is the deterministic stand-in for waiting
    # out the TTL, exactly as the dedicated reclaim proofs in 02-04 / 02-05 do.
    force_lease_expiry(run_id)

    # -- second, entirely separate process: the hook is not in its environment --
    resume_env = child_env(pg_url)
    assert "DARK_FACTORY_CRASH_AFTER" not in resume_env
    p2 = spawn(["resume", str(run_id)], resume_env)
    assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"
    assert "BA → COMPLETED" in p2.stdout

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        assert execs[0].attempt == 1  # never reset by the resume
        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert events == [
            "RUN_CREATED",
            "ROLE_STARTED",
            "ROLE_COMPLETED",
            "RUN_COMPLETED",
        ]

    # resuming never creates a run
    assert _count_runs(engine) == runs_before_resume


def test_run_without_the_hook_reaches_completed_unchanged(pg_url: str) -> None:
    """With the variable unset, ``run`` behaves exactly as it did before the hook."""
    proc = spawn(["run", "text:no hook armed here"], child_env(pg_url))
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    run_id_from_stdout(proc.stdout)
    assert "CREATED → BA" in proc.stdout
    assert "BA → COMPLETED" in proc.stdout


def test_crash_hook_lives_in_exactly_one_function_and_reads_the_env_each_call() -> None:
    """The seam appears in one place, is read at call time (not import time), and
    terminates abruptly rather than raising (acceptance criteria for Task 1)."""
    source = _RUNNER_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions_naming_the_hook: list[str] = []
    functions_calling_abrupt_exit: list[str] = []
    module_level_names_the_env_var = False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            segment = ast.get_source_segment(source, node) or ""
            if "DARK_FACTORY_CRASH_AFTER" in segment or "_CRASH_AFTER_ENV" in segment:
                functions_naming_the_hook.append(node.name)
            if "_exit(" in segment:
                functions_calling_abrupt_exit.append(node.name)

    # The env-var *name* may be defined as a module constant; its *value* must
    # never be captured at module import.
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    rhs = ast.get_source_segment(source, stmt.value) or ""
                    if "environ" in rhs:
                        module_level_names_the_env_var = True

    assert functions_naming_the_hook == ["_maybe_crash_after"]
    assert functions_calling_abrupt_exit == ["_maybe_crash_after"]
    assert not module_level_names_the_env_var
    # os._exit, not sys.exit / raise: no finally, no context manager, no rollback.
    assert "os._exit(" in source
