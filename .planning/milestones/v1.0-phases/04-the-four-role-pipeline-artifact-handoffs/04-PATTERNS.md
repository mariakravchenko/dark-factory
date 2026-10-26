# Phase 4: The Four-Role Pipeline & Artifact Handoffs - Pattern Map

**Mapped:** 2026-09-12
**Files analyzed:** 16 (new + modified)
**Analogs found:** 14 / 16

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/dark_factory/domain/artifacts.py` (new) | model | transform (validate JSON→pydantic) | `src/dark_factory/domain/worker.py` | exact |
| `src/dark_factory/context/builder.py` (new) | service | request-response (assemble RoleContext) | `src/dark_factory/orchestrator/runner.py::_build_context` + `_role_definition` | role-match |
| `src/dark_factory/context/__init__.py` (new) | config/barrel | — | `src/dark_factory/domain/__init__.py`-style barrel | exact |
| `src/dark_factory/artifacts/paths.py` (new) | utility | file-I/O | `src/dark_factory/config/loader.py` (path resolution + size cap idiom) | role-match |
| `src/dark_factory/artifacts/store.py` (new) | service | file-I/O + CRUD (read/write content, list refs) | `src/dark_factory/config/loader.py` (safe read) + `persistence/repositories.py` (read queries) | role-match |
| `src/dark_factory/artifacts/validation.py` (new) | service | transform | `domain/artifacts.py` dispatch by `Model.model_validate` | exact (self-referential to D-10 models) |
| `src/dark_factory/persistence/models.py` (modified: + `ArtifactReference`) | model | CRUD | `HumanInteraction` ORM class (same file, lines 217+) | exact |
| `migrations/versions/0004_artifacts.py` (new) | migration | batch (DDL) | `migrations/versions/0003_pause_resume_lease.py` | exact |
| `src/dark_factory/persistence/mutations.py` (modified: `apply_transition` + `ArtifactReferenceWrite`) | service | CRUD (single mutation path) | `HumanInteractionWrite` + its `apply_transition` wiring (same file) | exact |
| `src/dark_factory/config/loader.py` (modified: `RoleDefinition.inputs`) | config | transform | `RoleDefinition.outputs`/`examples` fields (same file, lines 70-83) | exact |
| `.dark-factory/roles/ARCHITECTURE.yaml` (new) | config | request-response | `.dark-factory/roles/BA.yaml` | exact |
| `.dark-factory/roles/DEVELOPMENT.yaml` (new) | config | request-response | `.dark-factory/roles/BA.yaml` | exact |
| `.dark-factory/roles/BA.yaml` (modified: + `inputs: []`) | config | request-response | itself (before/after fields already present) | exact |
| `.dark-factory/roles/QA.yaml` (modified: + `inputs: [...]`) | config | request-response | `.dark-factory/roles/QA.yaml` (self, add field) | exact |
| `src/dark_factory/roles/registry.py` (modified: + architect/developer/qa `Role`) | model/config | — | `ba_role` (same file) | exact |
| `src/dark_factory/input/loaders.py` (modified: `_load_spec`) | utility | file-I/O | `_load_text` (same file, lines 29-48) | exact |
| `src/dark_factory/orchestrator/runner.py` (modified: `_build_context` call site → `build_role_context`, artifact validation before signal) | controller/service | request-response | `_run_current_role`'s existing `Signal.ROLE_FAILED` branch (lines ~467-482) | exact |
| `tests/unit/test_single_mutation_path.py` (modified: `_LIFECYCLE_CTORS` += `"ArtifactReference"`) | test | — | same file's existing `HumanInteraction` addition precedent | exact |
| `tests/support/fake_artifacts.py` (new) | test utility | file-I/O | `src/dark_factory/workers/fake.py` (`FakeWorker`, `_default_script`) | role-match |

## Pattern Assignments

### `src/dark_factory/domain/artifacts.py` (model, transform)

**Analog:** `src/dark_factory/domain/worker.py`

**Module docstring / boundary-model discipline** (lines 1-9):
```python
"""The normalized worker-output contract (WORK-08).

A :class:`WorkerResult` is the only value that crosses back from a runtime the
orchestrator does not control. ... the model is ``frozen`` (a result the
orchestrator cannot mutate cannot become a back-channel for state changes --
ORCH-05) and ``extra="forbid"`` (an adapter that invents a field is caught here
rather than silently dropping data into a JSONB column).
"""
```

**Core model pattern** (lines 32-38):
```python
class ArtifactRef(BaseModel):
    """A reference to an artifact file -- shape only; Phase 1 persists no rows."""

    model_config = ConfigDict(extra="forbid")

    type: str
    path: str
    checksum: str | None = None
```
Every new artifact-type model (`AcceptanceCriteriaDocument`, `ConstraintsDocument`, `ImplementationSummary`, `TestReport`, `Verdict`, and their nested item models) copies this exact `model_config = ConfigDict(frozen=True, extra="forbid")` shape (RESEARCH's Code Examples section gives the concrete D-04/D-05 shapes for `AcceptanceCriterion`/`Verdict` — copy those verbatim as the starting point). Validation entry point is `Model.model_validate(json_content)`, never a hand-rolled key check.

**Error handling pattern:** none inside this module — a `pydantic.ValidationError` propagates to the caller (`artifacts/validation.py` / `orchestrator/runner.py`), which is caught there and turned into the D-09 failure path. Do not catch `ValidationError` inside `domain/artifacts.py` itself.

---

### `src/dark_factory/context/builder.py` (service, request-response)

**Analog:** `src/dark_factory/orchestrator/runner.py::_build_context` (lines 122-136) and `_role_definition` (lines 139-163)

**Current minimal context-assembly pattern to extend** (lines 122-136):
```python
def _build_context(run_id: UUID, state: RunState, node: RoleNode) -> dict[str, Any]:
    """The role context handed to ``worker.execute``. ..."""
    attempt = state.latest_execution.attempt if state.latest_execution else 1
    return {
        "run_id": str(run_id),
        "role": node.name,
        "worker": node.worker,
        "attempt": attempt,
        "task": state.normalized_task.model_dump(mode="json"),
        "answer": state.pending_answer,
    }
```
`build_role_context(session, repo_root, run_id, state, role_def)` in the new module replaces this body: keep every field above, add resolved `inputs` artifact content, baseline docs, and examples. Return a frozen pydantic `RoleContext` model (matching the `frozen=True, extra="forbid"` boundary-model discipline), not a bare dict — the dict shape above is the field checklist, not the target type.

**Data-lookup-by-value pattern (no role-name branching)** (lines 139-163):
```python
def _role_definition(state: RunState, role: str) -> Mapping[str, Any]:
    """The persisted snapshot's entry for ``role`` -- a data lookup by name. ..."""
    for entry in state.workflow["roles"]:
        if isinstance(entry, str):
            name = entry
            definition: Mapping[str, Any] = {"name": entry, "before": [], "after": []}
        else:
            name = entry["name"]
            definition = entry
        if name == role:
            return definition
    raise LookupError(f"role {role!r} is not in the run snapshot")
```
`ContextBuilder`'s filename→producing-role resolution (RESEARCH Pattern 2) must follow this exact "iterate the persisted `state.workflow['roles']` snapshot, in-memory, no query" idiom — never re-read `.dark-factory/roles/*.yaml` at runtime (that would violate the "resume comes from the persisted snapshot" rule stated in `config/loader.py`'s own module docstring).

**The D-03 query** (RESEARCH Pattern 3, to add as a private helper in `builder.py`):
```python
def _latest_completed_execution(
    session: Session, run_id: UUID, role: str
) -> RoleExecution | None:
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

**Baseline-doc / capped-file-read pattern** — copy `config/loader.py`'s size-cap + relative-path-under-root idiom (lines 134-141, 149):
```python
instr_path = (role_path.parent / rd.instructions).resolve()
if not instr_path.is_file() or not instr_path.is_relative_to(root):
    raise ConfigError(
        f"{role_path}: instructions file not found under the repo root: {instr_path}"
    )
text = instr_path.read_text("utf-8")
if len(text.encode("utf-8")) > _MAX_INSTRUCTION_BYTES:
    raise ConfigError(f"{instr_path}: instruction file exceeds {_MAX_INSTRUCTION_BYTES} bytes")
...
"instructions_path": str(instr_path.relative_to(root)),
```
Apply the identical `is_file()` / `is_relative_to(root)` / size-cap shape to README.md/AGENTS.md/CLAUDE.md reads, **except** make each read optional (skip silently if `not path.is_file()`, per Pitfall 5) rather than raising `ConfigError` — these are supplementary context, not role-defining config.

---

### `src/dark_factory/artifacts/paths.py` + `store.py` (utility/service, file-I/O)

**Analog:** `src/dark_factory/config/loader.py` (path safety) + checksum idiom cited in RESEARCH.

**Path-traversal guard to copy** (same `is_relative_to(root)` shape as above, applied to `run_root(repo_root, run_id) / "artifacts" / role / filename` before any read):
```python
if not artifact_path.is_relative_to(run_root):
    raise ValueError(f"artifact path escapes run root: {artifact_path}")
```

**Checksum pattern** (stdlib, no existing analog file — first use in this codebase per RESEARCH's Don't-Hand-Roll table):
```python
import hashlib
checksum = hashlib.sha256(content_bytes).hexdigest()
```

**Missing-content error** (Pitfall 6) — new named exception, same shape as existing domain errors (`ScriptExhaustedError` in `workers/fake.py`, `ConfigError` in `config/loader.py`):
```python
class MissingArtifactContentError(RuntimeError):
    """Raised when an ArtifactReference row exists but its file is absent on disk."""
```

---

### `src/dark_factory/persistence/models.py` — `ArtifactReference` ORM class

**Analog:** `HumanInteraction` (same file, lines 217+)

```python
class HumanInteraction(Base):
    """One row per question asked of a human (STATE-04). ``status`` is a
    ``VARCHAR`` + CHECK carrying exactly ``WAITING`` / ``ANSWERED`` / ``CANCELLED``
    (never a native PG ``ENUM``), so a future value edit is a constraint change.
    ...
    """
    __tablename__ = "human_interactions"
    __table_args__ = (
        sa.Index("uq_one_waiting_interaction_per_run", "run_id", unique=True, ...),
    )
```
Copy this class shape for `ArtifactReference`: `__tablename__ = "artifacts"`, columns per the docstring already committed in this file (lines ~37-40: `id, run_id, role_execution_id, type, path, checksum, metadata, created_at`), FK to both `runs.id` and `role_executions.id` (NOT NULL, same as `HumanInteraction.role_execution_id`), and a `UniqueConstraint("role_execution_id", "path", name="uq_artifact_role_execution_path")` mirroring `uq_role_exec_attempt`'s defense-in-depth philosophy.

---

### `migrations/versions/0004_artifacts.py`

**Analog:** `migrations/versions/0003_pause_resume_lease.py` (full file structure: docstring explaining the vertical slice, `revision`/`down_revision`, `upgrade()`/`downgrade()` mirror order).

**Table-creation shape to copy** (adapted per RESEARCH Pattern 5):
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
`down_revision = "0003_pause_resume_lease"`; `downgrade()` drops the index then the table, mirror order (same as 0003's downgrade pattern for `human_interactions`).

---

### `src/dark_factory/persistence/mutations.py` — `ArtifactReferenceWrite` + `apply_transition` param

**Analog:** `HumanInteractionWrite` (lines 122-133) + its threading through `apply_transition`'s signature (line ~216-220) and the ordered-steps docstring (step 5).

```python
class HumanInteractionWrite(BaseModel):
    """Insert-or-update spec for the ``human_interactions`` row that accompanies a
    pause (``ask``) or a resume (``answer``). Mirrors :class:`RoleExecutionWrite`:
    ``question`` / ``answer`` are **raw** — redaction happens inside
    ``apply_transition`` at the single call site, never in the caller.
    """
```
Add `ArtifactReferenceWrite(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `role_execution_id: UUID, type: str, path: str, checksum: str | None, metadata: dict[str, Any] = Field(default_factory=dict)`. Add `artifact_references: Sequence[ArtifactReferenceWrite] = ()` as a new keyword-only parameter on `apply_transition`, inserted inside the same `with session.begin():` block, after the role_execution write and before the event writes (per RESEARCH Pattern 5's ordering). Update the docstring's numbered steps list the same way `human_interactions` (step 5) was added.

**Redaction discipline** — `metadata` (if it ever carries free text) must pass through `redact()` the same way `result`/`error`/`question`/`answer` do, at the single call site inside `apply_transition`, never in the caller.

---

### `src/dark_factory/config/loader.py` — `RoleDefinition.inputs`

**Analog:** `RoleDefinition.outputs` / `.examples` (same file, lines 70-83)

```python
class RoleDefinition(BaseModel):
    """One ``.dark-factory/roles/<name>.yaml`` document."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    worker: str
    instructions: str
    tools: list[str] = Field(default_factory=list)
    permissions: RolePermissions = RolePermissions()
    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
```
Add `inputs: list[str] = Field(default_factory=list)` as a sibling field (RESEARCH Pattern 2: entries are literal filenames, exactly like `outputs`). Also add `"inputs": list(rd.inputs)` to the resolved-role dict built in `load_effective_config` (mirrors the existing `"outputs": list(rd.outputs)` line).

---

### `.dark-factory/roles/ARCHITECTURE.yaml` / `DEVELOPMENT.yaml` (new), `BA.yaml` / `QA.yaml` (modified)

**Analog:** `.dark-factory/roles/BA.yaml` (full file) and `.dark-factory/roles/QA.yaml` (full file)

```yaml
# Business Analyst role definition (CFG-02 / CFG-03). Editing this file changes
# the resolved role in the next run's snapshot with no Python change.
name: BA
worker: fake
instructions: ../instructions/ba.md

tools: [repo.read, repo.search, artifacts.read, artifacts.write]
permissions:
  write_scope: []

before: [prepare_role_context]
after: [store_role_artifacts]

outputs: [requirements.md, acceptance_criteria.json]
examples: []
```
New role YAMLs copy this shape verbatim, changing `name`, `instructions`, `outputs`, and adding `inputs: [...]` (new field). Per RESEARCH: `ARCHITECTURE.yaml` → `inputs: [acceptance_criteria.json]`, `outputs: [design.md, constraints.json]`; `DEVELOPMENT.yaml` → `inputs: [design.md, constraints.json]`, `outputs: [implementation_summary.json]`; `QA.yaml` gets `inputs: [acceptance_criteria.json, implementation_summary.json]` added (its `outputs: [test_report.json, verdict.json]` already exists). `BA.yaml` gets `inputs: []` added explicitly (D-02: baseline docs are not repeated per-role, so BA's only declared `inputs` is empty).

---

### `src/dark_factory/roles/registry.py` — architect/developer/qa `Role` entries

**Analog:** `ba_role` (same file, lines 32-38)

```python
ba_role = Role(
    name="BA",
    worker="fake",
    description=(
        "Business Analyst -- clarifies and analyses the task; read-only on "
        "repository source, so it needs no worktree."
    ),
)
```
Add `architect_role`, `developer_role`, `qa_role` following this exact shape (`name`, `worker="fake"` per D-08, one-line `description`), and add each to `__all__`.

---

### `src/dark_factory/input/loaders.py` — `_load_spec`

**Analog:** `_load_text` (same file, lines 29-48)

```python
def _load_text(locator: str) -> NormalizedTask:
    """Build a :class:`NormalizedTask` from a plain-text task body. ..."""
    body = locator.strip().strip('"')
    if not body:
        raise UnresolvableSourceError("text: task body is empty")
    title = body.splitlines()[0][:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="text",
        source_ref=None,
        title=title,
        body=body,
        metadata={},
    )
```
Replace the current stub:
```python
def _load_spec(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError(
        "spec: sources are not supported until Phase 4 (spec loader)"
    )
```
with the real implementation given in RESEARCH's Code Examples (reads a file via `pathlib.Path`, raises `UnresolvableSourceError` — not `SourceNotSupportedError` — for missing/empty file, matching the CLI's existing exit-2 mapping at `cli.py:180`).

**Error handling pattern:** `UnresolvableSourceError` (not `SourceNotSupportedError`) for a missing/empty file — `src/dark_factory/cli.py:180`:
```python
except (UnresolvableSourceError, SourceNotSupportedError, ConfigError) as exc:
```

---

### `src/dark_factory/orchestrator/runner.py` — context-builder call site + schema-validation gate

**Analog:** existing `Signal.ROLE_FAILED` branch (lines ~467-482)

```python
elif signal is Signal.ROLE_FAILED:
    re_status = _ROLE_FAILED
    re_result = None
    re_error = outcome
    events = [
        EventWrite(
            type=EventType.ROLE_FAILED,
            payload={"role": node.name, "error": result.error or result.summary},
        ),
        EventWrite(type=EventType.RUN_FAILED, payload={"role": node.name}),
    ]
```
Per RESEARCH Pattern 4 (D-09): after the worker call returns and *before* `signal_from_result(result)` is computed, validate every JSON artifact the role's `outputs` marks as a machine type. On `pydantic.ValidationError`, force `signal = Signal.ROLE_FAILED` (or synthesize the identical `re_status/re_result/re_error/events` shape above) rather than trusting `result.status == COMPLETED`. Do **not** add new `EventType` members (`ARTIFACT_CREATED` etc. are explicitly deferred — see `events/catalog.py`'s own docstring); reuse `ROLE_FAILED`/`RUN_FAILED`.

Replace the call site `context = _build_context(run_id, state, node)` with `context = build_role_context(session, repo_root, run_id, state, role_def)` from the new `context/builder.py` module — same call position, same three-line proximity to `result = worker.execute(context)`.

---

### `tests/unit/test_single_mutation_path.py` — `_LIFECYCLE_CTORS`

**Analog:** the existing `HumanInteraction` addition, same file:
```python
_LIFECYCLE_CTORS = {"RunEvent", "RoleExecution", "HumanInteraction"}
```
Change to `{"RunEvent", "RoleExecution", "HumanInteraction", "ArtifactReference"}` in the same plan wave that introduces the ORM class (Pitfall 2).

---

### `tests/support/fake_artifacts.py` (new test helper)

**Analog:** `src/dark_factory/workers/fake.py::_default_script` (lines 46-53) for the "build a scripted `WorkerResult`" shape, and `domain/worker.py::ArtifactRef` for the reference shape each helper call must return.

```python
def _default_script() -> list[WorkerResult]:
    return [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            worker_session_id=f"fake-{uuid4()}",
        )
    ]
```
The new helper takes a run root + role name + `{filename: content}` mapping, writes each file under `artifacts/<role>/`, computes `hashlib.sha256(...).hexdigest()`, and returns `list[ArtifactRef]` to embed in that role's scripted `WorkerResult.artifacts` field — kept in `tests/support/`, not shipped `src/`, per RESEARCH Pattern 6 / Assumption A3.

## Shared Patterns

### Frozen, extra-forbid pydantic boundary models
**Source:** `src/dark_factory/domain/worker.py` (`WorkerResult`, `ArtifactRef`, `WorkerCapabilities`), `src/dark_factory/config/loader.py` (`RoleDefinition`, `RolePermissions`)
**Apply to:** every new model in `domain/artifacts.py`, the new `RoleContext` model in `context/builder.py`, `ArtifactReferenceWrite` in `persistence/mutations.py`.
```python
model_config = ConfigDict(frozen=True, extra="forbid")
```

### Single mutation path discipline
**Source:** `src/dark_factory/persistence/mutations.py` (module docstring + `HumanInteractionWrite`/`apply_transition` wiring), enforced by `tests/unit/test_single_mutation_path.py`
**Apply to:** `ArtifactReference` construction — only ever inside `apply_transition`'s `with session.begin():` block, never in `artifacts/store.py`, `context/builder.py`, or an action hook.

### Path-safety (no `..` escape, capped size)
**Source:** `src/dark_factory/config/loader.py` lines 134-144 (`instr_path.is_relative_to(root)` + `_MAX_INSTRUCTION_BYTES` cap)
**Apply to:** `artifacts/paths.py`'s artifact-path resolution and `context/builder.py`'s baseline-doc reads.

### Config-driven, no role-name branching
**Source:** `src/dark_factory/orchestrator/runner.py::_role_definition` (data lookup by value, never `if role == "BA"`); `src/dark_factory/roles/registry.py`'s `Role` dataclass note ("The orchestrator resolves that name through `WorkerRegistry`; it never branches on the value.")
**Apply to:** `ContextBuilder`'s filename→role resolution (Pattern 2) and any artifact-type dispatch in `artifacts/validation.py` (dispatch by filename/`role_def["outputs"]` entry, not by role name).

### Error types matching existing domain-error idiom
**Source:** `ConfigError` (`config/loader.py`), `ScriptExhaustedError` (`workers/fake.py`), `UnresolvableSourceError`/`SourceNotSupportedError` (`input/loaders.py` + `input/resolver.py`)
**Apply to:** new `MissingArtifactContentError` (Pitfall 6) — a plain `RuntimeError` subclass, raised loudly, never silently degrading to "no prior artifact."

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `hashlib.sha256` checksum call in `artifacts/paths.py` | utility | transform | No existing hashing code in this codebase (RESEARCH: "no hashing library is used anywhere in this codebase today"); use stdlib directly, no pattern to copy beyond the one-liner shown above. |
| `RoleContext` model's exact field set (baseline docs + resolved inputs + examples) | model | request-response | Genuinely new shape — CONTEXT.md/RESEARCH leave exact fields to planner discretion; use `_build_context`'s current dict fields as the floor and extend, per the excerpt above. |

## Metadata

**Analog search scope:** `src/dark_factory/` (domain, config, persistence, orchestrator, workers, roles, input), `.dark-factory/roles/`, `migrations/versions/`, `tests/unit/`
**Files scanned:** domain/worker.py, config/loader.py, config/repo_config.py, persistence/models.py, persistence/mutations.py, orchestrator/runner.py, roles/registry.py, workers/fake.py, input/loaders.py, migrations/versions/0003_pause_resume_lease.py, tests/unit/test_single_mutation_path.py, .dark-factory/roles/BA.yaml, .dark-factory/roles/QA.yaml
**Pattern extraction date:** 2026-09-12
