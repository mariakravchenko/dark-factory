"""The five MVP built-in actions referenced by the example role YAML.

An action must never open a database session, construct a ``RunEvent`` /
``RoleExecution`` / ``HumanInteraction``, or assign a lifecycle ``.status`` --
``tests/unit/test_single_mutation_path.py`` rglobs ``src/`` and covers this
package. That is a hard constraint, not a temporary one: it is exactly why
``prepare_role_context`` and ``store_role_artifacts`` stay permanent no-ops
below (WR-01, 04-REVIEW) rather than ever becoming the real context-assembly
/ artifact-persistence call sites -- ``build_role_context`` and
``collect_role_artifacts`` both open a session and write mutation-path state,
which this package's actions are forbidden to do. The shipped role YAMLs
(``.dark-factory/roles/*.yaml``) no longer list either name in
``before:``/``after:``; both calls happen unconditionally in
``orchestrator/runner.py`` for every role, not as something a role's config
opts into. ``collect_diff`` becomes real in a later phase named in its own
docstring; ``ensure_clean_worktree`` became real in Phase 5 (GIT-01, D-05,
D-06, D-08) -- it is no longer one of the stubs waiting on a later phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dark_factory.git.lifecycle import assert_attached_head, wip_commit_if_dirty

if TYPE_CHECKING:
    from dark_factory.actions.context import ActionContext

__all__ = [
    "collect_diff",
    "collect_test_results",
    "ensure_clean_worktree",
    "prepare_role_context",
    "store_role_artifacts",
]


def prepare_role_context(ctx: ActionContext) -> None:
    """Permanent no-op (WR-01, 04-REVIEW): ``RoleContext`` assembly
    (CTX-01) is ``orchestrator/runner.py``'s unconditional
    ``build_role_context`` call for every role attempt, not a hook a role's
    ``before:`` list opts into -- an action may not open the session that
    call needs. Kept only because a role YAML predating this fix may still
    reference the name; no shipped role lists it anymore."""
    return None


def ensure_clean_worktree(ctx: ActionContext) -> None:
    """Real body since Phase 5 (GIT-01, D-05, D-06, D-08): asserts the run
    worktree's ``HEAD`` is attached, then recovers any dirty content onto
    the currently-checked-out branch with a plain commit.

    This action performs **git-only work**: it never opens a ``Session`` or
    constructs a lifecycle ORM row (WR-01). It communicates its two possible
    outcomes with no return channel -- the registered action-callable type
    is ``(ActionContext) -> None`` -- so it communicates a detached HEAD by
    **raising** :class:`~dark_factory.git.DetachedHeadError` (caught by the
    runner's before-hook try/except, which fails the role without ever
    calling the worker) and communicates a recovery by **leaving a new
    commit on the branch**, which the runner observes by comparing
    ``HEAD`` before and after the before-hook pass -- there is no other way
    for an action with this signature to signal "I made a commit".

    A role YAML that omits this action from its ``before:`` list forgoes
    recovery entirely for that role (A-05-01) -- recovery is opt-in per
    role, exactly like every other configured hook.
    """
    worktree = Path(ctx.worktree)
    assert_attached_head(worktree)
    wip_commit_if_dirty(worktree, role=ctx.role, attempt=ctx.attempt)
    return None


def collect_diff(ctx: ActionContext) -> None:
    """No-op until Phase 5 / Phase 9: collects the role's working-tree diff."""
    return None


def store_role_artifacts(ctx: ActionContext) -> None:
    """Permanent no-op (WR-01, 04-REVIEW): artifact persistence (ART-01/03)
    is ``orchestrator/runner.py``'s unconditional ``collect_role_artifacts``
    call after every ``ROLE_COMPLETED`` signal, not a hook a role's
    ``after:`` list opts into -- an action may not write the mutation-path
    state that call produces. Kept only because a role YAML predating this
    fix may still reference the name; no shipped role lists it anymore."""
    return None


def collect_test_results(ctx: ActionContext) -> None:
    """No-op until Phase 9 (GATE-04): captures the quality-gate test results."""
    return None
