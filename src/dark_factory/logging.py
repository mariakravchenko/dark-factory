"""structlog configuration — the single wiring point for the redaction processor.

``configure_logging()`` is the only place in the codebase that calls
``structlog.configure``. The redaction processor sits *after*
``merge_contextvars`` (so bound ``run_id`` / ``role`` / ``attempt`` context is
also scrubbed) and *before* ``JSONRenderer`` (so nothing reaches the sink
unscrubbed; JSON encoding additionally stops a newline in task text from forging
a log line).
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact


def _redaction_processor(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """structlog processor: redact the whole event dict (D-14 wiring point a)."""
    result: EventDict = redact(
        dict(event_dict), known_secrets=get_settings().known_secret_values()
    )
    return result


def configure_logging(logger_factory: Any | None = None) -> None:
    """Install the production structlog processor chain.

    ``logger_factory`` lets a test point the *same* configured chain at a
    ``StringIO`` (``structlog.PrintLoggerFactory(file=...)``); production leaves
    it unset and logs to stdout.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redaction_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=logger_factory
        if logger_factory is not None
        else structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
