# Phase 12: Observability & Audit Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-03
**Phase:** 12-Observability & Audit Surface
**Areas discussed:** Full status view depth, runs/artifacts command design, events command design, missing event emission + redaction proof

---

## Full status view depth

| Option | Description | Selected |
|--------|-------------|----------|
| Full detail in text too | Text view grows to a multi-section report (run header, per-role history, artifacts, questions/answers, gate results, errors, PR info); `--json` carries the same data structured. | ✓ |
| Compact text, full detail only in JSON | Text stays near today's short field list; full detail only via `--json`. | |
| Tiered: compact default, `--verbose` for full text | Add a verbosity flag; default compact, `-v` for full report. | |

**User's choice:** Full detail in text too.
**Notes:** Followed by a rendering sub-question.

### Rendering sub-question

| Option | Description | Selected |
|--------|-------------|----------|
| Use `rich` tables/trees | Typer already bundles rich; use Table/tree/panel layout, matching the tech stack doc's stated intent. | ✓ |
| Plain-text aligned columns | No rich styling; simpler to diff in tests/CI logs. | |

**User's choice:** Use `rich` tables/trees.
**Notes:** User declined the optional follow-up on errors/PR-info panel styling specifics and moved on — left to planner/executor discretion.

---

## `runs` / `artifacts` command design

### `runs` command

| Option | Description | Selected |
|--------|-------------|----------|
| Table: id, status, source, created, updated — newest first, `--status` filter | Rich table sorted by created_at DESC; `--status` filters to one status. | ✓ |
| Minimal: just id + status, no filtering | Smallest useful listing, no sort/filter options. | |

**User's choice:** Table with `--status` filter.

### `artifacts` command

| Option | Description | Selected |
|--------|-------------|----------|
| List metadata + `--show <artifact-id>` to print content | Lists ArtifactReference metadata; `--show` reads filesystem content and prints it (redacted). | ✓ |
| Metadata listing only | No content display; user follows the filesystem path shown. | |

**User's choice:** Metadata + `--show`.
**Notes:** User declined the optional follow-up on pagination for long-running runs and moved on — left as a deferred/unresolved sizing question for the planner.

---

## `events` command design

| Option | Description | Selected |
|--------|-------------|----------|
| Chronological text list + `--json` + `--type` filter | One line per event in seq order by default; `--json` for the full array; `--type` filters to specific event types. | ✓ |
| JSON-only, no text rendering | Always emit raw JSON rows; no human-readable default. | |

**User's choice:** Chronological text + `--json` + `--type` filter.
**Notes:** User declined the optional follow-up on `--role`/`--since`/`--until` filters and moved on — not locked in, noted as deferred.

---

## Missing event emission + redaction proof

### ARTIFACT_CREATED emission point

| Option | Description | Selected |
|--------|-------------|----------|
| Wherever an ArtifactReference row is written | One event per artifact row, in the same transaction as the insert. | ✓ |
| Only for "final" artifacts per role | Skip intermediate files; only emit for canonical role output artifacts. | |

**User's choice:** Wherever an ArtifactReference row is written.

### QA_FAILED/QA_PASSED relationship to existing events

| Option | Description | Selected |
|--------|-------------|----------|
| Emit alongside ROLE_COMPLETED | Purpose-built event in addition to the generic role event — mirrors QUALITY_GATE_*/ROLE_BOUNCED precedent. | ✓ |
| Replace ROLE_COMPLETED for QA role | Emit QA_FAILED/QA_PASSED instead of the generic event for QA specifically. | |

**User's choice:** Emit alongside ROLE_COMPLETED.

### SC4 secret-redaction proof design

| Option | Description | Selected |
|--------|-------------|----------|
| Seeded fake creds run through FakeWorker + FakeGitHub, grep all surfaces | Full integration test: realistic fake secrets, drive a run to completion, assert zero occurrences across artifacts/events/logs/GitHub comments/test reports. | ✓ |
| Unit-level: assert redact() catches known patterns | Table-driven unit tests against `redact()` only; no full end-to-end run. | |

**User's choice:** Full integration test reusing existing fakes.

---

## Claude's Discretion

- Exact `rich` table column widths / box style.
- Exact short-payload-summary format for `events` text lines per event type.
- Whether `runs`/`artifacts` need `--limit`/pagination flags.
- Specific presentation of the errors/PR-info section within the full status report (dedicated panel vs inline field).
- `--role`/`--since`/`--until` filters on `events` — not locked in as scope.

## Deferred Ideas

- `--limit`/pagination for `runs`/`artifacts` commands.
- Additional `events` filters beyond `--type` (`--role`, `--since`, `--until`).
- Dedicated error/PR-info panel styling in `status` — content is locked, presentation is not.
