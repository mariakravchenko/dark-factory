# Requirements: Dark Factory

**Defined:** 2026-09-06
**Core Value:** A delivery run is durable — its complete lifecycle state lives in Neon, so any process on any machine can resume exactly where a previous one stopped and still produce a correct, independently verified GitHub PR.

## v1 Requirements

Milestone 1 is the entire technical specification. Every requirement below is committed scope and maps to a roadmap phase.

### Task Intake

- [ ] **INTAKE-01**: Operator can start a run from plain text — `dark-factory run text:"..."`
- [ ] **INTAKE-02**: Operator can start a run from a spec file — `dark-factory run spec:./path.md`
- [ ] **INTAKE-03**: Operator can start a run from a GitHub issue — `dark-factory run github:152` — pulling issue title, body, comments, labels, and repository metadata
- [ ] **INTAKE-04**: The input resolver classifies the task source deterministically (text vs path vs GitHub reference) with no LLM call, and does not inspect the repo, call GitHub, or create a run
- [ ] **INTAKE-05**: Every source is loaded through a source-specific loader and normalized to one internal `NormalizedTask` model, after which the orchestrator is agnostic to origin

### Orchestration

- [ ] **ORCH-01**: A deterministic orchestrator drives the run lifecycle; the outer delivery flow is never a single LLM loop
- [ ] **ORCH-02**: The orchestrator executes a configured ordered sequence of roles, not hardcoded role calls
- [ ] **ORCH-03**: The role pipeline is defined in configuration (`workflow.roles`) and can be shortened or reordered without changing orchestrator code
- [ ] **ORCH-04**: Roles communicate through durable artifacts, not one shared agent conversation
- [ ] **ORCH-05**: Only the orchestrator changes lifecycle state; a worker result never directly drives a transition
- [ ] **ORCH-06**: Every lifecycle mutation (store result, transition state, create interaction, emit event) is written in a single database transaction through one mutation path

### Engineering Roles

- [ ] **ROLE-01**: The Business Analyst role makes the request implementation-ready and emits `requirements.md` and `acceptance_criteria.json`; it is read-only with respect to repository source code
- [ ] **ROLE-02**: The Architect role consumes the task, BA output, and repository and emits `design.md` and `constraints.json`; it is read-only with respect to repository source code
- [ ] **ROLE-03**: The Developer role implements the change, adds/updates tests, runs tests/lint/build, iterates on failures, and emits `implementation_summary.json`; it may modify production code and tests
- [ ] **ROLE-04**: The QA role independently verifies each acceptance criterion and emits `test_report.json` and a machine-readable `verdict.json`; it may modify only tests, fixtures, and test utilities
- [ ] **ROLE-05**: A role's permitted file-write scope is enforced after execution (e.g. QA's diff must not touch production code) using path rules from configuration
- [ ] **ROLE-06**: The QA verdict (pass/fail per criterion, issues with severity) is the machine input to the orchestrator's next decision; free-form prose alone never drives a transition

### Worker Abstraction

- [ ] **WORK-01**: All agent runtimes implement one `CodingWorker` contract — `execute()`, `resume()`, `capabilities()`
- [ ] **WORK-02**: A `WorkerRegistry` maps `claude-code` / `copilot` / `hermes` to adapters; worker creation is centralized
- [ ] **WORK-03**: No worker-specific branching (`if worker == "claude-code"`) appears in the orchestrator or workflow code
- [ ] **WORK-04**: `ClaudeCodeWorker` is a functional adapter that runs a role non-interactively and returns a normalized result
- [ ] **WORK-05**: `CopilotWorker` is a functional adapter that runs a role non-interactively and returns a normalized result
- [ ] **WORK-06**: `HermesWorker` is a functional adapter that runs a role non-interactively and returns a normalized result
- [ ] **WORK-07**: `WorkerCapabilities` represents runtime differences explicitly (native resume, session id, non-interactive, structured output)
- [ ] **WORK-08**: Every adapter normalizes its output to one `WorkerResult` (status COMPLETED | NEEDS_INPUT | FAILED, summary, questions, artifacts, changed_files, worker_session_id, metadata)
- [ ] **WORK-09**: Any role can be assigned to any supported worker via configuration with no change to workflow code
- [ ] **WORK-10**: A `FakeWorker` returns a scripted sequence of `WorkerResult`s for orchestration tests with no external AI call

### Tools & Permissions

- [ ] **TOOL-01**: A `ToolRegistry` provides the capability layer (`repo.read/search/write/write_tests`, `shell.execute`, `git.status/diff/history`, `github.issue.read`, `github.comments.read`, `artifacts.read/write`)
- [ ] **TOOL-02**: New tools can be added to the registry without modifying every role executor
- [ ] **TOOL-03**: Each role receives only its explicitly configured tools; grants are deny-by-default (BA/Architect read-only on code; Developer write + shell; QA write_tests + shell, no publish)
- [ ] **TOOL-04**: A worker's subprocess environment is built from an explicit allowlist; infrastructure credentials (`DATABASE_URL`, `GITHUB_TOKEN`, worker credentials) are never passed to a worker
- [ ] **TOOL-05**: MCP is supported as one optional transport adapter for exposing tools to compatible workers; the orchestrator has no internal dependency on MCP

### Context Preparation

- [ ] **CTX-01**: A `ContextBuilder` produces role-specific `RoleContext` (task, role instructions, relevant prior artifacts, README/AGENTS.md/CLAUDE.md, architecture docs, human answers, constraints, permitted capabilities)
- [ ] **CTX-02**: Context preparation does not copy the whole repository into the prompt; the agent inspects the repository itself
- [ ] **CTX-03**: Optional few-shot examples referenced from role configuration are included as context only, never as application logic
- [ ] **CTX-04**: On a retry, the rebuilt context does not leak stale artifacts from a superseded attempt

### Artifacts

- [ ] **ART-01**: Run artifacts are stored on the filesystem under `.dark-factory/runs/<run-id>/` (`input/`, `artifacts/<role>/`, `verification/`, `logs/`)
- [ ] **ART-02**: Machine-consumed decisions are emitted as structured JSON; human documentation may be Markdown; where orchestration depends on a result, the JSON contract is authoritative
- [ ] **ART-03**: Each artifact is recorded in Neon as an `ArtifactReference` (id, run_id, role_execution_id, type, path, metadata, created_at); Neon stores references, the filesystem stores content
- [ ] **ART-04**: Artifact content is available to a resuming process on a different machine (durability strategy for cross-machine resume)

### Durable State

- [ ] **STATE-01**: The persistence stack is SQLAlchemy + Alembic + PostgreSQL (Neon); the application uses only `DATABASE_URL` and contains no provider-specific database logic
- [ ] **STATE-02**: A `runs` table persists run identity, source, workflow, status, current role, current step, repository, base/working branch, PR number/URL, and timestamps
- [ ] **STATE-03**: A `role_executions` table persists one row per attempt (role, worker, status, attempt number, worker_session_id, result/error JSONB, timestamps)
- [ ] **STATE-04**: A `human_interactions` table persists questions, answers, and status (WAITING | ANSWERED | CANCELLED)
- [ ] **STATE-05**: An `artifacts` table persists artifact metadata
- [ ] **STATE-06**: A `run_events` append-only audit trail persists every important lifecycle event; the run's current position is read from state columns and is never recomputed by folding the event log
- [ ] **STATE-07**: Run status is one of CREATED, BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING, COMPLETED, WAITING_HUMAN, FAILED; the active role is stored separately
- [ ] **STATE-08**: The complete execution of a run is reconstructable from persisted data alone

### Human-in-the-Loop, Pause & Resume

- [ ] **HITL-01**: Any role can ask the human for clarification through one identical mechanism
- [ ] **HITL-02**: On a worker `NEEDS_INPUT` result the orchestrator stores the result and worker session, creates a human interaction, persists `WAITING_HUMAN`, and releases the execution so the process can terminate safely
- [ ] **HITL-03**: Operator can resume a paused run locally — `dark-factory resume <run-id> --answer "..."` — from a brand-new process with no in-memory state from the original run
- [ ] **HITL-04**: When a worker adapter supports native sessions, resume uses the opaque `worker_session_id`; the orchestrator does not interpret it
- [ ] **HITL-05**: When native resume is unavailable, the adapter resumes by reconstructing context; the orchestrator sees the same `worker.resume(...)` call either way
- [ ] **HITL-06**: A run can be resumed on a different machine or process than the one that started it (local → CI, webhook, delayed human answer)
- [ ] **HITL-07**: Two processes cannot execute the same run simultaneously; single-owner execution is enforced with PostgreSQL transactions / row locking / conditional updates and no separate distributed-lock service
- [ ] **HITL-08**: A database transaction is never held open across a worker subprocess call; ownership is held by a lease with database-clock expiry

### Feedback Loops & Retry

- [ ] **LOOP-01**: A QA FAIL returns a structured issues artifact (severity, acceptance_criterion, description) to the Developer for the next attempt
- [ ] **LOOP-02**: A quality-gate failure returns the actual failure output to the Developer, after which QA re-evaluates and the gate re-runs
- [ ] **LOOP-03**: Feedback iterations are bounded by repository configuration (`retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations`), checked before dispatch
- [ ] **LOOP-04**: When retry limits are exhausted the run transitions to FAILED with every attempt and reason persisted

### Independent Quality Gate

- [ ] **GATE-01**: After QA passes, Dark Factory independently runs the configured `quality_gate.commands` in the repository environment
- [ ] **GATE-02**: The gate decision is based on command exit codes, not on agent prose or self-reports
- [ ] **GATE-03**: Developer and QA agents can still run their own tests/lint/build during their work; that self-validation is never accepted as final system truth
- [ ] **GATE-04**: The quality-gate result is written to `verification/quality_gate.json`

### Git Lifecycle & GitHub

- [ ] **GIT-01**: Each run has an explicit working branch created from the configured base branch; all roles operate on the same run repository state
- [ ] **GIT-02**: Dark Factory owns delivery actions (create branch, commit, push, create PR); agents never own commit/push/PR policy
- [ ] **GIT-03**: Publishing occurs only when QA = PASS and Quality Gate = PASS, then collects the final diff, commits, pushes, creates the PR, persists PR metadata, and transitions to COMPLETED
- [ ] **GIT-04**: Publishing is idempotent — retrying with an existing `pr_number` does not open a second PR; branch, commit SHA, PR number/URL, and clarification-comment id are persisted and checked before acting
- [ ] **GIT-05**: For a GitHub-sourced run, Dark Factory can post a clarification comment on the issue and keep the run `WAITING_HUMAN` until an answer is associated with the pending interaction
- [ ] **GIT-06**: A GitHub event handler receiving a new comment finds the associated run and pending interaction, stores the answer, and resumes the same `RoleExecution` — it never creates a new run

### Triggers & CLI

- [ ] **TRIG-01**: There is one orchestration implementation; CLI, IDE, CI, and GitHub events are only triggers — there is no separate CI orchestrator
- [ ] **TRIG-02**: The CLI provides `run`, `resume`, `status`, `runs`, `artifacts`, and `events`
- [ ] **TRIG-03**: `dark-factory status <run>` renders the run id, task, state, per-role pipeline with worker and attempt counts, artifacts, and human interactions
- [ ] **TRIG-04**: A run can continue across the local → CI boundary through Neon with no separate CI code path

### Configuration

- [ ] **CFG-01**: Repository behavior is configured in `.dark-factory.yaml` (version, `workflow.roles`, `repository.base_branch`, per-role definition files, `quality_gate.commands`, `retry` limits, `publishing.create_pr`)
- [ ] **CFG-02**: Role behavior lives in `.dark-factory/` files (role YAML, instruction Markdown, examples) and is editable without changing Python source
- [ ] **CFG-03**: A role definition is fully configuration-driven — instructions, tools, permissions, before/after hooks, outputs, worker
- [ ] **CFG-04**: An `ActionRegistry` exposes deterministic before/after actions referenced by configuration (`prepare_role_context`, `ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, `collect_test_results`, …) and accepts new actions without core changes
- [ ] **CFG-05**: The configuration resolved at run creation is snapshotted and persisted, so a later resume is deterministic even if `.dark-factory.yaml` changed in between

### Observability

- [ ] **OBS-01**: Dark Factory can report, for any run, its current state, active role, worker, worker session id, attempt number, role history, artifacts, questions, human answers, quality-gate results, errors, PR information, and state-transition history
- [ ] **OBS-02**: Important state changes and side effects are persisted as typed events (RUN_CREATED, ROLE_STARTED/COMPLETED/FAILED, ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED, PUBLISH_STARTED, PR_CREATED, RUN_COMPLETED, RUN_FAILED)
- [ ] **OBS-03**: `dark-factory events <run>` and `dark-factory runs` expose the audit trail and run list

### Secrets

- [ ] **SEC-01**: `DATABASE_URL`, GitHub credentials, and worker credentials never appear in role artifacts, worker prompts, Neon event payloads, GitHub comments, logs, or test reports
- [ ] **SEC-02**: Secret redaction is applied to persisted event payloads and logs from the first persistence code, not retrofitted
- [ ] **SEC-03**: A worker subprocess does not inherit the full Dark Factory process environment; it receives only the minimum required for its role

### Quality & Testing

- [ ] **QUAL-01**: Orchestration behavior is tested end-to-end with `FakeWorker` — role transitions, artifact handoffs, pause/resume, QA rejection, Developer retries, quality-gate retries, failure limits, publishing — with no external AI calls
- [ ] **QUAL-02**: A shared `CodingWorker` contract-test suite runs against every adapter (including `FakeWorker`) so `FakeWorker` cannot diverge from real adapter behavior
- [ ] **QUAL-03**: Each real worker adapter (ClaudeCode, Copilot, Hermes) has its own integration test suite, skipped when the runtime's credentials are absent
- [ ] **QUAL-04**: A CI check fails the build if worker-name branching leaks outside the adapters

## v2 Requirements

Deferred. Tracked, not in the current roadmap.

### Integrations

- **INTG-01**: Confluence / Jira / TestRail / Figma / Teams / Slack / Azure DevOps / GitLab providers as task sources, context providers, tools, artifact stores, human-interaction channels, or publishing targets — the integration layer must make these addable without changing core orchestration, but none ship in Milestone 1

### Observability surface

- **OBS-V2-01**: Real-time web dashboard for run monitoring (CLI `status`/`events` is the v1 surface)

## Out of Scope

Explicitly excluded. Anti-features carry a warning against re-adding.

| Feature | Reason |
|---------|--------|
| Building another coding agent / autonomous engineering loop | The engineering agent owns *how*; Dark Factory owns only *what happens next* |
| Generic arbitrary-DAG workflow engine (Airflow/Prefect-style) | The workflow stays a clear ordered role pipeline with explicit feedback transitions |
| Embedded JavaScript / scripting runtime for actions | Actions are Python implementations referenced by config (DMTools-style extensibility without the JS runtime) |
| Separate CI orchestration implementation | CI is just another trigger for the one orchestrator |
| Separate distributed-lock service (ZooKeeper/etcd/Redis lock) | Run concurrency is enforced with PostgreSQL transactions / row locking / conditional updates |
| Durable-workflow engine (Temporal / Prefect / Celery) | Overkill for a short human-speed pipeline; violates the "no separate orchestrator / no lock service" intent — hand-rolled enum FSM with Neon checkpoints instead |
| Async SQLAlchemy / async orchestrator core | One run at a time, blocking on multi-minute agent subprocesses — async adds function-coloring and pooling hazards for zero throughput gain |
| Turning Neon into a document store | Neon holds state, metadata, and audit references; the filesystem holds artifact content |
| Trusting agent transcripts / self-reports as verification truth | The independent quality gate re-runs the repo's real commands and decides on exit codes |
| Agents owning git / PR operations | Publishing policy stays out of autonomous agents |
| Copying the whole repository into prompts | The agent inspects the repo itself; context is role-scoped |
| Multi-agent chat negotiation between roles | Roles hand off through durable artifacts, not a shared conversation |
| Auto-merging a PR on a green quality gate | Dark Factory opens the PR; a human merges |
| Worker eval / benchmark harness | Not part of the delivery-orchestration core |

## Traceability

Populated during roadmap creation. Each v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (all v1 requirements) | TBD | Pending |

**Coverage:**
- v1 requirements: 89 total
- Mapped to phases: 0 ⚠️ (roadmap not yet created)
- Unmapped: 89 ⚠️

---
*Requirements defined: 2026-09-06*
*Last updated: 2026-09-06 after initial definition*
