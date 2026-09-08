"""The run-event type catalog.

Phase 1 emits only the six members below (D-22). The full catalog listed in
PROJECT.md -- ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED,
HUMAN_ANSWER_RECEIVED, RUN_RESUMED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED,
PUBLISH_STARTED, PR_CREATED -- is completed in Phase 12. A member present in the
enum but never written is a false signal in the audit surface, so the unreachable
types are deliberately not pre-declared here.
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
