# Phase 12: Observability & Audit Surface - Context

**Gathered:** 2026-10-03
**Status:** Ready for planning

<domain>
## Phase Boundary

For any run, Dark Factory can say exactly where it is and retell everything
that happened to it. This phase closes the CLI surface (`runs`, `artifacts`,
`events`, and a materially deeper `status`) and the event-catalog gaps
(`ARTIFACT_CREATED`, `QA_FAILED`, `QA_PASSED`) left open by prior phases, and
proves end-to-end that no credential ever surfaces across that surface.

Requirements: OBS-01, OBS-02, OBS-03, TRIG-02, TRIG-03.

</domain>

<decisions>
## Implementation Decisions

### Status view depth and rendering
- **D-01:** The default text `status <run>` view carries the same full detail
  as `--json` — run header, per-role history (role, worker, attempt, status),
  artifacts, questions/answers, quality-gate results, errors, and PR info.
  There is no separate compact/verbose tier; `--json` differs only in
  serialization, not in content.
- **D-02:** The full status report is rendered with `rich` (tables for
  per-role history, panels/tree for the overall layout) rather than plain
  aligned text. `rich` already arrives transitively via Typer and the tech
  stack doc calls this out as the intended use.

### `runs` command
- **D-03:** `dark-factory runs` is a `rich` table of id, status, source,
  created_at, updated_at, sorted by `created_at DESC` (most recent first).
  Supports `--status <STATUS>` to filter to one status (e.g. only
  `WAITING_HUMAN` or `FAILED` runs) — the common operator question is "what
  needs my attention."

### `artifacts` command
- **D-04:** `dark-factory artifacts <run>` lists `ArtifactReference` metadata
  only (id, type, role, path, created_at) — consistent with "Neon is not a
  document store." A `--show <artifact-id>` flag reads the actual file from
  the filesystem artifact store and prints its content to stdout, passed
  through the same redaction path as `status`/`events` (never raw).

### `events` command
- **D-05:** `dark-factory events <run>` defaults to a chronological
  human-readable list — one line per event in `seq` order (seq, timestamp,
  type, short payload summary) — including every `ROLE_BOUNCED` cycle in a
  feedback loop. `--json` emits the full array of event rows (shape mirrors
  the `run_events` columns). `--type <EventType>` filters to one or more
  event types for focused debugging. Both text and JSON paths run through the
  redaction processor.

### Missing event emission points
- **D-06:** `ARTIFACT_CREATED` is emitted in the same transaction as every
  `ArtifactReference` insert (i.e. wherever `store_role_artifacts` or
  equivalent action writes a row) — one event per artifact row. This follows
  the existing pattern in `persistence/mutations.py` of pairing a state
  mutation with its event in the same transaction; it does not special-case
  "final" vs "intermediate" artifacts.
- **D-07:** `QA_FAILED` / `QA_PASSED` are emitted **alongside** (not instead
  of) `ROLE_COMPLETED` when the QA role's `verdict.json` is processed — the
  same precedent `QUALITY_GATE_PASSED/FAILED` and `ROLE_BOUNCED` already set
  in `events/catalog.py`: a purpose-built event in addition to the generic
  role event, so no existing consumer of `ROLE_COMPLETED` needs a new branch.
  `QA_FAILED`/`QA_PASSED` speak to the acceptance-criteria verdict;
  `QUALITY_GATE_*` stays about the independent command re-run — they are
  deliberately distinct signals in the same event stream.

### Secret-redaction end-to-end proof (SC4)
- **D-08:** The SC4 proof is a full integration test, not a redaction-unit
  test. Settings are populated with realistically-shaped fake credentials
  (a fake `GITHUB_TOKEN`, a fake `DATABASE_URL`, a fake worker API key) via
  the existing `FakeWorker`/`fake_github.py` test doubles. Drive one run to
  completion (including a publish step), then assert none of the raw secret
  strings appear in: artifact files on disk, `run_events` payloads read back
  from Neon, captured log output, `fake_github`'s recorded comment bodies,
  and `test_report.json`. Reuses existing fixtures
  (`fake_claude_cli.py`, `fake_github.py`) rather than new test
  infrastructure — this is the only way to prove the whole pipeline (not
  just `redact()` in isolation) actually calls redaction everywhere it must.

### Claude's Discretion
- Exact column widths/box style for `rich` tables.
- Exact short-payload-summary format for the `events` text line (e.g. how a
  `ROLE_STARTED` line differs from a `QUALITY_GATE_FAILED` line).
- Whether `runs`/`artifacts` need `--limit`/pagination flags — not raised as
  a blocking gray area; left to the planner/researcher to size based on
  realistic run/artifact counts in this project's own test fixtures.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/REQUIREMENTS.md` §Observability (OBS-01/02/03), §Triggers & CLI
  (TRIG-02/03) — the locked requirement text for this phase.
- `.planning/ROADMAP.md` §Phase 12 — goal, success criteria, invariants
  ("read models never mutate anything; the event log stays audit-only and is
  never used to compute control state").

### Existing code this phase extends (not replaces)
- `src/dark_factory/cli.py` — existing `run`/`resume`/`status` Typer commands
  and their output-contract conventions (exit codes, `_route_logs_to_stderr`,
  redaction wiring via `functools.partial(redact, known_secrets=...)`). New
  `runs`/`artifacts`/`events` commands must follow the same conventions.
- `src/dark_factory/observability/status.py` — `read_status`/`RunView`; the
  module-level docstring states the architectural rule this phase must keep:
  no query against `run_events`, no import from `dark_factory.events`, no
  writes. Expanding `RunView` to carry per-role history/artifacts/questions/
  gate results/errors/PR info must preserve this boundary (it becomes
  additional `runs`/`role_executions`/`artifacts`/`human_interactions`/event
  reads composed at the CLI or a new read-model layer, not a status rewrite
  that folds the event log).
- `src/dark_factory/events/catalog.py` — `EventType` enum and its docstring,
  which explicitly defers `ARTIFACT_CREATED`, `QA_FAILED`, `QA_PASSED` to
  this phase and states the "not-yet-reachable types are deliberately not
  pre-declared" rule — any new member added here must be genuinely emitted
  by this phase's code.
- `src/dark_factory/events/redaction.py` — `redact()` and the known-secrets
  pattern table; the CLI's existing `functools.partial(redact, ...)` call
  site is the template for the new `runs`/`artifacts --show`/`events`
  commands.
- `src/dark_factory/persistence/mutations.py` — the pattern of writing a
  state mutation and its `RunEvent` in the same transaction (`EventWrite`);
  `ARTIFACT_CREATED` emission must follow this, not a separate best-effort
  write.
- `src/dark_factory/persistence/models.py` — `RunEvent`/`Run`/
  `RoleExecution`/`HumanInteraction`/`ArtifactReference` ORM models backing
  every new read.
- `tests/integration/test_status_cli.py` — existing CLI output-contract
  tests; new commands' tests should sit alongside this file.
- `tests/support/fake_github.py`, `tests/support/fake_claude_cli.py` —
  fixtures the SC4 redaction-proof test reuses rather than building new
  fakes.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `functools.partial(redact, known_secrets=get_settings().known_secret_values())`
  (cli.py) — the exact redaction call-site pattern to reuse for `runs`,
  `artifacts --show`, and `events`.
- `rich` (transitive via Typer) — not yet used directly in `cli.py`; this
  phase introduces its first direct use for tables/panels.
- `tests/support/fake_github.py` / `fake_claude_cli.py` / `fake_hermes_cli.py`
  / `fake_copilot_cli.py` — existing worker/GitHub fakes to drive a full run
  in the SC4 proof test without real network/API calls.

### Established Patterns
- Every state mutation pairs with a `RunEvent` written in the same
  transaction (`persistence/mutations.py`'s `EventWrite`) — the pattern
  `ARTIFACT_CREATED` must follow.
- A purpose-built event is emitted *in addition to* the generic `ROLE_*`
  event, never instead of it (`QUALITY_GATE_*`, `ROLE_BOUNCED` precedent) —
  the pattern `QA_FAILED`/`QA_PASSED` must follow.
- Read-only observability modules (`observability/status.py`) are
  structurally forbidden from importing `dark_factory.events` or querying
  `run_events`, enforced by an import-graph test
  (`tests/unit/test_status_import_graph.py`-style). Any new read-model code
  for the expanded status view needs the same enforcement.
- CLI commands exit 2 for "nothing persisted / bad invocation", never let an
  unhandled exception escape as a raw traceback for known error types.

### Integration Points
- `cli.py` — where `runs`, `artifacts`, `events` Typer commands get added
  alongside `run`/`resume`/`status`.
- `observability/status.py` (or a new sibling module) — where the expanded
  `RunView` / new read functions for per-role history, artifacts, questions,
  gate results, PR info are composed.
- Wherever `store_role_artifacts` (or equivalent) writes `ArtifactReference`
  rows — `ARTIFACT_CREATED` emission point.
- Wherever the orchestrator processes QA's `verdict.json` — `QA_FAILED`/
  `QA_PASSED` emission point, alongside the existing `ROLE_COMPLETED`.

</code_context>

<specifics>
## Specific Ideas

No specific UI/visual references beyond "use `rich` the way the tech stack
doc already calls for." No specific wording requirements for event summary
lines — left to Claude's discretion (see above).

</specifics>

<deferred>
## Deferred Ideas

- **`--limit`/pagination for `runs`/`artifacts`** — not decided as in-scope
  or out-of-scope; left for the planner to size against realistic fixture
  counts rather than speculatively building it now.
- **`--role`/`--since`/`--until` filters on `events`** — only `--type` is
  locked in; additional filters were raised but not pursued as a blocking
  decision for this discussion.
- **Dedicated error/PR-info panel styling in `status`** — the content is
  locked (errors and PR info are part of the full report), but the specific
  presentation (dedicated panel vs inline field) was not drilled into
  further; left to the planner/executor.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (`todo.match-phase` found no
candidates).

</deferred>

---

*Phase: 12-Observability & Audit Surface*
