"""Gaps G-09-6 and G-09-7 (09-UAT.md): ``tests/db/test_feedback_reaches_developer.py``'s
``_CapturingWorker._record_and_maybe_rebuild`` rebuilds the Developer's attempt-2
``RoleContext`` to prove D-07's durability guarantee, but was passing the
**config repo root** (``self._repo_root``) where the production runner
(``runner.py:866``) passes the **git worktree** (``work_dir``).
``worktree_path`` places the worktree at ``<repo_root.parent>/dark-factory-runs/<run_id>/``
-- a SIBLING of ``repo_root``, documented as never a descendant of it -- so the
two roots can never coincide. The rebuild therefore resolved artifact reads
against a directory nothing was ever written into, and both LOOP-01 and
LOOP-02 raised ``MissingArtifactContentError`` on ``design.md``, DEVELOPMENT's
first declared input, unconditionally in every environment (see
``.planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md``).

The behavioural proof that the fix actually resolves artifacts correctly is
db-tier and requires a reachable PostgreSQL 17, which this sandbox does not
have (recorded under Manual-Only Verification in ``09-06-PLAN.md``). This
module is the DB-free structural guard that restores a fast, always-runnable
detection signal: it fails the moment the rebuild's context root is ever again
something other than the value ``ensure_worktree`` returned, so an
unconditionally-red db-tier test cannot again go unnoticed for a whole phase.

Mirrors ``tests/unit/test_write_scope_guard_covers_bounce.py``'s AST-walking
idiom.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SUBJECT_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "db"
    / "test_feedback_reaches_developer.py"
)

_REBUILD_FUNC_NAME = "_record_and_maybe_rebuild"


def _parse_subject() -> ast.Module:
    return ast.parse(
        _SUBJECT_PATH.read_text(encoding="utf-8"), filename=str(_SUBJECT_PATH)
    )


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    """Every ``ast.Call`` in ``tree`` whose callee unparses to ``name``."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == name
    ]


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no function named {name!r} found in {_SUBJECT_PATH}")


def _ensure_worktree_bound_name(func: ast.FunctionDef) -> str:
    """The single local name assigned from the ``ensure_worktree`` call inside
    ``func`` -- raises an ``AssertionError`` naming ``func`` if there is not
    exactly one such call, so a future refactor produces a diagnosis rather
    than an opaque ``IndexError``."""
    calls = _calls_named(func, "ensure_worktree")
    if len(calls) != 1:
        raise AssertionError(
            f"expected exactly one ensure_worktree call inside {func.name!r}, "
            f"found {len(calls)}"
        )
    call = calls[0]
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and node.value is call
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            return node.targets[0].id
    raise AssertionError(
        f"the ensure_worktree call inside {func.name!r} is not the direct "
        "value of a single-target assignment, so no local name could be "
        "determined"
    )


def test_the_rebuild_derives_the_worktree_with_ensure_worktree() -> None:
    """``_record_and_maybe_rebuild`` must call ``ensure_worktree`` itself,
    deriving the run's worktree exactly as a fresh process (``_advance_once``,
    runner.py:854) does -- not read a path computed out of band. Absent, this
    is G-09-6/G-09-7's root cause: the rebuild resolves artifacts against the
    config repo root, which ``worktree_path`` places as a SIBLING of the
    worktree, never the same directory -- so every declared input read raises
    ``MissingArtifactContentError`` for whichever input is declared first."""
    tree = _parse_subject()
    func = _find_function(tree, _REBUILD_FUNC_NAME)
    calls = _calls_named(func, "ensure_worktree")
    assert calls, (
        f"{_REBUILD_FUNC_NAME} must call ensure_worktree to derive the run's "
        "worktree from the freshly loaded RunState -- see "
        ".planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md"
    )


def test_the_rebuild_never_resolves_the_context_against_the_stored_root() -> None:
    """The single ``build_role_context`` call in this module must pass the
    ``ensure_worktree``-derived local as its root argument, never
    ``self._repo_root`` -- the worktree is a sibling of the repo root
    (``worktree_path``), so passing the stored root resolves artifact reads
    against a directory nothing was ever written into (G-09-6, G-09-7)."""
    tree = _parse_subject()
    func = _find_function(tree, _REBUILD_FUNC_NAME)
    worktree_local = _ensure_worktree_bound_name(func)
    build_calls = _calls_named(func, "build_role_context")
    assert len(build_calls) == 1, (
        "expected exactly one build_role_context call inside "
        f"{_REBUILD_FUNC_NAME!r}, found {len(build_calls)}"
    )
    root_arg_source = ast.unparse(build_calls[0].args[1])
    assert root_arg_source != "self._repo_root", (
        "build_role_context's root argument is 'self._repo_root' -- the "
        "config repo root, which worktree_path places as a SIBLING of the "
        "run's worktree, never the same directory. This reproduces "
        "G-09-6/G-09-7's MissingArtifactContentError: whichever declared "
        "input is first (design.md, for DEVELOPMENT) is read from a "
        "directory nothing was ever written into."
    )
    assert root_arg_source == worktree_local, (
        f"build_role_context's root argument is {root_arg_source!r}, but the "
        f"ensure_worktree-derived local is {worktree_local!r} -- the rebuild "
        "must resolve its context against the worktree, exactly as "
        "_advance_once (runner.py:866) does."
    )


def test_exactly_one_build_role_context_call_site_in_the_module() -> None:
    """Guard-on-the-guard: exactly one ``build_role_context`` call exists in
    the whole module, so the two tests above cannot silently pass by matching
    nothing, or drift onto a different call site if the module later grows a
    second one."""
    tree = _parse_subject()
    calls = _calls_named(tree, "build_role_context")
    assert len(calls) == 1, (
        f"expected exactly one build_role_context call in "
        f"{_SUBJECT_PATH.name}, found {len(calls)} -- update this guard "
        "deliberately if the module now legitimately has more than one call "
        "site"
    )
