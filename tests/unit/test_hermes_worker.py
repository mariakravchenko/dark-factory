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
    assert Path(observed_env["XDG_CONFIG_HOME"]).parent == Path(
        observed_env["HERMES_HOME"]
    ).parent


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
