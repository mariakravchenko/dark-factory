"""The run-event type catalog.

Phase 1 emitted the first six members (D-22). Phase 2 adds exactly four more --
QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED -- the pause and
resume transitions this phase actually writes. Phase 5 adds exactly one more --
WIP_COMMIT_CREATED (A-05-06) -- the WIP-recovery audit tie this phase's
``_persist_wip_commit`` genuinely writes: a permanent git side effect (a
recovery commit landing on the run's working branch) with no accompanying
``run_events`` row is precisely the gap this project's "durability and
observability are the same requirement" core value forbids, so declaring this
member does not violate the not-yet-reachable-types rule below -- it is
reachable, and reached, by this phase's own code. The remainder listed in
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

    # Phase 5 -- the WIP-recovery audit tie (A-05-06).
    WIP_COMMIT_CREATED = "WIP_COMMIT_CREATED"
