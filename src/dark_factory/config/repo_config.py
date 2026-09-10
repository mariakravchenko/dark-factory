"""Pydantic v2 schema for ``.dark-factory.yaml`` -- the repo-behaviour contract (CFG-01).

``.dark-factory.yaml`` is repo-controlled input. It is validated here *as if it
were external*: every model is ``frozen`` (a config value the orchestrator cannot
mutate cannot become a back-channel) and ``extra="forbid"`` (a typo'd or invented
key is caught at load time, not silently dropped into a snapshot column).

This module imports nothing from :mod:`dark_factory.config.settings`. ``Settings``
is the infrastructure-secret choke point and ``Settings.known_secret_values()``
walks ``model_fields`` for ``SecretStr``; a repo-config type reachable from there
would pollute the redaction map (03-RESEARCH Pitfall 6). ``config/loader.py``
wraps every ``ValueError`` these validators raise into ``ConfigError``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dark_factory.domain.status import RunStatus

__all__ = [
    "PublishingConfig",
    "QualityGateConfig",
    "RepoConfig",
    "RepositoryConfig",
    "RetryConfig",
    "WorkflowConfig",
]

_LEGAL_ROLE_STATUSES: frozenset[RunStatus] = frozenset(RunStatus) - {
    RunStatus.CREATED,
    RunStatus.COMPLETED,
    RunStatus.WAITING_HUMAN,
    RunStatus.FAILED,
}
"""``{BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}`` -- the run
statuses a role may occupy. ``transition()`` computes a role's status as
``RunStatus(role_name)``, so every ``workflow.roles`` entry must be one of these
values; a human label ("Architect") or a typo is rejected here, not deep in the
pure transition function at step-execution time (03-RESEARCH Pitfall 1)."""

_LEGAL_ROLE_VALUES: frozenset[str] = frozenset(s.value for s in _LEGAL_ROLE_STATUSES)


class WorkflowConfig(BaseModel):
    """``workflow:`` -- the ordered role pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: list[str] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def _roles_are_legal_statuses(cls, value: list[str]) -> list[str]:
        bad = [r for r in value if r not in _LEGAL_ROLE_VALUES]
        if bad:
            raise ValueError(
                "workflow.roles entries must be RunStatus role values "
                f"({sorted(_LEGAL_ROLE_VALUES)}); got illegal: {bad}"
            )
        return value


class RepositoryConfig(BaseModel):
    """``repository:`` -- the target repo's Git conventions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_branch: str = "main"


class QualityGateConfig(BaseModel):
    """``quality_gate:`` -- stored in the snapshot this phase, executed in Phase 9."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    commands: list[str] = Field(default_factory=list)


class RetryConfig(BaseModel):
    """``retry:`` -- feedback-loop iteration caps; stored now, enforced in Phase 9."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    qa_developer_max_iterations: int = Field(default=3, ge=0)
    quality_gate_max_iterations: int = Field(default=2, ge=0)


class PublishingConfig(BaseModel):
    """``publishing:`` -- stored now, gates PR creation in Phase 10."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    create_pr: bool = True


class RepoConfig(BaseModel):
    """The whole ``.dark-factory.yaml`` document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    repository: RepositoryConfig = RepositoryConfig()
    workflow: WorkflowConfig
    roles_dir: str = ".dark-factory/roles"
    quality_gate: QualityGateConfig = QualityGateConfig()
    retry: RetryConfig = RetryConfig()
    publishing: PublishingConfig = PublishingConfig()
