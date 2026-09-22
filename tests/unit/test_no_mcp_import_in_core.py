"""TOOL-05 / D-14 / SC5 removability guard: no module on the orchestrator's
core import closure imports the third-party ``mcp`` package.

ROADMAP SC5 makes two claims: tools are exposed over MCP, and removing MCP
entirely leaves the orchestrator fully functional. This module is the
*import-graph* half of that second claim's proof; ``pyproject.toml``'s
``[project.optional-dependencies] mcp`` group (D-13) is the *install-graph*
half. An installation that never runs ``uv sync --all-extras`` never has
``mcp`` on disk at all, and every test in this suite except
``tests/unit/test_mcp_adapter.py`` still passes -- this guard is what keeps
that true over time rather than true only on the day it was written.

This module imports nothing from ``mcp`` and is **not** gated on the extra
being installed -- unlike ``tests/unit/test_mcp_adapter.py``, it carries no
pytest skip-on-missing-dependency marker of any kind. It is an absence
proof and must run and pass whether or not ``mcp`` is present, using only
``ast`` and ``pathlib`` to read source. Do not "fix" a future failure here
by making this module conditional on the extra; that would make the guard
silently stop proving anything in exactly the configuration (the extra
genuinely absent) it exists to protect.

The walk (``_module_to_path`` / ``_dark_factory_imports`` /
``_transitive_closure``) is reused verbatim from
``tests/unit/test_orchestrator_no_live_config_read.py``. Its hit *detector*
is deliberately **not** reused: ``_dark_factory_imports`` only collects
``dark_factory.*``-prefixed import names, so a bare ``import mcp`` at the
top of a core module is invisible to it -- a guard copy-pasted verbatim
from that precedent would pass even if core code imported the SDK directly
(RESEARCH Pitfall 4). ``_third_party_mcp_imports`` below is a second,
purpose-built AST helper that scans a module's own source for a genuinely
third-party ``mcp`` / ``mcp_types`` import, and is careful not to confuse
that with the in-package module name ``dark_factory.tools.mcp_transport``,
which merely contains the substring ``mcp``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PKG = "dark_factory"
_MCP_TRANSPORT_MODULE = "dark_factory.tools.mcp_transport"
_THIRD_PARTY_MCP_NAMES = ("mcp", "mcp_types")
_ROOT_MODULES = (
    "dark_factory.orchestrator.runner",
    "dark_factory.orchestrator.answers",
    "dark_factory.orchestrator.lifecycle",
    "dark_factory.workflows.pipeline",
    "dark_factory.tools.registry",
)


def _module_to_path(mod: str) -> Path | None:
    rel = mod.replace(".", "/")
    for candidate in (_SRC_ROOT / f"{rel}.py", _SRC_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _dark_factory_imports(path: Path) -> set[str]:
    """Every ``dark_factory[...]`` module name imported anywhere in
    ``path`` -- used only to drive the transitive *walk*, mirroring
    ``test_orchestrator_no_live_config_read.py`` exactly. This helper
    cannot see a third-party ``import mcp`` at all; see
    :func:`_third_party_mcp_imports` for the detector that actually proves
    this guard's claim."""
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


def _is_third_party_mcp_name(name: str) -> bool:
    """``True`` for exactly ``mcp`` / ``mcp_types`` or a dotted submodule of
    either (``mcp.server``, ``mcp_types.tool``, ...) -- and ``False`` for
    any ``dark_factory``-prefixed name, including
    ``dark_factory.tools.mcp_transport``, which merely *contains* the
    substring ``mcp`` and is never a hit on that basis alone."""
    return name in _THIRD_PARTY_MCP_NAMES or any(
        name.startswith(f"{prefix}.") for prefix in _THIRD_PARTY_MCP_NAMES
    )


def _third_party_mcp_imports(path: Path) -> set[str]:
    """Every top-level third-party ``mcp`` / ``mcp_types`` import
    statement in ``path``'s own source -- ``import mcp``, ``import
    mcp.server``, ``from mcp import Client``, ``from mcp_types import
    Tool``, and so on. Distinct from :func:`_dark_factory_imports`: this
    helper is what actually detects the SDK, not an in-package import
    (RESEARCH Pitfall 4)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_third_party_mcp_name(alias.name):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue  # this codebase uses no relative imports
            module = node.module or ""
            if _is_third_party_mcp_name(module):
                found.add(module)
    return found


# --------------------------------------------------------------------------- #
# The guard itself (D-14, SC5)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("root_module", _ROOT_MODULES)
def test_core_closure_never_imports_the_third_party_mcp_package(
    root_module: str,
) -> None:
    assert _module_to_path(root_module) is not None, f"{root_module} not on disk"
    closure = _transitive_closure(root_module)

    offenders: list[str] = []
    for module in sorted(closure):
        path = _module_to_path(module)
        if path is None:
            continue
        hits = _third_party_mcp_imports(path)
        if hits:
            offenders.append(f"{module} imports {sorted(hits)}")

    assert not offenders, (
        f"{root_module}'s transitive dark_factory import closure reaches a "
        f"third-party mcp import: {offenders}"
    )


@pytest.mark.parametrize("root_module", _ROOT_MODULES)
def test_mcp_transport_module_is_absent_from_the_core_closure(
    root_module: str,
) -> None:
    closure = _transitive_closure(root_module)
    assert _MCP_TRANSPORT_MODULE not in closure, (
        f"{root_module} transitively imports {_MCP_TRANSPORT_MODULE}, the "
        f"one module that imports mcp directly -- it must remain unreachable "
        f"from every core root"
    )


# --------------------------------------------------------------------------- #
# Walk-has-teeth companion (D-14): a broken/silent walk and a clean codebase
# are indistinguishable without this. Positive control against the one
# module on disk that DOES import mcp.
# --------------------------------------------------------------------------- #


def test_the_detector_would_catch_mcp_transport_importing_mcp() -> None:
    path = _module_to_path(_MCP_TRANSPORT_MODULE)
    assert path is not None, (
        f"{_MCP_TRANSPORT_MODULE} is absent from disk -- this positive "
        f"control depends on plan 06-03 Task 2's src/dark_factory/tools/"
        f"mcp_transport.py existing and importing mcp; if that file is "
        f"missing, this test cannot prove the detector has teeth and must "
        f"not be allowed to pass vacuously"
    )
    hits = _third_party_mcp_imports(path)
    assert hits, (
        f"{_MCP_TRANSPORT_MODULE} provably imports mcp at module scope, but "
        f"_third_party_mcp_imports found nothing -- the detector's walk is "
        f"broken and this guard would pass over a real violation"
    )


def test_the_detector_does_not_confuse_the_in_package_module_name_with_mcp() -> None:
    """Sanity: a module that merely *imports* ``dark_factory.tools.mcp_transport``
    -- an in-package name containing the substring ``mcp`` -- is not itself a
    hit. Only a genuinely third-party ``mcp`` / ``mcp_types`` import is."""
    source = (
        "from dark_factory.tools.mcp_transport import build_mcp_server\n"
        "import dark_factory.tools.mcp_transport\n"
    )
    tree = ast.parse(source, filename="<inline>")
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_third_party_mcp_name(alias.name):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if _is_third_party_mcp_name(module):
                found.add(module)
    assert found == set(), (
        f"the in-package module name dark_factory.tools.mcp_transport was "
        f"misidentified as a third-party mcp import: {found}"
    )
