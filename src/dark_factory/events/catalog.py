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
reachable, and reached, by this phase's own code. Phase 6 adds exactly one
more -- CAPABILITY_DENIED (D-07) -- the capability-denial audit tie
``orchestrator/runner.py`` genuinely writes: a role whose invocation was
denied by ``ToolRegistry.invoke()`` (T-06-05) must leave a first-class,
auditable fact behind, not just the ``ROLE_FAILED`` / ``RUN_FAILED`` pair a
denial already produces -- this member is emitted *in addition to* those
two, never instead of them (D-08), so no existing observability consumer
needs a new branch to recognise a failed run. Phase 9 adds exactly three
more -- QUALITY_GATE_STARTED, QUALITY_GATE_PASSED, QUALITY_GATE_FAILED
(D-02) -- the independent-quality-gate audit tie
``orchestrator/quality_gate.py`` / ``orchestrator/runner.py`` genuinely
write: the gate has no ``role_executions`` row of its own (D-01), so these
purpose-built events are the only durable trace that it ran at all,
following the identical ``CAPABILITY_DENIED`` precedent. Phase 9 also adds
a fourth member -- ROLE_BOUNCED (D-04) -- the bounded-feedback-loop audit
tie ``orchestrator/runner.py`` writes when a QA-verdict FAIL or a
quality-gate FAIL sends the run back to the Developer under its
configured iteration cap: deliberately **not** the ``ROLE_FAILED`` /
``RUN_FAILED`` pair, because those two specifically mean the run is dead,
and a bounce is a run that is still alive and looping. The remainder
listed in PROJECT.md -- ARTIFACT_CREATED, QA_FAILED/PASSED -- still
arrive in Phase 12; Phase 9 having already shipped
``QUALITY_GATE_FAILED/PASSED``/``ROLE_BOUNCED`` above means Phase 12 must
not re-add them. Phase 10 adds exactly three more --
PUBLISH_STARTED, PR_CREATED, PUBLISH_FAILED (D-07) -- the
idempotent-publishing audit tie ``orchestrator/publish.py`` /
``orchestrator/runner.py`` genuinely write: the publish step has no
``role_executions`` row of its own (mirroring the quality gate's D-01
posture), so these three are the only durable trace that a publish
attempt ran at all. Phase 12 is now a *consumer* of these three events,
never their origin. A member present in the enum but never written is a
false signal in the audit surface, so the not-yet-reachable types are
deliberately not pre-declared here; that rule is what keeps the Phase 12
observability claim honest. Phase 12 (plan 12-01) adds exactly one more --
ARTIFACT_CREATED (D-06) -- the artifact-write audit tie
``orchestrator/runner.py`` genuinely writes: one event per
``ArtifactReferenceWrite`` an attempt produces, in the same
``apply_transition`` call that inserts the matching ``artifacts`` row, so
the two can never drift apart. Phase 12 (plan 12-04) adds the final two --
QA_FAILED and QA_PASSED (D-07) -- the acceptance-criteria-verdict audit
tie ``orchestrator/runner.py`` genuinely writes, once each, from the
existing structural ``verdict.computed_status`` block: these answer "did
the work meet the stated acceptance criteria?", a genuinely different
question from ``QUALITY_GATE_PASSED``/``QUALITY_GATE_FAILED``'s "did the
independent command re-run pass?" -- a run can fail the first while never
reaching the second, so the two families are deliberately distinct
signals in one stream rather than two names for the same fact. With these
two, the catalog is now complete for the full set PROJECT.md declares --
every member below is written by some shipped code path, and this
docstring names no further pending member.
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

    # Phase 6 -- the capability-denial audit tie (D-07, D-08).
    CAPABILITY_DENIED = "CAPABILITY_DENIED"

    # Phase 9 -- the independent quality-gate audit tie (D-02).
    QUALITY_GATE_STARTED = "QUALITY_GATE_STARTED"
    QUALITY_GATE_PASSED = "QUALITY_GATE_PASSED"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"

    # Phase 9 -- the bounded-feedback-loop bounce audit tie (D-04).
    ROLE_BOUNCED = "ROLE_BOUNCED"

    # Phase 10 -- the idempotent-publishing audit tie (D-07).
    PUBLISH_STARTED = "PUBLISH_STARTED"
    PR_CREATED = "PR_CREATED"
    PUBLISH_FAILED = "PUBLISH_FAILED"

    # Phase 12 -- the artifact-write audit tie (D-06).
    ARTIFACT_CREATED = "ARTIFACT_CREATED"

    # Phase 12 -- the QA-verdict audit tie (D-07).
    QA_FAILED = "QA_FAILED"
    QA_PASSED = "QA_PASSED"
