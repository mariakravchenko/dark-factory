"""TRIG-01: there is one orchestration implementation; CLI and CI are only
triggers, and a trigger carries zero lifecycle logic.

ROADMAP.md's Phase 11 invariant, quoted verbatim: "triggers carry zero
lifecycle logic; the run's working state is re-materialized from Neon plus
git on any machine."

This guard walks the AST, never raw source text: several modules in this
tree mention ``advance()`` in prose only -- ``persistence/engine.py``,
``persistence/repositories.py``, ``domain/status.py``, and three
``workers/*.py`` modules -- and must not trip it. A docstring or comment is
never an ``ast.FunctionDef``, ``ast.Call`` or ``ast.Import``/``ast.ImportFrom``
node, so this walk is structurally blind to prose regardless of wording.

**Deviation, documented (11-03-SUMMARY.md).** The plan authoring this test
stated ``_PERMITTED_CALL_SITES`` should contain two entries,
``{"orchestrator/runner.py", "cli.py"}``, reasoning that "``runner.py``
[belongs] because ``drive`` calls ``advance`` internally." Read against the
actual source tree before writing this guard (``src/dark_factory/orchestrator/runner.py``,
``def advance`` and ``def drive``): that reasoning does not hold. ``advance``
and ``drive`` are *siblings* -- each independently calls the private
``_advance_once`` helper; neither calls the other. ``advance`` (a public
function, exported for tests and any future single-step trigger) has **zero**
call sites anywhere in ``src/dark_factory/`` today; the only real call site
for either name is ``cli.py``'s ``run``/``resume`` commands calling ``drive``.
``_PERMITTED_CALL_SITES`` below is therefore the one-entry set the tree
actually contains, not the plan's stated-but-unverified two-entry set. The
anti-vacuity check for the call-site test asserts only that the *aggregate*
collected call list is non-empty (``drive``'s one real call site) -- not that
both names individually have a call site, since ``advance`` legitimately has
none today. A rename of either name, or a genuinely new call site appearing
anywhere else, still trips the guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"

_LIFECYCLE_ENTRY_POINTS = frozenset({"advance", "drive"})
"""TRIG-01's orchestrator entry points -- the only two names a trigger may
ever reach for. ``advance(run_id)`` runs exactly one committed step;
``drive`` loops it to a stop status. Neither name may be (re)defined a
second time anywhere in ``src/dark_factory/``, and any *call* to either name
outside the named trigger allowlist below (:data:`_PERMITTED_CALL_SITES`) is
a second orchestration implementation by definition."""

_PERMITTED_CALL_SITES = frozenset({"cli.py"})
"""TRIG-01's call-site allowlist, read from the actual source tree rather
than assumed: ``cli.py`` is the one trigger present in this source tree
today -- its ``run``/``resume`` commands each call ``drive(run_id, ...)``
exactly once. ``advance`` itself has zero call sites anywhere in
``src/dark_factory/`` right now (exported for tests and any future
single-step trigger, but no shipped trigger calls it directly); this
constant tracks that fact and must be updated deliberately -- never
silently -- the day a second trigger legitimately calls either name. The
CI runner is a trigger too, and it reaches ``drive`` through this same
``cli.py`` -- there is no CI-specific module."""


def _relative(path: Path) -> str:
    return str(path.relative_to(_SRC_ROOT))


def _modules() -> list[Path]:
    return sorted(_SRC_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defines(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in _LIFECYCLE_ENTRY_POINTS
    }


def _calls(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _LIFECYCLE_ENTRY_POINTS:
            found.add(func.id)
        elif isinstance(func, ast.Attribute) and func.attr in _LIFECYCLE_ENTRY_POINTS:
            found.add(func.attr)
    return found


def _imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom | ast.Import):
            for alias in node.names:
                if alias.name in _LIFECYCLE_ENTRY_POINTS:
                    found.add(alias.name)
    return found


def test_advance_and_drive_are_defined_in_exactly_one_module() -> None:
    defining_modules: set[str] = set()
    names_found: set[str] = set()
    for path in _modules():
        names = _defines(_parse(path))
        if names:
            defining_modules.add(_relative(path))
            names_found |= names

    # Anti-vacuity: both names must genuinely be found as definitions, or a
    # rename would silently turn this guard into a no-op.
    assert names_found == _LIFECYCLE_ENTRY_POINTS, (
        "expected both 'advance' and 'drive' to be found as top-level "
        f"definitions; found only {sorted(names_found)}"
    )
    assert defining_modules == {"orchestrator/runner.py"}, (
        "advance/drive defined outside orchestrator/runner.py: "
        f"{sorted(defining_modules)}"
    )


def test_only_named_triggers_call_the_lifecycle_entry_points() -> None:
    calling_modules: set[str] = set()
    calls_found: set[str] = set()
    for path in _modules():
        calls = _calls(_parse(path))
        if calls:
            calling_modules.add(_relative(path))
            calls_found |= calls

    # Anti-vacuity: at least one real call site must be found (drive, from
    # cli.py) -- see the module docstring's deviation note for why the
    # aggregate list, not a per-name check, is what must be non-empty.
    assert calls_found, (
        "found zero calls to advance()/drive() anywhere in src/dark_factory/"
    )
    assert calling_modules == _PERMITTED_CALL_SITES, (
        "advance/drive called from outside the named trigger allowlist "
        f"{sorted(_PERMITTED_CALL_SITES)}: {sorted(calling_modules)}"
    )
