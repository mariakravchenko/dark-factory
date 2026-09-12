"""``dark-factory status <run-id>`` and its ``--json`` form (D-12 / D-13 / D-05).

The command is the operator-facing form of the question this whole phase exists
to answer: *where is this run, and should I resume it?* It is a thin read -- it
calls ``read_status`` and renders, and never inspects the status to decide on an
action. ``--json`` ships now because it is what makes "position comes from
columns" cleanly testable and what the later CI phases consume.

The CLI is invoked as a real subprocess against the provisioned PostgreSQL. The
child ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` come from ``pg_url`` so no
connection string is hardcoded or printed.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SRC = _REPO_ROOT / "src" / "dark_factory" / "cli.py"
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


def _text_field_keys(stdout: str) -> set[str]:
    return {line.split(":", 1)[0] for line in stdout.strip().splitlines()}


# --------------------------------------------------------------------------- #
# happy path, both modes
# --------------------------------------------------------------------------- #


def test_status_text_mode_reports_position(pg_url: str, config_root: Path) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["status", run_id], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    keys = _text_field_keys(proc.stdout)
    assert {"status", "current_role", "latest_attempt"} <= keys
    assert "status: COMPLETED" in proc.stdout
    assert "current_role: BA" in proc.stdout
    assert "latest_attempt: 1" in proc.stdout


def test_status_json_mode_emits_exactly_one_clean_json_object(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["status", run_id, "--json"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    stripped = proc.stdout.strip()
    assert stripped.startswith("{") and stripped.endswith("}")
    assert len(stripped.splitlines()) == 1, "extra lines on the --json stdout stream"
    payload = json.loads(proc.stdout)  # no preamble, no trailing text
    assert isinstance(payload, dict)


def test_json_key_set_equals_the_text_field_set(pg_url: str, config_root: Path) -> None:
    run_id = _start_run(pg_url, config_root)

    text = _cli(["status", run_id], pg_url)
    js = _cli(["status", run_id, "--json"], pg_url)

    assert text.returncode == 0 and js.returncode == 0
    assert set(json.loads(js.stdout).keys()) == _text_field_keys(text.stdout)


def test_status_after_a_run_reports_completed_ba_attempt_1(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["status", run_id, "--json"], pg_url)

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["run_id"] == run_id
    assert payload["status"] == "COMPLETED"
    assert payload["current_role"] == "BA"
    assert payload["latest_attempt"] == 1


# --------------------------------------------------------------------------- #
# unknown / malformed ids reserve exit 2 with an empty stdout
# --------------------------------------------------------------------------- #


def test_unknown_run_id_exits_2_with_empty_stdout(pg_url: str) -> None:
    proc = _cli(["status", _UNKNOWN_ID], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert _UNKNOWN_ID in proc.stderr


def test_malformed_run_id_exits_2_with_empty_stdout(pg_url: str) -> None:
    proc = _cli(["status", "not-a-uuid"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# the mid-run question: a run parked at BA by the Plan 07 crash hook
# --------------------------------------------------------------------------- #


def test_status_reports_ba_for_a_run_left_mid_flight_by_the_crash_hook(
    pg_url: str,
) -> None:
    p1 = _cli(
        ["run", "text:die right after CREATED -> BA"],
        pg_url,
        extra_env={"DARK_FACTORY_CRASH_AFTER": "CREATED_BA"},
    )
    assert p1.returncode != 0
    run_id = p1.stdout.splitlines()[0].strip()
    UUID(run_id)

    proc = _cli(["status", run_id, "--json"], pg_url)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload["status"] == "BA"
    assert payload["latest_attempt"] == 1


# --------------------------------------------------------------------------- #
# the command body is a read, not orchestration
# --------------------------------------------------------------------------- #


def test_status_command_body_carries_no_lifecycle_logic() -> None:
    source = _CLI_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)

    bodies = [
        ast.get_source_segment(source, node) or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "status"
    ]
    assert len(bodies) == 1, "expected exactly one `status` command function"
    (body,) = bodies

    assert "read_status" in body, (
        "the status command must source its data from read_status"
    )
    assert "RunStatus" not in body, (
        "the status command compares a run status to a RunStatus member — that is "
        "the orchestrator's job, not a read command's"
    )
