"""SC2 / CFG-02 / CFG-03: editing a ``.dark-factory/roles/*.yaml`` field changes
what a fresh run does, with no Python source touched.

Every case drives a real ``python -m dark_factory run`` subprocess whose working
directory is a throwaway ``.dark-factory/`` tree (the ``config_root`` builder
from 03-02). Between runs this module rewrites *only* ``BA.yaml`` -- its
``after`` list, its ``instructions`` path, its ``worker`` -- and asserts the
persisted ``runs.workflow`` snapshot of the next run reflects the edit:

* an edited ``after:`` list shows up verbatim in ``roles[0]["after"]``;
* an edited ``instructions:`` path inlines the *new* file's bytes verbatim into
  ``roles[0]["instruction_text"]``;
* an edited ``worker:`` changes which worker the run dispatches (``copilot`` is a
  registered placeholder, so the run reaches dispatch and fails with the
  ``NotImplementedError`` that names Phase 8 -- proving the name came from YAML).

A SHA-256 digest of every ``*.py`` under ``src/dark_factory`` is taken before and
after each test: editing role YAML must never require a source change.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.persistence.models import Run
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    run_id_from_stdout,
    spawn,
)

pytestmark = pytest.mark.integration

_SRC = REPO_ROOT / "src" / "dark_factory"


def _src_digest() -> str:
    h = hashlib.sha256()
    for path in sorted(_SRC.rglob("*.py")):
        h.update(path.relative_to(REPO_ROOT).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _write_ba_role(
    root: Path,
    *,
    worker: str = "fake",
    before: str = "[prepare_role_context]",
    after: str = "[store_role_artifacts]",
    instructions: str = "../instructions/ba.md",
) -> None:
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        f"worker: {worker}\n"
        f"instructions: {instructions}\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        f"before: {before}\n"
        f"after: {after}\n"
        "outputs: []\n"
        "examples: []\n",
        encoding="utf-8",
    )


def _run(root: Path, pg_url: str, source: str) -> tuple[int, str, str]:
    proc = spawn(["run", source], child_env(pg_url), cwd=root)
    return proc.returncode, proc.stdout, proc.stderr


def _persisted_role0(engine: Engine, run_id: object) -> dict[str, Any]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        roles = dict(run.workflow)["roles"]
        assert isinstance(roles, list) and roles
        return roles[0]


def test_editing_the_after_list_changes_the_persisted_role_snapshot(
    config_root: Path, pg_url: str, engine: Engine
) -> None:
    digest_before = _src_digest()

    rc, stdout, stderr = _run(config_root, pg_url, "text:sc2-after-baseline")
    assert rc == 0, f"exit={rc}\n{stdout}\n{stderr}"
    baseline = _persisted_role0(engine, run_id_from_stdout(stdout))
    assert baseline["after"] == ["store_role_artifacts"]

    _write_ba_role(config_root, after="[collect_test_results, store_role_artifacts]")

    rc, stdout, stderr = _run(config_root, pg_url, "text:sc2-after-edited")
    assert rc == 0, f"exit={rc}\n{stdout}\n{stderr}"
    edited = _persisted_role0(engine, run_id_from_stdout(stdout))
    assert edited["after"] == ["collect_test_results", "store_role_artifacts"]

    assert _src_digest() == digest_before


def test_editing_the_instructions_path_inlines_the_new_bytes_verbatim(
    config_root: Path, pg_url: str, engine: Engine
) -> None:
    digest_before = _src_digest()

    new_text = "# BA (alternate)\n\nDistinct instruction bytes: ¡hola! 4217.\n"
    (config_root / ".dark-factory/instructions/ba_alt.md").write_text(
        new_text, encoding="utf-8"
    )
    _write_ba_role(config_root, instructions="../instructions/ba_alt.md")

    rc, stdout, stderr = _run(config_root, pg_url, "text:sc2-instructions-edited")
    assert rc == 0, f"exit={rc}\n{stdout}\n{stderr}"

    role0 = _persisted_role0(engine, run_id_from_stdout(stdout))
    assert role0["instruction_text"] == new_text
    assert role0["instructions_path"] == ".dark-factory/instructions/ba_alt.md"

    assert _src_digest() == digest_before


def test_editing_the_worker_changes_which_worker_the_run_dispatches(
    config_root: Path, pg_url: str, engine: Engine
) -> None:
    digest_before = _src_digest()

    _write_ba_role(config_root, worker="copilot")
    rc, stdout, stderr = _run(config_root, pg_url, "text:sc2-worker-copilot")

    # the run is created (copilot is a registered placeholder), so the name was
    # read from YAML and persisted; dispatch then raises the Phase 8 placeholder.
    run_id = run_id_from_stdout(stdout)
    assert _persisted_role0(engine, run_id)["worker"] == "copilot"
    assert rc != 0
    assert "copilot" in stderr and "Phase 8" in stderr

    # revert: a fake worker drives the same one-role pipeline to COMPLETED
    _write_ba_role(config_root, worker="fake")
    rc, stdout, stderr = _run(config_root, pg_url, "text:sc2-worker-reverted")
    assert rc == 0, f"exit={rc}\n{stdout}\n{stderr}"
    assert "BA → COMPLETED" in stdout
    assert _persisted_role0(engine, run_id_from_stdout(stdout))["worker"] == "fake"

    assert _src_digest() == digest_before
