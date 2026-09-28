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

Plan 08-04 reassigned the shipped config's ``ARCHITECTURE``/``DEVELOPMENT``/
``QA`` roles away from ``fake`` onto real Copilot/Claude-Code/Hermes
adapters (WORK-09/SC2) -- this test predates that reassignment and, without
fake CLI executables on ``PATH``, those three roles now fail for real
(no such binaries installed) instead of running FakeWorker's in-process
zero-config synthesis. Installing the same three fake CLI executables
``test_real_pipeline_zero_config.py`` uses restores BA-only zero-config
synthesis as the *only* thing this test's own proof depends on, while the
other three roles run their real (faked) adapters exactly as the shipped
config now declares -- this test's actual claim (fresh-clone artifact
durability) never depended on which worker produced the artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.git.worktree import worktree_path
from dark_factory.persistence.models import ArtifactReference, Run
from tests.support.fake_claude_cli import write_fake_claude
from tests.support.fake_copilot_cli import write_fake_copilot
from tests.support.fake_hermes_cli import write_fake_hermes
from tests.support.git_repo import clone_repo, make_git_repo
from tests.support.shipped_config import copy_shipped_config_into

pytestmark = pytest.mark.integration

# 10-07 (G-10-1): this module's own copy helper and the two constants that
# existed only to feed it (`_copy_shipped_config_into`,
# `_SHIPPED_CONFIG_PATHS`) were collapsed into the shared
# `tests.support.shipped_config` harness -- see that module's docstring for
# why `quality_gate`/`publishing` must be neutralized for a throwaway repo.
# This module is rewired first, and alone, because it is the only one of the
# four real-CLI-subprocess modules whose helper has no importers.


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
        # 08-04: the shipped config's ARCHITECTURE/DEVELOPMENT/QA roles now
        # spawn real (faked) Copilot/Claude-Code/Hermes CLI subprocesses on
        # top of BA's in-process FakeWorker step -- a generous upper bound
        # on a cold start across four role attempts, not a timing assertion.
        timeout=240,
        check=False,
    )


@pytest.fixture
def _external_runtime_fakes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Install all three fake CLI executables -- ``claude``, ``copilot``,
    ``hermes`` -- on ``PATH`` with fake credentials (mirrors
    ``test_real_pipeline_zero_config.py``'s ``_external_runtime_fakes``, 08-04
    Task 2), so the shipped config's post-reassignment roles run their real
    (faked) adapters instead of failing outright for a missing binary. This
    test's own proof (fresh-clone artifact durability) never depended on
    which worker produced the artifacts -- only BA's zero-config synthesis
    matters here, and it stays in-process regardless."""
    fake_dir = tmp_path / "external-runtime-fakebin"
    write_fake_claude(
        fake_dir,
        stdout_payload=json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "session_id": "sess-cross-clone-development",
                "result": "implementation complete",
            }
        ),
        declared_outputs=True,
    )
    write_fake_copilot(
        fake_dir, stdout_payload="architecture design complete", declared_outputs=True
    )
    write_fake_hermes(
        fake_dir, stdout_payload="QA verification complete", declared_outputs=True
    )

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{fake_dir}{os.pathsep}{existing_path}")
    monkeypatch.setenv(
        "COPILOT_GITHUB_TOKEN", "github_pat_fake0000000000000000000000000000"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake0000000000000000000000000000")
    yield fake_dir


def test_fresh_clone_of_the_working_branch_carries_every_artifact_byte(
    pg_url: str, engine: Engine, tmp_path: Path, _external_runtime_fakes: Path
) -> None:
    config_root = copy_shipped_config_into(make_git_repo(tmp_path / "repo"))
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
        content_path = working_clone / ".dark-factory" / "runs" / str(run_id) / row.path
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
