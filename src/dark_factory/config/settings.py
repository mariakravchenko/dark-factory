"""The single choke point for infrastructure secrets (Plan 01-03, Task 2).

``Settings`` is the *one* declared source of live secret values. ``redact()``
(``dark_factory.events.redaction``) asks this object — via
:meth:`Settings.known_secret_values` — for the literal strings it must scrub
everywhere they appear (D-16). A credential that is not loaded here is never
substituted, so any run persisted while a secret was unregistered has already
leaked it into Neon; keep every infrastructure credential on this object.

Discipline, not decoration: the ``SecretStr`` wrappers keep values out of reprs
and tracebacks, but nothing in this module may log, echo, format or interpolate
a settings value.
"""

from __future__ import annotations

import functools

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed infrastructure configuration, loaded from the environment / ``.env``.

    ``DATABASE_URL`` is the pooled Neon ``-pooler`` host used by the application
    engine; ``DATABASE_URL_DIRECT`` is the non-pooled host used only by Alembic,
    because DDL and PgBouncer transaction pooling do not mix. ``GITHUB_TOKEN`` is
    loaded even though Phase 1 never calls GitHub — it is loaded so ``redact()``
    knows its literal value for exact-substring scrubbing (D-16).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr
    database_url_direct: SecretStr
    github_token: SecretStr | None = None
    log_level: str = "INFO"

    def known_secret_values(self) -> dict[str, str]:
        """Return ``{live secret value: label}`` for exact-value redaction.

        The label is the lowercase field name. The walk is over
        ``model_fields`` with an ``isinstance`` check rather than a hardcoded
        list of names, so a credential added in a later phase is covered
        automatically. Values that are unset (``None``) or shorter than 8
        characters are skipped — a short or empty configured secret must not be
        able to turn ``redact()`` into a string shredder.
        """
        known: dict[str, str] = {}
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, SecretStr):
                secret = value.get_secret_value()
                if len(secret) >= 8:
                    known[secret] = field_name
        return known


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` singleton.

    The same object is the source of truth for the engine, the log processor and
    the lifecycle mutation path.
    """
    return Settings()
