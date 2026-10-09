"""``AttemptAwareFourRoleWorker`` must reject a context whose ``attempt`` is
not an ``int`` instead of silently selecting the wrong fixture content.

Why this file exists (debug session ``fake-artifacts-mypy-strict-errors``):
``_record`` composes its ``(role, attempt)`` lookup key from
``getattr(context, ..., None)``, because the ``CodingWorker`` port types
``context`` as ``object`` (WORK-01 -- so no adapter couples to
:class:`~dark_factory.context.builder.RoleContext`). That ``getattr`` erases
``RoleContext.attempt: int`` to ``Any | None``. The method always asserted its
``role`` invariant but never its ``attempt`` one, which had two coupled
consequences: three ``mypy --strict`` ``[arg-type]`` errors (``tuple[Any, Any
| None]`` against the three dicts' declared ``tuple[str, int]`` key), and --
the part that actually bites -- a missing or non-int ``attempt`` would *not*
raise. It would merely miss all three ``(role, attempt)`` lookups and fall
back to ``_FOUR_ROLE_FILES[role]``'s shared PASS-shaped default, so an
attempt-specific scenario ("QA FAILs on attempt 1", "the quality gate flips
on the Developer's attempt 2") would quietly become a *vacuous pass* -- the
same failure mode ``__init__`` already raises ``ValueError`` to prevent for
``out_of_scope_writes``/``worktree_root``.

This is the only gate on that assert: CI's typecheck step runs
``mypy src/dark_factory`` (``.github/workflows/ci.yml``), so ``tests/`` is not
type-checked in CI and the static half of the fix has no CI gate of its own.
The ``db``-tier suites that exercise this fixture for real need PostgreSQL;
these cases need no database and no subprocess -- ``_record`` only reads
context attributes and writes files -- so they run in the fast unit tier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dark_factory.context.builder import RoleContext
from dark_factory.domain.worker import WorkerResultStatus
from tests.support.fake_artifacts import (
    QA_VERDICT_FAIL_FILES,
    AttemptAwareFourRoleWorker,
)

pytestmark = pytest.mark.unit


def _role_context(role: str, attempt: int) -> RoleContext:
    """A real ``RoleContext`` -- the only context shape ``drive()`` ever hands
    a worker -- carrying just the fields ``_record`` reads."""
    return RoleContext(
        run_id="11111111-1111-1111-1111-111111111111",
        role=role,
        worker="fake",
        attempt=attempt,
        task={},
        answer=None,
        instructions="irrelevant to _record",
        artifacts_dir="artifacts",
    )


def _worker(tmp_path: Path) -> AttemptAwareFourRoleWorker:
    """A worker whose only override is QA attempt 1 -> FAIL-shaped verdict, so
    a wrong ``attempt`` is observable as PASS-vs-FAIL content."""
    run_dir = tmp_path / ".dark-factory" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    return AttemptAwareFourRoleWorker(
        run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
    )


def _verdict_status(tmp_path: Path) -> str:
    path = tmp_path / ".dark-factory" / "runs" / "run-1" / "artifacts" / "QA"
    return str(
        json.loads((path / "verdict.json").read_text(encoding="utf-8"))["status"]
    )


def test_mapped_attempt_selects_its_override(tmp_path: Path) -> None:
    """The in-scope boundary: the exact mapped ``(role, attempt)`` pair."""
    worker = _worker(tmp_path)

    result = worker.execute(_role_context("QA", 1))

    assert result.status is WorkerResultStatus.COMPLETED
    assert _verdict_status(tmp_path) == "FAIL"


@pytest.mark.parametrize("attempt", [2, 3])
def test_unmapped_neighbour_attempt_falls_back_to_the_shared_default(
    tmp_path: Path, attempt: int
) -> None:
    """The off-by-one neighbours of the mapped attempt must still fall back to
    ``_FOUR_ROLE_FILES``'s PASS default -- the fallback is load-bearing for
    every other db test, so narrowing ``attempt`` must not have narrowed it
    into always-hitting or always-missing."""
    worker = _worker(tmp_path)

    worker.execute(_role_context("QA", attempt))

    assert _verdict_status(tmp_path) == "PASS"


class _ContextWithoutAttempt:
    """A context that reached a worker without an ``attempt`` at all."""

    role = "QA"


class _ContextWithStringAttempt:
    """A context whose ``attempt`` survived as the string it was parsed from."""

    role = "QA"
    attempt = "1"


@pytest.mark.parametrize(
    "context",
    [_ContextWithoutAttempt(), _ContextWithStringAttempt()],
    ids=["missing-attempt", "non-int-attempt"],
)
def test_non_int_attempt_raises_instead_of_a_vacuous_pass(
    tmp_path: Path, context: object
) -> None:
    """The regression guard. Before the fix both of these returned a normal
    COMPLETED result carrying the PASS-shaped default -- a scenario asserting
    on QA's FAIL verdict would have passed for the wrong reason. They must
    fail loudly instead."""
    worker = _worker(tmp_path)

    with pytest.raises(AssertionError):
        worker.execute(context)


def test_unknown_role_still_raises(tmp_path: Path) -> None:
    """The sibling invariant ``_record`` already enforced, pinned so the two
    asserts cannot drift apart."""
    worker = _worker(tmp_path)

    class _UnknownRole:
        role = "PRODUCT_OWNER"
        attempt = 1

    with pytest.raises(AssertionError):
        worker.execute(_UnknownRole())
