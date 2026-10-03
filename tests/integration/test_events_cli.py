"""``dark-factory events <run-id>`` -- the Typer wiring and exit-code contract,
proven through a real subprocess (Plan 12-01, Task 2 / Plan 12-02, Task 2,
OBS-03 / TRIG-02).

The CLI is invoked as a real subprocess against the provisioned PostgreSQL,
mirroring ``tests/integration/test_status_cli.py``'s own idiom exactly: the
child ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` come from ``pg_url`` so no
connection string is hardcoded or printed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration

_UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


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
# happy path: a driven run's full audit trail, in order, one seq-prefixed
# line per event
# --------------------------------------------------------------------------- #


def test_events_for_a_completed_run_names_role_and_run_lifecycle_in_order(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["events", run_id], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "expected at least one event line for a completed run"

    # Exactly one trailing newline discipline: every non-blank line begins
    # with its `seq` value, so a script can parse the stream.
    for line in lines:
        assert re.match(r"^\d+\s", line), (
            f"line does not start with a seq value: {line!r}"
        )

    joined = "\n".join(lines)
    # The shipped `FakeWorker` declares no outputs for the default
    # one-role config, so this run has no artifacts and therefore no
    # ARTIFACT_CREATED lines -- that cardinality is Task 1's db-tier proof.
    role_started_idx = joined.find("ROLE_STARTED")
    role_completed_idx = joined.find("ROLE_COMPLETED")
    run_completed_idx = joined.find("RUN_COMPLETED")
    assert -1 not in (role_started_idx, role_completed_idx, run_completed_idx)
    assert role_started_idx < role_completed_idx < run_completed_idx


# --------------------------------------------------------------------------- #
# unknown / malformed ids reserve exit 2 with an empty stdout
# --------------------------------------------------------------------------- #


def test_unknown_run_id_exits_2_with_empty_stdout(pg_url: str) -> None:
    proc = _cli(["events", _UNKNOWN_ID], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert _UNKNOWN_ID in proc.stderr


def test_malformed_run_id_exits_2_with_empty_stdout(pg_url: str) -> None:
    proc = _cli(["events", "not-a-uuid"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# the empty/short edge: a run parked mid-flight by the Plan-07 crash hook has
# "nothing much to show" -- that is success, not a bad invocation
# --------------------------------------------------------------------------- #


def test_events_for_a_run_parked_mid_flight_exits_0_with_a_short_event_list(
    pg_url: str,
) -> None:
    p1 = _cli(
        ["run", "text:park me right after CREATED -> BA"],
        pg_url,
        extra_env={"DARK_FACTORY_CRASH_AFTER": "CREATED_BA"},
    )
    assert p1.returncode != 0
    run_id = p1.stdout.splitlines()[0].strip()
    UUID(run_id)

    proc = _cli(["events", run_id], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    joined = "\n".join(lines)
    assert "RUN_CREATED" in joined
    assert "ROLE_STARTED" in joined
    # The run was parked before the worker ever ran -- it never reached
    # ROLE_COMPLETED or RUN_COMPLETED.
    assert "ROLE_COMPLETED" not in joined
    assert "RUN_COMPLETED" not in joined


# --------------------------------------------------------------------------- #
# --json: one clean array, same content as text mode, column-shaped keys
# (Plan 12-02, Task 2)
# --------------------------------------------------------------------------- #

_EVENT_ROW_KEYS = {"seq", "created_at", "type", "role_execution_id", "payload"}


def test_json_mode_emits_exactly_one_clean_json_array(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["events", run_id, "--json"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    stripped = proc.stdout.strip()
    assert stripped.startswith("[") and stripped.endswith("]")
    assert len(stripped.splitlines()) == 1, "extra lines on the --json stdout stream"
    payload = json.loads(proc.stdout)  # no preamble, no trailing text
    assert isinstance(payload, list)
    assert payload, "expected at least one event for a completed run"


def test_json_element_count_and_seq_order_match_text_mode(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    text_proc = _cli(["events", run_id], pg_url)
    json_proc = _cli(["events", run_id, "--json"], pg_url)

    assert text_proc.returncode == 0 and json_proc.returncode == 0
    text_lines = [line for line in text_proc.stdout.splitlines() if line.strip()]
    elements = json.loads(json_proc.stdout)

    assert len(elements) == len(text_lines)

    text_seqs = [int(line.split(maxsplit=1)[0]) for line in text_lines]
    json_seqs = [element["seq"] for element in elements]
    assert json_seqs == text_seqs
    assert json_seqs == sorted(json_seqs)


def test_every_json_element_key_set_equals_the_five_name_column_set(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["events", run_id, "--json"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    elements = json.loads(proc.stdout)
    assert elements
    for element in elements:
        assert set(element.keys()) == _EVENT_ROW_KEYS


# --------------------------------------------------------------------------- #
# --type: filters, repeatable, rejects an unknown name before any query
# --------------------------------------------------------------------------- #


def test_type_filter_returns_only_matching_events(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["events", run_id, "--type", "ROLE_COMPLETED"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "expected at least one ROLE_COMPLETED event"
    assert all("ROLE_COMPLETED" in line for line in lines)


def test_type_filter_is_repeatable_and_returns_both_types(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(
        [
            "events",
            run_id,
            "--type",
            "ROLE_COMPLETED",
            "--type",
            "RUN_COMPLETED",
        ],
        pg_url,
    )

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "ROLE_COMPLETED" in proc.stdout
    assert "RUN_COMPLETED" in proc.stdout


def test_unknown_type_exits_2_with_empty_stdout_before_any_query(pg_url: str) -> None:
    proc = _cli(["events", _UNKNOWN_ID, "--type", "NOT_A_TYPE"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert "NOT_A_TYPE" in proc.stderr


def test_type_filter_matching_nothing_exits_0_with_an_empty_event_list(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["events", run_id, "--type", "WIP_COMMIT_CREATED", "--json"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert json.loads(proc.stdout) == []
