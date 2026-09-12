"""End-to-end proof that a spec file on disk starts and drives a real run
(INTAKE-02).

``dark-factory run spec:./task.md`` reads a Markdown file from the operator's
filesystem, normalizes it into a :class:`NormalizedTask` with ``source_kind``
``"spec"``, and drives it exactly like any other source. A missing spec file
raises ``UnresolvableSourceError`` before anything is persisted -- exit 2, no
run id on stdout, zero ``runs`` rows created.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run

pytestmark = pytest.mark.integration


def _run_cli(
    args: list[str], pg_url: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)  # want the default COMPLETED script
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=90,
        check=False,
    )


def _run_count(engine: Engine) -> int:
    with Session(engine) as session:
        value = session.scalar(select(func.count()).select_from(Run))
    return int(value or 0)


def test_spec_file_starts_and_drives_a_real_run(
    pg_url: str,
    engine: Engine,
    config_root_factory: Callable[..., Path],
) -> None:
    config_root = config_root_factory()  # throwaway one-role [BA] tree
    spec_file = config_root / "task.md"
    spec_file.write_text(
        "# Ship a health endpoint\n\nAdd a `/health` route returning 200.\n",
        encoding="utf-8",
    )

    proc = _run_cli(["run", "spec:./task.md"], pg_url, config_root)

    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    lines = proc.stdout.splitlines()
    run_id = UUID(lines[0].strip())  # D-01: bare run id on line 1

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value in {"COMPLETED", "FAILED", "WAITING_HUMAN"}
        assert run.source_kind == "spec"
        assert run.source_ref is not None
        assert run.source_ref.endswith("task.md")


def test_missing_spec_file_exits_2_and_persists_nothing(
    pg_url: str,
    engine: Engine,
    config_root_factory: Callable[..., Path],
) -> None:
    config_root = config_root_factory()
    before = _run_count(engine)

    proc = _run_cli(["run", "spec:./does-not-exist.md"], pg_url, config_root)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert _run_count(engine) == before
