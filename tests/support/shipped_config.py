"""The single shipped-config copy harness for the whole test tree (10-07,
G-10-1).

``copy_shipped_config_into`` copies this repository's real shipped
``.dark-factory.yaml`` / ``.dark-factory/roles/`` / ``.dark-factory/instructions/``
set into a throwaway ``tmp_path`` git repository, then rewrites exactly two
keys before committing:

* ``quality_gate.commands`` -- the shipped value (``uv run pytest -q``,
  ``uv run ruff check .``) names *this repository's own* Python test suite.
  Since Phase 9 (commit ``4a7a19e``) these commands are genuinely executed
  by the real quality gate once the terminal role produces a PASS verdict;
  in a throwaway repo containing only the copied config tree, ``uv run
  pytest -q`` exits 5 (``EXIT_NOTESTSCOLLECTED``) -- there is no Python
  project to collect tests from. ``QualityGateResult.status`` requires
  every command to exit 0, so the gate was FAIL on every attempt, forever;
  ``_bounce_or_fail`` then bounced QA -> DEVELOPMENT against
  ``quality_gate_max_iterations`` until the run terminated FAILED. This is
  root cause (1) of G-10-1.
* ``publishing.create_pr`` -- the shipped value is ``true``, but names no
  ``repository.github_owner`` / ``repository.github_repo`` and has no
  ``GITHUB_TOKEN`` reachable from a throwaway repo's cwd (``Settings``'s
  ``env_file=".env"`` is CWD-relative). The moment root cause (1) is fixed
  the run would enter the publish branch and fail there instead -- this is
  the latent, serial root cause (2) of G-10-1.

Both keys name resources that belong to dark-factory's own checkout (its
Python test suite) and its own GitHub remote (an owner/repo a throwaway
``tmp_path`` repo does not have) -- neither is part of the property these
tests exist to prove: that the SHIPPED configuration, unmodified in every
other respect, drives a real ``dark-factory run`` subprocess to
``COMPLETED``. See ``.planning/debug/qa-gate-exhausts-bounces-terminates-failed.md``
for the full two-root-cause diagnosis this module closes.

Before this module, four integration test modules each duplicated their own
copy of this helper (``_copy_shipped_config_into`` /
``_SHIPPED_CONFIG_PATHS`` / ``_REPO_ROOT``), none of them neutralizing
anything -- which is exactly how G-10-1 went undetected for two phases.
This module is now the only shipped-config copy helper under ``tests/``;
every real-CLI-subprocess integration module imports
:func:`copy_shipped_config_into` from here.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from dark_factory.git.client import run_git

__all__ = [
    "HARNESS_GATE_COMMANDS",
    "SHIPPED_CONFIG_PATHS",
    "copy_shipped_config_into",
    "neutralize_repo_local_config",
]

# tests/support/shipped_config.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

SHIPPED_CONFIG_PATHS: tuple[str, ...] = (
    ".dark-factory.yaml",
    ".dark-factory/roles",
    ".dark-factory/instructions",
)

# A placeholder standing in for a repository's real quality-gate commands --
# present so the gate execution path actually runs and folds PASS, not a
# quality check of its own. `git --version` is chosen because `git >= 2.40`
# is a hard dependency of this project (every one of these tests shells out
# to it to build its own throwaway repo), it always exits 0, it writes
# nothing into the worktree, and `PATH` is in `WORKER_ENV_ALLOWLIST` so it
# resolves through `shell_execute`'s constructed environment.
HARNESS_GATE_COMMANDS: tuple[str, ...] = ("git --version",)


def neutralize_repo_local_config(config_path: Path) -> None:
    """Rewrite ``config_path`` (an already-copied ``.dark-factory.yaml``) in
    place: replace ``quality_gate`` with :data:`HARNESS_GATE_COMMANDS` and
    ``publishing`` with the existing mapping plus ``create_pr: False``.
    Touches no other key.

    Operates on the parsed document (``yaml.safe_load`` /
    ``yaml.safe_dump(..., sort_keys=False)``) rather than appending a second
    ``quality_gate:`` block -- a duplicate YAML key resolves by last-wins
    silently, which is exactly the kind of implicit behaviour that let
    G-10-1 live undetected for two phases.
    """
    document: dict[str, Any] = yaml.safe_load(config_path.read_text("utf-8"))
    document["quality_gate"] = {"commands": list(HARNESS_GATE_COMMANDS)}
    document["publishing"] = {**document["publishing"], "create_pr": False}
    config_path.write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def copy_shipped_config_into(root: Path) -> Path:
    """Copy this repo's real shipped config set into ``root`` (already a
    real git repository), neutralize the two repo-local declarations, and
    commit; return ``root``.

    Same signature and return contract every per-module helper this
    replaces already had, so every call site is a one-line import change.
    """
    for relative in SHIPPED_CONFIG_PATHS:
        source = _REPO_ROOT / relative
        dest = root / relative
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    neutralize_repo_local_config(root / ".dark-factory.yaml")
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", "shipped config"], cwd=root)
    return root
