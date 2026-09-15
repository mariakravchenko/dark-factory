"""GIT-02: ``src/dark_factory/git/client.py`` is the sole module under
``src/dark_factory/`` that invokes the ``git`` binary, and no worker module
imports the ``dark_factory.git`` package.

Mirrors ``tests/unit/test_single_mutation_path.py``'s AST-walk technique
exactly: a module-level ``_ALLOWED`` set, a ``_modules()`` generator skipping
it, a ``_violations(path)`` function returning ``"file:line reason"`` strings
so a failure names the offending file and line, and a sanity test proving the
guard would trip on the allowed module -- a guard that cannot detect its own
subject proves nothing.

A violation is any ``ast.Call`` whose first positional argument is a list or
tuple display whose first element is the string constant ``"git"``, or any
``ast.Call`` to an ``ast.Attribute`` named ``run``/``Popen``/``check_output``/
``call`` on a name bound to the standard ``subprocess`` module where that same
call's arguments mention the string ``"git"``. Because the AST walk inspects
only executable call expressions -- never string literals inside a docstring
or a comment -- a module that merely *documents* a git command does not trip
it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ALLOWED = {_SRC_ROOT / "git" / "client.py"}

# actions/ is exempt from the "no import of dark_factory.git" half of this
# guard: plans 05-02 (ensure_clean_worktree) and 05-04 (collect_diff) make
# these two built-ins thin dispatchers into dark_factory.git -- they perform
# only git-level work and never open a Session (WR-01), which is the
# invariant test_single_mutation_path.py polices instead. Stating the
# exemption as data here, rather than leaving the test to be silently
# weakened when those plans land, is what keeps this guard meaningful.
_IMPORT_EXEMPT = {_SRC_ROOT / "actions"}

_SUBPROCESS_INVOCATION_ATTRS = {"run", "Popen", "check_output", "call"}


def _modules() -> Iterator[Path]:
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in _ALLOWED:
            continue
        yield path


def _first_string_element(node: ast.expr) -> str | None:
    """If ``node`` is a list/tuple display whose first element is a string
    constant, return that string; otherwise ``None``."""
    if isinstance(node, ast.List | ast.Tuple) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _call_mentions_git(call: ast.Call) -> bool:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and arg.value == "git":
            return True
        collected = _first_string_element(arg)
        if collected == "git":
            return True
        if isinstance(arg, ast.List | ast.Tuple):
            for elt in arg.elts:
                if isinstance(elt, ast.Constant) and elt.value == "git":
                    return True
    return False


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(_SRC_ROOT)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        first_arg_git = (
            _first_string_element(node.args[0]) == "git" if node.args else False
        )
        if first_arg_git:
            out.append(f"{rel}:{node.lineno} invokes git via a git-first argument list")
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _SUBPROCESS_INVOCATION_ATTRS
            and _call_mentions_git(node)
        ):
            out.append(
                f"{rel}:{node.lineno} calls subprocess.{node.func.attr}(...) naming 'git'"
            )
    return out


def _import_violations(path: Path) -> list[str]:
    if any(path.is_relative_to(exempt) for exempt in _IMPORT_EXEMPT):
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(_SRC_ROOT)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dark_factory.git" or alias.name.startswith(
                    "dark_factory.git."
                ):
                    out.append(f"{rel}:{node.lineno} imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "dark_factory.git" or module.startswith("dark_factory.git."):
                out.append(f"{rel}:{node.lineno} imports from {module}")
    return out


def test_git_client_is_the_sole_git_invoker() -> None:
    offenders: list[str] = []
    for path in _modules():
        offenders.extend(_violations(path))
    assert not offenders, (
        "git-binary invocations found outside src/dark_factory/git/client.py:\n  "
        + "\n  ".join(offenders)
    )


def test_git_client_itself_would_trip_the_walk() -> None:
    # Sanity: the guard is meaningful only if the allowed module actually
    # invokes git.
    (client_path,) = _ALLOWED
    assert _violations(client_path)


def test_no_worker_module_imports_the_git_package() -> None:
    workers_root = _SRC_ROOT / "workers"
    offenders: list[str] = []
    for path in sorted(workers_root.rglob("*.py")):
        offenders.extend(_import_violations(path))
    assert not offenders, (
        "dark_factory.git imported from src/dark_factory/workers/:\n  "
        + "\n  ".join(offenders)
    )
