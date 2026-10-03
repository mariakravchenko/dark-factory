"""``dark-factory runs`` -- the triage entry point, proven through a real
subprocess (Plan 12-02, Task 1, OBS-03 / D-03).

The CLI is invoked as a real subprocess against the provisioned PostgreSQL,
mirroring ``tests/integration/test_status_cli.py``'s own idiom exactly: the
child ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` come from ``pg_url`` so no
connection string is hardcoded or printed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dark_factory.observability.render import render_runs_table

pytestmark = pytest.mark.integration


def _cli(
    args: list[str],
    pg_url: str,
    *,
    extra_env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": pg_url,
        "DATABASE_URL_DIRECT": pg_url,
    }
    env.pop("DARK_FACTORY_FAKE_SCRIPT", None)
    env.pop("DARK_FACTORY_CRASH_AFTER", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=120,
        check=False,
    )


def _start_run(pg_url: str, cwd: Path, source: str = "text:where is this run") -> str:
    proc = _cli(["run", source], pg_url, cwd=cwd)
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout.splitlines()[0].strip()


# --------------------------------------------------------------------------- #
# happy path: both runs appear, ids survive rendering intact, newest first
# --------------------------------------------------------------------------- #


def test_two_runs_both_appear_with_full_intact_ids_newest_first(
    pg_url: str, config_root: Path
) -> None:
    older_id = _start_run(pg_url, config_root, source="text:the older run")
    newer_id = _start_run(pg_url, config_root, source="text:the newer run")

    proc = _cli(["runs"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    stdout = proc.stdout

    # (a) the full id is present as an exact substring -- not a prefix slice.
    assert older_id in stdout
    assert newer_id in stdout

    # (b) the more recently created run's id appears at a lower stdout offset.
    newer_idx = stdout.find(newer_id)
    older_idx = stdout.find(older_id)
    assert -1 not in (newer_idx, older_idx)
    assert newer_idx < older_idx

    # (e) the column header tokens all appear.
    for token in ("id", "status", "source", "created_at", "updated_at"):
        assert token in stdout


# --------------------------------------------------------------------------- #
# --status filters
# --------------------------------------------------------------------------- #


def test_status_filter_includes_matching_and_excludes_others(
    pg_url: str, config_root: Path
) -> None:
    completed_id = _start_run(pg_url, config_root, source="text:this one completes")

    p1 = _cli(
        ["run", "text:park me right after CREATED -> BA"],
        pg_url,
        extra_env={"DARK_FACTORY_CRASH_AFTER": "CREATED_BA"},
    )
    assert p1.returncode != 0
    parked_id = p1.stdout.splitlines()[0].strip()

    completed_proc = _cli(["runs", "--status", "COMPLETED"], pg_url)
    assert completed_proc.returncode == 0, (
        f"{completed_proc.stdout}\n{completed_proc.stderr}"
    )
    assert completed_id in completed_proc.stdout

    waiting_proc = _cli(["runs", "--status", "WAITING_HUMAN"], pg_url)
    assert waiting_proc.returncode == 0, f"{waiting_proc.stdout}\n{waiting_proc.stderr}"
    assert parked_id not in waiting_proc.stdout
    assert completed_id not in waiting_proc.stdout


def test_unknown_status_exits_2_with_empty_stdout(pg_url: str) -> None:
    proc = _cli(["runs", "--status", "not-a-real-status"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert "not-a-real-status" in proc.stderr


# --------------------------------------------------------------------------- #
# the empty-table case, rendered directly (seeding a genuinely empty `runs`
# table through the CLI would require tearing down rows other tests in the
# shared database own)
# --------------------------------------------------------------------------- #


def test_render_runs_table_on_an_empty_list_shows_headers_and_no_rows() -> None:
    out = render_runs_table([])

    for token in ("id", "status", "source", "created_at", "updated_at"):
        assert token in out
