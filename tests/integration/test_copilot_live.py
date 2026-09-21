"""Skip-guarded live integration suite for :class:`CopilotWorker` (QUAL-03,
D-02, Plan 08-03 Task 1).

This module is the live spike D-02 explicitly deferred: it drives the real
``copilot`` CLI end to end through ``CopilotWorker.execute()`` whenever both
the binary and ``Settings.copilot_github_token`` are available, and it
collects and reports a named skip in every other environment -- it never
disappears from ``pytest --collect-only`` output and never silently excludes
itself. It runs automatically the day the CLI is installed, with zero code
change required to make it run.

This module imports nothing from ``tests.support.fake_copilot_cli`` -- the
fake-CLI path is already covered by the unit and contract suites
(``tests/unit/test_copilot_worker.py``,
``tests/contract/test_coding_worker_contract.py``); pointing this module at
a fake executable to make it "pass" would defeat QUAL-03's entire purpose
(T-08-21).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.cli_runtime import resolve_dirs
from dark_factory.workers.copilot import CopilotWorker
from tests.support.live_runtime import LIVE_RUNTIMES, skip_reason

_RUNTIME = LIVE_RUNTIMES["copilot"]
_SKIP_REASON = skip_reason(_RUNTIME)

# A single skipif, evaluated once at import so the module still collects
# (its test appears as a reported skip, never as an excluded/absent test) in
# every environment -- T-08-19.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]


def test_copilot_worker_executes_a_trivial_role_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs only when both the ``copilot`` binary and
    ``Settings.copilot_github_token`` are present (the ``skipif`` guard
    above). Deliberately shallow -- this test's job is to prove the adapter
    drives a real binary end to end, not to assert on model output, which is
    not deterministic.

    ``tmp_path`` confines every side effect this test can trigger to a
    throwaway directory outside the developer's checkout (T-08-20 threat
    register).
    """
    monkeypatch.chdir(tmp_path)
    run_id = str(uuid4())
    role = "LIVE_SPIKE"
    attempt = 1

    context = RoleContext(
        run_id=run_id,
        role=role,
        worker="copilot",
        attempt=attempt,
        task={},
        answer=None,
        instructions=(
            "Reply with a single short sentence confirming you received "
            "this instruction. Do not modify any files."
        ),
        tools=["repo.read"],
        outputs=[],
        artifacts_dir=f"artifacts/{role}",
    )

    result = CopilotWorker().execute(context)

    assert isinstance(result, WorkerResult)
    assert isinstance(result.status, WorkerResultStatus)

    _work_dir, root = resolve_dirs(run_id)
    stdout_log = root / "logs" / role / f"attempt-{attempt}.stdout.log"
    assert stdout_log.is_file()
