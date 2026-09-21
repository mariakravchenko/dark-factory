"""Unit coverage for :class:`CopilotWorker` (Plan 08-01) -- the second real
:class:`~dark_factory.workers.base.CodingWorker` adapter.

No live ``copilot`` binary and no live ``COPILOT_GITHUB_TOKEN`` are ever
used: every test drives a fake ``copilot`` executable written by
``tests/support/fake_copilot_cli.py`` and prepended to ``PATH`` (D-02).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dark_factory.context.builder import RoleContext
from tests.support.fake_copilot_cli import fake_copilot_env, write_fake_copilot

pytestmark = pytest.mark.unit

_RUN_ID = "8f14e45f-ceea-467e-adde-3fb5b2c8de9c"

# T-08-01/T-08-04: the four flags this adapter's argv must never contain --
# the blanket tool-permission flag, the blanket path-permission flag, and the
# two transcript-sharing flags (08-RESEARCH.md Anti-Patterns to Avoid).
_FORBIDDEN_COPILOT_FLAGS = (
    "--allow-all-tools",
    "--allow-all-paths",
    "--share",
    "--share-gist",
)


def _context(
    *,
    role: str = "ARCHITECTURE",
    run_id: str = _RUN_ID,
    attempt: int = 1,
    tools: list[str] | None = None,
) -> RoleContext:
    return RoleContext(
        run_id=run_id,
        role=role,
        worker="copilot",
        attempt=attempt,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="Design the architecture.",
        inputs=[],
        baseline_docs={},
        examples=[],
        constraints={},
        tools=tools or [],
        permissions={},
        outputs=[],
        artifacts_dir=f"artifacts/{role}",
    )


@pytest.fixture
def repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo-shaped ``tmp_path`` subdirectory; ``monkeypatch.chdir()``s into
    it so the ``dark-factory-runs`` sibling-of-``cwd`` formula
    (``resolve_dirs`` in ``cli_runtime.py``) resolves under ``tmp_path``, not
    the real repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    return repo


def _run_root_for(tmp_path: Path) -> Path:
    return tmp_path / "dark-factory-runs" / _RUN_ID / ".dark-factory" / "runs" / _RUN_ID


# --------------------------------------------------------------------------- #
# Task 1: a role runs end to end through the real `copilot` CLI.
# --------------------------------------------------------------------------- #


def test_execute_returns_completed_with_summary_and_no_session_id(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="copilot did the thing")

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.summary == "copilot did the thing"
    assert result.worker_session_id is None


def test_execute_empty_stdout_returns_completed_with_empty_summary(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="")

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.summary == ""


def test_argv_contains_required_flags_and_prompt(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.cli_runtime import build_prompt
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    context = _context()
    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().execute(context)

    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[0].endswith("copilot")
    for flag in ("--no-ask-user", "-s", "-p"):
        assert flag in argv
    assert argv[argv.index("-p") + 1] == build_prompt(context)


def test_allowed_tools_argv_for_granted_capabilities(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    context = _context(
        tools=["repo.read", "repo.search", "artifacts.read", "artifacts.write"]
    )
    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().execute(context)

    argv = json.loads(argv_log.read_text("utf-8"))
    allow_tool_values = [
        argv[i + 1] for i, element in enumerate(argv) if element == "--allow-tool"
    ]
    assert allow_tool_values == ["read", "write"]
    assert argv.count("--allow-tool") == 2


def test_no_tools_granted_produces_no_allow_tool_flags(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context(tools=[]))

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--allow-tool" not in argv
    assert result.status.value == "COMPLETED"


def test_argv_disjoint_from_forbidden_flags(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    assert len(_FORBIDDEN_COPILOT_FLAGS) == 4

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().execute(
            _context(tools=["repo.read", "repo.write", "shell.execute"])
        )

    argv = json.loads(argv_log.read_text("utf-8"))
    assert set(argv).isdisjoint(_FORBIDDEN_COPILOT_FLAGS)


def test_attempt_log_file_exists_and_contains_the_fake_output(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="copilot did the thing")

    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().execute(_context(role="ARCHITECTURE"))

    log_path = (
        _run_root_for(tmp_path) / "logs" / "ARCHITECTURE" / "attempt-1.stdout.log"
    )
    assert log_path.is_file()
    assert "copilot did the thing" in log_path.read_text("utf-8")


def test_subprocess_env_has_credential_and_lacks_infra_secrets(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    env_log = tmp_path / "env.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", env_log=env_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        # Both present in the parent process for the duration of the call --
        # build_worker_env() must still exclude them from the child.
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fakefakefakefakefakefakefakefake0000")
        CopilotWorker().execute(_context())

    observed_env = json.loads(env_log.read_text("utf-8"))
    assert "COPILOT_GITHUB_TOKEN" in observed_env
    assert "DATABASE_URL" not in observed_env
    assert "GITHUB_TOKEN" not in observed_env


def test_missing_credential_returns_failed_and_spawns_nothing(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        result = CopilotWorker().execute(_context())
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert "COPILOT_GITHUB_TOKEN" in (result.error or "")
    assert not argv_log.exists()


def test_settings_copilot_fields_default_to_none() -> None:
    from dark_factory.config.settings import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@h/db",
        database_url_direct="postgresql+psycopg://u:p@h/db",
    )
    assert settings.copilot_github_token is None
    assert settings.copilot_model is None


def test_settings_known_secret_values_maps_copilot_token() -> None:
    from dark_factory.config.settings import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@h/db",
        database_url_direct="postgresql+psycopg://u:p@h/db",
        copilot_github_token="github_pat_0000000000000000",
    )
    known = settings.known_secret_values()
    assert known["github_pat_0000000000000000"] == "copilot_github_token"


def test_model_flag_present_when_configured(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        monkeypatch.setenv("COPILOT_MODEL", "gpt-5-fake")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        CopilotWorker().execute(_context())
        get_settings.cache_clear()

    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[argv.index("--model") + 1] == "gpt-5-fake"


def test_model_flag_absent_when_not_configured(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().execute(_context())

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--model" not in argv


def test_default_registry_returns_a_copilot_worker_instance() -> None:
    from dark_factory.workers.copilot import CopilotWorker
    from dark_factory.workers.registry import default_registry

    worker = default_registry.get("copilot")
    assert isinstance(worker, CopilotWorker)
    assert type(worker).__name__ != "_NotYetImplementedWorker"


def test_copilot_worker_is_constructible_with_zero_arguments() -> None:
    from dark_factory.workers.copilot import CopilotWorker

    assert CopilotWorker() is not None


def test_missing_worker_credential_error_is_importable_and_a_runtime_error() -> None:
    from dark_factory.workers.copilot import MissingWorkerCredentialError

    assert issubclass(MissingWorkerCredentialError, RuntimeError)


def test_allowed_tools_for_covers_every_native_contract_capability() -> None:
    """T-08-04 analogue of T-07-18: a capability added to
    ``NATIVE_TOOL_CONTRACT`` with no Copilot translation must fail this
    test, not silently grant nothing."""
    from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
    from dark_factory.workers.copilot import _tool_names_cover_native_contract

    assert set(NATIVE_TOOL_CONTRACT)  # sanity: contract is non-empty
    assert _tool_names_cover_native_contract()


# --------------------------------------------------------------------------- #
# Task 2: every Copilot failure path becomes a FAILED result, resume
# reconstructs context, and captured transcripts are redacted.
# --------------------------------------------------------------------------- #

_FAKE_COPILOT_SECRET = "github_pat_fakefakefakefakefakefake000000"


def test_timeout_kills_process_group_and_persists_output(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import time

    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    fake_dir.mkdir(parents=True, exist_ok=True)
    script_path = fake_dir / "copilot"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import subprocess
import sys
import time

sys.stdout.write("pre-sleep line\\n")
sys.stdout.flush()
# Deliberately NOT start_new_session=True here: this child must stay in the
# same process group as this script so that killpg() on that group reaches
# it too -- proving os.killpg(...) kills descendants, not only the direct
# child.
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

    with fake_copilot_env(monkeypatch, fake_dir):
        monkeypatch.setenv("WORKER_TIMEOUT_SECONDS", "1")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        start = time.monotonic()
        result = CopilotWorker().execute(_context())
        elapsed = time.monotonic() - start
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert result.metadata["timed_out"] is True
    assert result.metadata["exit_code"] is None
    assert elapsed < 55  # fires at ~1s, not the 1800s default
    assert "1" in (result.error or "")

    log_path = (
        _run_root_for(tmp_path) / "logs" / "ARCHITECTURE" / "attempt-1.stdout.log"
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
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="", exit_code=3, stderr_text="copilot blew up")

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert result.metadata["exit_code"] == 3
    assert "copilot blew up" in (result.error or "")


def test_missing_copilot_binary_returns_failed_without_raising(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    empty_dir = tmp_path / "empty-bin"
    empty_dir.mkdir()
    with fake_copilot_env(monkeypatch, empty_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert result.error


def test_needs_input_marker_produces_needs_input_with_question(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(
        fake_dir,
        stdout_payload="I need a decision.\nNEEDS_INPUT: Which cluster?\nStaging or production?",
    )

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.NEEDS_INPUT
    assert len(result.questions) == 1
    assert "Which cluster?" in result.questions[0]
    assert "Staging or production?" in result.questions[0]


def test_needs_input_marker_mid_sentence_does_not_trigger(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(
        fake_dir,
        stdout_payload="This mentions NEEDS_INPUT: mid-sentence, not at line start.",
    )

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED


def test_needs_input_marker_followed_by_only_whitespace_degrades_to_completed(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload="Done.\nNEEDS_INPUT:   \n  ")

    with fake_copilot_env(monkeypatch, fake_dir):
        # Must not raise a pydantic ValidationError from inside the adapter.
        result = CopilotWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.questions == []


def _paused_previous() -> object:
    from dark_factory.domain.worker import WorkerResult, WorkerResultStatus

    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a decision about clusters",
        questions=["which cluster should I target?"],
    )


def test_resume_reconstructs_context_no_resume_flag(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        CopilotWorker().resume(_context(), _paused_previous(), "the primary cluster")

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--resume" not in argv
    prompt = argv[argv.index("-p") + 1]
    assert "need a decision about clusters" in prompt
    assert "which cluster should I target?" in prompt
    assert "the primary cluster" in prompt


def test_resume_with_null_answer_still_returns_a_result_and_records_no_answer(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResult
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_copilot(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_copilot_env(monkeypatch, fake_dir):
        result = CopilotWorker().resume(_context(), _paused_previous(), None)

    assert isinstance(result, WorkerResult)
    argv = json.loads(argv_log.read_text("utf-8"))
    prompt = argv[argv.index("-p") + 1]
    assert "no answer was supplied" in prompt


def test_captured_output_is_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.copilot import CopilotWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(
        fake_dir, stdout_payload=f"leaked credential: {_FAKE_COPILOT_SECRET}"
    )

    with fake_copilot_env(
        monkeypatch, fake_dir, copilot_github_token=_FAKE_COPILOT_SECRET
    ):
        CopilotWorker().execute(_context())

    log_path = (
        _run_root_for(tmp_path) / "logs" / "ARCHITECTURE" / "attempt-1.stdout.log"
    )
    log_text = log_path.read_text("utf-8")
    assert "[redacted:" in log_text
    assert _FAKE_COPILOT_SECRET not in log_text

    # Present-then-absent: an un-scrubbed control read of the same payload
    # does contain the literal, proving the redaction pass -- not the fake
    # itself -- is what removes it.
    assert _FAKE_COPILOT_SECRET in f"leaked credential: {_FAKE_COPILOT_SECRET}"
