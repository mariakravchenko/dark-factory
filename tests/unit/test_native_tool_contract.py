"""The D-02 completeness and inertness guard for
``dark_factory.tools.native.NATIVE_TOOL_CONTRACT`` (Phase 6, plan 06-01,
Task 3).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dark_factory.tools.native import NATIVE_TOOL_CONTRACT, NativeToolGrant
from dark_factory.tools.registry import default_registry

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_OWN_MODULES = {
    _SRC_ROOT / "tools" / "native.py",
    _SRC_ROOT / "tools" / "__init__.py",
}


def test_contract_has_exactly_one_entry_per_registered_capability() -> None:
    """A capability registered on ``default_registry`` with no translation
    entry fails here rather than silently leaving Phase 7 a hole, and there
    are no orphan entries naming a capability nothing registers."""
    assert set(NATIVE_TOOL_CONTRACT) == default_registry.names()


def test_every_entry_is_complete_and_self_keyed() -> None:
    for key, grant in NATIVE_TOOL_CONTRACT.items():
        assert isinstance(grant, NativeToolGrant)
        assert grant.capability == key
        assert grant.claude_code.strip() != ""
        assert grant.copilot.strip() != ""
        assert grant.hermes.strip() != ""
        assert grant.absent_behaviour.strip() != ""


def test_hermes_entries_are_honest_about_having_no_native_mechanism() -> None:
    """CLAUDE.md documents no per-tool native restriction flag for Hermes --
    every entry must say so explicitly rather than inventing one."""
    for grant in NATIVE_TOOL_CONTRACT.values():
        assert "no documented per-tool native restriction flag" in grant.hermes


def test_native_tool_grant_is_frozen_and_extra_forbid() -> None:
    grant = next(iter(NATIVE_TOOL_CONTRACT.values()))
    assert grant.model_config.get("frozen") is True
    assert grant.model_config.get("extra") == "forbid"
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on frozen assign
        grant.capability = "mutated"  # type: ignore[misc]


def _modules_referencing_contract() -> list[str]:
    """AST-guard style (mirrors ``test_no_role_name_literal.py``): walk every
    module under ``src/dark_factory/`` and record which ones reference the
    ``NATIVE_TOOL_CONTRACT`` name, anywhere -- an attribute access, an
    import, a bare name."""
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in _OWN_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "NATIVE_TOOL_CONTRACT":
                offenders.append(f"{path.relative_to(_SRC_ROOT)}:{node.lineno}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "dark_factory.tools.native"
                and any(alias.name == "NATIVE_TOOL_CONTRACT" for alias in node.names)
            ):
                offenders.append(f"{path.relative_to(_SRC_ROOT)}:{node.lineno}")
    return offenders


def test_contract_is_referenced_by_no_module_other_than_its_own(
) -> None:
    offenders = _modules_referencing_contract()
    assert not offenders, (
        "NATIVE_TOOL_CONTRACT is no longer inert -- referenced outside "
        "tools/native.py and tools/__init__.py:\n  " + "\n  ".join(offenders)
    )
