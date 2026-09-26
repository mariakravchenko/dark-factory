"""Schema-level coverage for ``config/repo_config.py`` + ``config/loader.py`` (CFG-01).

Proves: ``extra="forbid"`` rejection, empty / non-mapping file rejection via
``_safe_load_mapping``, the ``workflow.roles`` ``RunStatus``-membership validator,
a clean ``model_dump(mode="json")`` round-trip, and an AST guard that the loader
only ever calls ``yaml.safe_load``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from dark_factory.config.loader import (
    ConfigError,
    RoleDefinition,
    _safe_load_mapping,
    load_effective_config,
)
from dark_factory.config.repo_config import RepoConfig, RepositoryConfig

pytestmark = pytest.mark.unit

_LOADER_SRC = Path(__file__).resolve().parents[2] / "src/dark_factory/config/loader.py"


def test_repo_config_rejects_an_unknown_key() -> None:
    with pytest.raises(ValidationError):
        RepoConfig.model_validate({"workflow": {"roles": ["BA"]}, "bogus": 1})


def test_role_definition_rejects_an_unknown_key() -> None:
    with pytest.raises(ValidationError):
        RoleDefinition.model_validate(
            {"name": "BA", "worker": "fake", "instructions": "x.md", "bogus": 1}
        )


def test_empty_file_is_not_a_mapping(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a mapping"):
        _safe_load_mapping(empty)


def test_scalar_only_file_is_not_a_mapping(tmp_path: Path) -> None:
    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("main\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a mapping, got str"):
        _safe_load_mapping(scalar)


def test_empty_roles_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RepoConfig.model_validate({"workflow": {"roles": []}})


@pytest.mark.parametrize("bad_role", ["Architect", "bogus", "CREATED", "COMPLETED"])
def test_non_runstatus_role_name_is_rejected_naming_the_legal_set(
    bad_role: str,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        RepoConfig.model_validate({"workflow": {"roles": [bad_role]}})
    message = str(excinfo.value)
    assert "RunStatus role values" in message
    assert "ARCHITECTURE" in message and "BA" in message


def test_valid_repo_config_round_trips_to_a_plain_dict() -> None:
    cfg = RepoConfig.model_validate(
        {
            "version": 1,
            "repository": {"base_branch": "main"},
            "workflow": {"roles": ["BA", "QA"]},
            "quality_gate": {"commands": ["uv run pytest -q"]},
            "retry": {
                "qa_developer_max_iterations": 3,
                "quality_gate_max_iterations": 2,
            },
            "publishing": {"create_pr": True},
        }
    )
    dumped = cfg.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert dumped["workflow"]["roles"] == ["BA", "QA"]
    assert dumped["repository"]["base_branch"] == "main"
    assert dumped["roles_dir"] == ".dark-factory/roles"


def test_repository_config_round_trips_github_owner_and_repo() -> None:
    cfg = RepoConfig.model_validate(
        {
            "repository": {
                "base_branch": "main",
                "github_owner": "o",
                "github_repo": "r",
            },
            "workflow": {"roles": ["BA"]},
        }
    )
    dumped = cfg.model_dump(mode="json")
    assert dumped["repository"]["github_owner"] == "o"
    assert dumped["repository"]["github_repo"] == "r"


def test_repository_config_github_owner_and_repo_default_to_none() -> None:
    cfg = RepositoryConfig()
    assert cfg.github_owner is None
    assert cfg.github_repo is None


def test_repository_config_rejects_a_typo_d_github_owner_key() -> None:
    with pytest.raises(ValidationError):
        RepositoryConfig.model_validate({"github_onwer": "o"})


def _string_constants(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


_MINIMAL_ROLE_YAML = (
    "name: BA\n"
    "worker: fake\n"
    "instructions: ba.md\n"
    "tools: []\n"
    "permissions:\n  write_scope: []\n"
    "before: []\n"
    "after: []\n"
    "inputs: []\n"
    "outputs: []\n"
    "examples: []\n"
)


def _minimal_repo_yaml(roles_dir: str) -> str:
    return (
        "version: 1\n"
        "repository:\n  base_branch: main\n"
        "workflow:\n  roles: [BA]\n"
        f"roles_dir: {roles_dir}\n"
        "quality_gate:\n  commands: []\n"
        "retry:\n"
        "  qa_developer_max_iterations: 3\n"
        "  quality_gate_max_iterations: 2\n"
        "publishing:\n  create_pr: true\n"
    )


def test_roles_dir_escaping_the_repo_root_is_rejected(tmp_path: Path) -> None:
    """CR-01: a ``roles_dir`` that resolves outside ``root`` must raise
    ``ConfigError`` before any role YAML outside the repo is ever read --
    mirroring the containment check already applied to ``instructions:``."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "BA.yaml").write_text(_MINIMAL_ROLE_YAML, encoding="utf-8")
    (outside / "ba.md").write_text("# BA\n", encoding="utf-8")
    (root / ".dark-factory.yaml").write_text(
        _minimal_repo_yaml("../outside"), encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="roles_dir escapes the repo root"):
        load_effective_config(root)


def test_roles_dir_within_the_repo_root_still_loads(tmp_path: Path) -> None:
    """Sanity check: a well-behaved ``roles_dir`` under the repo root is
    unaffected by the CR-01 containment check."""
    root = tmp_path / "repo"
    roles_dir = root / ".dark-factory/roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "BA.yaml").write_text(_MINIMAL_ROLE_YAML, encoding="utf-8")
    (roles_dir / "ba.md").write_text("# BA\n", encoding="utf-8")
    (root / ".dark-factory.yaml").write_text(
        _minimal_repo_yaml(".dark-factory/roles"), encoding="utf-8"
    )

    snapshot = load_effective_config(root)

    assert snapshot["roles"][0]["name"] == "BA"


def test_loader_only_ever_calls_yaml_safe_load() -> None:
    tree = ast.parse(_LOADER_SRC.read_text("utf-8"), filename=str(_LOADER_SRC))

    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "safe_load" in called_attrs, "loader must call yaml.safe_load"
    assert "load" not in called_attrs, "loader must never call yaml.load"

    kwargs = {
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
    }
    assert "Loader" not in kwargs, "loader must never pass an explicit Loader="
