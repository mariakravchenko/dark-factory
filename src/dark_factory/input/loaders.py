"""Source loaders -- normalize every origin to one :class:`NormalizedTask` (INTAKE-05).

Once :func:`load` returns, nothing downstream knows or cares where the task came
from. Phase 1 ships only the ``text:`` loader for real; ``spec:`` (Phase 4) and
``github:`` (Phase 10) classify successfully but their loaders raise a clean
:class:`SourceNotSupportedError` naming the phase that will implement them.

Loader selection is a ``{SourceKind: loader}`` mapping, not a chain of
conditionals on the kind: adding a kind without a matching loader fails at import
time (the key-set assertion in the tests), never silently at runtime.
"""

from __future__ import annotations

from collections.abc import Callable

from dark_factory.domain.task import NormalizedTask
from dark_factory.input.resolver import SourceKind, UnresolvableSourceError

__all__ = ["SourceNotSupportedError", "load"]

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


def _load_spec(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError(
        "spec: sources are not supported until Phase 4 (spec loader)"
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
