"""Unit coverage for WorkerRegistry membership + the three placeholder worker
names (Plan 03-01 Task 2, WORK-02).

Membership must work without constructing a worker; a placeholder invocation must
raise ``NotImplementedError`` naming the phase its real adapter lands in.
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


def test_claude_code_placeholder_resolves_but_every_entry_point_names_phase_7() -> None:
    worker = default_registry.get("claude-code")  # construction must not raise
    with pytest.raises(NotImplementedError, match="Phase 7"):
        worker.execute({})
    with pytest.raises(NotImplementedError, match="Phase 7"):
        worker.resume({}, None, None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="Phase 7"):
        worker.capabilities()


@pytest.mark.parametrize("name", ["copilot", "hermes"])
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
