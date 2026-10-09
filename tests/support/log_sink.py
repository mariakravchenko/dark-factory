"""Real-sink structlog capture helper (Plan 01-03, Task 3).

``real_log_sink()`` attaches the **production** processor chain
(``dark_factory.logging.configure_logging``) to an in-memory ``StringIO`` and
restores the previous structlog configuration on exit.

It deliberately does NOT use ``structlog.testing.capture_logs``: that helper
bypasses the processor chain, so the redaction processor would never run and a
suite built on it would pass green while the real log file leaks
(01-RESEARCH.md, Pitfall 5). Plan 08's SC5 end-to-end proof reuses this helper.

``configure_logging`` transitively calls ``get_settings()`` twice (the level
filter at configure time, the redaction processor per event), so this helper
must make ``Settings`` constructible in a process with no ``DATABASE_URL`` /
``DATABASE_URL_DIRECT`` and no readable ``.env`` (G-11-3, plan 11-09). It does
this by supplying the two fake constants below **only when the corresponding
environment variable is absent** — never overriding one already present, and
per variable rather than all-or-nothing.

That asymmetry is load-bearing: ``tests/unit/test_log_redaction.py`` deliberately
sets its own database URL via ``monkeypatch.setenv`` before entering this context
manager and asserts that exact value is redacted from the sink. An unconditional
override would replace the value before ``configure_logging`` ever saw it, so
``Settings.known_secret_values()`` would never learn it and exact-value scrubbing
could not remove it.

WHICH TESTS PIN THIS (debug session ``log-sink-conditional-override-unpinned``):
an earlier version of this docstring claimed an unconditional override would make
those redaction assertions vacuous. **That was measured and found false** — the
mutant SURVIVED the entire suite, because every assertion looked only at the
sink's text and the D-15 *pattern* rule for ``postgres://...@...`` URLs redacts
any credential-bearing DSN on shape alone, so substituting one for another
changed nothing observable. Two tests now pin it, and both are required:

* ``test_sink_helper_supplies_only_absent_database_vars_and_restores`` — observes
  ``os.environ`` and ``Settings`` from inside the context across all four
  presence cells. This is the direct pin and it involves no redaction, keeping
  this helper's contract decomposed from the redactor's.
* ``test_known_secret_value_no_pattern_can_rescue_never_reaches_the_sink`` — the
  end-to-end pin, using a credential-free DSN that no pattern can match, so only
  exact-value substitution of the value this helper preserved can scrub it.

Do not "simplify" the per-variable absence check away; it is covered now.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from contextlib import contextmanager

import structlog

from dark_factory.config.settings import get_settings
from dark_factory.logging import configure_logging

# Obviously-fake, greppable values — never real credentials. Distinct from
# tests/conftest.py's own fake constants (a different test-support layer) and
# at least 8 characters so they participate in Settings.known_secret_values()'s
# own redaction floor rather than silently sitting below it.
_FAKE_DATABASE_URL = (
    "postgresql://df_logsink_fake_user:df_logsink_fake_pw@"
    "fake-logsink-pooler.invalid:5432/df_logsink_fake_db"
)
_FAKE_DATABASE_URL_DIRECT = (
    "postgresql://df_logsink_fake_user:df_logsink_fake_pw@"
    "fake-logsink-direct.invalid:5432/df_logsink_fake_db"
)

_REQUIRED_ENV_VARS = {
    "DATABASE_URL": _FAKE_DATABASE_URL,
    "DATABASE_URL_DIRECT": _FAKE_DATABASE_URL_DIRECT,
}


@contextmanager
def real_log_sink() -> Iterator[io.StringIO]:
    """Yield a ``StringIO`` fed by the real configured structlog chain.

    Supplies ``DATABASE_URL`` / ``DATABASE_URL_DIRECT`` with fake values only
    when absent from the environment, so ``Settings`` is constructible even in
    a database-free process — without ever touching a value a test set on
    purpose (see module docstring).
    """
    buffer = io.StringIO()
    previous_config = structlog.get_config()
    supplied: list[str] = [
        name for name in _REQUIRED_ENV_VARS if name not in os.environ
    ]
    for name in supplied:
        os.environ[name] = _REQUIRED_ENV_VARS[name]
    if supplied:
        get_settings.cache_clear()
    try:
        configure_logging(logger_factory=structlog.PrintLoggerFactory(file=buffer))
        yield buffer
    finally:
        structlog.configure(**previous_config)
        for name in supplied:
            del os.environ[name]
        if supplied:
            get_settings.cache_clear()
