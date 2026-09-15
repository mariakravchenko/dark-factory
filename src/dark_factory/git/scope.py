"""``write_scope`` matching, its config-time validation, and the targeted
revert of an out-of-scope change (ROLE-05, D-12, D-13, D-14).

No database access anywhere in this module -- every function takes an
explicit ``worktree``/pattern argument and returns a plain value or raises a
typed error, exactly like ``git/lifecycle.py`` and ``git/diff.py`` beside it
(WR-01). This is what lets ``actions/builtins.py`` stay git-only if it ever
dispatches here, and what lets ``orchestrator/runner.py`` call
:func:`enforce_write_scope` directly and fold its exception into the existing
``ROLE_FAILED``/``RUN_FAILED`` shape.

``write_scope`` is an **authorization control**, not a formatting nicety:
every path this module is handed is treated as untrusted input (it came from
``git diff``/``git ls-files`` output describing a worker's own writes) and
every pattern in a role's ``write_scope`` is treated as a boundary
definition the worker itself never sees and cannot influence. D-14's
polarity is the load-bearing fact a future reader must not miss: an empty
``write_scope`` means **zero tolerance**, not "unrestricted" -- a path
matches none of zero patterns, so every path is a violation, and no branch
in this module ever special-cases the empty list to mean the opposite.
Matching uses ``fnmatch.fnmatchcase``, never ``pathlib``'s path-matching API
-- research proved the latter is right-anchored by path-component count with
no true recursive ``**`` on this project's Python floor, producing both a
false positive against a decoy directory and a false negative against deep
nesting (see ``05-RESEARCH.md`` Pitfall 1).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path

import structlog

from dark_factory.git import WriteScopeViolation
from dark_factory.git.client import run_git
from dark_factory.git.diff import ARTIFACT_EXCLUDE_PATHSPEC

_log = structlog.get_logger(__name__)

# The exact substring git emits on stderr when ``git rm --cached`` is asked
# to remove a path with no index entry at all -- the expected, no-op-shaped
# failure ``revert_paths`` deliberately tolerates for a role-created file
# that was never staged. Any other non-zero exit is an unexpected failure
# (permission error, corrupted index entry, a git-level conflict) and is
# logged rather than silently swallowed (WR-01).
_RM_CACHED_NOT_STAGED_MARKER = "did not match any files"

__all__ = [
    "attempt_changed_paths",
    "enforce_write_scope",
    "is_out_of_scope",
    "revert_paths",
    "validate_write_scope_patterns",
]


def is_out_of_scope(path: str, write_scope: Sequence[str]) -> bool:
    """``True`` iff ``path`` matches none of ``write_scope``'s patterns (D-12, D-14).

    Matching is ``fnmatch.fnmatchcase`` -- fully left-anchored, with no
    path-separator concept, so a single ``*`` and ``**`` behave identically
    and both cross ``/`` boundaries. This is what makes ``src/**`` match
    ``src/sub/deep/app.py`` (deep nesting, a true match) while rejecting
    ``tests/fixtures/src/evil.py`` (a decoy directory whose *trailing*
    components happen to look like a match) -- the exact two failure modes
    the right-anchored ``pathlib`` matching API gets wrong. ``fnmatchcase``,
    not the case-normalising ``fnmatch.fnmatch``, so behaviour never depends
    on the host filesystem's case sensitivity.

    D-14's zero tolerance falls out of this expression for free: an empty
    ``write_scope`` makes ``any(...)`` over an empty iterable ``False``, so
    ``not False`` is ``True`` -- a violation -- for every path. **No
    early-return branch for the empty-list case may ever be added here.**
    The intuitive ``if not write_scope: return False`` ("nothing configured,
    so nothing is restricted") is exactly the inversion D-14 forbids: it
    would silently grant write access to every role -- BA and ARCHITECTURE
    included -- whose ``write_scope`` is the deliberate empty list.
    """
    return not any(fnmatch.fnmatchcase(path, pattern) for pattern in write_scope)


def attempt_changed_paths(worktree: Path) -> list[str]:
    """The sorted, de-duplicated set of repository paths this attempt changed
    (A-05-14).

    Exactly two git invocations, both sharing
    :data:`~dark_factory.git.diff.ARTIFACT_EXCLUDE_PATHSPEC` so Dark
    Factory's own machinery is never itself subject to write-scope
    enforcement:

    * ``git diff --name-only HEAD`` -- tracked modifications, staged
      changes and deletions, relative to the last commit;
    * ``git ls-files --others --exclude-standard`` -- untracked files that
      are not gitignored.

    Bare paths come back from both invocations, with no rename arrow and no
    status prefix to strip -- unlike ``git status --porcelain``, which is
    why this function does not parse porcelain output.

    This set is precise because it is exactly this attempt's *uncommitted*
    repository changes at the moment of the check: plan 05-02's recovery
    pass made the worktree clean at this role's entry, and plan 05-03's
    artifact commit removed this role's own run-tree writes immediately
    before this check runs -- so nothing here was left by an earlier role
    or by Dark Factory's own bookkeeping. A gitignored file the role
    produced is deliberately absent: by construction it is not part of any
    diff, so it is out of scope for enforcement (A-05-15).
    """
    tracked = run_git(
        ["diff", "--name-only", "HEAD", "--", ".", ARTIFACT_EXCLUDE_PATHSPEC],
        cwd=worktree,
    )
    untracked = run_git(
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            ".",
            ARTIFACT_EXCLUDE_PATHSPEC,
        ],
        cwd=worktree,
    )
    paths = {line.strip() for line in tracked.stdout.splitlines() if line.strip()}
    paths.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    return sorted(paths)


def _resolve_in_worktree(worktree: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` against ``worktree`` and reject any escape.

    Mirrors ``artifacts/paths.py::resolve_under_run_root``'s T-04-01
    containment guard exactly: resolve the candidate, resolve the root, and
    raise :class:`~dark_factory.git.WriteScopeViolation` naming both when the
    candidate is not relative to the root -- reject, never clamp. In
    practice ``git diff``/``git ls-files`` run inside a worktree Dark
    Factory itself created will never emit an escaping path, but
    ``write_scope`` is an authorization boundary and this project treats
    every path crossing a trust boundary the same way. Called on every path
    before any revert or delete acts on it.
    """
    candidate = (worktree / relative_path).resolve()
    resolved_root = worktree.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise WriteScopeViolation(
            f"write-scope path escapes worktree {resolved_root}: "
            f"{relative_path!r} resolved to {candidate}"
        )
    return candidate


def revert_paths(worktree: Path, paths: Sequence[str]) -> None:
    """Revert exactly ``paths`` -- never a whole-tree reset, never an
    untargeted clean, never a checkout of the current directory (D-13,
    RESEARCH Pitfall 2).

    Every path is containment-checked via :func:`_resolve_in_worktree`
    before anything acts on it. The revert mechanism then branches on
    whether the path exists in ``HEAD`` (``git cat-file -e HEAD:<path>``,
    ``check=False`` so a non-zero exit is read as "absent" rather than
    raised):

    * **present in HEAD** -- ``git restore --source=HEAD --staged
      --worktree -- <path>`` returns both the index and the working tree to
      the committed content in one call.
    * **absent from HEAD** -- the role created this file; there is nothing
      to restore *to*, and ``git restore --source=HEAD`` fails outright with
      a pathspec error on a path git has no HEAD version of. Any staged
      index entry is cleared first with ``git rm --cached --force --quiet``
      (``check=False``: a path that was never staged makes this a
      no-op-shaped failure, not a real error), then the file itself is
      removed with ``git clean --force``. A non-zero ``git rm --cached`` exit
      whose stderr does not match the expected "pathspec did not match any
      files" text is an *unexpected* failure (permission error, corrupted
      index entry, a git-level conflict) and is logged via
      ``write_scope.revert_rm_cached_unexpected_failure`` rather than
      silently swallowed alongside the expected case -- ``git clean`` is
      still attempted immediately after either way, since a real ``rm
      --cached`` failure is not itself something ``git clean`` could resolve
      or avoid (WR-01).

    Branching on HEAD membership is mandatory: a single-mechanism revert
    (always ``restore``, or always ``clean``) leaves every newly-created
    violating file on disk -- and possibly still staged -- while appearing
    to have succeeded on the tracked-edit case. Acting on exactly the
    supplied paths and nothing else is what keeps an enforcement mechanism
    from being a worse outcome than the violation it corrects: it must never
    destroy a role's legitimate in-scope work alongside the violation.

    The containment check (:func:`_resolve_in_worktree`) is applied per-path
    inside a ``try``/``except`` rather than left to propagate directly: a
    single escaping path (e.g. a worker-created symlink that resolves
    outside the worktree) must never abort the revert of every *other*,
    perfectly revertible violation still queued after it in ``paths``. Every
    escape is collected and raised together only after every non-escaping
    path has been reverted -- this is what actually delivers
    :func:`enforce_write_scope`'s docstring promise that "every violating
    path is reverted before the exception is raised," rather than only the
    ones that happen to sort before the first escape.
    """
    escapes: list[str] = []
    for path in paths:
        try:
            _resolve_in_worktree(worktree, path)
        except WriteScopeViolation:
            escapes.append(path)
            continue
        in_head = run_git(["cat-file", "-e", f"HEAD:{path}"], cwd=worktree, check=False)
        if in_head.returncode == 0:
            run_git(
                ["restore", "--source=HEAD", "--staged", "--worktree", "--", path],
                cwd=worktree,
            )
        else:
            rm_cached = run_git(
                ["rm", "--cached", "--force", "--quiet", "--", path],
                cwd=worktree,
                check=False,
            )
            if (
                rm_cached.returncode != 0
                and _RM_CACHED_NOT_STAGED_MARKER not in rm_cached.stderr
            ):
                _log.warning(
                    "write_scope.revert_rm_cached_unexpected_failure",
                    path=path,
                    returncode=rm_cached.returncode,
                    stderr=rm_cached.stderr.strip(),
                )
            run_git(["clean", "--force", "--", path], cwd=worktree)
    if escapes:
        raise WriteScopeViolation(
            f"write-scope paths escape worktree {worktree.resolve()}: {escapes!r}"
        )


def enforce_write_scope(
    worktree: Path, *, write_scope: Sequence[str], role: str, attempt: int
) -> None:
    """Enumerate this attempt's changes, revert every out-of-scope path, and
    raise :class:`~dark_factory.git.WriteScopeViolation` naming all of them
    (D-13).

    Every changed path is checked -- this never short-circuits on the first
    violation -- so a caught violation always names the *complete* set
    rather than the first one encountered (an incomplete error payload would
    make an operator fix one violation, re-run, and discover a second one
    that was there all along). When any violation exists, every violating
    path is reverted **before** the exception is raised: the caller must
    never be able to accept a failure that left an out-of-scope change on
    disk. Returns ``None`` with nothing reverted when the collection is
    empty.
    """
    changed = attempt_changed_paths(worktree)
    violations = sorted(path for path in changed if is_out_of_scope(path, write_scope))
    if not violations:
        return None
    revert_paths(worktree, violations)
    raise WriteScopeViolation(
        f"role {role} attempt {attempt} wrote outside its configured "
        f"write_scope {list(write_scope)!r}: {violations!r}"
    )


def validate_write_scope_patterns(patterns: Sequence[str], *, source: str) -> None:
    """Raise :class:`ValueError` naming ``source`` and the offending pattern
    for a malformed ``write_scope`` entry (A-05-13, fail-loud config
    validation).

    ``fnmatch`` has no syntax-error class of its own -- ``fnmatch.translate``
    accepts essentially any string -- so "malformed" has to be *defined*
    rather than detected. This defines it as any of four shapes that are
    either meaningless against the relative paths git reports, or an attempt
    to describe something outside the worktree:

    * empty or whitespace-only;
    * beginning with ``/`` (absolute);
    * beginning with ``./``;
    * containing a ``..`` path segment (split on ``/``).

    Anything else is accepted -- this is deliberately permissive beyond
    those four cases, since ``fnmatch`` itself imposes no further
    constraint. Called from ``config/loader.py::load_effective_config`` while
    resolving each role, so a bad pattern is rejected before any ``runs`` row
    is created, never silently at diff time.
    """
    for pattern in patterns:
        if not pattern.strip():
            raise ValueError(
                f"{source}: write_scope pattern is empty or whitespace-only: {pattern!r}"
            )
        if pattern.startswith("/"):
            raise ValueError(
                f"{source}: write_scope pattern must not be absolute: {pattern!r}"
            )
        if pattern.startswith("./"):
            raise ValueError(
                f"{source}: write_scope pattern must not begin with './': {pattern!r}"
            )
        if ".." in pattern.split("/"):
            raise ValueError(
                f"{source}: write_scope pattern must not contain a '..' segment: {pattern!r}"
            )
