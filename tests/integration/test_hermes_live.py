"""Skip-guarded live integration suite for :class:`HermesWorker` (QUAL-03,
D-02, Plan 08-03 Task 2).

Mirrors ``test_copilot_live.py``/``test_claude_code_live.py`` structurally.
It runs automatically the day the ``hermes`` CLI is installed, with zero
code change required to make it run. This module imports nothing from
``tests.support.fake_hermes_cli`` -- the fake-CLI path is already covered
by the unit and contract suites; pointing this module at a fake executable
to make it "pass" would defeat QUAL-03's entire purpose (T-08-21).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.cli_runtime import resolve_dirs
from dark_factory.workers.hermes import HermesWorker
from tests.support.live_runtime import LIVE_RUNTIMES, skip_reason

_RUNTIME = LIVE_RUNTIMES["hermes"]
_SKIP_REASON = skip_reason(_RUNTIME)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]

# Hermes exposes no native per-tool restriction flag at all
# (NATIVE_TOOL_CONTRACT), so HermesWorker.spawn_is_permitted() refuses to
# spawn at all for a role denied any capability with no post-hoc
# compensating control (checkpoint decision, Option A -- 08-02-SUMMARY.md).
# Every capability except the two write capabilities (compensated by
# enforce_write_scope) must therefore be granted here, or a live run on a
# genuinely installed binary would fail with a spawn refusal and be
# misread as an adapter bug rather than as an intentionally minimal grant.
# Exported (not underscore-prefixed) so
# tests/unit/test_every_real_adapter_has_a_live_suite.py can pin that this
# grant list genuinely satisfies spawn admission, unconditionally -- i.e.
# even in an environment where this module's own test is skipped.
HERMES_LIVE_SPIKE_TOOLS: list[str] = [
    "repo.read",
    "repo.search",
    "shell.execute",
    "artifacts.read",
    "artifacts.write",
]


def test_hermes_worker_executes_a_trivial_role_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs only when both the ``hermes`` binary and
    ``Settings.anthropic_api_key`` are present (the ``skipif`` guard
    above). Deliberately shallow, mirroring ``test_copilot_live.py``.
    """
    monkeypatch.chdir(tmp_path)
    run_id = str(uuid4())
    role = "LIVE_SPIKE"
    attempt = 1

    context = RoleContext(
        run_id=run_id,
        role=role,
        worker="hermes",
        attempt=attempt,
        task={},
        answer=None,
        instructions=(
            "Reply with a single short sentence confirming you received "
            "this instruction. Do not modify any files."
        ),
        tools=HERMES_LIVE_SPIKE_TOOLS,
        outputs=[],
        artifacts_dir=f"artifacts/{role}",
    )

    result = HermesWorker().execute(context)

    assert isinstance(result, WorkerResult)
    assert isinstance(result.status, WorkerResultStatus)

    _work_dir, root = resolve_dirs(run_id)
    stdout_log = root / "logs" / role / f"attempt-{attempt}.stdout.log"
    assert stdout_log.is_file()


# Deliberately NOT a test function in this module: this module's own
# `pytestmark` (module-level) applies to every test defined here, including
# one that merely wants to prove the grant list above -- so a check that
# must hold unconditionally, even when this module's execution test skips,
# cannot live in this file. It is asserted instead in
# `tests/unit/test_every_real_adapter_has_a_live_suite.py`, which imports
# `HERMES_LIVE_SPIKE_TOOLS` and `spawn_is_permitted` from here rather than
# re-deriving its own copy of either.
