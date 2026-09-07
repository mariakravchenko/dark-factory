# Phase 1: Walking Skeleton — One Durable Run - Context

**Gathered:** 2026-09-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the durable-run tracer. `dark-factory run text:"..."` deterministically
classifies the source as text, loads it into one `NormalizedTask`, creates a `runs` row in
Neon, and drives the run through a **single role executed by `FakeWorker`** (zero external
AI) to a terminal state. The complete lifecycle lives in Neon (`runs`, `role_executions`,
`run_events`); a brand-new process with no in-memory carryover continues any run from its
last committed step via `dark-factory resume <run-id>`. `dark-factory status <run-id>`
reports position read from state columns, never recomputed from the event log. Secret
redaction is wired into the first persistence code.

**Not in this phase:** GitHub (intake, comments, publishing), real worker adapters, the
independent quality gate, config-driven pipeline / YAML, isolated worktree + git lifecycle,
human pause/resume (`WAITING_HUMAN`, `--answer`), Postgres lease / single-owner concurrency,
`ArtifactReference` persistence and artifact file writes.

</domain>

<decisions>
## Implementation Decisions

### CLI drive & resume surface (discussed)

- **D-01:** `dark-factory run text:"..."` blocks until the run reaches a terminal state. It
  creates the `runs` row (status `CREATED`), prints the run id on its own line to stdout
  immediately (so a killed process is still recoverable), then loops the resume-first
  `advance(run_id)` entrypoint until `COMPLETED` or `FAILED`.
- **D-02:** `advance(run_id)` is the single orchestrator entrypoint and is always
  resume-first: it reconstructs all state from Neon on every call, executes exactly one
  step, commits through the one mutation path, and returns the new state. `run` and
  `resume` are both thin wrappers around a drive loop over `advance(run_id)`.
  — **Reversibility:** costly — this is the spine of the durability thesis; changing the
  entrypoint shape later touches every lifecycle path and every trigger in Phases 2–12.
- **D-03:** `dark-factory resume <run-id>` ships in Phase 1 with **no** `--answer` argument
  — it runs the same drive loop as `run`. Phase 2 extends the *same* command with
  `--answer "..."` for human replies. There is no separate `advance` CLI command.
- **D-04:** `run` and `resume` emit: run id on its own first line, then one line per state
  transition (`CREATED → BA`, `BA → COMPLETED`), then a short final summary block (run id,
  terminal state, last role, attempt). Plain text. Machine-readable detail is left to
  `status` / `events`.
- **D-05:** Exit codes for `run` / `resume`: `0` when the run reaches `COMPLETED`; `1` when
  the run reaches `FAILED` (a real, persisted terminal delivery failure); `2` for bad
  invocation (unresolvable input, unknown run-id, config/validation error — nothing
  persisted or advanced). — **Reversibility:** costly — the Phase 11 CI trigger and any
  operator scripts will encode these three codes.
- **D-06:** In Phase 2+, the same drive loop additionally halts (exit `0`) when the run
  reaches `WAITING_HUMAN`. Recorded now so the loop's stop-condition set is designed with
  that seam in mind.

### Skeleton role & state path (Claude's discretion — settled from spec + roadmap)

- **D-07:** The Phase-1 pipeline is the single **real** role **Business Analyst (`BA`)** —
  not a synthetic placeholder, not Developer. Rationale: BA is first in the real pipeline,
  is read-only on repository source (no worktree/git needed — that is Phase 5), and makes
  the run genuinely occupy the `BA` status value from STATE-07. Phase 4 then *adds*
  Architect / Developer / QA rather than replacing a stub. — **Reversibility:** costly —
  later phases assume `BA` is the first role and that the run-status enum was exercised for
  real from Phase 1.
- **D-08:** Happy-path state sequence is `CREATED → BA → COMPLETED`. The run does not pass
  through `ARCHITECTURE` / `DEVELOPMENT` / `QA` / `VERIFYING` / `PUBLISHING` because the
  Phase-1 pipeline is literally `["BA"]`. The full STATE-07 enum is defined in code; only
  `CREATED`, `BA`, `COMPLETED`, `FAILED` are reachable in Phase 1.
- **D-09:** The one-role pipeline `["BA"]` is a hardcoded Python default in Phase 1. The
  orchestrator iterates an in-memory ordered role list that happens to have one entry — it
  must not bake in a role *count* (no "call these N roles"). Phase 3 externalises pipeline
  shape to `.dark-factory.yaml` `workflow.roles`.
- **D-10:** `FakeWorker` returns a scripted sequence of `WorkerResult`s (WORK-10). Happy
  path: one `WorkerResult(status=COMPLETED, summary=…, questions=[], artifacts=[],
  changed_files=[], worker_session_id="fake-<uuid>", metadata={})`. A scripted
  `WorkerResult(status=FAILED, …)` drives the `FAILED` terminal path and the
  crash-consistency test. `NEEDS_INPUT` is in the enum but not exercised until Phase 2.
  Phase 1 does not persist `ArtifactReference` rows or write artifact files (Phase 4/5) —
  the `artifacts` list may be empty.

### `status` output shape (Claude's discretion — settled from spec + roadmap)

- **D-11:** `dark-factory status <run-id>` reads only from state columns — the `runs` row
  plus the latest `role_executions` row for that run. It never folds `run_events` to
  compute position (SC3).
- **D-12:** Default output is a plain-text `key: value` field list: run id, source
  (redacted), status, current role, current step, latest attempt number, `created_at`,
  `updated_at` (`base_branch` / `working_branch` shown even though null until Phase 5). No
  Rich per-role pipeline visualisation — that is Phase 12.
- **D-13:** `status` supports `--json`, emitting the same fields as a single JSON object.
  Ships in Phase 1 because it makes the "position comes from columns" property cleanly
  testable and the later CI phases will consume it.

### Redaction behavior (Claude's discretion — settled from spec + roadmap)

- **D-14:** A single `redact(value) -> value` function (recursive over dict / list / str) is
  the one redaction path. Wired in two places from the first persistence code: (a) as a
  `structlog` processor on every log event, and (b) at the one lifecycle mutation path,
  applied to every JSONB payload before write (`run_events.payload`,
  `role_executions.result`, `role_executions.error`). — **Reversibility:** one-way — the
  invariant is "redaction from the first persistence code, never retrofitted"; a value that
  reaches Neon or a log file un-redacted is unrecoverable.
- **D-15:** Pattern set caught in Phase 1: (1) Postgres/DB connection URIs with credentials
  (`postgres://`, `postgresql://`, `postgresql+psycopg://`, `…user:pass@host…`);
  (2) `key=value` / `key: value` pairs whose key matches a sensitivity list (`password`,
  `passwd`, `secret`, `secret_key`, `token`, `api_key`, `apikey`, `access_key`,
  `database_url`, `github_token`, `authorization`, `bearer`); (3) GitHub token shapes
  (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` prefixes; 40-hex classic PAT in a github-ish
  context); (4) `Authorization: Bearer <…>` header values.
- **D-16:** Exact-value redaction *in addition to* pattern redaction: the
  `pydantic-settings` object (with `SecretStr` fields) is the single source of the live
  `DATABASE_URL` / `GITHUB_TOKEN` / worker-credential values; `redact()` also does
  literal-substring replacement of those known values wherever they appear. This directly
  satisfies the "grep the known secret values across artifacts / events / logs → zero
  occurrences" checks used in Phases 6 and 12.
- **D-17:** Placeholder format is a labeled token — `[redacted:database_url]`,
  `[redacted:github_token]`, `[redacted:secret]`, etc.; `[redacted]` when the label is
  unknown. Labeled rather than bare `***` so an operator can still see *what kind* of value
  was present without leaking it.
- **D-18:** Scope split. Pattern-based redaction (D-15) applies to every persisted
  `run_events.payload`, every `role_executions.result` / `error`, and every log line, per
  SEC-02 / SC5. The stored task source / persisted `NormalizedTask` is scrubbed only for
  **exact matches of the known live secret values** (D-16), not by generic pattern — so a
  task that legitimately discusses connection-string syntax keeps its wording, while a real
  leaked credential value is removed everywhere. Raw task text otherwise persists as given.

### Schema-shaping decisions (flagged by ROADMAP Phase 1 Note; enforced in later phases)

- **D-19:** Retry / feedback-loop counters are explicit integer columns — never derived by
  folding `run_events` or counting `role_executions` rows (checkpoint-not-replay
  invariant). `role_executions.attempt` covers per-role attempts (STATE-03). The two
  bounded feedback-loop counters — `qa_developer_iterations`, `quality_gate_iterations` —
  are non-null integer columns on `runs`, default `0`, incremented only in the one mutation
  path. Defined in the Phase 1 schema; enforced in Phase 9. — **Reversibility:** one-way —
  adding or moving these columns later is an Alembic migration against persisted run rows.
- **D-20:** `runs` carries `base_branch` and `working_branch` columns from the Phase 1
  schema (STATE-02 lists them), nullable, unused until Phase 5.
- **D-21:** Artifact-content durability (open decision 1) intended approach, recorded for
  schema shape only: the future `artifacts` table (Phase 4) stores `ArtifactReference`
  metadata only — `id, run_id, role_execution_id, type, path, checksum, metadata,
  created_at` — never artifact content. Content lives on the filesystem under
  `.dark-factory/runs/<run-id>/` and (Phase 5) travels between machines by being committed
  to a `.dark-factory/` path on the run's working branch, excluded from the published diff.
  Phase 1 does **not** create the `artifacts` table.
- **D-22:** `run_events` is append-only: `id, run_id, role_execution_id` (nullable)`, type,
  payload` (JSONB, redacted)`, created_at`. `type` is a string/enum drawn from the event
  catalog in PROJECT.md. Phase 1 emits at least `RUN_CREATED`, `ROLE_STARTED`,
  `ROLE_COMPLETED` / `ROLE_FAILED`, `RUN_COMPLETED` / `RUN_FAILED`. Full catalog coverage
  is Phase 12.

### Input resolver (INTAKE-01 / INTAKE-04 / INTAKE-05 — in Phase 1 scope)

- **D-23:** The resolver classifies the `text:` / `spec:` / `github:` prefix
  deterministically (prefix match, no LLM, no repo inspection, no GitHub call, no network,
  does not create a run — INTAKE-04). Phase 1 implements only the `text:` loader; the
  `spec:` (Phase 4) and `github:` (Phase 10) classification arms exist but their loaders
  raise a clean "not yet supported" error. Every source normalises to one `NormalizedTask`,
  after which the orchestrator is origin-agnostic (INTAKE-05).

### Claude's Discretion

The user delegated all four *discussed* sub-decisions (drive model, resume command shape,
`run`/`resume` output, exit codes) to Claude with "you decide". The choices recorded above
(D-01…D-06) are the decisions to implement — not loosely-held defaults.

Skeleton role & state path (D-07…D-10), `status` output (D-11…D-13), and redaction
behavior (D-14…D-18) were **not** discussed; they are settled here from the spec, roadmap,
and cross-cutting invariants at the user's explicit request ("choose the best option
without clarifying"). The planner may refine details but should treat the shape as decided.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec & scope
- `.planning/PROJECT.md` — authoritative scope summary of the 84-section technical spec;
  role boundaries, the guiding "where does this belong?" principle (§83), key decisions,
  out-of-scope list. No standalone spec file is checked into the repo — the specification
  exists only as digested into PROJECT.md and `.planning/research/`.
- `.planning/REQUIREMENTS.md` — all 89 v1 requirement IDs. Phase 1 owns INTAKE-01,
  INTAKE-04, INTAKE-05, ORCH-01, ORCH-05, ORCH-06, STATE-01, STATE-02, STATE-03, STATE-06,
  STATE-07, STATE-08, WORK-01, WORK-03, WORK-08, WORK-10, SEC-02.
- `.planning/ROADMAP.md` §"Phase 1: Walking Skeleton — One Durable Run" — goal, five
  success criteria, invariants, and the schema-shaping **Note** (artifact-durability
  strategy + retry-counter placement settled with this schema).
- `.planning/ROADMAP.md` §"Cross-Cutting Invariants" — the six invariants introduced at
  Phase 1 (single-transaction mutation path; every resume input is a persisted column;
  control state from columns not the event log; only the orchestrator mutates state;
  redaction from the first persistence code; no worker-name branching outside adapters).
- `.planning/ROADMAP.md` §"Open Decisions" — decision 1 (artifact durability) affects
  Phase 1 schema shape; decisions 2 and 3 are out of Phase 1 scope.

### Architecture & stack
- `.planning/research/ARCHITECTURE.md` — durable-run architecture, enum FSM + resume-first
  `advance(run_id)`, the one mutation path, checkpoint-not-replay.
- `.planning/research/STACK.md` — pinned stack and version-compatibility matrix (mirrored
  in `.claude/CLAUDE.md`).
- `.planning/research/PITFALLS.md` — known hazards: Neon / PgBouncer prepared statements,
  subprocess env allowlist, redaction-retrofitting, SQLModel, `os.environ.copy()`.
- `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — feature inventory and
  synthesis.
- `.claude/CLAUDE.md` — project constraints, full technology-stack table, "Alternatives
  Considered", "What NOT to Use", "Version Compatibility", suggested `src/` layout.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None. Greenfield — fresh git repo, no application code.

### Established Patterns
- None yet. Phase 1 establishes them: the one lifecycle mutation path, the `redact()`
  function + `structlog` processor, the resume-first `advance(run_id)` entrypoint, the
  `CodingWorker` / `WorkerResult` / `WorkerCapabilities` contracts, and `FakeWorker`.

### Integration Points
- Reference package layout is in PROJECT.md Context (spec §72): `dark_factory/` with
  `orchestrator/`, `workflows/`, `roles/`, `workers/`, `tools/`, `actions/`, `input/`,
  `context/`, `artifacts/`, `quality/`, `persistence/`, `integrations/`, `workspace/`,
  `events/`. Phase 1 touches `input/`, `orchestrator/`, `workers/` (FakeWorker only),
  `roles/` (BA definition), `persistence/`, `events/`, plus the Typer CLI entrypoint.
- `seed-app-new.sh` at repo root is an unrelated VibeGuard test-repo seeder — not part of
  this project; ignore or remove.

</code_context>

<specifics>
## Specific Ideas

- "Portfolio-showcase quality **and** genuinely runnable against a real repository"
  (PROJECT.md) applies directly to the CLI ergonomics decided here — the transition-line
  output (D-04) and `--json` on `status` (D-13) serve both audiences.
- The five Phase 1 success criteria in ROADMAP.md are the acceptance bar; the planner
  should map plan tasks to them one-to-one, especially SC4 (crash injected between the
  sub-writes of a transition leaves a consistent, resumable run) and SC5 (a
  `DATABASE_URL`-shaped value in task text is redacted in every persisted event payload and
  every log line).

</specifics>

<deferred>
## Deferred Ideas

- Rich per-role pipeline visualisation in `status` — Phase 12 (Observability & Audit
  Surface).
- `resume --answer "..."`, `WAITING_HUMAN`, and safe process release — Phase 2.
- Postgres lease / single-owner concurrency / heartbeat — Phase 2.
- Config-driven `workflow.roles` in YAML + per-run config snapshot on resume — Phase 3.
- `spec:` loader — Phase 4; `github:` loader + issue intake — Phase 10.
- `ArtifactReference` persistence + filesystem artifact writes — Phase 4; cross-machine
  artifact travel via committed `.dark-factory/` path — Phase 5.
- Full `run_events` catalog coverage and the `runs` / `events` / `artifacts` CLI
  subcommands — Phase 12.
- Enforcement of `qa_developer_iterations` / `quality_gate_iterations` caps — Phase 9
  (columns defined now, per D-19).

None of the above were scope-creep requests — they surfaced only as "recorded now,
implemented later" seams while settling Phase 1 decisions.

</deferred>

---

*Phase: 1-walking-skeleton-one-durable-run*
*Context gathered: 2026-09-07*
