"""Unit coverage for ``ToolRegistry`` -- the TOOL-01/TOOL-03 grant/deny
matrix against the shipped ``.dark-factory/roles/*.yaml``, the edge-probe
criteria (TOOL-02 adjacency/empty/ordering), the ``<assumption_delta_decision>``
invariant (one enforcement point, no raw-implementation accessor, deny
precedes dispatch), and the D-04 capability-set scope (Phase 6, plan 06-01).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dark_factory.config.loader import load_effective_config
from dark_factory.tools import CapabilityDeniedError, ToolError, UnknownCapabilityError
from dark_factory.tools.registry import ToolRegistry, default_registry

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _shipped_role_tools() -> dict[str, list[str]]:
    """The shipped per-role ``tools:`` grants, resolved through
    ``load_effective_config`` against the real repo root -- driven from the
    actual config, not a hard-coded copy of it, so this module cannot drift
    from what the shipped role YAMLs say."""
    snapshot = load_effective_config(_REPO_ROOT)
    return {role["name"]: list(role["tools"]) for role in snapshot["roles"]}


# --------------------------------------------------------------------------- #
# TOOL-01 / TOOL-03 -- ROADMAP SC1's grant/deny matrix, verbatim
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("role", "capability", "expected_granted"),
    [
        ("BA", "repo.write", False),
        ("BA", "repo.write_tests", False),
        ("ARCHITECTURE", "repo.write", False),
        ("ARCHITECTURE", "repo.write_tests", False),
        ("DEVELOPMENT", "repo.write", True),
        ("DEVELOPMENT", "shell.execute", True),
        ("QA", "repo.write_tests", True),
        ("QA", "shell.execute", True),
        ("QA", "repo.write", False),
    ],
)
def test_sc1_grant_matrix_against_the_shipped_role_yamls(
    role: str, capability: str, expected_granted: bool
) -> None:
    """BA and ARCHITECTURE are denied ``repo.write``/``repo.write_tests``;
    DEVELOPMENT is granted ``repo.write``/``shell.execute``; QA is granted
    ``repo.write_tests``/``shell.execute`` and denied ``repo.write`` -- the
    "can write tests and shell but cannot publish" half of SC1 (D-16)."""
    granted = _shipped_role_tools()[role]
    assert (capability in granted) is expected_granted
    if not expected_granted:
        with pytest.raises(CapabilityDeniedError) as excinfo:
            default_registry.invoke(role, capability, granted)
        assert excinfo.value.capability == capability
        assert excinfo.value.role == role


def test_a_granted_capability_reaches_a_registered_implementation() -> None:
    """The positive counterpart to the matrix above: when a capability IS
    granted, ``invoke`` reaches the registered implementation and returns
    its value, proven against a fresh registry (not ``default_registry``,
    whose real bodies take their own specific keyword arguments)."""
    registry = ToolRegistry()
    calls: list[dict[str, Any]] = []

    def _impl(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        return "ok"

    registry.register("custom.capability", _impl)
    result = registry.invoke("BA", "custom.capability", ["custom.capability"], x=1)
    assert result == "ok"
    assert calls == [{"x": 1}]


# --------------------------------------------------------------------------- #
# TOOL-02 edge-probe criteria
# --------------------------------------------------------------------------- #


def test_reregistering_a_capability_replaces_the_earlier_implementation() -> None:
    """Re-registering an already-registered name replaces the earlier
    implementation rather than keeping both -- a plain dict, never a second
    implementation for one name (TOOL-02, edge: adjacency)."""
    registry = ToolRegistry()
    registry.register("dup", lambda: "first")
    registry.register("dup", lambda: "second")
    assert registry.invoke("BA", "dup", ["dup"]) == "second"


def test_empty_granted_list_denies_every_registered_capability() -> None:
    """``invoke`` called with an empty ``granted`` list denies every
    registered capability, including a real one (TOOL-02, edge: empty)."""
    for capability in default_registry.names():
        with pytest.raises(CapabilityDeniedError):
            default_registry.invoke("BA", capability, [])


def test_granted_but_unregistered_capability_raises_unknown_capability_error() -> None:
    """A granted-but-unregistered name raises ``UnknownCapabilityError``, not
    ``CapabilityDeniedError`` and not a bare ``KeyError`` -- a configuration
    bug, never an authorization decision (TOOL-02, edge: unclassified
    corner)."""
    registry = ToolRegistry()
    with pytest.raises(UnknownCapabilityError) as excinfo:
        registry.invoke("BA", "not.registered", ["not.registered"])
    assert type(excinfo.value) is UnknownCapabilityError
    assert not isinstance(excinfo.value, CapabilityDeniedError)


def test_grant_list_order_and_duplicates_do_not_change_the_outcome() -> None:
    """The position of a name inside ``granted`` never affects ``invoke`` --
    the check is set membership, never ordering -- and a duplicate entry
    behaves identically to one containing it once (TOOL-02, edge:
    ordering)."""
    registry = ToolRegistry()
    registry.register("dup.cap", lambda: "ok")
    assert registry.invoke("BA", "dup.cap", ["x", "dup.cap", "y"]) == "ok"
    assert registry.invoke("BA", "dup.cap", ["dup.cap", "dup.cap"]) == "ok"


def test_a_grant_never_implies_an_adjacent_capability_name() -> None:
    """Capability names are exact, flat keys with no hierarchy: a role
    granted ``repo.write_tests`` is denied ``repo.write``, and a grant of
    ``repo.read`` never implies ``repo.search`` -- no prefix matching, no
    wildcard (TOOL-03, edge: adjacency)."""
    with pytest.raises(CapabilityDeniedError):
        default_registry.invoke("QA", "repo.write", ["repo.write_tests"])
    with pytest.raises(CapabilityDeniedError):
        default_registry.invoke("BA", "repo.search", ["repo.read"])


def test_a_role_definition_with_no_tools_key_grants_nothing() -> None:
    """A role whose persisted snapshot entry carries no ``tools`` key at all
    (the legacy Phase 1/2 bare-string snapshot shape) is treated as granting
    nothing -- mirrors ``orchestrator/runner.py``'s own
    ``role_def.get("tools", [])`` read (TOOL-03, edge: empty)."""
    role_def: dict[str, object] = {"name": "BA"}
    granted = list(role_def.get("tools", []))
    assert granted == []
    with pytest.raises(CapabilityDeniedError):
        default_registry.invoke("BA", "artifacts.read", granted)


# --------------------------------------------------------------------------- #
# <assumption_delta_decision> invariant: one enforcement point, N callers
# --------------------------------------------------------------------------- #


def test_deny_check_runs_before_dispatch_never_reaching_the_implementation() -> None:
    """The deny check precedes the implementation lookup: a denied
    invocation never reaches a registered implementation, proven by a
    call-recording stub that records nothing after a denial."""
    registry = ToolRegistry()
    calls: list[dict[str, object]] = []

    def _impl(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    registry.register("guarded", _impl)
    with pytest.raises(CapabilityDeniedError):
        registry.invoke("BA", "guarded", [])
    assert calls == []


def test_registry_exposes_no_accessor_returning_a_raw_implementation() -> None:
    """``ToolRegistry`` exposes no public method returning a registered
    implementation callable -- ``invoke`` is the only way to reach one, so
    "one enforcement point" is structural, not a convention a caller could
    route around."""
    public_names = {name for name in dir(ToolRegistry) if not name.startswith("_")}
    assert public_names == {"invoke", "names", "register"}


def test_capability_denied_and_unknown_capability_are_tool_errors() -> None:
    assert issubclass(CapabilityDeniedError, ToolError)
    assert issubclass(UnknownCapabilityError, ToolError)


# --------------------------------------------------------------------------- #
# D-04 -- exactly the shipped capability set, no git.*/github.*
# --------------------------------------------------------------------------- #


def test_default_registry_contains_exactly_the_seven_shipped_capabilities() -> None:
    assert default_registry.names() == {
        "repo.read",
        "repo.search",
        "repo.write",
        "repo.write_tests",
        "shell.execute",
        "artifacts.read",
        "artifacts.write",
    }


def test_default_registry_has_no_git_or_github_prefixed_capability() -> None:
    names = default_registry.names()
    assert not any(name.startswith("git.") for name in names)
    assert not any(name.startswith("github.") for name in names)
