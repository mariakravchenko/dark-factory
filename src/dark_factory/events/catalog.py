"""The run-event type catalog.

Phase 1 emitted the first six members (D-22). Phase 2 adds exactly four more --
QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED -- the pause and
resume transitions this phase actually writes. The remainder listed in
PROJECT.md -- ARTIFACT_CREATED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED,
PUBLISH_STARTED, PR_CREATED -- still arrive in Phase 12. A member present in the
enum but never written is a false signal in the audit surface, so the
not-yet-reachable types are deliberately not pre-declared here; that rule is what
keeps the Phase 12 observability claim honest.
"""

from enum import StrEnum

__all__ = ["EventType"]


class EventType(StrEnum):
    """Append-only ``run_events.type`` values. Value equals name."""

    RUN_CREATED = "RUN_CREATED"
    ROLE_STARTED = "ROLE_STARTED"
    ROLE_COMPLETED = "ROLE_COMPLETED"
    ROLE_FAILED = "ROLE_FAILED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"

    # Phase 2 -- the pause / resume audit trail.
    QUESTION_CREATED = "QUESTION_CREATED"
    RUN_PAUSED = "RUN_PAUSED"
    HUMAN_ANSWER_RECEIVED = "HUMAN_ANSWER_RECEIVED"
    RUN_RESUMED = "RUN_RESUMED"
