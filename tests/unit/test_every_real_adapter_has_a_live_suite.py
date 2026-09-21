"""QUAL-03 completeness guard: every real worker registered in
``default_registry`` -- every name except ``fake``, the in-process test
worker with no binary and no credential -- must have its own non-empty,
skip-guarded live integration module (Plan 08-03, Task 2).

Enumerates from ``default_registry`` directly (never a hand-maintained
list), so a fourth real adapter registered later and left without a live
suite fails this test rather than silently shipping uncovered
(08-03-PLAN.md key_links).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dark_factory.workers.hermes import spawn_is_permitted
from dark_factory.workers.registry import default_registry
from tests.integration.test_hermes_live import HERMES_LIVE_SPIKE_TOOLS
from tests.support.live_runtime import LIVE_RUNTIMES

pytestmark = pytest.mark.unit

_INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "integration"

# The in-process test worker: no binary, no credential, no live suite to
# have -- the sole registered name this guard does not require a module for.
_EXEMPT_WORKER_NAMES: frozenset[str] = frozenset({"fake"})


def _expected_live_module_name(worker_name: str) -> str:
    """Derive ``test_<module>_live.py`` from a worker name by a single
    documented transformation -- hyphens become underscores -- so adding a
    fourth adapter needs no edit to this function or this test file."""
    return f"test_{worker_name.replace('-', '_')}_live.py"


def _missing_live_suites(worker_names: frozenset[str]) -> set[str]:
    """The pure checking helper: every name in ``worker_names`` (minus the
    exempt set) with no corresponding non-empty live module file.

    A plain function, not a fixture or an inline assertion, so
    ``test_the_guard_detects_a_reference_outside_the_allowed_set`` below can
    drive it directly against a synthetic name -- the same "prove the guard
    detects its own subject" pattern
    ``test_native_tool_contract.py::test_the_guard_detects_a_reference_outside_the_allowed_set``
    already applies.
    """
    missing: set[str] = set()
    for name in worker_names - _EXEMPT_WORKER_NAMES:
        module_path = _INTEGRATION_DIR / _expected_live_module_name(name)
        if not module_path.is_file() or module_path.stat().st_size == 0:
            missing.add(name)
    return missing


def test_every_real_adapter_has_a_live_suite() -> None:
    """Enumerates every registered worker name except ``fake`` directly from
    ``default_registry`` and asserts each has a non-empty live integration
    module -- the QUAL-03 obligation, checked mechanically rather than by
    inspection."""
    registered = default_registry.names()
    missing = _missing_live_suites(registered)
    assert not missing, (
        "the following registered worker(s) have no live integration "
        f"module under tests/integration/: {sorted(missing)}"
    )


def test_enumerated_worker_names_equal_registry_minus_fake() -> None:
    """Pins the concrete expectation directly, so a change to
    ``default_registry``'s registered names is visible here as a failing
    assertion rather than only as a silent change in what
    ``_missing_live_suites`` iterates over."""
    assert default_registry.names() - _EXEMPT_WORKER_NAMES == {
        "claude-code",
        "copilot",
        "hermes",
    }


def test_every_registered_worker_also_has_a_live_runtimes_entry() -> None:
    """``tests/support/live_runtime.py``'s ``LIVE_RUNTIMES`` mapping must
    cover the identical name set this guard enumerates, so the skip
    condition and the completeness guard cannot drift against each other."""
    registered = default_registry.names() - _EXEMPT_WORKER_NAMES
    assert set(LIVE_RUNTIMES) == registered


def test_the_guard_detects_a_reference_outside_the_allowed_set() -> None:
    """A guard that cannot fail on a real omission proves nothing -- feeds
    the pure checking helper a synthetic worker name with no module and
    asserts it is reported as missing, mirroring
    ``test_native_tool_contract.py``'s identical self-detection pattern."""
    synthetic_name = "a-synthetic-worker-nobody-registered"
    missing = _missing_live_suites(frozenset({synthetic_name}))
    assert missing == {synthetic_name}


def test_the_hermes_live_spike_grant_list_satisfies_spawn_admission() -> None:
    """Runs unconditionally -- this module carries no ``integration`` mark
    and no ``skipif`` guard -- so this holds even in an environment where
    ``tests/integration/test_hermes_live.py``'s own execution test is
    skipped: a wrong grant list must surface as a genuine unit-test
    failure, never hidden behind a skip."""
    assert spawn_is_permitted(HERMES_LIVE_SPIKE_TOOLS) is None
