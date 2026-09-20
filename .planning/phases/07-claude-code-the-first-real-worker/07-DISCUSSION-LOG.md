# Phase 7: Claude Code — the First Real Worker - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-20
**Phase:** 7-Claude Code — the First Real Worker
**Areas discussed:** Clarifying-question signal, Credential handling, Timeout policy, Log streaming target

---

## Clarifying-question signal

| Option | Description | Selected |
|--------|-------------|----------|
| Convention marker in output | The role's prompt instructs Claude to end its turn with a fixed marker (e.g. a line starting 'NEEDS_INPUT:') when it needs a human decision; the adapter parses the CLI's final result text for that marker. Adapter-only, no CLI feature dependency. | ✓ |
| Never for Claude Code this phase | Ship COMPLETED/FAILED only; NEEDS_INPUT stays proven solely via FakeWorker. Simplest, but SC2's pause/resume path is never exercised by the real adapter. | |
| Structured JSON field convention | Role prompt asks Claude to write a small JSON object ({"needs_input": true, "question": "..."}) instead of prose. More robust to prose variation, adds a mini-schema. | |

**User's choice:** Convention marker in output (recommended)
**Notes:** No follow-up — user moved to next area immediately.

---

## Credential handling

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy, at first claude-code use | Settings.anthropic_api_key stays optional; missing only fails when a run actually invokes a claude-code role, via a typed error from the adapter. Consistent with github_token's existing optional shape. | ✓ |
| Eager, at process startup | Settings validation fails immediately if unset, even for environments that only run 'fake' pipelines. | |
| Eager, at config-load time | load_effective_config validates the credential exists whenever .dark-factory.yaml names 'claude-code' as a role's worker — fails at run-creation time. | |

**User's choice:** Lazy, at first claude-code use (recommended)
**Notes:** No follow-up — user moved to next area immediately.

---

## Timeout policy

| Option | Description | Selected |
|--------|-------------|----------|
| Settings field, generous default | A single Settings.worker_timeout_seconds (env-overridable, generous default e.g. 30min) applies to every worker subprocess call, mirroring lease_ttl_seconds. | ✓ |
| Per-role in .dark-factory.yaml | Each role entry gains an optional timeout_seconds — lets QA differ from DEVELOPMENT, but adds a new config key + snapshot field. | |
| Hardcoded constant, no config | A single module-level constant, no Settings/config knob at all. | |

**User's choice:** Settings field, generous default (recommended)
**Notes:** No follow-up — user moved to next area immediately.

---

## Log streaming target

| Option | Description | Selected |
|--------|-------------|----------|
| Under the run's artifact tree | A new logs/<role>/ subdirectory alongside artifacts/<role>/ under .dark-factory/runs/<run_id>/ — raw stdout/stderr text, one file per attempt. Reuses run_root() and the existing durability model. | ✓ |
| Structured JSON lines alongside raw text | Same location, but each line is a JSON event (timestamp, stream, text) — easier to build a future live-tail feature on, adds a schema now. | |
| Piped straight to structlog only | No separate log files — each chunk emitted as a structlog event bound with run_id/role/attempt. | |

**User's choice:** Under the run's artifact tree (recommended)
**Notes:** No follow-up — user was ready to wrap up context capture after this area.

---

## Claude's Discretion

- Exact `NEEDS_INPUT:` marker text/format and multi-line question extraction.
- Exact `Settings` field name for the Claude Code credential and the typed error raised on missing credential.
- Exact default value of `Settings.worker_timeout_seconds`.
- Exact log file naming/rotation scheme within `logs/<role>/` (separate stdout/stderr files vs. interleaved).
- Whether `resume()` shares the same timeout as `execute()` (default: yes, one shared value).

## Deferred Ideas

None raised as new capabilities. Per-role timeout overrides and a structured JSON-lines log format were named as possible future refinements, not requested now — see CONTEXT.md decision rationale.
