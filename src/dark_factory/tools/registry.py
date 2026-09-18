"""``ToolRegistry`` -- the one enforcement point every capability invocation
funnels through (D-01, TOOL-01, TOOL-03).

Mirrors :class:`~dark_factory.workers.registry.WorkerRegistry` /
:class:`~dark_factory.actions.registry.ActionRegistry` for the base map: a
plain ``dict`` from a capability name to its implementation callable.
:meth:`ToolRegistry.invoke` is the only way to reach an implementation --
this class deliberately exposes no accessor that returns a raw callable, so
"one enforcement point" is a structural property, not a convention a caller
could route around.

``invoke``'s order is load-bearing: the deny check runs *before* the
implementation lookup, so a denied invocation has zero side effects
regardless of what is registered or in what order (TOOL-03, edge:
ordering). Membership is exact-name set containment -- no prefix match, no
wildcard, no hierarchy, no default (TOOL-03, edge: adjacency).

``invoke`` opens no ``Session`` and constructs no lifecycle ORM row (WR-01,
D-06) -- ``tests/unit/test_single_mutation_path.py`` covers this module.

TOOL-02 extension seam: a new capability is added with one
``default_registry.register(name, fn)`` call at module bottom, mirroring
``workers/registry.py`` / ``actions/registry.py`` exactly -- zero change to
the orchestrator, the pipeline, or any role executor. Re-registering an
already-registered name replaces the earlier implementation rather than
keeping both (TOOL-02, edge: adjacency) -- this is a plain dict assignment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from dark_factory.artifacts.paths import resolve_under_run_root
from dark_factory.artifacts.store import read_artifact_text, write_artifact_text
from dark_factory.tools import CapabilityDeniedError, UnknownCapabilityError

__all__ = ["ToolRegistry", "default_registry"]


class ToolRegistry:
    """A plain ``dict`` lookup from a capability name to its implementation
    callable, gated by :meth:`invoke`'s per-call grant check."""

    def __init__(self) -> None:
        self._impls: dict[str, Callable[..., object]] = {}

    def register(self, name: str, fn: Callable[..., object]) -> None:
        """Bind ``name`` to ``fn``. Replaces any earlier implementation
        registered under the same name (TOOL-02, edge: adjacency)."""
        self._impls[name] = fn

    def __contains__(self, name: object) -> bool:
        """Membership without invocation -- ``config/loader.py`` validates a
        role's ``tools:`` entries against this, never :meth:`invoke`."""
        return name in self._impls

    def names(self) -> frozenset[str]:
        """Every registered capability name. Used by config-load validation
        and by the guard tests -- never returns a raw implementation."""
        return frozenset(self._impls)

    def invoke(
        self, role: str, capability: str, granted: Sequence[str], /, **kwargs: object
    ) -> object:
        """The deny-by-default gate (TOOL-01, TOOL-03, D-01).

        Order is load-bearing: the grant check runs first -- exact-name set
        membership against ``granted``, never a prefix or wildcard match --
        and only once a role is proven to hold the grant is the
        implementation looked up. A denied invocation therefore never
        reaches an implementation, registered or not.

        Raises :class:`~dark_factory.tools.CapabilityDeniedError` when
        ``capability`` is not in ``granted``, and
        :class:`~dark_factory.tools.UnknownCapabilityError` when it is
        granted but nothing is registered under that name -- a
        configuration bug, never an authorization decision, so it is never
        confused with a denial and never surfaces as a bare ``KeyError``.

        ``**kwargs`` is never interpolated into
        :class:`~dark_factory.tools.CapabilityDeniedError`'s message -- a
        capability argument can carry worker- or repo-supplied content, and
        this string reaches an event payload (threat T-06-04).
        """
        if capability not in set(granted):
            raise CapabilityDeniedError(role, capability, list(granted))
        try:
            impl = self._impls[capability]
        except KeyError:
            raise UnknownCapabilityError(capability) from None
        return impl(**kwargs)


def _artifacts_read(*, root: Path, relative_path: str) -> str:
    """Thin wrapper over
    :func:`~dark_factory.artifacts.store.read_artifact_text` -- the
    capability layer adds the permission check here in :meth:`ToolRegistry.invoke`;
    it does not reimplement the I/O, and this implementation must never
    re-check or second-guess the grant that already ran."""
    return read_artifact_text(root, relative_path)


def _artifacts_write(
    *, root: Path, role: str, filename: str, text: str
) -> tuple[str, str]:
    """Thin wrapper over
    :func:`~dark_factory.artifacts.store.write_artifact_text` -- same
    discipline as :func:`_artifacts_read`: the grant check already ran in
    :meth:`ToolRegistry.invoke`."""
    return write_artifact_text(root, role, filename, text)


def _repo_read(*, worktree: Path, relative_path: str) -> str:
    """Read ``relative_path`` under ``worktree`` as UTF-8 text (D-04).

    Resolves through :func:`~dark_factory.artifacts.paths.resolve_under_run_root`
    first -- the exact same containment guard the artifact-tier capabilities
    reuse (that function is root-agnostic: it only proves the resolved
    candidate stays inside whatever root it is handed), so a resolved path
    outside ``worktree`` raises :class:`~dark_factory.artifacts.ArtifactPathError`
    before any file is opened (threat T-06-07). The grant check already ran
    in :meth:`ToolRegistry.invoke`; this implementation must never re-check
    or second-guess it.
    """
    path = resolve_under_run_root(worktree, relative_path)
    return path.read_text("utf-8")


def _repo_search(
    *, worktree: Path, pattern: str, path_prefix: str = ""
) -> list[tuple[str, int, str]]:
    """A literal (never regex) scan of every file under
    ``<worktree>/<path_prefix>`` for lines containing ``pattern``, returning
    ``(relative_path, lineno, line)`` tuples (D-04).

    Never shells out -- pure Python file iteration -- and never accepts a
    caller-supplied regular expression, so a pathological pattern cannot
    become a denial-of-service. ``path_prefix`` (default ``""``, meaning the
    whole worktree) resolves through the same containment guard
    :func:`_repo_read` uses (threat T-06-07). Files that are not valid UTF-8
    text are skipped, not raised on -- a binary file in the tree is not a
    capability-layer failure.
    """
    scan_root = resolve_under_run_root(worktree, path_prefix)
    resolved_worktree = worktree.resolve()
    matches: list[tuple[str, int, str]] = []
    for file_path in sorted(scan_root.rglob("*")):
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = str(file_path.relative_to(resolved_worktree))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                matches.append((relative, lineno, line))
    return matches


def _repo_write(*, worktree: Path, relative_path: str, text: str) -> str:
    """Write ``text`` to ``relative_path`` under ``worktree``, returning the
    worktree-relative path written (D-04).

    Resolves through the same containment guard :func:`_repo_read` uses
    (threat T-06-09). ``repo.write`` and ``repo.write_tests`` are registered
    against this identical implementation -- they differ only in the
    *grant* a role needs to reach it, never in mechanism.
    :func:`~dark_factory.git.scope.enforce_write_scope` (Phase 5, ROLE-05)
    still decides *where* a granted write may land, enforced post-hoc by
    ``orchestrator/runner.py`` after the worker call returns -- this
    implementation neither consults nor duplicates that check.
    """
    path = resolve_under_run_root(worktree, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(worktree.resolve()))


def _shell_execute_not_yet_implemented(**_kwargs: object) -> object:
    """A registered-but-inert placeholder, mirroring the
    ``_NotYetImplementedWorker`` precedent in ``workers/registry.py``: its
    name resolves so ``load_effective_config`` validates the shipped
    QA/DEVELOPMENT roles' ``shell.execute`` entry, but calling it always
    raises. ``shell.execute``'s real body cannot exist without the
    credential-boundary env builder (D-11) -- plan 06-02 replaces this
    placeholder with the real implementation.
    """
    raise NotImplementedError("shell.execute capability lands in plan 06-02")


default_registry = ToolRegistry()
# TOOL-02 extension seam: a new capability is added with one
# ``default_registry.register(name, fn)`` call here -- zero change to the
# orchestrator, the pipeline, or any role executor.
default_registry.register("artifacts.read", _artifacts_read)
default_registry.register("artifacts.write", _artifacts_write)
default_registry.register("repo.read", _repo_read)
default_registry.register("repo.search", _repo_search)
default_registry.register("repo.write", _repo_write)
default_registry.register("repo.write_tests", _repo_write)
# ``shell.execute`` resolves for config-load validation (the shipped
# QA/DEVELOPMENT roles both name it) but is not yet callable -- see
# ``_shell_execute_not_yet_implemented``'s docstring. Plan 06-02 replaces
# this registration together with ``build_worker_env`` (D-11).
default_registry.register("shell.execute", _shell_execute_not_yet_implemented)
