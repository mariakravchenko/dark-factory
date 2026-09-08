"""Real-sink structlog capture helper (Plan 01-03, Task 3).

``real_log_sink()`` attaches the **production** processor chain
(``dark_factory.logging.configure_logging``) to an in-memory ``StringIO`` and
restores the previous structlog configuration on exit.

It deliberately does NOT use ``structlog.testing.capture_logs``: that helper
bypasses the processor chain, so the redaction processor would never run and a
suite built on it would pass green while the real log file leaks
(01-RESEARCH.md, Pitfall 5). Plan 08's SC5 end-to-end proof reuses this helper.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager

import structlog

from dark_factory.logging import configure_logging


@contextmanager
def real_log_sink() -> Iterator[io.StringIO]:
    """Yield a ``StringIO`` fed by the real configured structlog chain."""
    buffer = io.StringIO()
    previous_config = structlog.get_config()
    try:
        configure_logging(logger_factory=structlog.PrintLoggerFactory(file=buffer))
        yield buffer
    finally:
        structlog.configure(**previous_config)
