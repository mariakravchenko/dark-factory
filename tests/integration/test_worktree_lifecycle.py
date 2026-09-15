"""D-03: the same worktree survives a pause and a fresh-process resume.

Two real operating-system processes are the whole point -- an in-process
``advance()``/``advance()`` pair shares a Python heap and cannot distinguish
"the same worktree, reused" from "a fresh worktree that happens to be at the
same path", which is exactly the claim under test. Follows
``tests/integration/test_fresh_process_resume.py``'s two-real-process idiom:
``child_env`` / ``spawn`` / ``run_id_from_stdout`` from
``tests/support/subprocess_runner.py``, a second process given nothing but
the run id and the answer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from dark_factory.git.client import run_git
from dark_factory.git.lifecycle import WIP_COMMIT_SUBJECT_PREFIX
from dark_factory.git.worktree import (
    remove_worktree,
    working_branch_name,
    worktree_path,
)
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from tests.support.git_repo import read_committed
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn

pytestmark = pytest.mark.integration

_QUESTION = "Which environment?"
_ANSWER = "Use staging"
_NEW_FILE_RELATIVE = "worker_left_this_untracked.txt"
_NEW_FILE_CONTENT = "content a stopped worker never committed\n"

_PAUSE_SCRIPT = [
    {
        "status": "NEEDS_INPUT",
        "questions": [_QUESTION],
        "worker_session_id": "fake-lifecycle-ba-001",
    },
]
_RESUME_SCRIPT = [
    {
        "status": "COMPLETED",
        "summary": "ba resumed and finished",
        "worker_session_id": "fake-lifecycle-ba-001",
    },
    {
        "status": "COMPLETED",
        "summary": "architecture done",
        "worker_session_id": "fake-lifecycle-architecture-001",
    },
]


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[tuple[Any, Path]]]:
    entries: list[tuple[Any, Path]] = []
    yield entries
    ids = [run_id for run_id, _root in entries]
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
    for run_id, root in entries:
        remove_worktree(root, run_id, force=True)


def test_a_paused_run_is_resumed_by_a_fresh_process_reusing_the_same_worktree(
    pg_url: str,
    engine: Engine,
    cleanup_runs: list[tuple[Any, Path]],
    config_root_factory: Callable[..., Path],
) -> None:
    root = config_root_factory(roles=("BA", "ARCHITECTURE"))

    # -- first process: pauses BA on NEEDS_INPUT ------------------------------
    p1 = spawn(
        ["run", "text:pause then resume, proving the same worktree survives"],
        child_env(pg_url, fake_script=_PAUSE_SCRIPT),
        cwd=root,
    )
    assert p1.returncode == 0, f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    assert "BA → WAITING_HUMAN" in p1.stdout, p1.stdout
    run_id = run_id_from_stdout(p1.stdout)
    cleanup_runs.append((run_id, root))

    # -- the worktree the paused run left behind ------------------------------
    work_dir = worktree_path(root, run_id)
    branch = working_branch_name(run_id)
    assert work_dir.is_dir()
    assert (work_dir / ".git").exists()

    head_ref = run_git(["symbolic-ref", "-q", "HEAD"], cwd=work_dir).stdout.strip()
    assert head_ref == f"refs/heads/{branch}"

    recorded_path = work_dir.resolve()
    recorded_tip = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()

    worktree_list_before = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert worktree_list_before.count(f"worktree {work_dir}\n") == 1

    # -- dirty the worktree while the run is paused, exactly as a stopped
    # worker would have left it: a new untracked file and a modified tracked
    # one.
    (work_dir / _NEW_FILE_RELATIVE).write_text(_NEW_FILE_CONTENT, encoding="utf-8")
    (work_dir / "README.md").write_text(
        "# throwaway test repository\n\nmodified while paused\n", encoding="utf-8"
    )

    # -- resume from a brand-new process, given nothing but the run id and
    # the answer --------------------------------------------------------------
    resume_env = child_env(pg_url, fake_script=_RESUME_SCRIPT)
    assert "DARK_FACTORY_CRASH_AFTER" not in resume_env
    p2 = spawn(["resume", str(run_id), "--answer", _ANSWER], resume_env, cwd=root)
    assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"

    # -- the resumed run reaches a terminal state ------------------------------
    with engine.begin() as conn:
        final_status = conn.execute(
            sa.select(Run.status).where(Run.id == run_id)
        ).scalar_one()
    assert final_status.value == "COMPLETED"

    # -- the worktree's absolute path is byte-identical before/after ---------
    assert work_dir.resolve() == recorded_path
    assert work_dir.is_dir()

    worktree_list_after = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert worktree_list_after.count(f"worktree {work_dir}\n") == 1

    # -- a recovery commit landed, carrying the WIP prefix ---------------------
    subjects = run_git(["log", "--format=%s"], cwd=work_dir).stdout.splitlines()
    recovery_subjects = [s for s in subjects if s.startswith(WIP_COMMIT_SUBJECT_PREFIX)]
    assert len(recovery_subjects) == 1, subjects

    new_tip = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()
    assert new_tip != recorded_tip

    # -- the second process appended to the same history, never started a
    # fresh one: recorded_tip must be an ancestor of the new tip. A path
    # comparison alone would also pass against an implementation that deleted
    # and re-created the worktree at the same path -- exactly what D-03
    # forbids -- so ancestry is the assertion that actually proves reuse.
    ancestry = run_git(
        ["merge-base", "--is-ancestor", recorded_tip, new_tip],
        cwd=work_dir,
        check=False,
    )
    assert ancestry.returncode == 0, (
        f"{recorded_tip} is not an ancestor of {new_tip} -- the worktree's "
        "history was not continuous across the resume"
    )

    # -- nothing written before the pause was lost -----------------------------
    recovered_content = read_committed(root, branch, _NEW_FILE_RELATIVE)
    assert recovered_content == _NEW_FILE_CONTENT
