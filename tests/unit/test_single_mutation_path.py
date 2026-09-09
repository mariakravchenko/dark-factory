"""Source-tree proof that ``persistence/mutations.py`` is the ONLY module that
writes lifecycle state or audit events (T-01-22, STATE-06, D-14).

Implemented as a pytest test rather than a shell gate so a failure names the
offending file and line, and so it keeps working when ``mutations.py``
legitimately mentions ``RunEvent`` / ``RoleExecution`` / ``Run.status`` in its
own docstring (the AST walk ignores strings and comments entirely).

A violation is any module under ``src/dark_factory/`` other than
``persistence/mutations.py`` that:

* constructs a ``RunEvent(...)``, ``RoleExecution(...)`` or
  ``HumanInteraction(...)``, or
* assigns to a ``.status`` attribute (``obj.status = ...`` / ``obj.status += ...``).

``HumanInteraction`` joins the list for Phase 2: a question row written outside
the one mutation path would be a state change with no guarantee that its status
transition and its audit event committed with it. The guard passes trivially
today — nothing constructs the class yet — and becomes load-bearing the moment
plan ``02-03`` writes the pause path.

Class *definitions* in ``persistence/models.py`` and typed field *annotations*
(``status: Mapped[...] = mapped_column(...)``) are not assignments and do not
trip the walk.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ALLOWED = {_SRC_ROOT / "persistence" / "mutations.py"}
_LIFECYCLE_CTORS = {"RunEvent", "RoleExecution", "HumanInteraction"}


def _modules() -> Iterator[Path]:
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in _ALLOWED:
            continue
        yield path


def _attribute_targets(node: ast.Assign | ast.AugAssign) -> Iterator[ast.Attribute]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    stack = list(targets)
    while stack:
        target = stack.pop()
        if isinstance(target, ast.Attribute):
            yield target
        elif isinstance(target, ast.Tuple | ast.List):
            stack.extend(target.elts)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(_SRC_ROOT)
    out: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _LIFECYCLE_CTORS
        ):
            out.append(f"{rel}:{node.lineno} constructs {node.func.id}()")
        if isinstance(node, ast.Assign | ast.AugAssign):
            for attr in _attribute_targets(node):
                if attr.attr == "status":
                    out.append(f"{rel}:{node.lineno} assigns .status")
    return out


def test_mutations_py_is_the_sole_lifecycle_writer() -> None:
    offenders: list[str] = []
    for path in _modules():
        offenders.extend(_violations(path))
    assert not offenders, (
        "lifecycle state / audit-event writes found outside "
        "persistence/mutations.py:\n  " + "\n  ".join(offenders)
    )


def test_mutations_py_itself_would_trip_the_walk() -> None:
    # Sanity: the guard is meaningful only if the allowed module actually writes.
    (mutations_path,) = _ALLOWED
    assert _violations(mutations_path)
