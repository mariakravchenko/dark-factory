"""SC3 as an architecture constraint, not only a behavioural one.

``dark_factory.observability.status`` -- the ``status`` command's only data
source -- and every ``dark_factory`` module it transitively imports must not
import ``dark_factory.events`` (or any submodule of it). A read path that *can*
fold the audit log will eventually be asked to, and at that point the append-only
log has silently become the control state.

Walking the transitive closure (rather than the module's own import list) is what
makes the assertion meaningful: a helper that reaches the events module two hops
away would satisfy a shallow check and violate the constraint just the same.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PKG = "dark_factory"
_FORBIDDEN = "dark_factory.events"
_ROOT_MODULE = "dark_factory.observability.status"


def _module_to_path(mod: str) -> Path | None:
    rel = mod.replace(".", "/")
    for candidate in (_SRC_ROOT / f"{rel}.py", _SRC_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _dark_factory_imports(path: Path) -> set[str]:
    """Every ``dark_factory[...]`` module name imported anywhere in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _PKG or alias.name.startswith(_PKG + "."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue  # this codebase uses no relative imports
            module = node.module or ""
            if module == _PKG or module.startswith(_PKG + "."):
                found.add(module)
                for alias in node.names:
                    found.add(f"{module}.{alias.name}")
    return found


def _transitive_closure(root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_to_path(module)
        if path is None:
            continue  # a `from pkg.mod import name` symbol, not a module
        stack.extend(_dark_factory_imports(path) - seen)
    return seen


def _events_hits(closure: set[str]) -> list[str]:
    return sorted(
        m for m in closure if m == _FORBIDDEN or m.startswith(_FORBIDDEN + ".")
    )


def test_status_read_path_never_imports_the_events_module() -> None:
    assert _module_to_path(_ROOT_MODULE) is not None, (
        f"{_ROOT_MODULE} does not exist on disk"
    )

    offenders = _events_hits(_transitive_closure(_ROOT_MODULE))

    assert not offenders, (
        f"{_ROOT_MODULE} transitively imports the events module: {offenders}"
    )


def test_the_walk_actually_resolves_transitive_imports() -> None:
    """Sanity: the closure walk really follows imports -- ``persistence.mutations``
    genuinely imports the events module, so the guard would catch a regression."""
    closure = _transitive_closure("dark_factory.persistence.mutations")
    assert _events_hits(closure), (
        "the transitive walk failed to reach dark_factory.events from a module "
        "that provably imports it"
    )
