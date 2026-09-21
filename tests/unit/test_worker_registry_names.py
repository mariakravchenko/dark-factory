"""Unit coverage for WorkerRegistry membership + the placeholder worker names
(Plan 03-01 Task 2, WORK-02; ``claude-code`` updated by Plans 07-01/07-03;
``copilot`` updated by Plan 08-01).

Membership must work without constructing a worker. ``hermes`` invocations
still raise ``NotImplementedError`` naming the phase its real adapter lands
in (Phase 8, plan 08-02). ``claude-code`` is no longer a placeholder as of
Plan 07-01 -- it resolves to a real :class:`~dark_factory.workers.
claude_code.ClaudeCodeWorker` whose ``execute()`` and (as of Plan 07-03)
``resume()`` both never raise (see ``tests/unit/test_claude_code_worker.py``
for the full behavior suite). ``copilot`` is no longer a placeholder as of
Plan 08-01 -- it resolves to a real :class:`~dark_factory.workers.
copilot.CopilotWorker`, same shape (see ``tests/unit/test_copilot_worker.py``
for the full behavior suite).
"""

import pytest

from dark_factory.workers.registry import UnknownWorkerError, default_registry

pytestmark = pytest.mark.unit


def test_all_placeholder_names_plus_fake_are_members() -> None:
    for name in ("claude-code", "copilot", "hermes", "fake"):
        assert name in default_registry


def test_an_unregistered_name_is_not_a_member() -> None:
    assert "bogus" not in default_registry


def test_get_on_an_unregistered_name_raises_unknown_worker_error() -> None:
    with pytest.raises(UnknownWorkerError):
        default_registry.get("bogus")


def test_claude_code_resolves_to_a_real_adapter_not_a_placeholder() -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    worker = default_registry.get("claude-code")
    assert isinstance(worker, ClaudeCodeWorker)

    # execute() never raises (WORK-04) -- with no ANTHROPIC_API_KEY configured
    # in this test's environment, the credential gate returns FAILED, not an
    # exception. See test_claude_code_worker.py for the full behavior suite.
    result = worker.execute({})
    assert result.status is WorkerResultStatus.FAILED

    # resume() is fully implemented as of Plan 07-03 -- it never raises, even
    # given this test's deliberately bare `None` previous result and no
    # ANTHROPIC_API_KEY configured (see test_claude_code_worker.py for the
    # full resume() behavior suite).
    resume_result = worker.resume({}, None, None)  # type: ignore[arg-type]
    assert resume_result.status is WorkerResultStatus.FAILED

    # capabilities() is implemented (not a placeholder); does not raise.
    assert worker.capabilities().non_interactive is True


def test_copilot_resolves_to_a_real_adapter_not_a_placeholder() -> None:
    from dark_factory.domain.worker import WorkerResultStatus
    from dark_factory.workers.copilot import CopilotWorker

    worker = default_registry.get("copilot")
    assert isinstance(worker, CopilotWorker)

    # execute() never raises (WORK-05) -- with no COPILOT_GITHUB_TOKEN
    # configured in this test's environment, the credential gate returns
    # FAILED, not an exception. See test_copilot_worker.py for the full
    # behavior suite.
    result = worker.execute({})
    assert result.status is WorkerResultStatus.FAILED

    # resume() never raises either, given this test's deliberately bare
    # `None` previous result and no COPILOT_GITHUB_TOKEN configured.
    resume_result = worker.resume({}, None, None)  # type: ignore[arg-type]
    assert resume_result.status is WorkerResultStatus.FAILED

    # capabilities() is implemented (not a placeholder); does not raise.
    assert worker.capabilities().non_interactive is True


@pytest.mark.parametrize("name", ["hermes"])
def test_phase_8_placeholders_resolve_but_every_entry_point_names_phase_8(
    name: str,
) -> None:
    worker = default_registry.get(name)  # construction must not raise
    with pytest.raises(NotImplementedError, match="Phase 8"):
        worker.execute({})
    with pytest.raises(NotImplementedError, match="Phase 8"):
        worker.resume({}, None, None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="Phase 8"):
        worker.capabilities()
