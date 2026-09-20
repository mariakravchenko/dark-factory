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
