"""``dark-factory artifacts <run-id> [--show <artifact-id>]`` -- proven through
a real subprocess (Plan 12-05, OBS-01 / TRIG-02).

Mirrors ``tests/integration/test_status_cli.py``'s own idiom exactly: the CLI
is invoked as a real subprocess against the provisioned PostgreSQL, the
child ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` come from ``pg_url`` so no
connection string is hardcoded or printed, and ``cwd=`` is the repository the
run was driven against -- the same resolution the ``artifacts`` command
itself uses via ``Path.cwd()``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import ArtifactReference

pytestmark = pytest.mark.integration

_UNKNOWN_RUN_ID = "00000000-0000-0000-0000-000000000000"
_UNKNOWN_ARTIFACT_ID = "11111111-1111-1111-1111-111111111111"

_DEFINITIONS: dict[str, tuple[str, str]] = {
    "BA": ("[]", "[requirements.md, acceptance_criteria.json]"),
    "ARCHITECTURE": (
        "[acceptance_criteria.json]",
        "[design.md, constraints.json]",
    ),
    "DEVELOPMENT": (
        "[design.md, constraints.json]",
        "[implementation_summary.json]",
    ),
    "QA": (
        "[acceptance_criteria.json, implementation_summary.json]",
        "[test_report.json, verdict.json]",
    ),
}
_TOOLS: dict[str, str] = {
    "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
    "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
    "DEVELOPMENT": (
        "[repo.read, repo.search, repo.write, repo.write_tests, "
        "shell.execute, artifacts.read, artifacts.write]"
    ),
    "QA": (
        "[repo.read, repo.search, repo.write_tests, shell.execute, "
        "artifacts.read, artifacts.write]"
    ),
}


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


def _start_run(
    pg_url: str, cwd: Path, source: str = "text:where are this run's artifacts"
) -> str:
    proc = _cli(["run", source], pg_url, cwd=cwd)
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout.splitlines()[0].strip()


def _artifact_ids_for_run(pg_url: str, run_id: str) -> list[uuid.UUID]:
    """Read the ``artifacts`` row ids for ``run_id`` directly from Postgres
    -- the test's own ground truth, independent of the CLI output under
    test."""
    engine = create_engine(pg_url, future=True)
    try:
        with Session(engine) as session:
            return list(
                session.scalars(
                    select(ArtifactReference.id).where(
                        ArtifactReference.run_id == uuid.UUID(run_id)
                    )
                ).all()
            )
    finally:
        engine.dispose()


def _write_four_role_tree_with_real_outputs(
    config_root_factory: Callable[..., Path],
) -> Path:
    """The same build-then-overwrite idiom
    ``tests/db/test_artifact_commit_per_role.py``'s own
    ``_write_four_role_tree`` uses -- real ``inputs:``/``outputs:``
    declarations so the shipped (unscripted) ``FakeWorker`` default actually
    synthesizes artifact files for each role (CR-01, 04-REVIEW) -- the
    default ``config_root_factory`` tree declares every role's ``outputs:``
    as ``[]``, which would otherwise leave this run with zero artifact rows
    to show at all."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"))
    for role, (inputs, outputs) in _DEFINITIONS.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {_TOOLS[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )
    return root


# --------------------------------------------------------------------------- #
# (a) + (e): the list form -- header tokens, and every id renders complete
# --------------------------------------------------------------------------- #


def test_artifacts_list_exits_0_with_the_five_column_headers_and_complete_ids(
    pg_url: str, config_root_factory: Callable[..., Path]
) -> None:
    root = _write_four_role_tree_with_real_outputs(config_root_factory)
    run_id = _start_run(pg_url, root)

    proc = _cli(["artifacts", run_id], pg_url, cwd=root)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    for header in ("artifact_id", "type", "role", "path", "created_at"):
        assert header in proc.stdout, f"missing column header: {header}"

    # Every artifact id this run produced appears intact, as a 36-character
    # substring -- an ellipsized id would make `--show` unreachable.
    ids = _artifact_ids_for_run(pg_url, run_id)
    assert ids, "the four-role tree produced zero artifact rows to assert against"
    for artifact_id in ids:
        assert str(artifact_id) in proc.stdout


# --------------------------------------------------------------------------- #
# (b): unknown / malformed run ids reserve exit 2 with an empty stdout
# --------------------------------------------------------------------------- #


def test_artifacts_list_with_a_malformed_run_id_exits_2_with_empty_stdout(
    pg_url: str,
) -> None:
    proc = _cli(["artifacts", "not-a-uuid"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""


def test_artifacts_list_with_an_unknown_run_id_exits_2_with_empty_stdout(
    pg_url: str,
) -> None:
    proc = _cli(["artifacts", _UNKNOWN_RUN_ID], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# (c) + (d): --show rejects an unknown artifact id and a bad uuid
# --------------------------------------------------------------------------- #


def test_show_with_an_unused_artifact_id_exits_2_naming_it(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["artifacts", run_id, "--show", _UNKNOWN_ARTIFACT_ID], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert _UNKNOWN_ARTIFACT_ID in proc.stderr


def test_show_with_a_malformed_artifact_id_exits_2(
    pg_url: str, config_root: Path
) -> None:
    run_id = _start_run(pg_url, config_root)

    proc = _cli(["artifacts", run_id, "--show", "not-a-uuid"], pg_url)

    assert proc.returncode == 2
    assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# (f): --show on a real artifact id prints content, exit 0
# --------------------------------------------------------------------------- #


def test_show_on_a_real_artifact_id_exits_0_and_prints_content(
    pg_url: str, config_root_factory: Callable[..., Path]
) -> None:
    root = _write_four_role_tree_with_real_outputs(config_root_factory)
    run_id = _start_run(pg_url, root)

    list_proc = _cli(["artifacts", run_id], pg_url, cwd=root)
    assert list_proc.returncode == 0, f"{list_proc.stdout}\n{list_proc.stderr}"

    ids = _artifact_ids_for_run(pg_url, run_id)
    assert ids, "the run produced no artifact to --show"

    proc = _cli(["artifacts", run_id, "--show", str(ids[0])], pg_url, cwd=root)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert proc.stdout.strip() != ""
