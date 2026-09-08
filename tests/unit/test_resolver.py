"""Unit coverage for ``input.resolver.classify`` (INTAKE-04).

The no-I/O and no-run-creation properties are proved *positively*: ``open``,
``socket.socket``, the session factory and ``create_run`` are each patched to
raise on any call, and ``classify`` is asserted to still return normally.
"""

from __future__ import annotations

import socket

import pytest

from dark_factory.input import resolver
from dark_factory.input.resolver import SourceKind, UnresolvableSourceError, classify

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("text:add a health endpoint", (SourceKind.TEXT, "add a health endpoint")),
        ("spec:./tasks/one.md", (SourceKind.SPEC, "./tasks/one.md")),
        ("github:152", (SourceKind.GITHUB, "152")),
        ("text:", (SourceKind.TEXT, "")),
    ],
)
def test_classify_returns_kind_and_remainder(
    raw: str, expected: tuple[SourceKind, str]
) -> None:
    assert classify(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "notaprefix:hello",
        "TEXT:upper",
        "  text:leading space",
        "\ttext:leading tab",
        "\ntext:leading newline",
        "just some words",
    ],
)
def test_classify_rejects_unrecognised_or_prefixed_input(raw: str) -> None:
    with pytest.raises(UnresolvableSourceError):
        classify(raw)


def test_classify_rejects_a_leading_byte_order_mark() -> None:
    bom = chr(0xFEFF)
    with pytest.raises(UnresolvableSourceError):
        classify(bom + "text:body after a BOM")


def test_classify_does_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("classify performed I/O")

    monkeypatch.setattr("builtins.open", boom)
    monkeypatch.setattr(socket, "socket", boom)
    from dark_factory.persistence import engine

    monkeypatch.setattr(engine, "new_session", boom, raising=False)

    for prefix in ("text:", "spec:", "github:"):
        assert classify(prefix + "body")[1] == "body"


def test_classify_creates_no_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from dark_factory.persistence import mutations

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("classify created a run")

    monkeypatch.setattr(mutations, "create_run", boom)

    assert classify("text:still fine") == (SourceKind.TEXT, "still fine")


def test_classify_is_pure_and_holds_no_mutable_state() -> None:
    before = dict(resolver._PREFIXES)
    first = classify("text:hello")
    second = classify("text:hello")
    classify("github:1")
    assert first == second
    assert dict(resolver._PREFIXES) == before


def test_no_prefix_is_a_proper_prefix_of_another() -> None:
    prefixes = list(resolver._PREFIXES)
    for a in prefixes:
        for b in prefixes:
            if a is not b:
                assert not a.startswith(b)
