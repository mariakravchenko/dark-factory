"""Machine artifact-type contracts (D-05, D-10).

A machine artifact is a JSON file a later role or Dark Factory itself parses
and acts on -- as opposed to a Markdown document, which is human documentation
and carries no schema. Every model here is the frozen, ``extra="forbid"``
boundary-model shape used everywhere a value crosses a role/worker boundary
(:mod:`dark_factory.domain.worker`): a role's artifact file the orchestrator
cannot mutate cannot become a back-channel for state changes, and an
unexpected field is caught here rather than silently accepted.

Validation entry point is always ``Model.model_validate(json_content)``, never
a hand-rolled key check. A ``pydantic.ValidationError`` is **not** caught in
this module -- it propagates to the caller
(:mod:`dark_factory.artifacts.validation`), which turns it into the D-09
failure path.

This phase (04-01) registers exactly one machine artifact type,
``acceptance_criteria.json``. The remaining four (``constraints.json``,
``implementation_summary.json``, ``test_report.json``, ``verdict.json``) are
plan 04-02's scope.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AcceptanceCriteriaDocument", "AcceptanceCriterion"]


class AcceptanceCriterion(BaseModel):
    """One acceptance check the BA derived from a requirement.

    ``id`` is a stable string id (``AC-1`` shape, D-05) -- never a positional
    index, so a later insertion/reorder never renumbers an existing criterion.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    description: str


class AcceptanceCriteriaDocument(BaseModel):
    """The BA's ``acceptance_criteria.json`` output -- an ordered list of
    :class:`AcceptanceCriterion`, each linked to the requirement it verifies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[AcceptanceCriterion] = Field(default_factory=list)
