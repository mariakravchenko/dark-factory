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


def test_set_and_frozenset_are_redacted_elementwise_as_a_list() -> None:
    """IN-07: a set of secret strings must not pass through untouched."""
    from dark_factory.events.redaction import redact

    out = redact({FAKE_DB_URI}, known_secrets={})
    assert out == ["[redacted:database_url]"]

    out_frozen = redact(frozenset({"password=hunter2"}), known_secrets={})
    assert out_frozen == ["password=[redacted:password]"]


def test_bytes_credential_is_decoded_redacted_and_re_encoded() -> None:
    """IN-07: a bytes credential is scrubbed, not returned verbatim."""
    from dark_factory.events.redaction import redact

    out = redact(f"connect {FAKE_DB_URI}".encode(), known_secrets={})
    assert isinstance(out, bytes)
    assert b"hunter2" not in out
    assert b"[redacted:database_url]" in out


def test_non_utf8_bytes_pass_through_unchanged() -> None:
    from dark_factory.events.redaction import redact

    raw = b"\xff\xfe\x00secret"
    assert redact(raw, known_secrets={}) == raw


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


def test_quoted_sensitive_value_keeps_its_closing_quote() -> None:
    """IN-06: the kv rule captures an optional opening quote on the value and
    requires a matching closing quote; the replacement must re-emit both so a
    log line like ``... token="abc" ...`` stays balanced."""
    from dark_factory.events.redaction import redact

    out = redact('the header token="abc123def" was sent', known_secrets={})
    assert out == 'the header token="[redacted:token]" was sent'
    assert "abc123def" not in out


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


@pytest.mark.parametrize(
    "prefix",
    ["commit", "commit:", "sha =", "revision #", "git commit"],
)
def test_forty_hex_in_a_git_object_context_survives(prefix: str) -> None:
    from dark_factory.events.redaction import redact

    text = f"{prefix} {SHA40} is the fix"
    assert redact(text, known_secrets={}) == text


@pytest.mark.parametrize(
    "key", ["commit", "sha", "revision", "commit_sha", "wip_commit_sha"]
)
def test_forty_hex_value_under_a_git_object_dict_key_survives(key: str) -> None:
    """Regression guard (05-02 db-tier round-trip): `redact()` recurses through
    a Mapping value-by-value with no visibility into its own key name, so a
    bare `{"commit": "<40hex>"}` payload value used to be redacted even though
    its key literally says `commit` -- exactly the `WIP_COMMIT_CREATED` event
    payload shape `_persist_wip_commit` writes."""
    from dark_factory.events.redaction import redact

    out = redact({key: SHA40, "role": "ARCHITECTURE"}, known_secrets={})
    assert out[key] == SHA40
    assert out["role"] == "ARCHITECTURE"


def test_git_object_key_exemption_does_not_weaken_other_patterns() -> None:
    """The dict-key exemption applies ONLY to the bare hex-token pattern --
    a real secret shape under a `commit`-named key must still be redacted."""
    from dark_factory.events.redaction import redact

    out = redact({"commit": FAKE_DB_URI}, known_secrets={})
    assert out["commit"] == "[redacted:database_url]"

    out2 = redact({"commit": FAKE_GHP}, known_secrets={})
    assert out2["commit"] == "[redacted:github_token]"


def test_unrelated_dict_key_still_redacts_a_bare_forty_hex_value() -> None:
    from dark_factory.events.redaction import redact

    out = redact({"note": SHA40}, known_secrets={})
    assert out["note"] == "[redacted:github_token]"


# --- `checksum` key exemption (SHA-256 digest false positive) ----------------
#
# These four cases are ONE regression guard and must be read together: the
# first proves a real artifact checksum survives, the other three prove the
# exemption that lets it survive did not become a credential-leak path. A fix
# that satisfies only the first has converted a safe over-redaction into an
# unsafe under-redaction. Do not delete one without the others.


def test_sha256_checksum_under_a_checksum_dict_key_survives() -> None:
    """Regression guard: `ArtifactRef.checksum` is a SHA-256 hex digest --
    exactly 64 hex characters -- so `_HEX_TOKEN` used to mangle it into
    `[redacted:github_token]` in the `WorkerResult.model_dump()` blob stored in
    `role_executions.result` (every artifact-producing attempt) and
    `role_executions.error` (a FAILED attempt). Uses a REAL digest, not a
    hand-built 64-char string, so the test tracks `artifacts.paths.checksum`'s
    actual output shape rather than an assumption about it."""
    from dark_factory.artifacts.paths import checksum
    from dark_factory.events.redaction import redact

    digest = checksum(b"an artifact body")
    assert len(digest) == 64  # guards the premise: SHA-256 collides with _HEX_TOKEN

    out = redact(
        {"type": "implementation_summary.json", "path": "x/y.json", "checksum": digest},
        known_secrets={},
    )
    assert out["checksum"] == digest


def test_checksum_key_exemption_does_not_weaken_other_patterns() -> None:
    """NEGATIVE POLARITY. The `checksum` exemption suppresses the bare
    hex-token rule ONLY -- every real credential SHAPE parked under a
    `checksum`-named key must still be redacted."""
    from dark_factory.events.redaction import redact

    for value, expected in (
        (FAKE_DB_URI, "[redacted:database_url]"),
        (FAKE_GHP, "[redacted:github_token]"),
        (FAKE_GH_PAT, "[redacted:github_token]"),
    ):
        out = redact({"checksum": value}, known_secrets={})
        assert out["checksum"] == expected, value

    bearer = redact({"checksum": FAKE_BEARER}, known_secrets={})
    assert "eyJfake.token.value-0000" not in bearer["checksum"]


def test_known_secret_is_still_scrubbed_from_a_checksum_field() -> None:
    """NEGATIVE POLARITY, the load-bearing one. A configured LIVE secret whose
    value happens to be 64 lowercase hex characters -- i.e. one that passes the
    digest shape gate exactly -- must still be removed from a `checksum` field.
    `_scrub_known` runs before the pattern table and is never exempted, which
    is what keeps this fix from being a credential leak: `Settings` is the one
    declared source of live secret values, so known-value substitution is the
    authoritative defence, not the shape heuristic."""
    from dark_factory.events.redaction import redact

    hex64_secret = "deadbeef" * 8  # 64 lowercase hex chars -- passes the shape gate
    assert len(hex64_secret) == 64

    out = redact(
        {"checksum": hex64_secret},
        known_secrets={hex64_secret: "github_token"},
    )
    assert out["checksum"] == "[redacted:github_token]"
    assert hex64_secret not in out["checksum"]


@pytest.mark.parametrize(
    ("value", "why"),
    [
        (SHA40, "40 hex is not a SHA-256 digest -- gate requires exactly 64"),
        ("DEADBEEF" * 8, "hexdigest() never emits uppercase"),
        ("DeadBeef" * 8, "hexdigest() never emits mixed case"),
        (
            f"sha256:{'a' * 64}",
            "gate is anchored; a digest inside prose is not a digest",
        ),
        (f"{'a' * 64} {SHA40}", "a digest plus a second hex run is not a bare digest"),
    ],
)
def test_checksum_key_exemption_is_shape_gated(value: str, why: str) -> None:
    """NEGATIVE POLARITY, boundary neighbours. The exemption is granted on the
    VALUE's shape, not on the key name alone, so each near-miss of
    `\\A[0-9a-f]{64}\\Z` under a `checksum` key is still redacted. Without the
    shape gate a `checksum` key would be an unconditional hex-token bypass."""
    from dark_factory.events.redaction import redact

    out = redact({"checksum": value}, known_secrets={})
    assert "[redacted:" in out["checksum"], why


def test_checksum_exemption_does_not_propagate_into_a_nested_container() -> None:
    """The gate inspects the value directly, so a list or dict under a
    `checksum` key is NOT a digest and earns no exemption -- the conservative
    direction. Guards against a future refactor that moves the gate to the key
    check alone and silently exempts whole subtrees."""
    from dark_factory.events.redaction import redact

    out = redact({"checksum": ["a" * 64]}, known_secrets={})
    assert out["checksum"] == ["[redacted:github_token]"]


def test_sha256_digest_under_an_unrelated_key_is_still_redacted() -> None:
    """The exemption is scoped to `_CHECKSUM_KEYS`; the same digest under any
    other key stays redacted, so this fix did not globally retire the 64-hex
    arm of `_HEX_TOKEN`."""
    from dark_factory.events.redaction import redact

    digest = "a" * 64
    out = redact({"note": digest, "summary": f"saw {digest}"}, known_secrets={})
    assert out["note"] == "[redacted:github_token]"
    assert digest not in out["summary"]


def test_worker_result_dump_round_trip_preserves_checksums_and_redacts_secrets() -> (
    None
):
    """End-to-end at the ACTUAL blast-radius shape: the `outcome` dict
    `runner.py` builds with `result.model_dump(mode="json")` and hands to
    `redact()` on both the `role_executions.result` and
    `role_executions.error` write paths (`mutations.py`). Asserts both
    polarities in one payload -- every artifact checksum survives while a
    credential leaked into the same blob's prose does not."""
    from dark_factory.artifacts.paths import checksum
    from dark_factory.domain.worker import ArtifactRef, WorkerResult, WorkerResultStatus
    from dark_factory.events.redaction import redact

    digests = [checksum(b"first body"), checksum(b"second body")]
    result = WorkerResult(
        status=WorkerResultStatus.FAILED,
        summary="run aborted",
        artifacts=[
            ArtifactRef(
                type="implementation_summary.json", path="a.json", checksum=digests[0]
            ),
            ArtifactRef(type="verdict.json", path="b.json", checksum=digests[1]),
        ],
        error=f"push rejected; credential {FAKE_GHP} was refused",
    )

    out = redact(result.model_dump(mode="json"), known_secrets={})

    assert [a["checksum"] for a in out["artifacts"]] == digests
    assert FAKE_GHP not in out["error"]
    assert "[redacted:github_token]" in out["error"]


def test_forty_hex_after_detached_head_at_phrase_survives() -> None:
    """Regression guard (05-02 db-tier round-trip): the D-08 detached-HEAD
    error message reads "...has a detached HEAD at <sha>; refusing..." -- the
    word immediately before the hex is "at", not "commit"/"sha"/"revision",
    so the original word list missed this legitimate git-object mention."""
    from dark_factory.events.redaction import redact

    text = f"worktree /tmp/wt has a detached HEAD at {SHA40}; refusing to enter"
    assert redact(text, known_secrets={}) == text


def test_bare_at_without_head_still_redacts() -> None:
    """The `head at` exemption is scoped narrowly: a bare "at" preposition with
    no "head" immediately before it must not exempt a real token."""
    from dark_factory.events.redaction import redact

    out = redact(f"the build failed at {SHA40} today", known_secrets={})
    assert SHA40 not in out
    assert "[redacted:github_token]" in out


def test_forty_hex_in_github_context_is_redacted() -> None:
    from dark_factory.events.redaction import redact

    out = redact(f"see the github mirror {SHA40} today", known_secrets={})
    assert SHA40 not in out
    assert "[redacted:github_token]" in out


def test_bare_forty_hex_pat_without_github_context_is_redacted() -> None:
    """WR-06: a 40-hex classic PAT in prose -- no nearby "github", space-separated
    so the key=value rule does not fire either -- must still be scrubbed."""
    from dark_factory.events.redaction import redact

    for text in (
        f"auth failed with {SHA40} today",
        f"key: {SHA40}",
        f"token was {SHA40}.",
    ):
        out = redact(text, known_secrets={})
        assert SHA40 not in out, text
        assert "[redacted:" in out


def test_db_uri_with_special_characters_in_password_is_fully_redacted() -> None:
    """WR-06: a password containing raw `/`, `:` and `+` must not defeat the URI
    rule and leak the whole connection string."""
    from dark_factory.events.redaction import redact

    uri = "postgresql+psycopg://u:p/a:s+s.w0rd@host:5432/db"
    out = redact(f"dsn is {uri} ok", known_secrets={})
    assert "[redacted:database_url]" in out
    assert "p/a:s+s.w0rd" not in out
    assert "host:5432" not in out
    assert out == "dsn is [redacted:database_url] ok"


def test_base64_bearer_token_is_fully_redacted() -> None:
    """WR-06: a standard-base64 bearer value (with `+` `/` `=`) must be consumed
    whole, not leave a trailing fragment in the sink."""
    from dark_factory.events.redaction import redact

    token = "aB3+cD/4eF5gH6==" * 2
    out = redact(f"Authorization: Bearer {token}", known_secrets={})
    assert "[redacted:authorization]" in out
    assert token not in out
    assert "==" not in out.replace("[redacted:authorization]", "")


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
