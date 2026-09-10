# Roadmap: Dark Factory

## Overview

Dark Factory is built tracer-first. Phase 1 is a walking skeleton: a real task becomes a real run
whose entire lifecycle lives in Neon, executes one role through a `FakeWorker`, and can be advanced
to completion by a brand-new process — proving the durable-run thesis before a single AI agent is
involved. Every phase after that adds one vertical capability slice on top of a system that already
works end to end: pausing for a human and resuming under a Postgres lease; moving the pipeline shape
into YAML; growing to the four engineering roles handing off through durable artifacts; giving each
run an isolated worktree and branch; locking down tools, permissions and credentials; then swapping
`FakeWorker` for Claude Code, then Copilot and Hermes; then the independent quality gate and bounded
feedback loops; then GitHub intake, idempotent publishing and comment-driven resume; then the
local→CI handoff; and finally the observability surface that makes the whole run explainable. At no
point is there a horizontal layer that cannot be run and verified on its own.

## Cross-Cutting Invariants

These hold from the phase that introduces them and are never relaxed. They are constraints on every
later phase, not one-time tasks.

| Invariant | From | Why |
|-----------|------|-----|
| Every lifecycle mutation (store result, transition state, create interaction, emit event) commits in ONE transaction through one mutation path | Phase 1 | State can never move without its audit row, or vice versa |
| Every input a `resume()` needs is a persisted column — zero in-memory carryover | Phase 1 | A fresh process on a fresh machine must reconstruct everything |
| Control state is read from state columns, never recomputed by folding `run_events` | Phase 1 | Checkpoint, not replay |
| Only the orchestrator mutates lifecycle state; worker results are typed signals, never transitions | Phase 1 | The outer loop stays deterministic |
| Secret redaction is applied in the first persistence code, never retrofitted | Phase 1 | Leaks are unrecoverable once persisted |
| No worker-name branching outside adapters (CI-enforced) | Phase 1 (guard from Phase 7) | Role ≠ Worker |
| A database transaction is never held open across a subprocess call | Phase 2 | Multi-minute agent steps must not hold locks |
| Concurrency is claim-don't-check: conditional `UPDATE` lease + guarded status update, no lock service | Phase 2 | Postgres already gives single-owner execution |
| Every external side effect is idempotent, keyed on a persisted identifier | Phase 5 (git), Phase 10 (GitHub) | Retry-safety is the last mile of durability |
| Verdicts come from exit codes and machine JSON, never agent prose | Phase 4 (QA verdict), Phase 9 (gate) | Agents emit completion language regardless of reality |

## Open Decisions

Three decisions were flagged during research and are resolved inside the phase that first needs them.

| # | Decision | Resolved in | Leading option |
|---|----------|-------------|----------------|
| 1 | Artifact-content durability for cross-machine resume | Phase 5 | Commit artifacts to a `.dark-factory/` path on the run's working branch so they travel with the clone |
| 2 | Lease TTL vs. unpredictable agent step duration | Phase 2 | Heartbeat `lock_expires_at` every TTL/3 on a 5–15 min baseline; validate with a slow-step + competing-process test |
| 3 | Exact non-interactive flag/env matrix for the Copilot and Hermes CLIs | Phase 8 | Hands-on spike per adapter in a clean container; document the result in `WorkerCapabilities` |

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Walking Skeleton — One Durable Run** - A text task becomes a run that persists its whole lifecycle in Neon and is resumable from a fresh process (completed 2026-09-09)
- [x] **Phase 2: Pause, Resume & Single-Owner Execution** - A run stops for a human answer, releases its process, and is resumed later by exactly one process (completed 2026-09-10)
- [ ] **Phase 3: Configuration-Driven Pipeline** - Pipeline shape and role behaviour come from YAML, snapshotted per run for deterministic resume
- [ ] **Phase 4: The Four-Role Pipeline & Artifact Handoffs** - BA → Architect → Developer → QA hand off through durable artifacts with machine-readable verdicts
- [ ] **Phase 5: Isolated Workspace & Git Lifecycle** - Every run owns a working branch and clean worktree, and its artifacts travel to another machine
- [ ] **Phase 6: Tools, Permissions & the Credential Boundary** - Roles get only granted capabilities; workers never see an infrastructure credential
- [ ] **Phase 7: Claude Code — the First Real Worker** - A real agent runtime performs a role and resumes, with the orchestrator runtime-agnostic
- [ ] **Phase 8: Copilot & Hermes — Worker Independence Proven** - The same role runs unchanged on three genuinely different runtimes, chosen in config
- [ ] **Phase 9: Independent Quality Gate & Bounded Feedback Loops** - The platform re-runs the repo's own commands and bounds every retry
- [ ] **Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume** - An issue starts a run, the run asks on the issue, and a verified result becomes exactly one PR
- [ ] **Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume** - A run started locally finishes in CI through Neon alone, proven by the FakeWorker suite
- [ ] **Phase 12: Observability & Audit Surface** - For any run, Dark Factory can explain exactly where it is and everything that happened to it

## Phase Details

### Phase 1: Walking Skeleton — One Durable Run

**Goal**: A plain-text task becomes a durable run whose complete lifecycle lives in Neon and can be advanced to a terminal state by any fresh process, with a redacted audit trail — no AI, no GitHub, no quality gate.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: INTAKE-01, INTAKE-04, INTAKE-05, ORCH-01, ORCH-05, ORCH-06, STATE-01, STATE-02, STATE-03, STATE-06, STATE-07, STATE-08, WORK-01, WORK-03, WORK-08, WORK-10, SEC-02
**Success Criteria** (what must be TRUE):

  1. `dark-factory run text:"..."` creates a run in Neon, drives it through one configured role using `FakeWorker` with zero external AI calls, and reaches a terminal state.
  2. Killing the process mid-run and invoking the orchestrator again from a brand-new process — with no in-memory carryover — continues from the last committed step and reaches the same terminal state.
  3. `dark-factory status <run-id>` reports run state, current role and attempt number read from state columns, never recomputed by folding the event log.
  4. A crash injected between the sub-writes of a transition leaves a consistent, resumable run: no state change exists without its `run_events` row, and no event exists without its state change.
  5. A task whose text contains a `DATABASE_URL`-shaped value shows redacted values in every persisted event payload and every log line.

**Plans**: 9/9 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Wave 0: uv scaffold, pinned stack, tooling, and a reachable test PostgreSQL 17 (blocking)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Domain contracts: RunStatus, Signal, event catalog, NormalizedTask, WorkerResult, CodingWorker, WorkerRegistry, FakeWorker

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Redaction at birth: Settings with SecretStr, the one redact(), and the structlog processor

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Schema: runs / role_executions / run_events and Alembic revision 0001 applied to a real PostgreSQL 17

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — The one mutation path (create_run, apply_transition) and the read model (load_run_state)

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-06-PLAN.md — TRACER: `dark-factory run text:"..."` drives CREATED → BA → COMPLETED end to end

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 01-07-PLAN.md — SC2 fresh-process resume and SC4 crash-consistency proofs
- [x] 01-08-PLAN.md — `dark-factory status` reading position from columns, plus `--json`

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 01-09-PLAN.md — SC5 end-to-end redaction proof, phase acceptance gate, and the documented full-stack run command

**Invariants**: single-transaction lifecycle mutation through one mutation path; every resume input is a persisted column; control state from columns not the event log; only the orchestrator mutates state; redaction from the first persistence code; no worker-name branching outside adapters.
**Note**: The artifact-durability strategy (open decision 1) affects schema shape; record the intended approach here even though it is implemented in Phase 5. Retry-counter placement (columns on `runs` vs. derived) is settled with this schema.

### Phase 2: Pause, Resume & Single-Owner Execution

**Goal**: A run can stop mid-role to ask a human a question, release its process safely, and later be resumed by exactly one process — even after the original process died.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: HITL-01, HITL-02, HITL-03, HITL-07, HITL-08, STATE-04
**Success Criteria** (what must be TRUE):

  1. A role returning `NEEDS_INPUT` leaves the run `WAITING_HUMAN` with the question, the worker result, the worker session id and the current role persisted; the process exits 0 holding no open database transaction.
  2. `dark-factory resume <run-id> --answer "..."` from a brand-new process continues the same role execution and attempt — it never creates a new run and needs nothing from the original process.
  3. Two processes racing `advance` on the same run: one executes, the other exits cleanly without changing status and without duplicating work.
  4. A process killed while owning a run loses its lease by database-clock expiry, and the next process claims the run and continues from the last committed step.
  5. A role step that runs longer than the lease TTL is not falsely stolen — the owner heartbeats the lease while the step is in flight.

**Plans**: 7/7 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Wave 0: the `human_interactions` table and the two lease columns on `runs`, applied as Alembic revision 0003 (blocking)
- [x] 02-02-PLAN.md — Wave 0: WAITING_HUMAN as a stop status, the four Phase 2 event types, the lease TTL/heartbeat settings (Open Decision 2), and the two-real-process test harness

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — TRACER: a run pauses for a human, releases its process, and a brand-new process resumes it with `resume --answer`, under a Postgres lease

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — SC3 single-owner race and SC4 killed-owner expiry reclaim, across two real processes
- [x] 02-05-PLAN.md — SC5 heartbeat on a slow step, the no-transaction-across-the-worker proof, and the lease-lost abort
- [x] 02-06-PLAN.md — HITL-01 generic pause mechanism, pause/answer crash atomicity, and the redaction sweep over the new text fields

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-07-PLAN.md — Phase acceptance gate, operator documentation for the lease knobs and the pause/resume walkthrough

**Invariants**: no database transaction held across a worker call; claim-don't-check concurrency (conditional `UPDATE` lease + guarded status update); all expiry checks use the database clock, never a process clock.
**Decision**: Resolves open decision 2 — lease TTL and heartbeat policy, validated by a slow-step + competing-process test.

### Phase 3: Configuration-Driven Pipeline

**Goal**: The pipeline shape and every role's behaviour come from repository configuration rather than code, and the configuration a run resolves at creation is snapshotted so a later resume is deterministic.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: ORCH-02, ORCH-03, CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, WORK-02
**Success Criteria** (what must be TRUE):

  1. Shortening or reordering `workflow.roles` in `.dark-factory.yaml` changes the executed pipeline with no Python change and no orchestrator edit.
  2. A role's instructions, tools, permissions, before/after hooks, outputs and worker are read from `.dark-factory/` role YAML and instruction Markdown; editing those files changes behaviour without touching source.
  3. Editing `.dark-factory.yaml` while a run is paused and then resuming executes the configuration snapshot resolved at run creation, not the edited file.
  4. A before/after hook named in configuration resolves through the `ActionRegistry`, and an unknown action or worker name fails validation at run creation with a non-zero exit and no orphan run.

**Plans**: TBD
**Invariants**: workers are created only through the registry; configuration is never re-read live on resume.

### Phase 4: The Four-Role Pipeline & Artifact Handoffs

**Goal**: BA → Architect → Developer → QA execute in sequence, communicating only through durable artifacts, with the QA verdict as the machine input to the orchestrator's next decision.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04, ROLE-06, CTX-01, CTX-02, CTX-03, CTX-04, ART-01, ART-02, ART-03, STATE-05, INTAKE-02
**Success Criteria** (what must be TRUE):

  1. A run started from `spec:./task.md` executes all four roles in order on `FakeWorker` and produces `requirements.md` + `acceptance_criteria.json`, `design.md` + `constraints.json`, `implementation_summary.json`, and `test_report.json` + `verdict.json` under `.dark-factory/runs/<run-id>/`.
  2. Every artifact has an `ArtifactReference` row in Neon while its content stays on the filesystem — no artifact body is stored in the database.
  3. A role's context contains only the prior artifacts its configuration selects, plus repository document paths and any human answers — never a dump of the repository source tree.
  4. A retried attempt's rebuilt context contains no artifact from the superseded attempt.
  5. A machine artifact that violates its JSON schema fails the role with a persisted error instead of advancing the run, and the transition after QA is decided by `verdict.json`, never by summary prose.

**Plans**: TBD
**Invariants**: roles hand off through artifacts, never a shared conversation; where orchestration depends on a result, the JSON contract is authoritative; the ContextBuilder never walks the source tree.

### Phase 5: Isolated Workspace & Git Lifecycle

**Goal**: Every run owns an explicit working branch and a clean worktree that all roles share, Dark Factory owns the git actions, and the run's artifacts travel with it to another machine.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: GIT-01, GIT-02, ART-04, ROLE-05
**Success Criteria** (what must be TRUE):

  1. A run creates a working branch from the configured base branch, named so it is unique to the run id, and every role executes against that same worktree.
  2. A process on a different machine, given only the run id and a fresh clone, has the run's artifact content available to rebuild context and continue.
  3. A role that finishes with uncommitted changes is recovered on next entry — changes WIP-committed to a persisted ref, worktree clean, nothing lost — and an entry on a detached HEAD fails the role with a persisted event instead of proceeding.
  4. A role whose diff touches paths outside its configured write scope (QA touching production code) fails the role; the out-of-scope edit is reverted and the violation is logged.

**Plans**: TBD
**Invariants**: agents never own commit/push/PR policy; git effects are guarded by persisted identifiers before acting.
**Decision**: Resolves open decision 1 — artifact-content durability for cross-machine resume (leading option: commit artifacts to a `.dark-factory/` path on the run's working branch, excluded from the published diff).

### Phase 6: Tools, Permissions & the Credential Boundary

**Goal**: A role receives exactly the capabilities its configuration grants and nothing more, and a worker subprocess can never reach an infrastructure credential.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, SEC-01, SEC-03
**Success Criteria** (what must be TRUE):

  1. A role invoking a capability it was not granted is denied by the registry (deny-by-default) and the denial is persisted as an event; BA and Architect cannot write source, Developer can write and shell, QA can write tests and shell but cannot publish.
  2. Dumping a worker subprocess environment shows no `DATABASE_URL`, no `GITHUB_TOKEN`, and no unrelated key inherited from the Dark Factory process — only the allowlisted minimum plus that worker's own credential.
  3. A new capability is added to the `ToolRegistry` and granted to one role without editing any role executor.
  4. Grepping every role artifact, worker prompt, event payload, log and report for the known secret values returns zero occurrences.
  5. Tools are exposed to a compatible worker over the optional MCP transport, and removing MCP entirely leaves the orchestrator fully functional — core code imports nothing from MCP.

**Plans**: TBD
**Invariants**: worker environments are built up from an empty dict, never from `os.environ`; permission checks happen on every invocation and are never delegated to the worker.

### Phase 7: Claude Code — the First Real Worker

**Goal**: A real agent runtime performs a role end to end, including pause and resume, while the orchestrator remains unable to tell which runtime it is talking to.
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: WORK-04, WORK-07, HITL-04, HITL-05, QUAL-02, QUAL-04
**Success Criteria** (what must be TRUE):

  1. A run configured with `claude-code` executes a role non-interactively as a subprocess and returns a normalized `WorkerResult` (status, summary, questions, artifacts, changed_files, worker_session_id, metadata).
  2. A run paused mid-role resumes through the adapter's native session id, and a worker declaring `native_resume=false` resumes by context reconstruction — the orchestrator issues the identical `worker.resume(...)` call in both cases and never interprets the session id.
  3. The shared `CodingWorker` contract-test suite passes against both `FakeWorker` and `ClaudeCodeWorker`, so the fake cannot diverge from real adapter semantics.
  4. A CI check fails the build when a worker name appears outside the adapter modules.
  5. A hung or over-long agent subprocess is killed by timeout with its process group, its output is streamed to the run's log files rather than buffered, and the role failure is persisted with the captured output.

**Plans**: TBD
**Invariants**: the native-resume vs. context-reconstruction branch lives inside the adapter; adapters never import orchestrator, workflow or persistence code.

### Phase 8: Copilot & Hermes — Worker Independence Proven

**Goal**: The same role runs unchanged on three genuinely different agent runtimes, selected purely in configuration.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: WORK-05, WORK-06, WORK-09, QUAL-03
**Success Criteria** (what must be TRUE):

  1. `copilot` and `hermes` each execute a role non-interactively and unattended in a clean container with no pre-existing CLI state, and each returns a normalized `WorkerResult`.
  2. Reassigning roles across the three runtimes in configuration (for example Architect on Copilot, Developer on Claude Code, QA on Hermes) requires no change to workflow code and the run still completes.
  3. Each adapter has its own integration suite that is skipped — not failed — when that runtime's credentials are absent, and the shared contract suite passes over all four workers.
  4. Each adapter's declared `WorkerCapabilities` matches its observed behaviour for native resume, session id, non-interactive mode and structured output.

**Plans**: TBD
**Decision**: Resolves open decision 3 — the exact non-interactive flag/env matrix for the Copilot and Hermes CLIs, established by hands-on spike in a clean container and documented in `WorkerCapabilities`.

### Phase 9: Independent Quality Gate & Bounded Feedback Loops

**Goal**: Nothing an agent claims is accepted as truth — Dark Factory re-runs the repository's own commands itself, and every rejection loops back to the Developer under a hard cap.
**Mode:** mvp
**Depends on**: Phase 5 (run worktree), Phase 4 (QA verdict)
**Requirements**: GATE-01, GATE-02, GATE-03, GATE-04, LOOP-01, LOOP-02, LOOP-03, LOOP-04
**Success Criteria** (what must be TRUE):

  1. Once QA passes, the configured `quality_gate.commands` run in the run's worktree in the repository's own environment, and `verification/quality_gate.json` records each command's exit code and captured output.
  2. When the agents report success but a gate command exits non-zero, the run does not advance to publishing — the gate decision comes from exit codes, and agent self-validation is preserved but never final.
  3. A QA FAIL returns a structured issues artifact (severity, acceptance criterion, description) to the Developer; a gate FAIL returns the actual command failure output, after which QA re-evaluates and the gate re-runs.
  4. Iteration counts are checked before dispatch against `retry.qa_developer_max_iterations` and `retry.quality_gate_max_iterations`, and on exhaustion the run transitions to FAILED with every attempt and reason persisted.

**Plans**: TBD
**Invariants**: verdicts from exit codes and machine JSON, never prose; the real failure payload is persisted, not just a boolean.

### Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume

**Goal**: A GitHub issue starts a run, the run asks its clarifying questions on that issue, and a QA-passed and gate-passed result becomes exactly one pull request.
**Mode:** mvp
**Depends on**: Phase 9
**Requirements**: INTAKE-03, GIT-03, GIT-04, GIT-05, GIT-06
**Success Criteria** (what must be TRUE):

  1. `dark-factory run github:152` builds a `NormalizedTask` from the issue title, body, comments, labels and repository metadata, after which the orchestrator is agnostic to the origin.
  2. With QA PASS and Quality Gate PASS, the run collects the final diff, commits, pushes, creates the PR, persists PR number, URL and commit SHA, and reaches COMPLETED.
  3. Killing the process after the PR API call but before its identifier is committed, then resuming, yields one PR — not two; branch, commit SHA, PR number and comment id are all checked before acting.
  4. A GitHub-sourced run posts exactly one clarification comment and stays `WAITING_HUMAN`; a duplicate webhook delivery of the reply stores exactly one answer.
  5. An issue comment answering a pending interaction resumes the same `RoleExecution`, and a comment that matches no pending interaction creates no run.

**Plans**: TBD
**Invariants**: every external side effect is idempotent, keyed on a persisted identifier; the webhook path takes the same lease as the CLI path.

### Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume

**Goal**: A run started on a laptop finishes in CI (and the reverse) through Neon alone, and the complete lifecycle is provable in CI without a single AI call.
**Mode:** mvp
**Depends on**: Phase 10
**Requirements**: TRIG-01, TRIG-04, HITL-06, QUAL-01
**Success Criteria** (what must be TRUE):

  1. A run started and paused locally is picked up by a CI job on a different machine with no local state carried over, and it completes correctly.
  2. CLI, webhook and CI entrypoints all funnel into the same `advance(run_id)`; there is no separate CI orchestrator and no CI-only code path.
  3. The `FakeWorker` orchestration suite covers role transitions, artifact handoffs, pause/resume, QA rejection, Developer retries, quality-gate retries, retry exhaustion and publishing, and runs green in CI with no external AI calls and no live worker credentials.

**Plans**: TBD
**Invariants**: triggers carry zero lifecycle logic; the run's working state is re-materialized from Neon plus git on any machine.

### Phase 12: Observability & Audit Surface

**Goal**: For any run, Dark Factory can say exactly where it is and retell everything that happened to it — the observability half of the durability thesis.
**Mode:** mvp
**Depends on**: Phase 11
**Requirements**: OBS-01, OBS-02, OBS-03, TRIG-02, TRIG-03
**Success Criteria** (what must be TRUE):

  1. `dark-factory status <run-id>` reports current state, active role, worker, worker session id, attempt number, per-role history, artifacts, questions and human answers, quality-gate results, errors, PR information and the state-transition history.
  2. The CLI command set is complete — `run`, `resume`, `status`, `runs`, `artifacts`, `events` — with `runs` listing runs and `events` exposing the full typed audit trail.
  3. Every event type in the catalog (RUN_CREATED through RUN_FAILED, including ROLE_*, ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED, QA_*, QUALITY_GATE_*, PUBLISH_STARTED, PR_CREATED) is emitted at the right moment, and a finished run's story is reconstructable from the event stream alone.
  4. An end-to-end run seeded with realistically-shaped fake secrets leaves zero occurrences of them across artifacts, events, logs, GitHub comments and test reports.

**Plans**: TBD
**Invariants**: read models never mutate anything; the event log stays audit-only and is never used to compute control state.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Walking Skeleton — One Durable Run | 9/9 | Complete    | 2026-09-09 |
| 2. Pause, Resume & Single-Owner Execution | 7/7 | Complete    | 2026-09-10 |
| 3. Configuration-Driven Pipeline | 0/TBD | Not started | - |
| 4. The Four-Role Pipeline & Artifact Handoffs | 0/TBD | Not started | - |
| 5. Isolated Workspace & Git Lifecycle | 0/TBD | Not started | - |
| 6. Tools, Permissions & the Credential Boundary | 0/TBD | Not started | - |
| 7. Claude Code — the First Real Worker | 0/TBD | Not started | - |
| 8. Copilot & Hermes — Worker Independence Proven | 0/TBD | Not started | - |
| 9. Independent Quality Gate & Bounded Feedback Loops | 0/TBD | Not started | - |
| 10. GitHub — Issue Intake, Idempotent Publishing, Comment Resume | 0/TBD | Not started | - |
| 11. One Orchestrator, Many Triggers — Cross-Machine Resume | 0/TBD | Not started | - |
| 12. Observability & Audit Surface | 0/TBD | Not started | - |

## Coverage

All 89 v1 requirements map to exactly one phase. No orphans, no duplicates.

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1 | INTAKE-01, INTAKE-04, INTAKE-05, ORCH-01, ORCH-05, ORCH-06, STATE-01, STATE-02, STATE-03, STATE-06, STATE-07, STATE-08, WORK-01, WORK-03, WORK-08, WORK-10, SEC-02 | 17 |
| 2 | HITL-01, HITL-02, HITL-03, HITL-07, HITL-08, STATE-04 | 6 |
| 3 | ORCH-02, ORCH-03, CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, WORK-02 | 8 |
| 4 | ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04, ROLE-06, CTX-01, CTX-02, CTX-03, CTX-04, ART-01, ART-02, ART-03, STATE-05, INTAKE-02 | 15 |
| 5 | GIT-01, GIT-02, ART-04, ROLE-05 | 4 |
| 6 | TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, SEC-01, SEC-03 | 7 |
| 7 | WORK-04, WORK-07, HITL-04, HITL-05, QUAL-02, QUAL-04 | 6 |
| 8 | WORK-05, WORK-06, WORK-09, QUAL-03 | 4 |
| 9 | GATE-01, GATE-02, GATE-03, GATE-04, LOOP-01, LOOP-02, LOOP-03, LOOP-04 | 8 |
| 10 | INTAKE-03, GIT-03, GIT-04, GIT-05, GIT-06 | 5 |
| 11 | TRIG-01, TRIG-04, HITL-06, QUAL-01 | 4 |
| 12 | OBS-01, OBS-02, OBS-03, TRIG-02, TRIG-03 | 5 |
| **Total** | | **89** |

---
*Roadmap created: 2026-09-07*
