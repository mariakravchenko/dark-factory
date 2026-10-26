# Phase 4: The Four-Role Pipeline & Artifact Handoffs - Research

**Researched:** 2026-09-12
**Domain:** Internal orchestration architecture (role pipeline, context assembly, filesystem+Postgres artifact durability) — no new external services or libraries
**Confidence:** HIGH for architecture (verified by reading every touched source file this session); MEDIUM/LOW where CONTEXT.md leaves a design open and no external authority settles it (flagged per-item below)

## Summary

Phase 4 is an **internal wiring phase**, not a new-technology phase: every dependency it needs (pydantic, SQLAlchemy, PyYAML, `hashlib`, `pathlib`) is already installed and already used in exactly the pattern this phase should extend. There is no new package to vet. The work is: (1) add Architect/Developer/QA role YAML + instructions beside the existing BA/QA fixtures, (2) add an `ArtifactReference` ORM table + Alembic migration, (3) add per-artifact-type frozen pydantic models with `Model.model_validate()` validation (D-10), (4) implement a `ContextBuilder` that resolves each role's declared `inputs` to the latest-COMPLETED artifacts of the role(s) that produced them, and (5) make `spec:` a real loader (INTAKE-02).

The single highest-risk design gap this research surfaces — not resolved by CONTEXT.md's D-01..D-10 — is **how a `before`/`after` action hook's output reaches back into `_run_current_role`**. Today `ActionRegistry` callables return `None` and are pure side-effecting no-ops (`prepare_role_context` and `store_role_artifacts` are literally `return None` today, per their own docstrings marking them "No-op until Phase 4"). But `ContextBuilder`'s output must reach `worker.execute(context)`, and `store_role_artifacts`'s artifact rows must land in the *same transaction* as the role's `COMPLETED`/`FAILED` status (the project's own "no state change exists without its audit trail" discipline, applied here as "no artifact reference exists without its role_execution's committed status"). Section "Architecture Patterns" below gives a concrete, minimally-invasive recommendation; the planner should treat it as the load-bearing decision of this phase's Wave 0.

The two explicitly-requested discretion questions are answered concretely below (Architecture Patterns, Patterns 2 and 3): (1) the "latest COMPLETED role_execution per role" query is a plain filtered/ordered/`LIMIT 1` select — no window function needed because it is always scoped to one `(run_id, role)` pair, and `uq_role_exec_attempt` already makes `attempt DESC` a total order within that scope; (2) `RoleDefinition.inputs` entries should name **literal artifact filenames** (mirroring `outputs`' existing shape exactly), not role names, because the config snapshot's `outputs` lists already give `ContextBuilder` a free, in-memory filename→producing-role map with zero new schema.

**Primary recommendation:** Do the context build and the artifact validation+persistence as direct function calls inside `orchestrator/runner.py::_run_current_role` (new pure helper modules under `dark_factory/context/` and `dark_factory/artifacts/`), not as opaque action-hook side effects — keep the `before`/`after` hook mechanism (CFG-04) for genuinely optional/pluggable steps, and treat `prepare_role_context`/`store_role_artifacts` as the two hook *names* whose real logic is now implemented (per their docstrings) but invoked from the runner directly, with the hook list becoming a place for *additional* future custom actions.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Role sequencing (BA→Architect→Developer→QA) | Orchestrator (`orchestrator/runner.py`, pure `lifecycle.transition`) | Database (`role_executions`, `runs.current_role`) | ORCH-01/02/05: only the deterministic orchestrator computes "what next"; a worker result is mapped to a `Signal`, never interpreted for its prose. |
| Role behavior (instructions, tools, outputs, `inputs`) | Configuration (`.dark-factory/roles/*.yaml`, `RoleDefinition`) | Database (`runs.workflow` snapshot) | CFG-02/03/05: fully config-driven, snapshotted at run creation so a later resume is deterministic even if the YAML changed. |
| Context assembly (CTX-01..04) | New `dark_factory/context/` module, called from `orchestrator/runner.py` | Database (read-only: `role_executions`, new `artifacts` table) + Filesystem (read-only: artifact content, README/AGENTS.md/CLAUDE.md) | CTX-02 forbids walking the repo tree; the builder does named, bounded reads only — it is orchestration-adjacent logic, not a role's own work. |
| Artifact content | Filesystem (`.dark-factory/runs/<run-id>/artifacts/<role>/`) | — | ART-01/ART-03 + `persistence/models.py` docstring (already written, pre-Phase-4): "Neon stores metadata only... content lives on the filesystem." `.gitignore` already excludes `.dark-factory/runs/` in anticipation of this phase. |
| Artifact reference (metadata) | Database (new `artifacts` table / `ArtifactReference` ORM) | — | STATE-05/ART-03; written through the single mutation path (`persistence/mutations.py`), same discipline as every other lifecycle row. |
| Machine-artifact schema validation | New `dark_factory/domain/artifacts.py` (pydantic) | Orchestrator (invokes it, decides FAILED on `ValidationError`) | D-10/D-09/ART-02: JSON contracts are authoritative; a schema violation is a role failure, not a warning. |
| QA verdict → transition decision | Orchestrator (signal computed from `WorkerResult.status`, never `verdict.json` prose) | `verdict.json` schema validation (above) | D-06: in Phase 4's scope the run advances past QA regardless of PASS/FAIL — "decided by verdict.json" is satisfied by schema validation gating the transition, not by branching on the verdict's content (that branch is Phase 9). |
| `spec:` task intake | `input/loaders.py::_load_spec` | Filesystem (read the spec file) | INTAKE-02; mirrors the already-shipped `_load_text` shape exactly. |

## User Constraints

<user_constraints>
### Locked Decisions (verbatim from 04-CONTEXT.md)

- **D-01:** Add an explicit `inputs: list[str]` field to `RoleDefinition` (mirrors the existing `outputs`/`examples` fields) naming exactly which prior artifacts a role consumes. `ContextBuilder` reads this list rather than assuming a fixed "role N sees role N-1" convention. — **Reversibility:** costly.
- **D-02:** Every role's `RoleContext` always includes a fixed baseline set — README/AGENTS.md/CLAUDE.md and the repo-level constraints — in addition to whatever `inputs` selects. This baseline is not repeated in each role YAML.
- **D-03:** Artifacts are scoped to one attempt via `ArtifactReference.role_execution_id`, reusing the existing per-attempt `RoleExecution` row pattern from Phases 1–2. `ContextBuilder` only ever reads artifacts belonging to the latest `COMPLETED` `role_execution` per role, so a superseded attempt's artifacts are never queried (satisfies CTX-04 by construction, not by filtering after the fact).
- **D-04:** `verdict.json` carries a per-criterion array (criterion id, PASS/FAIL, notes) plus a separate `issues` list with a `severity` field (`blocking`/`minor`). Overall status is PASS only if every criterion is PASS **and** no blocking issue exists; any criterion FAIL or blocking issue ⇒ overall FAIL.
- **D-05:** `acceptance_criteria.json` (BA's output) is a list of `{id, description}` objects with a stable string id (e.g. `AC-1`). `verdict.json`'s per-criterion entries reference the same id — never positional-index matching.
- **D-06:** Within Phase 4's scope, the run advances past QA regardless of verdict PASS or FAIL — Phase 4 only needs the transition to be *decided by* `verdict.json` rather than agent prose, not to *act differently* on FAIL. The FAIL → Developer bounce is deferred to Phase 9.
- **D-07:** Phase 4 fixtures script `FakeWorker` with minimal but schema-valid placeholder content per role. The phase tests durable handoff plumbing and schema validation, not content quality.
- **D-08:** All four roles share the single `fake` worker entry in `WorkerRegistry` (role ≠ worker). Tests differentiate role behavior purely by which script is wired into `FakeWorker` — the worker itself never branches on role.
- **D-09:** A machine artifact that fails validation persists a `FAILED` `role_execution` + a `run_events` error entry and transitions the run to `FAILED` immediately — no in-process re-ask/retry. Any bounded retry belongs to Phase 9.
- **D-10:** Each machine artifact type gets its own pydantic model in `dark_factory.domain.artifacts` (or similar), following the existing `WorkerResult`/`ArtifactRef` pattern (`frozen`, `extra="forbid"`). Validation is `Model.model_validate(json_content)`; a `ValidationError` is caught and turned into the persisted failure from D-09. No standalone JSON Schema files, no new validation dependency.

### Claude's Discretion (resolved by this research — see Architecture Patterns 2 & 3)

- Exact query mechanism `ContextBuilder` uses to find "the latest COMPLETED role_execution per role" (D-03).
- Whether `inputs` entries name a role or a literal artifact path.

### Deferred Ideas (OUT OF SCOPE)

- QA-FAIL → Developer bounce / bounded retry loop — Phase 9.
- In-process re-ask on schema violation — rejected for Phase 4 (D-09); any retry-before-fail behavior belongs with Phase 9.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORCH-04 | Roles communicate through durable artifacts, not one shared agent conversation | Architecture Pattern 1 (filesystem+Neon handoff); `_build_context` never receives a prior role's raw `WorkerResult`, only `ContextBuilder`-selected artifact content |
| ROLE-01 | BA emits `requirements.md` + `acceptance_criteria.json`; read-only on source | New `.dark-factory/roles/BA.yaml` already exists and already declares `outputs: [requirements.md, acceptance_criteria.json]` — no source-write tools granted |
| ROLE-02 | Architect consumes task+BA output+repo, emits `design.md` + `constraints.json`; read-only on source | New `ARCHITECTURE.yaml` with `inputs: [acceptance_criteria.json]` (or `requirements.md` too, planner's call) |
| ROLE-03 | Developer implements, emits `implementation_summary.json`; may modify code+tests | New `DEVELOPMENT.yaml`; Phase 4 has no git worktree (Phase 5) so "modifies code" is not yet enforced/exercised — `FakeWorker` only emits the JSON artifact this phase |
| ROLE-04 | QA independently verifies criteria, emits `test_report.json` + `verdict.json` | `.dark-factory/roles/QA.yaml` already exists (`outputs: [test_report.json, verdict.json]`); needs `inputs` added |
| ROLE-06 | QA verdict (not prose) is the machine input to the next decision | D-06 + Architecture Pattern 4 (schema validation gates the transition) |
| CTX-01 | `ContextBuilder` produces role-specific `RoleContext` | Architecture Pattern 1/2 |
| CTX-02 | No whole-repo dump; agent inspects the repo itself | Baseline docs are named-file reads only, reusing `config/loader.py`'s safe-path-resolution + size-cap idiom |
| CTX-03 | Few-shot examples referenced from role config are context only | `RoleDefinition.examples` already exists (Phase 3); `ContextBuilder` reads it as-is, never executes it |
| CTX-04 | Retry rebuilds context with no stale-attempt artifact leakage | D-03 query (Architecture Pattern 3) — status filter to `COMPLETED` makes this true by construction |
| ART-01 | Artifacts on filesystem under `.dark-factory/runs/<run-id>/` (`input/`, `artifacts/<role>/`, `verification/`, `logs/`) | `.gitignore` already excludes this path; `persistence/models.py` docstring already names the shape |
| ART-02 | Machine decisions are structured JSON; JSON is authoritative where orchestration depends on it | D-10 pydantic models; Markdown (`requirements.md`, `design.md`) is human-only, unvalidated |
| ART-03 | Each artifact recorded as `ArtifactReference` (id, run_id, role_execution_id, type, path, metadata, created_at) in Neon | New ORM class + migration 0004 (Architecture Pattern 5) |
| STATE-05 | An `artifacts` table persists artifact metadata | Same as ART-03 |
| INTAKE-02 | `spec:./path.md` starts a run | `input/loaders.py::_load_spec` (Code Examples) |

</phase_requirements>

## Standard Stack

### Core

No new runtime dependency is required for this phase. Everything below is already pinned in `pyproject.toml` and already used in the exact pattern this phase extends.

| Library | Version (installed) | Purpose in Phase 4 | Why Standard (for this codebase) |
|---------|---------|---------|--------------|
| pydantic | `>=2.9,<3` [VERIFIED: pyproject.toml:14] | New frozen, `extra="forbid"` models for each machine artifact type (D-10); new `RoleContext` model | Identical pattern already used for `WorkerResult`/`ArtifactRef` (`domain/worker.py`) and every config model (`config/repo_config.py`) |
| SQLAlchemy | `>=2.0.40,<2.1` [VERIFIED: pyproject.toml:11] | New `ArtifactReference` ORM class, mapped to a new `artifacts` table | Identical pattern to `RoleExecution`/`RunEvent`/`HumanInteraction` in `persistence/models.py` |
| Alembic | `>=1.19,<2` [VERIFIED: pyproject.toml:13] | New migration `0004_artifacts.py` | Same revision-chain pattern as `0001`→`0002`→`0003` |
| PyYAML | `>=6,<7` [VERIFIED: pyproject.toml:19] | Two new role YAML files (`ARCHITECTURE.yaml`, `DEVELOPMENT.yaml`) | Already the sole config format (CFG-01/02) |
| `hashlib` (stdlib) | 3.12 | Artifact content checksums | `ArtifactRef.checksum: str | None` already exists in `domain/worker.py`; no hashing library is used anywhere in this codebase today — stdlib SHA-256 is the obvious, zero-dependency choice |
| `pathlib` (stdlib) | 3.12 | All artifact filesystem paths | Already the sole path-handling idiom throughout (`config/loader.py`, `cli.py`) |

### Supporting

None new.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Model.model_validate(json_content)` per-type (D-10, locked) | A generic `TypeAdapter[Annotated[Union[...], Field(discriminator="type")]]` dispatcher [CITED: pydantic.dev/docs/validation/latest/concepts/unions/] | Discriminated unions are the idiomatic pydantic v2 way to validate "one of several JSON shapes by a tag field," but D-10 already locks per-type direct validation (the caller already knows which artifact type it expects from `role_def["outputs"]`), so a union adds indirection with no benefit here. Worth knowing about if a later phase needs a single "validate anything" entry point. |
| Plain filtered/ordered/`LIMIT 1` select for "latest COMPLETED per role" (recommended below) | A window-function (`ROW_NUMBER() OVER (PARTITION BY role ORDER BY attempt DESC)`) [CITED: general SQLAlchemy "latest row per group" pattern] | Window functions solve "the latest row for *every* group in one query." `ContextBuilder` only ever needs one role at a time (from `inputs`), so a plain per-role query is simpler and matches the existing `load_run_state` style exactly. |

**Installation:** none — no `pyproject.toml` change needed for this phase's core work.

## Package Legitimacy Audit

**Not applicable.** This phase installs no new external package. No `npm view` / `pip index versions` / registry check was needed or performed. If the plan later decides to add something (e.g. a Markdown front-matter parser), run the Package Legitimacy Gate at that time.

## Architecture Patterns

### System Architecture Diagram

```
 CLI (`dark-factory run spec:./task.md`)
   │
   ▼
 input.loaders._load_spec (INTAKE-02) ──► NormalizedTask (source_kind="spec")
   │
   ▼
 orchestrator.runner.advance() / drive()          [one committed step per call]
   │
   ├─ RunState reconstructed from Neon (unchanged Phase 1-3 machinery)
   │
   ▼
 _run_current_role(role = BA | ARCHITECTURE | DEVELOPMENT | QA)
   │
   ├──(1)── ContextBuilder.build(session, repo_root, run_id, state, role_def)
   │           │
   │           ├─ resolve role_def["inputs"] filenames → producing role
   │           │    (via state.workflow["roles"][*]["outputs"], in-memory, no query)
   │           ├─ for each producing role: SELECT latest COMPLETED role_execution
   │           │    (Pattern 3, below) → its ArtifactReference rows
   │           ├─ read matching artifact file content from
   │           │    .dark-factory/runs/<run-id>/artifacts/<role>/<filename>
   │           ├─ read baseline docs (README.md / AGENTS.md / CLAUDE.md) — named
   │           │    files only, never a directory walk (CTX-02)
   │           └─ read state.pending_answer (already on RunState)
   │         ──► RoleContext (pydantic, frozen) ──► passed to worker.execute(context)
   │
   ├──(2)── worker.execute(context) / worker.resume(...)   [FakeWorker: scripted
   │           WorkerResult + pre-written placeholder files under
   │           artifacts/<role>/ — see Pattern 6]
   │
   ├──(3)── ArtifactValidator: for each ArtifactRef the WorkerResult reports,
   │           read the file, and if role_def["outputs"] marks it a *machine*
   │           artifact (JSON), validate via the matching domain/artifacts.py
   │           model. A ValidationError here overrides the signal to ROLE_FAILED
   │           (Pattern 4) before apply_transition is ever called.
   │
   └──(4)── apply_transition(... , artifact_references=[...])   [same one
             transaction as the role_execution status write — new
             ArtifactReferenceWrite list, mirrors HumanInteractionWrite]
             │
             ▼
       Neon: role_executions row (COMPLETED|FAILED) + artifacts rows + run_events row
             (all-or-nothing, one commit)
```

A reader can trace `spec:./task.md` → `NormalizedTask` → four `_run_current_role` passes → four `(ContextBuilder read, worker call, validate, one commit)` cycles → `COMPLETED`, with artifact **content** living only in the filesystem box and artifact **references** living only in the Neon box — never both, never neither.

### Recommended Project Structure

```
src/dark_factory/
├── context/                       # NEW (CTX-01)
│   ├── __init__.py
│   └── builder.py                 # RoleContext model + build_role_context()
├── artifacts/                     # NEW (ART-01/02/03, D-10 companion I/O)
│   ├── __init__.py
│   ├── paths.py                   # run_root(), role_artifact_dir(), checksum()
│   ├── store.py                   # read/write file content, list ArtifactReference rows
│   └── validation.py              # dispatch: filename/type -> domain.artifacts model
├── domain/
│   └── artifacts.py               # NEW (D-10): per-type frozen pydantic models
├── persistence/
│   └── models.py                  # + ArtifactReference ORM class
├── roles/
│   └── registry.py                # + architect_role, developer_role, qa_role (catalog only)
└── input/
    └── loaders.py                 # _load_spec implemented (INTAKE-02)

migrations/versions/
└── 0004_artifacts.py              # NEW

.dark-factory/
├── roles/
│   ├── BA.yaml                    # existing — add inputs: []
│   ├── ARCHITECTURE.yaml          # NEW
│   ├── DEVELOPMENT.yaml           # NEW
│   └── QA.yaml                    # existing — add inputs: [...]
└── instructions/
    ├── ba.md / qa.md              # existing
    ├── architecture.md            # NEW
    └── development.md             # NEW

.dark-factory.yaml                 # workflow.roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]
```

### Pattern 1: ContextBuilder is a direct function call, not an opaque action hook

**What:** `ContextBuilder` (or a plain `build_role_context()` function) is called directly from `orchestrator/runner.py::_run_current_role`, in the same place `_build_context()` is called today (`context = _build_context(run_id, state, node)`), and its return value **is** the `context` object passed to `worker.execute(context)` / `worker.resume(...)`.

**Why this over routing it through `prepare_role_context` (the `before` action hook already named in `BA.yaml`'s `before: [prepare_role_context]`):** `ActionRegistry.get(name)` currently has type `Callable[[ActionContext], None]` [VERIFIED: src/dark_factory/actions/registry.py:30-38 — `def register(self, name: str, fn: Callable[[ActionContext], None]) -> None:`] and `_run_hooks` in `runner.py` discards whatever an action returns [VERIFIED: src/dark_factory/orchestrator/runner.py:414-427 — `_run_hooks` calls `action_registry.get(action_name)(ActionContext(...))` for side effect only, no assignment of a return value]. There is currently **no path** by which a `before` hook's output can reach the `context` variable used three lines later at `result = worker.execute(context)`. Making `prepare_role_context` "real" without changing this would require widening `ActionRegistry`'s contract to `Callable[[ActionContext], Mapping[str, Any] | None]` and threading a merge step through `_run_hooks` — a larger, riskier change to a mechanism (CFG-04) that exists for optional side-effecting hooks (git worktree prep, diff collection), not for a value the very next line depends on.

**Recommendation:** Keep `_build_context()`'s call site, but replace its body with a call into the new `context.builder.build_role_context(...)`. Leave `prepare_role_context` and `store_role_artifacts` registered in the `ActionRegistry` as **inert** (still `return None`) for now, or remove them from the two existing role YAMLs' `before`/`after` lists if their presence would mislead a future reader — either is defensible; document the choice in the plan. This keeps CFG-04's hook mechanism honest (it still only ever does fire-and-forget side effects) and keeps the one line that matters (`context = ...`) in the same well-tested function that already computes `attempt`, `role_def`, and threads `state.pending_answer`.

**Confidence:** This is original architectural reasoning grounded in verified source (the callable signatures and call sites cited above are read from the file this session), not an external authority — treat the *recommendation* as a proposal for planner sign-off, not a locked fact. [ASSUMED]

### Pattern 2: `RoleDefinition.inputs` entries are literal filenames, resolved via the snapshot's `outputs`

**Decision requested by CONTEXT.md, resolved here.**

`inputs: list[str]` entries should be **filenames** — e.g. Architect's YAML gets `inputs: [acceptance_criteria.json]` — for the same reason `outputs` already is a filename list [VERIFIED: .dark-factory/roles/BA.yaml:16 — `outputs: [requirements.md, acceptance_criteria.json]`; .dark-factory/roles/QA.yaml:15 — `outputs: [test_report.json, verdict.json]`]. `RoleDefinition` (`config/loader.py:70-83`) currently has `outputs: list[str] = Field(default_factory=list)` and `examples: list[str] = Field(default_factory=list)`, both plain filename/path lists with no special parsing [VERIFIED: src/dark_factory/config/loader.py:70-83]. Making `inputs` the same shape means:

1. `ContextBuilder` needs **zero new config vocabulary** — it resolves `inputs` against the already-persisted snapshot's `roles[*].outputs` lists (available in-memory from `state.workflow`, no query) to find which role produced a given filename, then does one query per resolved role (Pattern 3).
2. Reordering the pipeline (ORCH-03, already proven in Phase 3) does not require editing any role's `inputs` — a filename's producer is discovered from the snapshot at build time, not hardcoded by role name in config.
3. It matches the explicit hint in CONTEXT.md's `code_context`: *"`RoleDefinition` already has `outputs`... `inputs` is a natural sibling addition, not a new concept."*

The alternative (`inputs` naming a role, e.g. `["BA"]`, meaning "everything BA output") is simpler to resolve (skip the filename→role lookup, go straight to Pattern 3's per-role query) but loses per-file granularity — a role that wants only `acceptance_criteria.json` and not `requirements.md` cannot express that. Since D-05 depends on `acceptance_criteria.json` being independently addressable (QA references it by criterion id, not "BA's output blob"), filename-level granularity is the better fit for this project's own data shapes.

**Confidence:** [ASSUMED] — a design recommendation, not extracted from an external source. Grounded in verified shapes of `RoleDefinition`/`BA.yaml`/`QA.yaml` (cited above).

### Pattern 3: The D-03 query — one filtered/ordered/`LIMIT 1` select per role, not a window function

**Decision requested by CONTEXT.md, resolved here.**

```python
# dark_factory/context/builder.py (new)
def _latest_completed_execution(
    session: Session, run_id: UUID, role: str
) -> RoleExecution | None:
    """The most recent COMPLETED role_execution row for one (run_id, role) pair.

    ``uq_role_exec_attempt`` (UniqueConstraint on run_id, role, attempt — see
    persistence/models.py:158-160) already makes ``attempt`` a total order
    *within one role*, so — unlike ``load_run_state``'s cross-role "latest
    overall" query, which needs (created_at, attempt, id) tiebreakers because
    different roles' attempts collide at attempt=1 — a single ``ORDER BY
    attempt DESC LIMIT 1`` is deterministic with no tiebreak needed. The
    ``status == COMPLETED`` filter is what makes CTX-04 hold *by construction*:
    a FAILED or WAITING_HUMAN attempt is never a candidate, and a retried
    attempt's higher ``attempt`` number naturally wins over the completed one
    it superseded (moot in Phase 4's scope since QA-FAIL retries are Phase 9,
    but the query is correct regardless).
    """
    return session.scalar(
        select(RoleExecution)
        .where(
            RoleExecution.run_id == run_id,
            RoleExecution.role == role,
            RoleExecution.status == "COMPLETED",
        )
        .order_by(RoleExecution.attempt.desc())
        .limit(1)
    )
```

[VERIFIED: src/dark_factory/persistence/models.py:158-160 — `__table_args__ = (sa.UniqueConstraint("run_id", "role", "attempt", name="uq_role_exec_attempt"),)`]

Called once per filename in the current role's `inputs`, after resolving the filename to its producing role via the snapshot (Pattern 2). This is deliberately simpler than the general "latest row per group, for every group, in one query" pattern (window functions / correlated subqueries) [CITED: SQLAlchemy discussion "Sorting rows grouped by ID..." — github.com/sqlalchemy/sqlalchemy/discussions/9976; miguelgrinberg.com "Nested Queries with SQLAlchemy ORM"] because `ContextBuilder` never needs "every role's latest row" at once — only the specific roles named by one role's `inputs`.

### Pattern 4: Schema validation gates the transition — no new EventType this phase

**What:** After the worker call returns and before `signal_from_result`/`transition()` is invoked, validate every JSON artifact the role's `outputs` names a "machine" type (all except `requirements.md`/`design.md`) against its `dark_factory.domain.artifacts` model. On `pydantic.ValidationError`, do **not** let the worker's own `COMPLETED` status stand — synthesize the D-09 failure path: `RoleExecutionWrite(status=_ROLE_FAILED, error={...})`, `EventWrite(type=EventType.ROLE_FAILED, ...)` + `EventWrite(type=EventType.RUN_FAILED, ...)`, `next_status=RunStatus.FAILED` — i.e. reuse the *exact* branch `_run_current_role` already has for `Signal.ROLE_FAILED` [VERIFIED: src/dark_factory/orchestrator/runner.py:472-482], just reached by a validation exception instead of `result.status == FAILED`.

**Pitfall — do not add `QA_PASSED`/`QA_FAILED`/`ARTIFACT_CREATED` to `EventType` in this phase.** `events/catalog.py`'s own docstring is explicit: *"The remainder listed in PROJECT.md -- ARTIFACT_CREATED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED, PUBLISH_STARTED, PR_CREATED -- still arrive in Phase 12. A member present in the enum but never written is a false signal in the audit surface, so the not-yet-reachable types are deliberately not pre-declared here"* [VERIFIED: src/dark_factory/events/catalog.py:6-10]. Adding `ARTIFACT_CREATED` would be a natural-feeling but explicitly-forbidden-by-the-codebase-itself move; reuse the existing `ROLE_COMPLETED`/`ROLE_FAILED` events (their payload can note the artifact count/types if useful).

**Why this satisfies ROLE-06/SC5 without branching on verdict content (D-06):** `signal_from_result` reads only `result.status` [VERIFIED: src/dark_factory/domain/signal.py:38-41], never `result.summary` (prose). The "decided by `verdict.json`, never by summary prose" requirement is satisfied because (a) the *only* way a QA step's outcome differs from a worker-reported `COMPLETED` is a validation failure on the JSON contract, never a read of prose, and (b) D-06 explicitly says Phase 4 does not yet act differently on PASS vs FAIL — that branch is Phase 9. Validating `verdict.json`'s internal PASS/FAIL consistency (D-04's rule: overall PASS iff every criterion PASS and no blocking issue) inside the pydantic model itself (a `model_validator` that checks a declared `status` field against the computed one, if the shape declares one) is what makes the JSON contract "authoritative" per ART-02, ahead of the Phase 9 code that will actually route on it.

### Pattern 5: `ArtifactReference` writes go through the one mutation path, in the same transaction as the role's status change

**What:** Extend `persistence/mutations.py::apply_transition` with a new keyword-only parameter (mirrors the existing `human_interaction: HumanInteractionWrite | None = None` parameter [VERIFIED: src/dark_factory/persistence/mutations.py:216-220]), e.g. `artifact_references: Sequence[ArtifactReferenceWrite] = ()`, each carrying `role_execution_id, type, path, checksum, metadata`. Insert them inside the same `with session.begin():` block, after the role_execution write, before the event writes.

**Why this is required, not optional:** `tests/unit/test_single_mutation_path.py` AST-walks `src/dark_factory/` and fails the build if any module other than `persistence/mutations.py` constructs a row in `_LIFECYCLE_CTORS` [VERIFIED: tests/unit/test_single_mutation_path.py:37-39 — `_LIFECYCLE_CTORS = {"RunEvent", "RoleExecution", "HumanInteraction"}`]. That set does **not** yet include `"ArtifactReference"` — the planner must (a) add `"ArtifactReference"` to `_LIFECYCLE_CTORS` and (b) make sure the new ORM class is constructed *only* inside `mutations.py`, following the exact precedent set when `"HumanInteraction"` was added for Phase 2 [VERIFIED: tests/unit/test_single_mutation_path.py:16-20 docstring — *"HumanInteraction joins the list for Phase 2: a question row written outside the one mutation path would be a state change with no guarantee that its status transition and its audit event committed with it."*]. The identical argument applies to artifact references: an artifact row written outside `apply_transition`'s transaction could exist for a role attempt whose status write later rolled back (or vice versa), breaking ART-03's "every artifact has a reference row" guarantee.

**Recommended `artifacts` table shape** (migration `0004_artifacts.py`, mirrors `0003`'s style):

```python
op.create_table(
    "artifacts",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("run_id", sa.Uuid(), nullable=False),
    sa.Column("role_execution_id", sa.Uuid(), nullable=False),
    sa.Column("type", sa.String(64), nullable=False),
    sa.Column("path", sa.String(), nullable=False),
    sa.Column("checksum", sa.String(), nullable=True),
    sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
    sa.ForeignKeyConstraint(["role_execution_id"], ["role_executions.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("role_execution_id", "path", name="uq_artifact_role_execution_path"),
)
op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
```

Column set matches the docstring already committed in `persistence/models.py` verbatim: *"the future `artifacts` table (Phase 4) will store `ArtifactReference` metadata only -- `id, run_id, role_execution_id, type, path, checksum, metadata, created_at`"* [VERIFIED: src/dark_factory/persistence/models.py:37-40]. The `uq_artifact_role_execution_path` constraint is defense-in-depth, mirroring `uq_role_exec_attempt`'s own stated philosophy [VERIFIED: src/dark_factory/persistence/models.py:154-155] — it protects against a double-write producing duplicate reference rows for the same attempt if a lease-loss retry (`_run_current_role`'s documented "the step re-runs cleanly on the same attempt from the next process" [VERIFIED: src/dark_factory/orchestrator/runner.py:436-444]) ever re-executes the artifact-persistence step for the same `role_execution_id`.

`path` should be **relative to the run root** (e.g. `artifacts/BA/requirements.md`), not absolute — the same discipline `config/loader.py` already applies to `instructions_path` (`str(instr_path.relative_to(root))` [VERIFIED: src/dark_factory/config/loader.py:149]) — because an absolute path baked in at write time will not resolve on a different machine (ART-04/Phase 5 concern, but storing relative paths now costs nothing and avoids a later migration).

### Pattern 6: FakeWorker differentiation writes real files as a *test-fixture* concern, not a FakeWorker feature

**The gap:** `FakeWorker.execute()` only returns the next scripted `WorkerResult` — it performs **no filesystem I/O** [VERIFIED: src/dark_factory/workers/fake.py:93-103]. For SC1 to hold (`requirements.md` + `acceptance_criteria.json` etc. actually exist under `.dark-factory/runs/<run-id>/`), *something* must write those bytes to disk before or during the step, in addition to the `WorkerResult.artifacts: list[ArtifactRef]` declaration.

**Also note:** `default_registry`'s `"fake"` entry is **one process-lifetime singleton** shared by every role [VERIFIED: src/dark_factory/workers/registry.py:96-109, esp. docstring lines 21-30 — "a fresh FakeWorker per call would reset the script cursor to 0 every step"]. This means a full four-role run needs **one script list of four `WorkerResult`s** (BA, then ARCHITECTURE, then DEVELOPMENT, then QA, in that order), not four independently-scripted workers.

**Recommendation:** Add a small test-support helper (e.g. `tests/support/fake_artifacts.py`, not shipped `src/`) that, given a run root, a role name, and a `{filename: content}` mapping, (a) creates `artifacts/<role>/` under the run root, (b) writes each file, (c) computes its SHA-256, and (d) returns the matching `list[ArtifactRef]` to embed in that role's scripted `WorkerResult`. Building this in test-fixture code (not production `FakeWorker`) keeps `WORK-10`'s shipped worker exactly as simple as it is today and matches D-07's framing ("testing durable handoff plumbing... not content quality") — the content-writing step is fixture setup, not a new capability the fake needs to carry into Phase 7/8's contract-test suite. If the planner instead wants `FakeWorker` itself to write files (arguably more representative of a real worker, which will write via an `artifacts.write` tool once Phase 6 lands), that is a legitimate alternative — flag it as a plan-time choice, not a locked decision.

### Anti-Patterns to Avoid

- **Reading `ArtifactReference.path` as an absolute filesystem path baked in at another machine's mount point.** Store relative-to-run-root; resolve at read time against `run_root(repo_root, run_id)`.
- **Letting `store_role_artifacts` (or any action hook) open its own `Session` and construct `ArtifactReference` rows directly.** Violates the single-mutation-path invariant this codebase enforces with an AST test (Pattern 5); also violates `actions/builtins.py`'s own stated rule: *"An action must never open a database session, construct a `RunEvent`/`RoleExecution`/`HumanInteraction`, or assign a lifecycle `.status`"* [VERIFIED: src/dark_factory/actions/builtins.py:8-10] — the same rule should be read as extending to the new `ArtifactReference`.
- **Adding `ARTIFACT_CREATED`/`QA_PASSED`/`QA_FAILED` to `EventType` this phase.** Explicitly deferred to Phase 12 by the enum's own docstring (Pattern 4).
- **Validating `verdict.json`'s PASS/FAIL and then branching the transition on it.** D-06 explicitly scopes that branch to Phase 9; Phase 4 only needs schema validity to gate `COMPLETED` vs `FAILED`.
- **Walking the repository tree to build baseline context (`os.walk`, `Path.rglob` over the repo).** CTX-02 and the phase's own stated invariant ("the ContextBuilder never walks the source tree") forbid it — read only the small, named baseline file set (README.md, AGENTS.md, CLAUDE.md), each individually, each capped, exactly like `config/loader.py`'s `_MAX_INSTRUCTION_BYTES` idiom [VERIFIED: src/dark_factory/config/loader.py:50, 140-144].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-artifact-type JSON validation | A hand-written `if/elif` chain of manual key checks | `Model.model_validate(json_content)` per D-10, one frozen pydantic model per type | Already the codebase's universal boundary-validation idiom (`WorkerResult`, `RepoConfig`, `RoleDefinition`) — consistent error shape (`pydantic.ValidationError`), consistent `frozen`/`extra="forbid"` discipline |
| "Which role produced this filename" lookup | A new config field or a hardcoded `{filename: role}` dict in Python | Derive it from `state.workflow["roles"][*]["outputs"]`, already persisted in the snapshot (Pattern 2) | Zero new schema, stays correct automatically if the pipeline is reordered/shortened (ORCH-03) |
| Content checksums | A custom rolling hash or `zlib.crc32` | `hashlib.sha256(content).hexdigest()`, stdlib | `ArtifactRef.checksum` is already typed `str | None`; SHA-256 is the unambiguous default for content-addressing in this class of system |
| "Latest completed row for X" | A cached/derived in-memory index rebuilt from `run_events` | A parameterized SQL query against `role_executions` (Pattern 3) | STATE-06's own rule: control state is read from columns, never folded from the append-only event log |

**Key insight:** Every hand-rolling temptation in this phase already has a same-shape precedent living in the codebase from Phases 1-3. The fastest way to get this phase right is to grep for the nearest sibling (`WorkerResult` for a new pydantic model, `HumanInteractionWrite` for a new `apply_transition` parameter, `load_run_state`'s query style for a new read) and match its shape exactly, rather than inventing a new idiom.

## Runtime State Inventory

Not applicable — this is a greenfield feature phase, not a rename/refactor/migration phase. No existing production data, service config, OS registrations, secrets, or build artifacts carry a name this phase changes.

## Common Pitfalls

### Pitfall 1: `prepare_role_context`/`store_role_artifacts` look wired but do nothing today
**What goes wrong:** A plan that assumes registering real logic under these two action names is sufficient (because they're already referenced in `BA.yaml`'s `before`/`after` lists) will silently no-op, because `_run_hooks` discards every action's return value.
**Why it happens:** The docstrings in `actions/builtins.py` ("No-op until Phase 4... builds the role-specific RoleContext" / "persists the role's output artifacts") read as an implementation roadmap, but the surrounding mechanism (`ActionRegistry`, `ActionContext`, `_run_hooks`) has no return-value channel.
**How to avoid:** Follow Pattern 1 — call the context builder and artifact validator directly from `_run_current_role`, not through the action-hook return value.
**Warning signs:** A test that registers a custom `prepare_role_context` and expects `worker.execute()` to receive its output will fail with the *old* minimal `_build_context()` dict, silently.

### Pitfall 2: Forgetting the `_LIFECYCLE_CTORS` AST guard
**What goes wrong:** Constructing `ArtifactReference(...)` anywhere outside `persistence/mutations.py` (e.g. in a new `artifacts/store.py` "convenience" writer) compiles and passes unit tests but is architecturally the same violation `HumanInteraction` was guarded against in Phase 2.
**Why it happens:** `tests/unit/test_single_mutation_path.py`'s `_LIFECYCLE_CTORS` set is a literal Python set that must be *manually* extended — it does not discover new ORM classes automatically.
**How to avoid:** Add `"ArtifactReference"` to `_LIFECYCLE_CTORS` in the same plan wave that introduces the ORM class, and route every construction through `apply_transition`.
**Warning signs:** `test_mutations_py_is_the_sole_lifecycle_writer` failing after the artifact-persistence code lands, naming a file+line outside `mutations.py`.

### Pitfall 3: `spec:` loader breaks two existing tests that currently assert it's unsupported
**What goes wrong:** Implementing `_load_spec` without updating its two existing "this is Phase 4" assertions leaves a broken/contradictory test suite.
**Why it happens:** `tests/unit/test_loaders.py::test_spec_loader_names_phase_4` and `tests/integration/test_unsupported_source.py`'s `("spec:./task.md", "Phase 4")` parametrization [VERIFIED: tests/unit/test_loaders.py:45-48; tests/integration/test_unsupported_source.py:48-53] both currently *require* `SourceNotSupportedError` naming "Phase 4" for exactly the locator (`spec:./task.md`) this phase's own SC1 uses as its example.
**How to avoid:** Remove/replace `test_spec_loader_names_phase_4` with a real-loader test; remove the `spec:` row from `test_unsupported_source.py`'s parametrization (keep the `github:` row, still Phase 10).
**Warning signs:** CI red on these two named tests immediately after `_load_spec` starts returning a `NormalizedTask` instead of raising.

### Pitfall 4: The shared singleton `FakeWorker` needs one script list, not four
**What goes wrong:** Writing four separate `FakeWorker(script=[...])` instances (one per role) and expecting `default_registry` to dispatch between them — it can't; there is one `"fake"` factory, one shared instance, one script cursor advancing across the whole run.
**Why it happens:** It is tempting to think of "the BA fake worker" and "the QA fake worker" as separate things because their content differs, but D-08 is explicit that they are the same worker differentiated only by script content.
**How to avoid:** Build one four-element script (`DARK_FACTORY_FAKE_SCRIPT` env var, or a test's own `WorkerRegistry` with a per-test `FakeWorker(script=[ba_result, arch_result, dev_result, qa_result])` — see `workers/registry.py`'s own note that "Tests that need isolated cursors build their own `WorkerRegistry`" [VERIFIED: src/dark_factory/workers/registry.py:28-30]).
**Warning signs:** `ScriptExhaustedError` after the first role, or the same `WorkerResult` (content) repeating for every role.

### Pitfall 5: Baseline-doc reads must be capped and optional, not required
**What goes wrong:** Treating README.md/AGENTS.md/CLAUDE.md as required files causes `ContextBuilder` to raise `ConfigError`-equivalent errors on a repo (like this one, mid-scaffold) where `AGENTS.md` may not exist yet.
**Why it happens:** D-02 says these are "always included," which could be misread as "must exist."
**How to avoid:** Each of the three is an independent, optional, capped read (skip silently if absent — mirror `config/loader.py`'s `is_file()` check pattern, but non-fatal here since these are supplementary context, not role-defining config).
**Warning signs:** A run failing at the BA role in a repo that has no `AGENTS.md`.

### Pitfall 6: Cross-machine artifact content is out of scope this phase — fail loudly, don't silently degrade
**What goes wrong:** `ContextBuilder` finds an `ArtifactReference` row in Neon (proving the artifact *was* written) but the file is missing on the current filesystem (different machine, deleted, etc.) — a scenario Phase 4 does not solve (that's ART-04/Phase 5's "commit artifacts to the run's working branch" plan [VERIFIED: .planning/ROADMAP.md:227, quoted in REQUIREMENTS.md traceability]).
**Why it happens:** STATE-08 promises "reconstructable from persisted data alone," which is true for **lifecycle** state but not yet true for artifact **content** in this phase — a gap the roadmap itself acknowledges and defers.
**How to avoid:** Raise a distinct, named error (e.g. `MissingArtifactContentError`) rather than treating a missing file as "no prior artifact" (which would silently degrade context quality) or crashing with a bare `FileNotFoundError`.
**Warning signs:** A resumed run on the *same* machine works, but the failure mode on a different machine is an unhelpful traceback instead of a clear, typed error naming the missing path.

## Code Examples

### `input/loaders.py::_load_spec` (INTAKE-02)

```python
# Source: mirrors the already-shipped _load_text exactly
# (src/dark_factory/input/loaders.py:29-48, read this session)
from pathlib import Path

def _load_spec(locator: str) -> NormalizedTask:
    path = Path(locator.strip().strip('"')).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise UnresolvableSourceError(f"spec: file not found: {path}")
    body = path.read_text("utf-8").strip()
    if not body:
        raise UnresolvableSourceError(f"spec: file is empty: {path}")
    title = body.splitlines()[0].lstrip("#").strip()[:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="spec",
        source_ref=str(path),
        title=title,
        body=body,
        metadata={},
    )
```

Raising `UnresolvableSourceError` (not `SourceNotSupportedError`) for a missing/empty file matches the existing exit-2/nothing-persisted contract the CLI already handles for exactly that exception type [VERIFIED: src/dark_factory/cli.py:180 — `except (UnresolvableSourceError, SourceNotSupportedError, ConfigError) as exc:`].

### `domain/artifacts.py` model shape (D-04, D-05, D-10)

```python
# New module — same discipline as domain/worker.py (frozen, extra="forbid")
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str          # e.g. "AC-1" — D-05: stable string id, never positional
    description: str

class AcceptanceCriteriaDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    criteria: list[AcceptanceCriterion]

class VerdictCriterionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    criterion_id: str            # matches AcceptanceCriterion.id (D-05)
    result: Literal["PASS", "FAIL"]
    notes: str = ""

class VerdictIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    severity: Literal["blocking", "minor"]
    description: str

class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    criteria: list[VerdictCriterionResult]
    issues: list[VerdictIssue] = Field(default_factory=list)

    @property
    def overall_status(self) -> Literal["PASS", "FAIL"]:
        # D-04: PASS iff every criterion PASS AND no blocking issue
        all_pass = all(c.result == "PASS" for c in self.criteria)
        no_blocking = not any(i.severity == "blocking" for i in self.issues)
        return "PASS" if all_pass and no_blocking else "FAIL"
```

`constraints.json` (Architect) and `implementation_summary.json` (Developer) and `test_report.json` (QA) have no shape locked by CONTEXT.md; the planner has discretion here. A minimal, symmetric starting shape — `{"constraints": [{"id": "C-1", "description": ...}]}` for `constraints.json`, mirroring `AcceptanceCriteriaDocument` — is a reasonable default; flag this as an assumption if the plan locks it in.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A | N/A | — | This phase has no "old way, new way" — it is the first implementation of context assembly and artifact persistence in this codebase (Phases 1-3 built the substrate it sits on). |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ContextBuilder`/artifact-validation logic should be direct function calls from `_run_current_role`, with `prepare_role_context`/`store_role_artifacts` left inert or removed from role YAML `before`/`after` lists, rather than extending `ActionRegistry`'s return-value contract | Architecture Pattern 1 | If the planner instead widens `ActionRegistry` to support return values, more files change (registry, `ActionContext`, `_run_hooks`, both existing role YAMLs stay meaningful) but the outcome is equivalent; low risk either way as long as one approach is chosen deliberately, not left ambiguous mid-implementation |
| A2 | `RoleDefinition.inputs` entries are literal filenames (mirroring `outputs`), not role names | Architecture Pattern 2 | If wrong, `ContextBuilder`'s filename→role resolution step is unnecessary and role-YAML `inputs` values need rewriting from filenames to role names — a config-shape change (D-01 marks the field itself "costly to reverse") |
| A3 | FakeWorker artifact-file writing lives in test-fixture helper code (`tests/support/`), not shipped `FakeWorker` itself | Architecture Pattern 6 | If wrong, `WORK-10`'s shipped `FakeWorker` needs a new constructor shape before Phase 7/8's contract-test suite can rely on it; a rework, not a blocker |
| A4 | `constraints.json` / `implementation_summary.json` / `test_report.json` minimal shapes (Code Examples) | Code Examples | These are genuinely undecided by CONTEXT.md; any reasonable schema works as long as it's a pydantic model per D-10 — low risk, purely a naming/shape choice |
| A5 | Baseline docs (README/AGENTS/CLAUDE.md) are optional, capped, individually-read files, not a required set | Common Pitfalls #5 | If wrong (i.e. a plan makes them required), a repo missing one would break every run — high blast radius for a low-value strictness gain |
| A6 | `artifacts.path` column stores a path relative to the run root, not absolute | Architecture Pattern 5 | If wrong, cross-machine resume (Phase 5, ART-04) requires a data migration to convert already-stored absolute paths to relative ones |

## Open Questions

1. **Does the Developer role's `implementation_summary.json` need `changed_files`/diff information in Phase 4, given there is no git worktree yet (Phase 5)?**
   - What we know: ROLE-03 says Developer "implements the change, adds/updates tests, runs tests/lint/build" — real behavior that needs a worktree.
   - What's unclear: Phase 4 has no worktree (Phase 5 adds it) and `FakeWorker` performs no real code changes.
   - Recommendation: `FakeWorker`'s Developer step should emit only the JSON artifact (schema-valid, D-07) with placeholder `changed_files`/summary text; real code modification is exercised starting Phase 5 with real workers in Phase 7+. Confirm this scoping explicitly in the plan so ROLE-03's "may modify production code and tests" clause isn't misread as a Phase 4 requirement.

2. **Should `ArtifactReference.metadata` (JSONB) carry anything in Phase 4, or stay `{}`?**
   - What we know: The column exists per the docstring's locked shape; nothing in CONTEXT.md specifies its Phase 4 content.
   - What's unclear: Whether a later phase (e.g. Phase 9's quality gate, Phase 12's observability) will want something specific stored here now to avoid a later migration.
   - Recommendation: Leave it `{}` (or a trivial `{"role": role_name}` for query convenience, though `role_execution_id` already joins to role) in Phase 4; revisit if a later phase's research surfaces a concrete need.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 17 (test tier) | `db`/`integration` test markers, migration 0004 | ✓ (probe ladder: Docker → local `initdb` → `DARK_FACTORY_TEST_DATABASE_URL`) [VERIFIED: tests/conftest.py:1-16, 40-90] | 17 | Already the project's documented "no SQLite/mock substitute" policy |
| Filesystem write access under repo root | `.dark-factory/runs/<run-id>/` creation | ✓ (already gitignored in anticipation — `.gitignore` line "Per-run artifact content (Phase 4)... .dark-factory/runs/") [VERIFIED: .gitignore] | — | — |
| Docker / local Postgres initdb | Alembic migration test round-trip | Same probe ladder as above | — | — |

No new external service or credential is introduced by this phase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest `>=9,<10` [VERIFIED: pyproject.toml:27] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` [VERIFIED: pyproject.toml:44-51] |
| Quick run command | `uv run pytest -m unit -q` |
| Full suite command | `set -a; . ./.env; set +a; uv run pytest -q` (env-loaded, per the existing Phase 3 acceptance-gate docstring convention [VERIFIED: tests/integration/test_phase3_acceptance.py:18-19]) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTAKE-02 | `spec:./task.md` loads a real task | unit | `uv run pytest tests/unit/test_loaders.py -k spec -x` | ❌ Wave 0 (rewrite `test_spec_loader_names_phase_4`) |
| INTAKE-02 | CLI end-to-end from a spec file | integration | `uv run pytest tests/integration/test_unsupported_source.py -x` (after removing the `spec:` row) + new `test_spec_source_starts_a_run.py` | ❌ Wave 0 |
| ORCH-04/ROLE-01..04 | Four roles run in sequence via `FakeWorker`, producing all 6 artifact files | db | `uv run pytest tests/db/test_four_role_pipeline.py -x` (new) | ❌ Wave 0/1 |
| CTX-01/02/03 | `ContextBuilder` resolves `inputs` to the correct filenames, includes baseline docs, never reads outside named files | unit | `uv run pytest tests/unit/test_context_builder.py -x` (new) | ❌ Wave 0 |
| CTX-04 | A superseded attempt's artifacts never appear in a rebuilt context | db | `uv run pytest tests/db/test_context_builder_retry_isolation.py -x` (new) | ❌ Wave 1 |
| ART-01/03/STATE-05 | Every artifact has a matching `ArtifactReference` row; content is filesystem-only | db | `uv run pytest tests/db/test_artifact_persistence.py -x` (new) + `alembic check` | ❌ Wave 0 |
| ROLE-06 | A malformed `verdict.json` fails the role, not the run's summary prose | db | `uv run pytest tests/db/test_artifact_schema_violation_fails_role.py -x` (new) | ❌ Wave 1 |

### Sampling Rate

- **Per task commit:** `uv run pytest -m unit -q`
- **Per wave merge:** full suite (`db` + `integration` + `unit`)
- **Phase gate:** Full suite green + `alembic check` clean before `/gsd-verify-work`, following the exact precedent of Phases 1-3's acceptance gates (`tests/integration/test_phase{1,2,3}_acceptance.py`).

### Wave 0 Gaps

- [ ] `tests/unit/test_context_builder.py` — covers CTX-01/02/03
- [ ] `tests/db/test_four_role_pipeline.py` — covers ORCH-04, ROLE-01..04, ART-01
- [ ] `tests/db/test_artifact_persistence.py` — covers ART-03, STATE-05
- [ ] Rewrite `tests/unit/test_loaders.py::test_spec_loader_names_phase_4` and the `spec:` row in `tests/integration/test_unsupported_source.py` (Pitfall 3)
- [ ] Add `"ArtifactReference"` to `tests/unit/test_single_mutation_path.py::_LIFECYCLE_CTORS` (Pitfall 2)
- [ ] `tests/integration/test_phase4_acceptance.py` — the phase's own acceptance gate, sibling of `test_phase3_acceptance.py`, mapping this phase's 5 success criteria + its 15 requirement ids

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Not touched this phase |
| V3 Session Management | no | Not touched this phase |
| V4 Access Control | partial | Role tool grants exist in config (`tools:` per role YAML) but are stored-not-enforced until Phase 6 (TOOL-03) — Phase 4 does not newly violate this, but should not claim enforcement it doesn't yet have |
| V5 Input Validation | **yes** | pydantic `Model.model_validate()` per D-10 for every machine artifact; `frozen=True, extra="forbid"` on every new model, matching the codebase's existing boundary-validation discipline |
| V6 Cryptography | no (checksums are integrity, not confidentiality) | `hashlib.sha256` for content-addressing only — not a security control, a correctness one |
| V12 File and Resources | **yes** | Artifact paths must resolve **under** the run root, same discipline as `config/loader.py`'s `instr_path.is_relative_to(root)` check [VERIFIED: src/dark_factory/config/loader.py:135] — apply the identical "no `..` escape" check to any path read from an `ArtifactRef`/`ArtifactReference` before opening it |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via a worker-reported `ArtifactRef.path` (e.g. `../../etc/passwd` or an absolute path escaping the run root) | Tampering / Information Disclosure | Resolve every artifact path against the run root and reject (raise, don't silently clamp) any path that is not `is_relative_to(run_root)` — same pattern already proven for role instruction files |
| A schema-invalid or oversized JSON artifact used to exhaust memory or crash validation | Denial of Service | Cap artifact file read size before `json.loads`/`model_validate` (mirror `_MAX_INSTRUCTION_BYTES`'s 64 KiB cap idiom, sized appropriately for JSON artifacts — a few hundred KB is generous for this domain) |
| A worker (even `FakeWorker` today, a real one from Phase 7) reporting an `ArtifactRef` for a file it never actually wrote, to be picked up as "prior context" by the next role | Spoofing / Tampering | `ContextBuilder` should treat "file referenced but missing on disk" as a hard error (Pitfall 6's `MissingArtifactContentError`), never as "artifact absent, skip silently" |

## Sources

### Primary (HIGH confidence — read this session)

- `src/dark_factory/config/loader.py`, `config/repo_config.py`, `domain/worker.py`, `domain/task.py`, `domain/status.py`, `domain/signal.py`, `persistence/models.py`, `persistence/mutations.py`, `persistence/repositories.py`, `orchestrator/runner.py`, `orchestrator/lifecycle.py`, `workflows/pipeline.py`, `workers/base.py`, `workers/fake.py`, `workers/registry.py`, `actions/builtins.py`, `actions/context.py`, `actions/registry.py`, `roles/registry.py`, `input/loaders.py`, `input/resolver.py`, `events/catalog.py`, `config/settings.py`, `cli.py` — full contents read this session (paths cited inline throughout)
- `tests/unit/test_single_mutation_path.py`, `tests/unit/test_loaders.py`, `tests/integration/test_unsupported_source.py`, `tests/db/test_role_hooks_invoked.py`, `tests/support/config.py`, `tests/conftest.py`, `migrations/versions/0003_pause_resume_lease.py`, `.dark-factory.yaml`, `.dark-factory/roles/BA.yaml`, `.dark-factory/roles/QA.yaml`, `.gitignore`, `pyproject.toml` — read this session
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/phases/04-.../04-CONTEXT.md`, `.planning/ROADMAP.md` (Phase 4/5 sections), `.claude/CLAUDE.md` (project tech-stack doc) — read this session

### Secondary (MEDIUM confidence)

- pydantic v2 discriminated-union docs — https://pydantic.dev/docs/validation/latest/concepts/unions/ (context for Alternatives Considered, not used in the recommended design)
- SQLAlchemy "latest row per group" community discussions — https://github.com/sqlalchemy/sqlalchemy/discussions/9976, https://blog.miguelgrinberg.com/post/nested-queries-with-sqlalchemy-orm (context for Alternatives Considered; the recommended query is simpler than these general patterns because it is always scoped to one role)

### Tertiary (LOW confidence)

None used as a basis for a claim in this document.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; every library/version cited was read directly from `pyproject.toml` this session
- Architecture: HIGH for what already exists in the codebase (every cited file/line was read this session); MEDIUM/ASSUMED for the new-design recommendations (Patterns 1, 2, 6) since CONTEXT.md left them open and no external authority governs an internal architecture choice — flagged per-item in the Assumptions Log
- Pitfalls: HIGH — every pitfall traces to a specific, read file/line (an AST guard, an existing test's literal assertion, a singleton's documented behavior), not speculation

**Research date:** 2026-09-12
**Valid until:** Effectively indefinite for the architectural facts (they are this codebase's own source, verified by reading it) — but re-verify against `main` if Phase 3's code changes materially before Phase 4 planning starts (e.g. if `_run_current_role`'s hook-ordering or `ActionRegistry`'s signature changes).
