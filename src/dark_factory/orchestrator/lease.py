"""Ownership of a run — the claim-don't-check Postgres lease (HITL-07, HITL-08).

This module touches **only** ``runs.owner_token``, ``runs.lock_expires_at`` and
``runs.updated_at``. It never writes a lifecycle column and never constructs an
audit row, which is why it sits *beside* the one mutation path
(``persistence/mutations.py``) rather than inside it, and why
``tests/unit/test_single_mutation_path.py`` does not need to police it — the
lease is ownership, not lifecycle state.

**One clock domain — the server's.** Every expiry *value* written here is a SQL
expression over the database clock (``func.now() + timedelta(...)``); every
expiry *comparison* is a SQL predicate against that same clock
(``lock_expires_at < func.now()``). Nothing in this module reads the process
clock for a correctness decision — the only use of ``time`` is the heartbeat's
sleep *between* renewals, which is a delay, not a timestamp. That is what makes
two machines (Phase 11) unable to disagree about whether an owner is alive.

**One statement is the whole design.** ``claim_lease`` is a single conditional
``UPDATE ... RETURNING``: the update takes its own row lock for its duration,
two concurrent claims serialise, and the loser re-evaluates its predicate
against the now-committed row and matches nothing. ``RETURNING`` tells the winner
in the same round trip, so there is no check-then-act window a
select-then-update would open. There is deliberately no select-for-update, no
advisory lock and no row-skipping clause layered on top — a second coordination
primitive for the same guarantee is exactly what the project's constraints exist
to forbid.

**The heartbeat never outlives its owner.** ``run_lease`` is a context manager;
its ``__exit__`` runs on **every** exit — normal, exceptional, or a clean pause
— and always stops the heartbeat thread, joins it, and best-effort releases the
lease. A heartbeat that kept renewing after its owner decided to stop would hold
the run hostage for the life of the process, so the thread is never started
outside this context manager and ``__exit__`` has no early return.

**What the lease guarantees — and what it does not.** The guarantee is *no
concurrent durable mutation*, not *no concurrent execution*. The worker call in
``_run_current_role`` runs *outside* the lease-validity window and is not
cancellable: if an owning process stalls (GC pause, ``SIGSTOP``, VM pause, a
network partition that also starves the heartbeat) past ``lease_ttl_seconds``, a
second process can legitimately claim the lease and start executing the same
role's worker while the first is still running. Durable state stays correct —
the ``expected_owner_token`` fence in ``apply_transition`` rejects the stalled
process's commit (``LeaseLost``, nothing written) — but two workers can be
in-flight at once for that window. This is harmless while the shipped worker is
``FakeWorker`` (no side effects) and must be addressed before credentialled
agent subprocesses on a shared worktree land (Phase 7): e.g. poll
``lease.lease_lost`` on a timer during the worker call and kill the subprocess
process-group on loss, or have the worker adapter re-verify ownership
immediately before any irreversible side effect.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from dark_factory.config.settings import get_settings
from dark_factory.domain.status import TERMINAL_STATUSES
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import Run

__all__ = [
    "LeaseHandle",
    "LeaseNotAcquired",
    "claim_lease",
    "release_lease",
    "renew_lease",
    "run_lease",
]

_log = structlog.get_logger(__name__)

SessionFactory = Callable[[], Session]

# String values, not enum members: the ``UPDATE`` predicate compares against the
# ``runs.status`` VARCHAR + CHECK column.
_TERMINAL_VALUES = tuple(status.value for status in TERMINAL_STATUSES)

# How long ``__exit__`` waits for the daemon heartbeat to notice the stop Event
# and return. The thread's blocking wait is interruptible (``Event.wait``), so
# this is a safety bound, not the expected latency.
_JOIN_TIMEOUT_SECONDS = 5.0


class LeaseNotAcquired(RuntimeError):
    """Raised by :func:`run_lease` when the claim returns no row: another live
    process owns the run, or the run is terminal. Carries the run id and the
    run's observed status so a caller can report cleanly without re-reading the
    row."""

    def __init__(self, run_id: UUID, observed_status: str | None) -> None:
        super().__init__(
            f"run {run_id} could not be leased (observed status={observed_status}); "
            "it is owned by another process — exiting without changes"
        )
        self.run_id = run_id
        self.observed_status = observed_status


@dataclass(frozen=True)
class LeaseHandle:
    """The live lease. ``token`` fences every ``apply_transition`` commit made
    while the lease is held; ``lease_lost`` is set by the heartbeat if a renewal
    ever finds the lease gone, so the main thread can abort fast."""

    token: UUID
    lease_lost: threading.Event


def claim_lease(session: Session, run_id: UUID, *, ttl_seconds: int) -> UUID | None:
    """Claim the run with one conditional ``UPDATE ... RETURNING``.

    Returns a fresh ``uuid4`` owner token when a row came back (this process now
    holds the lease), or ``None`` when none did — a live owner holds an unexpired
    lease, or the run is terminal.
    """
    token = uuid4()
    with session.begin():
        row = session.execute(
            sa.update(Run)
            .where(
                Run.id == run_id,
                Run.status.not_in(_TERMINAL_VALUES),
                sa.or_(
                    Run.owner_token.is_(None),
                    Run.lock_expires_at < func.now(),
                ),
            )
            .values(
                owner_token=token,
                lock_expires_at=func.now() + timedelta(seconds=ttl_seconds),
                updated_at=func.now(),
            )
            .returning(Run.id)
        ).first()
    return token if row is not None else None


def renew_lease(
    session: Session, run_id: UUID, token: UUID, *, ttl_seconds: int
) -> bool:
    """Push ``lock_expires_at`` forward, guarded by the owner token. Returns
    whether the row was still ours to renew."""
    with session.begin():
        row = session.execute(
            sa.update(Run)
            .where(Run.id == run_id, Run.owner_token == token)
            .values(
                lock_expires_at=func.now() + timedelta(seconds=ttl_seconds),
                updated_at=func.now(),
            )
            .returning(Run.id)
        ).first()
    return row is not None


def release_lease(session: Session, run_id: UUID, token: UUID) -> None:
    """Clear both lease columns, guarded by the owner token, so a process can
    only ever release its own lease. A no-op when the row is already unowned
    (e.g. ``apply_transition`` cleared it on reaching a stop status)."""
    with session.begin():
        session.execute(
            sa.update(Run)
            .where(Run.id == run_id, Run.owner_token == token)
            .values(owner_token=None, lock_expires_at=None, updated_at=func.now())
        )


def _observed_status(session_factory: SessionFactory, run_id: UUID) -> str | None:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        return run.status.value if run is not None else None
    finally:
        session.close()


@contextlib.contextmanager
def run_lease(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
    ttl_seconds: int | None = None,
    heartbeat_seconds: int | None = None,
) -> Iterator[LeaseHandle]:
    """Hold the single-owner lease on ``run_id`` for the duration of the ``with``
    block, renewed by one daemon heartbeat thread.

    Raises :class:`LeaseNotAcquired` (after logging, run id bound) when the claim
    returns nothing. On a successful claim, starts a daemon thread that loops on
    a stop ``Event``'s timed wait — so it wakes immediately on shutdown — and on
    each wake opens its **own** session (a ``Session`` is not thread-safe),
    renews, and on a renewal that matches no row sets ``lease_lost`` and returns.
    """
    settings = get_settings()
    ttl = settings.lease_ttl_seconds if ttl_seconds is None else ttl_seconds
    interval = (
        settings.lease_heartbeat_seconds
        if heartbeat_seconds is None
        else heartbeat_seconds
    )

    claim_session = session_factory()
    try:
        token = claim_lease(claim_session, run_id, ttl_seconds=ttl)
    finally:
        claim_session.close()

    if token is None:
        status = _observed_status(session_factory, run_id)
        _log.info(
            "lease.not_acquired",
            run_id=str(run_id),
            observed_status=status,
            detail="run is owned by another process; exiting without changes",
        )
        raise LeaseNotAcquired(run_id, status)

    lease_lost = threading.Event()
    stop = threading.Event()

    def _heartbeat() -> None:
        # Distinguish "renewal raised" (transient: dropped connection, Neon
        # scale-to-zero cold start, momentary DNS/TCP failure) from "renewal
        # executed and matched no row" (authoritative: the lease is genuinely
        # gone). A single network blip must not discard an otherwise-successful
        # in-flight step, because the lease row itself is still valid until
        # ``lock_expires_at`` from the last good renewal. Only give up on a
        # transient error once repeated failures have eaten most of the TTL.
        consecutive_errors = 0
        while not stop.wait(interval):
            hb_session = session_factory()
            try:
                still_ours = renew_lease(hb_session, run_id, token, ttl_seconds=ttl)
            except Exception:
                consecutive_errors += 1
                _log.warning(
                    "lease.renew_error",
                    run_id=str(run_id),
                    attempt=consecutive_errors,
                    exc_info=True,
                )
                if consecutive_errors * interval >= ttl - interval:
                    _log.warning("lease.lost", run_id=str(run_id))
                    lease_lost.set()
                    return
                continue
            finally:
                hb_session.close()
            consecutive_errors = 0
            if not still_ours:
                _log.warning("lease.lost", run_id=str(run_id))
                lease_lost.set()
                return

    thread = threading.Thread(
        target=_heartbeat, name=f"lease-heartbeat-{run_id}", daemon=True
    )
    thread.start()
    try:
        yield LeaseHandle(token=token, lease_lost=lease_lost)
    finally:
        stop.set()
        thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
        release_session = session_factory()
        try:
            release_lease(release_session, run_id, token)
        except Exception:
            # Best-effort: a failed release just leaves the lease to expire by
            # TTL. Never let it mask the exception (if any) from the with-body.
            _log.warning("lease.release_error", run_id=str(run_id), exc_info=True)
        finally:
            release_session.close()
