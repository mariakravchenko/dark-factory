"""The application's SQLAlchemy engine, tuned for a short-lived CLI against a
PgBouncer-pooled PostgreSQL (Plan 01-04).

``dark-factory run`` / ``resume`` / ``status`` each run a handful of queries and
exit, often after a long human wait, against Neon's transaction pooler. That
shapes every setting here:

* ``poolclass=NullPool`` — the process must not retain Neon connections across a
  scale-to-zero window; every ``advance()`` call opens and closes its own.
* ``pool_pre_ping=True`` — a resume after a delayed human answer must verify the
  connection is still alive before using it.
* ``connect_args={"prepare_threshold": None}`` — psycopg 3's client-side
  prepared-statement cache is what breaks through PgBouncer transaction pooling;
  disabling it is the documented Neon-safe setting.
* a single ``tenacity`` retry-once-on-``OperationalError`` around the **initial**
  connect only, to absorb the Neon cold start (300-800 ms). Nothing else is
  wrapped — the drive loop's retries are orchestration logic with persisted
  attempt counts, not transient-fault retries.

STATE-01: the application knows only ``DATABASE_URL``. Nothing here imports a
Neon package or references a Neon hostname; ``database_url`` comes from the
cached ``Settings`` singleton via ``get_secret_value()``.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from dark_factory.config.settings import get_settings

__all__ = ["SessionLocal", "build_engine"]

# psycopg v3 is the only supported driver (project guidelines, Version
# Compatibility): ``postgresql+psycopg://``, never ``postgresql+psycopg2://``.
_PSYCOPG_SCHEME = "postgresql+psycopg://"
_LEGACY_SCHEMES = (
    "postgresql+psycopg2://",
    "postgresql://",
    "postgres://",
)


def _normalise_scheme(url: str) -> str:
    for legacy in _LEGACY_SCHEMES:
        if url.startswith(legacy):
            return _PSYCOPG_SCHEME + url[len(legacy) :]
    return url


def build_engine() -> Engine:
    """Return an :class:`~sqlalchemy.Engine` for the pooled application endpoint.

    The engine is lazy — no socket is opened here. The first real connection is
    made through :func:`_connect_once`, which retries once on a Neon cold-start
    ``OperationalError``.
    """
    settings = get_settings()
    url = _normalise_scheme(settings.database_url.get_secret_value())
    return create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
        future=True,
    )


@retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.5),
    reraise=True,
)
def _connect_once(engine: Engine) -> None:
    """Open and immediately close one connection, retrying once on the Neon cold
    start. This is the *only* place a retry wraps a database call."""
    with engine.connect():
        pass


_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the process-wide engine, building and warming it on first use."""
    global _engine
    if _engine is None:
        engine = build_engine()
        _connect_once(engine)
        _engine = engine
    return _engine


# ``sessionmaker`` with no bind: the engine is attached lazily by ``new_session``
# the first time a session is actually needed, so importing this module never
# forces a ``Settings`` load or a database connection.
SessionLocal = sessionmaker(expire_on_commit=False, future=True)


def new_session() -> object:
    """Return a new ``Session`` bound to the process-wide warmed engine."""
    return SessionLocal(bind=get_engine())
