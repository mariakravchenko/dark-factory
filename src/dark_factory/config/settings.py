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

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = frozenset(
    {"CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "NOTSET"}
)


class Settings(BaseSettings):
    """Typed infrastructure configuration, loaded from the environment / ``.env``.

    ``DATABASE_URL`` is the pooled Neon ``-pooler`` host used by the application
    engine; ``DATABASE_URL_DIRECT`` is the non-pooled host used only by Alembic,
    because DDL and PgBouncer transaction pooling do not mix. ``GITHUB_TOKEN`` is
    loaded even though Phase 1 never calls GitHub — it is loaded so ``redact()``
    knows its literal value for exact-substring scrubbing (D-16).

    ``lease_ttl_seconds`` (900) and ``lease_heartbeat_seconds`` (300) resolve the
    roadmap's Open Decision 2. 900 s is the top of the roadmap's 5-to-15-minute
    baseline, so a genuinely dead owner's run is reclaimable within fifteen
    minutes, which is acceptable for a human-speed delivery pipeline. 300 s is
    one third of the TTL, the standard lease-renewal ratio, chosen so that two
    consecutive missed renewals still land inside the TTL before the lease is
    lost. "Slow" and "dead" are not distinguished and are not meant to be:
    liveness *is* a freshly pushed expiry, and an owner proves it by renewing,
    not by anyone probing it. Both are ordinary integers (not credentials)
    overridable from the environment, so a test can inject a 2-second lease.

    ``anthropic_api_key`` (Plan 07-01, D-02) is optional -- exactly like
    ``github_token`` -- so nothing new is required at process startup for an
    environment that only ever runs ``fake``-worker pipelines. Its absence
    only surfaces when a role actually tries to invoke the ``claude-code``
    worker (``ClaudeCodeWorker.execute()`` raises a typed
    ``MissingWorkerCredentialError`` before spawning anything).
    ``worker_timeout_seconds`` (D-03) is the single knob governing every
    worker subprocess call; 1800s (30 minutes) is a deliberately generous
    *estimate*, not a measured figure -- no authoritative "typical role
    duration" exists to anchor it against (07-RESEARCH.md Open Question #1),
    chosen so a DEVELOPMENT-role attempt that builds and iterates is not
    truncated mid-flight.

    ``copilot_github_token`` (Plan 08-01, D-01) is deliberately a *separate*
    field from ``github_token`` even though both are GitHub-scoped PATs:
    ``github_token`` is Dark Factory's own infrastructure credential (used
    for its own push/PR creation, TOOL-04/SEC-01) and must never reach a
    worker subprocess, while ``copilot_github_token`` is a worker's own
    authentication material, injected into the ``copilot`` subprocess
    exclusively through ``build_worker_env(role, env_var_name=
    "COPILOT_GITHUB_TOKEN", value=...)``. Conflating the two fields would
    make "did the infrastructure credential ever reach a worker" unanswerable
    from the field name alone. The GitHub Copilot CLI requires a
    fine-grained, personal-account-owned personal access token carrying the
    ``Copilot Requests`` permission -- a classic PAT (``ghp_*``) is rejected
    by the CLI (08-RESEARCH.md Finding 3). Like ``anthropic_api_key``, its
    absence only surfaces as a typed error (``CopilotWorker``'s own
    ``MissingWorkerCredentialError``) when a role actually tries to invoke
    the ``copilot`` worker. ``copilot_model`` is optional: no model
    identifier is pinned by default because no verified identifier exists
    for this environment (D-02 defers the live spike to whenever the CLI is
    actually installed), so the CLI's own default model is used unless an
    operator configures one.

    ``github_webhook_secret`` (Plan 10-01, D-04) is Dark Factory's own
    infrastructure credential for verifying inbound GitHub webhook
    deliveries (consumed by plan 10-04's receiver). It is distinct from
    ``github_token``: the webhook secret authenticates deliveries *arriving
    at* Dark Factory, while ``github_token`` authenticates calls Dark
    Factory *makes to* GitHub. Declared as ``SecretStr | None`` exactly
    like every other optional credential on this object, so
    ``known_secret_values()``'s ``model_fields`` walk covers it with zero
    additional code.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr
    database_url_direct: SecretStr
    github_token: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    log_level: str = "INFO"
    lease_ttl_seconds: int = 900
    lease_heartbeat_seconds: int = 300
    anthropic_api_key: SecretStr | None = None
    copilot_github_token: SecretStr | None = None
    copilot_model: str | None = None
    worker_timeout_seconds: int = 1800

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        """Reject a typo loudly rather than let ``configure_logging`` silently
        fall back to INFO. Normalised to upper case so ``LOG_LEVEL=debug`` works."""
        normalised = value.strip().upper()
        if normalised not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level {value!r} is not a Python logging level name "
                f"(one of: {', '.join(sorted(_VALID_LOG_LEVELS))})"
            )
        return normalised

    @model_validator(mode="after")
    def _lease_intervals_are_coherent(self) -> Settings:
        """Reject a lease configuration that would defeat itself.

        A non-positive TTL is meaningless. The important one is the second check:
        a heartbeat interval that fires no more often than the lease expires
        guarantees the owner loses its own lease, which surfaces later as an
        unreproducible mid-step abort rather than as a configuration error.
        """
        if self.lease_ttl_seconds <= 0:
            raise ValueError(
                f"lease_ttl_seconds must be strictly positive, got "
                f"{self.lease_ttl_seconds!r}"
            )
        if self.lease_heartbeat_seconds >= self.lease_ttl_seconds:
            raise ValueError(
                f"lease_heartbeat_seconds ({self.lease_heartbeat_seconds!r}) must "
                f"be strictly less than lease_ttl_seconds "
                f"({self.lease_ttl_seconds!r}); a heartbeat that fires no more "
                f"often than the lease expires guarantees the owner loses its "
                f"own lease"
            )
        return self

    @model_validator(mode="after")
    def _worker_timeout_is_positive(self) -> Settings:
        """A non-positive worker timeout would either fail every subprocess
        call immediately (0) or be meaningless for ``Popen.wait(timeout=...)``
        (negative) -- reject both loudly rather than let a typo'd
        ``WORKER_TIMEOUT_SECONDS`` produce a mysteriously instant-FAILED role.
        """
        if self.worker_timeout_seconds <= 0:
            raise ValueError(
                f"worker_timeout_seconds must be strictly positive, got "
                f"{self.worker_timeout_seconds!r}"
            )
        return self

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
