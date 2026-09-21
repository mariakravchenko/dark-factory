"""The D-02 completeness and inertness guard for
``dark_factory.tools.native.NATIVE_TOOL_CONTRACT`` (Phase 6, plan 06-01,
Task 3).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dark_factory.tools.native import (
    NATIVE_TOOL_CONTRACT,
    WORKTREE_CONFINEMENT_NOTE,
    NativeToolGrant,
)
from dark_factory.tools.registry import default_registry

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ALLOWED_CONSUMERS = {
    _SRC_ROOT / "tools" / "native.py",
    _SRC_ROOT / "tools" / "__init__.py",
    # Phase 7 (plan 07-04), 06-CONTEXT.md D-02: the contract table was always
    # meant to be implemented *from* -- dark_factory.workers.claude_code is
    # the first real adapter to do so (see that module's docstring for the
    # import). A new consumer must be added here deliberately, never
    # silently -- that is the whole point of this allowlist.
    _SRC_ROOT / "workers" / "claude_code.py",
    # Plan 08-01: dark_factory.workers.copilot is this contract's second
    # real runtime consumer, mirroring what 07-04 did for claude_code.py.
    _SRC_ROOT / "workers" / "copilot.py",
    # Plan 08-02: dark_factory.workers.hermes is this contract's third real
    # runtime consumer, and the first to also read past the .hermes field --
    # spawn_is_permitted() derives from the whole contract's capability set.
    _SRC_ROOT / "workers" / "hermes.py",
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


def _references_in_source(source: str, *, filename: str) -> list[str]:
    """Every AST reference to ``NATIVE_TOOL_CONTRACT`` in ``source`` -- an
    attribute access, an import, a bare name -- labelled with ``filename``.

    Pure (no filesystem coupling of its own): given raw source text and a
    label, this is the whole detection mechanism
    :func:`_modules_referencing_contract` applies to real files on disk.
    Factored out so a sanity test can prove the walk itself catches a
    reference, independent of what currently happens to be on disk or in
    ``_ALLOWED_CONSUMERS``.
    """
    offenders: list[str] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "NATIVE_TOOL_CONTRACT":
            offenders.append(f"{filename}:{node.lineno}")
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "dark_factory.tools.native"
            and any(alias.name == "NATIVE_TOOL_CONTRACT" for alias in node.names)
        ):
            offenders.append(f"{filename}:{node.lineno}")
    return offenders


def _modules_referencing_contract() -> list[str]:
    """AST-guard style (mirrors ``test_no_role_name_literal.py``): walk every
    module under ``src/dark_factory/`` outside ``_ALLOWED_CONSUMERS`` and
    record which ones reference the ``NATIVE_TOOL_CONTRACT`` name."""
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in _ALLOWED_CONSUMERS:
            continue
        offenders.extend(
            _references_in_source(
                path.read_text(encoding="utf-8"),
                filename=str(path.relative_to(_SRC_ROOT)),
            )
        )
    return offenders


def test_contract_is_referenced_only_by_its_declared_consumers() -> None:
    offenders = _modules_referencing_contract()
    assert not offenders, (
        "NATIVE_TOOL_CONTRACT gained an undeclared consumer -- if this is "
        "intentional, add the module to _ALLOWED_CONSUMERS on purpose:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_detects_a_reference_outside_the_allowed_set() -> None:
    """A guard that cannot detect its own subject proves nothing (see
    ``tests/unit/test_git_ownership_boundary.py``'s docstring for the same
    principle). Feeds the offender-collection helper source that imports
    ``NATIVE_TOOL_CONTRACT`` under a synthetic module path outside
    ``_ALLOWED_CONSUMERS``, proving the AST walk itself -- not just today's
    absence of offenders -- would catch a real one."""
    synthetic_path = _SRC_ROOT / "orchestrator" / "not_a_real_consumer.py"
    assert synthetic_path not in _ALLOWED_CONSUMERS

    offenders = _references_in_source(
        "from dark_factory.tools.native import NATIVE_TOOL_CONTRACT\n",
        filename=str(synthetic_path.relative_to(_SRC_ROOT)),
    )

    assert offenders


def test_every_claude_code_entry_names_the_real_worktree_mechanism() -> None:
    """The corrected prose (Task 2) cannot silently regress back to
    attributing directory scoping to a nonexistent approval-policy flag."""
    for grant in NATIVE_TOOL_CONTRACT.values():
        assert WORKTREE_CONFINEMENT_NOTE in grant.claude_code
