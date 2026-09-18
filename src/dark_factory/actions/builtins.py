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
opts into. ``ensure_clean_worktree`` became real in Phase 5 (GIT-01, D-05,
D-06, D-08); ``collect_diff`` became real in plan 05-03 (D-10) -- only
``collect_test_results`` still waits on a later phase (Phase 9, GATE-04).

Phase 6 (plan 06-01, TOOL-03): artifact-tier capability grants are checked
inside ``collect_role_artifacts`` itself, at the same unconditional
post-``ROLE_COMPLETED`` call site -- never here. A role-configurable
``after:`` hook is opt-in, so a permission check hosted inside one is a
check a role's own config could omit; deny-by-default that a role's config
can switch off is not deny-by-default.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dark_factory.artifacts.paths import resolve_under_run_root
from dark_factory.git.diff import DIFF_PATCH_FILENAME, collect_pr_diff
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
    """Real since plan 05-03 (D-10): writes the PR-bound diff of the run's
    working branch against its base, with every ``.dark-factory`` path
    excluded, to ``verification/<DIFF_PATCH_FILENAME>`` under the run root.

    This action performs **git and filesystem work only** and opens no
    ``Session`` (WR-01): the registered action-callable type is
    ``(ActionContext) -> None``, so a file in the run tree is the only
    durable channel to hand its result to Phase 9's quality gate and
    Phase 10's publisher. Because the ``after:`` hook pass runs *before*
    that role's artifact commit (``orchestrator/runner.py``'s
    ``commit_run_artifacts`` call), this patch file is carried by that same
    commit and is itself excluded from the PR-bound diff by the same
    pathspec that excludes the rest of ``.dark-factory`` (A-05-09).

    Returns immediately, writing nothing, when either ``ctx.base_branch`` or
    ``ctx.working_branch`` is ``None`` -- a legacy run predating this phase
    has no branch identity to diff, and a hook is not the place to fail a
    run for that.
    """
    if ctx.base_branch is None or ctx.working_branch is None:
        return None
    diff_text = collect_pr_diff(
        Path(ctx.worktree),
        base_branch=ctx.base_branch,
        working_branch=ctx.working_branch,
    )
    destination = resolve_under_run_root(
        Path(ctx.run_root), f"verification/{DIFF_PATCH_FILENAME}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(diff_text, encoding="utf-8")
    return None


def store_role_artifacts(ctx: ActionContext) -> None:
    """Permanent no-op (WR-01, 04-REVIEW): artifact persistence (ART-01/03)
    is ``orchestrator/runner.py``'s unconditional ``collect_role_artifacts``
    call after every ``ROLE_COMPLETED`` signal, not a hook a role's
    ``after:`` list opts into -- an action may not write the mutation-path
    state that call produces. Kept only because a role YAML predating this
    fix may still reference the name; no shipped role lists it anymore.

    Phase 6 (plan 06-01, TOOL-03): this is also where the artifact-tier
    capability grant (``artifacts.read``) is checked, via
    ``collect_role_artifacts``'s own ``tool_registry.invoke(...)`` call --
    deliberately not here, for the identical reason: an ``after:`` hook is
    opt-in per role, and a permission check a role's own config can omit by
    dropping the hook name is not deny-by-default."""
    return None


def collect_test_results(ctx: ActionContext) -> None:
    """No-op until Phase 9 (GATE-04): captures the quality-gate test results."""
    return None
