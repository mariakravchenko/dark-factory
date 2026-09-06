# Research Synthesis: Dark Factory

**Domain:** Durable, resumable AI-agent delivery orchestration platform (Python + Neon PostgreSQL)
**Synthesized:** 2026-09-06
**Status:** READY FOR ROADMAP PLANNING

---

## Executive Summary

Dark Factory is a deterministic orchestration platform that hires external AI coding agents (Claude Code, Copilot, Hermes) to perform bounded engineering work within a role-based pipeline (BA → Architect → Developer → QA → Quality Gate → Publish), and **guarantees that any run survives a crash, a machine change, and a delayed human answer and still produces a correctly verified GitHub PR.** This is the execution environment *around* coding agents, not a coding agent itself.

The durable-run thesis — "if the orchestrator cannot explain where a run is, it cannot reliably resume it" — is the load-bearing constraint. Everything follows from this: every lifecycle state and side effect must be persisted in Neon, cross-process resume must work from any machine with zero in-memory carryover, and observability is not optional—it is the prerequisite for durability.

The recommended approach is **fully synchronous, checkpoint-in-Postgres, hand-rolled state machine** with explicit enum states, Postgres-native row leasing for concurrency, and no distributed-lock service or workflow engine. The stack is Python 3.12 + SQLAlchemy 2.0 + psycopg3 + Typer CLI + githubkit for GitHub, with Neon as a plain-Postgres database (no provider-specific logic in the application layer). The worker abstraction (`CodingWorker` port + `WorkerRegistry` + `WorkerCapabilities` model) decouples the orchestrator from runtime details; runtime-specific logic lives sealed inside adapters. The critical architectural patterns are: (1) resume-first (all paths reconstruct from Neon with zero process-memory carryover), (2) deterministic outer lifecycle (platform owns state transitions; agents have freedom only inside engineering work), (3) Postgres-only concurrency (no external lock service), and (4) artifact-based handoffs (JSON for machine decisions, Markdown for humans; content on the filesystem, metadata in Neon).

The research across four dimensions strongly converges on a **unified, convergent phase spine** for build order (see "Implications for Roadmap" below). No contradictions emerged; the findings reinforce each other.

---

## Key Findings from Research Files

### From STACK.md

**Technology recommendations (verified against PyPI 2026-09-06):**

- **Core runtime:** Python 3.12, Typer 0.27.2 (CLI), SQLAlchemy 2.0.52 + psycopg 3.3.5 (sync Postgres via Neon), Alembic 1.19.2
- **Domain models:** pydantic 2.13.5 (validated boundary data), pydantic-settings 2.15.0 (secrets with `SecretStr`)
- **GitHub:** githubkit 0.16.1 (fully typed REST + GraphQL + webhook models)
- **Subprocess & Git:** stdlib `subprocess` (non-interactive agent CLI, explicit `env` allowlist), system `git >=2.40` via subprocess
- **Logging & structure:** structlog 26.1.0 (JSON logging with **secret-redaction processor from day one**), tenacity 9.1.4 (idempotent call retry)
- **Testing:** pytest 9.1.1, testcontainers 4.15.0 (ephemeral Postgres), polyfactory 2.x (pydantic fixtures)
- **Dev:** uv 0.12.10 (lock + deps), ruff 0.16.6 (lint + format), mypy 2.3.1 (strict typing)

**NOT to use:** Async (blocks on subprocesses; sync pays nothing here), Temporal/Prefect/Celery (overkill), psycopg2 (maintenance-only), SQLModel (lags 2.0), embedded JS, MCP as internal dependency.

**Neon strategy:** Pooled string for short queries; **direct/unpooled** for migrations; expect 300–800 ms cold starts; no long-held transactions across agent calls.

**Confidence: HIGH on libraries; MEDIUM on sync-vs-async judgment.**

---

### From FEATURES.md

**Feature landscape:**

1. **Table stakes:** Multi-source task intake, role decomposition, agent self-validation, isolated workspace, platform Git ownership, human review gate, bounded iteration, status view, repo config, CLI, secret hygiene, audit trail, idempotency.

2. **Differentiators** (where Dark Factory excels):
   - Durable run state in Neon; resume from any machine after crash/handoff/human delay
   - Deterministic outer lifecycle; agents can't drive state; only orchestrator mutates status
   - Role ≠ Worker; any role → any runtime via config, zero code changes
   - `WorkerCapabilities` model; codifies real runtime differences (native resume vs. none, JSON output, etc.)
   - Dual resume (native session OR context reconstruction) behind one interface
   - Role-specific tool permissions enforced (not advisory); BA/Architect read-only; Developer write+shell; QA write_tests+shell no publish
   - Credential isolation (agents never see `DATABASE_URL`/`GITHUB_TOKEN`; only role's minimum env)
   - Independent Quality Gate re-runs repo commands; gates publishing on QA PASS **AND** Gate PASS
   - Artifact-based handoffs (JSON for decisions, Markdown for docs; content on filesystem, metadata in Neon)
   - Event-sourced audit trail; full run reconstructable
   - Human-in-the-loop mid-run; any role can pause, persist `WAITING_HUMAN`, resume via CLI or GitHub comment
   - Bounded feedback loops (QA→Dev, Gate→Dev) with real failure payloads
   - Config-driven pipeline (reorder/shorten in YAML without code changes)
   - One orchestrator (CLI/CI/GitHub all just triggers calling same `advance()`)
   - Postgres-native concurrency (no external lock service)
   - `FakeWorker` as first-class deliverable (orchestration testable without AI calls)
   - Idempotent publishing (retry safe via persisted identifiers)

3. **Anti-features** (avoid these): Own coding agent, arbitrary DAG engine, embedded JS, separate CI orchestrator, distributed lock service, artifact content in Neon, non-core integrations in M1, trusting agent self-reports, agent owns commits/PRs, whole-repo prompts, multi-agent free-for-all, auto-merge, web dashboard in v1.

**Feature dependencies:** Durable state is foundational. Worker abstraction + FakeWorker precede multi-role testing. GitHub-issue intake unlocks comment-based clarification. Workspace isolation precedes independent verification. Tool permissions precede credential boundary. Feedback loops require machine-readable verdicts.

**MVP:** All features from spec (4 roles, 3 task sources, 3 real workers, GitHub, durable resume, human loop, quality gate, feedback, pause/resume, CI, CLI, events).

**Confidence: MEDIUM — scope from PROJECT.md is HIGH; competitor analysis is secondary (MEDIUM).**

---

### From ARCHITECTURE.md

**Foundation:**

- **Checkpoint-in-Postgres, not replay:** Authoritative state in `runs` columns + child rows, NOT in `run_events`. Events are append-only audit/observability. Every state transition writes state-column update + event in ONE transaction (transactional outbox).

- **Resume-first pattern:** One `advance(run_id)` entry point: reconstruct RunState from Neon (zero process carryover) → current node → execute one step → commit transition. `create_run()` writes row then calls `advance()`. `resume(run_id, answer)` stores answer then calls `advance()`. Crash recovery: any process calling `advance()` again.

- **Deterministic control / free engineering:** `LifecycleController.transition()` is the **only** code changing `runs.status`. Consumes typed signals from role outputs (WorkerResult.status, QAVerdict, QualityGateResult, HumanAnswer). Workers have freedom only inside their granted toolset.

- **Postgres-only concurrency:**
  - Run lease: `UPDATE runs SET owner_token = :tok, lock_expires_at = now() + 5min WHERE id = :id AND (owner_token IS NULL OR lock_expires_at < now())`; if rowcount==0 → another process owns it. Heartbeat every TTL/3; survives process death.
  - Guarded transition: `UPDATE runs SET status = :next WHERE id = :id AND status = :expected`; if rowcount==0 → someone else advanced.
  - Never `SELECT FOR UPDATE` across agent calls; only for short claim/commit. Never `pg_advisory_lock` (session-scoped, leaks through pooler); use `pg_advisory_xact_lock` or avoid advisory locks.

- **Worker as a port; resume branch inside adapter:** `CodingWorker` port (`execute()`, `resume()`, `capabilities()`). `WorkerCapabilities` explicit (native_resume, session_id, structured_output, max_prompt_bytes, etc.). Orchestrator reads capabilities only for generic decisions. The **native-session-resume vs context-reconstruction** branch is inside `adapter.resume()`. `WorkerResult` normalized (status, summary, questions, artifacts, changed_files, worker_session_id, metadata, error). No adapter imports orchestrator code.

- **Tool grants + filtered environment as security boundary:** `ToolRegistry` grants `GrantedToolset` per role. Every invocation permission-checked server-side, deny-by-default. Worker subprocess env built explicitly from allowlist (never `os.environ`): only `PATH`, `HOME`, locale, work dir, worker's own credential. Never `DATABASE_URL`, `GITHUB_TOKEN`. Redaction processor scrubs every egress.

- **Idempotent external side effects via persisted identifiers:** Publishing sub-state-machine: check branch exists (skip if yes) → check commit SHA (skip if matched) → commit → check PR exists (skip if yes) → create PR, persist `pr_number`/`pr_url` in one txn. Webhook deduped by GitHub's `X-GitHub-Delivery`.

- **Context by reference, not repo dump:** `ContextBuilder` assembles `RoleContext` = { task, instructions, selected prior artifacts, repo doc **paths**, human answers, constraints, granted capabilities }. Agent reads repo via tools. Never walks source tree; reads artifacts + interactions + config only. Prompt size budgeted.

**15-module structure:** `domain/` (value objects), `config/` (YAML + ResolvedConfig snapshot), `orchestrator/` (runner/lifecycle/effects), `workflows/`, `roles/`, `workers/`, `tools/`, `actions/`, `input/`, `context/`, `artifacts/`, `quality/`, `persistence/` (port interfaces + SQLAlchemy adapter), `integrations/`, `workspace/`, `events/`, `security/`, `observability/`, `triggers/`.

**Build order (12 stages, each independently testable):**
1. Persistence + config (5 tables, repos ports, event log with redaction, ResolvedConfig snapshot)
2. Domain value objects
3. Lifecycle state machine + runner + resume-first + Postgres lease + guarded UPDATE
4. FakeWorker + WorkerRegistry + CodingWorker port — **critical unblock for orchestration testing**
5. RoleExecutor + RoleDefinition + ActionRegistry + ContextBuilder + ArtifactStore
6. Workspace / Git lifecycle (VersionControl port)
7. ToolRegistry + permission model + security/ (env allowlist, credential store, redaction) + optional MCP
8. Real worker adapters (ClaudeCode, Copilot, Hermes) + per-adapter integration suites
9. Independent Quality Gate runner
10. GitHub integration (issue source, idempotent publish, webhook → resume)
11. Triggers (CLI/webhook/CI)
12. Observability read models + event-redaction hardening

**Cross-cutting invariants** (enforced from stage 1):
- Single-transaction lifecycle mutations; every resume input persisted; never hold DB transaction across subprocess
- Claim-don't-check concurrency; per-side-effect idempotency keyed by persisted id
- Verification via exit codes, not agent prose
- Secret redaction from day one

**Confidence: MEDIUM-HIGH — patterns well-established; mapping to Dark Factory is reasoned synthesis.**

---

### From PITFALLS.md

**23 critical pitfalls** with prevention phases and verification steps. Most load-bearing:

1. Non-atomic result+transition+interaction → all writes in ONE txn
2. State unreconstructable without process memory → every resume value persisted
3. Two processes resume same run simultaneously → lease claim + guarded transition + heartbeat
4. Transaction held across agent call → `txn { mark running } → agent → txn { store result }`
5. Lost `worker_session_id` → first-class column, same txn as pause
6. Worker abstraction leaks (`if worker ==`) → CI grep-guard, enforce with import-linter
7. Brittle stdout parsing → structured output where available; otherwise artifact-based verdicts
8. Subprocess hazards (zombies, PIPE deadlock, no timeout, unbounded buffers) → stream to files, timeout, process group kill
9. Non-interactive flags still prompt → per-adapter non-interactive posture + integration test in clean container
10. Secrets leaking everywhere → explicit env allowlist, single `redact()` scrubber, `SecretStr` wrappers
11. Retry publish → second PR → check-before-create keyed by persisted id
12. Trusting agent self-reports → independent Quality Gate re-runs repo commands
13. Retry limits unenforced → persisted counters checked before dispatch
14. Actual failure output not persisted → raw command output + structured issues artifact
15. Role permission boundaries not enforced → tool-layer grants + post-role diff check
16. Stale artifacts/worktree bleed → artifacts namespaced by (run_id, role, attempt); worktree clean at entry
17. Whole-repo prompt stuffing → context by reference; agent reads repo; prompt-size budget checked
18. Webhook resume: wrong run / new run / race → persist linkage, resolve carefully, dedupe on delivery id, same claim mechanism as CLI
19. Git lifecycle (dirty/detached/collision/lost) → branch includes run id, assert named branch, WIP-commit before destructive ops
20. Config resolved late → snapshot resolved workflow into JSONB at creation; resume reads snapshot
21. Clock skew across processes → all timestamps use DB clock; lease checks in SQL
22. Alembic unsafe concurrently; JSONB unbounded → direct connection + advisory-lock; large content on filesystem
23. FakeWorker diverges; integration tests need live creds → shared contract suite over all workers; recorded-integration tests in CI

**Confidence: HIGH for durable-execution / Neon / PgBouncer; MEDIUM for per-worker CLI specifics.**

---

## Implications for Roadmap

### Convergent Phase Spine (12 Phases)

The four research files converge on a unified build order. Each phase is independently testable and earlier phases don't create dependency debt.

#### Phase 1: Persistence + Configuration Foundation
- Neon schema (5 core tables), SQLAlchemy models, Alembic migrations
- Repository port interfaces + SQLAlchemy adapter
- **Secret redaction from day one:** EventLog filters all payloads
- Neon strategy: pooled vs. direct strings, PgBouncer gotchas, cold-start retry
- ResolvedConfig model: workflow snapshot persisted per run
- `.dark-factory.yaml` + role-file loader
- Migration lock pattern via direct connection + pg_advisory_xact_lock
- **Verification:** Concurrent alembic upgrade doesn't corrupt; crash between state writes leaves consistent resumable run; secrets redacted from all events

#### Phase 2: Domain Value Objects
- NormalizedTask, RoleContext, WorkerResult, WorkerCapabilities
- QAVerdict, QualityGateResult, ArtifactReference
- Signal enum (COMPLETED, NEEDS_INPUT, FAILED, PAUSE_FOR_HUMAN, …)
- SideEffectIntent enum
- Pure data + enums; no I/O, no dependencies on other modules
- **Verification:** None; pure data

#### Phase 3: Lifecycle State Machine + Runner
- Pure `LifecycleController.transition(state, signal) -> (next_state, [SideEffectIntent])` function
- `advance(run_id)` loop: lease claim → reconstruct RunState → determine node → execute step → commit transition + event
- Lease claim/renew/release with heartbeat; guarded status UPDATE
- Resume-first: `create_run()` writes row then calls `advance()`; `resume()` stores answer then calls `advance()`
- All paths reconstruct full state from Neon (zero in-memory carryover)
- **Verification:** Kill mid-role, resume in fresh process on fresh checkout → identical branch, counters, QA ledger, no lost work. Two `advance()` processes on same run → only one executes; other exits cleanly; status never clobbered. Inject crash between sub-writes → run remains consistent and resumable

#### Phase 4: FakeWorker + WorkerRegistry + CodingWorker Port
- CodingWorker port (execute, resume, capabilities)
- WorkerRegistry (name → adapter factory) from config
- **FakeWorker:** scripted WorkerResult sequences; testable without AI calls
- WorkerResult normalization; FakeWorker passes same contract as real adapters
- **Critical unblock:** Orchestration testing (state machine, feedback loops, pause/resume, QA rejection, retry caps, publishing) is now possible in CI without external AI or credentials
- **Verification:** FakeWorker passes shared contract-test suite; capabilities round-trip correctly (native_resume tested both True and False)

#### Phase 5: RoleExecutor + RoleDefinition + ActionRegistry + ContextBuilder + ArtifactStore
- RoleExecutor: before-actions → context → worker → persist result+artifacts → after-actions
- RoleDefinition: instructions, tools, permissions, hooks, output contract
- ActionRegistry: deterministic Python implementations (prepare_role_context, ensure_clean_worktree, collect_diff, store_role_artifacts, etc.)
- ContextBuilder → RoleContext: task + instructions + selected prior artifacts + repo doc paths + answers + constraints + granted tools
- ArtifactStore: filesystem `.dark-factory/runs/<id>/artifacts/<role>/` + ArtifactReference rows in Neon
- End-to-end wired with FakeWorker
- **Verification:** All four roles complete in sequence with FakeWorker; each stores artifacts; next role's context correctly filters prior artifacts by role config. Malformed schema fails validation + marks role FAILED

#### Phase 6: Workspace / Git Lifecycle
- VersionControl port (clone_or_open, ensure_clean, create_branch, status, diff, commit, push)
- git CLI adapter via subprocess
- Per-run worktree isolation
- Branch naming: includes run id (guaranteed unique)
- Dirty-worktree recovery: WIP-commit to persisted ref before any destructive reset
- Pre-role asserts: `git status --porcelain` empty, HEAD on named branch (not detached)
- **Verification:** Dirty-worktree test: role finishes with uncommitted changes; resume in fresh process → changes WIP-committed, worktree clean, no data lost. Detached-HEAD test: previous phase leaves detached HEAD; next phase entry asserts failure + event

#### Phase 7: ToolRegistry + Permission Model + Security
- ToolRegistry: capability → tool impl; `grant(role_name)` → GrantedToolset
- Tool port: execute with deny-by-default broker
- Built-in tools: repo.read/search/write/write_tests, git.status/diff, shell.execute, github.issue.read, artifacts.read/write
- EnvironmentBuilder: construct worker env from {}, add only PATH/HOME/locale/workdir + worker's own credential
- WorkerCredentialStore: per-worker-name key, separate from infra secrets
- Redaction utils integrated with EventLog
- Optional MCP transport adapter (tools/transports/mcp/); core never imports it
- Post-role auditor: git diff --name-only against role's allowed globs; revert out-of-bounds edits + log
- **Verification:** Worker env dump contains zero DATABASE_URL/GITHUB_TOKEN/unrelated keys. QA writing source file is rejected/reverted/logged. Grep all artifacts/events/comments for known secrets = 0

#### Phase 8: Real Worker Adapters (Claude Code, Copilot, Hermes)
- ClaudeCodeWorker: execute via `claude -p --output-format json --resume <session_id>`, parses JSON, manages sessions
- CopilotWorker: `copilot -p --no-ask-user --allow-tool`, handle non-interactive posture, parse output
- HermesWorker: `hermes chat -q --oneshot`, non-interactive, output parsing
- Each: subprocess management (streaming to files, timeouts with process-group kill, stdin=DEVNULL), resume strategy (native session OR context reconstruction) inside adapter.resume()
- Per-adapter integration suite in clean container (no prior CLI state); proves non-interactive mode works
- Shared contract-test suite ensures all three + FakeWorker emit identical WorkerResult semantics
- **Verification:** Each adapter's integration suite runs in clean container unattended. Shared contract tests pass over FakeWorker + all real adapters. Recorded-integration tests (real transcripts replayed through adapter code) cover parsing in CI without live creds

#### Phase 9: Independent Quality Gate Runner
- Execute quality_gate.commands (pytest, ruff, mypy, build, etc.) in run's worktree
- Controlled environment (explicit PATH, PYTHONPATH, venv)
- Decide on **exit codes**, not prose; capture per-command stdout+stderr
- QualityGateResult verdict: PASS or FAIL; persist verification/quality_gate.json artifact
- Feedback loop: if FAIL, store output, advance to DEVELOPMENT, feed actual output to Developer
- Wired into state machine: VERIFYING runs gate; FAIL or PASS leads to distinct transitions
- **Verification:** Real adapters claim PASS while pytest exits non-zero → run does NOT publish. Flaky test handling: output captured + fed to Developer; loop respects retry caps

#### Phase 10: GitHub Integration
- Task source: read GitHub issue → NormalizedTask (github:152 prefix)
- Idempotent publish: collect diff → check branch exists (skip if yes) → check commit SHA (skip if matched) → commit with run-id marker → check PR exists (skip if yes) → create PR, persist pr_number/pr_url/SHA in one txn
- Comment posting: post question, store clarification_comment_id, embed hidden run/interaction marker
- Webhook handler: issue comment → resolve to run + pending human_interactions via marker/latest-WAITING query → dedupe on X-GitHub-Delivery → conditional answer UPDATE (WHERE status='WAITING') → enqueue via same lease/claim mechanism as CLI
- Idempotency: retried webhook is no-op; retried publish skips duplicates
- **Verification:** Idempotent publish: run publish, kill after POST/pulls but before txn commits, resume → **one** PR. Idempotent clarification: duplicate webhook delivery → one comment, one answer. Unmatched comment → no new run

#### Phase 11: Triggers (CLI / Webhook / CI)
- CLI: run [text | spec | github], resume, status, runs, artifacts, events (Typer-based)
- Thin commands parsing args, resolving run_id, calling `orchestrator.advance()`
- Webhook endpoint: GitHub events (issues.opened, issue_comment); handler resolves run+interaction, stores answer, enqueues
- CI entrypoint: same `advance(run_id)` call; run continues from Neon across local→CI
- **Verification:** Runs from CLI, webhook, CI all execute identically (all paths → advance())

#### Phase 12: Observability Read Models + Event-Redaction Hardening
- `status` aggregation: joins runs + role_executions + artifacts + human_interactions + run_events
- Renders: state, per-role pipeline (worker/attempts), artifacts, questions, gate results, PR info, history
- `events` command: persisted event stream; human-readable narrative reconstruction
- Event-redaction hardening: review all egress paths (logs, comments, artifacts); integration tests assert secrets absent
- **Verification:** End-to-end run with real-shaped fake secrets; grep across all artifacts/events/comments = 0

### Critical Early Unblocks

- **Phase 4 (FakeWorker)** is the critical unblock. Orchestration logic (state machine, feedback loops, pause/resume, QA rejection, retry, publishing) must be testable in CI without external AI calls.
- **Phases 1–3 must land before anything else is testable.**
- **Phases 6–7 (workspace + security) must precede phase 8 (real workers) so credentials and permissions are established.**

### Phases Likely to Need Research

- **Phase 1 (Persistence):** Neon PgBouncer behavior — mostly resolved; small spike on pooled-connection-mode edge cases.
- **Phase 3 (Orchestrator):** Lease TTL vs. unpredictable agent duration — needs heartbeat policy + false-steal test (spike required).
- **Phases 7–8 (Tools/Workers):** Exact non-interactive flag/env matrix for Copilot + Hermes — requires hands-on CLI testing (spike required).
- **Artifact durability for cross-machine resume (gap 1 below):** Commit to working branch vs. S3 vs. inline Neon — decision needed by end of phase 1.

### Standard Patterns (No Research Needed)

- Phase 2 (Domain models): pydantic models.
- Phase 5 (RoleExecutor): Python patterns; reference in ARCHITECTURE.
- Phase 11 (CLI): Typer patterns well-established.
- Phase 12 (Observability): Read-model aggregation standard.

---

## Confidence Assessment

| Area | Confidence | Basis | Gaps |
|------|------------|-------|------|
| **Stack** | HIGH | Verified against PyPI 2026-09-06; rationale well-researched | Sync-vs-async MEDIUM; Neon PgBouncer test in phase 1 |
| **Features** | MEDIUM-HIGH | PROJECT.md scope HIGH; competitor analysis secondary (MEDIUM) | None; table comprehensive |
| **Architecture** | MEDIUM-HIGH | Durable-execution + Postgres-concurrency patterns HIGH; Dark Factory mapping MEDIUM | Artifact durability (decision 1); lease TTL (decision 2); per-CLI flags (decision 3) |
| **Pitfalls** | HIGH | Neon/PgBouncer official docs; durable-execution literature canonical | Per-worker CLI flags MEDIUM |
| **Overall** | MEDIUM-HIGH | Four dimensions converge; no contradictions | Three decisions need early resolution |

---

## Unresolved Decisions That Need Early Resolution

### Decision 1: Artifact-Content Durability for Cross-Machine Resume

**Problem:** Artifact content on local filesystem; resume on different machine won't have files.

**Options:**
- **(a) Commit to working branch** — Artifacts go to `.dark-factory/artifacts/<role>/` on working branch; travel with clone. Simple, versioned. Cons: pollutes PR diff (mitigate with .gitignore rules; exclude from final published diff).
- **(b) S3-compatible storage** — Upload to bucket by `<run-id>/<role>/`; metadata in Neon. Cons: new infra, creds, retention policy.
- **(c) Relax spec, inline small JSON in Neon** — Contradicts "not a document store"; bloats rows; complicates migrations.

**Recommendation:** Option (a). Simple, testable by phase 6.

**Window:** By end of phase 6 (Workspace).

### Decision 2: Lease TTL vs. Unpredictable Agent Step Duration

**Problem:** Agent steps run long; fixed TTL risks false steals (short TTL) or slow recovery (long TTL).

**Options:**
- **Heartbeat during step:** Write `UPDATE runs SET lock_expires_at = now() + interval '5 min'` every TTL/3. Keeps lease alive as long as orchestrator alive; on death, expires cleanly.
- **Adaptive TTL:** Risky (guessing doesn't always work).
- **No per-step timeout:** Role timeout (e.g., 60 min) + grace → lease TTL (e.g., 65 min). Simpler; slower recovery.

**Recommendation:** Heartbeat every TTL/3 with baseline 5–15 min. Validate with slow-step + competitor-process test.

**Window:** Phase 3 design.

### Decision 3: Exact Non-Interactive Flag/Env Matrix for Copilot + Hermes

**Problem:** Each CLI has different "don't prompt" flags, env vars, pre-seeded configs. Clean CI container requires complete posture per runtime.

**Option:** Empirical spike per adapter during phase 8; each integration suite runs unattended in clean container; iterate flags + env + config until it works; document in WorkerCapabilities.

**Window:** Phase 8 (Real Workers). Can spike earlier to unblock.

---

## Gaps to Address

1. **Cross-machine artifact durability** (decision 1) — resolves open gap in ARCHITECTURE.md
2. **Lease heartbeat policy + false-steal test** (decision 2) — concurrency-edge-case risk
3. **Copilot + Hermes CLI non-interactive completeness** (decision 3) — needs empirical validation
4. **QA "tests-only" path allowlist enforcement** — feasible in phase 7; git adapter must classify test vs. non-test cheaply
5. **Retry-counter schema location** — columns on `runs` vs. derived from role_executions/events? Decide in phase 1

All five are manageable; none block the convergent build order.

---

## Recommendations for Roadmap Creation

1. **Follow the convergent phase spine.** Only sequence where each phase is independently testable.

2. **Gate phase 4 (FakeWorker) as critical unblock.** Ship as first-class package deliverable.

3. **Resolve decision 1 (artifact durability) in phase 1.** Affects schema design + publish sub-state-machine.

4. **Resolve decision 2 (lease TTL + heartbeat) in phase 3 design.** Early clarity on concurrency.

5. **Plan phase 8 (real workers) with spikes for decision 3.** Each adapter tested in clean container before sign-off.

6. **Treat 23 pitfalls as phase checklist.** PITFALLS.md line 706–733 maps pitfalls → phases. Include "Looks Done But Isn't" (line 672–690) in every phase's acceptance criteria.

7. **Invest in durable-state discipline from day one.** Pitfalls 1 (non-atomic) and 2 (resume-first) are load-bearing. Import-linter enforces boundaries.

8. **Make credential boundary structural.** security/EnvironmentBuilder (phase 7) makes "agents never see DATABASE_URL" checkable + verifiable; not just prompt instruction.

---

**Research synthesis prepared for:** `/gsd-roadmapper`
**Ready for:** Phase-sequencing, dependency modeling, detailed acceptance-criteria writing
**Awaiting:** User validation and roadmap planning decision
