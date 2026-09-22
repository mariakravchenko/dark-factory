# Phase 9: Independent Quality Gate & Bounded Feedback Loops - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-22
**Phase:** 9-Independent Quality Gate & Bounded Feedback Loops
**Areas discussed:** Gate placement in pipeline, Bounce-back mechanism, Feedback payload to Developer, Gate command execution semantics

---

## Gate placement in pipeline

| Option | Description | Selected |
|--------|-------------|----------|
| Orchestrator-only step after QA PASS | No role_executions row, no worker; runner.py directly invokes shell_execute after QA's transition | ✓ |
| Pseudo-role node in workflow.roles | New "internal" worker + role config entry, reuses dispatch loop | |
| After-hook on QA (like collect_diff) | Registered as a QA after: hook via ActionRegistry | |

**User's choice:** Orchestrator-only step after QA PASS

| Option | Description | Selected |
|--------|-------------|----------|
| New GATE_RUN event pair (QUALITY_GATE_STARTED/PASSED/FAILED) | Dedicated run_events, following CAPABILITY_DENIED precedent | ✓ |
| Piggyback on existing QA events only | No new event types | |

**User's choice:** New GATE_RUN event pair

| Option | Description | Selected |
|--------|-------------|----------|
| Run in the run's existing worktree at HEAD | Same worktree shell.execute already uses | ✓ |
| Fresh clean checkout for gate isolation | Separate clone/worktree just for gate | |

**User's choice:** Run in the run's existing worktree at HEAD

---

## Bounce-back mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| New Signal.ROLE_BOUNCED | New Signal type, mapped by lifecycle.transition() to re-enter DEVELOPMENT; cap check decides signal choice before dispatch | ✓ |
| Reuse ROLE_FAILED, branch inside runner.py only | No new Signal; runner.py hand-builds next state | |

**User's choice:** New Signal.ROLE_BOUNCED

| Option | Description | Selected |
|--------|-------------|----------|
| New attempt row each time | Fresh role_executions row per bounce for Developer and QA | ✓ |
| Reuse/update the same row | Update existing row in place | |

**User's choice:** New attempt row each time

| Option | Description | Selected |
|--------|-------------|----------|
| Separate counters, incremented right before the bounced dispatch | qa_developer_iterations and quality_gate_iterations independent, each checked against its own cap | ✓ |
| Single shared iteration counter | One counter, one combined cap | |

**User's choice:** Separate counters, incremented right before the bounced dispatch

---

## Feedback payload to Developer

| Option | Description | Selected |
|--------|-------------|----------|
| New durable artifact file, read by ContextBuilder | QA verdict.json / verification/quality_gate.json read as declared inputs | ✓ |
| Inject directly into RoleContext without a file | In-memory pass-through, not resumable | |

**User's choice:** New durable artifact file, read by ContextBuilder

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit new inputs in DEVELOPMENT.yaml | Config-declared inputs, consistent with CFG-02 | ✓ |
| Implicit orchestrator behavior, no config change | ContextBuilder special-cases bounced attempts in code | |

**User's choice:** Explicit new inputs in DEVELOPMENT.yaml

---

## Gate command execution semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Run all, collect every result | All commands run regardless of earlier failures; gate PASSes only if all exit 0 | ✓ |
| Stop at first failure | CI-style short-circuit | |

**User's choice:** Run all, collect every result

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Settings.worker_timeout_seconds | Same knob as Phase 7 D-03 worker calls | ✓ |
| New dedicated Settings.quality_gate_timeout_seconds | Separate timeout knob for gate commands | |

**User's choice:** Reuse Settings.worker_timeout_seconds

| Option | Description | Selected |
|--------|-------------|----------|
| List of per-command results + overall status | `{status, commands: [{command, exit_code, stdout, stderr, timed_out}]}`, status computed like Verdict.computed_status | ✓ |
| Simple boolean pass/fail with combined output | `{passed, output}` — loses per-command attribution | |

**User's choice:** List of per-command results + overall status

---

## Claude's Discretion

- Exact `EventType` names/payload shapes for the new gate events and the `RUN_FAILED` exhaustion-reason payload.
- Exact filenames/field names for the QA-issues-to-Developer feedback artifact (reuse verdict.json directly vs. a Developer-facing transform).
- Exact placement in runner.py of the iteration-cap check relative to the existing QA branch and hook dispatch.

## Deferred Ideas

None — discussion stayed within phase scope.
