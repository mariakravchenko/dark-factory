"""The shared CodingWorker contract suite.

Parametrized over ``WORKER_FACTORIES``. Phase 7 (Plan 07-03) has appended
``ClaudeCodeWorker`` to that list, so this suite now runs a real
subprocess-spawning adapter -- driven against a faked ``claude`` executable on
``PATH`` (see the ``_fake_claude_cli_on_path`` autouse fixture below), never a
live binary or a live Anthropic credential -- alongside ``FakeWorker``. Phase 8
will append ``CopilotWorker`` and ``HermesWorker``. This suite is the mechanism
that stops the fake drifting from real adapter semantics, so every downstream
orchestration test keeps testing a faithful worker rather than a divergent
stub.

It covers **both** methods the orchestrator actually calls: ``execute`` and
``resume``. The runner picks ``resume`` off a persisted ``RESUMING`` marker after
an answer is submitted, so a real adapter that diverged from the fake on the
resume path would break pause/resume in Phase 7 -- pinning ``resume`` here by
construction is what stops that. The empty-question guard is pinned too: no
adapter may hand the orchestrator a ``NEEDS_INPUT`` result it cannot act on.

The sharpest thing this suite now proves for free: ``_paused_previous()``
supplies no ``worker_session_id``, so a ``native_resume=True`` adapter
(``ClaudeCodeWorker``) is driven down its context-reconstruction branch here --
HITL-05's "the orchestrator sees the same call either way" is pinned by
construction rather than by a bespoke test.
"""

from collections.abc import Callable, Iterator

import pytest
from pydantic import ValidationError

from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.claude_code import ClaudeCodeWorker
from dark_factory.workers.fake import FakeWorker
from tests.support.fake_claude_cli import fake_claude_env, write_fake_claude

pytestmark = pytest.mark.contract

WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker, ClaudeCodeWorker]

# A clean COMPLETED payload -- no NEEDS_INPUT marker -- so the fake CLI does
# not force every ClaudeCodeWorker call in this module down the pause branch;
# individual tests below still drive NEEDS_INPUT explicitly via
# `_paused_previous()`, which is constructed in-process and never touches the
# CLI at all.
_FAKE_CLI_PAYLOAD = """{"subtype": "success", "duration_ms": 1, "duration_api_ms": 1, \
"is_error": false, "num_turns": 1, "session_id": "sess-contract-fake", \
"total_cost_usd": 0.0, "usage": {}, \
"result": "contract-suite fake CLI result, no marker here", \
"structured_output": null, "permission_denials": []}"""


@pytest.fixture(autouse=True)
def _fake_claude_cli_on_path(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Install a fake ``claude`` executable on ``PATH`` plus obviously-fake
    credentials before any parametrized worker in this module is
    constructed, so a ``ClaudeCodeWorker.execute()``/``resume()`` call here
    spawns the fake -- never a real ``claude`` binary -- and needs no live
    ``ANTHROPIC_API_KEY`` (Task 3, QUAL-02).

    Environment variables take precedence over ``.env`` in
    pydantic-settings, so this fixture behaves identically on a developer
    machine with a populated ``.env`` and on a CI runner with none -- which
    is exactly why it sets the database URLs too, rather than relying on
    ``.env`` being present.
    """
    fake_dir = tmp_path_factory.mktemp("fake-claude-bin")
    write_fake_claude(fake_dir, stdout_payload=_FAKE_CLI_PAYLOAD)
    with fake_claude_env(monkeypatch, fake_dir):
        yield


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
