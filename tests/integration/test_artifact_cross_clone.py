"""The SC2 / ART-04 proof: a fresh clone of a completed run's working branch
carries every artifact byte the run produced, matching the checksum Neon
recorded -- and the same paths are absent from a clone of the base branch
(D-11) (05-03 Task 3).

Drives a real four-role run as a genuine CLI subprocess against a throwaway
copy of this repository's own shipped config set, mirroring
``tests/integration/test_real_pipeline_zero_config.py``'s idiom: no explicit
``DARK_FACTORY_FAKE_SCRIPT``, so ``FakeWorker``'s true zero-config default
synthesizes real, schema-valid artifact content for every declared output
with nothing here to keep in sync with the shipped role definitions.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.git.client import run_git
from dark_factory.git.worktree import worktree_path
from dark_factory.persistence.models import ArtifactReference, Run
from tests.support.git_repo import clone_repo, make_git_repo

pytestmark = pytest.mark.integration

# tests/integration/test_artifact_cross_clone.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

_SHIPPED_CONFIG_PATHS: tuple[str, ...] = (
    ".dark-factory.yaml",
    ".dark-factory/roles",
    ".dark-factory/instructions",
)


def _copy_shipped_config_into(root: Path) -> Path:
    """Copy this repo's real shipped config set into ``root`` (already a real
    git repository on ``main``) and commit it -- the same helper
    ``test_real_pipeline_zero_config.py`` uses, duplicated per this repo's
    existing convention of each integration module owning its own fixture
    helper."""
    for relative in _SHIPPED_CONFIG_PATHS:
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


def _run_cli_against_real_repo(
    source: str, pg_url: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)  # the true zero-config default
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", "run", source],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=90,
        check=False,
    )


def test_fresh_clone_of_the_working_branch_carries_every_artifact_byte(
    pg_url: str, engine: Engine, tmp_path: Path
) -> None:
    config_root = _copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
    proc = _run_cli_against_real_repo(
        "text:prove the fresh-clone durability guarantee", pg_url, config_root
    )
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"

    run_id = UUID(proc.stdout.splitlines()[0].strip())

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        working_branch = run.working_branch
        assert working_branch is not None

        artifact_rows = list(
            session.scalars(
                select(ArtifactReference).where(ArtifactReference.run_id == run_id)
            )
        )
    assert artifact_rows, "expected at least one artifact row"

    # -- the worktree is gone: the proof is worthless if the content could
    # -- still be read from it (D-04 cleanup, this plan's Task 3) -----------
    removed_worktree = worktree_path(config_root, run_id)
    assert not removed_worktree.exists()

    # -- a fresh clone of the working branch carries every artifact byte,
    # -- matching the checksum Neon recorded (ART-04, SC2) -------------------
    working_clone = clone_repo(
        config_root, tmp_path / "fresh-clone-working", branch=working_branch
    )
    for row in artifact_rows:
        content_path = (
            working_clone / ".dark-factory" / "runs" / str(run_id) / row.path
        )
        assert content_path.is_file(), f"expected {content_path} to exist"
        data = content_path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == row.checksum, (
            f"{row.path}: content in the fresh clone does not match the "
            "checksum Neon recorded"
        )

    # -- the negative half (D-11): the same paths are absent from a clone of
    # -- the BASE branch -- run artifacts never reach the base branch's own
    # -- permanent history -----------------------------------------------
    base_clone = clone_repo(config_root, tmp_path / "fresh-clone-base", branch="main")
    for row in artifact_rows:
        content_path = base_clone / ".dark-factory" / "runs" / str(run_id) / row.path
        assert not content_path.exists(), (
            f"{content_path} must not exist on the base branch (D-11)"
        )
