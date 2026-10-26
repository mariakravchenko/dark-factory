# Phase 4: The Four-Role Pipeline & Artifact Handoffs - Context

**Gathered:** 2026-09-12
**Status:** Ready for planning

<domain>
## Phase Boundary

BA → Architect → Developer → QA execute in sequence on `FakeWorker`, communicating only through durable, schema-validated artifacts on the filesystem plus `ArtifactReference` metadata rows in Neon — never a shared agent conversation. Each role's context is built fresh per attempt from an explicit, config-declared set of prior artifacts (never the whole repo, never a stale attempt). The QA role's `verdict.json` is the sole machine input to the transition after QA; free-form prose never drives it. Retry/bounded-feedback loops on a QA FAIL (Developer bounce) are explicitly out of scope — that is Phase 9.

</domain>

<decisions>
## Implementation Decisions

### Context selection per role (CTX-01–CTX-04)
- **D-01:** Add an explicit `inputs: list[str]` field to `RoleDefinition` (mirrors the existing `outputs`/`examples` fields) naming exactly which prior artifacts a role consumes. `ContextBuilder` reads this list rather than assuming a fixed "role N sees role N-1" convention. — **Reversibility:** costly — changing this later means migrating every role YAML and the `ContextBuilder` selection logic together.
- **D-02:** Every role's `RoleContext` always includes a fixed baseline set — README/AGENTS.md/CLAUDE.md and the repo-level constraints — in addition to whatever `inputs` selects. This baseline is not repeated in each role YAML.
- **D-03:** Artifacts are scoped to one attempt via `ArtifactReference.role_execution_id`, reusing the existing per-attempt `RoleExecution` row pattern from Phases 1–2. `ContextBuilder` only ever reads artifacts belonging to the latest `COMPLETED` `role_execution` per role, so a superseded attempt's artifacts are never queried (satisfies CTX-04 by construction, not by filtering after the fact).

### verdict.json shape & pass/fail semantics (ROLE-04, ROLE-06)
- **D-04:** `verdict.json` carries a per-criterion array (criterion id, PASS/FAIL, notes) plus a separate `issues` list with a `severity` field (`blocking`/`minor`). Overall status is PASS only if every criterion is PASS **and** no blocking issue exists; any criterion FAIL or blocking issue ⇒ overall FAIL.
- **D-05:** `acceptance_criteria.json` (BA's output) is a list of `{id, description}` objects with a stable string id (e.g. `AC-1`). `verdict.json`'s per-criterion entries reference the same id — never positional-index matching — so the two files stay aligned even if criteria are reordered or filtered between BA and QA.
- **D-06:** Within Phase 4's scope, the run advances past QA regardless of verdict PASS or FAIL — Phase 4 only needs the transition to be *decided by* `verdict.json` rather than agent prose, not to *act differently* on FAIL. The FAIL → Developer bounce is explicitly deferred to Phase 9's bounded feedback loops (ORCH-04 context, not this phase's success criteria).

### Fake-worker script realism for the four roles
- **D-07:** Phase 4 fixtures script `FakeWorker` with minimal but schema-valid placeholder content per role (e.g., "Criterion AC-1 met" rather than task-aware prose). The phase is testing durable handoff plumbing and schema validation, not content quality — realistic content only matters once Phase 7 wires a real Claude Code worker.
- **D-08:** All four roles share the single `fake` worker entry in `WorkerRegistry` (role ≠ worker, consistent with the Phase 1 precedent). Tests differentiate role behavior purely by which script is wired into `FakeWorker` (via `DARK_FACTORY_FAKE_SCRIPT` or direct construction) — the worker itself never branches on role.

### Schema-violation failure behavior (ART-02, ROLE-06)
- **D-09:** A machine artifact that fails validation persists a `FAILED` `role_execution` + a `run_events` error entry and transitions the run to `FAILED` immediately — no in-process re-ask/retry. That shape mirrors the existing worker-failure path already in the orchestrator. Any bounded retry belongs to Phase 9.
- **D-10:** Each machine artifact type (`acceptance_criteria.json`, `constraints.json`, `implementation_summary.json`, `test_report.json`, `verdict.json`) gets its own pydantic model in a new domain module (e.g. `dark_factory.domain.artifacts`), following the existing `WorkerResult`/`ArtifactRef` pattern (`frozen`, `extra="forbid"`). Validation is `Model.model_validate(json_content)`; a `ValidationError` is caught and turned into the persisted failure from D-09. No standalone JSON Schema files, no new validation dependency.

### Claude's Discretion
- Exact query mechanism ContextBuilder uses to find "the latest COMPLETED role_execution per role" (D-03) — left to planning as long as CTX-04 holds.
- Whether `inputs` entries name a role (e.g. `"BA"`, meaning "that role's declared outputs") or a literal artifact path — planner/researcher to resolve against what keeps `RoleDefinition` simplest.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — ORCH-04, ROLE-01–ROLE-04, ROLE-06, CTX-01–CTX-04, ART-01–ART-03, STATE-05, INTAKE-02 (this phase's full requirement set)
- `.planning/ROADMAP.md` §"Phase 4: The Four-Role Pipeline & Artifact Handoffs" — goal, success criteria, invariants ("roles hand off through artifacts, never a shared conversation"; "the ContextBuilder never walks the source tree")

### Existing domain/config contracts this phase extends
- `src/dark_factory/domain/worker.py` — `WorkerResult`, `ArtifactRef` (shape only, no persistence yet), `WorkerCapabilities` — the pattern new artifact-type models (D-10) must follow (`frozen=True, extra="forbid"`)
- `src/dark_factory/config/loader.py` — `RoleDefinition` (`outputs`, `examples`, `permissions.write_scope`, `before`/`after` hooks) — where the new `inputs` field (D-01) is added
- `src/dark_factory/config/repo_config.py` — `_LEGAL_ROLE_STATUSES`/`_LEGAL_ROLE_VALUES` — the role-name ↔ `RunStatus` mapping that Architect/Developer/QA role YAMLs must respect
- `src/dark_factory/orchestrator/runner.py` — `_build_context` (current minimal `RoleContext` dict, to be replaced/extended by `ContextBuilder`), `_role_definition` (snapshot lookup pattern), `_run_current_role`
- `src/dark_factory/persistence/models.py` — existing `Run`, `RoleExecution`, `RunEvent`, `HumanInteraction` ORM classes; docstring at top already names the target `ArtifactReference` shape (`id, run_id, role_execution_id, type, path, checksum, metadata, created_at`) — this phase adds that table (STATE-05, ART-03)
- `src/dark_factory/workers/fake.py` — `FakeWorker` scripting mechanism (`DARK_FACTORY_FAKE_SCRIPT`, constructor `script` arg) reused per D-07/D-08
- `src/dark_factory/roles/registry.py` — `Role` dataclass, `ba_role`; this phase adds Architect/Developer/QA role definitions alongside it

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WorkerResult`/`ArtifactRef` pydantic pattern (`domain/worker.py`) — template for the new per-artifact-type models (D-10).
- `RoleDefinition` (`config/loader.py`) already has `outputs: list[str]` and `examples: list[str]` fields — `inputs` (D-01) is a natural sibling addition, not a new concept.
- `_role_definition()` in `orchestrator/runner.py` is already a pure data lookup by role value on the persisted snapshot — the pattern `ContextBuilder` should follow (no role-name branching).
- Attempt tracking already exists via `RoleExecution` rows and `state.latest_execution.attempt` — D-03's per-attempt artifact scoping builds directly on this, no new attempt-tracking mechanism needed.

### Established Patterns
- Role ≠ Worker is enforced throughout (Phase 1 docstring, `WorkerRegistry`) — D-08 (single shared `fake` worker) continues this rather than introducing per-role worker variants.
- Config validation fails loudly with `ConfigError` before any run/row is created (`config/loader.py`) — the new artifact-type validation (D-10) should fail the same way: loud, typed, no silent defaults.
- `frozen=True, extra="forbid"` on every pydantic boundary model (`domain/worker.py`, `config/repo_config.py`) — apply the same to the new artifact-type models.

### Integration Points
- `_build_context()` (runner.py:122) is the current context-assembly point; `ContextBuilder` (CTX-01) either replaces or wraps this function.
- No `ArtifactReference` ORM class exists yet in `persistence/models.py` — this phase adds it plus an Alembic migration.
- No JSON-schema/pydantic artifact-type models exist yet — this phase adds `dark_factory.domain.artifacts` (or similar) per D-10.

</code_context>

<specifics>
## Specific Ideas

No particular content examples given for requirements.md/design.md — user confirmed minimal schema-valid placeholder text is the right level of realism for this phase (D-07).

</specifics>

<deferred>
## Deferred Ideas

- **QA-FAIL → Developer bounce / bounded retry loop** — explicitly Phase 9 ("Independent Quality Gate & Bounded Feedback Loops"). Phase 4 only requires the post-QA transition to be *decided by* `verdict.json`, not to branch behavior on it.
- **In-process re-ask on schema violation** — considered and rejected for Phase 4 (D-09); any retry-before-fail behavior belongs with Phase 9's bounded feedback loops.

### Reviewed Todos (not folded)
None — `.planning/todos/pending/` was empty at discussion time.

</deferred>

---

*Phase: 4-The Four-Role Pipeline & Artifact Handoffs*
*Context gathered: 2026-09-12*
