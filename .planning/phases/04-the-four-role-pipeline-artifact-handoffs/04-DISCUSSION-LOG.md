# Phase 4: The Four-Role Pipeline & Artifact Handoffs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-12
**Phase:** 4-The Four-Role Pipeline & Artifact Handoffs
**Areas discussed:** Context selection per role, verdict.json shape & pass/fail semantics, Fake-worker script realism for 4 roles, Schema-violation failure behavior

---

## Context selection per role

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit `inputs` field in role YAML | Add `inputs: list[str]` to `RoleDefinition` mirroring `outputs`/`examples`, naming exactly which prior artifacts a role consumes | ✓ |
| Fixed convention: role N sees role N-1's outputs | ContextBuilder always hands each role its immediate predecessor's outputs | |
| You decide | Claude picks during planning | |

**User's choice:** Explicit `inputs` field in role YAML (Recommended)
**Notes:** Chosen because a strictly-linear convention breaks for QA needing acceptance_criteria.json from BA (two roles back).

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — a fixed 'always included' set | Every RoleContext gets README/AGENTS.md/CLAUDE.md + constraints.json baseline, on top of role-specific `inputs` | ✓ |
| No — each role's YAML must list them explicitly too | Fully config-driven, no hidden defaults | |

**User's choice:** Yes — a fixed 'always included' set (Recommended)
**Notes:** Matches CTX-01's explicit listing of README/AGENTS.md/CLAUDE.md as part of every RoleContext.

| Option | Description | Selected |
|--------|-------------|----------|
| Scope by role_execution_id | ArtifactReference.role_execution_id ties an artifact to the exact attempt that produced it; ContextBuilder reads only the latest COMPLETED role_execution per role | ✓ |
| You decide | Claude figures out the exact mechanism during planning | |

**User's choice:** Scope by role_execution_id (Recommended)
**Notes:** Reuses the existing per-attempt RoleExecution row pattern from Phase 1/2.

---

## verdict.json shape & pass/fail semantics

| Option | Description | Selected |
|--------|-------------|----------|
| All acceptance criteria must PASS | Per-criterion array + issues list (severity: blocking/minor); overall PASS only if every criterion PASSes and no blocking issue exists | ✓ |
| Weighted/majority pass | Some criteria optional/nice-to-have, don't block overall PASS | |
| You decide | Claude designs the exact schema during planning/research | |

**User's choice:** All acceptance criteria must PASS (Recommended)
**Notes:** Matches ROLE-04's "independently verifies each acceptance criterion" — no "optional criterion" concept exists in REQUIREMENTS.md.

| Option | Description | Selected |
|--------|-------------|----------|
| PASS or FAIL both just advance the run forward | Phase 4 only requires the post-QA transition to be decided by verdict.json, not to branch differently on PASS vs FAIL | ✓ |
| FAIL routes the run straight to a terminal FAILED state | A QA FAIL immediately ends the run as FAILED in Phase 4, no bounce | |

**User's choice:** PASS or FAIL both just advance the run forward (Recommended)
**Notes:** Feedback-loop/bounce behavior is explicitly Phase 9's scope, not Phase 4's success criteria.

| Option | Description | Selected |
|--------|-------------|----------|
| Stable string id per criterion | acceptance_criteria.json is a list of {id, description}; verdict.json references the same id | ✓ |
| Positional index | verdict.json entries line up by array position | |

**User's choice:** Stable string id per criterion (Recommended)
**Notes:** Survives criteria being reordered/filtered between BA and QA reading them.

---

## Fake-worker script realism for 4 roles

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal but schema-valid placeholders | Scripted content satisfies schema (right keys, valid ids/enums) but with generic text, not task-aware prose | ✓ |
| Task-aware realistic mock content | Fixtures generate plausible-sounding text referencing the actual task | |
| You decide | Claude picks simplest approach | |

**User's choice:** Minimal but schema-valid placeholders (Recommended)
**Notes:** Phase 4 tests durable handoff plumbing and schema validation, not content quality — realistic content only matters once Phase 7 wires a real Claude Code worker.

| Option | Description | Selected |
|--------|-------------|----------|
| Share one `fake` worker, differ by scripted content | WorkerRegistry stays at one `fake` entry; tests wire different scripts per role | ✓ |
| You decide | Claude decides based on cleanest fit with existing registry code | |

**User's choice:** Share one `fake` worker, differ by scripted content (Recommended)
**Notes:** Matches D-10/Phase-1 precedent that role ≠ worker; worker registry shouldn't grow per-role variants.

---

## Schema-violation failure behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate FAILED run, no retry within the role | Schema violation persists a FAILED role_execution + run_events error entry and transitions the run to FAILED, same shape as any other worker failure path | ✓ |
| One in-process re-ask before failing | Orchestrator re-calls worker.execute() once with an error message appended before failing | |

**User's choice:** Immediate FAILED run, no retry within the role (Recommended)
**Notes:** Bounded retry is explicitly Phase 9's job (ORCH-04/Phase 9 "bounded feedback loops").

| Option | Description | Selected |
|--------|-------------|----------|
| Python/pydantic models in domain code | Each artifact type gets a pydantic model (mirroring WorkerResult/ArtifactRef) in a new domain module; validation via model_validate | ✓ |
| Standalone JSON Schema files | A .json schema file per artifact type validated with `jsonschema`, adding a new dependency | |

**User's choice:** Python/pydantic models in domain code (Recommended)
**Notes:** No separate JSON Schema files or schema registry to keep in sync; consistent with existing `frozen=True, extra="forbid"` boundary-model pattern.

---

## Claude's Discretion

- Exact query mechanism ContextBuilder uses to find "the latest COMPLETED role_execution per role" — left to planning as long as CTX-04 holds.
- Whether `inputs` entries name a role (implying "that role's declared outputs") or a literal artifact path — left to planner/researcher.

## Deferred Ideas

- QA-FAIL → Developer bounce / bounded retry loop — belongs to Phase 9 ("Independent Quality Gate & Bounded Feedback Loops").
- In-process re-ask on schema violation — considered and rejected for Phase 4; any such retry belongs with Phase 9.
