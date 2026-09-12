"""Source loaders -- normalize every origin to one :class:`NormalizedTask` (INTAKE-05).

Once :func:`load` returns, nothing downstream knows or cares where the task came
from. ``text:`` (Phase 1) and ``spec:`` (Phase 4) are real loaders; ``github:``
(Phase 10) classifies successfully but its loader raises a clean not-supported
error naming the phase that will implement it.

Loader selection is a ``{SourceKind: loader}`` mapping, not a chain of
conditionals on the kind: adding a kind without a matching loader fails at import
time (the key-set assertion in the tests), never silently at runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dark_factory.domain.task import NormalizedTask
from dark_factory.input.resolver import SourceKind, UnresolvableSourceError

__all__ = ["load"]

_TITLE_MAX_LEN = 120


class SourceNotSupportedError(NotImplementedError):
    """Raised by a loader for a source kind whose implementation lands in a later phase."""


def _load_text(locator: str) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a plain-text task body.

    Surrounding double quotes and outer whitespace are stripped so
    ``run text:"do the thing"`` and ``run text:do the thing`` produce the same
    task. An empty or whitespace-only body is refused with
    :class:`UnresolvableSourceError` -- the CLI turns that into exit 2 with
    nothing persisted.
    """
    body = locator.strip().strip('"')
    if not body:
        raise UnresolvableSourceError("text: task body is empty")
    title = body.splitlines()[0][:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="text",
        source_ref=None,
        title=title,
        body=body,
        metadata={},
    )


def _strip_heading_marker(first_line: str) -> str:
    """Strip a leading Markdown heading marker (``#``, ``##``, ...) and the
    whitespace around it, so ``"# Ship a health endpoint"`` and
    ``"Ship a health endpoint"`` produce the same title."""
    stripped = first_line.lstrip()
    while stripped.startswith("#"):
        stripped = stripped[1:]
    return stripped.strip()


def _load_spec(locator: str) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a Markdown spec file on disk.

    Mirrors :func:`_load_text`'s shape: the locator's outer whitespace and
    surrounding double quotes are stripped before it is treated as a path. A
    relative locator resolves against the current working directory; ``~``
    expands. A locator naming a non-file, or a file whose body is empty or
    whitespace-only, is refused with :class:`UnresolvableSourceError` naming the
    resolved path -- the CLI already maps that to exit 2 with nothing persisted.
    """
    raw_path = locator.strip().strip('"')
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()

    if not resolved.is_file():
        raise UnresolvableSourceError(f"spec: file not found: {resolved}")

    body = resolved.read_text(encoding="utf-8").strip()
    if not body:
        raise UnresolvableSourceError(f"spec: file is empty: {resolved}")

    first_line = body.splitlines()[0]
    title = _strip_heading_marker(first_line)[:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="spec",
        source_ref=str(resolved),
        title=title,
        body=body,
        metadata={},
    )


def _load_github(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError(
        "github: sources are not supported until Phase 10 (issue intake)"
    )


_LOADERS: dict[SourceKind, Callable[[str], NormalizedTask]] = {
    SourceKind.TEXT: _load_text,
    SourceKind.SPEC: _load_spec,
    SourceKind.GITHUB: _load_github,
}


def load(kind: SourceKind, locator: str) -> NormalizedTask:
    """Dispatch to the loader registered for ``kind`` and return its task."""
    return _LOADERS[kind](locator)
