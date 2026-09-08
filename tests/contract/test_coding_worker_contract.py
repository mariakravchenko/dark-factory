"""The shared CodingWorker contract suite.

Parametrized over ``WORKER_FACTORIES``, which currently holds only
:class:`FakeWorker`. Phases 7-8 append ``ClaudeCodeWorker``, ``CopilotWorker`` and
``HermesWorker`` to that list -- this suite is the mechanism that stops the fake
drifting from real adapter semantics, so every downstream orchestration test
keeps testing a faithful worker rather than a divergent stub.
"""

from collections.abc import Callable

import pytest

from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker

pytestmark = pytest.mark.contract

WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker]


@pytest.fixture(params=WORKER_FACTORIES, ids=lambda factory: factory.__name__)
def worker(request: pytest.FixtureRequest) -> CodingWorker:
    factory = request.param
    return factory()


def test_execute_returns_a_worker_result(worker: CodingWorker) -> None:
    assert isinstance(worker.execute(None), WorkerResult)


def test_execute_status_is_a_worker_result_status_member(worker: CodingWorker) -> None:
    assert isinstance(worker.execute(None).status, WorkerResultStatus)


def test_worker_session_id_matches_capability_declaration(worker: CodingWorker) -> None:
    caps = worker.capabilities()
    result = worker.execute(None)
    if caps.session_id:
        assert result.worker_session_id is not None
    else:
        assert result.worker_session_id is None


def test_needs_input_result_carries_at_least_one_question(worker: CodingWorker) -> None:
    result = worker.execute(None)
    if result.status is WorkerResultStatus.NEEDS_INPUT:
        assert result.questions
