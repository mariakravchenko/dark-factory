"""Unit coverage for ``input.loaders`` (INTAKE-05).

The text loader is the only real loader in Phase 1; ``spec:`` / ``github:``
loaders raise :class:`SourceNotSupportedError` naming the implementing phase.
Dispatch is a mapping keyed by every :class:`SourceKind` member.
"""

from __future__ import annotations

import pytest

from dark_factory.input import loaders
from dark_factory.input.loaders import SourceNotSupportedError, load
from dark_factory.input.resolver import SourceKind, UnresolvableSourceError

pytestmark = pytest.mark.unit


def test_text_loader_builds_a_normalized_task_from_the_body() -> None:
    task = load(SourceKind.TEXT, "add a health endpoint")
    assert task.source_kind == "text"
    assert task.source_ref is None
    assert task.body == "add a health endpoint"
    assert task.title == "add a health endpoint"


def test_text_loader_strips_surrounding_quotes_and_whitespace() -> None:
    task = load(SourceKind.TEXT, '  "wrapped in quotes"  ')
    assert task.body == "wrapped in quotes"


def test_text_loader_title_is_the_first_line_truncated() -> None:
    body = "x" * 200 + "\nsecond line"
    task = load(SourceKind.TEXT, body)
    assert task.title == "x" * 120
    assert task.body == body


@pytest.mark.parametrize("locator", ["", "   ", "\n\t  \n"])
def test_text_loader_refuses_empty_or_whitespace_body(locator: str) -> None:
    with pytest.raises(UnresolvableSourceError):
        load(SourceKind.TEXT, locator)


def test_spec_loader_names_phase_4() -> None:
    with pytest.raises(SourceNotSupportedError) as excinfo:
        load(SourceKind.SPEC, "./task.md")
    assert "Phase 4" in str(excinfo.value)


def test_github_loader_names_phase_10() -> None:
    with pytest.raises(SourceNotSupportedError) as excinfo:
        load(SourceKind.GITHUB, "152")
    assert "Phase 10" in str(excinfo.value)


def test_loader_mapping_covers_every_source_kind() -> None:
    assert set(loaders._LOADERS) == set(SourceKind)
