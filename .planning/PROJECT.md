# Dark Factory

## What This Is

Dark Factory is a durable software-delivery orchestration platform for AI engineering
agents. It coordinates a single development task through specialized engineering roles —
Business Analyst → Architect → Developer → QA → Quality Gate → PR — where each role is
performed by an external AI agent runtime (Claude Code, GitHub Copilot, Hermes). It is
the execution environment *around* autonomous engineering agents: task intake, role
orchestration, agent-runtime abstraction, context preparation, tools and role-specific
permissions, artifacts and handoffs, durable execution state in Neon PostgreSQL, worker
sessions, human clarification, pause/resume, feedback loops, independent verification,
Git lifecycle, GitHub interaction, CI execution, and observability/audit history.

Dark Factory does **not** implement another coding agent. The responsibility boundary is:
Dark Factory decides *what happens next*; the engineering agent decides *how* to perform
the engineering work. The outer delivery lifecycle stays under deterministic application
control — it is not one giant LLM loop.

## Core Value

A delivery run is durable: its complete lifecycle state lives in Neon, so any process on
any machine can resume exactly where a previous one stopped — after a crash, a local→CI
handoff, a webhook, or a delayed human answer — and still produce a correct, independently
verified GitHub PR. If the orchestrator cannot explain where a run is, it cannot reliably
resume it; durability and observability are the same requirement.

## Requirements

### Validated

- ✓ Deterministic orchestrator drives a configured ordered role pipeline (not four hardcoded calls) — Phase 3
- ✓ Configurable workflow: `workflow.roles` list can be shortened/reordered without changing orchestrator code — Phase 3
- ✓ `WorkerRegistry` maps `claude-code|copilot|hermes` → adapter; no worker-specific `if` branches leak into the orchestrator — Phase 3 (adapters are placeholders raising `NotImplementedError`; functional adapters land Phase 7/8)
- ✓ Repo config in `.dark-factory.yaml` (version, workflow.roles, repository.base_branch, per-role definition files, quality_gate.commands, retry limits, publishing.create_pr) — Phase 3
- ✓ Role files under `.dark-factory/` (config.yaml, roles/*.yaml, instructions/*.md, examples/) — role behavior editable without touching Python — Phase 3
- ✓ `ActionRegistry` of deterministic pre/post actions referenced by config (`prepare_role_context`, `ensure_clean_worktree`, `collect_diff`, `store_role_artifacts`, `collect_test_results`, …); extensible — Phase 3 (the five built-ins are no-ops until the phases that give them real work: `ensure_clean_worktree`/`collect_diff` in Phase 5, `store_role_artifacts` in Phase 4, `collect_test_results` in Phase 9)
- ✓ Explicit role handoffs happen through durable artifacts, not one shared conversation — Phase 4
- ✓ Business Analyst role: makes the request implementation-ready; outputs `requirements.md`, `acceptance_criteria.json`; read-only on source code — Phase 4
- ✓ Architect role: consumes task + BA output + repo; outputs `design.md`, `constraints.json`; read-only on source code — Phase 4
- ✓ Developer role: implements change, adds/updates tests, runs tests/lint/build, iterates; outputs `implementation_summary.json`; may modify production code and tests — Phase 4
- ✓ QA role: independently verifies each acceptance criterion; may modify tests/fixtures/test utilities only; outputs `test_report.json`, `verdict.json` (machine-readable) — Phase 4
- ✓ `ContextBuilder` produces role-specific `RoleContext` (task, role instructions, relevant prior artifacts, README/AGENTS.md/CLAUDE.md, architecture docs, human answers, constraints, permitted capabilities) — Phase 4
- ✓ Context does not copy the whole repository into prompts — the agent inspects the repo itself — Phase 4
- ✓ Optional few-shot examples referenced from role config are treated as context, not application logic — Phase 4
- ✓ On a retry, the rebuilt context does not leak stale artifacts from a superseded attempt — Phase 4
- ✓ Artifacts stored on the filesystem under `.dark-factory/runs/<run-id>/` (input, artifacts/<role>, verification, logs) — Phase 4
- ✓ Machine-consumed decisions emitted as structured JSON; human docs may be Markdown; JSON contract wins where orchestration depends on it — Phase 4
- ✓ `ArtifactReference` metadata (id, run_id, role_execution_id, type, path, metadata, created_at) stored in Neon; filesystem holds the real content — Phase 4
- ✓ `artifacts` table (metadata only) — Phase 4
- ✓ Run a task from a spec file: `dark-factory run spec:./path.md` — Phase 4
- ✓ Each run has an explicit working branch created from the configured base branch; all roles operate on the same run repository state — Phase 5 (GIT-01)
- ✓ Dark Factory owns delivery actions (create branch, commit, push, create PR); agents never own commit/push/PR policy — Phase 5 (GIT-02)
- ✓ Role-specific tool permissions enforced (write-scope authorization: a role's permitted file-write scope is enforced after execution against path rules from configuration) — Phase 5 (ROLE-05)
- ✓ Artifact content is available to a resuming process on a different machine — commit-per-role onto the run's working branch, proven via cross-clone tests — Phase 5 (ART-04)
- ✓ `ToolRegistry` capability layer with `invoke()` as the single deny-by-default enforcement point; extensible without touching every role executor — Phase 6 (TOOL-01/02, scoped to the 7 `repo.*`/`shell.execute`/`artifacts.*` capabilities; `git.*`/`github.*` deferred to Phase 9/10 per disclosed scope decision)
- ✓ Each role receives only its explicitly configured tools; grants are deny-by-default (BA/Architect read-only on code; Developer write + shell; QA write_tests + shell, no publish) — Phase 6 (TOOL-03)
- ✓ A worker's subprocess environment is built from an explicit allowlist; infrastructure credentials (`DATABASE_URL`, `GITHUB_TOKEN`, worker credentials) are never passed to a worker — Phase 6 (TOOL-04, SEC-03)
- ✓ MCP supported as one optional transport adapter for exposing tools to compatible workers; orchestrator has no internal dependency on MCP — Phase 6 (TOOL-05)
- ✓ Credential/secret values never appear in role artifacts, worker prompts, Neon event payloads, logs, or reports — Phase 6 (SEC-01)
- ✓ `ClaudeCodeWorker` — functional `CodingWorker` adapter registered as `default_registry`'s `"claude-code"` factory (`execute()`, `resume()`, `capabilities()`) — Phase 7
- ✓ `CodingWorker` contract proven for a real runtime: `execute()`, `resume()` (native `--resume <session_id>` when a prior `worker_session_id` exists, context-reconstruction fallback when it doesn't), `capabilities()` reporting `native_resume=True` — Phase 7
- ✓ Any role can be assigned to `claude-code` via config with no workflow-code change (worker registry factory lookup only) — Phase 7
- ✓ Role `context.tools` grants translate into `--allowedTools`, deny-by-omission, via `NATIVE_TOOL_CONTRACT`'s first real runtime consumer — Phase 7 (defense-in-depth; `enforce_write_scope` (ROLE-05) remains the authoritative after-the-fact boundary)
- ✓ CI executes the same quality gates on every push/PR: lint, types, worker-name leak guard, unit/contract tiers — one `.github/workflows/ci.yml`, not a separate CI orchestrator — Phase 7 (verified live: real green run + real red run on a deliberate leak)
- ✓ Attempt logs and resume transcripts pass through one shared spawn/redact/parse pipeline so secret redaction and the never-raise failure wrapper cannot drift between `execute()` and `resume()` — Phase 7
- ✓ `CopilotWorker` is a functional adapter that runs a role non-interactively and returns a normalized result — Phase 8 (WORK-05)
- ✓ `HermesWorker` is a functional adapter that runs a role non-interactively and returns a normalized result — Phase 8 (WORK-06)
- ✓ `CodingWorker` contract proven across all three runtimes (Claude Code — Phase 7; Copilot and Hermes — Phase 8) — shared contract suite pins the invariant across all three, and plan 08-06 additionally executed the full negative/positive proof set against a real PostgreSQL instance for the first time
- ✓ Any role can be assigned to any of the three workers via configuration with no workflow-code change — Phase 8 (WORK-09, ROADMAP SC2: shipped roles reassigned across all three runtimes, run still completes)
- ✓ Each real worker adapter (ClaudeCode, Copilot, Hermes) has its own integration test suite, skipped when the runtime's credentials are absent — Phase 8 (QUAL-03)

### Active

<!-- Milestone 1 = the full technical specification. All hypotheses until shipped. -->

**Task intake**
- [ ] Run a task from plain text: `dark-factory run text:"..."`
- [ ] Run a task from a GitHub issue: `dark-factory run github:152` (title, body, comments, labels, metadata)
- [ ] Deterministic source identification (no LLM needed to classify text vs path vs issue)
- [ ] Normalize every source to one internal `NormalizedTask` model

**Role orchestration**
- [ ] Role definitions are configuration-driven: instructions, tools, permissions, before/after hooks, outputs, worker (instructions/before-after-hooks/outputs/worker shipped Phase 3; write-scope permission enforcement shipped Phase 5 (ROLE-05); tool-capability enforcement shipped Phase 6 (TOOL-01/02/03))

**Worker (agent runtime) abstraction**
- [ ] `WorkerCapabilities` represents runtime differences explicitly (native resume, session id, non-interactive, structured output)
- [ ] `WorkerResult` normalizes every adapter's output (status COMPLETED|NEEDS_INPUT|FAILED, summary, questions, artifacts, changed_files, worker_session_id, metadata)
- [ ] `FakeWorker` for orchestration tests (scripted `WorkerResult` sequence)

**Tools, permissions, security boundary**
- [ ] `git.status/diff/history`, `github.issue.read`, `github.comments.read` capabilities — deferred from Phase 6's `ToolRegistry` scope to Phase 9/10, where Git lifecycle and GitHub integration actually need them

**Durable execution state (Neon PostgreSQL)**
- [ ] Persistence stack: SQLAlchemy + Alembic + PostgreSQL (Neon); `DATABASE_URL` only; no provider-specific logic in orchestration code
- [ ] `runs` table (id, task/source, workflow, status, current_role, current_step, repository, base/working branch, pr_number, pr_url, timestamps)
- [ ] `role_executions` table — one run holds multiple attempts (attempt N, worker, status, worker_session_id, result/error JSONB, timestamps)
- [ ] `human_interactions` table (question, answer, status WAITING|ANSWERED|CANCELLED, timestamps)
- [ ] `run_events` audit trail — every important lifecycle event persisted; the complete execution is reconstructable from persisted data
- [ ] Run states: CREATED, BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING, COMPLETED, WAITING_HUMAN, FAILED; active role stored separately
- [ ] Only Dark Factory mutates orchestration state; a worker returning `NEEDS_INPUT` never directly controls transitions

**Human-in-the-loop, pause & resume**
- [ ] Any role can ask for clarification via the same mechanism
- [ ] Pause: store `WorkerResult` + worker session + human interaction, persist `WAITING_HUMAN`, release execution; the process may terminate safely
- [ ] Resume (local): `dark-factory resume <run-id> --answer "..."` — a brand-new process reconstructs everything from Neon; no in-memory state from the original run required
- [ ] Native worker resume when the adapter supports sessions (opaque `worker_session_id`)
- [ ] Resume by context reconstruction when native resume is unavailable — same external `worker.resume(...)` behavior
- [ ] Cross-process / cross-machine resume works (local → CI, webhook, delayed human answer)
- [ ] Concurrency: two processes must not execute the same run simultaneously — Postgres transactions / row locking / conditional updates; no separate distributed-lock service

**Feedback loops & retry policy**
- [ ] QA FAIL returns a structured issues artifact to the Developer (severity, acceptance_criterion, description)
- [ ] Quality-gate failure returns actual failure output to the Developer, then QA re-evaluates, then the gate re-runs
- [ ] Retry limits from repo config (`retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations`); on exhaustion → `FAILED`, every attempt and reason persisted

**Independent verification (Quality Gate)**
- [ ] After QA passes, Dark Factory independently runs the configured `quality_gate.commands` in the repo environment (e.g. `pytest`, `ruff check .`, `mypy .`)
- [ ] Agent self-validation (Developer/QA running their own tests/lint/build) is preserved and is *not* accepted as final system truth
- [ ] Quality-gate result written to `verification/quality_gate.json`

**Git lifecycle & GitHub integration**
- [ ] Publishing occurs only when QA = PASS **and** Quality Gate = PASS → collect diff, commit, push, create PR, persist PR metadata → COMPLETED
- [ ] GitHub as task source, human-interaction channel (post clarification comment, ingest reply), and publishing destination
- [ ] GitHub event handler: a new issue comment finds the associated run + pending interaction, stores the answer, resumes the same `RoleExecution` (never creates a new run)
- [ ] Idempotency: retrying publishing with an existing `pr_number` does not open a second PR; branch, commit SHA, PR number/URL, clarification comment id persisted

**Triggers: CLI / IDE / CI / GitHub**
- [ ] One orchestration implementation; environments are only triggers — no separate CI orchestrator
- [ ] CLI commands: `run`, `resume`, `status`, `runs`, `artifacts`, and `events`
- [ ] `status <run>` renders run id, task, state, per-role pipeline with worker + attempts, artifacts, human interactions
- [ ] CI can execute the same orchestrator; run continues across the local→CI boundary via Neon

**Configuration**
- [ ] Config resolved at run creation is snapshotted (`runs.workflow`) so a later resume is deterministic even if `.dark-factory.yaml` changed in between (mechanism shipped Phase 3; deterministic resume for real multi-role runs proven Phase 4+)

**Observability & audit**
- [ ] Expose current run state, active role, worker, worker session id, attempt number, role history, artifacts, questions, human answers, quality-gate results, errors, PR info, and state-transition history
- [ ] Important state changes and side effects persisted as events (RUN_CREATED, ROLE_STARTED/COMPLETED/FAILED, ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED, PUBLISH_STARTED, PR_CREATED, RUN_COMPLETED, RUN_FAILED)

**Secrets**
- [ ] `DATABASE_URL`, GitHub credentials, worker credentials never appear in role artifacts, worker prompts, Neon event payloads, GitHub comments, logs, or test reports (unless specifically necessary and sanitized)
- [ ] Worker environments do not inherit the full Dark Factory process environment

**Quality**
- [ ] Orchestration tested with `FakeWorker` (role transitions, artifact handoffs, pause/resume, QA rejection, Developer retries, quality-gate retries, failure limits, publishing) — no external AI calls

### Out of Scope

- **Building another coding agent / autonomous engineering loop** — the engineering agent owns *how* the work is done; Dark Factory only owns *what happens next*
- **A generic arbitrary-DAG workflow engine** — the workflow stays a clear ordered role pipeline with explicit feedback transitions
- **An embedded JavaScript/scripting runtime for actions** — actions are Python implementations referenced by config (DMTools-style extensibility without the JS runtime)
- **A separate CI orchestration implementation** — CI is just another trigger for the one orchestrator
- **A distributed-lock service** — run concurrency is enforced with PostgreSQL transactions / row locking / conditional updates
- **Turning Neon into a document store** — Neon holds state, metadata, and audit references; the filesystem holds artifact content
- **Non-core integrations (Confluence, Jira, TestRail, Figma, Teams, Slack, Azure DevOps, GitLab)** — the integration layer must make these addable later without changing core orchestration, but none ship in Milestone 1

## Context

- **Language / stack:** Python. Neon PostgreSQL via SQLAlchemy + Alembic. YAML config. CLI is the primary interface; IDE / CI / GitHub are additional triggers.
- **Agent runtimes targeted:** Claude Code, GitHub Copilot, Hermes — all three get real adapters in Milestone 1. Access to the Copilot and Hermes CLIs is required to run their integration tests; the `WorkerCapabilities` model and per-adapter integration test suites exist precisely because the three runtimes are not identical.
- **Reference project structure** is given in the spec (§72): `dark_factory/` with `orchestrator/`, `workflows/`, `roles/`, `workers/`, `tools/`, `actions/`, `input/`, `context/`, `artifacts/`, `quality/`, `persistence/`, `integrations/`, `workspace/`, `events/`.
- **Prior art:** intentionally adopts DMTools patterns (configurable roles, instructions, tool abstraction, role-specific capabilities, pre/post processing, artifacts, external AI workers, CI execution, integration abstraction) but organizes everything around the central abstraction of a **durable delivery run**.
- **Guiding principle for "where does this belong?"** (spec §83): decides what happens next → Orchestrator/Workflow; defines an engineering responsibility → Role; decides how work is done → Worker; provides an operation → Tool; carries durable info between roles → Artifact; records where execution is → Neon state; decides if the result is acceptable → QA/Quality Gate; talks to an external service → Integration.
- **Repo state:** greenfield. Fresh git repository, no application code yet. A leftover `seed-app-new.sh` (an unrelated VibeGuard test-repo seeder) is present and not part of this project.
- **Full technical specification** provided by the user is the authoritative scope reference (84 sections). This PROJECT.md summarizes it; the spec governs on any detail conflict.

## Constraints

- **Tech stack**: Python + Neon PostgreSQL + SQLAlchemy + Alembic — from the spec; application logic treats Neon as plain PostgreSQL and provider-specific logic must not leak into orchestration code.
- **Architecture**: Deterministic outer lifecycle — the delivery pipeline must not become one LLM loop; agents have freedom only *inside* engineering work.
- **Architecture**: Role ≠ Worker — any role assignable to any worker with zero workflow-code change; no `if worker == "claude"` branching in the orchestrator.
- **Security**: Infrastructure credentials (`DATABASE_URL`, `GITHUB_TOKEN`, worker creds) must never reach workers, artifacts, prompts, event payloads, comments, logs, or reports.
- **Durability**: Every lifecycle state and side effect persisted; a run must survive process termination, machine change, and delayed human response, and be fully reconstructable from Neon.
- **Idempotency**: External side effects (branch, push, PR, GitHub comment) must be retry-safe via persisted identifiers.
- **Publishing policy**: PR creation only after QA PASS *and* independent Quality Gate PASS.
- **Compatibility**: The workflow definition, tool registry, action registry, worker registry, and integration layer must all accept new entries without modifying the core orchestrator.
- **Quality bar**: Portfolio-showcase quality *and* genuinely runnable against a real repository.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Milestone 1 = the entire technical specification (all 4 roles, all 3 real workers, all 3 task sources, full GitHub + CI, durable resume, human-in-loop, quality gate, PR publishing) | User wants the complete system as the first milestone, not a thin slice | — Pending |
| All three worker adapters (Claude Code, Copilot, Hermes) are functional in v1, not stubs | User selected "All three"; proves worker-independence with three real examples | — Pending |
| `FakeWorker` is a first-class deliverable for orchestration testing | Spec §74; lets lifecycle behavior be tested without external AI systems | — Pending |
| All three task sources (text, spec file, GitHub issue) in v1 | User selected all; `github:` also unlocks the GitHub human-interaction + resume path | — Pending |
| Portfolio-quality **and** runnable on a real repo | User selected "Both" | — Pending |
| Config snapshot reuses the existing `runs.workflow` JSONB column instead of a new `config_snapshot` column | Zero migration; column already redacted-on-write and loaded on every resume; avoids an Alembic `0004` for a value the reused column already handles | Shipped Phase 3 |
| `.dark-factory.yaml` `workflow.roles` entries are `RunStatus` values (`BA`, `ARCHITECTURE`, …), not human names | Keeps `transition()`/`answers.py` untouched — no name→status mapping to maintain | Shipped Phase 3 |
| PyYAML approved as the YAML parser (`yaml.safe_load` only) | ~19-year-old package, MIT, source `github.com/yaml/pyyaml`, CLAUDE.md-pinned; automated legitimacy verdict was `SUS` only on a missing-downloads-metric technicality | Shipped Phase 3 |
| Neon holds state + metadata + audit references only; filesystem holds artifact content | Spec §28–29; keeps Neon from becoming a document store | Shipped Phase 4 |
| Config-driven role pipeline over hardcoded role calls | Spec §5; enables shorter/reordered pipelines without orchestrator rewrites | — Pending |
| MCP is an optional tool transport, never an internal dependency | Spec §70 | — Pending |
| Zero-config artifact synthesis derives every downstream criterion id from the role's resolved `context.inputs` (structural validation, then a Markdown carrier-line regex) rather than any hardcoded literal — dispatch stays on content shape only, never `context.role` | UAT gap G-04-1: `FakeWorker`'s placeholder synthesis had two independent hardcoded ids that only coincidentally matched, so renaming one didn't move the other; regression tests now compare against the origin artifact's own emitted ids, never a fixed expectation, so a reintroduced hardcode fails the test the way the original defect would have | Shipped Phase 4 (plan 04-05) |
| On COMPLETED, the run driver commits any trailing worktree content onto the run's working branch (via `wip_commit_if_dirty`, which stages untracked files) *before* deleting the worktree — the working branch, not the worktree filesystem, is the durable record D-04 guarantees | UAT gap G-05-1: the SC4 in-scope-edit test asserted against the worktree filesystem, a location D-04 deliberately deletes after COMPLETED — a test defect, not a product bug. Root cause: `.planning/debug/in-scope-edit-missing-after-completed.md` | Shipped Phase 5 (plan 05-05); zero production changes |
| CR-02's `revert_paths` escape-ordering fix needed unit-tier coverage with no database — the scope module never touched Postgres, but its tests were partitioned "pure functions only" vs. "full pipeline behind a DB fixture," leaving no DB-free home and letting a Critical review fix ship with zero executed coverage | UAT gap G-05-2: `tests/unit/test_write_scope_revert.py` added as a new DB-free unit-tier home (mirroring `test_git_lifecycle.py`'s real-git-on-`tmp_path` pattern), proving escape-first/last/only/multiple cases directly against `revert_paths` and `enforce_write_scope`. Root cause: `.planning/debug/cr02-revert-ordering-test-gap.md` | Shipped Phase 5 (plan 05-06); zero production changes |
| `ToolRegistry.invoke()` is the single deny-by-default enforcement point every capability call and every transport (MCP included) funnels through — never a second permission check at the transport layer | Spec's tool-permission-as-security-boundary requirement (TOOL-03); keeps the grant check in exactly one place so a new transport can't accidentally bypass it | Shipped Phase 6 |
| `build_worker_env` is additive-from-empty-dict over an explicit allowlist, never `os.environ.copy()`/spread/exclusion-filter | CLAUDE.md's explicit "What NOT to Use" prohibition on `os.environ.copy()` when spawning workers — the credential boundary must be constructive, not subtractive | Shipped Phase 6 (TOOL-04, SEC-03) |
| Three long-standing "pre-existing, unrelated" test failures (phase-4/5 git-worktree/artifact-commit mechanics) were a stale-fixture defect, not a product bug — each test declared its role's `write_scope: []` (D-14 zero-tolerance deny-all) while its own worker planted a non-artifact file in the worktree, and write-scope enforcement correctly reverted it | Root cause: `.planning/debug/resolved/phase4-artifact-commit-bugs.md`. The detection gate (db/integration tier) worked and reported it correctly for two phases; the response gate did not — it was triaged as pre-existing/unrelated and carried as an accepted baseline instead of investigated | Fixed at Phase 6 close-out (commit `ffc333f`); zero production changes |
| `execute()` and `resume()` both route through one shared `_spawn_and_parse` pipeline rather than each owning its own spawn/redact/parse logic | Prevents secret redaction or the never-raise failure wrapper from drifting between entry points as the adapter grows | Shipped Phase 7 (plan 07-03) |
| `NEEDS_INPUT:` is a trusted model-authored marker (D-01) that lets the agent itself select the pause branch, accepted rather than requiring structured (`--json-schema`) output for this phase | Worst case of a false positive is a spurious human-resolved pause, not privilege escalation; structured-output hardening deferred to a future phase (recorded in 07-RESEARCH.md) | Shipped Phase 7 (plan 07-03); threat T-07-11 accepted |
| `--allowedTools` is built strictly from `context.tools` with deny-by-omission as defense-in-depth, while `enforce_write_scope` (ROLE-05) remains the sole authoritative after-the-fact boundary | A role without a grant should not even present the native tool to the agent, but the post-hoc scope check is what actually can't be bypassed by a misbehaving worker | Shipped Phase 7 (plan 07-04) |
| CI's `quality` job holds no secrets and skips the `db`/`integration` tiers entirely, rather than provisioning a throwaway Postgres in the hosted runner | Nothing to leak if there's nothing to leak; `db`/`integration` tiers verified manually against a real backend instead (this UAT: 828 passed, 56m22s) | Shipped Phase 7 (plan 07-02); threat T-07-09 accepted, revisit at Phase 8 credential-gated integration jobs |
| `enforce_artifact_scope` confines a role's `artifacts.write` grant to its own `artifacts/<role>/` subtree — a narrower, orchestrator-side, worker-agnostic control distinct from `enforce_write_scope` (ROLE-05's repo-wide boundary) — because Copilot's and Hermes's native tool surfaces expose no path-scoped read/write specifier to narrow at the adapter level | CR-01 (08-REVIEW.md): a granted `artifacts.write`, once native-tool-confined only by each adapter's own (uneven) capability, let one role overwrite another's committed artifact. Deny-by-default over the whole tree when the role holds no `artifacts.write` grant at all, matching D-14's zero-tolerance polarity | Shipped Phase 8 (plan 08-05); proven negatively on both Hermes and Copilot, positively on the untampered control |
| A shared test harness's exit-code expectation must be stated per-caller with no default, never inherited from whichever caller was written first | G-08-2 (08-REVIEW.md, `.planning/debug/cli-exit-code-on-failed-run.md`): `_drive_shipped_config` asserted a positive-path exit code unconditionally, contradicting the two negative-path tests it also served — committed and never executed against a real database, so the contradiction shipped silently | Fixed Phase 8 (plan 08-06); zero production change, `src/dark_factory/cli.py`'s D-05 mapping unchanged |
| A `FakeWorker`-scripted multi-role fixture must write each role's artifact files at `execute()` time, never all up front | Front-loading (the original `four_role_script` shape) is invisible to `enforce_write_scope`/exit-code checks but trips `enforce_artifact_scope` (08-05) the moment it exists: a later role's not-yet-run files are already on disk when an earlier role's own scope check runs. `LazyFourRoleWorker` is now the shared pattern for any db test driving a real multi-role `drive()` call | Found and fixed Phase 8 (plan 08-06, out of that plan's declared scope, fixed at user request); `tests/db/test_artifact_commit_per_role.py` had already independently discovered the same fix for the same reason |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-22 after Phase 8*
