"""CFG-01 / SC4 across a real process boundary: a bad ``.dark-factory.yaml``
makes ``dark-factory run`` exit 2 with nothing on stdout line 1 and no ``runs``
row.

The CLI resolves the effective-config snapshot from its cwd before it prints the
run id or creates a run; a ``ConfigError`` is mapped to exit 2 with a one-line
stderr diagnostic naming the offending file/field -- never a Typer traceback,
never a partial run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn

pytestmark = pytest.mark.integration

_BAD_BA_YAML = (
    "name: BA\n"
    "worker: bogus\n"  # <- unregistered worker: the canonical SC4 case
    "instructions: ../instructions/ba.md\n"
    "tools: []\n"
    "permissions:\n  write_scope: []\n"
    "before: [prepare_role_context]\n"
    "after: [store_role_artifacts]\n"
    "outputs: []\n"
    "examples: []\n"
)
_REPO_YAML = (
    "version: 1\n"
    "repository:\n  base_branch: main\n"
    "workflow:\n  roles: [BA]\n"
    "roles_dir: .dark-factory/roles\n"
    "quality_gate:\n  commands: []\n"
    "retry:\n"
    "  qa_developer_max_iterations: 3\n"
    "  quality_gate_max_iterations: 2\n"
    "publishing:\n  create_pr: true\n"
)


def _bad_config_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".dark-factory/roles").mkdir(parents=True)
    (root / ".dark-factory/instructions").mkdir(parents=True)
    (root / ".dark-factory.yaml").write_text(_REPO_YAML, encoding="utf-8")
    (root / ".dark-factory/roles/BA.yaml").write_text(_BAD_BA_YAML, encoding="utf-8")
    (root / ".dark-factory/instructions/ba.md").write_text("# BA\n", encoding="utf-8")
    return root


def _run_count(engine: Engine) -> int:
    with Session(engine) as session:
        return int(session.scalar(select(func.count()).select_from(Run)) or 0)


def test_bad_config_run_exits_2_with_no_run_id_and_no_row(
    tmp_path: Path, pg_url: str, engine: Engine
) -> None:
    root = _bad_config_root(tmp_path)
    before = _run_count(engine)

    proc = spawn(["run", 'text:"x"'], child_env(pg_url), cwd=root)

    assert proc.returncode == 2, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert proc.stdout.strip() == "", f"stdout was not empty: {proc.stdout!r}"
    with pytest.raises(ValueError):
        run_id_from_stdout(proc.stdout)  # no UUID on stdout line 1
    assert "bogus" in proc.stderr and "BA.yaml" in proc.stderr
    assert _run_count(engine) == before
