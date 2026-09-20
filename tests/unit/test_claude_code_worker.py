"""Unit coverage for :class:`ClaudeCodeWorker` (Plan 07-01) — the first real
:class:`~dark_factory.workers.base.CodingWorker` adapter.

No live ``claude`` binary and no live ``ANTHROPIC_API_KEY`` are ever used:
every test drives a fake ``claude`` executable written by
``tests/support/fake_claude_cli.py`` and prepended to ``PATH``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dark_factory.context.builder import RoleContext
from tests.support.fake_claude_cli import fake_claude_env, write_fake_claude

pytestmark = pytest.mark.unit

_RUN_ID = "8f14e45f-ceea-467e-adde-3fb5b2c8de9c"
_SUCCESS_PAYLOAD = json.dumps(
    {
        "subtype": "success",
        "duration_ms": 1234,
        "duration_api_ms": 1000,
        "is_error": False,
        "num_turns": 2,
        "session_id": "sess-abc",
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "result": "done",
        "structured_output": None,
        "permission_denials": [],
    }
)


def _context(
    *,
    role: str = "DEVELOPMENT",
    run_id: str = _RUN_ID,
    attempt: int = 1,
) -> RoleContext:
    return RoleContext(
        run_id=run_id,
        role=role,
        worker="claude-code",
        attempt=attempt,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="Implement the feature.",
        inputs=[],
        baseline_docs={},
        examples=[],
        constraints={},
        tools=[],
        permissions={},
        outputs=[],
        artifacts_dir=f"artifacts/{role}",
    )


@pytest.fixture
def repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo-shaped ``tmp_path`` subdirectory; ``monkeypatch.chdir()``s into
    it so the ``dark-factory-runs`` sibling-of-``cwd`` formula
    (``ClaudeCodeWorker``/``FakeWorker`` mirror it verbatim) resolves under
    ``tmp_path``, not the real repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    return repo


def _run_root_for(tmp_path: Path) -> Path:
    return tmp_path / "dark-factory-runs" / _RUN_ID / ".dark-factory" / "runs" / _RUN_ID


def test_execute_returns_completed_with_session_id_and_summary(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD)

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status.value == "COMPLETED"
    assert result.worker_session_id == "sess-abc"
    assert result.summary == "done"


def test_argv_contains_required_flags(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context())

    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[0].endswith("claude")
    for flag in ("-p", "--output-format", "json", "--permission-mode", "dontAsk"):
        assert flag in argv


def test_attempt_log_file_exists_and_contains_the_fake_output(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context(role="DEVELOPMENT"))

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    assert log_path.is_file()
    assert "sess-abc" in log_path.read_text("utf-8")


def test_subprocess_env_has_credential_and_lacks_infra_secrets(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    env_log = tmp_path / "env.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, env_log=env_log)

    with fake_claude_env(monkeypatch, fake_dir):
        # Both present in the parent process for the duration of the call —
        # build_worker_env() must still exclude them from the child.
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fakefakefakefakefakefakefakefake0000")
        ClaudeCodeWorker().execute(_context())

    observed_env = json.loads(env_log.read_text("utf-8"))
    assert "ANTHROPIC_API_KEY" in observed_env
    assert "DATABASE_URL" not in observed_env
    assert "GITHUB_TOKEN" not in observed_env


def test_default_registry_returns_a_claude_code_worker_instance() -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker
    from dark_factory.workers.registry import default_registry

    assert isinstance(default_registry.get("claude-code"), ClaudeCodeWorker)


def test_claude_code_worker_is_constructible_with_zero_arguments() -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    assert ClaudeCodeWorker() is not None


# --------------------------------------------------------------------------- #
# Task 2: every failure path becomes a persisted FAILED result, and a hung
# child dies with its process group.
# --------------------------------------------------------------------------- #


def test_timeout_kills_process_group_and_persists_output(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import time

    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    directory = fake_dir
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / "claude"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import subprocess
import sys
import time

sys.stdout.write("pre-sleep line\\n")
sys.stdout.flush()
# Deliberately NOT start_new_session=True here: this child must stay in the
# same process group as this script (which _run_streamed already spawned
# with start_new_session=True) so that killpg() on that group reaches it too
# -- proving os.killpg(...) kills descendants, not only the direct child.
proc = subprocess.Popen(
    ["python3", "-c", "import time; time.sleep(30)"],
)
with open({str(grandchild_pid_file)!r}, "w") as fh:
    fh.write(str(proc.pid))
time.sleep(30)
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    with fake_claude_env(monkeypatch, fake_dir):
        monkeypatch.setenv("WORKER_TIMEOUT_SECONDS", "1")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        start = time.monotonic()
        result = ClaudeCodeWorker().execute(_context())
        elapsed = time.monotonic() - start
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert elapsed < 55  # fires at ~1s, not the 1800s default
    assert "1" in (result.error or "")

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    assert "pre-sleep line" in log_path.read_text("utf-8", errors="replace")

    # Give the OS a beat to actually reap/kill the grandchild before probing.
    time.sleep(0.5)
    grandchild_pid = int(grandchild_pid_file.read_text("utf-8").strip())
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)


def test_non_zero_exit_returns_failed_with_exit_code_and_stderr(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir, stdout_payload="", exit_code=2, stderr_text="boom"
    )

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert "2" in (result.error or "")
    assert "boom" in (result.error or "")


def test_non_json_stdout_returns_failed_without_raising(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload="not json at all")

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert "json" in (result.error or "").lower()


def test_missing_claude_binary_returns_failed_without_raising(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    empty_dir = tmp_path / "empty-bin"
    empty_dir.mkdir()
    with fake_claude_env(monkeypatch, empty_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED


def test_missing_credential_returns_failed_and_spawns_nothing(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        result = ClaudeCodeWorker().execute(_context())
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert "ANTHROPIC_API_KEY" in (result.error or "")
    assert not argv_log.exists()


def test_missing_worker_credential_error_is_importable_and_a_runtime_error() -> None:
    from dark_factory.workers.claude_code import MissingWorkerCredentialError

    assert issubclass(MissingWorkerCredentialError, RuntimeError)


# --------------------------------------------------------------------------- #
# Task 3 [BLOCKING]: redact the captured transcript before it can reach the
# PR branch, on every exit path.
# --------------------------------------------------------------------------- #

_FAKE_SECRET = "sk-ant-fake0000000000000000000000000000"


def _payload_leaking(secret: str) -> str:
    return json.dumps(
        {
            "subtype": "success",
            "duration_ms": 1,
            "duration_api_ms": 1,
            "is_error": False,
            "num_turns": 1,
            "session_id": "sess-secret",
            "total_cost_usd": 0.0,
            "usage": {},
            "result": f"leaked credential: {secret}",
            "structured_output": None,
            "permission_denials": [],
        }
    )


def test_captured_output_is_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=_payload_leaking(_FAKE_SECRET))

    with fake_claude_env(
        monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET
    ):
        ClaudeCodeWorker().execute(_context())

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text


def test_captured_stderr_is_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_SUCCESS_PAYLOAD,
        stderr_text=f"debug: key is {_FAKE_SECRET}",
    )

    with fake_claude_env(
        monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET
    ):
        ClaudeCodeWorker().execute(_context())

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stderr.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text


def test_redaction_applies_on_non_zero_exit_path(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload="",
        exit_code=2,
        stderr_text=f"boom: {_FAKE_SECRET}",
    )

    with fake_claude_env(
        monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET
    ):
        result = ClaudeCodeWorker().execute(_context())

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stderr.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text
    assert _FAKE_SECRET not in (result.error or "")


def test_redaction_applies_on_timeout_kill_path(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    # write_fake_claude() writes stdout_payload AFTER sleeping (it models a
    # clean-exit result, not a partial pre-kill transcript), so this test
    # writes its own script that writes the secret BEFORE sleeping -- the
    # exact "partial output survives a kill" shape SC5/Task 2 already prove;
    # this test only adds that the surviving partial output is scrubbed.
    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir(parents=True, exist_ok=True)
    script_path = fake_dir / "claude"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import sys
import time

sys.stdout.write({f"pre-sleep output: {_FAKE_SECRET}\\n"!r})
sys.stdout.flush()
time.sleep(30)
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    with fake_claude_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET):
        monkeypatch.setenv("WORKER_TIMEOUT_SECONDS", "1")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        ClaudeCodeWorker().execute(_context())
        get_settings.cache_clear()

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text


def test_pattern_only_secret_not_in_settings_is_still_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    github_token = "ghp_" + ("x" * 40)
    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir, stdout_payload=_payload_leaking(github_token)
    )

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context())

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    log_text = log_path.read_text("utf-8")
    assert github_token not in log_text


def test_non_utf8_stdout_byte_does_not_raise(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResult
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=b"\xff")

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert isinstance(result, WorkerResult)


# --------------------------------------------------------------------------- #
# 07-03 Task 1 (D-01): a role can ask a human a question through the real
# CLI, via a line-initial ``NEEDS_INPUT:`` marker in the CLI's own ``result``
# text.
# --------------------------------------------------------------------------- #


def _payload_with_result(result_text: str, *, session_id: str = "sess-abc") -> str:
    return json.dumps(
        {
            "subtype": "success",
            "duration_ms": 1,
            "duration_api_ms": 1,
            "is_error": False,
            "num_turns": 1,
            "session_id": session_id,
            "total_cost_usd": 0.0,
            "usage": {},
            "result": result_text,
            "structured_output": None,
            "permission_denials": [],
        }
    )


def test_needs_input_marker_produces_needs_input_with_question(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_payload_with_result(
            "I need a decision.\nNEEDS_INPUT: Which cluster should I target?"
        ),
    )

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.NEEDS_INPUT
    assert result.questions == ["Which cluster should I target?"]


def test_needs_input_marker_multiline_question_captured_whole(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_payload_with_result(
            "NEEDS_INPUT: Which cluster?\nStaging or production?"
        ),
    )

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.NEEDS_INPUT
    assert len(result.questions) == 1
    assert "Which cluster?" in result.questions[0]
    assert "Staging or production?" in result.questions[0]


def test_needs_input_marker_mid_sentence_does_not_trigger(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_payload_with_result(
            "This mentions NEEDS_INPUT: mid-sentence, not at line start."
        ),
    )

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED


def test_needs_input_marker_followed_by_only_whitespace_degrades_to_completed(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_payload_with_result("Done.\nNEEDS_INPUT:   \n  "),
    )

    with fake_claude_env(monkeypatch, fake_dir):
        # Must not raise a pydantic ValidationError from inside the adapter.
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED


def test_needs_input_result_carries_worker_session_id(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=_payload_with_result(
            "NEEDS_INPUT: pick one", session_id="sess-needs-input"
        ),
    )

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.NEEDS_INPUT
    assert result.worker_session_id == "sess-needs-input"


def test_prompt_argument_contains_the_needs_input_marker_token(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import NEEDS_INPUT_MARKER, ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(
        fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log
    )

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context())

    argv = json.loads(argv_log.read_text("utf-8"))
    prompt = argv[argv.index("-p") + 1]
    assert NEEDS_INPUT_MARKER in prompt


# --------------------------------------------------------------------------- #
# 07-03 Task 2: a paused role resumes -- natively by session id, or by
# context reconstruction -- both behind the identical worker.resume(...)
# call (HITL-04, HITL-05).
# --------------------------------------------------------------------------- #


def test_capabilities_reports_native_resume_and_all_expected_flags() -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    caps = ClaudeCodeWorker().capabilities()

    assert caps.native_resume is True
    assert caps.session_id is True
    assert caps.structured_output is True
    assert caps.non_interactive is True
    assert caps.emits_changed_files is False


def _paused_with_session_id(session_id: str | None) -> "object":
    from dark_factory.domain.worker import WorkerResult, WorkerResultStatus

    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a decision about clusters",
        questions=["which cluster should I target?"],
        worker_session_id=session_id,
    )


def test_resume_uses_native_session_id(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    previous = _paused_with_session_id("sess-abc")

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().resume(_context(), previous, "the primary cluster")

    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[argv.index("--resume") + 1] == "sess-abc"
    assert argv[argv.index("-p") + 1] == "the primary cluster"


def test_resume_without_session_id_reconstructs_context(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    previous = _paused_with_session_id(None)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().resume(_context(), previous, "the primary cluster")

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--resume" not in argv
    prompt = argv[argv.index("-p") + 1]
    assert "need a decision about clusters" in prompt
    assert "which cluster should I target?" in prompt
    assert "the primary cluster" in prompt


def test_resume_with_null_answer_yields_non_empty_prompt_on_both_branches(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().resume(_context(), _paused_with_session_id("sess-abc"), None)
    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[argv.index("-p") + 1]

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().resume(_context(), _paused_with_session_id(None), None)
    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[argv.index("-p") + 1]


def test_resume_timeout_returns_failed_and_persists_partial_log(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir(parents=True, exist_ok=True)
    script_path = fake_dir / "claude"
    script_path.write_text(
        """#!/usr/bin/env python3
import sys
import time

sys.stdout.write("pre-sleep line\\n")
sys.stdout.flush()
time.sleep(30)
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    with fake_claude_env(monkeypatch, fake_dir):
        monkeypatch.setenv("WORKER_TIMEOUT_SECONDS", "1")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        result = ClaudeCodeWorker().resume(
            _context(), _paused_with_session_id("sess-abc"), "answer"
        )
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    assert "pre-sleep line" in log_path.read_text("utf-8", errors="replace")


def test_resume_redacts_captured_transcript(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=_payload_leaking(_FAKE_SECRET))

    with fake_claude_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET):
        ClaudeCodeWorker().resume(
            _context(), _paused_with_session_id("sess-abc"), "answer"
        )

    log_path = (
        _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text


def test_resume_missing_credential_returns_failed_without_raising(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        result = ClaudeCodeWorker().resume(
            _context(), _paused_with_session_id("sess-abc"), "answer"
        )
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert not argv_log.exists()
