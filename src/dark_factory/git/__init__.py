"""The ``dark_factory.git`` package -- the ONLY place in ``dark_factory`` that
invokes the ``git`` binary (GIT-02).

Nothing in this package opens a ``Session`` or constructs a lifecycle ORM row
(WR-01) -- ``tests/unit/test_git_ownership_boundary.py`` proves this package
(and no other module under ``src/dark_factory/``) ever shells out to ``git``.
Every function here takes explicit paths and returns plain values or raises a
typed error from the hierarchy below; nothing reads ``Path.cwd()`` or opens a
database connection.

Error hierarchy:

* :class:`GitError` -- the base class for every failure this package raises.
* :class:`GitCommandError` -- a ``git`` subprocess exited non-zero on a
  checked invocation; carries ``args``, ``returncode`` and ``stderr`` as
  attributes alongside a message naming the subcommand, the exit code and the
  first line of stderr.
* :class:`DetachedHeadError` -- raised by :func:`~dark_factory.git.lifecycle.assert_attached_head`
  when a role enters a worktree whose ``HEAD`` is detached (plan 05-02).
* :class:`WorktreePathError` -- raised by :func:`~dark_factory.git.worktree.ensure_worktree`
  for a run with no persisted ``working_branch`` / ``base_branch``, and by
  other worktree-path failures.
* :class:`WriteScopeViolation` -- raised by
  :func:`~dark_factory.git.scope.enforce_write_scope` (plan 05-04, D-13) when
  a role's diff touches a path outside its configured ``write_scope``, after
  every violating path has already been reverted.
* :class:`ArtifactScopeViolation` -- raised by
  :func:`~dark_factory.git.scope.enforce_artifact_scope` (plan 08-05, CR-01)
  when a role's attempt changes an artifact path under the run's
  ``.dark-factory/runs/<run_id>/artifacts/`` tree outside its own
  ``artifacts/<role>/`` subtree, after every violating path has already been
  reverted. A sibling of :class:`WriteScopeViolation`, not a replacement for
  it -- ``write_scope`` enforcement (``attempt_changed_paths``) deliberately
  excludes the gitignored run tree (A-05-15); this exception covers exactly
  that excluded subtree instead.
* :class:`GitPushError` -- raised by :func:`~dark_factory.git.diff.push_working_branch`
  (plan 05-03, D-16) when every retry of ``git push origin <working_branch>``
  fails. A distinguishable subtype of :class:`GitError` (not of
  :class:`GitCommandError`, since its message is already redacted and
  reworded rather than the raw subprocess failure) so a caller (or a future
  retry-aware caller) can tell "the artifact commit itself failed" from "the
  commit succeeded but publishing it did not," even though this plan's
  runner wiring currently treats both the same way (folds into the existing
  ``ROLE_FAILED`` path).

Declaring the whole hierarchy in one place keeps the package's error surface
legible to a caller from the start.

:func:`~dark_factory.git.committed.read_committed` and
:func:`~dark_factory.git.committed.run_artifact_text` (plan 12-05, OBS-01)
are the one production ``git show`` read path -- see
``dark_factory.git.committed``'s module docstring for why a finished run's
artifact content can only be read this way.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ARTIFACT_COMMIT_SUBJECT_PREFIX",
    "ARTIFACT_EXCLUDE_PATHSPEC",
    "DIFF_PATCH_FILENAME",
    "GIT_ENV_ALLOWLIST",
    "GIT_IDENTITY_ENV",
    "GIT_PUSH_TOKEN_ENV_VAR",
    "MAX_DIFF_BYTES",
    "WIP_COMMIT_SUBJECT_PREFIX",
    "WORKTREE_PARENT_DIRNAME",
    "ArtifactScopeViolation",
    "DetachedHeadError",
    "GitCommandError",
    "GitError",
    "GitPushError",
    "WorktreePathError",
    "WriteScopeViolation",
    "assert_attached_head",
    "attempt_changed_artifact_paths",
    "attempt_changed_paths",
    "collect_pr_diff",
    "commit_run_artifacts",
    "dirty_paths",
    "enforce_artifact_scope",
    "enforce_write_scope",
    "ensure_worktree",
    "git_env",
    "head_sha",
    "is_dirty",
    "is_out_of_scope",
    "pr_changed_paths",
    "push_working_branch",
    "read_committed",
    "remove_worktree",
    "revert_paths",
    "run_artifact_text",
    "run_git",
    "validate_write_scope_patterns",
    "wip_commit_if_dirty",
    "working_branch_name",
    "worktree_path",
]


# The error hierarchy lives in its own leaf module, ``dark_factory.git.errors``
# (Plan 12-06), and is re-exported here unchanged -- every existing
# ``from dark_factory.git import GitError`` (or any sibling class) caller is
# unaffected; see ``errors.py``'s module docstring for why the split exists.
# Every submodule below now imports its own error classes directly from
# ``dark_factory.git.errors`` rather than the bare ``dark_factory.git``
# package name, so this block carries no circular-import ordering
# constraint and sorts alphabetically like any other import block.
from dark_factory.git.client import (
    GIT_ENV_ALLOWLIST,
    GIT_IDENTITY_ENV,
    git_env,
    run_git,
)
from dark_factory.git.committed import read_committed, run_artifact_text
from dark_factory.git.diff import (
    ARTIFACT_COMMIT_SUBJECT_PREFIX,
    ARTIFACT_EXCLUDE_PATHSPEC,
    DIFF_PATCH_FILENAME,
    GIT_PUSH_TOKEN_ENV_VAR,
    MAX_DIFF_BYTES,
    collect_pr_diff,
    commit_run_artifacts,
    pr_changed_paths,
    push_working_branch,
)
from dark_factory.git.errors import (
    ArtifactScopeViolation,
    DetachedHeadError,
    GitCommandError,
    GitError,
    GitPushError,
    WorktreePathError,
    WriteScopeViolation,
)
from dark_factory.git.lifecycle import (
    WIP_COMMIT_SUBJECT_PREFIX,
    assert_attached_head,
    dirty_paths,
    head_sha,
    is_dirty,
    wip_commit_if_dirty,
)
from dark_factory.git.scope import (
    attempt_changed_artifact_paths,
    attempt_changed_paths,
    enforce_artifact_scope,
    enforce_write_scope,
    is_out_of_scope,
    revert_paths,
    validate_write_scope_patterns,
)
from dark_factory.git.worktree import (
    WORKTREE_PARENT_DIRNAME,
    ensure_worktree,
    remove_worktree,
    working_branch_name,
    worktree_path,
)
