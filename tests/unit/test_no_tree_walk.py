"""CTX-02 / CTX-03 mechanical guard: no directory enumeration, no dynamic
execution, anywhere under ``dark_factory.context`` or ``dark_factory.artifacts``.

Implemented as an AST source-tree walk in the register of
``tests/unit/test_no_role_name_literal.py``: a failure names the offending file
and line, and a self-sanity test proves the walk actually trips on a synthetic
violating source string so a guard that silently matches nothing cannot pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_SCANNED_PACKAGES = ("context", "artifacts")

# The forbidden call-name set -- a module-level literal, per the CTX-02/CTX-03
# contract this test enforces. Attribute-call names are matched by name alone
# (never by verifying the receiver is genuinely ``os`` / ``pathlib.Path``): the
# guard is intentionally over-inclusive across these two small packages, the
# same "match the literal regardless of context" posture
# ``test_no_role_name_literal.py`` already takes for role-name strings.
_FORBIDDEN_ATTR_NAMES = frozenset(
    {"listdir", "scandir", "walk", "iterdir", "glob", "rglob"}
)
_FORBIDDEN_BARE_NAMES = frozenset({"exec", "eval", "compile", "__import__"})


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for package in _SCANNED_PACKAGES:
        files.extend(sorted((_SRC_ROOT / package).rglob("*.py")))
    return files


def _forbidden_call_hits(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BARE_NAMES:
            hits.append(f"{filename}:{node.lineno}: {func.id}(...)")
        elif isinstance(func, ast.Attribute):
            if func.attr in _FORBIDDEN_ATTR_NAMES:
                hits.append(f"{filename}:{node.lineno}: .{func.attr}(...)")
            elif (
                func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id == "importlib"
            ):
                hits.append(f"{filename}:{node.lineno}: importlib.import_module(...)")
    return hits


def test_no_directory_enumeration_or_dynamic_execution_in_context_or_artifacts() -> (
    None
):
    scanned = _scanned_files()
    assert scanned, f"no files found under {_SRC_ROOT} / {_SCANNED_PACKAGES}"
    offenders: list[str] = []
    for path in scanned:
        offenders.extend(
            _forbidden_call_hits(path.read_text(encoding="utf-8"), str(path))
        )
    assert not offenders, (
        "directory-enumeration or dynamic-execution call found under "
        "dark_factory.context / dark_factory.artifacts:\n" + "\n".join(offenders)
    )


def test_the_walk_would_catch_a_directory_listing_call() -> None:
    """Sanity: the guard actually trips on a synthetic violating source."""
    hits = _forbidden_call_hits(
        "import os\n\ndef f():\n    return os.listdir('.')\n", "<inline>"
    )
    assert hits == ["<inline>:4: .listdir(...)"]


def test_the_walk_would_catch_a_glob_call() -> None:
    hits = _forbidden_call_hits(
        "from pathlib import Path\n\ndef f(p: Path):\n    return list(p.glob('*'))\n",
        "<inline>",
    )
    assert hits == ["<inline>:4: .glob(...)"]


def test_the_walk_would_catch_eval() -> None:
    hits = _forbidden_call_hits("eval('1 + 1')\n", "<inline>")
    assert hits == ["<inline>:1: eval(...)"]
