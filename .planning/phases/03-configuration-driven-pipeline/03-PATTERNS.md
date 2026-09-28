# Phase 3: Configuration-Driven Pipeline - Pattern Map

**Mapped:** 2026-09-10
**Files analyzed:** 18 (7 new source, 8 modified source, plus example config set + test guards + conftest fixture)
**Analogs found:** 18 / 18 (every new/modified file has a same-repo analog; RESEARCH.md pre-named most of them and this map confirms them against the tree)

No CONTEXT.md — discuss-phase was not run. File list taken from `03-RESEARCH.md` §"Recommended project-structure delta", §"Code Examples", §"Wave 0 Gaps", and the eight Pattern subsections, then verified against `git ls-files`.

Tracked-source note: every analog path below is git-tracked working-tree source under `src/`, `tests/`, or `migrations/`. `src/dark_factory/actions/` and `.dark-factory/` do not exist yet (`git ls-files` empty for both) — those are pure NEW.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/dark_factory/config/repo_config.py` (NEW) | config / schema model | transform (YAML dict → validated model) | `src/dark_factory/domain/worker.py` (frozen `extra="forbid"` pydantic v2 + `model_validator`) | exact (role), strong |
| `src/dark_factory/config/loader.py` (NEW) | config loader | file-I/O + transform (read YAML/MD → snapshot dict) | `src/dark_factory/input/loaders.py` + `src/dark_factory/input/resolver.py` | role-match (mapping-dispatch + phase-named errors) |
| `src/dark_factory/actions/registry.py` (NEW) | registry | request-response (name → callable lookup) | `src/dark_factory/workers/registry.py` (`WorkerRegistry`, `UnknownWorkerError`, `default_registry`) | exact — clone verbatim |
| `src/dark_factory/actions/context.py` (NEW) | domain model | transform (frozen boundary value) | `src/dark_factory/domain/worker.py::WorkerCapabilities` / `WorkerResult` | exact |
| `src/dark_factory/actions/builtins.py` (NEW) | utility callables | event-driven (hook invoked around role) | `src/dark_factory/orchestrator/runner.py::_build_context` (runner.py:116-131) | role-match (no-op MVP) |
| `src/dark_factory/actions/__init__.py` (NEW) | package init / lazy registration | event-driven (register-at-import) | `src/dark_factory/workers/registry.py:55-69` (lazy `default_registry.register(...)`) | exact |
| `src/dark_factory/workers/registry.py` (MODIFY) | registry | request-response | itself (add `__contains__` + 3 placeholder factories mirroring `_shared_fake_worker` at :62-69) | exact |
| `src/dark_factory/workflows/pipeline.py` (MODIFY) | workflow builder | transform (snapshot dict → `Pipeline`) | itself — `DEFAULT_PIPELINE` at pipeline.py:40; `RoleNode`/`Pipeline`/`index_of` unchanged | exact |
| `src/dark_factory/orchestrator/runner.py` (MODIFY) | orchestrator entrypoint | request-response + event-driven | itself — `start_run` (:156-174), `advance`/`_advance_once` (:194-264), `_run_current_role` (:307-342), `_workflow_snapshot` (:111-113) | exact |
| `src/dark_factory/orchestrator/lifecycle.py` (MODIFY) | orchestrator pure fn | transform | itself — `transition()` `RunStatus(first.name)` at lifecycle.py:87,104-108 (study only; likely zero edit) | exact |
| `src/dark_factory/persistence/mutations.py` (MODIFY) | persistence mutation | CRUD (one transaction) | itself — `create_run` (mutations.py:148-196), `redact(workflow, ...)` at :174 | exact (no signature change; pass richer dict) |
| `src/dark_factory/persistence/repositories.py` (MODIFY) | persistence read | CRUD (read) | itself — `load_run_state` → `RunState.workflow` (repositories.py:94-163, `workflow=dict(run.workflow)` at :158) | exact (confirm only) |
| `src/dark_factory/cli.py` (MODIFY) | CLI | request-response | itself — `run` command exit-2 guard (cli.py:158-168), `_ORCHESTRATION_ERRORS` (:64-83) | exact |
| `migrations/versions/0004_*.py` (NEW, OPTIONAL) | migration | schema DDL | `migrations/versions/0003_pause_resume_lease.py` (JSONB/column DDL, model byte-parity, mirror `downgrade`) | exact |
| `tests/unit/test_repo_config_schema.py` etc. (NEW) | test | — | `tests/unit/test_domain_models.py`, `tests/unit/test_workers.py` | role-match |
| `tests/unit/test_no_role_name_literal.py` (NEW) | test guard (AST/source) | — | `tests/unit/test_no_worker_name_leak.py` (line-scan, exempt dirs) | exact |
| `tests/unit/test_orchestrator_no_live_config_read.py` (NEW) | test guard (import graph) | — | `tests/unit/test_status_import_graph.py` (transitive closure walk) | exact |
| `tests/unit/test_single_mutation_path.py` (NO CHANGE) | test guard | — | itself — already `rglob`s `src/dark_factory/` (test_single_mutation_path.py:42-46); `actions/` auto-covered | exact |
| `tests/integration/test_phase3_acceptance.py` (NEW) | acceptance gate | — | `tests/integration/test_phase2_acceptance.py` (+ `test_phase_acceptance.py`) | exact — sibling |
| `tests/conftest.py` (MODIFY) | test fixture builder | file-I/O (write temp config tree) | `conftest.py:262-281` `fake_settings` builder + `use_fake_secrets` monkeypatch | role-match |
| `.dark-factory.yaml` + `.dark-factory/roles/*.yaml` + `.dark-factory/instructions/*.md` (NEW) | example config | — | RESEARCH §"Recommended `.dark-factory/` layout" + Pattern 1 / Pattern 2 YAML blocks | n/a (greenfield data) |

---

## Pattern Assignments

### `src/dark_factory/config/repo_config.py` (config schema, transform)

**Analog:** `src/dark_factory/domain/worker.py`

**Imports / module-docstring convention** (worker.py:1-14): module opens with a `"""..."""` explaining *why the boundary is validated as if external*; imports are `from pydantic import BaseModel, ConfigDict, Field, model_validator`. Match this — add `from dark_factory.domain.status import RunStatus` (the loader needs the legal role set). **Do NOT import anything from `dark_factory.config.settings`** (Pitfall 6 — `Settings.known_secret_values()` at settings.py:98-115 walks `model_fields` for `SecretStr`).

**Frozen-forbid model config** (worker.py:44-45, 57-58):
```python
model_config = ConfigDict(frozen=True, extra="forbid")
```
Apply verbatim to every sub-model (`WorkflowConfig`, `RepositoryConfig`, `QualityGateConfig`, `RetryConfig`, `PublishingConfig`, `RepoConfig`).

**Validator pattern** — worker.py uses `@model_validator(mode="after")` returning `Self` with a `ValueError` (worker.py:69-75):
```python
@model_validator(mode="after")
def _require_question_for_needs_input(self) -> Self:
    if self.status is WorkerResultStatus.NEEDS_INPUT and not self.questions:
        raise ValueError("questions must be non-empty when status is NEEDS_INPUT")
    return self
```
For `repo_config.py` use a `@field_validator("roles")` `@classmethod` (RESEARCH Code Examples lines 473-482) rejecting any entry not in `frozenset(RunStatus) - {CREATED, COMPLETED, WAITING_HUMAN, FAILED}` — i.e. `{BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}` (status.py:18-27). The `ValueError` it raises is wrapped into `ConfigError` by the loader.

**Enum-value convention** (status.py:15-27, worker.py:24-29): `StrEnum`, "value equals name". Reuse `RunStatus` directly — do not define a parallel `RoleName` enum (RESEARCH Alternatives / Open Question 1: role name == status value is the zero-change path; `transition()` does `RunStatus(role_name)` at lifecycle.py:87).

---

### `src/dark_factory/config/loader.py` (config loader, file-I/O + transform)

**Analogs:** `src/dark_factory/input/loaders.py`, `src/dark_factory/input/resolver.py`

**Phase-named typed error** (loaders.py:25-27, resolver.py:31-33):
```python
class SourceNotSupportedError(NotImplementedError):
    """Raised by a loader for a source kind whose implementation lands in a later phase."""
```
Mirror as `class ConfigError(ValueError)` with a docstring stating it is raised in `start_run` **before** `create_run` → CLI exit 2, no `runs` row (RESEARCH Code Examples lines 518-520).

**Mapping-dispatch, not conditionals** (loaders.py:63-72, resolver.py:38-42): loader selection is a `dict[SourceKind, Callable]`, and the module docstring explicitly says "not a chain of conditionals". The config loader iterates `repo.workflow.roles` and dispatches by building `<roles_dir>/<name>.yaml` paths — no `if role == "BA"` anywhere.

**Pure-classify-before-persist discipline** (resolver.py:3-13): resolver docstring — "runs *before anything is persisted* ... a classifier with a side effect is a side effect that cannot be undone". `load_effective_config()` inherits this: it only reads files and raises; it never opens a `Session`.

**`yaml.safe_load` + shape guard** (RESEARCH Code Examples lines 540-549, Pitfall 2 & 3): after `yaml.safe_load(path.read_text("utf-8"))`, `isinstance(data, dict)` check → `ConfigError` if `None`/scalar. Never `yaml.load`. Wrap `yaml.YAMLError` and pydantic `ValidationError` into `ConfigError`.

**Path-under-root check** (RESEARCH Security Domain, Pitfall — path traversal): `instr_path = (role_path.parent / rd.instructions).resolve()`; assert it is under `root.resolve()` and `.is_file()`; cap `len(text.encode("utf-8"))` at `_MAX_INSTRUCTION_BYTES = 64 * 1024`.

**Membership-only registry validation** (see `workers/registry.py` below): `rd.worker not in worker_registry` and `hook not in action_registry` — **never** `registry.get(name)` (that invokes the placeholder factory and raises; RESEARCH Pitfall 5).

**Snapshot output shape** (RESEARCH Code Examples lines 579-595): a plain JSON-serialisable `dict` with top-level `roles` list of dicts (`model_dump(mode="json")` for every nested model; `str()` every `Path`).

**Import-isolation guard target:** `orchestrator/*` must never transitively import this module (enforced by the new import-graph guard — see test section).

---

### `src/dark_factory/actions/registry.py` (registry, name→callable lookup)

**Analog:** `src/dark_factory/workers/registry.py` — clone the class verbatim.

`WorkerRegistry` core (registry.py:32-53):
```python
class UnknownWorkerError(KeyError):
    """Raised by :meth:`WorkerRegistry.get` for a name with no registered factory."""

class WorkerRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], CodingWorker]] = {}
    def register(self, name: str, factory: Callable[[], CodingWorker]) -> None:
        self._factories[name] = factory
    def get(self, name: str) -> CodingWorker:
        try:
            factory = self._factories[name]
        except KeyError:
            raise UnknownWorkerError(name) from None
        return factory()

default_registry = WorkerRegistry()
```
For `ActionRegistry`: rename → `_actions: dict[str, Callable[[ActionContext], None]]`, `get()` raises `UnknownActionError(KeyError)`, add `def __contains__(self, name: object) -> bool: return name in self._actions` (RESEARCH Pattern 5). Module-level `default_registry = ActionRegistry()`. `__all__` list like registry.py:29.

---

### `src/dark_factory/actions/context.py` (domain model, frozen boundary value)

**Analog:** `src/dark_factory/domain/worker.py::WorkerCapabilities` (worker.py:42-53)
```python
model_config = ConfigDict(frozen=True, extra="forbid")
```
`ActionContext` fields per RESEARCH Pattern 5 (lines 303-313): `run_id: UUID`, `role: str`, `worker: str`, `attempt: int`, `phase: Literal["before", "after"]`, `task: dict[str, Any]`, `answer: str | None`, `role_definition: dict[str, Any]`. Mirror `_build_context`'s existing shape (runner.py:124-131) for `run_id`/`role`/`worker`/`attempt`/`task`/`answer` so the two converge.

---

### `src/dark_factory/actions/builtins.py` (utility callables, event-driven)

**Analog:** `src/dark_factory/orchestrator/runner.py::_build_context` (runner.py:116-131) — the "built fresh every call, never carried between invocations" doc note.

MVP built-ins are **callable no-ops** (RESEARCH Pattern 5 table + Assumption A3), NOT `raise NotImplementedError` (a raising stub fails every run that names the hook). Signature `def prepare_role_context(ctx: ActionContext) -> None`. Register five: `prepare_role_context`, `ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, `collect_test_results`. Each docstring names the phase it becomes real in (4 / 5 / 5 / 4 / 9).

**Hard constraint:** an action must not construct `RunEvent`/`RoleExecution`/`HumanInteraction` or assign `.status` — `tests/unit/test_single_mutation_path.py:42-46` already `rglob`s all of `src/dark_factory/`, so `actions/` is auto-scanned (RESEARCH Pattern 8). Actions must not open a `Session`.

---

### `src/dark_factory/actions/__init__.py` (lazy register-at-import)

**Analog:** `src/dark_factory/workers/registry.py:55-69` — lazy registration comment + `default_registry.register("fake", _shared_fake_worker)` at import.
```python
_fake_worker: FakeWorker | None = None
def _shared_fake_worker() -> CodingWorker:
    global _fake_worker
    if _fake_worker is None:
        _fake_worker = FakeWorker()
    return _fake_worker
default_registry.register("fake", _shared_fake_worker)
```
`actions/__init__.py` imports `builtins` and calls `default_registry.register("prepare_role_context", builtins.prepare_role_context)` etc. — the five built-ins registered at import of `dark_factory.actions`.

---

### `src/dark_factory/workers/registry.py` (MODIFY — add `__contains__` + 3 placeholders)

**Analog:** itself. Add `__contains__` next to `get` (registry.py:45-50):
```python
def __contains__(self, name: object) -> bool:
    return name in self._factories
```
Add three placeholder factories mirroring the lazy `_shared_fake_worker` pattern (registry.py:62-69). RESEARCH Pattern 7:
```python
class _NotYetImplementedWorker:
    def __init__(self, name: str, phase: str) -> None: self._name, self._phase = name, phase
    def _fail(self, *_a, **_k):
        raise NotImplementedError(f"{self._name} worker adapter lands in Phase {self._phase}")
    execute = resume = capabilities = _fail

default_registry.register("claude-code", lambda: _NotYetImplementedWorker("claude-code", "7"))
default_registry.register("copilot",     lambda: _NotYetImplementedWorker("copilot", "8"))
default_registry.register("hermes",      lambda: _NotYetImplementedWorker("hermes", "8"))
```
Legal because `tests/unit/test_no_worker_name_leak.py:16` exempts `workers/` and `config/` (`_EXEMPT_TOP_LEVEL = {"workers", "config"}`). Keep the literals out of every other package.

---

### `src/dark_factory/workflows/pipeline.py` (MODIFY — add `pipeline_from_snapshot`, retire `DEFAULT_PIPELINE` prod default)

**Analog:** itself. `RoleNode` (pipeline.py:18-24), `Pipeline` + `index_of` (pipeline.py:26-37), `current_node` / `next_node` (pipeline.py:44-62) are **unchanged** — they already never assume a count.

Current default to remove from the production path (pipeline.py:13, 40):
```python
from dark_factory.roles.registry import ba_role
DEFAULT_PIPELINE = Pipeline(nodes=(RoleNode(name=ba_role.name, worker=ba_role.worker),))
```
Add (RESEARCH Pattern 4, lines 263-270), tolerating both legacy (`["BA"]`) and new (`[{"name":..,"worker":..}]`) shapes (RESEARCH Runtime State Inventory):
```python
def pipeline_from_snapshot(snapshot: Mapping[str, Any]) -> Pipeline:
    return Pipeline(nodes=tuple(
        RoleNode(name=r, worker="fake") if isinstance(r, str)
        else RoleNode(name=r["name"], worker=r["worker"])
        for r in snapshot["roles"]
    ))
```
Update the module docstring (pipeline.py:1-7) — it already forecasts this change ("Phase 3 replaces `DEFAULT_PIPELINE` with a snapshot"). Keep a `DEFAULT_PIPELINE`-shaped object only as a `tests/` fixture (RESEARCH Open Question 3).

---

### `src/dark_factory/orchestrator/runner.py` (MODIFY)

**Analog:** itself. Keyword-only-with-production-default is the established test-injection seam.

**`start_run`** (runner.py:156-174) currently:
```python
def start_run(source, *, session_factory=new_session, pipeline: Pipeline = DEFAULT_PIPELINE) -> UUID:
    kind, locator = classify(source)
    task = load(kind, locator)
    session = session_factory()
    try:
        return create_run(session, task=task, workflow=_workflow_snapshot(pipeline))
    finally:
        session.close()
```
Change (RESEARCH lines 600-613): add kw-only `worker_registry=default_registry`, `action_registry=action_default_registry`, `root: Path | None = None`; call `snapshot = load_effective_config(root or Path.cwd(), worker_registry=..., action_registry=...)` **before** `session_factory()`; pass `workflow=snapshot` straight to `create_run`. `ConfigError` propagates out un-caught (CLI maps it). `_workflow_snapshot` (runner.py:111-113) is superseded — delete or keep as a thin `{"roles": [...]}` extractor.

**`advance` / `_advance_once`** (runner.py:194-264): change `pipeline: Pipeline = DEFAULT_PIPELINE` → `pipeline: Pipeline | None = None`; in `_advance_once`, right after `load_run_state` (runner.py:244-248), `if pipeline is None: pipeline = pipeline_from_snapshot(state.workflow)`. Preserves D-02 "reconstruct everything from columns". `drive` (has the same default at ~:446) gets the same treatment.

**`_run_current_role`** (runner.py:307-342) — hook invocation site. `node`/`worker`/`context` are resolved at :329-337, `worker.execute`/`worker.resume` at :338-342, all **outside** `with session.begin()`. Insert: resolve `role_definition["before"]` names → `action_registry.get(name)(ActionContext(...))` immediately before the worker call; `["after"]` immediately after (still before `signal_from_result` at :354). Never branch on `node.name`.

---

### `src/dark_factory/orchestrator/lifecycle.py` (MODIFY — study only, likely no edit)

**Analog:** itself. `transition()` computes `RunStatus(first.name)` / `RunStatus(following.name)` (lifecycle.py:87, 104-108) and takes `pipeline` as a parameter already. It stays free of role-name literals because the pipeline is data. The only Phase-3 dependency: every `workflow.roles` entry MUST be a `RunStatus` member value — enforced by the `field_validator` in `repo_config.py`, not here.

---

### `src/dark_factory/persistence/mutations.py` (MODIFY — no signature change)

**Analog:** itself. `create_run` (mutations.py:148-196):
```python
def create_run(session, *, task: NormalizedTask, workflow: dict[str, Any]) -> UUID:
    known = _known_secrets()
    run_id = uuid4()
    with session.begin():
        session.add(Run(..., workflow=redact(workflow, known_secrets=known), status=RunStatus.CREATED, ...))
        session.add(RunEvent(run_id=run_id, ..., type=EventType.RUN_CREATED.value, payload=redact({...}, known_secrets=known)))
    return run_id
```
Phase 3 passes a richer `workflow` dict (the effective-config snapshot). **No code change required** — `redact(workflow, ...)` at mutations.py:174 already scrubs any JSONB dict; one `with session.begin()`. Update the docstring (mutations.py:154-161) to note `workflow` now carries the full snapshot. Do not add a parameter.

---

### `src/dark_factory/persistence/repositories.py` (MODIFY — confirm only)

**Analog:** itself. `load_run_state` already does `workflow=dict(run.workflow)` into `RunState.workflow` (repositories.py:158), and `RunState` (repositories.py:72-91) is `frozen`, `extra="forbid"`, fully detached with `workflow: dict[str, Any]`. Confirm the resume path (`advance` → `_advance_once`) reads `state.workflow` and never `load_effective_config`. Update `RunState.workflow` / `load_run_state` docstrings to record the column's new dual role (pipeline shape + full snapshot). Add a `config_snapshot` field only if the 0004-column option is chosen.

---

### `src/dark_factory/cli.py` (MODIFY — `ConfigError` → exit 2)

**Analog:** itself. `run` command (cli.py:158-168):
```python
@app.command()
def run(source: str) -> None:
    _route_logs_to_stderr()
    try:
        run_id = start_run(source)
    except (UnresolvableSourceError, SourceNotSupportedError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(str(run_id))
    _drive_and_exit(run_id)
```
Add `ConfigError` to the `except (...)` tuple and `from dark_factory.config.loader import ConfigError` to the import block (cli.py:29-52). It is already a `ValueError` subclass so `_ORCHESTRATION_ERRORS` (cli.py:64-83, includes bare `ValueError`) would catch it in the drive path — but the explicit `run`-guard entry makes "exit 2, nothing persisted, no run id on stdout" unambiguous (the `typer.echo(str(run_id))` at :167 must not run).

---

### `migrations/versions/0004_*.py` (NEW — OPTIONAL, only if separating snapshot from `runs.workflow`)

**Analog:** `migrations/versions/0003_pause_resume_lease.py`

- Header block: `revision` / `down_revision = "0003_pause_resume_lease"` / `branch_labels` / `depends_on` (0003:42-45); revision id ≤ 32 chars.
- Module docstring states what/why + "Reversible: `downgrade()` ... in mirror order" (0003:28-31).
- `op.add_column("runs", sa.Column("config_snapshot", postgresql.JSONB(), nullable=True))` — nullable, no server default = "not yet snapshotted", no back-fill (mirrors the 0003 lease-column rationale at 0003:22-26, 92-96).
- `downgrade()` = `op.drop_column("runs", "config_snapshot")` (mirror order, 0003:99-104).
- Model byte-parity: add the matching `mapped_column` to `persistence/models.py::Run` (0003 docstring "byte-for-byte equivalent to ... models").
- `migrations/env.py::_OWNED_TABLES` (env.py:44) unchanged — still the `runs` table.
- `tests/conftest.py::_schema_at_head` autouse fixture picks up 0004 automatically.

RESEARCH recommendation (Assumption A2, Open Question 2): **reuse `runs.workflow`, skip this migration.**

---

## Shared Patterns

### Registry allowlist (name → callable), never `getattr`/`importlib`
**Source:** `src/dark_factory/workers/registry.py:32-53` (+ `src/dark_factory/input/loaders.py:63-72` mapping-dispatch)
**Apply to:** `actions/registry.py`, `workers/registry.py` mods, and the loader's validation calls.
- `get()` raises a typed `KeyError` subclass; `__contains__` is the membership check used by config validation.
- A new entry = `default_registry.register("name", fn)` at import — zero orchestrator change (Compatibility constraint).

### Frozen, `extra="forbid"` pydantic v2 boundary models
**Source:** `src/dark_factory/domain/worker.py:44-45,57-58,69-75`
**Apply to:** every model in `config/repo_config.py`, `config/loader.py` (`RoleDefinition`, `RolePermissions`), `actions/context.py`.
```python
model_config = ConfigDict(frozen=True, extra="forbid")
```
Validators are `@field_validator(...) @classmethod` or `@model_validator(mode="after") -> Self`, raising `ValueError` with a message naming the field and the legal set.

### Phase-named typed error raised before any persist
**Source:** `src/dark_factory/input/loaders.py:25-27,51-60`, `src/dark_factory/input/resolver.py:31-33`
**Apply to:** `ConfigError(ValueError)` in `config/loader.py`; placeholder-worker `NotImplementedError(f"... lands in Phase {n}")`.
- Raised in `start_run` before `create_run` → CLI `raise typer.Exit(code=2)`, no `runs` row, no run id on stdout.

### One mutation path / one transaction
**Source:** `src/dark_factory/persistence/mutations.py:165` (`with session.begin():`), guarded by `tests/unit/test_single_mutation_path.py`
**Apply to:** all of `actions/` — no `RunEvent`/`RoleExecution`/`HumanInteraction` construction, no `.status` assignment, no `Session`. Hooks run outside `with session.begin()` in `_run_current_role` (RESEARCH Pitfall 8).

### Redaction on the way into JSONB
**Source:** `src/dark_factory/persistence/mutations.py:174` — `redact(workflow, known_secrets=_known_secrets())`
**Apply to:** the snapshot automatically (it rides `create_run(workflow=...)`). Backstop only — loader docstring + example configs must forbid secrets in `.dark-factory.yaml`; `config/repo_config.py` must not be reachable from `config/settings.py` (Pitfall 6).

### Keyword-only param with production default = test-injection seam
**Source:** `src/dark_factory/orchestrator/runner.py:156-161,194-200` (`*, session_factory=new_session, registry=default_registry, pipeline=...`)
**Apply to:** `start_run` (add `worker_registry`, `action_registry`, `root`), `advance`/`drive`/`_advance_once` (`pipeline: Pipeline | None = None`).

### Source-tree / import-graph guard tests
**Source:** `tests/unit/test_no_worker_name_leak.py` (line-scan, `_EXEMPT_TOP_LEVEL`, `_strip_comment`), `tests/unit/test_status_import_graph.py` (`_transitive_closure`, `_module_to_path`, sanity test that the walk really resolves)
**Apply to:** `test_no_role_name_literal.py` (no `"BA"`/`"ARCHITECTURE"`/`"DEVELOPMENT"`/`"QA"`/`"VERIFYING"`/`"PUBLISHING"` literal under `orchestrator/` or `workflows/pipeline.py`), `test_orchestrator_no_live_config_read.py` (`dark_factory.orchestrator.*` transitive closure excludes `dark_factory.config.loader`). Each guard ships with its self-proving sanity test, like `test_status_import_graph.py:90-97`.

### Acceptance gate = present-and-non-empty proof map
**Source:** `tests/integration/test_phase2_acceptance.py` (SUCCESS_CRITERIA / REQUIREMENTS dicts, `_assert_proofs_exist`, "missing file is a FAILURE not a skip", exact-set assertions, no `skip` call anywhere)
**Apply to:** `tests/integration/test_phase3_acceptance.py` — map SC1-SC4 + the 8 requirement ids (ORCH-02, ORCH-03, CFG-01..CFG-05, WORK-02) each to named proof files; sibling of, not extension of, the earlier gates.

### Temp-tree builder fixture
**Source:** `tests/conftest.py:262-281` — `fake_settings` builds a model from obviously-fake values; `use_fake_secrets` monkeypatches `mutations.get_settings`.
**Apply to:** a new `tmp_path`-based fixture that writes `.dark-factory.yaml` + `.dark-factory/roles/{BA,QA}.yaml` + `.dark-factory/instructions/{ba,qa}.md` under a temp root and returns it, for injection via `start_run(..., root=...)`. Companion monkeypatch fixture if a test needs `Path.cwd()` to resolve there.

---

## No Analog Found

None. Every file has a same-repo analog. The weakest matches (still adequate):

| File | Role | Data Flow | Note |
|------|------|-----------|------|
| `src/dark_factory/actions/builtins.py` | utility callables | event-driven | No existing "hook" concept; closest is `_build_context` (runner.py:116-131). MVP bodies are no-ops, so the analog is only for the docstring/"built fresh, not carried" convention. |
| `.dark-factory.yaml` + role YAML + instruction MD | example config data | — | Greenfield content; shape comes from RESEARCH Pattern 1 & 2, not a code analog. `.gitignore` gets one new line: `.dark-factory/runs/`. |

---

## Metadata

**Analog search scope:** `src/dark_factory/{config,domain,input,orchestrator,persistence,workers,workflows,roles}/`, `tests/{unit,integration,conftest.py}`, `migrations/`
**Files scanned this session:** ~20 (runner.py, pipeline.py, roles/registry.py, workers/registry.py, workers/base pattern, domain/worker.py, domain/status.py, config/settings.py, input/loaders.py, input/resolver.py, persistence/mutations.py, persistence/repositories.py, cli.py, migrations/env.py, migrations/versions/0003_*.py, tests/conftest.py, tests/unit/test_single_mutation_path.py, tests/unit/test_no_worker_name_leak.py, tests/unit/test_status_import_graph.py, tests/integration/test_phase2_acceptance.py) plus full `git ls-files` tree
**Pattern extraction date:** 2026-09-10

---

## PATTERN MAPPING COMPLETE

**Phase:** 3 - Configuration-Driven Pipeline
**Files classified:** 21 rows (7 new source, 8 modified source, 1 optional migration, 4 test files/guards, 1 conftest mod, example config set)
**Analogs found:** 21 / 21

### Coverage
- Files with exact analog: 16
- Files with role-match analog: 5
- Files with no analog: 0

### Key Patterns Identified
- Every registry in the codebase (`WorkerRegistry`, the new `ActionRegistry`) is the same ~15-line name→callable dict with a typed `KeyError` subclass; Phase 3 clones it and adds `__contains__` for invoke-free config validation.
- The effective-config snapshot mechanism already exists end to end: `create_run(workflow=...)` redacts at mutations.py:174, `load_run_state` returns it as `RunState.workflow` at repositories.py:158 — Phase 3 widens the dict, changes no persistence signature.
- Boundary models are uniformly `ConfigDict(frozen=True, extra="forbid")` pydantic v2 with `@field_validator`/`@model_validator` raising field-named `ValueError` (domain/worker.py), wrapped to `ConfigError` at the loader.
- Config validation errors follow the `input/` precedent: a phase-named typed exception raised before any persist, mapped by the CLI to exit 2 with nothing written.
- Guard tests have fixed idioms to copy verbatim: line-scan with exempt top-level dirs (`test_no_worker_name_leak.py`), transitive import-closure walk with a self-proving sanity test (`test_status_import_graph.py`), and the present-and-non-empty acceptance proof map (`test_phase2_acceptance.py`).

### File Created
`/Users/maryiakrauchanka/portfolio/dark-factory/.planning/phases/03-configuration-driven-pipeline/03-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. The planner can reference each analog by `file:line` in PLAN.md action steps.
