"""Unit coverage for ``dark_factory.events.redaction`` (Plan 01-03, Task 3).

One case per ``<behavior>`` bullet plus one per pattern-table row. Every secret
here is a hand-built FAKE value; no real credential appears in this file.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# --- Fake fixtures -------------------------------------------------------------

FAKE_DB_URI = "postgresql+psycopg://user:hunter2@host:5432/db"
FAKE_GHP = "ghp_0123456789012345678901234567890123456789"  # ghp_ + 40 alnum
FAKE_GH_PAT = "github_pat_11ABCDE0aBcDeFgHiJkL_mnopqrstuvwx1234567890"
FAKE_BEARER = "Authorization: Bearer eyJfake.token.value-0000"
SHA40 = "0123456789abcdef0123456789abcdef01234567"  # 40 hex, a plausible git SHA
DOC_STYLE_URI = "postgres://user:pass@host/db"  # documentation example in prose


# --- Recursion / scalar passthrough -----------------------------------------


def test_non_string_scalars_pass_through_unchanged() -> None:
    from dark_factory.events.redaction import redact

    for scalar in (123, 4.5, True, False, None):
        assert redact(scalar, known_secrets={}) == scalar


def test_recurses_into_nested_mappings_and_sequences() -> None:
    from dark_factory.events.redaction import redact

    payload = {
        "outer": {"uri": FAKE_DB_URI},
        "items": [f"password={'hunter2'}", {"note": "clean"}],
        "tup": ("plain", FAKE_DB_URI),
    }
    out = redact(payload, known_secrets={})

    assert out["outer"]["uri"] == "[redacted:database_url]"
    assert out["items"][0] == "password=[redacted:password]"
    assert out["items"][1]["note"] == "clean"
    assert out["tup"] == ["plain", "[redacted:database_url]"]  # tuple -> list


def test_tuple_becomes_list() -> None:
    from dark_factory.events.redaction import redact

    assert redact(("a", "b"), known_secrets={}) == ["a", "b"]


# --- Pattern-table rows -----------------------------------------------------


def test_postgres_uri_with_credentials_is_labelled() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"connect to {FAKE_DB_URI} now", known_secrets={})
    assert "[redacted:database_url]" in out
    assert "hunter2" not in out


def test_github_classic_token_shape_is_labelled() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"token {FAKE_GHP} end", known_secrets={})
    assert "[redacted:github_token]" in out
    assert FAKE_GHP not in out


def test_github_fine_grained_pat_is_labelled() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"use {FAKE_GH_PAT}", known_secrets={})
    assert "[redacted:github_token]" in out
    assert FAKE_GH_PAT not in out


def test_authorization_bearer_header_is_labelled() -> None:
    from dark_factory.events.redaction import redact

    out = redact(FAKE_BEARER, known_secrets={})
    assert "[redacted:authorization]" in out
    assert "eyJfake.token.value-0000" not in out


def test_sensitive_key_value_pair_is_labelled() -> None:
    from dark_factory.events.redaction import redact

    out = redact("password=hunter2", known_secrets={})
    assert out == "password=[redacted:password]"
    assert "hunter2" not in out


def test_dict_key_match_replaces_value_of_any_type() -> None:
    from dark_factory.events.redaction import redact

    out = redact({"password": 12345, "api_key": ["a", "b"], "ok": 1}, known_secrets={})
    assert out["password"] == "[redacted:password]"
    assert out["api_key"] == "[redacted:api_key]"
    assert out["ok"] == 1


def test_bare_commit_sha_in_prose_survives() -> None:
    from dark_factory.events.redaction import redact

    text = f"the fix landed in commit {SHA40} last week"
    assert redact(text, known_secrets={}) == text


def test_forty_hex_in_github_context_is_redacted() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"see the github mirror {SHA40} today", known_secrets={})
    assert SHA40 not in out
    assert "[redacted:github_token]" in out


# --- Known-value substitution ---------------------------------------------


def test_known_secret_value_is_substituted_even_without_a_pattern() -> None:
    from dark_factory.events.redaction import redact

    secret = "s3cr3t-not-a-pattern-value-1234"
    out = redact(f"the value is {secret}!", known_secrets={secret: "api_key"})
    assert out == "the value is [redacted:api_key]!"


def test_known_secret_shorter_than_8_chars_is_ignored() -> None:
    from dark_factory.events.redaction import redact

    out = redact("keep short", known_secrets={"short": "token"})
    assert out == "keep short"


def test_longer_known_value_wins_over_a_shorter_substring() -> None:
    from dark_factory.events.redaction import redact

    known = {"abcdefgh": "token", "abcdefgh-longer-secret": "database_url"}
    out = redact("value abcdefgh-longer-secret here", known_secrets=known)
    assert "[redacted:database_url]" in out
    assert "abcdefgh-longer-secret" not in out


# --- patterns=False scope split (D-18) ----------------------------------------


def test_patterns_false_keeps_doc_style_uri_but_scrubs_known_value() -> None:
    from dark_factory.events.redaction import redact, scrub_known_values

    live = "postgresql+psycopg://real:live@prod-host.example/db"
    text = f"Support a {DOC_STYLE_URI} connection string; not {live}"

    out = redact(text, known_secrets={live: "database_url"}, patterns=False)
    assert DOC_STYLE_URI in out  # legitimate prose survives
    assert live not in out
    assert "[redacted:database_url]" in out

    assert scrub_known_values(text, known_secrets={live: "database_url"}) == out


def test_patterns_true_would_redact_the_same_doc_style_uri() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"tolerate a {DOC_STYLE_URI} value", known_secrets={})
    assert DOC_STYLE_URI not in out
    assert "[redacted:database_url]" in out


# --- Idempotency ----------------------------------------------------------


IDEMPOTENCY_CORPUS = [
    f"connect {FAKE_DB_URI}",
    f"token {FAKE_GHP}",
    f"pat {FAKE_GH_PAT}",
    FAKE_BEARER,
    "password=hunter2",
    f"the github ref {SHA40} here",
    {"password": "x", "nested": {"database_url": FAKE_DB_URI}},
    ["password=hunter2", {"token": "abc"}],
    "nothing sensitive at all",
]


@pytest.mark.parametrize("value", IDEMPOTENCY_CORPUS)
def test_redact_is_idempotent(value: object) -> None:
    from dark_factory.events.redaction import redact

    known = {"s3cr3t-value-abcdefgh": "api_key"}
    once = redact(value, known_secrets=known)
    twice = redact(once, known_secrets=known)
    assert twice == once


@pytest.mark.parametrize("value", IDEMPOTENCY_CORPUS)
def test_scrub_known_values_is_idempotent(value: object) -> None:
    from dark_factory.events.redaction import scrub_known_values

    known = {"s3cr3t-value-abcdefgh": "api_key"}
    once = scrub_known_values(value, known_secrets=known)
    twice = scrub_known_values(once, known_secrets=known)
    assert twice == once
