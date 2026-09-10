"""CFG-05 guard: configuration is never re-read live on resume.

The pipeline a run resumes with comes from the persisted ``runs.workflow``
snapshot, never from a fresh ``.dark-factory.yaml`` read. Enforced structurally:
the transitive ``dark_factory.*`` import closure of every orchestrator / pipeline
module must exclude ``dark_factory.config.loader`` (and anything under it).
``dark_factory.cli`` -- the composition root -- legitimately imports the loader,
which is what proves the closure walk actually resolves imports.

The closure walk is the ``tests/unit/test_status_import_graph.py`` idiom.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PKG = "dark_factory"
_FORBIDDEN = "dark_factory.config.loader"
_ROOT_MODULES = (
    "dark_factory.orchestrator.runner",
    "dark_factory.orchestrator.answers",
    "dark_factory.orchestrator.lifecycle",
    "dark_factory.workflows.pipeline",
)


def _module_to_path(mod: str) -> Path | None:
    rel = mod.replace(".", "/")
    for candidate in (_SRC_ROOT / f"{rel}.py", _SRC_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _dark_factory_imports(path: Path) -> set[str]:
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


def _loader_hits(closure: set[str]) -> list[str]:
    return sorted(
        m for m in closure if m == _FORBIDDEN or m.startswith(_FORBIDDEN + ".")
    )


@pytest.mark.parametrize("root_module", _ROOT_MODULES)
def test_resume_path_never_imports_the_config_loader(root_module: str) -> None:
    assert _module_to_path(root_module) is not None, f"{root_module} not on disk"
    offenders = _loader_hits(_transitive_closure(root_module))
    assert not offenders, (
        f"{root_module} transitively imports the config loader: {offenders}"
    )


def test_the_walk_resolves_imports_via_the_cli() -> None:
    """Sanity: ``dark_factory.cli`` *does* reach the loader -- it is the one
    composition point that resolves repo config -- so the guard can bite."""
    closure = _transitive_closure("dark_factory.cli")
    assert _loader_hits(closure), (
        "the transitive walk failed to reach dark_factory.config.loader from "
        "dark_factory.cli, which provably imports it"
    )
