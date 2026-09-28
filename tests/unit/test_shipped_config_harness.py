"""DB-free proof for ``tests/support/shipped_config.py`` (10-07, G-10-1).

``tests.support.shipped_config.copy_shipped_config_into`` is the single
sweep point every real-CLI-subprocess integration module (Task 2) uses to
copy this repository's shipped ``.dark-factory.yaml`` config set into a
throwaway ``tmp_path`` git repository. G-10-1's root cause was that copy
being verbatim: the shipped ``quality_gate.commands`` (``uv run pytest -q``)
and ``publishing.create_pr: true`` are correct for *this* repository's own
checkout and GitHub remote, but a throwaway repo satisfies neither -- see
``.planning/debug/qa-gate-exhausts-bounces-terminates-failed.md``.

These three DB-free tests are the guard that keeps the fix honest going
forward:

1. The copied snapshot must differ from the shipped snapshot in EXACTLY
   ``quality_gate`` and ``publishing`` -- if a future edit also blanked
   ``workflow.roles``, ``retry`` or ``roles_dir``, the four integration
   tests that rely on this harness would quietly stop proving anything
   about the shipped pipeline, and this is the only thing that would
   notice.
2. The harness's replacement ``quality_gate.commands`` must be non-empty
   and must actually fold to ``VerdictStatus.PASS`` through the real
   ``run_quality_gate`` -- a zero-length command list would pass vacuously
   and leave the gate-execution path (the exact path silently broken for
   two phases) unexercised.
3. The harness must flip ``publishing.create_pr`` to ``False`` in the copy
   while leaving the shipped file's own ``True`` default untouched -- the
   second half is what keeps this meaningful if the shipped default ever
   flips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import VerdictStatus
from dark_factory.orchestrator.quality_gate import run_quality_gate
from tests.support.git_repo import make_git_repo
from tests.support.shipped_config import copy_shipped_config_into

pytestmark = pytest.mark.unit

# tests/unit/test_shipped_config_harness.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_copied_snapshot_differs_from_the_shipped_snapshot_in_exactly_two_keys(
    tmp_path: Path,
) -> None:
    """Test 1 (the honesty guard, Task 1's <behavior>): same top-level key
    set, every key except ``quality_gate``/``publishing`` compares equal."""
    copied_root = copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
    copied_snapshot = load_effective_config(copied_root)
    shipped_snapshot = load_effective_config(_REPO_ROOT)

    assert set(copied_snapshot) == set(shipped_snapshot)

    differing_keys = {
        key
        for key in copied_snapshot
        if copied_snapshot[key] != shipped_snapshot[key]
    }
    assert differing_keys == {"quality_gate", "publishing"}


def test_the_harness_gate_command_list_is_non_empty_and_passes_the_real_gate(
    tmp_path: Path,
) -> None:
    """Test 2: root cause 1 removed the strong way -- a real, non-empty
    command list that actually folds to PASS through ``run_quality_gate``,
    never a zero-length list that would pass vacuously."""
    copied_root = copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
    snapshot = load_effective_config(copied_root)
    commands = snapshot["quality_gate"]["commands"]
    assert commands, "a zero-length command list folds to PASS vacuously"

    result = run_quality_gate(
        commands=commands, cwd=copied_root, timeout=30, known_secrets={}
    )
    assert result.status is VerdictStatus.PASS
    assert all(entry.exit_code == 0 for entry in result.commands)


def test_create_pr_is_false_in_the_copy_and_still_true_in_the_shipped_file(
    tmp_path: Path,
) -> None:
    """Test 3: root cause 2 removed, and proven to be a real change -- the
    copy's ``create_pr`` is ``False`` AND the shipped file's own default is
    still ``True`` (otherwise this assertion could pass against a no-op)."""
    copied_root = copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
    copied_snapshot = load_effective_config(copied_root)
    shipped_snapshot = load_effective_config(_REPO_ROOT)

    assert copied_snapshot["publishing"]["create_pr"] is False
    assert shipped_snapshot["publishing"]["create_pr"] is True
