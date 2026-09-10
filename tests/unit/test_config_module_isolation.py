"""``config/repo_config.py`` and ``config/loader.py`` must stay import-isolated
from ``config/settings.py`` and vice versa (03-RESEARCH Pitfall 6).

``Settings.known_secret_values()`` walks ``model_fields`` for ``SecretStr``. If a
repo-config type were reachable from ``Settings`` -- by import, subclass, or a
shared base -- a plain config value could land in the redaction map. The cheapest
durable guard is an AST check that the modules never import each other.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src/dark_factory"
_REPO_CONFIG = _SRC / "config/repo_config.py"
_LOADER = _SRC / "config/loader.py"
_SETTINGS = _SRC / "config/settings.py"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.add(module)
            for alias in node.names:
                found.add(f"{module}.{alias.name}")
    return found


def test_repo_config_does_not_import_settings() -> None:
    assert not any(
        m == "dark_factory.config.settings"
        or m.startswith("dark_factory.config.settings.")
        for m in _imported_modules(_REPO_CONFIG)
    )


def test_loader_does_not_import_settings() -> None:
    assert not any(
        m == "dark_factory.config.settings"
        or m.startswith("dark_factory.config.settings.")
        for m in _imported_modules(_LOADER)
    )


def test_settings_does_not_import_repo_config_or_loader() -> None:
    imported = _imported_modules(_SETTINGS)
    assert not any(
        m == "dark_factory.config.repo_config"
        or m.startswith("dark_factory.config.repo_config.")
        or m == "dark_factory.config.loader"
        or m.startswith("dark_factory.config.loader.")
        for m in imported
    )


def test_the_import_scan_actually_resolves_imports() -> None:
    """Sanity: the AST walk really finds imports -- ``loader.py`` provably imports
    ``dark_factory.config.repo_config``, so a settings regression would be caught."""
    assert "dark_factory.config.repo_config.RepoConfig" in _imported_modules(_LOADER)
