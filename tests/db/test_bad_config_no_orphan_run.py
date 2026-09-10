"""CFG-01 / SC4: every bad-config shape raises ``ConfigError`` at run creation --
*before* ``create_run`` -- so the ``runs`` table is never touched.

``load_effective_config`` opens no ``Session`` and writes no row, and
``start_run`` evaluates ``snapshot=load_effective_config(root)`` before it calls
``create_run``; so a malformed ``.dark-factory.yaml`` / role YAML / instruction
file leaves the ``runs`` count exactly where it was. Each case builds a throwaway
``.dark-factory/`` tree that is valid except for the one thing under test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.config.loader import ConfigError, load_effective_config
from dark_factory.orchestrator.runner import start_run
from dark_factory.persistence.models import Run

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_VALID_REPO_YAML = (
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
_VALID_BA_YAML = (
    "name: BA\n"
    "worker: fake\n"
    "instructions: ../instructions/ba.md\n"
    "tools: []\n"
    "permissions:\n  write_scope: []\n"
    "before: [prepare_role_context]\n"
    "after: [store_role_artifacts]\n"
    "outputs: []\n"
    "examples: []\n"
)


def _write_tree(
    root: Path,
    *,
    repo_yaml: str = _VALID_REPO_YAML,
    ba_yaml: str | None = _VALID_BA_YAML,
    ba_instructions: str | None = "# BA\n\nInstruction text.\n",
) -> Path:
    (root / ".dark-factory/roles").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory/instructions").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory.yaml").write_text(repo_yaml, encoding="utf-8")
    if ba_yaml is not None:
        (root / ".dark-factory/roles/BA.yaml").write_text(ba_yaml, encoding="utf-8")
    if ba_instructions is not None:
        (root / ".dark-factory/instructions/ba.md").write_text(
            ba_instructions, encoding="utf-8"
        )
    return root


def _bad_role_name(root: Path) -> Path:
    return _write_tree(
        root,
        repo_yaml=_VALID_REPO_YAML.replace("roles: [BA]", "roles: [Architect]"),
    )


def _unknown_worker(root: Path) -> Path:
    return _write_tree(
        root, ba_yaml=_VALID_BA_YAML.replace("worker: fake", "worker: bogus")
    )


def _unknown_action(root: Path) -> Path:
    return _write_tree(
        root,
        ba_yaml=_VALID_BA_YAML.replace(
            "before: [prepare_role_context]", "before: [nope]"
        ),
    )


def _missing_instruction_file(root: Path) -> Path:
    return _write_tree(root, ba_instructions=None)


def _escaping_instruction_path(root: Path) -> Path:
    return _write_tree(
        root,
        ba_yaml=_VALID_BA_YAML.replace(
            "instructions: ../instructions/ba.md",
            "instructions: ../../../../../../etc/hosts",
        ),
    )


def _empty_repo_yaml(root: Path) -> Path:
    return _write_tree(root, repo_yaml="")


def _non_mapping_repo_yaml(root: Path) -> Path:
    return _write_tree(root, repo_yaml="just a string\n")


def _unknown_role_key(root: Path) -> Path:
    return _write_tree(root, ba_yaml=_VALID_BA_YAML + "surprise: 1\n")


_CASES: dict[str, Callable[[Path], Path]] = {
    "non_runstatus_role_name": _bad_role_name,
    "unknown_worker": _unknown_worker,
    "unknown_action": _unknown_action,
    "missing_instruction_file": _missing_instruction_file,
    "escaping_instruction_path": _escaping_instruction_path,
    "empty_repo_yaml": _empty_repo_yaml,
    "non_mapping_repo_yaml": _non_mapping_repo_yaml,
    "unknown_role_key": _unknown_role_key,
}


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


def _run_count(engine: Engine) -> int:
    with Session(engine) as session:
        return int(session.scalar(select(func.count()).select_from(Run)) or 0)


@pytest.mark.parametrize("case", sorted(_CASES))
def test_bad_config_raises_before_create_run_and_writes_no_row(
    case: str,
    tmp_path: Path,
    engine: Engine,
    real_session_factory: SessionFactory,
) -> None:
    root = _CASES[case](tmp_path / case)

    before = _run_count(engine)

    with pytest.raises(ConfigError):
        # load_effective_config is evaluated first; it must raise before
        # start_run ever reaches create_run.
        start_run(
            "text:bad config",
            session_factory=real_session_factory,
            snapshot=load_effective_config(root),
        )

    assert _run_count(engine) == before, (
        f"{case}: a runs row was written despite the config being rejected"
    )
