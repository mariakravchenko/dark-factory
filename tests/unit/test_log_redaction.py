"""The log-path half of Plan 01-03, Task 3.

These assertions run against a **real** ``StringIO`` sink with the production
structlog processor chain active (via ``tests.support.log_sink``). They must not
use ``structlog.testing.capture_logs`` — it bypasses the processor chain, so the
redaction processor would never run and this suite would pass green while the
real log file leaks (RESEARCH Pitfall 5).

``redact()`` has TWO INDEPENDENT DEFENCES and this file must keep them visibly
separate (debug session ``log-sink-conditional-override-unpinned``):

* the **pattern** layer — the compiled D-15 table, which matches on *shape*; and
* the **known-secret** layer — ``_scrub_known``, exact-value substitution of
  whatever ``Settings.known_secret_values()`` reports, which exists precisely to
  catch credentials that match no shape at all.

Every secret assertion in this file originally used ONE pattern-shaped fixture,
so the pattern layer silently rescued all of them: commenting out
``_scrub_known`` entirely left this file at 4 passed, and a test *named*
``..._known_secret_value_...`` was in fact proving nothing about known secrets.
Each fixture below therefore declares which layer it exercises and **asserts
that precondition** via ``redact(value, known_secrets={})`` — with no known
secrets only the pattern layer runs, so an unchanged return proves the value is
invisible to patterns and a changed return proves it is not. Those guards are
the thing that stops the masking from re-forming the next time ``_PATTERNS`` is
broadened. If you add a fixture here, give it a layer and a guard.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.unit

_DB_ENV_VARS = ("DATABASE_URL", "DATABASE_URL_DIRECT")

# PATTERN-LAYER fixture: carries embedded credentials, so `_PATTERNS[0]`
# (`postgres(ql)?(+\w+)?://[^\s@]+@\S+`) matches it on shape alone, with or
# without it being a registered known secret.
FAKE_LIVE_DB_URL = "postgresql+psycopg://real:l1vepass@prod-host.example/darkfactory"

# KNOWN-SECRET-LAYER fixture: a credential-free DSN (password supplied
# out-of-band via `PGPASSWORD`) — a perfectly realistic Postgres URL that
# `_PATTERNS[0]` CANNOT match, because that row requires an `@`. It also trips no
# other row: no `github_pat_`/`gh[porsu]_` prefix, no 40-or-64-char hex run for
# `_HEX_TOKEN`, no bearer header, and no `_SENSITIVE_KEYS` word followed by
# `:`/`=` for the generic key=value rule. Comfortably over the 8-character floor
# below which `Settings.known_secret_values()` skips a value. Nothing but
# exact-value substitution can remove this string from a log line.
FAKE_OPAQUE_DB_URL = "postgresql://df-pin-host.invalid:5432/df_pin_credential_free_db"

# Preserved-value sentinels for the `real_log_sink` env-handling matrix. Same
# credential-free shape, one per variable so a helper that cross-wires the two
# cannot pass.
SENTINEL_DB_URLS = {
    name: f"postgresql://df-sentinel-{name.lower()}.invalid:5432/df_sentinel_db"
    for name in _DB_ENV_VARS
}


def test_this_module_uses_the_real_sink_not_structlog_testing() -> None:
    """Architectural: the real-sink helper is imported; structlog.testing is not.

    Checked against the parsed AST (not raw text) so this file's own prose about
    why ``structlog.testing.capture_logs`` is banned does not trip the check.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))

    imports_real_sink = any(
        isinstance(node, ast.ImportFrom) and node.module == "tests.support.log_sink"
        for node in ast.walk(tree)
    )
    assert imports_real_sink

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                not alias.name.startswith("structlog.testing") for alias in node.names
            )
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("structlog.testing")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == "structlog" and node.attr == "testing")


def test_pattern_shaped_secret_in_log_event_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATTERN layer: a token-shaped value in free text is redacted by shape.

    The ``ghp_`` token here is deliberately NOT a configured secret, so only
    ``_PATTERNS`` can remove it — the guard below proves that.
    """
    from dark_factory.events.redaction import redact

    leaked = "ghp_0123456789012345678901234567890123456789"
    assert redact(leaked, known_secrets={}) != leaked, (
        "fixture must be pattern-matched for this test to prove the pattern layer"
    )

    monkeypatch.setenv("DATABASE_URL", FAKE_LIVE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_LIVE_DB_URL)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    import structlog

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        with real_log_sink() as buffer:
            structlog.get_logger().info("run started", task=f"please use {leaked}")
        output = buffer.getvalue()
    finally:
        get_settings.cache_clear()

    assert output.strip(), "expected a log line"
    assert leaked not in output
    assert "[redacted:github_token]" in output
    # the line is valid JSON (JSONRenderer active) -> newlines can't forge lines
    json.loads(output.strip().splitlines()[-1])


def test_pattern_shaped_database_url_from_env_never_reaches_the_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATTERN layer, end to end: a credential-bearing DSN is scrubbed by shape.

    RENAMED. This was ``test_live_known_secret_value_never_reaches_the_sink``,
    a name that claimed the KNOWN-SECRET property it does not test: the fixture
    is pattern-shaped, so ``_PATTERNS[0]`` redacts it whether or not it is a
    registered secret — measured, by deleting ``_scrub_known`` and watching this
    assertion still pass. The guard below now states that honestly, and
    ``test_known_secret_value_no_pattern_can_rescue_never_reaches_the_sink``
    covers the layer this test never did.
    """
    from dark_factory.events.redaction import redact

    assert redact(FAKE_LIVE_DB_URL, known_secrets={}) != FAKE_LIVE_DB_URL, (
        "FAKE_LIVE_DB_URL is the PATTERN-layer fixture and must stay "
        "pattern-matched; if a _PATTERNS change made it immune, this test no "
        "longer proves the pattern layer"
    )

    monkeypatch.setenv("DATABASE_URL", FAKE_LIVE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_LIVE_DB_URL)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    import structlog

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        with real_log_sink() as buffer:
            structlog.get_logger().info("config loaded", where=FAKE_LIVE_DB_URL)
        output = buffer.getvalue()
    finally:
        get_settings.cache_clear()

    assert "l1vepass" not in output
    assert FAKE_LIVE_DB_URL not in output
    assert "[redacted:" in output


def test_known_secret_value_no_pattern_can_rescue_never_reaches_the_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KNOWN-SECRET layer, end to end — the composition no other test covers.

    ``tests/unit/test_redaction.py`` pins exact-value substitution on ``redact()``
    directly; this file pins the structlog wiring. Until this test existed,
    nothing pinned the INTERSECTION: environment variable ->
    ``Settings.known_secret_values()`` -> ``_redaction_processor`` -> real sink,
    for a value the pattern table cannot touch.

    It is also the end-to-end killer for ``real_log_sink``'s absence-conditional
    (``tests/support/log_sink.py``). An unconditional override would replace this
    value with ``_FAKE_DATABASE_URL`` before ``configure_logging`` ran, so the
    sentinel would never enter ``known_secrets``, no pattern would catch it, and
    it would appear here verbatim. ``DATABASE_URL_DIRECT`` is deliberately left
    ABSENT so the mixed case is the one exercised: a helper that supplies both
    vars whenever *either* is missing also fails this test.
    """
    from dark_factory.events.redaction import redact

    assert redact(FAKE_OPAQUE_DB_URL, known_secrets={}) == FAKE_OPAQUE_DB_URL, (
        "FAKE_OPAQUE_DB_URL must remain invisible to every _PATTERNS row, or this "
        "test silently degrades into another pattern-layer test — exactly the "
        "masking that debug session log-sink-conditional-override-unpinned fixed"
    )

    monkeypatch.setenv("DATABASE_URL", FAKE_OPAQUE_DB_URL)
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    import structlog

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        with real_log_sink() as buffer:
            structlog.get_logger().info("config loaded", where=FAKE_OPAQUE_DB_URL)
        output = buffer.getvalue()
    finally:
        get_settings.cache_clear()

    assert output.strip(), "expected a log line"
    assert FAKE_OPAQUE_DB_URL not in output
    # the label is the lowercased Settings field name (known_secret_values())
    assert "[redacted:database_url]" in output
    json.loads(output.strip().splitlines()[-1])


def test_sink_helper_restores_previous_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_LIVE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_LIVE_DB_URL)

    import structlog

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        before = structlog.get_config()
        with real_log_sink():
            pass
        after = structlog.get_config()
    finally:
        get_settings.cache_clear()

    assert after == before


@pytest.mark.parametrize(
    "preset",
    [
        pytest.param(("DATABASE_URL", "DATABASE_URL_DIRECT"), id="both-preset"),
        pytest.param(("DATABASE_URL",), id="only-pooled-preset"),
        pytest.param(("DATABASE_URL_DIRECT",), id="only-direct-preset"),
        pytest.param((), id="neither-preset"),
    ],
)
def test_sink_helper_supplies_only_absent_database_vars_and_restores(
    preset: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``real_log_sink`` fills in ONLY what is missing, and puts it all back.

    The absence-conditional in ``tests/support/log_sink.py`` is what lets a test
    set ``DATABASE_URL`` to a value it then asserts is scrubbed. Making that
    override unconditional was a SURVIVING MUTANT: the whole suite stayed green,
    because every test looked only at the sink's text and the pattern layer
    redacted either URL identically. This test closes that blind spot by
    observing ``os.environ`` and ``Settings`` from INSIDE the context, which no
    test previously did — and it needs no redaction at all, so the two properties
    that got entangled stay decomposed.

    All four cells of the presence matrix are covered on purpose. The mixed cells
    are the load-bearing ones: they fail an all-or-nothing helper that supplies
    both vars whenever either is absent, which a per-variable ``supplied`` list
    correctly does not. ``neither-preset`` is the original G-11-3 property —
    ``Settings`` must be constructible in a database-free process.
    """
    from dark_factory.config.settings import get_settings

    for name in _DB_ENV_VARS:
        if name in preset:
            monkeypatch.setenv(name, SENTINEL_DB_URLS[name])
        else:
            monkeypatch.delenv(name, raising=False)
    expect_supplied = tuple(name for name in _DB_ENV_VARS if name not in preset)

    get_settings.cache_clear()
    try:
        with real_log_sink():
            # Constructible in every cell — including with nothing preset.
            settings = get_settings()

            for name in preset:
                assert os.environ[name] == SENTINEL_DB_URLS[name], (
                    f"{name} was clobbered by real_log_sink; the absence-"
                    f"conditional in tests/support/log_sink.py is what prevents "
                    f"this, and a test that sets {name} on purpose depends on it"
                )
                loaded = getattr(settings, name.lower()).get_secret_value()
                assert loaded == SENTINEL_DB_URLS[name], (
                    f"Settings.{name.lower()} loaded {loaded!r}, not the preset "
                    f"sentinel — the value a test set never reached Settings"
                )

            for name in expect_supplied:
                supplied_value = os.environ.get(name)
                assert supplied_value, f"{name} was absent and must be supplied"
                assert supplied_value not in SENTINEL_DB_URLS.values()

        for name in preset:
            assert os.environ[name] == SENTINEL_DB_URLS[name], (
                f"{name} was not left as the test set it after the context exited"
            )
        for name in expect_supplied:
            assert name not in os.environ, (
                f"{name} was supplied by real_log_sink and must be removed again"
            )
    finally:
        get_settings.cache_clear()
