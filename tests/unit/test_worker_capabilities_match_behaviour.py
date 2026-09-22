"""ROADMAP SC4 proof: each real adapter's declared ``WorkerCapabilities`` are
checked against its own observed argv and result, never against a repeated
literal (Plan 08-03, Task 3).

Every test below reads the declaration first (``worker.capabilities()``),
then observes the behaviour (the argv the adapter actually built, or the
``WorkerResult`` it actually returned), then asserts the two agree -- never
"assert the declaration equals this literal", which would only restate the
source. 08-RESEARCH.md Finding 2 records exactly the failure mode this
module exists to catch: a ``native_resume=True`` declaration with no test
driving the native branch.

The ``session_id`` axis is deliberately NOT re-tested here:
``tests/contract/test_coding_worker_contract.py::
test_worker_session_id_matches_capability_declaration`` already pins that
one for all four workers (see this module's own ``read_first`` list in
08-03-PLAN.md). This module covers the three axes that suite does not:
``native_resume``, ``structured_output`` and ``non_interactive`` (all three
argv-observable, so subprocess-adapter-only), plus ``emits_changed_files``
(observable for every worker, including ``FakeWorker``, which spawns
nothing and has no argv to observe at all).
"""

from __future__ import annotations

import json
import stat
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import NamedTuple

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.claude_code import ClaudeCodeWorker
from dark_factory.workers.copilot import CopilotWorker
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.hermes import HermesWorker
from tests.support.fake_claude_cli import fake_claude_env, write_fake_claude
from tests.support.fake_copilot_cli import fake_copilot_env, write_fake_copilot
from tests.support.fake_hermes_cli import fake_hermes_env, write_fake_hermes

pytestmark = pytest.mark.unit

_RUN_ID = "8f14e45f-ceea-467e-adde-3fb5b2c8de9c"

# The whole NATIVE_TOOL_CONTRACT capability vocabulary -- fully granted, so
# every adapter's own spawn-admission rule (HermesWorker.spawn_is_permitted)
# never blocks any test in this module; which axis is under test is what
# varies, never whether the role holds enough capabilities to run at all.
_FULL_GRANT: list[str] = [
    "repo.read",
    "repo.search",
    "repo.write",
    "repo.write_tests",
    "shell.execute",
    "artifacts.read",
    "artifacts.write",
]

# A JSON payload whose extracted "result" field is a different string from
# the payload's own raw serialisation -- so the structured-output axis can
# tell "the adapter parsed a field out" apart from "the adapter used the raw
# text verbatim" by comparing result.summary against each string in turn.
_CLAUDE_STRUCTURED_PAYLOAD = json.dumps(
    {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "sess-observed",
        "total_cost_usd": 0.0,
        "usage": {},
        "result": "the-extracted-result-text",
        "structured_output": None,
        "permission_denials": [],
    }
)
_PLAINTEXT_PAYLOAD = "the-raw-plaintext-result"


def _context(*, role: str, tools: list[str]) -> RoleContext:
    return RoleContext(
        run_id=_RUN_ID,
        role=role,
        worker=role.lower(),
        attempt=1,
        task={"source_kind": "text", "source_ref": None, "title": "t", "body": "b"},
        answer=None,
        instructions="Do the work.",
        inputs=[],
        baseline_docs={},
        examples=[],
        constraints={},
        tools=tools,
        permissions={},
        outputs=[],
        artifacts_dir=f"artifacts/{role}",
    )


@pytest.fixture
def repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo-shaped ``tmp_path`` subdirectory; ``monkeypatch.chdir()``s into
    it so the ``dark-factory-runs`` sibling-of-``cwd`` formula
    (``resolve_dirs`` in ``cli_runtime.py``) resolves under ``tmp_path``,
    never the real repo -- mirrors ``test_hermes_worker.py::repo_dir``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    return repo


# --------------------------------------------------------------------------- #
# The per-worker installer table. Each subprocess adapter is paired with its
# own fake-CLI writer and credential-setting context manager (mirrors this
# module's own read_first list: fake_copilot_cli.py / fake_hermes_cli.py /
# fake_claude_cli.py's argv-log mechanism). FakeWorker's installer is a
# documented no-op -- it spawns nothing, so there is no CLI to write and no
# credential to set.
# --------------------------------------------------------------------------- #


@contextmanager
def _claude_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: str,
    *,
    argv_log: Path | None = None,
) -> Iterator[None]:
    fake_dir = tmp_path / "fakebin"
    write_fake_claude(fake_dir, stdout_payload=payload, argv_log=argv_log)
    with fake_claude_env(monkeypatch, fake_dir):
        yield


@contextmanager
def _copilot_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: str,
    *,
    argv_log: Path | None = None,
) -> Iterator[None]:
    fake_dir = tmp_path / "fakebin"
    write_fake_copilot(fake_dir, stdout_payload=payload, argv_log=argv_log)
    with fake_copilot_env(monkeypatch, fake_dir):
        yield


@contextmanager
def _hermes_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: str,
    *,
    argv_log: Path | None = None,
) -> Iterator[None]:
    fake_dir = tmp_path / "fakebin"
    write_fake_hermes(fake_dir, stdout_payload=payload, argv_log=argv_log)
    with fake_hermes_env(monkeypatch, fake_dir):
        yield


@contextmanager
def _fake_worker_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: str,
    *,
    argv_log: Path | None = None,
) -> Iterator[None]:
    """FakeWorker spawns nothing -- no CLI binary to write, no PATH entry,
    no credential to set. A documented no-op, not an omission."""
    yield


class _WorkerCase(NamedTuple):
    worker_name: str
    factory: Callable[[], CodingWorker]
    install: Callable[..., AbstractContextManager[None]]
    role: str
    payload: str


# Subprocess adapters only -- the argv-observable axes below (native_resume,
# structured_output, non_interactive) do not apply to FakeWorker, which has
# no argv at all.
_SUBPROCESS_CASES: list[_WorkerCase] = [
    _WorkerCase(
        "claude-code",
        ClaudeCodeWorker,
        _claude_installed,
        "DEVELOPMENT",
        _CLAUDE_STRUCTURED_PAYLOAD,
    ),
    _WorkerCase(
        "copilot", CopilotWorker, _copilot_installed, "ARCHITECTURE", _PLAINTEXT_PAYLOAD
    ),
    _WorkerCase("hermes", HermesWorker, _hermes_installed, "QA", _PLAINTEXT_PAYLOAD),
]

# All four workers, for the one axis (emits_changed_files) genuinely
# observable for every adapter including FakeWorker.
_ALL_WORKER_CASES: list[_WorkerCase] = [
    *_SUBPROCESS_CASES,
    _WorkerCase("fake", FakeWorker, _fake_worker_installed, "BA", ""),
]

_BINARY_NAMES = {"claude-code": "claude", "copilot": "copilot", "hermes": "hermes"}
_FAKE_ENVS = {
    "claude-code": fake_claude_env,
    "copilot": fake_copilot_env,
    "hermes": fake_hermes_env,
}

_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


# --------------------------------------------------------------------------- #
# Axis: native_resume -- resume() argv either does or does not carry the
# previous session id, matching the declaration exactly (08-RESEARCH.md
# Finding 2's warning sign: a True declaration with no native-branch test).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", _SUBPROCESS_CASES, ids=lambda c: c.worker_name)
def test_resume_argv_matches_the_native_resume_declaration(
    case: _WorkerCase, repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_log = tmp_path / "argv.json"
    previous = WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a decision",
        questions=["which cluster?"],
        worker_session_id="sess-xyz",
    )

    with case.install(monkeypatch, tmp_path, case.payload, argv_log=argv_log):
        worker = case.factory()
        caps = worker.capabilities()
        worker.resume(
            _context(role=case.role, tools=_FULL_GRANT), previous, "an answer"
        )

    argv = json.loads(argv_log.read_text("utf-8"))

    if caps.native_resume:
        # The declaring adapter: the id crosses as a single opaque argv
        # element immediately following its resume flag -- unparsed,
        # unmodified.
        assert "sess-xyz" in argv
        assert argv[argv.index("sess-xyz") - 1] == "--resume"
    else:
        # The non-declaring adapters: no resume element at all, and the
        # session id never appears anywhere in argv -- an adapter could
        # otherwise declare False while still quietly branching on it.
        assert "sess-xyz" not in argv
        assert "--resume" not in argv


# --------------------------------------------------------------------------- #
# Axis: structured_output -- both halves checked: the argv the adapter
# builds, and where result.summary actually came from.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", _SUBPROCESS_CASES, ids=lambda c: c.worker_name)
def test_structured_output_argv_and_summary_match_the_declaration(
    case: _WorkerCase, repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_log = tmp_path / "argv.json"

    with case.install(monkeypatch, tmp_path, case.payload, argv_log=argv_log):
        worker = case.factory()
        caps = worker.capabilities()
        result = worker.execute(_context(role=case.role, tools=_FULL_GRANT))

    argv = json.loads(argv_log.read_text("utf-8"))

    if caps.structured_output:
        assert "--output-format" in argv
        assert argv[argv.index("--output-format") + 1] == "json"
        assert result.summary == "the-extracted-result-text"
        assert result.summary != case.payload
    else:
        assert "--output-format" not in argv
        assert result.summary == case.payload


# --------------------------------------------------------------------------- #
# Axis: non_interactive -- execute() completes (never hangs) against a fake
# that reads from stdin only to observe it, and the spawn's stdin is
# genuinely closed (EOF), not merely unread. A DEVNULL-backed stdin returns
# EOF on the first read rather than blocking, so this assertion is about the
# spawn's own plumbing, not about wall-clock timing -- it cannot become
# flaky.
# --------------------------------------------------------------------------- #


def _write_stdin_probe_binary(
    directory: Path,
    binary_name: str,
    *,
    stdout_payload: str,
    stdin_state_path: Path,
) -> Path:
    """A minimal, self-contained fake executable written directly in this
    module (never in the shared ``tests/support/fake_*_cli.py`` helpers,
    which this module's own ``read_first`` list names only as the
    argv-log mechanism to mirror) -- probing the spawn's own stdin
    plumbing is specific to this one axis and belongs nowhere else."""
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / binary_name
    script = f"""#!/usr/bin/env python3
import sys

stdin_state_path = {str(stdin_state_path)!r}
stdout_payload = {stdout_payload!r}

try:
    data = sys.stdin.read()
    state = "closed-eof" if data == "" else f"unexpected-data:{{data!r}}"
except Exception as exc:  # pragma: no cover -- diagnostic only
    state = f"error:{{exc!r}}"

with open(stdin_state_path, "w", encoding="utf-8") as fh:
    fh.write(state)

sys.stdout.write(stdout_payload)
sys.stdout.flush()
sys.exit(0)
"""
    script_path.write_text(script, encoding="utf-8")
    mode = script_path.stat().st_mode
    script_path.chmod(mode | _EXEC_BITS)
    return directory


@pytest.mark.parametrize("case", _SUBPROCESS_CASES, ids=lambda c: c.worker_name)
def test_non_interactive_axis_spawns_with_closed_stdin_and_completes(
    case: _WorkerCase, repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_dir = tmp_path / "fakebin"
    stdin_state_path = tmp_path / "stdin_state.txt"
    _write_stdin_probe_binary(
        fake_dir,
        _BINARY_NAMES[case.worker_name],
        stdout_payload=case.payload,
        stdin_state_path=stdin_state_path,
    )
    fake_env = _FAKE_ENVS[case.worker_name]

    with fake_env(monkeypatch, fake_dir):
        worker = case.factory()
        caps = worker.capabilities()
        result = worker.execute(_context(role=case.role, tools=_FULL_GRANT))

    assert caps.non_interactive is True
    assert isinstance(result, WorkerResult)
    assert isinstance(result.status, WorkerResultStatus)
    assert stdin_state_path.read_text("utf-8") == "closed-eof"


# --------------------------------------------------------------------------- #
# Axis: emits_changed_files -- the one axis genuinely observable for every
# worker, including FakeWorker, which spawns nothing. Parametrized over all
# four workers per this module's own action text.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", _ALL_WORKER_CASES, ids=lambda c: c.worker_name)
def test_emits_changed_files_is_false_and_changed_files_is_empty(
    case: _WorkerCase, repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with case.install(monkeypatch, tmp_path, case.payload):
        worker = case.factory()
        caps = worker.capabilities()
        context = (
            None
            if case.worker_name == "fake"
            else _context(role=case.role, tools=_FULL_GRANT)
        )
        result = worker.execute(context)

    assert caps.emits_changed_files is False
    assert result.changed_files == []


# --------------------------------------------------------------------------- #
# FakeWorker, handled separately (it spawns nothing, so the argv-observable
# axes above do not apply to it at all): only the axes observable from its
# return value alone are checked here. emits_changed_files is already
# covered by the four-way parametrization above; session_id is the one
# remaining axis this module checks for FakeWorker specifically (the
# subprocess adapters' session_id axis is already pinned by
# tests/contract/test_coding_worker_contract.py, per this module's own
# docstring).
# --------------------------------------------------------------------------- #


def test_fake_worker_session_id_matches_its_declaration() -> None:
    worker = FakeWorker()
    caps = worker.capabilities()
    result = worker.execute(None)

    if caps.session_id:
        assert result.worker_session_id is not None
    else:
        assert result.worker_session_id is None
