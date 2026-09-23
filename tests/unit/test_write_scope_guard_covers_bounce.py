"""Gap CR-01 (09-VERIFICATION.md, failed truth #22): the ROLE-05 write-scope
guard in ``orchestrator/runner.py`` was written in Phase 5, before
``Signal.ROLE_BOUNCED`` existed, and Phase 9 never widened it -- so a
terminal-role attempt that resolves to ``ROLE_BOUNCED`` skips
``enforce_write_scope`` entirely. Its out-of-scope write survives uncaught
into the next role's WIP-recovery commit, indistinguishable in the audit
trail from that role's own legitimate work.

This is a source-structural regression guard, not a behavioural one: the
behavioural proof (``tests/db/test_write_scope_enforced_on_bounce.py``) is
db-tier and cannot run without a reachable PostgreSQL 17. This test is the
fast, always-runnable sentinel that keeps the ROLE-05 boundary from silently
narrowing again the way it did between Phase 5 and Phase 9.

Mirrors ``tests/unit/test_no_role_name_literal.py``'s AST-walking idiom.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RUNNER_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dark_factory"
    / "orchestrator"
    / "runner.py"
)

_REQUIRED_HANDLER_TARGETS = frozenset(
    {"signal", "outcome", "artifact_writes", "counter_increments", "bounce_reason"}
)


def _handler_catches_write_scope_violation(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    return "WriteScopeViolation" in ast.unparse(handler.type)


def _find_guarding_if_nodes(tree: ast.AST) -> list[ast.If]:
    """Every ``ast.If`` that encloses an ``ast.Try`` with a
    ``WriteScopeViolation`` handler."""
    matches: list[ast.If] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Try) and any(
                _handler_catches_write_scope_violation(h) for h in inner.handlers
            ):
                matches.append(node)
                break
    return matches


def _innermost(nodes: list[ast.If]) -> ast.If:
    return min(nodes, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)


def _write_scope_violation_handler(if_node: ast.If) -> ast.ExceptHandler:
    for inner in ast.walk(if_node):
        if isinstance(inner, ast.Try):
            for handler in inner.handlers:
                if _handler_catches_write_scope_violation(handler):
                    return handler
    raise AssertionError("no WriteScopeViolation handler found inside if_node")


def _assignment_targets(handler: ast.ExceptHandler) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(handler):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    targets.add(target.id)
    return targets


def test_exactly_one_write_scope_guard_call_site() -> None:
    tree = ast.parse(_RUNNER_PATH.read_text(encoding="utf-8"), filename=str(_RUNNER_PATH))
    guarding_ifs = _find_guarding_if_nodes(tree)
    assert len(guarding_ifs) == 1, (
        "expected exactly one enforce_write_scope-guarding if/try pair in "
        f"runner.py, found {len(guarding_ifs)} -- a future edit introducing a "
        "second call site must update this test deliberately, not silently"
    )


def test_guard_covers_both_role_completed_and_role_bounced() -> None:
    tree = ast.parse(_RUNNER_PATH.read_text(encoding="utf-8"), filename=str(_RUNNER_PATH))
    guarding_ifs = _find_guarding_if_nodes(tree)
    assert guarding_ifs, "no enforce_write_scope-guarding if/try pair found"
    if_node = _innermost(guarding_ifs)
    guard_source = ast.unparse(if_node.test)
    assert "ROLE_COMPLETED" in guard_source, guard_source
    assert "ROLE_BOUNCED" in guard_source, guard_source


def test_handler_clears_bounce_side_effects_and_leaves_gate_events_alone() -> None:
    tree = ast.parse(_RUNNER_PATH.read_text(encoding="utf-8"), filename=str(_RUNNER_PATH))
    guarding_ifs = _find_guarding_if_nodes(tree)
    assert guarding_ifs, "no enforce_write_scope-guarding if/try pair found"
    if_node = _innermost(guarding_ifs)
    handler = _write_scope_violation_handler(if_node)
    targets = _assignment_targets(handler)
    missing = _REQUIRED_HANDLER_TARGETS - targets
    assert not missing, (
        f"WriteScopeViolation handler is missing assignments to {sorted(missing)}"
    )
    assert "gate_events" not in targets, (
        "the WriteScopeViolation handler must not clear gate_events -- the "
        "gate's own audit events are already durably committed by the time "
        "this check runs (unlike the GitError branch)"
    )
