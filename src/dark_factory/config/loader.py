"""Resolve ``.dark-factory.yaml`` + role YAML + instruction Markdown into one
JSON-serialisable effective-config snapshot (CFG-02, CFG-03, CFG-05).

:func:`load_effective_config` is a *pure read*: it opens files, validates them,
and either returns a plain ``dict`` or raises :class:`ConfigError`. It never
opens a ``Session``, never creates a ``runs`` row, and takes no lock -- an
interrupted or parallel config load leaves no partial run. It is called from
``start_run`` (03-03) *before* ``create_run``; the CLI maps :class:`ConfigError`
to exit 2 with nothing persisted.

Security posture (03-RESEARCH § "Security Domain"):

* YAML is parsed with ``yaml.safe_load`` **only** -- never the unsafe full
  loader nor an explicit unsafe loader argument (object construction from a
  repo-controlled file is an RCE class).
* ``worker`` and before/after ``action`` names are validated by *membership* on
  the 03-01 allowlist registries (``name in registry``), never ``registry.get``
  / ``getattr`` / ``importlib``.
* A role's ``instructions`` path is resolved relative to its role YAML's own
  directory, confirmed to be a file *under the repo root* (no ``..`` escape), and
  its inlined text is capped at 64 KiB so the snapshot row stays small.

This module must never be imported by ``dark_factory.orchestrator.*`` -- the
pipeline on resume comes from the persisted snapshot, never a live file read
(03-RESEARCH Pitfall 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dark_factory.actions import default_registry as _action_default_registry
from dark_factory.config.repo_config import RepoConfig
from dark_factory.workers.registry import default_registry as _worker_default_registry

if TYPE_CHECKING:
    from collections.abc import Container

__all__ = [
    "ConfigError",
    "RoleDefinition",
    "RolePermissions",
    "load_effective_config",
]

_MAX_INSTRUCTION_BYTES = 64 * 1024


class ConfigError(ValueError):
    """Repo config is missing, malformed, or names an unknown role/worker/action.

    Raised in ``start_run`` (03-03) *before* ``create_run`` -- the CLI maps it to
    exit 2 and no ``runs`` row is written. A ``ValueError`` subclass so the
    existing orchestration-error handling already recognises it.
    """


class RolePermissions(BaseModel):
    """``permissions:`` on a role -- stored in the snapshot, enforced in Phase 5."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    write_scope: list[str] = Field(default_factory=list)


class RoleDefinition(BaseModel):
    """One ``.dark-factory/roles/<name>.yaml`` document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    worker: str
    instructions: str
    tools: list[str] = Field(default_factory=list)
    permissions: RolePermissions = RolePermissions()
    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


def _safe_load_mapping(path: Path) -> dict[str, Any]:
    """``yaml.safe_load`` ``path`` and require a mapping at the top level."""
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping, got {type(data).__name__}")
    return data


def load_effective_config(
    root: Path,
    *,
    worker_registry: Container[str] = _worker_default_registry,
    action_registry: Container[str] = _action_default_registry,
) -> dict[str, Any]:
    """Read + validate the repo config under ``root`` into a snapshot ``dict``.

    Raises :class:`ConfigError` on any problem; opens no ``Session``.
    """
    root = root.resolve()
    repo_raw = _safe_load_mapping(root / ".dark-factory.yaml")
    try:
        repo = RepoConfig.model_validate(repo_raw)
    except ValidationError as exc:
        raise ConfigError(f".dark-factory.yaml: {exc}") from exc

    roles_dir = root / repo.roles_dir
    resolved_roles: list[dict[str, Any]] = []
    for role_name in repo.workflow.roles:
        role_path = roles_dir / f"{role_name}.yaml"
        try:
            rd = RoleDefinition.model_validate(_safe_load_mapping(role_path))
        except ValidationError as exc:
            raise ConfigError(f"{role_path}: {exc}") from exc
        if rd.name != role_name:
            raise ConfigError(
                f"{role_path}: name {rd.name!r} != workflow.roles entry {role_name!r}"
            )
        if rd.worker not in worker_registry:
            raise ConfigError(f"{role_path}: unknown worker {rd.worker!r}")
        for hook in (*rd.before, *rd.after):
            if hook not in action_registry:
                raise ConfigError(f"{role_path}: unknown action {hook!r}")

        instr_path = (role_path.parent / rd.instructions).resolve()
        if not instr_path.is_file() or not instr_path.is_relative_to(root):
            raise ConfigError(
                f"{role_path}: instructions file not found under the repo root: "
                f"{instr_path}"
            )
        text = instr_path.read_text("utf-8")
        if len(text.encode("utf-8")) > _MAX_INSTRUCTION_BYTES:
            raise ConfigError(
                f"{instr_path}: instruction file exceeds {_MAX_INSTRUCTION_BYTES} bytes"
            )
        resolved_roles.append(
            {
                "name": rd.name,
                "worker": rd.worker,
                "instructions_path": str(instr_path.relative_to(root)),
                "instruction_text": text,
                "tools": list(rd.tools),
                "permissions": rd.permissions.model_dump(mode="json"),
                "before": list(rd.before),
                "after": list(rd.after),
                "outputs": list(rd.outputs),
                "examples": list(rd.examples),
            }
        )

    return {
        "version": repo.version,
        "roles": resolved_roles,
        "repository": repo.repository.model_dump(mode="json"),
        "quality_gate": repo.quality_gate.model_dump(mode="json"),
        "retry": repo.retry.model_dump(mode="json"),
        "publishing": repo.publishing.model_dump(mode="json"),
    }
