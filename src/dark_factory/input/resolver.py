"""Source classification -- pure prefix matching, no side effects (INTAKE-04).

``classify`` is the very first thing that happens to an operator's ``argv`` and
it runs *before anything is persisted*. INTAKE-04 makes "no file read, no repo
inspection, no GitHub call, no network, no run creation" a hard requirement, not
a style preference: a classifier with a side effect is a side effect that cannot
be undone when the input turns out to be garbage.

The classification table maps the three literal prefixes to their
:class:`SourceKind`. No prefix is a proper prefix of another, so the order in
which candidates are tested cannot change the result. An unmatched or empty
input raises :class:`UnresolvableSourceError` -- the CLI turns that into exit 2
with nothing written.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["SourceKind", "UnresolvableSourceError", "classify"]


class SourceKind(StrEnum):
    """The task-source families Dark Factory understands. Value equals name."""

    TEXT = "text"
    SPEC = "spec"
    GITHUB = "github"


class UnresolvableSourceError(ValueError):
    """Raised when a raw source string matches none of the known prefixes."""


# Literal prefix -> kind. Deliberately a module-level constant, never mutated:
# ``classify`` is a pure function of its argument and holds no state a prior call
# could have changed.
_PREFIXES: dict[str, SourceKind] = {
    "text:": SourceKind.TEXT,
    "spec:": SourceKind.SPEC,
    "github:": SourceKind.GITHUB,
}


def classify(raw: str) -> tuple[SourceKind, str]:
    """Return ``(kind, remainder)`` for a ``text:`` / ``spec:`` / ``github:`` string.

    Pure string work: no I/O of any kind and no run creation. ``remainder`` is
    everything after the matched prefix, verbatim -- quote stripping and body
    validation belong to the loader, not here. Prefix matching is on code points
    (``str.startswith``), so a leading byte-order mark or leading whitespace
    means the string is *not* a recognised source rather than being silently
    accepted.
    """
    for prefix, kind in _PREFIXES.items():
        if raw.startswith(prefix):
            return kind, raw[len(prefix) :]
    raise UnresolvableSourceError(f"cannot classify source: {raw!r}")
