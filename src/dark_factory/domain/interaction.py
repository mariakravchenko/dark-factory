"""The interaction-status vocabulary for the ``human_interactions`` table (STATE-04).

``InteractionStatus`` is the single closed set of states a human clarification row
can occupy. Each member's value equals its name, mirroring
:class:`dark_factory.domain.signal.Signal` and
:class:`dark_factory.domain.status.RunStatus` line for line.

``CANCELLED`` is declared here but **written nowhere in Phase 2**. That is safe and
deliberate: the value lives only as one arm of the ``interaction_status`` CHECK
constraint, and an unwritten CHECK value is inert. This is unlike an unwritten
``EventType`` member, which would be a false signal in the audit surface. A future
"abort a waiting run" feature (or Phase 12 observability) will be the first writer.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["InteractionStatus"]


class InteractionStatus(StrEnum):
    """Every state a ``human_interactions`` row can occupy. Value equals name."""

    WAITING = "WAITING"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"
