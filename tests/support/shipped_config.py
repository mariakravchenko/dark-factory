"""RED-phase stub (10-07 Task 1, TDD) -- intentionally does NOT neutralize.

Placeholder pending the GREEN commit; see the module docstring that
replaces this one once ``neutralize_repo_local_config`` lands.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from dark_factory.git.client import run_git

__all__ = [
    "SHIPPED_CONFIG_PATHS",
    "copy_shipped_config_into",
]

_REPO_ROOT = Path(__file__).resolve().parents[2]

SHIPPED_CONFIG_PATHS: tuple[str, ...] = (
    ".dark-factory.yaml",
    ".dark-factory/roles",
    ".dark-factory/instructions",
)


def copy_shipped_config_into(root: Path) -> Path:
    for relative in SHIPPED_CONFIG_PATHS:
        source = _REPO_ROOT / relative
        dest = root / relative
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", "shipped config"], cwd=root)
    return root
