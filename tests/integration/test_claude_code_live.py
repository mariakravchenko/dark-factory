"""Skip-guarded live integration suite for :class:`ClaudeCodeWorker`
(QUAL-03, D-02, Plan 08-03 Task 2).

Phase 7 proved ``ClaudeCodeWorker`` entirely against a faked ``claude``
executable on ``PATH`` (``tests/unit/test_claude_code_worker.py``,
``tests/contract/test_coding_worker_contract.py``) -- a different thing from
a suite that runs for real when the live binary and credential are present
and skips cleanly otherwise. ``ROADMAP.md`` maps QUAL-03 to Phase 8 only, so
Phase 7 never built this for ``claude-code`` either
(08-RESEARCH.md "Scope Correction"): this module is a retroactive obligation
Phase 7 left open under an adjacent-sounding name, being met here rather
than new scope. It runs automatically the day the ``claude`` CLI is
installed, with zero code change required to make it run.

This module imports nothing from ``tests.support.fake_claude_cli`` -- the
fake-CLI path is already covered elsewhere; pointing this module at a fake
executable to make it "pass" would defeat QUAL-03's entire purpose
(T-08-21).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.claude_code import ClaudeCodeWorker
from dark_factory.workers.cli_runtime import resolve_dirs
from tests.support.live_runtime import LIVE_RUNTIMES, skip_reason

_RUNTIME = LIVE_RUNTIMES["claude-code"]
_SKIP_REASON = skip_reason(_RUNTIME)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]


def test_claude_code_worker_executes_a_trivial_role_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs only when both the ``claude`` binary and
    ``Settings.anthropic_api_key`` are present (the ``skipif`` guard above).
    Deliberately shallow, mirroring ``test_copilot_live.py`` -- this test's
    job is to prove the adapter drives a real binary end to end, not to
    assert on model output, which is not deterministic.
    """
    monkeypatch.chdir(tmp_path)
    run_id = str(uuid4())
    role = "LIVE_SPIKE"
    attempt = 1

    context = RoleContext(
        run_id=run_id,
        role=role,
        worker="claude-code",
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

    result = ClaudeCodeWorker().execute(context)

    assert isinstance(result, WorkerResult)
    assert isinstance(result.status, WorkerResultStatus)

    _work_dir, root = resolve_dirs(run_id)
    stdout_log = root / "logs" / role / f"attempt-{attempt}.stdout.log"
    assert stdout_log.is_file()
