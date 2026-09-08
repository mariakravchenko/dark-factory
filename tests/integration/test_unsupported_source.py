"""Unsupported and unresolvable sources exit 2 with nothing persisted (D-23).

``spec:`` and ``github:`` classify successfully but their loaders raise
``SourceNotSupportedError``; an unresolvable prefix and an empty ``text:`` body
raise ``UnresolvableSourceError``. In every case the process exits 2 and the
``runs`` row count is unchanged -- exit 2 is reserved for failures *before*
anything is persisted.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run

pytestmark = pytest.mark.integration


def _cli(args: list[str], pg_url: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
        check=False,
    )


def _run_count(engine: Engine) -> int:
    with Session(engine) as session:
        value = session.scalar(select(func.count()).select_from(Run))
    return int(value or 0)


@pytest.mark.parametrize(
    ("source", "phase_marker"),
    [
        ("spec:./task.md", "Phase 4"),
        ("github:152", "Phase 10"),
    ],
)
def test_unsupported_source_exits_2_names_its_phase_and_persists_nothing(
    source: str, phase_marker: str, pg_url: str, engine: Engine
) -> None:
    before = _run_count(engine)
    proc = _cli(["run", source], pg_url)
    assert proc.returncode == 2
    assert phase_marker in proc.stderr
    assert _run_count(engine) == before


def test_empty_text_body_exits_2_and_persists_nothing(
    pg_url: str, engine: Engine
) -> None:
    before = _run_count(engine)
    proc = _cli(["run", 'text:""'], pg_url)
    assert proc.returncode == 2
    assert _run_count(engine) == before


def test_resume_with_an_unknown_run_id_exits_2(pg_url: str, engine: Engine) -> None:
    before = _run_count(engine)
    proc = _cli(["resume", "00000000-0000-0000-0000-000000000000"], pg_url)
    assert proc.returncode == 2
    assert _run_count(engine) == before
