"""Unit coverage for CodingWorker enforcement, FakeWorker and WorkerRegistry (Plan 01-02 Task 3).

The plan lists these assertions in Task 3's acceptance criteria but assigns no
unit-test file for the worker behaviour itself (only the contract suite and the
two abstraction guards). This file holds them.
"""

import time

import pytest

from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker, ScriptExhaustedError
from dark_factory.workers.registry import (
    UnknownWorkerError,
    WorkerRegistry,
    default_registry,
)

pytestmark = pytest.mark.unit


def test_coding_worker_subclass_missing_methods_cannot_be_instantiated() -> None:
    class Partial(CodingWorker):
        def execute(self, context: object) -> WorkerResult:
            return WorkerResult(status=WorkerResultStatus.COMPLETED)

    with pytest.raises(TypeError):
        Partial()  # type: ignore[abstract]


def test_fake_worker_default_returns_one_completed_result_with_fake_session_id() -> (
    None
):
    worker = FakeWorker()
    result = worker.execute(None)
    assert result.status is WorkerResultStatus.COMPLETED
    assert result.worker_session_id is not None
    assert result.worker_session_id.startswith("fake-")


def test_fake_worker_capability_declaration_matches_behaviour() -> None:
    worker = FakeWorker()
    assert worker.capabilities().session_id is True
    assert worker.execute(None).worker_session_id is not None


def test_fake_worker_empty_script_raises_script_exhausted() -> None:
    worker = FakeWorker([])
    with pytest.raises(ScriptExhaustedError):
        worker.execute(None)


def test_fake_worker_returns_scripted_results_in_declaration_order() -> None:
    first = WorkerResult(status=WorkerResultStatus.COMPLETED, summary="one")
    second = WorkerResult(status=WorkerResultStatus.FAILED, summary="two", error="boom")
    worker = FakeWorker([first, second])
    assert worker.execute(None) is first
    assert worker.execute(None) is second
    with pytest.raises(ScriptExhaustedError):
        worker.execute(None)


def test_fake_worker_resume_delegates_to_execute() -> None:
    only = WorkerResult(status=WorkerResultStatus.COMPLETED, summary="once")
    worker = FakeWorker([only])
    previous = WorkerResult(status=WorkerResultStatus.NEEDS_INPUT, questions=["q?"])
    assert worker.resume(None, previous, "an answer") is only


def test_fake_worker_reads_script_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DARK_FACTORY_FAKE_SCRIPT",
        '[{"status": "FAILED", "summary": "scripted failure", "error": "x"}]',
    )
    worker = FakeWorker()
    assert worker.execute(None).status is WorkerResultStatus.FAILED


def test_fake_worker_explicit_empty_script_beats_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DARK_FACTORY_FAKE_SCRIPT", '[{"status": "COMPLETED"}]')
    worker = FakeWorker([])
    with pytest.raises(ScriptExhaustedError):
        worker.execute(None)


_SLEEP_MS_ENV_VAR = "DARK_FACTORY_FAKE_SLEEP_MS"


def _time_execute(worker: FakeWorker) -> float:
    """Return how many milliseconds a single ``execute`` call took."""
    start = time.perf_counter()
    worker.execute(None)
    return (time.perf_counter() - start) * 1000.0


def test_fake_worker_sleep_ms_constructor_arg_delays_execute() -> None:
    assert _time_execute(FakeWorker(sleep_ms=40)) >= 40.0


def test_fake_worker_with_no_sleep_returns_well_under_the_delay() -> None:
    assert _time_execute(FakeWorker()) < 40.0


def test_fake_worker_reads_sleep_ms_env_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = FakeWorker()
    # armed AFTER construction -- the knob must be read inside execute()
    monkeypatch.setenv(_SLEEP_MS_ENV_VAR, "40")
    assert _time_execute(worker) >= 40.0


def test_fake_worker_sleep_env_unset_performs_no_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_SLEEP_MS_ENV_VAR, raising=False)
    assert _time_execute(FakeWorker()) < 40.0


def test_fake_worker_constructor_sleep_ms_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_SLEEP_MS_ENV_VAR, "500")
    assert _time_execute(FakeWorker(sleep_ms=0)) < 100.0


def test_fake_worker_resume_inherits_the_delay() -> None:
    only = WorkerResult(status=WorkerResultStatus.COMPLETED, summary="once")
    worker = FakeWorker([only], sleep_ms=40)
    previous = WorkerResult(status=WorkerResultStatus.NEEDS_INPUT, questions=["q?"])
    start = time.perf_counter()
    assert worker.resume(None, previous, "an answer") is only
    assert (time.perf_counter() - start) * 1000.0 >= 40.0


def test_fake_worker_malformed_sleep_ms_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_SLEEP_MS_ENV_VAR, "not-an-int")
    with pytest.raises(ValueError):
        FakeWorker().execute(None)


def test_worker_registry_get_returns_a_fresh_instance() -> None:
    registry = WorkerRegistry()
    registry.register("fake", FakeWorker)
    first = registry.get("fake")
    second = registry.get("fake")
    assert isinstance(first, CodingWorker)
    assert first is not second


def test_worker_registry_unknown_name_raises() -> None:
    registry = WorkerRegistry()
    with pytest.raises(UnknownWorkerError):
        registry.get("nope")


def test_default_registry_has_fake_bound() -> None:
    assert isinstance(default_registry.get("fake"), CodingWorker)
    with pytest.raises(UnknownWorkerError):
        default_registry.get("nope")
