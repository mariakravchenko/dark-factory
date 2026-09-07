# Phase 1: Walking Skeleton — One Durable Run - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-07
**Phase:** 1-walking-skeleton-one-durable-run
**Areas discussed:** CLI drive & resume surface

---

## CLI drive & resume surface

### Q1 — Drive model

| Option | Description | Selected |
|--------|-------------|----------|
| Block until terminal | `run` creates the run, prints its id immediately, then loops resume-first `advance(run_id)` until COMPLETED/FAILED; exit code reflects outcome. Phase 2 adds WAITING_HUMAN as another stop. | ✓ (Claude's choice) |
| One step, then exit | `run` creates the run and executes a single `advance`, then exits; reaching terminal needs repeated invocations. | |
| You decide | Pick the cleaner fit for the resume-first design. | (user picked this) |

**User's choice:** "You decide"
**Notes:** Claude selected *Block until terminal* — satisfies success criterion 1 directly,
keeps the drive loop in one place, and Phase 2 only adds `WAITING_HUMAN` as a stop condition.

### Q2 — Resume command surface

| Option | Description | Selected |
|--------|-------------|----------|
| Ship `resume <run-id>` now | Same drive loop; already in the final command set; Phase 2 adds `--answer`. No throwaway command. | ✓ (Claude's choice) |
| Hidden `advance <run-id>` | Dedicated Phase-1 command; `resume` arrives fully-formed in Phase 2. Second command doing nearly the same thing. | |
| `run --resume <run-id>` | Overload `run` with a flag instead of a subcommand. `run` then takes either a source or a run-id. | |

**User's choice:** "you choose the best option"
**Notes:** Claude selected *Ship `resume <run-id>` now* — one resume path from day one,
already in the final CLI surface, Phase 2 extends the same command with `--answer`.

### Q3 — `run` / `resume` terminal output

| Option | Description | Selected |
|--------|-------------|----------|
| Line per transition + summary | Run id first, one line per state transition, then a short final summary. Readable for a demo, still greppable. | ✓ (Claude's choice) |
| Minimal / script-first | Run id at start, single terminal-state line at end, nothing between. | |
| Rich live panel | Live-updating panel/spinner, plain fallback off-TTY. Most code for a walking skeleton. | |

**User's choice:** "choose the best option"
**Notes:** Claude selected *Line per transition + summary* — right weight for a project that
is both a portfolio piece and genuinely runnable. Same shape for `resume`.

### Q4 — Exit-code convention

| Option | Description | Selected |
|--------|-------------|----------|
| 0 / 1 / 2 by outcome | 0 = COMPLETED, 1 = FAILED (terminal delivery failure), 2 = bad invocation (nothing advanced). | ✓ (Claude's choice) |
| 0 = orchestrator did its job | 0 on any committed terminal state (COMPLETED or FAILED); non-zero only for infra errors. | |
| 0 / non-zero only | 0 on COMPLETED, unspecified non-zero otherwise; pin down later. | |

**User's choice:** "choose the best option"
**Notes:** Claude selected *0 / 1 / 2 by outcome* — cheap convention to set now, and the
Phase 11 CI trigger will want to distinguish pass from fail by exit code.

---

## Claude's Discretion

- **All four discussed questions** (drive model, resume command, `run` output, exit codes) —
  user answered "you decide" / "choose the best option" to each.
- **Three undiscussed gray areas settled from the spec at the user's request** ("choose the
  best option without clarifying with me"):
  - Skeleton role & state path → real `BA` role; `CREATED → BA → COMPLETED`; hardcoded
    one-role pipeline `["BA"]`.
  - `status` output shape → plain-text `key: value` field list from state columns; `--json`
    mode ships in Phase 1; no Rich pipeline view until Phase 12.
  - Redaction behavior → single recursive `redact()` used as a `structlog` processor and at
    the one mutation path; pattern set + exact-known-value replacement; labeled
    `[redacted:<label>]` placeholder.
- **Schema-shaping decisions** recorded per the ROADMAP Phase 1 Note: retry counters as
  explicit columns; `base_branch` / `working_branch` columns present but unused;
  `artifacts` table is references-only and not created until Phase 4.

## Deferred Ideas

- Rich per-role pipeline view in `status` — Phase 12.
- `resume --answer`, `WAITING_HUMAN`, safe process release — Phase 2.
- Postgres lease / single-owner concurrency / heartbeat — Phase 2.
- Config-driven `workflow.roles` YAML + per-run config snapshot — Phase 3.
- `spec:` loader — Phase 4; `github:` loader — Phase 10.
- `ArtifactReference` persistence + artifact files — Phase 4; cross-machine artifact travel — Phase 5.
- Full `run_events` catalog + `runs` / `events` / `artifacts` subcommands — Phase 12.
- Enforcement of feedback-loop iteration caps — Phase 9.
