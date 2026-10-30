"""Unit coverage for :class:`ClaudeCodeWorker` (Plan 07-01) — the first real
:class:`~dark_factory.workers.base.CodingWorker` adapter.

No live ``claude`` binary and no live ``ANTHROPIC_API_KEY`` are ever used:
every test drives a fake ``claude`` executable written by
``tests/support/fake_claude_cli.py`` and prepended to ``PATH``.
"""

from __future__ import annotations

import json
import stat
import sys
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
    tools: list[str] | None = None,
    outputs: list[str] | None = None,
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
        tools=tools or [],
        permissions={},
        outputs=outputs or [],
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

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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
    write_fake_claude(fake_dir, stdout_payload="", exit_code=2, stderr_text="boom")

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
        # REPLACE PATH, don't rely on `fake_claude_env`'s prepend: that helper
        # only PREPENDS `empty_dir` (fake_claude_cli.py:81-82), leaving the real
        # `claude` resolvable further down an 18-entry PATH on any machine that
        # has the CLI installed. This test then passed for the wrong reason --
        # the real binary ran with the helper's bogus `sk-ant-fake...` key,
        # failed auth, and returned the very FAILED this asserts. Measured in
        # debug session `claude-cli-test-spawns-real-binary-with-key-present`.
        # `build_worker_env` keeps PATH in its allowlist (tools/env.py:55) and
        # `Popen` resolves argv[0] through `os.get_exec_path(env)`, so replacing
        # PATH makes `claude` unresolvable in the spawned child too -- which is
        # what makes the binary genuinely absent, as this test's name claims.
        monkeypatch.setenv("PATH", str(empty_dir))
        result = ClaudeCodeWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    # A DERIVED oracle, not merely `FAILED`. `FAILED` alone cannot tell
    # "binary absent" -- the property under test -- from "real binary ran and
    # was rejected", because `execute()`'s never-raise wrapper collapses both.
    # That collapse is exactly what hid this defect. Pinning the errno text
    # means a future revert to a PATH *prepend* fails here loudly instead of
    # passing for the wrong reason.
    assert "claude" in (result.error or "")
    assert "No such file or directory" in (result.error or "")


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

    with fake_claude_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET):
        ClaudeCodeWorker().execute(_context())

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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

    with fake_claude_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET):
        ClaudeCodeWorker().execute(_context())

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stderr.log"
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

    with fake_claude_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_SECRET):
        result = ClaudeCodeWorker().execute(_context())

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stderr.log"
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

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
    log_text = log_path.read_text("utf-8")
    assert "[redacted:anthropic_api_key]" in log_text
    assert _FAKE_SECRET not in log_text


def test_pattern_only_secret_not_in_settings_is_still_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    github_token = "ghp_" + ("x" * 40)
    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=_payload_leaking(github_token))

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context())

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

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


def _paused_with_session_id(session_id: str | None) -> object:
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


def _write_resume_aware_fake_claude(
    directory: Path, *, resume_stderr: str, success_payload: str, calls_log: Path
) -> Path:
    """A fake ``claude`` whose behaviour depends on whether ``--resume`` is
    present in argv (G-11-5): exits 1 with ``resume_stderr`` when it is,
    exits 0 with ``success_payload`` otherwise. Unlike
    :func:`~tests.support.fake_claude_cli.write_fake_claude` (one fixed
    behaviour per script), this is what proving a *fallback* needs -- two
    sequential invocations of the same binary with different outcomes.
    ``calls_log`` is appended to (not overwritten) once per invocation, as a
    JSON-lines file of each call's full argv, so a test can assert both the
    order and the content of every invocation, not just the last.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / "claude"
    script = f"""#!{sys.executable}
import json
import sys

with open({str(calls_log)!r}, "a", encoding="utf-8") as log_fh:
    log_fh.write(json.dumps(sys.argv) + "\\n")

if "--resume" in sys.argv:
    sys.stderr.write({resume_stderr!r})
    sys.exit(1)
else:
    sys.stdout.write({success_payload!r})
    sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    mode = script_path.stat().st_mode
    script_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return directory


def test_resume_falls_back_to_context_reconstruction_when_native_session_not_found(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G-11-5: the session a previous attempt recorded is Claude Code's own
    local-filesystem state on the machine that created it (COVERAGE.md's
    rejection of ``--continue`` for process-local state applies equally to
    an explicit ``--resume <id>`` -- the id just makes the same locality
    constraint explicit instead of implicit). A cross-machine resume (pause
    on a laptop, resume inside CI) therefore cannot find that session, and
    this is Claude Code's own real failure signature for it -- reproduced
    verbatim from a live cross-machine resume attempt that hit exactly this
    (dark-factory run 472dc760-8b4e-4473-b5ad-63b8247ba1fe, 2026-10-02):
    the CLI exits 1 with "No conversation found with session ID: <id>" on
    stderr, never reaching its JSON stdout contract at all. Falling back to
    HITL-05's context-reconstruction branch (not simply failing the role)
    preserves the phase's stated goal -- "a run started on a laptop finishes
    in CI" -- without pretending Claude's own conversational memory
    travelled with it.
    """
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    calls_log = tmp_path / "calls.jsonl"
    _write_resume_aware_fake_claude(
        fake_dir,
        resume_stderr="No conversation found with session ID: sess-abc\n",
        success_payload=_SUCCESS_PAYLOAD,
        calls_log=calls_log,
    )

    previous = _paused_with_session_id("sess-abc")

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().resume(_context(), previous, "the primary cluster")

    calls = [json.loads(line) for line in calls_log.read_text("utf-8").splitlines()]
    assert len(calls) == 2, (
        "expected exactly one retry: the native attempt, then the fallback"
    )

    first_argv, second_argv = calls
    assert first_argv[first_argv.index("--resume") + 1] == "sess-abc"
    assert "--resume" not in second_argv
    fallback_prompt = second_argv[second_argv.index("-p") + 1]
    assert "need a decision about clusters" in fallback_prompt
    assert "which cluster should I target?" in fallback_prompt
    assert "the primary cluster" in fallback_prompt

    # The final result reflects the FALLBACK call's (successful) outcome,
    # not the native attempt's failure -- the caller never sees the
    # session-not-found error as this role's own result.
    assert result.status is WorkerResultStatus.COMPLETED
    assert result.summary == "done"
    assert result.worker_session_id == "sess-abc"


def test_resume_does_not_fall_back_on_an_unrelated_native_failure(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback above must be scoped to the one known cross-machine
    signature -- a native resume that fails for any OTHER reason (a crash, a
    real bug, an unrelated CLI error) must surface as a normal failure, not
    silently retry and potentially mask it. Only one invocation should ever
    occur in this case.
    """
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    calls_log = tmp_path / "calls.jsonl"
    _write_resume_aware_fake_claude(
        fake_dir,
        resume_stderr="internal error: unexpected panic\n",
        success_payload=_SUCCESS_PAYLOAD,
        calls_log=calls_log,
    )

    previous = _paused_with_session_id("sess-abc")

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().resume(_context(), previous, "the primary cluster")

    calls = [json.loads(line) for line in calls_log.read_text("utf-8").splitlines()]
    assert len(calls) == 1, "an unrelated failure must not trigger the fallback retry"
    assert result.status is WorkerResultStatus.FAILED
    assert "internal error: unexpected panic" in (result.error or "")


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

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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

    log_path = _run_root_for(tmp_path) / "logs" / "DEVELOPMENT" / "attempt-1.stdout.log"
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


# --------------------------------------------------------------------------- #
# 07-03 Task 3 (QUAL-02): registering a worker name twice leaves exactly one
# bound factory -- the last registration wins.
# --------------------------------------------------------------------------- #


def test_duplicate_registration_binds_exactly_one_factory() -> None:
    from dark_factory.domain.worker import WorkerCapabilities, WorkerResult
    from dark_factory.workers.base import CodingWorker
    from dark_factory.workers.registry import WorkerRegistry

    class _First(CodingWorker):
        def execute(self, context: object) -> WorkerResult:
            raise NotImplementedError

        def resume(
            self, context: object, previous: WorkerResult, answer: str | None
        ) -> WorkerResult:
            raise NotImplementedError

        def capabilities(self) -> WorkerCapabilities:
            raise NotImplementedError

    class _Second(CodingWorker):
        def execute(self, context: object) -> WorkerResult:
            raise NotImplementedError

        def resume(
            self, context: object, previous: WorkerResult, answer: str | None
        ) -> WorkerResult:
            raise NotImplementedError

        def capabilities(self) -> WorkerCapabilities:
            raise NotImplementedError

    registry = WorkerRegistry()
    registry.register("claude-code", _First)
    registry.register("claude-code", _Second)

    assert "claude-code" in registry
    assert isinstance(registry.get("claude-code"), _Second)


def test_default_registry_claude_code_is_not_the_not_yet_implemented_worker() -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker
    from dark_factory.workers.registry import default_registry

    worker = default_registry.get("claude-code")
    assert isinstance(worker, ClaudeCodeWorker)
    assert type(worker).__name__ != "_NotYetImplementedWorker"


# --------------------------------------------------------------------------- #
# 07-04 Task 1: the spawned agent gets exactly the native tools the role was
# granted -- `--allowedTools` derived from `context.tools` through
# `NATIVE_TOOL_CONTRACT`, deny by omission (WORK-04).
# --------------------------------------------------------------------------- #


def test_allowed_tools_for_repo_read_and_search_union_sorted_deduped() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"repo.read", "repo.search"}, None) == [
        "Glob",
        "Grep",
        "Read",
    ]


def test_allowed_tools_for_shell_execute() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"shell.execute"}, None) == ["Bash"]


def test_allowed_tools_for_repo_write() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"repo.write"}, None) == ["Edit", "Write"]


def test_allowed_tools_for_repo_write_tests() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"repo.write_tests"}, None) == ["Edit", "Write"]


def test_allowed_tools_for_artifacts_read_with_no_glob_yields_nothing() -> None:
    """A bare ``Read`` grant would give unrestricted worktree-wide native
    read access -- deny by omission, exactly like ``artifacts.write`` when
    it has no glob to scope to (CR-01)."""
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"artifacts.read"}, None) == []


def test_allowed_tools_for_artifacts_read_is_path_scoped_not_bare() -> None:
    """``artifacts.read`` must translate to a path-scoped ``Read(<glob>/**)``
    specifier over the run's artifacts tree, never a bare ``Read`` grant
    (CR-01) -- the sibling ``artifacts.write`` capability already gets this
    treatment; read was the one capability left ungated."""
    from dark_factory.workers.claude_code import allowed_tools_for

    result = allowed_tools_for(
        set(), None, artifacts_read_glob=".dark-factory/runs/R/artifacts"
    )
    assert result == []  # not granted -> still nothing, even with a glob

    result = allowed_tools_for(
        {"artifacts.read"}, None, artifacts_read_glob=".dark-factory/runs/R/artifacts"
    )
    assert result == ["Read(.dark-factory/runs/R/artifacts/**)"]


def test_allowed_tools_for_artifacts_write_is_path_scoped_not_bare() -> None:
    """The name's claim is unchanged -- both specifiers are path-scoped,
    neither is a bare tool name. The real ``claude`` CLI permission-gates
    its new-file tool (``Write``) and its existing-file tool (``Edit``)
    separately, and a role's first write to any declared output creates a
    new file, so both specifiers must be granted over the identical glob.
    The assertion also pins the pair's sorted order (``Edit`` before
    ``Write``), which is what makes the joined ``--allowedTools`` argv
    value in the sibling spawn test deterministic."""
    from dark_factory.workers.claude_code import allowed_tools_for

    glob = ".dark-factory/runs/R/artifacts/DEVELOPMENT"
    result = allowed_tools_for({"artifacts.write"}, glob)

    assert result == [f"Edit({glob}/**)", f"Write({glob}/**)"], result


def test_artifacts_write_grants_the_new_file_tool_not_only_the_edit_tool() -> None:
    """The real ``claude`` CLI permission-gates its new-file tool (``Write``)
    and its existing-file tool (``Edit``) as two separate tools under
    ``--permission-mode dontAsk``. Every role's first write to any declared
    output creates a new file, so an ``Edit``-only grant denies that first
    write outright -- the CLI refuses an absent tool rather than escalating
    to a prompt in this mode.

    This was observed live against a real target repository's CI run: the
    BA role's two declared outputs (``requirements.md`` and
    ``acceptance_criteria.json``) were both denied and the run reached
    FAILED. Dark Factory's own suite never caught it because the fake
    ``claude`` script on ``PATH`` in every other test simulates no
    permission gating at all -- it writes declared outputs unconditionally,
    so the Write/Edit split the real CLI enforces is invisible to the whole
    test tree. This test names ``Write`` specifically so that gap cannot
    reopen silently."""
    from dark_factory.workers.claude_code import allowed_tools_for

    glob = ".dark-factory/runs/R/artifacts/BA"
    result = allowed_tools_for({"artifacts.write"}, glob)

    # The assertion that fails before the fix: the new-file tool must be
    # granted, not only the existing-file tool.
    assert f"Write({glob}/**)" in result, (
        f"expected Write({glob}/**) in {result} -- the new-file tool is "
        "missing from the artifacts.write grant"
    )
    assert f"Edit({glob}/**)" in result, (
        f"expected Edit({glob}/**) in {result} -- additive, not a swap"
    )
    assert set(result) == {f"Edit({glob}/**)", f"Write({glob}/**)"}, (
        f"expected exactly the Edit/Write pair over {glob}, got {result}"
    )
    assert "Write" not in result, f"bare Write must never appear, got {result}"
    assert "Edit" not in result, f"bare Edit must never appear, got {result}"
    for specifier in result:
        # Every member's parenthesised argument is that one glob -- no
        # member may carry a broader pattern such as the run root or the
        # artifacts tree without the role subtree.
        assert specifier.endswith(f"({glob}/**)"), (
            f"expected every specifier scoped to exactly {glob}, got {specifier}"
        )


def test_allowed_tools_for_artifacts_write_with_no_glob_yields_nothing() -> None:
    """A context-free call has no run_id/artifacts_dir to build a glob from
    -- the specifier must be skipped, never fabricated."""
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for({"artifacts.write"}, None) == []


def test_allowed_tools_for_empty_grant_yields_empty_list() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    assert allowed_tools_for(set(), None) == []


def test_allowed_tools_for_is_deterministic_across_calls() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for

    granted = {"repo.write", "shell.execute", "repo.read"}
    first = allowed_tools_for(granted, None)
    second = allowed_tools_for(granted, None)

    assert first == second


def test_tool_names_cover_every_native_contract_capability() -> None:
    """T-07-18: a capability added to ``NATIVE_TOOL_CONTRACT`` with no
    translation must fail this test, not silently grant nothing."""
    from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
    from dark_factory.workers.claude_code import _TOOL_NAMES

    assert set(_TOOL_NAMES) | {"artifacts.write", "artifacts.read"} == set(
        NATIVE_TOOL_CONTRACT
    )


def test_ungranted_capability_contributes_no_tool_name() -> None:
    """Deny by omission (`NativeToolGrant.absent_behaviour`): a role denied
    `shell.execute` gets no `Bash` in its `--allowedTools` value at all."""
    from dark_factory.workers.claude_code import allowed_tools_for

    result = allowed_tools_for({"repo.read"}, None)

    assert "Bash" not in result


def test_allowed_tools_flag_present_in_execute_argv_for_granted_role(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(_context(tools=["repo.read", "repo.search"]))

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Glob,Grep,Read"


def test_allowed_tools_flag_present_in_resume_argv_for_granted_role(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    context = _context(tools=["shell.execute"])
    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().resume(
            context, _paused_with_session_id("sess-abc"), "answer"
        )

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Bash"


def test_no_tools_granted_produces_no_allowed_tools_flag(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(_context(tools=[]))

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--allowedTools" not in argv
    assert result.status.value == "COMPLETED"


def test_artifacts_write_grant_produces_path_scoped_edit_in_execute_argv(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This test's subject is the end-to-end argv -- it proves the Edit/
    Write pair survives ``_base_argv``'s join and reaches the spawned
    process, which is the only place the real CLI ever reads it."""
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(
            _context(role="DEVELOPMENT", tools=["artifacts.write"])
        )

    argv = json.loads(argv_log.read_text("utf-8"))
    value = argv[argv.index("--allowedTools") + 1]
    glob = f".dark-factory/runs/{_RUN_ID}/artifacts/DEVELOPMENT"
    assert value == f"Edit({glob}/**),Write({glob}/**)"


def test_artifacts_read_grant_produces_path_scoped_read_in_execute_argv(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-01: ``artifacts.read`` must reach the spawned CLI as a path-scoped
    ``Read(<run>/artifacts/**)`` specifier over the whole run's artifacts
    tree (a worker legitimately reads a *prior* role's output), not a bare
    ``Read`` that would grant unrestricted native filesystem access."""
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_claude(fake_dir, stdout_payload=_SUCCESS_PAYLOAD, argv_log=argv_log)

    with fake_claude_env(monkeypatch, fake_dir):
        ClaudeCodeWorker().execute(
            _context(role="DEVELOPMENT", tools=["artifacts.read"])
        )

    argv = json.loads(argv_log.read_text("utf-8"))
    value = argv[argv.index("--allowedTools") + 1]
    assert value == f"Read(.dark-factory/runs/{_RUN_ID}/artifacts/**)"


# --------------------------------------------------------------------------- #
# 08-01 Task 3: a real adapter reports the artifacts its CLI actually wrote,
# through the shared cli_runtime.collect_declared_artifacts helper.
# --------------------------------------------------------------------------- #


def test_end_to_end_completed_result_reports_declared_artifact(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = _run_root_for(tmp_path) / "artifacts" / "DEVELOPMENT"
    script_path = fake_dir / "claude"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys

os.makedirs({str(artifacts_dir)!r}, exist_ok=True)
with open(os.path.join({str(artifacts_dir)!r}, "implementation_summary.json"), "w") as fh:
    fh.write("{{}}")
sys.stdout.write(json.dumps({{
    "subtype": "success",
    "duration_ms": 1,
    "duration_api_ms": 1,
    "is_error": False,
    "num_turns": 1,
    "session_id": "sess-artifacts",
    "total_cost_usd": 0.0,
    "usage": {{}},
    "result": "done",
    "structured_output": None,
    "permission_denials": [],
}}))
sys.exit(0)
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    context = _context(role="DEVELOPMENT", outputs=["implementation_summary.json"])
    with fake_claude_env(monkeypatch, fake_dir):
        result = ClaudeCodeWorker().execute(context)

    assert result.status.value == "COMPLETED"
    assert {ref.type for ref in result.artifacts} == {"implementation_summary.json"}
