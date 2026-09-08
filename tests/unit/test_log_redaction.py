"""The log-path half of Plan 01-03, Task 3.

These assertions run against a **real** ``StringIO`` sink with the production
structlog processor chain active (via ``tests.support.log_sink``). They must not
use ``structlog.testing.capture_logs`` — it bypasses the processor chain, so the
redaction processor would never run and this suite would pass green while the
real log file leaks (RESEARCH Pitfall 5).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.unit

FAKE_LIVE_DB_URL = "postgresql+psycopg://real:l1vepass@prod-host.example/darkfactory"


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
    monkeypatch.setenv("DATABASE_URL", FAKE_LIVE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_LIVE_DB_URL)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    import structlog

    from dark_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        with real_log_sink() as buffer:
            structlog.get_logger().info(
                "run started",
                task="please use ghp_0123456789012345678901234567890123456789",
            )
        output = buffer.getvalue()
    finally:
        get_settings.cache_clear()

    assert output.strip(), "expected a log line"
    assert "ghp_0123456789012345678901234567890123456789" not in output
    assert "[redacted:github_token]" in output
    # the line is valid JSON (JSONRenderer active) -> newlines can't forge lines
    json.loads(output.strip().splitlines()[-1])


def test_live_known_secret_value_never_reaches_the_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
