"""Unit coverage for :class:`HermesWorker` (Plan 08-02) -- the third real
:class:`~dark_factory.workers.base.CodingWorker` adapter, completing the
three-real-runtime set (WORK-06, D-04).

No live ``hermes`` binary and no live ``ANTHROPIC_API_KEY`` are ever used:
every test drives a fake ``hermes`` executable written by
``tests/support/fake_hermes_cli.py`` and prepended to ``PATH`` (D-02).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dark_factory.context.builder import RoleContext
from tests.support.fake_hermes_cli import fake_hermes_env, write_fake_hermes

pytestmark = pytest.mark.unit

_RUN_ID = "1b2e3c4d-5e6f-4789-9abc-def012345678"

# 08-RESEARCH.md Finding 4: "NEVER pass: --tui (forces interactive mode)".
# This adapter's argv must always be disjoint from this tuple.
_FORBIDDEN_HERMES_FLAGS = ("--tui",)

# The whole NATIVE_TOOL_CONTRACT capability vocabulary -- a role holding all
# seven is unambiguously "fully granted" under the checkpoint's Option A
# rule, so spawn_is_permitted() never blocks it. Used as _context()'s
# default `tools` so ordinary end-to-end behavior tests are not entangled
# with the spawn-admission tests below, which construct their own reduced
# grant lists explicitly.
_ALL_CAPABILITIES = [
    "repo.read",
    "repo.search",
    "repo.write",
    "repo.write_tests",
    "shell.execute",
    "artifacts.read",
    "artifacts.write",
]

# .dark-factory/roles/QA.yaml's shipped grant list -- deliberately withholds
# only repo.write (Phase 6 SC1's "QA can write tests but cannot publish"
# half). Under the checkpoint's chosen Option A, this must still permit a
# Hermes spawn because repo.write's denial is compensated by
# enforce_write_scope (ROLE-05).
_QA_GRANT = [
    "repo.read",
    "repo.search",
    "repo.write_tests",
    "shell.execute",
    "artifacts.read",
    "artifacts.write",
]


def _context(
    *,
    role: str = "QA",
    run_id: str = _RUN_ID,
    attempt: int = 1,
    tools: list[str] | None = None,
    outputs: list[str] | None = None,
) -> RoleContext:
    return RoleContext(
        run_id=run_id,
        role=role,
        worker="hermes",
        attempt=attempt,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="Run the test suite and report results.",
        inputs=[],
        baseline_docs={},
        examples=[],
        constraints={},
        tools=tools if tools is not None else list(_ALL_CAPABILITIES),
        permissions={},
        outputs=outputs or [],
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
# Task 1: a role runs end to end through the real `hermes` CLI, state
# isolated per role.
# --------------------------------------------------------------------------- #


def test_execute_returns_completed_with_summary_and_no_session_id(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload="hermes did the thing")

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.summary == "hermes did the thing"
    assert result.worker_session_id is None


def test_execute_empty_stdout_returns_completed_with_empty_summary(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload="")

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.summary == ""


def test_argv_contains_required_flags_and_prompt(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.cli_runtime import build_prompt
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    context = _context()
    with fake_hermes_env(monkeypatch, fake_dir):
        HermesWorker().execute(context)

    argv = json.loads(argv_log.read_text("utf-8"))
    assert argv[0].endswith("hermes")
    assert argv[1] == "chat"
    for flag in ("-q", "--oneshot", "-Q", "--ignore-user-config"):
        assert flag in argv
    assert argv[argv.index("-q") + 1] == build_prompt(context)


def test_argv_disjoint_from_forbidden_flags(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        HermesWorker().execute(_context())

    argv = json.loads(argv_log.read_text("utf-8"))
    assert set(argv).isdisjoint(_FORBIDDEN_HERMES_FLAGS)


def test_hermes_home_is_under_the_same_root_as_xdg_config_home(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    env_log = tmp_path / "env.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", env_log=env_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        HermesWorker().execute(_context(role="QA"))

    observed_env = json.loads(env_log.read_text("utf-8"))
    assert isinstance(observed_env["HERMES_HOME"], str)
    assert (
        Path(observed_env["XDG_CONFIG_HOME"]).parent
        == Path(observed_env["HERMES_HOME"]).parent
    )


def test_two_roles_observe_two_different_hermes_home_values(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    qa_env_log = tmp_path / "qa-env.json"
    ba_env_log = tmp_path / "ba-env.json"

    with fake_hermes_env(monkeypatch, fake_dir):
        write_fake_hermes(fake_dir, stdout_payload="ok", env_log=qa_env_log)
        HermesWorker().execute(_context(role="QA"))

        write_fake_hermes(fake_dir, stdout_payload="ok", env_log=ba_env_log)
        HermesWorker().execute(_context(role="BA"))

    qa_env = json.loads(qa_env_log.read_text("utf-8"))
    ba_env = json.loads(ba_env_log.read_text("utf-8"))
    assert qa_env["HERMES_HOME"] != ba_env["HERMES_HOME"]


def test_subprocess_env_has_credential_and_lacks_infra_secrets(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    env_log = tmp_path / "env.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", env_log=env_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        # Both present in the parent process for the duration of the call --
        # build_worker_env() must still exclude them from the child.
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fakefakefakefakefakefakefakefake0000")
        HermesWorker().execute(_context())

    observed_env = json.loads(env_log.read_text("utf-8"))
    assert "ANTHROPIC_API_KEY" in observed_env
    assert "DATABASE_URL" not in observed_env
    assert "GITHUB_TOKEN" not in observed_env


def test_missing_credential_returns_failed_and_spawns_nothing(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        result = HermesWorker().execute(_context())
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert "ANTHROPIC_API_KEY" in (result.error or "")
    assert not argv_log.exists()


def test_default_registry_returns_a_hermes_worker_instance() -> None:
    from dark_factory.workers.hermes import HermesWorker
    from dark_factory.workers.registry import default_registry

    worker = default_registry.get("hermes")
    assert isinstance(worker, HermesWorker)
    assert type(worker).__name__ != "_NotYetImplementedWorker"


def test_hermes_worker_is_constructible_with_zero_arguments() -> None:
    from dark_factory.workers.hermes import HermesWorker

    assert HermesWorker() is not None


def test_missing_worker_credential_error_is_importable_and_a_runtime_error() -> None:
    from dark_factory.workers.hermes import MissingWorkerCredentialError

    assert issubclass(MissingWorkerCredentialError, RuntimeError)


# --------------------------------------------------------------------------- #
# Task 1: spawn-admission (checkpoint decision, Option A).
# --------------------------------------------------------------------------- #


def test_spawn_is_permitted_returns_none_for_a_fully_granted_role() -> None:
    from dark_factory.workers.hermes import spawn_is_permitted

    assert spawn_is_permitted(_ALL_CAPABILITIES) is None


def test_spawn_is_permitted_names_the_blocking_capability() -> None:
    from dark_factory.workers.hermes import spawn_is_permitted

    granted = [c for c in _ALL_CAPABILITIES if c != "shell.execute"]
    assert spawn_is_permitted(granted) == "shell.execute"


def test_spawn_is_permitted_allows_the_shipped_qa_grant_list() -> None:
    """Checkpoint decision: Option A (narrow the refusal rule to
    capabilities with no compensating control). QA's shipped grant
    withholds only repo.write, and repo.write's denial is compensated by
    enforce_write_scope (ROLE-05), so this must not block."""
    from dark_factory.workers.hermes import spawn_is_permitted

    assert spawn_is_permitted(_QA_GRANT) is None


def test_a_denied_non_compensated_capability_produces_failed_and_spawns_nothing(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    granted = [c for c in _ALL_CAPABILITIES if c != "shell.execute"]
    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context(tools=granted))

    assert result.status is WorkerResultStatus.FAILED
    assert "shell.execute" in (result.error or "")
    assert not argv_log.exists()


def test_unenforceable_grant_error_is_importable_and_a_runtime_error() -> None:
    from dark_factory.workers.hermes import UnenforceableGrantError

    assert issubclass(UnenforceableGrantError, RuntimeError)


def test_write_compensated_capabilities_are_a_subset_of_the_contract() -> None:
    """A renamed or removed NATIVE_TOOL_CONTRACT capability must fail this
    test, not silently widen or narrow the write-compensated set
    spawn_is_permitted() relies on."""
    from dark_factory.workers.hermes import (
        _write_compensated_capabilities_are_a_subset_of_the_contract,
    )

    assert _write_compensated_capabilities_are_a_subset_of_the_contract()


def test_a_none_context_is_exempted_from_spawn_admission(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared CodingWorker contract suite calls `execute(None)` -- a
    call carrying no context at all is a contract-suite shape, never a
    configured role, so it must not be blocked by spawn_is_permitted the
    way an empty `tools=[]` grant on a *real* context would be."""
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload="ok")

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(None)

    assert result.status is WorkerResultStatus.COMPLETED


# --------------------------------------------------------------------------- #
# Task 2: every Hermes failure path becomes a FAILED result, resume
# reconstructs context, and the contract suite runs all four workers.
# --------------------------------------------------------------------------- #

_FAKE_HERMES_SECRET = "sk-ant-fakefakefakefakefakefakefakefake0000"


def test_timeout_kills_process_group_and_persists_output(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import time

    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    fake_dir.mkdir(parents=True, exist_ok=True)
    script_path = fake_dir / "hermes"
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

    with fake_hermes_env(monkeypatch, fake_dir):
        monkeypatch.setenv("WORKER_TIMEOUT_SECONDS", "2")
        from dark_factory.config.settings import get_settings

        get_settings.cache_clear()
        start = time.monotonic()
        result = HermesWorker().execute(_context())
        elapsed = time.monotonic() - start
        get_settings.cache_clear()

    assert result.status is WorkerResultStatus.FAILED
    assert result.metadata["timed_out"] is True
    assert result.metadata["exit_code"] is None
    assert elapsed < 55  # fires at ~2s, not the 1800s default
    assert "2" in (result.error or "")

    log_path = _run_root_for(tmp_path) / "logs" / "QA" / "attempt-1.stdout.log"
    assert "pre-sleep line" in log_path.read_text("utf-8", errors="replace")

    # Give the OS a beat to actually reap/kill the grandchild before probing.
    time.sleep(0.5)
    grandchild_pid = int(grandchild_pid_file.read_text("utf-8").strip())
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)


@pytest.mark.parametrize("exit_code", [1, 2, 75])
def test_non_zero_exit_returns_failed_with_exit_code_and_stderr(
    exit_code: int,
    repo_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(
        fake_dir, stdout_payload="", exit_code=exit_code, stderr_text="hermes blew up"
    )

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert result.metadata["exit_code"] == exit_code
    assert "hermes blew up" in (result.error or "")


def test_missing_hermes_binary_returns_failed_without_raising(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    empty_dir = tmp_path / "empty-bin"
    empty_dir.mkdir()
    with fake_hermes_env(monkeypatch, empty_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.FAILED
    assert result.error


def test_needs_input_marker_produces_needs_input_with_question(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(
        fake_dir,
        stdout_payload="I need a decision.\nNEEDS_INPUT: Which suite?\nUnit or integration?",
    )

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.NEEDS_INPUT
    assert len(result.questions) == 1
    assert "Which suite?" in result.questions[0]
    assert "Unit or integration?" in result.questions[0]


def test_needs_input_marker_mid_sentence_does_not_trigger(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(
        fake_dir,
        stdout_payload="This mentions NEEDS_INPUT: mid-sentence, not at line start.",
    )

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED


def test_needs_input_marker_followed_by_only_whitespace_degrades_to_completed(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload="Done.\nNEEDS_INPUT:   \n  ")

    with fake_hermes_env(monkeypatch, fake_dir):
        # Must not raise a pydantic ValidationError from inside the adapter.
        result = HermesWorker().execute(_context())

    assert result.status is WorkerResultStatus.COMPLETED
    assert result.questions == []


def _paused_previous() -> object:
    from dark_factory.domain.worker import WorkerResult, WorkerResultStatus

    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a decision about test scope",
        questions=["which suite should I run?"],
    )


def test_resume_reconstructs_context_no_resume_flag(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        HermesWorker().resume(_context(), _paused_previous(), "the integration suite")

    argv = json.loads(argv_log.read_text("utf-8"))
    assert "--resume" not in argv
    prompt = argv[argv.index("-q") + 1]
    assert "need a decision about test scope" in prompt
    assert "which suite should I run?" in prompt
    assert "the integration suite" in prompt


def test_resume_with_null_answer_still_returns_a_result_and_records_no_answer(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.domain.worker import WorkerResult
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    argv_log = tmp_path / "argv.json"
    write_fake_hermes(fake_dir, stdout_payload="ok", argv_log=argv_log)

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().resume(_context(), _paused_previous(), None)

    assert isinstance(result, WorkerResult)
    argv = json.loads(argv_log.read_text("utf-8"))
    prompt = argv[argv.index("-q") + 1]
    assert "no answer was supplied" in prompt


def test_resume_accepts_a_none_context(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors the execute(None) exemption: the contract suite calls
    `resume(None, ...)` too, and it must not be blocked by
    spawn_is_permitted -- a None context is a contract-suite shape, never a
    configured role's empty grant list."""
    from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload="ok")

    with fake_hermes_env(monkeypatch, fake_dir):
        result = HermesWorker().resume(None, _paused_previous(), "an answer")

    assert isinstance(result, WorkerResult)
    assert result.status is WorkerResultStatus.COMPLETED


def test_captured_output_is_redacted(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dark_factory.workers.hermes import HermesWorker

    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(
        fake_dir, stdout_payload=f"leaked credential: {_FAKE_HERMES_SECRET}"
    )

    with fake_hermes_env(monkeypatch, fake_dir, anthropic_api_key=_FAKE_HERMES_SECRET):
        HermesWorker().execute(_context())

    log_path = _run_root_for(tmp_path) / "logs" / "QA" / "attempt-1.stdout.log"
    log_text = log_path.read_text("utf-8")
    assert "[redacted:" in log_text
    assert _FAKE_HERMES_SECRET not in log_text

    # Present-then-absent: an un-scrubbed control read of the same payload
    # does contain the literal, proving the redaction pass -- not the fake
    # itself -- is what removes it.
    assert _FAKE_HERMES_SECRET in f"leaked credential: {_FAKE_HERMES_SECRET}"
