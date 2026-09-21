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
import glob
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import structlog

from dark_factory.git import ArtifactScopeViolation, WriteScopeViolation
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

# The single source of D-14's "missing/empty write_scope means zero
# tolerance" default (WR-03). Both ``config/loader.py``'s
# ``RolePermissions.write_scope`` (a role whose config declares no
# ``permissions:`` block) and ``orchestrator/runner.py``'s
# ``_role_definition`` fallback (a legacy bare-string snapshot entry with no
# ``permissions`` key at all) read this constant rather than each spelling
# out their own ``[]`` literal -- a future edit to the default can no longer
# silently diverge between the two call sites.
DEFAULT_WRITE_SCOPE: tuple[str, ...] = ()

# The single source of the "artifacts.write" capability's spelling (plan
# 08-05). ``enforce_artifact_scope`` reads this rather than a bare string
# literal so the capability name cannot silently diverge from the
# ``tools:`` grant vocabulary ``NATIVE_TOOL_CONTRACT`` and every role YAML
# already use.
ARTIFACTS_WRITE_CAPABILITY = "artifacts.write"

__all__ = [
    "ARTIFACTS_WRITE_CAPABILITY",
    "DEFAULT_WRITE_SCOPE",
    "attempt_changed_artifact_paths",
    "attempt_changed_paths",
    "enforce_artifact_scope",
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
    diff, so it is out of scope for enforcement (A-05-15). The run's own
    ``artifacts/`` subtree is not left unenforced by this exclusion, though
    -- see :func:`attempt_changed_artifact_paths`, the sibling function
    plan 08-05 added specifically to cover it (CR-01).
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


def attempt_changed_artifact_paths(worktree: Path, run_id: UUID) -> list[str]:
    """The sorted, de-duplicated set of paths this attempt changed under the
    run's own ``.dark-factory/runs/<run_id>/artifacts/`` tree (plan 08-05,
    CR-01).

    :func:`attempt_changed_paths` answers a different question --
    "what repository *source* did this attempt change" -- and deliberately
    excludes the whole gitignored run tree by pathspec (A-05-15) so that
    question's answer stays silent about artifact content by design. This
    function answers "what *artifact* content did this attempt change",
    covers only the run's ``artifacts/`` subtree, and exists precisely
    because the first question's answer never sees it.

    Exactly two ``run_git`` invocations, both limited to the
    ``.dark-factory/runs/<run_id>/artifacts`` pathspec (relative to
    ``worktree`` -- git pathspecs are repository-relative, and an absolute
    path here would work by accident rather than by contract, the same
    reasoning :func:`~dark_factory.git.diff.commit_run_artifacts` already
    records):

    * ``git diff --name-only HEAD`` -- tracked modifications and deletions
      of a prior role's already-committed artifact content;
    * ``git ls-files --others --ignored --exclude-standard`` -- untracked
      files, **including ignored ones**. This is the deliberate divergence
      from :func:`attempt_changed_paths`'s sibling invocation (which passes
      ``--exclude-standard`` with no ``--ignored`` and so never reports a
      gitignored path): the entire run tree is gitignored, so a newly
      created file inside another role's artifact subtree is, by
      definition, an *ignored* untracked file, and only the
      ignored-inclusive form of ``ls-files`` can see it at all.

    Neither invocation walks a directory: no ``os.walk``, no ``rglob``, no
    ``iterdir``, no ``glob`` module call anywhere in this function -- git is
    the enumerator, exactly as it is for every other change set in this
    project. A worktree whose run ``artifacts/`` directory does not exist at
    all, or a run tree in which nothing under ``artifacts/`` changed, both
    naturally return ``[]``: an unmatched pathspec is not an error to either
    git subcommand, so no existence check is needed before issuing either
    call.

    This function never reports a path under the same run's
    ``verification/``, ``logs/`` or ``input/`` directories, and never
    reports a path outside the run tree -- the pathspec is scoped to
    ``artifacts/`` alone, not the whole run root.
    """
    pathspec = f".dark-factory/runs/{run_id}/artifacts"
    tracked = run_git(["diff", "--name-only", "HEAD", "--", pathspec], cwd=worktree)
    untracked = run_git(
        ["ls-files", "--others", "--ignored", "--exclude-standard", "--", pathspec],
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


def revert_paths(
    worktree: Path, paths: Sequence[str], *, include_ignored: bool = False
) -> None:
    """Revert exactly ``paths`` -- never a whole-tree reset, never an
    untargeted clean, never a checkout of the current directory (D-13,
    RESEARCH Pitfall 2).

    ``include_ignored`` (plan 08-05, CR-01) governs only the absent-from-
    ``HEAD`` branch's ``git clean`` invocation, adding ``-x`` when true. The
    default (``False``) preserves :func:`enforce_write_scope`'s existing
    behaviour byte-for-byte -- a role's ``write_scope`` violation lives
    entirely under tracked source paths, never under the gitignored run
    tree. The flag exists because :func:`enforce_artifact_scope` reverts
    paths under ``.dark-factory/runs/<run_id>/artifacts/``, which
    ``.gitignore`` excludes wholesale: a file a role created inside another
    role's artifact subtree is therefore an *ignored* untracked file, and
    a plain ``git clean --force`` silently leaves an ignored path on disk
    while still exiting 0 -- appearing to have succeeded. Verified
    empirically against a real repository: a single ``-x`` flag is
    sufficient to remove a specific ignored file nested several directories
    below an ignored parent when the path is passed as an explicit
    pathspec (as it always is here) -- git does not additionally require
    the recurse-into-untracked-directories flag (``-d``) for this shape,
    because the pathspec names the file itself rather than the directory
    containing it.

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
            clean_args = ["clean", "--force"]
            if include_ignored:
                clean_args.append("-x")
            clean_args += ["--", path]
            run_git(clean_args, cwd=worktree)
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


def enforce_artifact_scope(
    worktree: Path,
    run_id: UUID,
    *,
    role: str,
    attempt: int,
    granted: Sequence[str],
) -> None:
    """Enumerate this attempt's changes under the run's own ``artifacts/``
    tree, revert every path outside ``role``'s own ``artifacts/<role>/``
    subtree, and raise :class:`~dark_factory.git.ArtifactScopeViolation`
    naming all of them (plan 08-05, CR-01).

    Structurally mirrors :func:`enforce_write_scope`: enumerate, select
    violations, revert every one of them, then raise naming the complete
    set; return ``None`` with nothing reverted when the set is empty.

    The allowed-pattern list is a single-element list holding the run's own
    ``artifacts/<role>/**`` pattern when ``granted`` contains
    :data:`ARTIFACTS_WRITE_CAPABILITY`, and the empty list otherwise -- then
    handed straight to :func:`is_out_of_scope`. This is deliberate, not an
    implementation shortcut: an empty pattern list already means zero
    tolerance under D-14, so a role with no ``artifacts.write`` grant gets
    deny-by-default over the *entire* run artifacts tree -- including its
    own subtree -- for free, with no branch anywhere in this function ever
    special-casing the empty list to mean the opposite.

    ``role`` is passed through :func:`glob.escape` before being interpolated
    into the allowed pattern: the pattern is consumed by
    :func:`fnmatch.fnmatchcase`, so an unescaped metacharacter in a role
    name would widen the boundary this function exists to narrow rather
    than confine it to the literal role name. This is a targeted hardening
    of *this* pattern's own construction only -- it is not WR-01's
    repository-wide role-name path-traversal validation, which remains an
    open, separate finding this plan does not attempt.

    Every violating path is reverted (via :func:`revert_paths` with
    ``include_ignored=True`` -- the run's ``artifacts/`` tree is gitignored,
    so a role-created foreign file is an ignored untracked file) before the
    exception is raised, exactly like :func:`enforce_write_scope`: the
    caller must never be able to accept a failure that left an
    out-of-role-subtree artifact change on disk. The raised message names
    the role, the attempt, the complete violating path list, and -- when the
    role holds no :data:`ARTIFACTS_WRITE_CAPABILITY` grant at all -- that
    fact explicitly, so an operator reading the failure can tell which of
    the two boundaries (narrowed-to-own-subtree vs. zero-tolerance) was
    crossed.
    """
    changed = attempt_changed_artifact_paths(worktree, run_id)
    if ARTIFACTS_WRITE_CAPABILITY in granted:
        allowed = [f".dark-factory/runs/{run_id}/artifacts/{glob.escape(role)}/**"]
    else:
        allowed = []
    violations = sorted(path for path in changed if is_out_of_scope(path, allowed))
    if not violations:
        return None
    revert_paths(worktree, violations, include_ignored=True)
    no_grant_note = (
        ""
        if ARTIFACTS_WRITE_CAPABILITY in granted
        else f" (role holds no {ARTIFACTS_WRITE_CAPABILITY!r} grant)"
    )
    raise ArtifactScopeViolation(
        f"role {role} attempt {attempt} wrote outside its own artifact "
        f"subtree{no_grant_note}: {violations!r}"
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
