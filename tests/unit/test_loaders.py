"""Unit coverage for ``input.loaders`` (INTAKE-05).

``text:`` (Phase 1) and ``spec:`` (Phase 4) are real loaders; ``github:``
still raises :class:`SourceNotSupportedError` naming Phase 10. Dispatch is a
mapping keyed by every :class:`SourceKind` member.
"""

from __future__ import annotations

from pathlib import Path

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


def test_spec_loader_builds_a_normalized_task_from_the_file(tmp_path: Path) -> None:
    spec_file = tmp_path / "task.md"
    spec_file.write_text(
        "Ship a health endpoint\n\nAdd a /health route.\n", encoding="utf-8"
    )

    task = load(SourceKind.SPEC, str(spec_file))

    assert task.source_kind == "spec"
    assert task.source_ref == str(spec_file.resolve())
    assert task.title == "Ship a health endpoint"
    assert task.body == "Ship a health endpoint\n\nAdd a /health route."
    assert task.metadata == {}


def test_spec_loader_strips_a_leading_markdown_heading_marker(tmp_path: Path) -> None:
    spec_file = tmp_path / "task.md"
    spec_file.write_text("## Ship a health endpoint\n\nBody text.\n", encoding="utf-8")

    task = load(SourceKind.SPEC, str(spec_file))

    assert task.title == "Ship a health endpoint"


def test_spec_loader_truncates_the_title_at_title_max_len(tmp_path: Path) -> None:
    spec_file = tmp_path / "task.md"
    spec_file.write_text("x" * 200 + "\nsecond line\n", encoding="utf-8")

    task = load(SourceKind.SPEC, str(spec_file))

    assert task.title == "x" * loaders._TITLE_MAX_LEN
    assert task.body == "x" * 200 + "\nsecond line"


def test_spec_loader_resolves_a_relative_locator_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_file = tmp_path / "task.md"
    spec_file.write_text("Relative task\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    task = load(SourceKind.SPEC, "./task.md")

    assert task.source_ref == str(spec_file.resolve())


def test_spec_loader_expands_a_tilde_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    spec_file = tmp_path / "task.md"
    spec_file.write_text("Home task\n", encoding="utf-8")

    task = load(SourceKind.SPEC, "~/task.md")

    assert task.source_ref == str(spec_file.resolve())


def test_spec_loader_refuses_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"

    with pytest.raises(UnresolvableSourceError) as excinfo:
        load(SourceKind.SPEC, str(missing))

    assert str(missing.resolve()) in str(excinfo.value)


def test_spec_loader_refuses_an_empty_or_whitespace_only_file(tmp_path: Path) -> None:
    spec_file = tmp_path / "task.md"
    spec_file.write_text("   \n\t\n  ", encoding="utf-8")

    with pytest.raises(UnresolvableSourceError) as excinfo:
        load(SourceKind.SPEC, str(spec_file))

    assert str(spec_file.resolve()) in str(excinfo.value)


def test_github_loader_names_phase_10() -> None:
    with pytest.raises(SourceNotSupportedError) as excinfo:
        load(SourceKind.GITHUB, "152")
    assert "Phase 10" in str(excinfo.value)


def test_loader_mapping_covers_every_source_kind() -> None:
    assert set(loaders._LOADERS) == set(SourceKind)
