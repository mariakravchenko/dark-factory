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
        "LOG_LEVEL": None,
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
