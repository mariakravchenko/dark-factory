"""The shared CodingWorker contract suite.

Parametrized over ``WORKER_FACTORIES``, which currently holds only
:class:`FakeWorker`. Phases 7-8 append ``ClaudeCodeWorker``, ``CopilotWorker`` and
``HermesWorker`` to that list -- this suite is the mechanism that stops the fake
drifting from real adapter semantics, so every downstream orchestration test
keeps testing a faithful worker rather than a divergent stub.

It now covers **both** methods the orchestrator actually calls: ``execute`` and
``resume``. The runner picks ``resume`` off a persisted ``RESUMING`` marker after
an answer is submitted, so a real adapter that diverged from the fake on the
resume path would break pause/resume in Phase 7 -- pinning ``resume`` here by
construction is what stops that. The empty-question guard is pinned too: no
adapter may hand the orchestrator a ``NEEDS_INPUT`` result it cannot act on.
"""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

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


def _paused_previous() -> WorkerResult:
    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a decision",
        questions=["which cluster?"],
    )


def test_resume_returns_a_worker_result(worker: CodingWorker) -> None:
    result = worker.resume(None, _paused_previous(), "the primary cluster")
    assert isinstance(result, WorkerResult)
    assert isinstance(result.status, WorkerResultStatus)


def test_resume_accepts_a_null_answer(worker: CodingWorker) -> None:
    # a resume triggered by something other than a human answer is a shape a
    # later phase will use, so the contract must allow answer=None.
    result = worker.resume(None, _paused_previous(), None)
    assert isinstance(result, WorkerResult)


def test_a_needs_input_result_with_no_questions_cannot_be_constructed() -> None:
    # the boundary model rejects it at construction; pinning it here stops any
    # present or future adapter from inventing a pause with nothing to ask.
    with pytest.raises(ValidationError):
        WorkerResult(status=WorkerResultStatus.NEEDS_INPUT, questions=[])
