# Architecture Research

**Domain:** Durable, resumable multi-role agent-orchestration platform (Python + Neon PostgreSQL)
**Researched:** 2026-09-06
**Confidence:** MEDIUM-HIGH — durable-execution / Postgres-concurrency / idempotency / ports-and-adapters patterns are well-established and cross-checked (HIGH); the exact mapping onto Dark Factory's tables and the §72 module decomposition is reasoned synthesis (MEDIUM).

---

## Standard Architecture

### The core thesis, stated as an architecture rule

Dark Factory is a **checkpointing durable-execution system**, not a replay-based one. Two families exist in the wild:

| Family | How state is rebuilt | Examples | Fit for Dark Factory |
|--------|---------------------|----------|----------------------|
| **Replay / event-sourced** | Re-run the orchestrator function from the start, folding a complete event history; every non-deterministic call must be an "activity" whose recorded result is replayed | Temporal, Cadence | **No** — forces orchestrator code to be replay-deterministic forever; schema evolution across millions of events; overkill for a short, linear, human-speed pipeline |
| **Checkpoint / state-snapshot** | `SELECT` the current state row(s); resume from the last committed transition | DBOS Transact, LangGraph checkpointers, most job runners | **Yes** — the run's authoritative state is small and fits in `runs` + child tables; resume = read a row, not fold a log |

**Design rule:** the orchestrator's control flow is driven by **state columns** (`runs.status`, `runs.current_role`, latest `role_executions` row, open `human_interactions` rows). `run_events` is an **append-only audit/observability log**, rich enough to narrate the run for a human, but it is **not** the source of truth for "what happens next." Never reconstruct control state by replaying `run_events`.

**Corollary (the transactional-outbox insight, applied internally):** every state transition writes *both* the state-column update *and* its `run_events` row in **one database transaction**. There is never a moment where the state moved but the event is missing, or vice versa.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                            TRIGGERS (thin)                            │
│   ┌─────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐   │
│   │  CLI    │   │ GitHub webhook│  │ CI entrypoint │   │  IDE task │   │
│   └────┬────┘   └──────┬───────┘   └──────┬───────┘   └─────┬─────┘   │
│        └───────────────┴─── all call ─────┴─────────────────┘         │
│                     orchestrator.advance(run_id)                      │
├──────────────────────────────────────────────────────────────────────┤
│                        ORCHESTRATOR (platform-owned)                  │
│   ┌────────────────────┐   ┌──────────────────────────────────────┐   │
│   │ Runner / advance() │   │ LifecycleController (state machine)  │   │
│   │  - claim lease     │──▶│  (state, signal) -> (state, effects) │   │
│   │  - load RunState   │   │  PURE: no I/O, no LLM                │   │
│   │  - step one node   │   └──────────────────────────────────────┘   │
│   │  - commit + event  │        owns: Persistence, Quality Gate,      │
│   └─────────┬──────────┘        Repo lifecycle, Publishing            │
│             │                                                         │
│             ▼                                                         │
│   ┌────────────────────┐   Workflow = ordered role pipeline +         │
│   │ Workflow (pipeline)│   feedback edges + retry policy (config)     │
│   └─────────┬──────────┘                                              │
│             ▼                                                         │
│   ┌────────────────────────────────────────────────────────────┐     │
│   │ RoleExecutor (per role)                                     │     │
│   │  before-actions → ContextBuilder → Worker.execute/resume    │     │
│   │  → persist artifacts+result → after-actions                 │     │
│   └───┬───────────────┬───────────────┬───────────────┬─────────┘     │
│       ▼               ▼               ▼               ▼               │
│  ┌─────────┐   ┌────────────┐   ┌───────────┐   ┌───────────────┐     │
│  │ Context │   │ ToolRegistry│  │ Artifacts │   │ ActionRegistry│     │
│  │ Builder │   │ + perms     │  │ Store     │   │ (pre/post)    │     │
│  └─────────┘   └─────┬──────┘   └───────────┘   └───────────────┘     │
├─────────────────────┼────────────────────────────────────────────────┤
│                     ▼  PORTS (hexagonal boundary)                    │
│  CodingWorker  │ VersionControl │ Persistence repos │ Integration    │
│  (port)        │ (port)         │ (ports)           │ ports          │
│  ┌──────────┐  │  ┌──────────┐  │  ┌─────────────┐  │ ┌───────────┐  │
│  │ClaudeCode│  │  │ git CLI  │  │  │ SQLAlchemy  │  │ │ GitHub    │  │
│  │Copilot   │  │  │ adapter  │  │  │ + Alembic   │  │ │ (issue,   │  │
│  │Hermes    │  │  └──────────┘  │  │ (Neon)      │  │ │ PR, cmnt) │  │
│  │FakeWorker│  │                │  └─────────────┘  │ │ Jira/…    │  │
│  └──────────┘  │                │                   │ │ (later)   │  │
├────────────────┴────────────────┴───────────────────┴─┴───────────┴──┤
│  STATE: Neon PostgreSQL   │   ARTIFACT CONTENT: filesystem           │
│  runs, role_executions,   │   .dark-factory/runs/<run-id>/           │
│  human_interactions,      │     input/  artifacts/<role>/            │
│  artifacts (refs only),   │     verification/  logs/                 │
│  run_events               │                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility (owns) | Must NOT do |
|-----------|----------------------|-------------|
| **Triggers** (`cli/`, `webhooks/`, `ci/`) | Parse invocation, resolve `run_id`, call `orchestrator.advance()` / `orchestrator.create_run()` | Contain any lifecycle logic, transition decisions, or worker knowledge |
| **Runner** (`orchestrator/runner`) | The reconstruct-then-step loop; acquire/renew/release the run lease; open the transaction that commits a transition | Interpret engineering results (delegates to LifecycleController); hold a DB transaction open across a worker call |
| **LifecycleController** (`orchestrator/lifecycle`) | Pure transition function: `(persisted_state, typed_signal) -> (next_state, [side_effect_intent])`; retry-limit arithmetic | Any I/O, any LLM call, any direct DB write, any worker/git/github call |
| **Workflow** (`workflows/`) | Load the ordered `workflow.roles` pipeline + feedback edges + retry policy from resolved config; answer "given current role, what is the next node" | Be a generic DAG engine; execute anything |
| **RoleExecutor** (`roles/`) | Run one role: before-actions → build context → invoke worker → persist result+artifacts → after-actions; enforce role output contract | Decide run-level transitions; branch on worker type; talk to Neon directly (uses repos via orchestrator) |
| **ContextBuilder** (`context/`) | Assemble role-specific `RoleContext` from NormalizedTask + selected prior artifacts + repo doc references + human answers + granted capabilities | Walk / dump the source tree into prompts; read lifecycle state |
| **ToolRegistry + permission layer** (`tools/`) | Map capability name → Tool impl; produce a role-scoped `GrantedToolset`; enforce deny-by-default on every invocation | Trust the worker's self-reported permissions; expose infra credentials |
| **ActionRegistry** (`actions/`) | Deterministic Python pre/post hooks referenced by config (`prepare_role_context`, `ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, `collect_test_results`, …) | Contain non-determinism / LLM calls; mutate lifecycle state |
| **CodingWorker port + adapters** (`workers/`) | `execute()`, `resume()`, `capabilities()`; normalize everything into `WorkerResult`; **own the native-session-resume vs context-reconstruction branch** | Import `orchestrator/`, `workflows/`, `persistence/`; set run state |
| **WorkerRegistry** (`workers/`) | `name -> adapter factory` from config; includes `FakeWorker` | Let a worker-name `if` leak upward |
| **ArtifactStore** (`artifacts/`) | Write/read artifact files under `.dark-factory/runs/<id>/`; validate machine JSON against schema; create `ArtifactReference` rows | Put artifact *content* in Neon |
| **Persistence** (`persistence/`) | Repository **interfaces** (`RunRepository`, `EventLog`, `RoleExecutionRepository`, `HumanInteractionRepository`, `ArtifactRefStore`) + SQLAlchemy/Alembic **adapter**; unit-of-work/session | Leak SQLAlchemy or Neon specifics above the port; embed provider-specific SQL |
| **Quality Gate** (`quality/`) | Independently run configured `quality_gate.commands` in the repo env; write `verification/quality_gate.json`; return typed verdict | Accept the agent's own test run as truth |
| **Workspace / Repo lifecycle** (`workspace/`) | Clone/prepare working tree per run; one working branch from base; worktree isolation flag; git status/diff/commit/push behind a `VersionControl` port | Own commit/PR *policy* (that is the orchestrator's) |
| **Integrations** (`integrations/`) | Port definitions (`TaskSource`, `HumanChannel`, `PublishTarget`, service clients) + adapters; GitHub first | Be imported by core for anything other than the port interface |
| **Events** (`events/`) | Event type catalog; `EventLog` writer; **secret redaction / payload sanitization** | Be read back as control-flow truth |
| **Config** (`config/`) | Load + validate `.dark-factory.yaml` + role files; produce a **resolved-config snapshot** persisted with the run | Be re-read live during resume |
| **Observability read models** (`observability/`) | Aggregate `status`/`runs`/`events`/`artifacts` read queries for the CLI | Mutate anything |

---

## Recommended Project Structure

The spec's §72 layout is **validated with amendments**. Original folders kept; five modules added; two internal splits recommended.

```
dark_factory/
├── domain/              # ADDED. Cross-cutting value objects with no dependencies:
│                        #   NormalizedTask, RoleContext, WorkerResult, WorkerCapabilities,
│                        #   QAVerdict, QualityGateResult, ArtifactReference, RunState (read DTO),
│                        #   Signal / SideEffectIntent enums. Prevents import cycles.
├── config/              # ADDED. .dark-factory.yaml + role file loading & validation;
│                        #   ResolvedConfig snapshot model (persisted on the run).
├── orchestrator/
│   ├── runner.py        #   advance(run_id): claim lease → load → step → commit → release
│   ├── lifecycle.py     #   pure state machine: (state, signal) -> (state, effects)
│   └── effects.py       #   executes SideEffectIntent list via ports (persist, git, github…)
├── workflows/           # pipeline shape: ordered roles + feedback edges + retry policy
│                        #   (config-driven; NOT a generic engine)
├── roles/               # RoleExecutor, RoleDefinition model, role registry
├── workers/             # CodingWorker port, WorkerRegistry, WorkerCapabilities, WorkerResult,
│   ├── claude_code.py   #   adapters. Each adapter owns native-resume vs context-rebuild.
│   ├── copilot.py
│   ├── hermes.py
│   └── fake.py          #   FakeWorker — first-class deliverable, shipped in the package
├── tools/               # ToolRegistry, Tool port, built-in tools, role-permission model
│   └── transports/mcp/  #   MCP exposed as ONE optional transport adapter
├── actions/             # ActionRegistry, Action port, built-in deterministic hooks
├── input/               # source detection (text|spec|github), NormalizedTask assembly
│                        #   (delegates GitHub fetch to integrations/github)
├── context/             # ContextBuilder, RoleContext assembly
├── artifacts/           # ArtifactStore (fs read/write), JSON schema validation, ref creation
├── quality/             # QualityGate runner, verdict model
├── persistence/
│   ├── repositories.py  #   PORT interfaces the orchestrator imports
│   ├── sqlalchemy/      #   the only place SQLAlchemy/Neon specifics live
│   └── migrations/      #   Alembic
├── integrations/
│   ├── ports.py         #   TaskSource, HumanChannel, PublishTarget, …
│   └── github/          #   issue read, PR create, comment post/ingest
├── workspace/           # WorkspaceManager, VersionControl port + git adapter, worktrees
├── events/              # event catalog, EventLog writer, secret redaction
├── security/            # ADDED. EnvironmentBuilder (empty-dict-up), WorkerCredentialStore,
│                        #   redaction utils, permission-enforcement helpers
├── observability/       # ADDED. read-model aggregators for status/runs/events/artifacts
└── triggers/            # ADDED (or split cli/ + webhooks/ + ci/). Thin adapters only.
    ├── cli.py           #   run, resume, status, runs, artifacts, events
    ├── webhook.py       #   GitHub comment -> find run -> store answer -> advance()
    └── ci.py            #   same orchestrator, different entrypoint
```

### Structure Rationale

- **`domain/` added:** `WorkerResult`, `RoleContext`, `WorkerCapabilities`, verdicts, and the state-machine `Signal` enum are referenced by nearly every module. Without a dependency-free home they force cycles (e.g. `workers/` ↔ `roles/`). Keep it pure data + enums, no behavior.
- **`config/` added:** configuration spans workflow, roles, tools, actions, quality gate, retry, publishing. It is not a sub-concern of `workflows/`. Critically it produces the **`ResolvedConfig` snapshot** that is persisted on the run so a resume months later is deterministic even if `.dark-factory.yaml` changed.
- **`security/` added:** the "workers never see `DATABASE_URL`/`GITHUB_TOKEN`" rule is a *constraint*, and scattering it across `tools/` and `workers/` makes it un-auditable. One module owns env construction, credential scoping, and redaction so the boundary is reviewable in one place.
- **`observability/` added:** the `status` command needs a cross-table read aggregation (run + roles + attempts + artifacts + interactions + events). That is a read model, distinct from the write-side repositories.
- **`triggers/` added:** the spec says "environments are only triggers — no separate CI orchestrator." Making that literally true means a folder of thin adapters that all funnel into `orchestrator.advance()`.
- **`orchestrator/` split into `runner` / `lifecycle` / `effects`:** the single most important seam in the system. `lifecycle` is a **pure function** (trivially unit-testable, no mocks); `runner` does the I/O choreography and locking; `effects` translates intents into port calls. Keeping them in one file blurs the "deterministic core" boundary.
- **`workers/fake.py` in-package (not `tests/`):** it is a named deliverable used by orchestration tests *and* useful for demos/dry-runs. Ship it.
- **`tools/transports/mcp/`:** enforces "MCP is one optional transport, never an internal dependency" structurally — core `tools/` has no `import mcp`.
- **§72 folders all retained:** each maps cleanly to one entry in the guiding-principle table (§83). No original folder is redundant.

---

## Architectural Patterns

### Pattern 1: Resume-first — normal execution is a special case of resume

**What:** There is exactly one execution entry point, `advance(run_id)`, which (1) reconstructs the entire `RunState` from Neon with **zero in-memory carryover**, (2) determines the current node, (3) executes one step, (4) commits the transition. `create_run()` writes the `CREATED` row and then calls `advance()`. `resume(run_id, answer)` records the answer and then calls `advance()`. A crash mid-run is recovered by any process calling `advance()` again.

**When to use:** Always. Do not build a separate "happy path" runner that keeps objects in memory between roles — it will diverge from the resume path and the resume path will rot.

**Trade-offs:** Every step pays a full state reload from Postgres (cheap at human/agent timescales — steps take minutes). In exchange, cross-process and cross-machine resume are free and always exercised.

```python
def advance(run_id: str) -> None:
    if not lease.claim(run_id, owner=this_process):      # conditional UPDATE, see Pattern 3
        return                                            # another process owns it
    try:
        while True:
            state = RunState.load(run_id)                 # full reconstruct from Neon
            node = workflow.current_node(state)
            if node.is_terminal:
                return
            signal, outputs = execute_node(node, state)   # RoleExecutor / QualityGate / Publish
            next_state, effects = lifecycle.transition(state, signal)  # PURE
            with uow.transaction():                       # state col + event in ONE tx
                effects.apply(effects, run_id)
                repo.set_status(run_id, next_state, expected=state.status)  # guarded
                events.append(run_id, node, signal)
            if next_state in (WAITING_HUMAN, FAILED, COMPLETED):
                return
            lease.renew(run_id)
    finally:
        lease.release(run_id)
```

### Pattern 2: Deterministic control / free engineering — the platform owns the state machine

**What:** The `LifecycleController.transition()` function is the *only* code that changes `runs.status` / `runs.current_role`. It consumes **typed signals** derived from role outputs: `WorkerResult.status ∈ {COMPLETED, NEEDS_INPUT, FAILED}`, `QAVerdict ∈ {PASS, FAIL}`, `QualityGateResult ∈ {PASS, FAIL}`, `HumanAnswer`. A worker returning `NEEDS_INPUT` does **not** set `WAITING_HUMAN` — it returns a value; the controller decides. Inside `worker.execute()` the agent has full freedom (edit code, run shells, iterate) bounded only by its granted toolset.

**When to use:** Always. This is the project's founding constraint ("not one giant LLM loop").

**Trade-offs:** You must enumerate the state graph explicitly (states + feedback edges + retry counters). That is a feature: the graph is small, reviewable, and testable with `FakeWorker` and no LLM.

```
CREATED ─▶ BA ─▶ ARCHITECTURE ─▶ DEVELOPMENT ─▶ QA ─▶ VERIFYING ─▶ PUBLISHING ─▶ COMPLETED
                                    ▲            │        │
                                    │  QA FAIL   │        │ gate FAIL
                                    └────────────┘        │
                                    ▲                     │
                                    └─────────────────────┘   (retry counters gate both loops;
   any role ──▶ WAITING_HUMAN ──(answer)──▶ back to current_role     exhaustion ─▶ FAILED)
   any role ──▶ FAILED (terminal)
```
`current_role` is stored **separately** from `status` so `WAITING_HUMAN` knows where to return.

### Pattern 3: Postgres-only concurrency — lease claim + guarded transition, no held transaction

**What:** Two mechanisms, used for different durations:

1. **Run lease (long-lived, spans the worker call).** Columns on `runs`: `locked_by`, `locked_at`, `lock_expires_at`. Claim with a conditional update; success = `rowcount == 1`:
   ```sql
   UPDATE runs SET locked_by = :me, locked_at = now(), lock_expires_at = now() + interval '5 minutes'
   WHERE id = :id AND (locked_by IS NULL OR lock_expires_at < now());
   ```
   The process **heartbeats** `lock_expires_at` forward while the worker runs, and releases on pause/complete/fail. A dead process's lease simply expires — no distributed lock service, and no open transaction across a multi-minute agent call.
2. **Guarded transition (short-lived, the commit).** The status write always asserts the expected prior value:
   ```sql
   UPDATE runs SET status = :next WHERE id = :id AND status = :expected;
   ```
   `rowcount == 0` ⇒ someone else advanced the run ⇒ abort this step. This is the optimistic-concurrency backstop even if the lease logic has a bug.

**When to use:** Every `advance()` invocation. `SELECT … FOR UPDATE` / `pg_advisory_xact_lock(hashtext(run_id))` are fine for the *short* critical sections (claiming, the commit) but must never wrap the worker execution.

**Trade-offs:** Lease TTL tuning: too short ⇒ false steals during a slow agent step (mitigate with heartbeat); too long ⇒ slow recovery after a crash. A heartbeat every TTL/3 with TTL of a few minutes is a safe default. The webhook path must also take the lease before resuming, or enqueue if it cannot.

### Pattern 4: Worker as a hexagonal port; the resume branch lives inside the adapter

**What:** `CodingWorker` is a port with three methods. `WorkerCapabilities` is an explicit model (`native_resume`, `session_id`, `non_interactive`, `structured_output`, `mcp_tools`, `max_context_tokens`). The orchestrator/RoleExecutor reads capabilities only for **generic** decisions (parse structured output vs text; expect a session id or not). The **native-session-resume vs context-reconstruction** decision is made entirely inside `adapter.resume()` and is opaque to the orchestrator:

```python
class ClaudeCodeWorker(CodingWorker):
    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(native_resume=True, session_id=True, structured_output=True, ...)

    def resume(self, ctx: RoleContext, previous: WorkerResult, answer: HumanAnswer) -> WorkerResult:
        if self.capabilities().native_resume and previous.worker_session_id:
            return self._resume_session(previous.worker_session_id, answer)   # native
        return self._execute_fresh(self._rebuild_prompt(ctx, previous, answer))  # reconstruction
```

`WorkerResult` is the sole return channel: `status`, `summary`, `questions[]`, `artifacts[]`, `changed_files[]`, `worker_session_id`, `metadata`, `error`. No adapter imports `orchestrator/`, `workflows/`, or `persistence/` (enforced by import-linter).

**When to use:** Always. `FakeWorker` implements the same port with a scripted `WorkerResult` sequence, which is what makes lifecycle testing possible without AI calls.

**Trade-offs:** `WorkerCapabilities` must be honest and covered by each adapter's integration suite — the three runtimes genuinely differ, which is why the model exists rather than assuming uniformity.

### Pattern 5: Tool grants + filtered environment as a server-side security boundary

**What:** Role config declares `tools: [repo.read, repo.search, git.diff, …]`. `RoleExecutor` asks `ToolRegistry` for a `GrantedToolset` — the filtered subset. Tool calls from the worker are brokered (via in-process call, or via the MCP transport subprocess) and **permission-checked on every invocation, deny-by-default**, never trusted to the worker. Separately, `security/EnvironmentBuilder` constructs the worker subprocess environment starting from an **empty dict** (never `os.environ`), adding only: `PATH`/`HOME`/locale, the run's repo path, and the worker runtime's *own* credential pulled from `WorkerCredentialStore` (keyed by worker name, physically separate from infra secrets). `DATABASE_URL`, `GITHUB_TOKEN`, and Dark Factory's process env are never present.

```
role config ──▶ ToolRegistry.grant(role) ──▶ GrantedToolset ──┐
                                                              ├─▶ worker subprocess
security.EnvironmentBuilder.build(role) ──▶ WorkerEnvironment ─┘   (execve with scrubbed env)
        starts from {}, adds minimum, injects only worker's own key
```

**When to use:** Every worker invocation. QA's "tests only" restriction is enforced twice: by tool permissions (`repo.write_tests` not `repo.write`) *and* by a post-action diff check that fails the role if non-test files changed.

**Trade-offs:** Brokering tool calls (esp. over MCP) adds a moving part. Acceptable — it is the only place the permission model can actually be enforced. Workers that only shell out (e.g. Claude Code) may need a filesystem sandbox + allowlisted CLI instead of/alongside MCP.

### Pattern 6: Idempotent external side effects via persisted identifiers (mini-saga with a cursor)

**What:** Publishing is a sequence of individually-idempotent steps; each checks a persisted id before acting and records the id in its own committed transaction:

| Effect | Persisted id | Guard before acting |
|--------|-------------|---------------------|
| create working branch | `runs.working_branch` | branch ref already exists locally/remotely ⇒ skip |
| commit | `runs.commit_sha` | recompute diff; if head already at recorded SHA ⇒ skip |
| push | (branch ref) | push is ref-idempotent; still guard on `runs.pushed_at` |
| create PR | `runs.pr_number`, `runs.pr_url` | if set ⇒ skip; also query GitHub "PRs for head branch" as secondary guard |
| clarification comment | `human_interactions.channel_message_id` | if set ⇒ do not re-post |

A crash mid-publish resumes by re-entering the sequence; populated ids short-circuit completed steps (derive the cursor from which ids are set, or store `runs.publish_step`). The **GitHub webhook** path: incoming comment → find run by stored issue number / branch / PR + an **open** `human_interactions` row → dedupe on comment id (inbox pattern) → store answer, mark `ANSWERED` → `advance(run_id)`. **Never create a new run.**

**When to use:** Every effect that leaves a mark outside Dark Factory.

**Trade-offs:** More columns and more "check first" branches. This is the price of retry-safety and is non-negotiable given the durability thesis.

### Pattern 7: Context assembly by reference, not by repo dump

**What:** `ContextBuilder` produces `RoleContext` = { NormalizedTask, role instructions (from `instructions/*.md`), **selected** prior artifacts per role config (e.g. Developer gets `requirements.md`, `acceptance_criteria.json`, `design.md`, `constraints.json` — not the BA's raw transcript), repo doc **paths** (README, AGENTS.md, CLAUDE.md, architecture docs), human answers, constraints, granted-capability list, optional few-shot example refs }. The agent inspects the actual repository itself through tools. `ContextBuilder` reads from `artifacts/` + `persistence/` (human interactions) + `input/`; it does **not** walk the source tree.

**When to use:** Every role invocation.

**Trade-offs:** Requires disciplined per-role artifact selection in config. Benefit: prompt size stays bounded and stable regardless of repo size, and handoffs are explicit (JSON contract wins where orchestration depends on it).

---

## Data Flow

### A run, end to end

```
trigger: dark-factory run text:"..."  |  spec:./x.md  |  github:152
    │
    ▼
input/  detect source (deterministic, no LLM) ──▶ NormalizedTask
    │
    ▼
orchestrator.create_run():
    persist runs row (status=CREATED, current_role=null, resolved_config snapshot,
                      repository, base_branch, working_branch=null)
    event RUN_CREATED
    │
    ▼
orchestrator.advance(run_id)  ── claim lease ──▶ loop:
    │
    ├─ load RunState from Neon (runs + role_executions + artifacts refs + human_interactions)
    ├─ workflow.current_node(state)  →  BA
    ├─ RoleExecutor(BA):
    │     before-actions: prepare_role_context, ensure_clean_worktree
    │     ContextBuilder → RoleContext (task + BA instructions + repo doc paths)
    │     WorkerRegistry.get(role.worker) → adapter
    │     adapter.execute(ctx) → WorkerResult(status=COMPLETED, artifacts=[requirements.md, acceptance_criteria.json])
    │     after-actions: store_role_artifacts → ArtifactReference rows in Neon,
    │                    content on fs at .dark-factory/runs/<id>/artifacts/ba/
    │     persist role_executions row (attempt=1, worker, status, worker_session_id, result JSONB)
    │     events ROLE_STARTED, ARTIFACT_CREATED, ROLE_COMPLETED
    ├─ lifecycle.transition(state, signal=COMPLETED) → (ARCHITECTURE, [set current_role])
    ├─ commit (guarded status update + event) in one tx
    └─ loop → ARCHITECTURE → DEVELOPMENT → QA
                                              │
              ┌───────────────────────────────┴───────────────────────────────┐
              │ QA verdict.json = FAIL                                         │ = PASS
              ▼                                                               ▼
   lifecycle.transition(QA_FAIL):                                   status = VERIFYING
     write qa_issues artifact (severity, acceptance_criterion, …)            │
     if qa_dev_iterations < max:  status = DEVELOPMENT (loop)                ▼
     else: status = FAILED                                    quality/ run quality_gate.commands
                                                              in repo env → quality_gate.json
                                                                            │
                                                       ┌────────────────────┴───────────┐
                                                       │ FAIL                           │ PASS
                                                       ▼                                ▼
                                          feedback output → DEVELOPMENT      status = PUBLISHING
                                          (gate_iterations gate; else FAILED)          │
                                                                                       ▼
                                              workspace/ + integrations/github:
                                              [branch]→[commit]→[push]→[create PR]  each idempotent,
                                              each id persisted in its own tx
                                                                                       │
                                                                                       ▼
                                                              persist pr_number/pr_url
                                                              event PR_CREATED, RUN_COMPLETED
                                                              status = COMPLETED  (release lease)
```

### Pause / resume

```
worker returns WorkerResult(status=NEEDS_INPUT, questions=[...], worker_session_id=abc)
    │
lifecycle.transition(NEEDS_INPUT):
    persist role_executions result (incl. worker_session_id)
    INSERT human_interactions (question, status=WAITING)
    optional: integrations/github post comment → store channel_message_id (idempotent)
    status = WAITING_HUMAN   (current_role unchanged)
    event QUESTION_CREATED, RUN_PAUSED
    release lease
    ── process may now terminate safely ──

... hours later, different machine ...

dark-factory resume <run-id> --answer "..."     OR    GitHub webhook (issue comment)
    │
    find run + open human_interactions row  (webhook: dedupe on comment id)
    UPDATE human_interactions SET answer=..., status=ANSWERED
    event HUMAN_ANSWER_RECEIVED
    │
    ▼
orchestrator.advance(run_id)  ── claim lease ──▶ load RunState (fresh, zero carryover)
    workflow.current_node: status=WAITING_HUMAN + answered interaction → return to current_role
    RoleExecutor: adapter.resume(ctx, previous_result, answer)
        └─ adapter internally: native session resume (worker_session_id present + supported)
                               OR context reconstruction (rebuild prompt from ctx + artifacts + answer)
    event RUN_RESUMED → continue loop
```

### Artifact handoff between roles

1. Role's worker writes files to `.dark-factory/runs/<run-id>/artifacts/<role>/`.
2. `store_role_artifacts` after-action validates machine JSON against schema, writes `ArtifactReference` rows to Neon (`id, run_id, role_execution_id, type, path, metadata, created_at`).
3. Next role's `ContextBuilder` queries artifact refs by `run_id` + `type` filtered by that role's config, reads content from the filesystem, and places **decided facts (JSON)** into `RoleContext`. Human-readable Markdown is passed by path.
4. Neon never holds the content — only the reference. (**Gap flagged below** for cross-machine resume.)

### The `status` read path

`observability/` joins `runs` + `role_executions` (per-role attempts, worker, session id) + `artifacts` + `human_interactions` + `run_events` (transition history) into one view DTO. Read-only; never touches the write model.

---

## Build Order

Dependency-ordered. Each stage is independently testable before the next begins.

| # | Stage | Delivers / unblocks | Depends on |
|---|-------|--------------------|-----------|
| 1 | **Persistence + config foundation** | SQLAlchemy models + Alembic migrations for `runs`, `role_executions`, `human_interactions`, `artifacts`, `run_events`; repository **interfaces** + adapter; `EventLog` with **secret redaction from day one**; `.dark-factory.yaml` + role-file loader; `ResolvedConfig` snapshot | Neon URL only |
| 2 | **Domain value objects** | `NormalizedTask`, `RoleContext`, `WorkerResult`, `WorkerCapabilities`, `QAVerdict`, `QualityGateResult`, `Signal`, `SideEffectIntent` | none |
| 3 | **Lifecycle state machine + runner** | pure `transition()` with the full state graph + feedback loops + retry arithmetic; `advance()` reconstruct-then-step loop; **lease claim/renew/release + guarded status update**; import-linter dependency contracts in CI | 1, 2 |
| 4 | **FakeWorker + WorkerRegistry + CodingWorker port** | orchestration is now end-to-end testable with **no AI calls**: role transitions, artifact handoffs, pause/resume, QA FAIL loop, Developer retries, gate retries, failure limits | 2, 3 |
| 5 | **RoleExecutor + RoleDefinition + ActionRegistry + built-in actions + ContextBuilder + ArtifactStore** | the real role pipeline wired with `FakeWorker`; artifact refs in Neon, content on fs; JSON schema validation | 1, 4 |
| 6 | **Workspace / Git lifecycle** | `VersionControl` port + git adapter: per-run working tree, branch from base, worktree isolation flag, status/diff/commit; `ensure_clean_worktree`, `collect_diff` actions | 5 |
| 7 | **ToolRegistry + permission model + `security/`** | capability tools, role-scoped `GrantedToolset`, deny-by-default broker; `EnvironmentBuilder` (empty-dict-up), `WorkerCredentialStore`; optional MCP transport adapter | 5, 6 |
| 8 | **Real worker adapters** | `ClaudeCodeWorker` first (native resume + session id + structured output), then `CopilotWorker`, `HermesWorker`; per-adapter integration suites; the native-resume vs reconstruction branch inside each | 7 + real CLIs |
| 9 | **Quality Gate runner** | independent execution of `quality_gate.commands` in repo env → `verification/quality_gate.json` + typed verdict; wired into VERIFYING state | 6 |
| 10 | **GitHub integration** | `TaskSource` (issue ingest → NormalizedTask), `PublishTarget` (idempotent branch/commit/push/PR with persisted ids), `HumanChannel` (comment post + webhook ingest → `advance()`); idempotency guards | 3, 6, 8 |
| 11 | **Triggers** | `cli.py` (`run`, `resume`, `status`, `runs`, `artifacts`, `events`), then `webhook.py`, then `ci.py` — all thin, all funnel to `orchestrator.advance()` | 10 |
| 12 | **Observability read models** | cross-table aggregation for `status`; harden event redaction; run-narrative reconstruction check | 1, 11 |

**Cross-cutting from stage 1, not deferred:** import-linter dependency contracts; secret redaction in event payloads; the resume-first single-entry-point discipline.

**Critical early unblock:** stage 4 (`FakeWorker`) is what lets stages 5–6 and the entire lifecycle be verified without touching Claude Code / Copilot / Hermes. Do not let real adapters (stage 8) become a prerequisite for testing orchestration.

---

## Anti-Patterns

### Anti-Pattern 1: Reconstructing control state by replaying the event log

**What people do:** Treat `run_events` as an event-sourced aggregate and fold it to compute "where is the run."
**Why it's wrong:** Forces every event to be perfectly typed and versioned forever; projection rebuilds; couples control flow to audit-schema evolution. Temporal-style replay determinism is a heavy tax for a short human-speed pipeline.
**Do this instead:** Authoritative state in `runs` columns + child rows. `run_events` is append-only audit/observability. Both written in the same transaction as the state change.

### Anti-Pattern 2: Worker-type branching in the orchestrator

**What people do:** `if worker == "claude": ...` sprinkled through `RoleExecutor` / lifecycle.
**Why it's wrong:** Breaks "any role assignable to any worker with zero workflow-code change"; every new runtime edits core.
**Do this instead:** `CodingWorker` port + `WorkerRegistry`; runtime differences expressed only through `WorkerCapabilities`; runtime-specific logic (incl. native-resume decision) sealed inside the adapter. Enforce with import-linter.

### Anti-Pattern 3: Holding a database transaction open across the worker call

**What people do:** `SELECT … FOR UPDATE` on the run, then `await worker.execute()` (minutes to hours), then commit.
**Why it's wrong:** Long-held locks, idle-in-transaction bloat on Neon, connection exhaustion, no crash recovery until the transaction dies.
**Do this instead:** A lease column claimed by conditional `UPDATE`, heartbeated during the call, expiring on process death. Short transactions only for the claim and the guarded transition commit.

### Anti-Pattern 4: Passing `os.environ` (or the full process env) to the worker subprocess

**What people do:** `subprocess.run(..., env=os.environ | {"EXTRA": x})`.
**Why it's wrong:** Leaks `DATABASE_URL`, `GITHUB_TOKEN`, cloud creds into the agent's reach, its prompts, its logs, and any file it writes.
**Do this instead:** `security/EnvironmentBuilder` builds from `{}` and adds only the role's minimum plus the worker's *own* credential from a separate store.

### Anti-Pattern 5: Letting a worker's return value drive the transition directly

**What people do:** `if result.status == "NEEDS_INPUT": run.status = "WAITING_HUMAN"` inside the role code.
**Why it's wrong:** The engineering layer is now steering the lifecycle; the "deterministic outer loop" thesis is broken.
**Do this instead:** Role code returns a typed `Signal`; only `LifecycleController.transition()` maps signal → next state.

### Anti-Pattern 6: Re-reading `.dark-factory.yaml` live on resume

**What people do:** Load config fresh every `advance()`.
**Why it's wrong:** A pipeline edited while a run is paused resumes with a different role order / tool grants / retry limits — non-deterministic, unauditable.
**Do this instead:** Persist a `ResolvedConfig` snapshot on the `runs` row at creation; resume reads the snapshot.

### Anti-Pattern 7: Storing artifact content in Neon (or dumping the repo into prompts)

**What people do:** Put `design.md` / big JSON blobs in a `content` column; or inline file trees into the context.
**Why it's wrong:** Turns Neon into a document store (explicitly out of scope); bloats prompts unboundedly with repo size.
**Do this instead:** Content on the filesystem under `.dark-factory/runs/<id>/`; Neon holds `ArtifactReference` rows. Context passes *paths* and *decided facts*; the agent reads the repo via tools.

### Anti-Pattern 8: Creating a new run when a GitHub comment arrives

**What people do:** Webhook handler starts a fresh run per reply.
**Why it's wrong:** Loses the pending `RoleExecution`, the worker session, and the pipeline position.
**Do this instead:** Find the run by stored issue/branch/PR + open `human_interactions` row, dedupe on comment id, store the answer, call `advance()`.

### Anti-Pattern 9: Trusting the agent's own test/lint run as final truth

**What people do:** Publish when the Developer says "tests pass."
**Why it's wrong:** No independent verification; the agent both implements and grades.
**Do this instead:** Preserve agent self-validation, but gate publishing on QA PASS **and** a separate Quality Gate that re-runs `quality_gate.commands` in the repo environment.

### Anti-Pattern 10: Reaching for a distributed lock service

**What people do:** Add Redis/ZooKeeper for run mutual exclusion.
**Why it's wrong:** Another dependency for something Postgres already does correctly; explicitly out of scope.
**Do this instead:** Conditional `UPDATE` lease + guarded status transition + (optionally) `pg_advisory_xact_lock` for short critical sections.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes / gotchas |
|---------|--------------------|-----------------|
| **Neon PostgreSQL** | `DATABASE_URL` only, via SQLAlchemy + Alembic behind repository ports; treat as plain Postgres | No Neon-specific SQL above the adapter. Watch idle-in-transaction (see Anti-Pattern 3); pooled connection ("-pooler") for many short txns, direct for migrations. Lease pattern tolerates connection drops. |
| **GitHub** | `integrations/github` implements `TaskSource` (issue read), `PublishTarget` (branch/PR), `HumanChannel` (comment post + webhook ingest) | Idempotency via persisted ids + secondary "list PRs for head branch" check. Webhook must map comment → run without creating a run. Token lives in infra secret store, never in worker env. |
| **Agent runtimes** (Claude Code, Copilot, Hermes) | `CodingWorker` adapters spawned as subprocesses with scrubbed env + granted toolset; MCP optional transport | Capabilities genuinely differ (native resume, session id, structured output) — hence `WorkerCapabilities` + per-adapter integration suites. Each runtime's own API key from `WorkerCredentialStore`. |
| **CI system** | Just another trigger (`triggers/ci.py`) calling the same `orchestrator.advance()` | Run continues across local→CI via Neon. No separate CI orchestrator. CI needs `DATABASE_URL` + repo checkout; the run's working branch is re-materialized from git. |
| **Confluence / Jira / TestRail / Slack / etc.** | Not in Milestone 1. Added later purely as new `integrations/` adapters implementing existing ports (`TaskSource`, `HumanChannel`, `PublishTarget`, or new narrow ports) | Core must not gain an `import` of any of these. Registry + config wire them in. This is the payoff of the hexagonal boundary at `integrations/ports.py`. |

### Internal Boundaries

| Boundary | Communication | Rule |
|----------|---------------|------|
| Triggers → Orchestrator | direct function call (`create_run`, `advance`) | Triggers carry **no** lifecycle logic |
| Runner → LifecycleController | pure function call, in-memory values only | Controller does **zero** I/O; fully unit-testable without mocks |
| Runner/Effects → Persistence | via repository **port** interfaces | SQLAlchemy/Neon specifics never leak above `persistence/sqlalchemy/` |
| Orchestrator → RoleExecutor | call with `RunState` + `RoleDefinition` | RoleExecutor never decides run-level transitions |
| RoleExecutor → Worker | via `WorkerRegistry` → `CodingWorker` port | RoleExecutor never branches on worker name |
| Worker adapters → core | **forbidden**: no import of `orchestrator/`, `workflows/`, `persistence/`, `roles/` | Enforced by import-linter contract in CI |
| Roles → Workers | **forbidden** direct import; instance injected by orchestrator | Keeps dependency direction `roles → {context, tools, artifacts} → worker` |
| ContextBuilder → source tree | **forbidden** to walk/read repo source | Reads artifacts + interactions + config only; agent reads the repo |
| tools/ core → MCP | **forbidden** (`import mcp` only under `tools/transports/mcp/`) | MCP is one optional transport |
| events/ → secrets | **required**: redaction pass on every payload | `DATABASE_URL`/tokens/worker creds never in an event row |
| Actions → lifecycle state | **forbidden** to mutate `runs.status` | Actions touch workspace + artifacts; failures surface as a role failure the controller interprets |

### Dependency direction (spec §73) — validated

```
triggers ─▶ Orchestrator ─▶ Workflow ─▶ RoleExecutor ─▶ { Context, Tools, Artifacts } ─▶ Worker
                 │
                 ├─▶ Persistence (via ports)      ◀── AMENDMENT: repositories are ports;
                 ├─▶ Quality Gate                      SQLAlchemy is an adapter, so the
                 ├─▶ Repo lifecycle (VersionControl)   orchestrator depends on interfaces,
                 └─▶ Publishing (Integration ports)    matching "no provider-specific logic".

Workers depend on: domain/ value objects, tools/ port interfaces, context/ models.
Workers never depend on: orchestrator/, workflows/, persistence/, roles/.
```

The §73 direction holds as written. The only amendment: make **Persistence a port set** (not a concrete dependency) so the "Neon is just Postgres, no provider logic in orchestration" constraint is structurally enforced, not just intended.

---

## Open Gaps / Risks for the Roadmap

1. **Artifact content is not reconstructable from Neon (cross-machine resume).** The spec puts artifact *content* on the local filesystem under `.dark-factory/runs/<run-id>/` and only *references* in Neon. A resume on a different machine (local→CI, webhook worker) will not have those files. Options, in rough order of preference: **(a)** commit artifacts to a `.dark-factory/` path on the run's working branch so they travel with the git clone (simple, versioned, no new infra); **(b)** a content-addressed blob store / bucket keyed by run id; **(c)** relax the rule and store small critical machine-JSON artifacts inline in Neon (contradicts "not a document store"). This decision blocks true cross-machine resume and should be made in the Persistence/Artifacts phase.
2. **Lease TTL vs agent step duration.** Agent steps can run long and unpredictably. Heartbeat interval, TTL, and the false-steal window need a concrete policy and a test that simulates a slow step + a competing process. Belongs in the state-machine/concurrency phase.
3. **MCP tool brokering vs filesystem-sandbox** for shell-only runtimes (Claude Code). The permission model needs a real enforcement mechanism per runtime, not just a config list. Prototype in the tools/security phase before committing all three adapters.
4. **QA "tests-only" enforcement.** Tool-permission scoping plus a post-action diff assertion is the plan; confirm the git adapter can cheaply classify "test vs non-test" paths from config globs.
5. **Retry-counter placement.** Whether `qa_developer_iterations` / `quality_gate_iterations` live as columns on `runs` or are derived by counting `role_executions` / `run_events`. Columns are simpler for the guarded-update pattern; derivation is more audit-pure. Decide with the schema.

---

## Sources

- [Postgres-backed Durable Workflow Execution — DBOS](https://www.dbos.dev/blog/postgres-is-all-you-need-for-durable-execution) — checkpoint-in-Postgres model; state in the same transactional boundary as business data. Confidence: MEDIUM (vendor, but widely corroborated).
- [dbos-transact-py — Database-Backed Durable Python Workflows](https://github.com/dbos-inc/dbos-transact-py) — library-embedded durable execution in Python; annotate workflows/steps, checkpoint + recover.
- [DBOS vs Temporal: Choosing Durable Execution in 2026](https://tiarebalbi.com/en/blog/dbos-vs-temporal-postgres-durable-execution) — contrasts checkpoint vs service-boundary state models.
- [Temporal Workflow Definition — determinism & replay](https://docs.temporal.io/workflow-definition) and [Temporal Workflows](https://docs.temporal.io/workflows) — the replay/event-history model Dark Factory deliberately does **not** adopt; non-determinism constraints.
- [Understanding Non-Determinism in Temporal.io](https://medium.com/@sanhdoan/understanding-non-determinism-in-temporal-io-why-it-matters-how-to-avoid-it-3d397d8a5793) — why replay forces activities for all side effects.
- [LangGraph Persistence — checkpointers, threads, durability modes](https://docs.langchain.com/oss/python/langgraph/persistence) — thread-scoped state snapshots; pause-for-human and crash-recovery share one persistence layer (mirrors Dark Factory's resume-first).
- [Checkpoints Are Not Durable Execution — Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) — limits of naive checkpointing for agent workflows; informs the "explicit transition + guarded update" hardening.
- [Using FOR UPDATE SKIP LOCKED for Queue Workflows — Netdata](https://www.netdata.cloud/academy/update-skip-locked/) and [Build a Postgres Job Queue with SKIP LOCKED — Prisma](https://www.prisma.io/blog/you-dont-need-a-job-queue-postgres-already-has-skip-locked) — transaction-scoped locks auto-release on crash; no Redis needed.
- [Why FOR UPDATE SKIP LOCKED Isn't Enough: pg_advisory_xact_lock — Terris Linenbach](https://terrislinenbach.medium.com/why-for-update-skip-locked-isnt-enough-using-pg-advisory-xact-lock-to-build-a-correct-postgresql-d3eb9db46473) — when to add advisory locks for global constraints.
- [Locks in PostgreSQL: SELECT FOR UPDATE, SKIP LOCKED, advisory locks](https://vikulin-va.ru/en/postgres/locks/) — reference for the short-critical-section locking used at claim/commit.
- [Transactional Outbox Pattern — microservices.io](https://microservices.io/patterns/data/transactional-outbox.html) and [AWS Prescriptive Guidance — Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) — state change + its event committed in one local transaction (applied internally to state col + `run_events`).
- [Outbox, Inbox patterns and delivery guarantees — Event-Driven.io](https://event-driven.io/en/outbox_inbox_patterns_and_delivery_guarantees_explained/) — consumer-side inbox / `processed_events` dedupe keyed by id (applied to GitHub comment ingestion).
- [Is the audit log a proper architecture driver for Event Sourcing? — Event-Driven.io](https://event-driven.io/en/audit_log_event_sourcing/) — you can have a complete audit log without full event sourcing (basis for state-column + append-only log).
- [Event Sourcing, Audit Logs, and Event Logs — Arnaud Lemaire](https://medium.com/sundaytech/event-sourcing-audit-logs-and-event-logs-deb8f3c54663) — event sourcing records state changes, not everything attempted; complexity not justified for most systems.
- [Azure Architecture Center — Event Sourcing pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/event-sourcing) — canonical tradeoffs (projection rebuilds, schema evolution, eventual consistency).
- [Hexagonal architecture (software) — Wikipedia](https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)) and [Ports and Adapters — practical guide](https://medium.com/@tejasrawat_82721/hexagonal-architecture-ports-and-adapters-explained-a-practical-guide-from-concept-to-code-7903053f38f4) — core/ports/adapters; DI at runtime; core knows only interfaces (basis for Worker/VCS/Persistence/Integration ports + layered core).
- [Hexagonal Architecture implemented in Python — Workflows.guru](https://www.workflows.guru/blogs/hexagonal-architecture-implemented-in-python) — Python-specific port/adapter + registry wiring.

---
*Architecture research for: durable resumable multi-role agent-orchestration platform*
*Researched: 2026-09-06*
