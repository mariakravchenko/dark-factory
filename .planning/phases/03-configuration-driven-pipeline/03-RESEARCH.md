# Phase 3: Configuration-Driven Pipeline - Research

**Researched:** 2026-09-10
**Domain:** Repository-config-driven orchestration — YAML config schema (pydantic v2), a per-run config snapshot for deterministic resume, a name→callable `ActionRegistry`, a widened `WorkerRegistry`, and a `Pipeline` built from the snapshot instead of a hardcoded default.
**Confidence:** HIGH (codebase seams — every relevant module read this session), MEDIUM (concrete YAML schema shape and the snapshot-vs-new-column choice — recommendations, not locked), HIGH (no new hard dependency except PyYAML, which CLAUDE.md already pins).

## Summary

Phase 3 is pure config plumbing on top of a system that already runs end to end. It adds **no new roles** (`roles/registry.py` docstring: "Phase 4 *adds* Architect, Developer and QA beside it rather than replacing a stub" `[VERIFIED: src/dark_factory/roles/registry.py:1-11]`), **no AI, no git, no artifacts table**. The work is: (1) a `.dark-factory.yaml` + `.dark-factory/` file set with a pydantic-v2 schema, parsed with `yaml.safe_load`; (2) resolving that config into one JSON-serialisable **effective-config snapshot** at run creation and persisting it in the JSONB column that already exists on `runs` and is already loaded on every resume (`runs.workflow` / `RunState.workflow` `[VERIFIED: src/dark_factory/persistence/repositories.py:87,158]`); (3) building the `Pipeline` from that snapshot inside `advance()` instead of from the module-level `DEFAULT_PIPELINE` `[VERIFIED: src/dark_factory/workflows/pipeline.py:40]`; (4) an `ActionRegistry` that mirrors the existing `WorkerRegistry` name→factory map `[VERIFIED: src/dark_factory/workers/registry.py:36-53]`; (5) registering the three real worker names in `WorkerRegistry` with placeholder factories; (6) validating unknown role / worker / action names at run creation so the CLI exits non-zero with **no `runs` row written** (`start_run` already raises before `create_run` and the CLI already maps that to exit 2 `[VERIFIED: src/dark_factory/orchestrator/runner.py:156-174]` `[VERIFIED: src/dark_factory/cli.py:158-168]`).

The single load-bearing constraint the planner must design around: **`lifecycle.transition()` computes the run status of a role as `RunStatus(role_name)`** — `RunStatus(first.name)` and `RunStatus(following.name)` `[VERIFIED: src/dark_factory/orchestrator/lifecycle.py:87,104-108]`, and `orchestrator/answers.py` does `RunStatus(state.current_role)` `[VERIFIED: src/dark_factory/orchestrator/answers.py:120]`. Every name in `workflow.roles` MUST therefore be a member value of `RunStatus` — one of `BA`, `ARCHITECTURE`, `DEVELOPMENT`, `QA`, `VERIFYING`, `PUBLISHING` `[VERIFIED: src/dark_factory/domain/status.py:18-27]` (never `CREATED` / `COMPLETED` / `WAITING_HUMAN` / `FAILED`). An out-of-set name is not a config error today — it is a `ValueError` raised deep inside `transition()` at execution time. The config loader must reject it at run creation.

The determinism requirement (CFG-05 / SC3) is nearly free: `create_run(session, task, workflow=...)` already redacts and persists whatever dict it is handed `[VERIFIED: src/dark_factory/persistence/mutations.py:148-196]`, `load_run_state` already reads it back into `RunState.workflow` `[VERIFIED: src/dark_factory/persistence/repositories.py:152-163]`, and `advance()` is already "reconstruct everything from columns" (D-02). The change is to make `advance()`/`drive()` build the pipeline from `state.workflow` rather than accept a `DEFAULT_PIPELINE` production default, and to make `advance` never call the config loader.

**Primary recommendation:** Add `pyyaml>=6,<7` to `pyproject.toml`. Create `dark_factory/config/repo_config.py` (pydantic v2 models, `extra="forbid"`, `frozen`) **separate from** `config/settings.py`. Create `dark_factory/config/loader.py` with `load_effective_config(root: Path) -> dict` that reads `.dark-factory.yaml` + every referenced role YAML + instruction Markdown, validates role names ∈ the legal `RunStatus` set, validates every `worker` name is in `WorkerRegistry` and every hook name is in `ActionRegistry` (membership only — do **not** invoke the factory), and returns one JSON-serialisable snapshot dict. Call it from `start_run()` before `create_run()`; raise `ConfigError` (add to the CLI's exit-2 tuple). Persist the snapshot in `runs.workflow` (**no migration**) — or a new `config_snapshot` JSONB column via revision `0004` if the planner wants pipeline-shape and full-config separated. Add `dark_factory/actions/` with an `ActionRegistry` cloned from `WorkerRegistry` plus `__contains__`, and register `prepare_role_context`, `ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, `collect_test_results` as MVP no-op-or-minimal callables. In `workflows/pipeline.py` add `pipeline_from_snapshot(snapshot) -> Pipeline`; drop `DEFAULT_PIPELINE` as a production default. Invoke before/after hooks around `_run_current_role`, outside the transaction, resolved by name from the snapshot — never `if role == ...`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Repo behaviour config (`.dark-factory.yaml`) | Config loader (`dark_factory/config/repo_config.py` + `loader.py`) | — | Read-only at runtime; `yaml.safe_load` → pydantic v2 (CLAUDE.md) |
| Role behaviour config (`.dark-factory/roles/*.yaml` + instruction `.md`) | Config loader | Role tier (consumes the resolved definition) | CFG-02/03: editable without touching Python |
| Config validation (unknown role/worker/action → non-zero exit, no orphan run) | Run-creation path (`start_run` → `load_effective_config`) | CLI (`run` command maps `ConfigError` → exit 2) | `start_run` already raises before any persist `[VERIFIED: runner.py:156-174]` |
| Effective-config snapshot (persist + redact) | Persistence — the one mutation path (`create_run(workflow=snapshot)`) | Config loader (produces the dict) | ORCH-06 + SEC-02: snapshot is run metadata, written through the single redacting call site `[VERIFIED: mutations.py:174]` |
| Snapshot read on resume | Persistence read path (`load_run_state` → `RunState.workflow`) | Orchestrator (`advance` builds `Pipeline` from it) | D-02 / invariant "configuration is never re-read live on resume" |
| Pipeline shape from config (ORCH-02/03) | `workflows/pipeline.py` (`pipeline_from_snapshot`) | Orchestrator (`_advance_once` calls it) | `Pipeline`/`RoleNode` already never assume a role count `[VERIFIED: pipeline.py:26-37,56-62]` |
| Worker creation (WORK-02) | `workers/registry.py` (`WorkerRegistry`) | Config loader (validates names) | Adapters land Phases 7-8; Phase 3 registers names + placeholder factories |
| Deterministic before/after actions (CFG-04) | `dark_factory/actions/` (`ActionRegistry`) | Orchestrator (`_run_current_role` invokes hooks by name) | Mirrors `WorkerRegistry`; "accepts new actions without core changes" |
| Tool grants / write-scope in role YAML | Config schema + snapshot only (NOT enforced this phase) | Phase 6 (TOOL-03 enforcement), Phase 5 (ROLE-05 write-scope) | Keep Phase 3 scoped: schema + snapshot, no enforcement |

## Project Constraints (from CLAUDE.md)

These carry the same authority as locked decisions. Research proposes nothing that contradicts them.

- **Stack is fixed:** Python 3.12 (`requires-python = ">=3.12"` `[VERIFIED: pyproject.toml:9]`), Neon PostgreSQL, SQLAlchemy 2.0 **synchronous**, Alembic, psycopg 3 (`postgresql+psycopg://`), pydantic v2, Typer. No async core.
- **Config is read-only at runtime → `yaml.safe_load` into pydantic models** (CLAUDE.md "PyYAML 6.0.3 ... `yaml.safe_load` into pydantic models is all that's needed. No comment round-tripping requirement → no `ruamel.yaml`").
- **No embedded JS / scripting runtime for actions.** The `ActionRegistry` is "a registry of plain Python callables referenced by name in config" (CLAUDE.md "What NOT to Use"). Deferred/out-of-scope: `PyMiniRacer` / `quickjs` / any embedded JS.
- **No generic arbitrary-DAG workflow engine.** `workflow.roles` is "a fixed ordered role list with two known feedback edges (QA→Developer, Quality-Gate→Developer)" — not Airflow/Prefect/Dagster.
- **Role ≠ Worker; no `if worker == "claude"` branching in the orchestrator** — enforced by `tests/unit/test_no_worker_name_leak.py` (forbids the literals `claude`/`copilot`/`hermes` outside `workers/` and `config/`) `[VERIFIED: tests/unit/test_no_worker_name_leak.py:16-17,25-33]`.
- **Compatibility:** "The workflow definition, tool registry, action registry, worker registry ... must all accept new entries without modifying the core orchestrator."
- **One mutation path, one transaction:** every lifecycle mutation commits through `persistence/mutations.py`; `tests/unit/test_single_mutation_path.py` is an AST guard that fails if any other module constructs `RunEvent`/`RoleExecution`/`HumanInteraction` or assigns `.status` `[VERIFIED: tests/unit/test_single_mutation_path.py:37-39,60-76]`. **Actions must not write lifecycle state.**
- **Redaction is not retrofitted.** The snapshot is persisted through `create_run`, which already calls `redact(workflow, known_secrets=...)` `[VERIFIED: mutations.py:174]`. Do not put credentials in `.dark-factory.yaml`.
- **Neon connection shape (do not regress):** `poolclass=NullPool`, `pool_pre_ping=True`, `connect_args={"prepare_threshold": None, "application_name": "dark-factory"}` `[VERIFIED: src/dark_factory/persistence/engine.py:68-77]`; Alembic DDL on the **direct** endpoint via `migrations/env.py` resolution `DATABASE_URL_DIRECT → DATABASE_URL → DARK_FACTORY_TEST_DATABASE_URL` `[VERIFIED: migrations/env.py:52-56]`.
- **Do not turn Neon into a document store** — this rule targets *artifact content* / blobs. A fully-resolved config snapshot (tens of KB) is run metadata and belongs in a JSONB column on `runs`; the additional_context brief confirms this reading.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORCH-02 | The orchestrator executes a configured ordered sequence of roles, not hardcoded role calls | § "Pattern 4: Pipeline from the snapshot". `advance()`/`drive()` stop defaulting to `DEFAULT_PIPELINE`; `_advance_once` calls `pipeline_from_snapshot(state.workflow)`. The drive loop is already count-agnostic `[VERIFIED: runner.py:440-488]` |
| ORCH-03 | The role pipeline is defined in `workflow.roles` and can be shortened/reordered without changing orchestrator code | § "Pattern 4" + § "Validation Architecture" SC1. Proof = reorder/shorten the YAML, re-run the CLI subprocess, assert executed order changes; AST guard asserts no role-name literal in `orchestrator/` or `workflows/pipeline.py` |
| CFG-01 | Repo behaviour in `.dark-factory.yaml` (version, `workflow.roles`, `repository.base_branch`, per-role definition files, `quality_gate.commands`, `retry` limits, `publishing.create_pr`) | § "Pattern 1: The `.dark-factory.yaml` schema" + § "Code Examples" (`RepoConfig` pydantic v2 model, `extra="forbid"`) |
| CFG-02 | Role behaviour in `.dark-factory/` files (role YAML, instruction Markdown, examples), editable without changing Python | § "Pattern 2: The `.dark-factory/` layout" + § "Pattern 3: Resolving a role definition". Instruction `.md` read as UTF-8, path relative to the role YAML dir, inlined into the snapshot |
| CFG-03 | A role definition is fully config-driven — instructions, tools, permissions, before/after hooks, outputs, worker | § "Pattern 3" — `RoleDefinition` model carries all six. **Phase 3 stores `tools`/`permissions` in the snapshot but does not enforce them** (Phase 6 / Phase 5) |
| CFG-04 | An `ActionRegistry` exposes deterministic before/after actions referenced by config and accepts new actions without core changes | § "Pattern 5: The `ActionRegistry`" — name→callable dict cloned from `WorkerRegistry` `[VERIFIED: workers/registry.py:36-53]`; `ActionContext` signature; MVP no-op/minimal built-ins; new action = register a function, zero orchestrator change |
| CFG-05 | The config resolved at run creation is snapshotted and persisted, so a later resume is deterministic even if `.dark-factory.yaml` changed | § "Pattern 6: The effective-config snapshot" — persist in `runs.workflow` (no migration) via `create_run(workflow=snapshot)`; `advance` builds the pipeline from `state.workflow`, never re-reads the file |
| WORK-02 | A `WorkerRegistry` maps `claude-code` / `copilot` / `hermes` to adapters; worker creation is centralized | § "Pattern 7: Widening `WorkerRegistry`" — register the three names in `workers/registry.py` with placeholder factories that raise `NotImplementedError("<name> adapter lands in Phase 7/8")` on invocation; add `WorkerRegistry.__contains__` for membership-only validation |
</phase_requirements>

## Standard Stack

### Core — one new dependency

| Library | Version | Purpose | Why standard |
|---------|---------|---------|--------------|
| **PyYAML** | `>=6,<7` (latest 6.0.3, published 2025-09-25) | Parse `.dark-factory.yaml` and `.dark-factory/roles/*.yaml` with `yaml.safe_load` | Named in CLAUDE.md's pinned stack; the canonical YAML parser; MIT; read-only config load needs nothing more. `[VERIFIED: npm registry — see Package Legitimacy Audit]` for existence; version currency `[CITED: https://pypi.org/project/PyYAML/]` |

Everything else Phase 3 needs is already pinned: `pydantic>=2.9,<3`, `pydantic-settings` (infra only), `sqlalchemy>=2.0.40,<2.1`, `alembic` (only if the planner picks the new-column option). `[VERIFIED: pyproject.toml:10-19]`

### Standard library (load-bearing, no dependency)

| Module | Purpose |
|--------|---------|
| `pathlib.Path` | Resolve `.dark-factory.yaml` from the working directory; resolve instruction paths relative to each role YAML's directory |
| `importlib` / plain module import | `ActionRegistry` built-ins are registered at import of `dark_factory.actions` — same lazy pattern as `default_registry.register("fake", ...)` `[VERIFIED: workers/registry.py:69]` |

### Alternatives Considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| PyYAML `safe_load` | `ruamel.yaml` | Only needed for comment-preserving round-trip writes (a future `dark-factory init` that edits an existing file). Config is read-only at runtime → not needed (CLAUDE.md). |
| Reuse `runs.workflow` for the snapshot | New `config_snapshot` JSONB column (revision `0004`) | New column separates "pipeline shape" from "full resolved config" and is self-documenting, at the cost of a migration + model + `load_run_state` + `RunState` changes. Reuse needs zero migration and the column already has the exact lifecycle treatment (redacted on write, loaded on every resume, carried in `RunState`). **Recommend reuse; new column is a clean alternative.** |
| `workflow.roles` entries are `RunStatus` values (`ARCHITECTURE`) | Decouple role name from `runs.status`; introduce a `RoleName` type + widen the status CHECK | Decoupling is a lifecycle + migration change that contradicts Phase-1 D-08 and the "no orchestrator edit" spirit. Keep role name == status value; loader validates membership. |
| `before`/`after` hooks as `list[str]` | Parameterised hooks via pydantic v2 discriminated unions (`Annotated[Union[...], Field(discriminator='type')]` `[CITED: https://docs.pydantic.dev/latest/concepts/unions/]`) | No hook in CFG-04's list takes arguments. Discriminated unions are YAGNI for MVP; add only when a hook genuinely needs typed params. |
| Placeholder factories for `claude-code`/`copilot`/`hermes` | Register nothing; unknown-name validation covers it | Registering the three names makes WORK-02 ("maps the three names") literally true now and lets a config that names `claude-code` resolve at creation and fail loudly at dispatch with a phase-named message. SC4's "unknown worker name fails validation" is still proven with a genuinely bogus name. |

**Installation:**
```bash
uv add "pyyaml>=6,<7"
# types-PyYAML is optional; PyYAML 6.x ships inline type hints — mypy --strict is fine without stubs
```

**Version verification:**
```bash
pip index versions PyYAML   # confirm 6.0.3 is current
```
PyYAML 6.0.3 released 2025-09-25 `[CITED: https://pypi.org/project/PyYAML/]`.

## Package Legitimacy Audit

`gsd-tools query package-legitimacy check --ecosystem pypi pyyaml` →

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `PyYAML` | PyPI | latest 6.0.3 published 2025-09-25 (project ~19 yrs) | seam returned `null` (registry API did not surface a weekly figure) | `https://pyyaml.org/` → `github.com/yaml/pyyaml` | **SUS** (reason: `unknown-downloads` only) | **Approved** — PyYAML is one of the most-downloaded Python packages in existence, MIT-licensed, maintained by the `yaml` org, **and explicitly pinned in CLAUDE.md's authoritative stack table** ("PyYAML 6.0.3"). The `SUS` verdict is a metrics-gap artifact, not a trust signal. |

**Packages removed due to `SLOP`:** none.
**Packages flagged `SUS`:** `PyYAML` — flagged only because the downloads metric was absent from the API response. It is pre-approved by CLAUDE.md (locked-decision authority). Per protocol the planner *may* add a `checkpoint:human-verify` before `uv add pyyaml`; given the CLAUDE.md pin, a one-line confirmation ("yes, PyYAML, the standard `import yaml`") is sufficient. `npm view` is not applicable (PyPI package); `pip index versions PyYAML` confirms 6.0.3. No postinstall script (PyPI wheels have no npm-style postinstall).

## Architecture Patterns

### System Architecture Diagram

```
                       dark-factory run text:"..."
                                  │
                                  ▼
                        cli.run  (cli.py:158)
                                  │
                                  ▼
      start_run(source)                                   ── run creation, pre-persist ──
        │  classify(source) ─► (kind, locator)                (raises ⇒ CLI exit 2, NO runs row)
        │  load(kind, locator) ─► NormalizedTask
        │  load_effective_config(cwd)  ◄── .dark-factory.yaml
        │     ├─ yaml.safe_load each file        ◄── .dark-factory/roles/*.yaml
        │     ├─ RepoConfig / RoleDefinition (pydantic v2, extra=forbid)
        │     ├─ read instruction .md (UTF-8, rel. to role YAML dir)  ◄── .dark-factory/instructions/*.md
        │     ├─ validate: each workflow.roles entry ∈ RunStatus role-set
        │     ├─ validate: each RoleDefinition.worker ∈ WorkerRegistry   (membership, no invoke)
        │     ├─ validate: each before/after name ∈ ActionRegistry
        │     └─► effective-config snapshot  (one JSON-serialisable dict)
        │  create_run(session, task=…, workflow=snapshot)
        │     └─ ONE with session.begin(): insert runs(status=CREATED, workflow=redact(snapshot)),
        │        insert run_events(RUN_CREATED)                         ─► Neon
        ▼
      run_id  ─► stdout line 1
        │
        ▼
      drive(run_id)  ── resume-first loop, once per committed step ──
        │  run_lease(run_id)  ─► claim / heartbeat / release           (Phase 2, unchanged)
        │  loop:
        │    state = load_run_state(session, run_id)   ─► RunState(.workflow = snapshot)  ◄── Neon
        │    pipeline = pipeline_from_snapshot(state.workflow)          ── NOT DEFAULT_PIPELINE
        │    node = current_node(pipeline, state.current_role)
        │    ── outside any transaction ──
        │    ctx = ActionContext(run_id, role=node.name, worker=node.worker, task, answer, role_def)
        │    for name in role_def.before:  ActionRegistry.get(name)(ctx)      ── hooks by name, no role branch
        │    worker = WorkerRegistry.get(node.worker)                        ── "fake" today
        │    result = worker.execute(ctx)  /  worker.resume(ctx, previous, answer)
        │    for name in role_def.after:   ActionRegistry.get(name)(ctx)
        │    signal = signal_from_result(result)
        │    next_status,next_role,next_step = transition(state, signal, pipeline)
        │       └─ RunStatus(next_role.name)   ◄── REQUIRES role name ∈ RunStatus
        │    ── ONE with session.begin() ──
        │    apply_transition(session, …, expected_owner_token=lease.token)  ─► Neon
        └─ until state.status ∈ STOP_STATUSES  (COMPLETED / FAILED / WAITING_HUMAN)
```

### Recommended `.dark-factory/` layout

```
<repo root>/
├── .dark-factory.yaml               # repo behaviour (CFG-01) — COMMITTED
└── .dark-factory/
    ├── roles/
    │   ├── BA.yaml                   # one file per pipeline role (CFG-02/03) — COMMITTED
    │   └── QA.yaml                   # add for the SC1 reorder/shorten proof
    ├── instructions/
    │   ├── ba.md                     # role instruction Markdown (CFG-02) — COMMITTED
    │   └── qa.md
    ├── examples/                     # optional few-shot files, context-only (CTX-03, Phase 4) — COMMITTED
    └── runs/                         # per-run artifact CONTENT (Phase 4) — add to .gitignore this phase
```

`.gitignore` currently has **no `.dark-factory` entry** `[VERIFIED: .gitignore]`, so the config files are tracked by default — good. Phase 3 should add exactly one line: `.dark-factory/runs/` (artifact content dir arrives Phase 4; keep it out of git now so it is not a surprise later).

### Recommended project-structure delta (Phase 3 touches/creates)

```
src/dark_factory/
├── config/
│   ├── settings.py            # UNCHANGED — infra secrets only; must NOT import repo_config
│   ├── repo_config.py         # NEW — pydantic v2 models for .dark-factory.yaml + role YAML
│   └── loader.py              # NEW — load_effective_config(root) -> dict ; ConfigError
├── actions/
│   ├── __init__.py            # NEW — registers built-ins at import (lazy, like workers/registry)
│   ├── registry.py            # NEW — ActionRegistry (clone of WorkerRegistry) + __contains__
│   ├── context.py             # NEW — ActionContext (frozen)
│   └── builtins.py            # NEW — prepare_role_context / ensure_clean_worktree / collect_diff /
│                              #        store_role_artifacts / collect_test_results  (MVP no-op/minimal)
├── roles/registry.py          # CHANGED — Role/ba_role either kept as a fallback or superseded by
│                              #           RoleDefinition from the snapshot (planner's call)
├── workers/registry.py        # CHANGED — register claude-code/copilot/hermes placeholders;
│                              #           add WorkerRegistry.__contains__
├── workflows/pipeline.py      # CHANGED — add pipeline_from_snapshot(snapshot); drop DEFAULT_PIPELINE
│                              #           as a production default
└── orchestrator/
    ├── runner.py              # CHANGED — start_run() loads+validates config; advance()/drive()/
    │                          #           _advance_once build the pipeline from state.workflow;
    │                          #           _run_current_role invokes before/after hooks by name
    └── (lifecycle.py / answers.py / lease.py UNCHANGED)
```

### Pattern 1: The `.dark-factory.yaml` schema (CFG-01)

```yaml
# .dark-factory.yaml
version: 1
repository:
  base_branch: main
workflow:
  roles: [BA]              # ordered; each ∈ {BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}
roles_dir: .dark-factory/roles     # optional; this is the default
quality_gate:
  commands:
    - "uv run pytest -q"
    - "uv run ruff check ."
retry:
  qa_developer_max_iterations: 3
  quality_gate_max_iterations: 2
publishing:
  create_pr: true
```

**What:** the repo-level knobs. **When:** loaded once per run, at creation, in `start_run`.
Pydantic v2: `RepoConfig(BaseModel, model_config=ConfigDict(extra="forbid", frozen=True))`. Every sub-section is its own frozen model. `quality_gate`, `retry`, `publishing` are **stored in the snapshot but not acted on this phase** (GATE-* Phase 9, LOOP-* Phase 9, GIT-03 Phase 10) — schema now so Phase 9/10 add behaviour without a schema change.

### Pattern 2: The `.dark-factory/roles/*.yaml` + instruction Markdown (CFG-02)

```yaml
# .dark-factory/roles/BA.yaml
name: BA                      # MUST equal a RunStatus role value and the workflow.roles entry
worker: fake                  # MUST be a registered WorkerRegistry name
instructions: ../instructions/ba.md      # path resolved relative to THIS file's directory
tools: [repo.read, repo.search, artifacts.read, artifacts.write]   # stored, not enforced (Phase 6)
permissions:
  write_scope: []             # BA is read-only on source; stored, not enforced (Phase 5 ROLE-05)
before: [prepare_role_context]
after:  [store_role_artifacts]
outputs: [requirements.md, acceptance_criteria.json]
examples: []                  # optional list of paths, context-only (CTX-03)
```

**Loading:** `yaml.safe_load(path.read_text("utf-8"))` per file. Instruction Markdown is read as UTF-8 text, its path resolved against `role_yaml_path.parent`, and its **contents inlined** into the snapshot (so a resumed process on a machine without the file is still deterministic — SC3). Guard the instruction size (recommend refuse/warn > 64 KB) so the snapshot row stays small.

### Pattern 3: Resolving a role definition

`RoleDefinition` pydantic model with fields `name`, `worker`, `instructions` (input path), `instruction_text` (populated by the loader), `tools`, `permissions`, `before`, `after`, `outputs`, `examples`. The loader:
1. reads `.dark-factory.yaml` → `RepoConfig`;
2. for each `name` in `workflow.roles`: read `<roles_dir>/<name>.yaml` → `RoleDefinition`; assert `RoleDefinition.name == name`;
3. read + inline the instruction file;
4. validate `name ∈ {BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}`;
5. validate `RoleDefinition.worker in worker_registry` (membership — see Pattern 7);
6. validate every `before`/`after` entry `in action_registry`;
7. build the snapshot dict.
Any failure → `ConfigError` (subclass of `ValueError`), raised before `create_run` → CLI exit 2, no `runs` row.

### Pattern 4: Pipeline from the snapshot (ORCH-02 / ORCH-03)

```python
# workflows/pipeline.py  (add; DEFAULT_PIPELINE removed as a production default)
def pipeline_from_snapshot(snapshot: Mapping[str, Any]) -> Pipeline:
    """Build the Pipeline from the persisted effective-config snapshot.
    `snapshot["roles"]` is the ordered list of {"name", "worker"} dicts."""
    return Pipeline(
        nodes=tuple(
            RoleNode(name=r["name"], worker=r["worker"]) for r in snapshot["roles"]
        )
    )
```

`Pipeline` / `RoleNode` / `index_of` / `next_node` / `current_node` are **unchanged** — they already never assume a count `[VERIFIED: pipeline.py:26-62]`. In `runner.py`, `advance()` / `drive()` / `_advance_once` currently take `pipeline: Pipeline = DEFAULT_PIPELINE` `[VERIFIED: runner.py:199,446]`. Change: keyword-only `pipeline: Pipeline | None = None`; when `None`, `_advance_once` does `pipeline = pipeline_from_snapshot(state.workflow)` right after `load_run_state` — preserving the "reconstruct everything from columns" rule (D-02) and keeping the test-injection seam (STATE.md 01-06: "keyword-only params with production defaults — the test injection seam"). `start_run` builds the snapshot for `create_run`; it no longer needs a `pipeline` arg (or keeps one only for tests).

`transition()` keeps taking `pipeline` as a parameter — no change. Its `RunStatus(first.name)` / `RunStatus(following.name)` calls `[VERIFIED: lifecycle.py:87,104-108]` are exactly why step 4 of the loader validation exists.

### Pattern 5: The `ActionRegistry` (CFG-04)

Clone `WorkerRegistry` verbatim `[VERIFIED: workers/registry.py:36-53]`:

```python
# actions/registry.py
class UnknownActionError(KeyError): ...

class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, Callable[[ActionContext], None]] = {}
    def register(self, name: str, fn: Callable[[ActionContext], None]) -> None:
        self._actions[name] = fn
    def get(self, name: str) -> Callable[[ActionContext], None]:
        try:
            return self._actions[name]
        except KeyError:
            raise UnknownActionError(name) from None
    def __contains__(self, name: object) -> bool:      # membership-only, for config validation
        return name in self._actions

default_registry = ActionRegistry()
```

```python
# actions/context.py
class ActionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    role: str
    worker: str
    attempt: int
    phase: Literal["before", "after"]
    task: dict[str, Any]
    answer: str | None
    role_definition: dict[str, Any]     # the resolved role dict from the snapshot
```

**MVP built-ins** (`actions/builtins.py`, registered at import of `dark_factory.actions`):

| Action | Phase 3 behaviour | Becomes real in |
|--------|-------------------|-----------------|
| `prepare_role_context` | fold today's `_build_context` `[VERIFIED: runner.py:116-131]` in here, or a no-op returning `ctx` unchanged | Phase 4 (CTX-01 ContextBuilder) |
| `ensure_clean_worktree` | MVP: no-op, or a cheap real check (cwd is a git repo, HEAD not detached) | Phase 5 (GIT-01 worktree) |
| `collect_diff` | no-op stub (no worktree yet) | Phase 5 / Phase 9 |
| `store_role_artifacts` | no-op stub (no artifacts table yet) | Phase 4 (ART-01/03) |
| `collect_test_results` | no-op stub (no quality gate yet) | Phase 9 (GATE-04) |

Registering them as **callable no-ops** (not `raise NotImplementedError`) is deliberate: SC2 wants "before/after hooks ... are read from `.dark-factory/` role YAML ... editing those files changes behaviour", which means the runner must actually *invoke* them; a raising stub would fail every run that names one. "Accepts new actions without core changes": a new action = add a function + `default_registry.register("name", fn)` — zero change to `runner.py` / `lifecycle.py` / `pipeline.py`.

**Invocation site:** `_run_current_role` in `runner.py` `[VERIFIED: runner.py:307-343]`, **outside** `with session.begin()` (same rule as the worker call — HITL-08). Resolve `role_definition["before"]` → callables → invoke; call the worker; resolve `["after"]` → invoke; then the existing `apply_transition`. Never branch on the role name.

### Pattern 6: The effective-config snapshot (CFG-05 / SC3)

The snapshot dict (recommended shape, persisted in `runs.workflow`):

```python
{
  "version": 1,
  "roles": [                                  # ordered — pipeline_from_snapshot reads this
    {"name": "BA", "worker": "fake",
     "instructions_path": ".dark-factory/instructions/ba.md",
     "instruction_text": "<inlined UTF-8 contents>",
     "tools": [...], "permissions": {...},
     "before": ["prepare_role_context"], "after": ["store_role_artifacts"],
     "outputs": ["requirements.md", "acceptance_criteria.json"], "examples": []},
  ],
  "repository": {"base_branch": "main"},
  "quality_gate": {"commands": [...]},
  "retry": {"qa_developer_max_iterations": 3, "quality_gate_max_iterations": 2},
  "publishing": {"create_pr": true},
}
```

- `create_run(session, task=task, workflow=snapshot)` already `redact()`s and inserts it `[VERIFIED: mutations.py:174]` — no new write path.
- `load_run_state` already returns it as `RunState.workflow` (a plain `dict`, detached) `[VERIFIED: repositories.py:87,158]`.
- **The determinism guarantee:** `advance()`/`drive()` build the pipeline from `RunState.workflow` and never call `load_effective_config`. Edit `.dark-factory.yaml`, resume → the snapshot wins. Invariant "configuration is never re-read live on resume" holds by construction if `orchestrator/` does not import `config.loader` — enforce with an import-graph guard (Pattern 8).
- Top-level key `roles` keeps the current `_workflow_snapshot` shape `[VERIFIED: runner.py:111-113]` (`{"roles": [...]}`), so nothing that reads today's snapshot shape breaks — the entries just grow from bare names to dicts. Update `_workflow_snapshot` accordingly (it becomes `snapshot["roles"]` extraction from the loader output, or the loader replaces it entirely).

### Pattern 7: Widening `WorkerRegistry` (WORK-02)

```python
# workers/registry.py  (add)
class _NotYetImplementedWorker:
    def __init__(self, name: str, phase: str) -> None: self._name, self._phase = name, phase
    def _fail(self, *_a, **_k):  # execute/resume/capabilities all route here
        raise NotImplementedError(f"{self._name} worker adapter lands in Phase {self._phase}")
    execute = resume = capabilities = _fail

default_registry.register("claude-code", lambda: _NotYetImplementedWorker("claude-code", "7"))
default_registry.register("copilot",     lambda: _NotYetImplementedWorker("copilot", "8"))
default_registry.register("hermes",      lambda: _NotYetImplementedWorker("hermes", "8"))

def __contains__(self, name: object) -> bool:      # add to WorkerRegistry
    return name in self._factories
```

This is legal under `test_no_worker_name_leak.py` because the literals live under `workers/` (exempt) `[VERIFIED: tests/unit/test_no_worker_name_leak.py:16`—`_EXEMPT_TOP_LEVEL = {"workers", "config"}]`. **Config validation must use `name in registry`, never `registry.get(name)`** — `get()` invokes the factory `[VERIFIED: workers/registry.py:45-50]` and would raise the placeholder error during validation. SC4's "unknown worker name fails validation at run creation" is proven with a genuinely unregistered name (`worker: bogus`), which `__contains__` returns `False` for → `ConfigError` → exit 2, no run row. The shipped example `.dark-factory/roles/*.yaml` all use `worker: fake` so the project still runs end to end today.

### Pattern 8: The "no orchestrator edit" / "no live re-read" guards

Mirror the two existing AST/import guards:
- **`test_status_import_graph.py` style** `[VERIFIED: tests/unit/test_status_import_graph.py:57-88]` — assert the transitive import closure of `dark_factory.orchestrator.runner` (and `workflows.pipeline`) does **not** include `dark_factory.config.loader` (control state / pipeline comes from the snapshot column, never a live file read).
- **`test_no_worker_name_leak.py` style** `[VERIFIED: tests/unit/test_no_worker_name_leak.py:39-54]` — assert no `RunStatus` role-name literal (`"BA"`, `"ARCHITECTURE"`, `"DEVELOPMENT"`, `"QA"`, `"VERIFYING"`, `"PUBLISHING"`) appears in `orchestrator/` or `workflows/pipeline.py` source (the pipeline is data from the snapshot, not code).
- **`test_single_mutation_path.py`** `[VERIFIED: tests/unit/test_single_mutation_path.py:42-46]` already `rglob`s all of `src/dark_factory/` — the new `actions/` package is automatically in scope: an action that constructs `RunEvent`/`RoleExecution`/`HumanInteraction` or assigns `.status` fails the guard. No change needed; note it in the plan so an action author knows.
- **SC1 strongest form:** an integration test that runs the CLI subprocess with `workflow.roles: [BA, QA]`, then rewrites the YAML to `[QA, BA]`, re-runs, and asserts the executed transition sequence changed — with a companion assertion that `git diff --stat src/dark_factory/orchestrator src/dark_factory/workflows` is empty across the two runs (no source touched).

### Anti-Patterns to Avoid

- **`yaml.load()` without `SafeLoader`** — arbitrary Python object construction / RCE from a repo-controlled file. Always `yaml.safe_load`. Add a source grep guard over `config/`.
- **Leaving `DEFAULT_PIPELINE` as a live production default** — a run with a missing/empty snapshot would silently execute the old hardcoded `[BA]` instead of failing. Make the snapshot mandatory; remove the default.
- **Validating a worker name with `registry.get(name)`** — invokes the placeholder factory and raises during validation. Use `name in registry`.
- **Putting `RepoConfig` on `Settings`** — `Settings.known_secret_values()` walks `model_fields` looking for `SecretStr` `[VERIFIED: config/settings.py:98-115]`; a repo-config field there pollutes the redaction map. Keep `repo_config.py` import-isolated from `settings.py`.
- **Actions that open a `Session` / write lifecycle state** — breaks the one-mutation-path invariant and the `test_single_mutation_path.py` guard.
- **Re-reading `.dark-factory.yaml` in `advance()`/`resume`** — breaks CFG-05 / SC3. The file is read exactly once, in `start_run`.
- **Discriminated-union / parameterised hook specs for MVP** — YAGNI; `before`/`after` are `list[str]`.
- **Inlining large instruction files unbounded** — cap size; a multi-hundred-KB instruction set would bloat every `runs` row and every `load_run_state`.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | a hand parser / `eval` | `yaml.safe_load` (PyYAML) | Anchors, multi-doc, quoting, unicode — all solved; `safe_load` blocks object injection |
| Config schema validation + clear errors | ad-hoc `dict.get` + `assert` | pydantic v2 models (`extra="forbid"`, `field_validator`) | Precise field-path errors, `frozen` immutability, JSON-serialisable `model_dump(mode="json")` for the snapshot |
| Name→callable dispatch for actions | `getattr(module, name)` / `importlib` on a config string | `ActionRegistry` (clone of `WorkerRegistry`) | `getattr` on a config-supplied string is an arbitrary-import surface; a registry is an explicit allowlist and matches the project's compatibility constraint |
| Worker construction | `if name == "claude-code": ClaudeCodeWorker()` | `WorkerRegistry` (already exists) | Role ≠ Worker; CI-enforced no-branching |
| Per-run config immutability across resume/crash | copying files, mtime checks, re-parsing and diffing | one JSON snapshot in a `runs` JSONB column, read by `load_run_state` | The column already has redaction-on-write and load-on-every-resume; a file-based scheme reintroduces "which machine has the file" (that is Phase 5's problem, not config's) |

**Key insight:** every registry Phase 3 needs (`WorkerRegistry`, and the `ActionRegistry` to build) is the *same* five-line name→callable dict, and the snapshot mechanism (`runs.workflow` + `load_run_state` + `RunState.workflow`) is *already wired end to end* — Phase 3 widens existing seams, it does not add machinery.

## Runtime State Inventory

Phase 3 is greenfield config plumbing — it introduces no rename/refactor of a persisted string, no external service registration, no OS-level state. One item is close to "migration-shaped" and is called out:

| Category | Items found | Action required |
|----------|-------------|-----------------|
| Stored data | `runs.workflow` JSONB currently holds `{"roles": ["BA"]}` for existing runs `[VERIFIED: runner.py:111-113]`. Phase 3 widens the shape to the full effective-config snapshot. | **Forward-only, no back-fill.** `pipeline_from_snapshot` must tolerate the legacy shape (`roles` = list of bare strings) OR the plan accepts that pre-Phase-3 runs are already terminal (Phase 1/2 test runs) and need no migration. Recommend: `pipeline_from_snapshot` handles both `["BA"]` and `[{"name":..., "worker":...}]`. |
| Live service config | None — no external service holds Dark Factory config. | None. |
| OS-registered state | None. | None. |
| Secrets / env vars | `.dark-factory.yaml` must **not** carry credentials; infra secrets stay in `Settings`/`.env` `[VERIFIED: config/settings.py:27-59]`. The snapshot is redacted on write regardless `[VERIFIED: mutations.py:174]`. | Loader docstring + README note: no secrets in repo config. |
| Build artifacts | New dependency `pyyaml` → `uv.lock` changes; `uv sync` / `uv lock --check` in CI. | `uv add pyyaml`; commit `uv.lock`. |

**Nothing found** for live-service-config and OS-registered-state — verified by: no `integrations/` module exists yet, no scheduler/daemon in the codebase, `grep` of `src/` for external-service config returns only the Neon engine and (unused) `github_token`.

## Common Pitfalls

### Pitfall 1: A `workflow.roles` entry that is not a `RunStatus` value
**What goes wrong:** `transition()` calls `RunStatus("Architect")` (or `"Developer"`, or a typo) → `ValueError` raised deep in the pure transition function `[VERIFIED: lifecycle.py:87,104-108]`, at *step execution* time, under the lease, after the `runs` row exists — the worst place to discover it.
**Why:** the run status of a role IS the role name; the config author naturally writes human role names ("Architect") not status values ("ARCHITECTURE").
**How to avoid:** `WorkflowConfig` has a `field_validator("roles")` that rejects any entry not in `{RunStatus.BA, RunStatus.ARCHITECTURE, RunStatus.DEVELOPMENT, RunStatus.QA, RunStatus.VERIFYING, RunStatus.PUBLISHING}` (i.e. `set(RunStatus) - {CREATED, COMPLETED, WAITING_HUMAN, FAILED}`) → `ConfigError` at run creation → exit 2, no run row.
**Warning signs:** a run that reaches `CREATED` then fails on the first `advance` with a bare `ValueError` mentioning a role name.

### Pitfall 2: `yaml.safe_load` of an empty or scalar file
**What goes wrong:** an empty `.dark-factory.yaml` → `yaml.safe_load` returns `None`; a file containing just `main` → returns a `str`. `RepoConfig.model_validate(None)` raises a pydantic error that is technically fine, but a bare `parsed["workflow"]` first would `TypeError`.
**How to avoid:** after `safe_load`, assert the result is a `dict` before handing it to pydantic; otherwise raise `ConfigError("`.dark-factory.yaml` is empty or not a mapping")`.

### Pitfall 3: `yaml.load` instead of `yaml.safe_load`
**What goes wrong:** `yaml.load` without an explicit `SafeLoader` can construct arbitrary Python objects from a repo-controlled file (historical RCE class).
**How to avoid:** only ever `yaml.safe_load`. Add a grep/AST guard over `src/dark_factory/config/` for `yaml.load(` / `Loader=` that is not `SafeLoader`.

### Pitfall 4: Config re-read on resume
**What goes wrong:** `advance()` or a helper calls `load_effective_config()` → a `.dark-factory.yaml` edited during a pause changes the resumed pipeline → SC3 fails, invariant violated.
**How to avoid:** pipeline comes from `RunState.workflow` only. Enforce with an import-graph guard: `dark_factory.orchestrator.*` transitively must not import `dark_factory.config.loader` (mirror `test_status_import_graph.py` `[VERIFIED: tests/unit/test_status_import_graph.py:78-88]`).
**Warning signs:** an `import` of the loader anywhere under `orchestrator/`.

### Pitfall 5: Validating a worker/action name by invoking it
**What goes wrong:** `worker_registry.get("claude-code")` during validation → placeholder `NotImplementedError` → run creation fails for a *known* future worker; or `action_registry.get(name)` for a valid built-in returns fine but couples validation to import side effects.
**How to avoid:** add `__contains__` to both registries; validation is `name in registry`.

### Pitfall 6: `RepoConfig` fields leaking into the secret-redaction map
**What goes wrong:** if `repo_config.py` types are reachable from `Settings` (import, subclass, or a shared base with `SecretStr` fields), `known_secret_values()` `[VERIFIED: config/settings.py:98-115]` walks them and the redaction map is polluted / a config value is treated as a secret.
**How to avoid:** `repo_config.py` imports nothing from `settings.py` and vice versa; no `SecretStr` in repo-config models. A one-line import guard test.

### Pitfall 7: Snapshot bloat / non-JSON-serialisable values
**What goes wrong:** inlining a large instruction set into every `runs` row; or leaving a `Path` / `datetime` in the snapshot dict → JSONB insert error or a `model_dump()` without `mode="json"`.
**How to avoid:** `model_dump(mode="json")` for every model that goes into the snapshot; resolve `Path` → `str`; read instruction files to `str`; cap instruction file size (recommend 64 KB, raise `ConfigError` above it).

### Pitfall 8: Hooks invoked inside the transaction
**What goes wrong:** an `after` hook runs inside `with session.begin()` → a slow/hanging hook holds a DB transaction across non-DB work (HITL-08 violation), or the hook opens its own session and deadlocks on the row lock `apply_transition` holds `[VERIFIED: mutations.py:258-259]`.
**How to avoid:** hooks run in `_run_current_role` *before* and *after* the worker call, all outside `with session.begin()`, exactly where the worker call already sits.

## Code Examples

### `RepoConfig` (pydantic v2) — `config/repo_config.py`
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
from dark_factory.domain.status import RunStatus

_LEGAL_ROLE_STATUSES = frozenset(RunStatus) - {
    RunStatus.CREATED, RunStatus.COMPLETED, RunStatus.WAITING_HUMAN, RunStatus.FAILED,
}   # -> {BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}

class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    roles: list[str] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def _roles_are_legal_statuses(cls, v: list[str]) -> list[str]:
        bad = [r for r in v if r not in {s.value for s in _LEGAL_ROLE_STATUSES}]
        if bad:
            raise ValueError(
                f"workflow.roles entries must be RunStatus role values "
                f"({sorted(s.value for s in _LEGAL_ROLE_STATUSES)}); got illegal: {bad}"
            )
        return v

class RepositoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    base_branch: str = "main"

class QualityGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    commands: list[str] = Field(default_factory=list)

class RetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    qa_developer_max_iterations: int = Field(default=3, ge=0)
    quality_gate_max_iterations: int = Field(default=2, ge=0)

class PublishingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    create_pr: bool = True

class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = 1
    repository: RepositoryConfig = RepositoryConfig()
    workflow: WorkflowConfig
    roles_dir: str = ".dark-factory/roles"
    quality_gate: QualityGateConfig = QualityGateConfig()
    retry: RetryConfig = RetryConfig()
    publishing: PublishingConfig = PublishingConfig()
```

### `RoleDefinition` + loader skeleton — `config/loader.py`
```python
import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, ValidationError

class ConfigError(ValueError):
    """Repo config is missing, malformed, or references an unknown role/worker/action.
    Raised in start_run BEFORE create_run — the CLI maps it to exit 2, no runs row."""

class RolePermissions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    write_scope: list[str] = Field(default_factory=list)

class RoleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    worker: str
    instructions: str                      # input path, relative to the role YAML dir
    tools: list[str] = Field(default_factory=list)
    permissions: RolePermissions = RolePermissions()
    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)

_MAX_INSTRUCTION_BYTES = 64 * 1024

def _safe_load_mapping(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping, got {type(data).__name__}")
    return data

def load_effective_config(root: Path, *, worker_registry, action_registry) -> dict:
    repo_raw = _safe_load_mapping(root / ".dark-factory.yaml")
    try:
        repo = RepoConfig.model_validate(repo_raw)
    except ValidationError as exc:
        raise ConfigError(f".dark-factory.yaml: {exc}") from exc

    roles_dir = root / repo.roles_dir
    resolved_roles: list[dict] = []
    for role_name in repo.workflow.roles:
        role_path = roles_dir / f"{role_name}.yaml"
        try:
            rd = RoleDefinition.model_validate(_safe_load_mapping(role_path))
        except ValidationError as exc:
            raise ConfigError(f"{role_path}: {exc}") from exc
        if rd.name != role_name:
            raise ConfigError(f"{role_path}: name {rd.name!r} != workflow.roles entry {role_name!r}")
        if rd.worker not in worker_registry:
            raise ConfigError(f"{role_path}: unknown worker {rd.worker!r}")
        for hook in (*rd.before, *rd.after):
            if hook not in action_registry:
                raise ConfigError(f"{role_path}: unknown action {hook!r}")
        instr_path = (role_path.parent / rd.instructions).resolve()
        if not instr_path.is_file():
            raise ConfigError(f"{role_path}: instructions file not found: {instr_path}")
        text = instr_path.read_text("utf-8")
        if len(text.encode("utf-8")) > _MAX_INSTRUCTION_BYTES:
            raise ConfigError(f"{instr_path}: instruction file exceeds {_MAX_INSTRUCTION_BYTES} bytes")
        resolved_roles.append({
            "name": rd.name, "worker": rd.worker,
            "instructions_path": str(instr_path.relative_to(root)),
            "instruction_text": text,
            "tools": rd.tools, "permissions": rd.permissions.model_dump(mode="json"),
            "before": rd.before, "after": rd.after,
            "outputs": rd.outputs, "examples": rd.examples,
        })

    return {
        "version": repo.version,
        "roles": resolved_roles,
        "repository": repo.repository.model_dump(mode="json"),
        "quality_gate": repo.quality_gate.model_dump(mode="json"),
        "retry": repo.retry.model_dump(mode="json"),
        "publishing": repo.publishing.model_dump(mode="json"),
    }
```

### `start_run` change — `orchestrator/runner.py`
```python
def start_run(source: str, *, session_factory=new_session,
              worker_registry=default_registry, action_registry=action_default_registry,
              root: Path | None = None) -> UUID:
    kind, locator = classify(source)
    task = load(kind, locator)
    snapshot = load_effective_config(          # raises ConfigError -> CLI exit 2, no runs row
        root or Path.cwd(),
        worker_registry=worker_registry, action_registry=action_registry,
    )
    session = session_factory()
    try:
        return create_run(session, task=task, workflow=snapshot)
    finally:
        session.close()
```

### CLI change — `cli.py`
```python
from dark_factory.config.loader import ConfigError
...
@app.command()
def run(source: str) -> None:
    _route_logs_to_stderr()
    try:
        run_id = start_run(source)
    except (UnresolvableSourceError, SourceNotSupportedError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(str(run_id))
    _drive_and_exit(run_id)
```
(`ConfigError` is a `ValueError` subclass, already caught by `_ORCHESTRATION_ERRORS` in the drive path `[VERIFIED: cli.py:64-83]`; adding it explicitly to the `run` guard makes exit 2 + "nothing persisted" unambiguous.)

## State of the Art

| Old approach (Phase 1/2) | Current approach (Phase 3) | When changed | Impact |
|--------------------------|----------------------------|--------------|--------|
| `DEFAULT_PIPELINE = Pipeline((RoleNode("BA","fake"),))` module constant `[VERIFIED: pipeline.py:40]` | `pipeline_from_snapshot(state.workflow)` built per `advance` | Phase 3 | Pipeline shape is data in a `runs` column, not code |
| `runs.workflow = {"roles": ["BA"]}` `[VERIFIED: runner.py:111-113]` | `runs.workflow` = full effective-config snapshot (roles + resolved defs + instruction text + quality_gate + retry + publishing) | Phase 3 | Resume is file-independent (SC3) |
| Role catalog = one hardcoded `ba_role` dataclass `[VERIFIED: roles/registry.py:30-37]` | `RoleDefinition` loaded from `.dark-factory/roles/*.yaml` | Phase 3 | Role behaviour editable without Python (CFG-02/03) |
| `WorkerRegistry` knows only `"fake"` `[VERIFIED: workers/registry.py:69]` | `+ claude-code / copilot / hermes` placeholder factories | Phase 3 (WORK-02) | Real adapters slot in Phases 7-8 with no registry change |
| No before/after hook concept | `ActionRegistry` name→callable, invoked around each role by config | Phase 3 (CFG-04) | Deterministic pre/post steps extensible without core edits |

**Deprecated/outdated:**
- `DEFAULT_PIPELINE` as a production default — remove (keep at most a test fixture).
- `_workflow_snapshot(pipeline)` in `runner.py` — superseded by `load_effective_config`'s output; keep only if the planner wants a thin adapter that extracts `{"roles":[...]}`.
- `roles/registry.py::ba_role` — either repurpose as a fallback or delete once role definitions come from YAML (planner's call; deleting is cleaner and matches "no hardcoded role").

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | The legal `workflow.roles` name set is exactly `RunStatus` minus `{CREATED, COMPLETED, WAITING_HUMAN, FAILED}` = `{BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING}`. Derived from `RunStatus(role_name)` in `transition()`/`answers.py` `[VERIFIED: lifecycle.py:87,104-108; answers.py:120]` and the STATE-07 enum `[VERIFIED: status.py:18-27]`. | Summary, Pitfall 1, Code Examples | If the planner instead wants human role names ("Architect") in config, the status CHECK + `transition()` + `answers.py` all need changing — a much larger phase. Recommend confirming the status-value spelling is acceptable in `.dark-factory.yaml`. |
| A2 | Persist the snapshot by **reusing `runs.workflow`** (no migration) rather than adding a `config_snapshot` column. | Pattern 6, Alternatives, Migration | If the planner prefers a dedicated column: revision `0004_config_snapshot` (`op.add_column("runs", sa.Column("config_snapshot", postgresql.JSONB(), nullable=True))`), plus model + `load_run_state` + `RunState` field + byte-for-byte model/migration parity (the 0003 pattern `[VERIFIED: migrations/versions/0003_pause_resume_lease.py:47-55]`); `_OWNED_TABLES` unchanged (same `runs` table) `[VERIFIED: migrations/env.py:45]`. |
| A3 | MVP built-in actions are **no-op / minimal callables**, not `raise NotImplementedError`, so the runner can actually invoke before/after hooks (SC2). | Pattern 5 | If the planner wants hooks that *do* something in Phase 3, `prepare_role_context` is the only candidate with real work available (fold in `_build_context`). |
| A4 | Inline instruction Markdown **text** into the snapshot (size-capped 64 KB) rather than storing a path + hash. | Pattern 2, Pattern 6, Pitfall 7 | If instruction sets are expected to be large, store `{path, sha256}` and rely on Phase 5 artifact durability to carry the file — but then SC3 resume on a fresh machine needs the file present. Inlining is the safe MVP for small instructions. |
| A5 | `pyyaml>=6,<7` is acceptable to add (CLAUDE.md pins "PyYAML 6.0.3"). | Standard Stack, Package Legitimacy | Near-zero — it is in CLAUDE.md's authoritative stack table. |
| A6 | Phase 3 stores `tools`/`permissions`/`quality_gate`/`retry`/`publishing` in the schema + snapshot but enforces **none** of them (deferred to Phases 5/6/9/10). | Phase Requirements (CFG-03), Pattern 1 | If the planner reads CFG-03 as requiring enforcement now, scope balloons into Phase 6 territory. The success criteria only test that the values are *read from config*, not acted on. |
| A7 | `.dark-factory/runs/` should be added to `.gitignore` this phase; `.dark-factory.yaml` + `.dark-factory/roles/` + `.dark-factory/instructions/` stay tracked. | `.dark-factory/` layout | Low. If the planner defers the `.gitignore` line to Phase 4, the artifact dir just isn't created yet — harmless. |

## Open Questions

1. **Role-name spelling in `.dark-factory.yaml` — status values (`ARCHITECTURE`) vs human names (`Architect`)?**
   - What we know: `transition()` does `RunStatus(role_name)` `[VERIFIED: lifecycle.py:87]`, so status values are the zero-change path.
   - What's unclear: whether the portfolio-quality bar wants friendlier names in the config file.
   - Recommendation: use status values in `workflow.roles` and the role YAML `name`; put a human label in the role YAML `description`. Confirm with the user during discuss/plan.

2. **`config_snapshot` column vs reuse `runs.workflow`.**
   - What we know: reuse needs no migration and the column already has the right lifecycle treatment.
   - What's unclear: whether the planner values the explicit separation enough to spend revision `0004`.
   - Recommendation: reuse; document the column's new dual role in `models.py` and `repositories.py` docstrings.

3. **Does Phase 3 delete `roles/registry.py::ba_role` / `DEFAULT_PIPELINE`, or keep them as fallbacks?**
   - Recommendation: delete both from the production path (keep a `DEFAULT_PIPELINE`-shaped fixture in `tests/` only). A live fallback is the Anti-Pattern in Pattern 8.

4. **Should `ensure_clean_worktree` do a real (cheap) check now, or be a pure no-op until Phase 5?**
   - Recommendation: pure no-op stub with a docstring naming Phase 5. A half-real check invites a false sense of coverage.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| PyYAML | config parsing | ✗ (not yet in `pyproject.toml`) | target 6.0.3 | none — must `uv add pyyaml` (Wave 0) |
| PostgreSQL 17 (test) | `db` / `integration` tiers | resolved by `tests/conftest.py` probe ladder (testcontainers → pytest-postgresql → `DARK_FACTORY_TEST_DATABASE_URL`) `[VERIFIED: tests/conftest.py:44-94]` | — | external throwaway PG 17 via env var (already the standing arrangement per STATE.md 01-09) |
| `uv` | dep resolution, lockfile, `uv run pytest` | ✓ (project standard) | — | — |
| Alembic | only if the `config_snapshot` column option is chosen | ✓ (pinned) | `>=1.19,<2` | reuse `runs.workflow` → no Alembic work |

**Missing dependencies with no fallback:** PyYAML — trivially resolved with `uv add pyyaml` in Wave 0.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (`unit` / `db` / `integration` / `contract` markers, registered in `pyproject.toml` `[VERIFIED: pyproject.toml:35-41]`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| Quick run command | `uv run pytest -m "unit or contract"` (~0.2 s, no DB) |
| Full suite command | `set -a; . ./.env; set +a && uv run pytest` (`db`/`integration` need a reachable PG 17) |
| Static gates | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict); `uv lock --check` |
| Schema | autouse `_schema_at_head` runs `alembic upgrade head` `[VERIFIED: tests/conftest.py:198-220]` — picks up revision `0004` automatically **iff** the planner chooses the new-column option; no change if `runs.workflow` is reused |

### Phase Requirements → Test Map
| Req / SC | Behaviour | Test type | Automated command | File exists? |
|----------|-----------|-----------|-------------------|-------------|
| SC1 / ORCH-02 / ORCH-03 | reorder `workflow.roles` `[BA,QA]`→`[QA,BA]` and shorten to `[BA]` changes the executed transition sequence; `git diff --stat` of `orchestrator/`+`workflows/` empty across runs | integration | `uv run pytest tests/integration/test_config_drives_pipeline.py -x` | ❌ Wave 0 |
| SC1 (guard) | no `RunStatus` role-name literal in `orchestrator/` or `workflows/pipeline.py` | unit | `uv run pytest tests/unit/test_no_role_name_literal.py -x` | ❌ Wave 0 |
| SC2 / CFG-02 / CFG-03 | editing `.dark-factory/roles/BA.yaml` (worker, before/after, instructions path) changes what executes; instruction text is inlined into the snapshot | integration + db | `uv run pytest tests/integration/test_role_yaml_drives_behaviour.py tests/db/test_snapshot_roundtrip.py -x` | ❌ Wave 0 |
| SC3 / CFG-05 | pause a run (FakeWorker `NEEDS_INPUT` script), rewrite `.dark-factory.yaml`, `resume --answer`, assert executed order == snapshot order, not the edited file | integration | `uv run pytest tests/integration/test_snapshot_survives_edit.py -x` | ❌ Wave 0 |
| SC3 (guard) | `dark_factory.orchestrator.*` transitive imports exclude `dark_factory.config.loader` | unit | `uv run pytest tests/unit/test_orchestrator_no_live_config_read.py -x` | ❌ Wave 0 |
| SC4 / CFG-01 | unknown role name / unknown worker / unknown action / missing instruction file → `start_run` raises `ConfigError`, **no `runs` row inserted** (count before == count after), CLI exits 2 with no run id on stdout | db + integration | `uv run pytest tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py -x` | ❌ Wave 0 |
| CFG-04 | `ActionRegistry` resolves a configured hook name to a callable; unknown name → `UnknownActionError`; a newly registered action is usable from config with no orchestrator change | unit | `uv run pytest tests/unit/test_action_registry.py -x` | ❌ Wave 0 |
| CFG-04 (guard) | no module under `src/dark_factory/actions/` constructs `RunEvent`/`RoleExecution`/`HumanInteraction` or assigns `.status` | unit | `uv run pytest tests/unit/test_single_mutation_path.py -x` (already `rglob`s all of `src/` `[VERIFIED: tests/unit/test_single_mutation_path.py:42-46]`) | ✅ existing (no change) |
| WORK-02 | `WorkerRegistry` contains `claude-code`/`copilot`/`hermes`; `name in registry` works without invoking; invoking a placeholder raises `NotImplementedError` naming the phase | unit | `uv run pytest tests/unit/test_worker_registry_names.py -x` | ❌ Wave 0 |
| config schema | `RepoConfig` / `RoleDefinition` reject unknown keys (`extra="forbid"`), empty file, non-mapping top level, `roles` entry not a `RunStatus` value; `yaml.safe_load` only | unit | `uv run pytest tests/unit/test_repo_config_schema.py -x` | ❌ Wave 0 |
| isolation | `config/repo_config.py` and `config/loader.py` import nothing from `config/settings.py` (and vice versa) | unit | `uv run pytest tests/unit/test_config_module_isolation.py -x` | ❌ Wave 0 |
| regression | `pipeline_from_snapshot` builds an N-node `Pipeline`; `transition()` walks it with no count assumption; legacy `{"roles":["BA"]}` snapshot still loads | unit | `uv run pytest tests/unit/test_pipeline_from_snapshot.py tests/unit/test_lifecycle.py -x` | ⚠️ extend `test_lifecycle.py` |
| acceptance gate | SC1-SC4 + the 8 requirement IDs each map to a named, non-empty proof file | integration | `uv run pytest tests/integration/test_phase3_acceptance.py -x` | ❌ Wave 0 (sibling of `test_phase_acceptance.py` / `test_phase2_acceptance.py` `[VERIFIED: tests/integration/test_phase_acceptance.py; tests/integration/test_phase2_acceptance.py]`) |

### Sampling Rate
- **Per task commit:** `uv run pytest -m "unit or contract"` (~0.2 s)
- **Per wave merge:** full `uv run pytest` (with `.env` sourced) + `ruff` + `mypy --strict`
- **Phase gate:** full suite green + `tests/integration/test_phase3_acceptance.py` green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `uv add "pyyaml>=6,<7"`; commit `uv.lock`
- [ ] `src/dark_factory/config/repo_config.py` + `config/loader.py` (`ConfigError`)
- [ ] `src/dark_factory/actions/` package (`registry.py` + `context.py` + `builtins.py` + `__init__.py`) with built-ins registered at import
- [ ] `WorkerRegistry.__contains__` + `claude-code`/`copilot`/`hermes` placeholder factories in `workers/registry.py`
- [ ] `workflows/pipeline.py::pipeline_from_snapshot`; remove `DEFAULT_PIPELINE` production default (keep a test fixture)
- [ ] `.dark-factory.yaml` + `.dark-factory/roles/{BA,QA}.yaml` + `.dark-factory/instructions/{ba,qa}.md` example set the project can actually run against
- [ ] `.gitignore` += `.dark-factory/runs/`
- [ ] `tests/conftest.py` fixture: a `tmp_path`-based `.dark-factory/` builder (write a `RepoConfig` + role YAMLs + instruction md into a temp dir, return the root) — mirrors the `fake_settings` builder pattern `[VERIFIED: tests/conftest.py:262-281]`
- [ ] extend `tests/unit/test_lifecycle.py` for `pipeline_from_snapshot` + N-node walks
- [ ] `tests/integration/test_phase3_acceptance.py` (sibling gate)
- [ ] if the `config_snapshot` column option is chosen: Alembic revision `0004` + `models.py` + `repositories.py` + `RunState` field + `_OWNED_TABLES` review

*(If no gaps found later: "None — existing test infrastructure covers all phase requirements" — but Phase 3 has real Wave 0 work above.)*

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1`.

### Applicable ASVS Categories

| ASVS category | Applies | Standard control |
|---------------|---------|------------------|
| V5 Input Validation | **yes** | `.dark-factory.yaml` and role YAML are repo-controlled input. `yaml.safe_load` only (never `yaml.load`); pydantic v2 `extra="forbid"` + typed fields + `field_validator`; instruction path is resolved and confirmed inside the repo root; instruction size capped. |
| V5.2 Sanitization / injection | **yes** | Action names and worker names from config are looked up in an **allowlist registry** (`name in registry`), never `getattr`/`importlib` on a config string — no arbitrary import/exec surface. `quality_gate.commands` are stored only, not executed this phase (Phase 9 must run them without `shell=True` per CLAUDE.md). |
| V6 Cryptography | no | No crypto in this phase. |
| V7 Error Handling & Logging | **yes** | `ConfigError` messages name the file + field but must not echo a secret; the snapshot is `redact()`-ed on write `[VERIFIED: mutations.py:174]`; structlog redaction processor already installed. |
| V8 Data Protection | **yes** | No credentials in `.dark-factory.yaml` (loader docstring + README); snapshot redaction is the backstop; `repo_config.py` isolated from the `Settings` secret map (Pitfall 6). |
| V2 Authn / V3 Session / V4 Access Control | no | No auth surface in this phase. |
| V1 Architecture | **yes** | New trust boundary: repo config → orchestrator. Mitigated by registry allowlists + `safe_load` + snapshot-not-live-read. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| `yaml.load` object injection from a crafted `.dark-factory.yaml` | Tampering / Elevation | `yaml.safe_load` exclusively; grep/AST guard over `config/` |
| Action/worker name in config used to import/exec arbitrary code (`getattr`, `importlib`) | Elevation | name→callable **allowlist** registry; `UnknownActionError`/`ConfigError` on miss |
| Path traversal via `instructions: ../../../../etc/passwd` | Information disclosure | resolve the path, assert it is under the repo root, assert `.is_file()`, cap size |
| Secret committed in `.dark-factory.yaml` then persisted in `runs.workflow` | Information disclosure | `create_run` `redact()`s the snapshot `[VERIFIED: mutations.py:174]`; docs forbid secrets in repo config; `repo_config.py` not reachable from `Settings` |
| Config re-read on resume yields a different pipeline than the run started with | Tampering (of run determinism) | snapshot in `runs.workflow`; import-graph guard keeps `orchestrator/` from importing the loader |
| `quality_gate.commands` executed with `shell=True` (future phase) | Elevation / command injection | out of scope here; flag for Phase 9 — `Popen([...])` arg list, never `shell=True` (CLAUDE.md) |

## Sources

### Primary (HIGH confidence — read this session)
- `src/dark_factory/workflows/pipeline.py`, `orchestrator/runner.py`, `orchestrator/lifecycle.py`, `orchestrator/answers.py`, `orchestrator/lease.py` — pipeline construction, the resume-first `advance`/`drive` loop, the `RunStatus(role_name)` coupling, the lease.
- `src/dark_factory/persistence/models.py`, `mutations.py`, `repositories.py`, `engine.py` — `runs.workflow` JSONB, `create_run(workflow=…)` redaction, `load_run_state` → `RunState.workflow`, the one mutation path + AST guard.
- `src/dark_factory/workers/registry.py`, `workers/base.py`, `workers/fake.py`, `roles/registry.py` — the name→factory registry pattern to clone, the `CodingWorker` contract, the single `ba_role`.
- `src/dark_factory/config/settings.py` — the infra-secret choke point that `repo_config.py` must stay isolated from.
- `src/dark_factory/cli.py`, `input/resolver.py`, `input/loaders.py` — the exit-2 contract and the `classify → load → create_run` run-creation path.
- `migrations/env.py`, `migrations/versions/0001_walking_skeleton.py`, `0003_pause_resume_lease.py` — `_OWNED_TABLES`, the model/migration byte-parity pattern, JSONB column DDL.
- `tests/conftest.py`, `tests/unit/test_single_mutation_path.py`, `test_no_worker_name_leak.py`, `test_status_import_graph.py`, `tests/integration/test_phase_acceptance.py`, `test_phase2_acceptance.py`, `tests/db/test_transition_atomic.py` — the guard-test and acceptance-gate idioms to mirror.
- `.planning/REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `PROJECT.md`, `pyproject.toml`, `.gitignore`.

### Secondary (MEDIUM confidence — web, cross-checked against CLAUDE.md)
- PyYAML current version 6.0.3 (published 2025-09-25), MIT, `github.com/yaml/pyyaml` — [pypi.org/project/PyYAML](https://pypi.org/project/PyYAML/), [github.com/yaml/pyyaml/releases](https://github.com/yaml/pyyaml/releases).
- pydantic v2 discriminated / tagged unions — `Annotated[Union[...], Field(discriminator='type')]`, `union_mode` — [docs.pydantic.dev unions](https://pydantic.dev/docs/validation/latest/concepts/unions/) (referenced only to *reject* for MVP).

### Tertiary (LOW confidence)
- None load-bearing. The snapshot-column choice and the exact YAML key names are recommendations (Assumptions A1-A7), not verified external facts.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — one new dependency (PyYAML), pinned by CLAUDE.md; everything else already in `pyproject.toml`.
- Architecture / seams: HIGH — every touched module (`pipeline.py`, `runner.py`, `lifecycle.py`, `mutations.py`, `repositories.py`, `workers/registry.py`, `cli.py`) read in full this session; the snapshot column and the registry pattern already exist end to end.
- Config schema shape: MEDIUM — the YAML key names and the `RoleDefinition` field set are a reasoned proposal from CFG-01/CFG-03 text, not a locked contract; expect refinement in discuss/plan.
- Snapshot persistence (reuse `runs.workflow` vs new column): MEDIUM — recommendation is reuse; both paths fully specified.
- Pitfalls: HIGH — each is grounded in a specific line of existing code.

**Research date:** 2026-09-10
**Valid until:** ~2026-10-10 (stable — no fast-moving dependency; PyYAML and the codebase seams are slow-changing).
