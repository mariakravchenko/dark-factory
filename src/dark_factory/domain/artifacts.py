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

This module (Phase 4) registers all five machine artifact types: the
04-01-shipped ``acceptance_criteria.json`` plus the four this phase (04-03)
adds -- ``constraints.json``, ``implementation_summary.json``,
``test_report.json`` and ``verdict.json``. ``ConstraintsDocument`` and
``AcceptanceCriteriaDocument`` are deliberately symmetric (an ``id`` +
``description`` list with a minimum length of one and no duplicate id) so a
reader learns one shape, not several.

``Verdict`` (D-04) is the one model here with real internal semantics rather
than a plain container: its declared ``status`` must agree with
``computed_status``, an order-independent fold over ``criteria`` and
``issues`` -- PASS only when every criterion is PASS and no issue is
``blocking``. That is what makes the JSON contract authoritative rather than
advisory (ART-02, ROLE-06): a worker that claims PASS while reporting a
failing criterion produces a schema violation, not a value the orchestrator
has to interpret.
"""

from __future__ import annotations

from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dark_factory.domain.status import IssueSeverity, VerdictStatus

__all__ = [
    "AcceptanceCriteriaDocument",
    "AcceptanceCriterion",
    "ChangedFile",
    "ConstraintItem",
    "ConstraintsDocument",
    "ImplementationSummary",
    "TestCaseResult",
    "TestReport",
    "Verdict",
    "VerdictCriterionResult",
    "VerdictIssue",
]


def _duplicate_ids(ids: list[str]) -> list[str]:
    """The distinct values in ``ids`` that occur more than once, in first-seen order."""
    seen: set[str] = set()
    dupes: list[str] = []
    for value in ids:
        if value in seen and value not in dupes:
            dupes.append(value)
        seen.add(value)
    return dupes


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
    :class:`AcceptanceCriterion`, each linked to the requirement it verifies.

    A BA that emitted zero acceptance criteria has not made the request
    implementation-ready (minimum length one), and a repeated ``id`` would make
    D-05's id-based pairing with ``verdict.json`` ambiguous (rejected, naming
    the duplicated id) -- the same two rules :class:`Verdict` enforces on its
    own criteria list, so BA and QA are held to one standard.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[AcceptanceCriterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicate_criterion_ids(self) -> Self:
        dupes = _duplicate_ids([c.id for c in self.criteria])
        if dupes:
            raise ValueError(f"duplicate acceptance criterion id(s): {dupes}")
        return self


class ConstraintItem(BaseModel):
    """One constraint the Developer's implementation must respect."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    description: str


class ConstraintsDocument(BaseModel):
    """The Architect's ``constraints.json`` output -- deliberately symmetric
    with :class:`AcceptanceCriteriaDocument`: a non-empty list of ``id`` +
    ``description`` entries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    constraints: list[ConstraintItem] = Field(min_length=1)


class ChangedFile(BaseModel):
    """One file the Developer touched, and how."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    change: str


class ImplementationSummary(BaseModel):
    """The Developer's ``implementation_summary.json`` output.

    ``changed_files`` stays empty in Phase 4 -- there is no git worktree until
    Phase 5 (see the plan's A-04-03 scoping assumption) -- but the field exists
    now so Phase 5 fills it with no contract change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    changed_files: list[ChangedFile] = Field(default_factory=list)
    tests_added: list[str] = Field(default_factory=list)


class TestCaseResult(BaseModel):
    """One executed check QA recorded in ``test_report.json``."""

    # Not a pytest test class -- the name is a domain concept (D-10), and
    # pytest's collector otherwise warns on any class named ``Test*``.
    __test__: ClassVar[bool] = False

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    result: VerdictStatus
    detail: str = ""


class TestReport(BaseModel):
    """QA's ``test_report.json`` output -- a non-empty list of executed checks."""

    __test__: ClassVar[bool] = False

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: list[TestCaseResult] = Field(min_length=1)


class VerdictCriterionResult(BaseModel):
    """One ``acceptance_criteria.json`` criterion's QA outcome.

    ``criterion_id`` is the stable string id from
    :class:`AcceptanceCriterion.id` (D-05) -- never a positional index, so the
    two documents stay aligned when criteria are reordered or filtered between
    BA and QA. Nothing in this module or in
    :mod:`dark_factory.artifacts.validation` may pair the two files by list
    position.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str
    result: VerdictStatus
    notes: str = ""


class VerdictIssue(BaseModel):
    """One problem QA found, independent of any single criterion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: IssueSeverity
    description: str


class Verdict(BaseModel):
    """QA's ``verdict.json`` output (D-04) -- the run's independent PASS/FAIL
    decision.

    ``status`` is the worker-declared outcome; :attr:`computed_status` is the
    same outcome independently folded from ``criteria`` and ``issues``. The
    two must agree (enforced below) -- a document declaring PASS while
    carrying a FAIL criterion or a blocking issue is a schema violation, not a
    value the orchestrator has to second-guess. Reordering ``criteria`` never
    changes :attr:`computed_status` (the fold is order-independent), and the
    model preserves the input order verbatim in ``criteria`` regardless.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[VerdictCriterionResult] = Field(min_length=1)
    issues: list[VerdictIssue] = Field(default_factory=list)
    status: VerdictStatus

    @property
    def computed_status(self) -> VerdictStatus:
        """PASS iff every criterion is PASS and no issue is ``blocking`` --
        an order-independent reduction over both lists."""
        all_criteria_pass = all(
            c.result is VerdictStatus.PASS for c in self.criteria
        )
        no_blocking_issues = all(
            issue.severity is not IssueSeverity.blocking for issue in self.issues
        )
        if all_criteria_pass and no_blocking_issues:
            return VerdictStatus.PASS
        return VerdictStatus.FAIL

    @model_validator(mode="after")
    def _no_duplicate_criterion_ids(self) -> Self:
        dupes = _duplicate_ids([c.criterion_id for c in self.criteria])
        if dupes:
            raise ValueError(f"duplicate verdict criterion_id(s): {dupes}")
        return self

    @model_validator(mode="after")
    def _declared_status_matches_computed(self) -> Self:
        if self.status is not self.computed_status:
            raise ValueError(
                f"declared status {self.status.value!r} disagrees with the "
                f"computed status {self.computed_status.value!r} folded from "
                f"criteria/issues"
            )
        return self
