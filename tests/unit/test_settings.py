"""Unit coverage for ``dark_factory.config.settings`` (Plan 01-03, Task 2).

Every value here is an obviously-fake placeholder set through ``monkeypatch``.
No test reads the real ``.env`` (``_env_file=None`` is passed everywhere) and no
real credential is ever constructed or asserted against.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# Obviously-fake, >=8-char placeholder secret values.
FAKE_DB_URL = "postgresql+psycopg://fakeuser:fakepass@fake-host.example/darkfactory"
FAKE_DB_URL_DIRECT = (
    "postgresql+psycopg://fakeuser:fakepass@fake-direct.example/darkfactory"
)
FAKE_GITHUB_TOKEN = "ghp_fake000000000000000000000000000000"


def _set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    values: dict[str, str | None] = {
        "DATABASE_URL": FAKE_DB_URL,
        "DATABASE_URL_DIRECT": FAKE_DB_URL_DIRECT,
        "GITHUB_TOKEN": None,
        # Plan 10-01 added this secret field to Settings -- clear it for the
        # same reason ANTHROPIC_API_KEY / COPILOT_GITHUB_TOKEN are cleared
        # below: a developer's own shell/`.env` could have it set for
        # unrelated reasons, and "defaults to None" tests must not depend
        # on the ambient environment they happen to run in.
        "GITHUB_WEBHOOK_SECRET": None,
        # Plan 11-01 added this secret field to Settings -- clear it for the
        # same reason: a developer's own shell/`.env` may legitimately hold
        # it for unrelated reasons, and "defaults to None" tests must not
        # depend on the ambient environment.
        "DISPATCH_GITHUB_TOKEN": None,
        "LOG_LEVEL": None,
        "LEASE_TTL_SECONDS": None,
        "LEASE_HEARTBEAT_SECONDS": None,
        # Phase 8 added these two secret fields to Settings; a developer's own
        # shell commonly has both set for personal claude/copilot CLI use,
        # unrelated to this repo -- clear them so "defaults to None" tests
        # don't depend on the ambient environment they happen to run in.
        "ANTHROPIC_API_KEY": None,
        "COPILOT_GITHUB_TOKEN": None,
    }
    values.update(overrides)
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_settings_and_get_settings_are_importable() -> None:
    from dark_factory.config.settings import Settings, get_settings

    assert Settings is not None
    assert callable(get_settings)


def test_required_urls_load_and_optional_token_defaults_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    settings = Settings(_env_file=None)

    assert settings.database_url.get_secret_value() == FAKE_DB_URL
    assert settings.database_url_direct.get_secret_value() == FAKE_DB_URL_DIRECT
    assert settings.github_token is None


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).log_level == "INFO"


def test_log_level_is_read_from_env_and_normalised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LOG_LEVEL="debug")
    assert Settings(_env_file=None).log_level == "DEBUG"


def test_log_level_typo_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LOG_LEVEL="VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_configure_logging_honours_the_configured_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LOG_LEVEL=WARNING`` must actually filter out an ``info`` event."""
    import structlog

    from dark_factory.config.settings import get_settings
    from tests.support.log_sink import real_log_sink

    _set_env(monkeypatch, LOG_LEVEL="WARNING")
    get_settings.cache_clear()
    try:
        with real_log_sink() as buffer:
            log = structlog.get_logger()
            log.info("should be filtered")
            log.warning("should be kept")
        output = buffer.getvalue()
    finally:
        get_settings.cache_clear()

    assert "should be filtered" not in output
    assert "should be kept" in output


def test_secrets_are_secretstr(monkeypatch: pytest.MonkeyPatch) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, GITHUB_TOKEN=FAKE_GITHUB_TOKEN)
    settings = Settings(_env_file=None)

    assert type(settings.database_url).__name__ == "SecretStr"
    assert type(settings.database_url_direct).__name__ == "SecretStr"
    assert type(settings.github_token).__name__ == "SecretStr"


def test_repr_contains_no_live_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, GITHUB_TOKEN=FAKE_GITHUB_TOKEN)
    settings = Settings(_env_file=None)

    rendered = repr(settings) + str(settings)
    assert FAKE_DB_URL not in rendered
    assert FAKE_DB_URL_DIRECT not in rendered
    assert FAKE_GITHUB_TOKEN not in rendered
    assert "fakepass" not in rendered


def test_missing_required_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_known_secret_values_maps_value_to_lowercase_field_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, GITHUB_TOKEN=FAKE_GITHUB_TOKEN)
    known = Settings(_env_file=None).known_secret_values()

    assert known[FAKE_DB_URL] == "database_url"
    assert known[FAKE_DB_URL_DIRECT] == "database_url_direct"
    assert known[FAKE_GITHUB_TOKEN] == "github_token"


def test_known_secret_values_omits_unset_optional_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    known = Settings(_env_file=None).known_secret_values()

    assert "github_token" not in known.values()
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in known.items())


def test_known_secret_values_omits_secret_shorter_than_8_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, GITHUB_TOKEN="short")
    known = Settings(_env_file=None).known_secret_values()

    assert "short" not in known
    assert "github_token" not in known.values()


def test_lease_settings_default_to_900_and_300(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    settings = Settings(_env_file=None)

    assert settings.lease_ttl_seconds == 900
    assert settings.lease_heartbeat_seconds == 300


def test_lease_settings_are_read_from_env_as_plain_ints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LEASE_TTL_SECONDS="2", LEASE_HEARTBEAT_SECONDS="1")
    settings = Settings(_env_file=None)

    assert settings.lease_ttl_seconds == 2
    assert settings.lease_heartbeat_seconds == 1
    assert type(settings.lease_ttl_seconds) is int
    assert type(settings.lease_heartbeat_seconds) is int


def test_heartbeat_equal_to_ttl_is_rejected_naming_both_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LEASE_TTL_SECONDS="10", LEASE_HEARTBEAT_SECONDS="10")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    message = str(exc_info.value)
    assert "lease_heartbeat_seconds" in message
    assert "lease_ttl_seconds" in message


def test_heartbeat_greater_than_ttl_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LEASE_TTL_SECONDS="5", LEASE_HEARTBEAT_SECONDS="9")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("bad_ttl", ["0", "-1"])
def test_non_positive_ttl_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bad_ttl: str
) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, LEASE_TTL_SECONDS=bad_ttl, LEASE_HEARTBEAT_SECONDS="0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_known_secret_values_never_contains_a_lease_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, GITHUB_TOKEN=FAKE_GITHUB_TOKEN)
    known = Settings(_env_file=None).known_secret_values()

    assert "lease_ttl_seconds" not in known.values()
    assert "lease_heartbeat_seconds" not in known.values()
    assert "900" not in known
    assert "300" not in known


def test_github_webhook_secret_defaults_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).github_webhook_secret is None


def test_known_secret_values_maps_github_webhook_secret_to_its_field_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    fake_webhook_secret = "whsec_fake0000000000000000000000000000"
    _set_env(monkeypatch, GITHUB_WEBHOOK_SECRET=fake_webhook_secret)
    known = Settings(_env_file=None).known_secret_values()

    assert known[fake_webhook_secret] == "github_webhook_secret"


def test_known_secret_values_omits_unset_github_webhook_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    known = Settings(_env_file=None).known_secret_values()

    assert "github_webhook_secret" not in known.values()


def test_dispatch_github_token_defaults_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).dispatch_github_token is None


def test_known_secret_values_maps_dispatch_github_token_to_its_field_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    fake_dispatch_token = "dispatch_fake0000000000000000000000000"
    _set_env(monkeypatch, DISPATCH_GITHUB_TOKEN=fake_dispatch_token)
    known = Settings(_env_file=None).known_secret_values()

    assert known[fake_dispatch_token] == "dispatch_github_token"


def test_known_secret_values_omits_unset_dispatch_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    known = Settings(_env_file=None).known_secret_values()

    assert "dispatch_github_token" not in known.values()


def test_anthropic_api_key_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).anthropic_api_key is None


def test_worker_timeout_seconds_defaults_to_1800(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).worker_timeout_seconds == 1800


def test_worker_timeout_seconds_is_read_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, WORKER_TIMEOUT_SECONDS="1")
    settings = Settings(_env_file=None)
    assert settings.worker_timeout_seconds == 1
    assert type(settings.worker_timeout_seconds) is int


@pytest.mark.parametrize("bad_timeout", ["0", "-1"])
def test_non_positive_worker_timeout_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bad_timeout: str
) -> None:
    from pydantic import ValidationError

    from dark_factory.config.settings import Settings

    _set_env(monkeypatch, WORKER_TIMEOUT_SECONDS=bad_timeout)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_returns_a_cached_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import get_settings

    _set_env(monkeypatch)
    get_settings.cache_clear()
    try:
        first = get_settings()
        second = get_settings()
        assert first is second
    finally:
        get_settings.cache_clear()
