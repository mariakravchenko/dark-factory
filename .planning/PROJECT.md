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
- ✓ After QA passes, Dark Factory independently runs the configured `quality_gate.commands` in the repo environment; agent self-validation is preserved but never accepted as final system truth — Phase 9 (GATE-01, GATE-02, GATE-03)
- ✓ Quality-gate result written to `verification/quality_gate.json`, redacted against known secrets in both captured output and the command string itself (CR-02) — Phase 9 (GATE-04)
- ✓ QA FAIL returns a structured issues artifact to the Developer; quality-gate FAIL returns the real command failure output; both feed the Developer's next attempt via `optional_inputs`/`ContextBuilder` — Phase 9 (LOOP-01, LOOP-02)
- ✓ Retry limits from repo config (`retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations`) checked before dispatch; on exhaustion the run transitions to `FAILED` with every attempt and reason persisted — Phase 9 (LOOP-03, LOOP-04)
- ✓ Run a task from a GitHub issue: `dark-factory run github:<n>` (title, body, comments, labels; `source_ref`/`metadata` populated) — Phase 10 (INTAKE-03)
- ✓ Publishing occurs only when QA = PASS **and** Quality Gate = PASS → collect diff, commit, push, create exactly one PR, persist PR metadata → COMPLETED — Phase 10 (GIT-03), proven against real GitHub (a real PR opened at `mariakravchenko/app-new#10` during manual UAT)
- ✓ Idempotency: retrying publishing with an existing `pr_number`/`pr_url`/`published_commit_sha` does not open a second PR (three-way persisted-identifier fast path); a crash between GitHub-side create and the identity commit is recovered by a head-branch-scoped existence check before every create — Phase 10 (GIT-04)
- ✓ GitHub as human-interaction channel: a role reaching `NEEDS_INPUT` posts a clarification comment on the source issue, threaded by a persisted comment id so a resume never re-posts — Phase 10 (GIT-05)
- ✓ GitHub webhook receiver: verifies the inbound signature before any parse (fail-closed on an unset secret), resolves a reply comment to its pending interaction (never Dark Factory's own posted comment, never redelivery-duplicated), and calls `submit_answer` in-process — the same lease/transaction path `resume --answer` uses — Phase 10 (GIT-06)
- ✓ CLI commands `run`, `resume`, `status`, `runs`, `artifacts`, and `events` all shipped; `status <run>` renders run id, task, state, per-role pipeline with every attempt (not just the latest), artifacts, and human interactions — Phase 12 (TRIG-03)
- ✓ Full event catalog (20 members) covers every state change and side effect the spec names: RUN_CREATED/COMPLETED/FAILED, ROLE_STARTED/COMPLETED/FAILED/BOUNCED, ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED/RESUMED, HUMAN_ANSWER_RECEIVED, QA_PASSED/FAILED, QUALITY_GATE_STARTED/PASSED/FAILED, PUBLISH_STARTED/FAILED, PR_CREATED, WIP_COMMIT_CREATED, CAPABILITY_DENIED — Phase 12 (OBS-02; ARTIFACT_CREATED and QA_PASSED/QA_FAILED were the final two additions)
- ✓ Operator-facing read surface exposes run state, active role, worker, worker session id, attempt number, full role history, artifacts (including committed content via `git show`), questions, human answers, quality-gate results, errors, and PR info — Phase 12 (OBS-01)
- ✓ Credential/secret values never appear in role artifacts, worker prompts, Neon event payloads, GitHub comments, logs, or reports — re-proven end-to-end by a whole-pipeline sweep across every sink (real intake → human pause/resume → real `ClaudeCodeWorker` → quality gate → published PR), which also found and fixed one real gap: artifact file content was not scrubbed before commit — Phase 12 (TRIG-02; closes SEC-01 for the artifact-content sink)
- ✓ Run a task from plain text — `dark-factory run text:"..."`; deterministic source classification with no LLM call; every source normalized to one `NormalizedTask` model — Phase 1 (INTAKE-01, INTAKE-04, INTAKE-05)
- ✓ `WorkerCapabilities` represents runtime differences explicitly; every adapter normalizes output to one `WorkerResult`; a scripted `FakeWorker` needs no external AI call — Phase 1 (WORK-07/08/10)
- ✓ Persistence stack is SQLAlchemy + Alembic + PostgreSQL (Neon), `DATABASE_URL` only, no provider-specific logic; `runs` / `role_executions` / `run_events` tables; the ten-value run-status enum with active role stored separately; only the orchestrator mutates lifecycle state; the complete execution of a run is reconstructable from persisted data alone — Phase 1 (STATE-01/02/03/06/07/08, ORCH-05/06)
- ✓ `human_interactions` table (question, answer, status WAITING|ANSWERED|CANCELLED) — Phase 2 (STATE-04)
- ✓ Any role can ask for clarification through one identical mechanism; pause persists the worker result, session, and interaction, then releases the process safely; `dark-factory resume <run-id> --answer "..."` reconstructs everything from Neon in a brand-new process; native-session resume and context-reconstruction resume both call the same `worker.resume(...)`; cross-process/cross-machine resume works; two processes cannot execute the same run simultaneously, enforced by Postgres claim-don't-check leasing with no distributed-lock service — Phase 2 (HITL-01 through HITL-08)
- ✓ One orchestration implementation; CLI, webhook and CI are only triggers with no separate CI orchestrator; a run continues across the local→CI boundary through Neon alone — Phase 11 (TRIG-01, TRIG-04, HITL-06)
- ✓ Orchestration is tested end-to-end with `FakeWorker` — role transitions, artifact handoffs, pause/resume, QA rejection, Developer retries, quality-gate retries, failure limits, publishing — with no external AI calls, and the suite runs green in CI — Phase 1 + Phase 11 (QUAL-01)
- ✓ `git.status/diff/history`, `github.issue.read`, `github.comments.read` capabilities, deferred from Phase 6's initial `ToolRegistry` scope — shipped where Git lifecycle and GitHub integration actually need them — Phase 9/10 (TOOL-01 extended scope)
- ✓ Worker subprocess environments never inherit the full Dark Factory process environment — the Phase 6 allowlist mechanism (TOOL-04/SEC-03), re-confirmed clean by Phase 12's whole-pipeline secret sweep — Phase 6 + Phase 12

### Active

v2 scope — deferred, tracked, not in the v1.0 roadmap. Promote to Validated (with a phase reference) the milestone each ships.

- [ ] **INTG-01**: Confluence / Jira / TestRail / Figma / Teams / Slack / Azure DevOps / GitLab as task sources, context providers, tools, artifact stores, human-interaction channels, or publishing targets — the integration layer must make these addable without changing core orchestration
- [ ] **OBS-V2-01**: Real-time web dashboard for run monitoring (CLI `status`/`events` is the v1 surface)

### Out of Scope

- **Building another coding agent / autonomous engineering loop** — the engineering agent owns *how* the work is done; Dark Factory only owns *what happens next*
- **A generic arbitrary-DAG workflow engine** — the workflow stays a clear ordered role pipeline with explicit feedback transitions
- **An embedded JavaScript/scripting runtime for actions** — actions are Python implementations referenced by config (DMTools-style extensibility without the JS runtime)
- **A separate CI orchestration implementation** — CI is just another trigger for the one orchestrator
- **A distributed-lock service** — run concurrency is enforced with PostgreSQL transactions / row locking / conditional updates
- **Turning Neon into a document store** — Neon holds state, metadata, and audit references; the filesystem holds artifact content
- **Durable-workflow engine (Temporal / Prefect / Celery)** — overkill for a short human-speed pipeline; hand-rolled enum FSM with Neon checkpoints instead
- **Async SQLAlchemy / async orchestrator core** — one run at a time, blocking on multi-minute agent subprocesses; async adds function-coloring and pooling hazards for zero throughput gain
- **Trusting agent transcripts / self-reports as verification truth** — the independent quality gate re-runs the repo's real commands and decides on exit codes
- **Agents owning git / PR operations** — publishing policy stays out of autonomous agents
- **Copying the whole repository into prompts** — the agent inspects the repo itself; context is role-scoped
- **Multi-agent chat negotiation between roles** — roles hand off through durable artifacts, not a shared conversation
- **Auto-merging a PR on a green quality gate** — Dark Factory opens the PR; a human merges
- **Worker eval / benchmark harness** — not part of the delivery-orchestration core
- **Non-core integrations (Confluence, Jira, TestRail, Figma, Teams, Slack, Azure DevOps, GitLab)** — the integration layer must make these addable later without changing core orchestration; tracked as v2 requirement INTG-01, none ship in Milestone 1

## Current State (after v1.0)

Shipped 2026-10-26. 12/12 phases complete, all 89 v1 requirements validated. ~62,000 lines of Python across `src/` and `tests/` (224 test files, unit/contract/db/integration tiers), 681 commits over 50 days. Proven end-to-end against a real external repository (`mariakravchenko/app-new#10`) during Phase 10 UAT, not just against fixtures.

**Known tech debt (acknowledged, not blocking):**
- ~24 leftover git worktrees/branches from earlier phase testing sit in `dark-factory-runs/`; safe to `git worktree prune` once confirmed.
- `ruff format` drift across ~19 pre-existing files outside recent plans' scope.
- The optional `mcp` extra is not installed by default, producing 2 benign mypy `import-not-found` errors on `tools/mcp_transport.py` unless `uv sync --all-extras --dev` is run.
- `tests/db/test_status_from_columns.py::test_read_status_performs_no_write` counts DB rows globally rather than scoped to its own `run_id`, so it can flake under concurrent test runs against the shared external Postgres rung.

## Context

- **Language / stack:** Python. Neon PostgreSQL via SQLAlchemy + Alembic. YAML config. CLI is the primary interface; IDE / CI / GitHub are additional triggers.
- **Agent runtimes targeted:** Claude Code, GitHub Copilot, Hermes — all three shipped real adapters in v1.0. Access to the Copilot and Hermes CLIs is required to run their integration tests; the `WorkerCapabilities` model and per-adapter integration test suites exist precisely because the three runtimes are not identical.
- **Reference project structure** is given in the spec (§72): `dark_factory/` with `orchestrator/`, `workflows/`, `roles/`, `workers/`, `tools/`, `actions/`, `input/`, `context/`, `artifacts/`, `quality/`, `persistence/`, `integrations/`, `workspace/`, `events/`.
- **Prior art:** intentionally adopts DMTools patterns (configurable roles, instructions, tool abstraction, role-specific capabilities, pre/post processing, artifacts, external AI workers, CI execution, integration abstraction) but organizes everything around the central abstraction of a **durable delivery run**.
- **Guiding principle for "where does this belong?"** (spec §83): decides what happens next → Orchestrator/Workflow; defines an engineering responsibility → Role; decides how work is done → Worker; provides an operation → Tool; carries durable info between roles → Artifact; records where execution is → Neon state; decides if the result is acceptable → QA/Quality Gate; talks to an external service → Integration.
- **Usage model** (confirmed during Phase 10 UAT): Dark Factory is installed as a standalone CLI tool and run from *inside* the target repository's own local checkout — `.dark-factory.yaml`, `.env`, and all git/worktree operations resolve against `Path.cwd()`, never against wherever Dark Factory's own source lives.
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
| Milestone 1 = the entire technical specification (all 4 roles, all 3 real workers, all 3 task sources, full GitHub + CI, durable resume, human-in-loop, quality gate, PR publishing) | User wants the complete system as the first milestone, not a thin slice | ✓ Shipped v1.0 |
| All three worker adapters (Claude Code, Copilot, Hermes) are functional in v1, not stubs | User selected "All three"; proves worker-independence with three real examples | ✓ Shipped v1.0 (Phase 7/8) |
| `FakeWorker` is a first-class deliverable for orchestration testing | Spec §74; lets lifecycle behavior be tested without external AI systems | ✓ Shipped v1.0 (Phase 1) |
| All three task sources (text, spec file, GitHub issue) in v1 | User selected all; `github:` also unlocks the GitHub human-interaction + resume path | ✓ Shipped v1.0 (Phases 1/4/10) |
| Portfolio-quality **and** runnable on a real repo | User selected "Both" | ✓ Shipped v1.0 — proven against a real external repo (`mariakravchenko/app-new#10`) during Phase 10 UAT |
| Config snapshot reuses the existing `runs.workflow` JSONB column instead of a new `config_snapshot` column | Zero migration; column already redacted-on-write and loaded on every resume; avoids an Alembic `0004` for a value the reused column already handles | Shipped Phase 3 |
| `.dark-factory.yaml` `workflow.roles` entries are `RunStatus` values (`BA`, `ARCHITECTURE`, …), not human names | Keeps `transition()`/`answers.py` untouched — no name→status mapping to maintain | Shipped Phase 3 |
| PyYAML approved as the YAML parser (`yaml.safe_load` only) | ~19-year-old package, MIT, source `github.com/yaml/pyyaml`, CLAUDE.md-pinned; automated legitimacy verdict was `SUS` only on a missing-downloads-metric technicality | Shipped Phase 3 |
| Neon holds state + metadata + audit references only; filesystem holds artifact content | Spec §28–29; keeps Neon from becoming a document store | Shipped Phase 4 |
| Config-driven role pipeline over hardcoded role calls | Spec §5; enables shorter/reordered pipelines without orchestrator rewrites | ✓ Shipped v1.0 (Phase 3) |
| MCP is an optional tool transport, never an internal dependency | Spec §70 | ✓ Shipped v1.0 (Phase 6) |
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
| `enforce_write_scope`'s guard widened to fire on both `Signal.ROLE_COMPLETED` and `Signal.ROLE_BOUNCED` (one call site, not a parallel second check) | CR-01 (09-REVIEW.md): the guard originally covered only completion, so a bounced attempt's out-of-scope write bypassed the ROLE-05 authorization boundary entirely | Shipped Phase 9 (plan 09-04); proved by `tests/db/test_write_scope_enforced_on_bounce.py` |
| `run_quality_gate`'s command-text field is redacted identically to its stdout/stderr, at construction time, before `GateCommandResult` exists | CR-02 (09-REVIEW.md): only the two output streams were redacted; a secret embedded in the configured command string itself reached the committed `quality_gate.json` unredacted | Shipped Phase 9 (plan 09-05); single choke point, no second redaction call site |
| The Developer's attempt-2 `RoleContext` rebuild in test fixtures must derive the run's worktree via `ensure_worktree(base_branch, working_branch)` from the freshly loaded `RunState`, never from a pre-computed `repo_root` | G-09-6/G-09-7: `_CapturingWorker` passed the config repo root instead of the git worktree to `build_role_context`, making LOOP-01/LOOP-02's db-tier proofs unconditionally red for a whole phase — a test-fixture defect, zero production impact (`runner.py:866` always passed the correct value). Root cause: `.planning/debug/resolved/g-09-6-and-g-09-7-missing-architecture-design-md.md` | Fixed Phase 9 (plan 09-06); new DB-free AST guard (`tests/unit/test_role_context_rebuild_uses_the_worktree.py`) restores detection; behaviorally confirmed against real PostgreSQL 17 (2 passed) |
| `source_ref = "{owner}/{repo}#{issue_number}"` and `metadata = {owner, repo, issue_number, labels, comment_count}` for a GitHub-sourced run, rather than a bare URL or dedicated `runs` columns | 10-RESEARCH.md Open Question 2 / Task 2 checkpoint option A1: human-legible in `status`/`RUN_CREATED`, and the webhook resolver queries typed `metadata` fields with no string parsing or API-host coupling; avoids `runs`-table columns that every non-GitHub source would carry as permanent NULLs | Shipped Phase 10 (plan 10-01) |
| The webhook receiver's own mutation is exactly `submit_answer`, in-process, never `advance`/`drive` — enforced by two AST import-closure guards (no `advance`/`drive` reachable under `src/dark_factory/webhook/`; `dark_factory.webhook` unreachable from the orchestrator core) | GIT-06/D-01/D-02: the receiver is the first unauthenticated network edge in the codebase; a request must never be able to hold a lease for a role's duration or spawn a worker subprocess | Shipped Phase 10 (plans 10-04, 10-05) |
| Four real-CLI-subprocess integration tests copying the shipped `.dark-factory.yaml` verbatim into a throwaway repo must neutralize `quality_gate.commands` and `publishing.create_pr` through one shared harness, not per-test ad hoc fixes | G-10-1 root cause: the shipped config's `quality_gate.commands` (`uv run pytest -q`) has no meaning in a throwaway repo with no Python project — exit 5 every attempt, QA↔DEVELOPMENT bounces to exhaustion, run terminates FAILED, masking whether the actual publish/intake path works at all. Two independent test-only defects (a LOOP-04 test reading the wrong event field, an over-broad redaction-guard assertion) surfaced in the same diagnosis. Root cause: `.planning/debug/qa-gate-exhausts-bounces-terminates-failed.md` | Fixed Phase 10 (gap-closure plans 10-07/10-08); zero production changes; independently re-verified (808/808 unit+contract, then 1171/1171 full sweep against real Postgres in manual UAT) |
| Dark Factory is installed as a standalone CLI tool (`uv tool install`) and run from *inside* the target repository's own local checkout — `.dark-factory.yaml`, `.env`, and all git/worktree operations resolve against `Path.cwd()`, never against wherever Dark Factory's own source lives | Discovered during live UAT: `repo_root` defaults to `Path.cwd()` throughout `orchestrator/runner.py`, so running `dark-factory` from inside its own checkout while pointing its own `.dark-factory.yaml` at a different GitHub repo would branch/commit/push against Dark Factory's *own* git history, not the target repo's. Confirmed the correct usage model (own checkout + `.env` per target repo, tool installed once) by setting up and successfully running a real end-to-end delivery against a separate repo (`mariakravchenko/app-new`, PR #10) | Confirmed Phase 10 UAT; not a code change, a usage-model clarification worth documenting before Phase 11 (cross-machine resume) or a README "getting started" section |
| `scrub_artifact_text_in_place` redacts artifact file content before it is ever committed, as its own call site ahead of `collect_role_artifacts` | Found by Phase 12's whole-pipeline secret sweep (plan 12-07): every other D-08 sink (events, logs, comments, quality-gate output) was already redacted, but artifact *file content* itself was not — a worker could commit a credential literal straight into a tracked file and it would reach the PR diff unredacted. A real production gap, not a test defect | Shipped Phase 12 (plan 12-07) |
| `dark_factory.git`'s error hierarchy lives in a standalone leaf module (`git/errors.py`), imported by both `git/__init__.py` and `observability/run_detail.py` | Phase 12's package-wide "observability imports no orchestration internals" sweep (`test_observability_import_graph.py`) would otherwise trip the moment `run_detail.py` needed `GitError` from the `git` package's main namespace | Shipped Phase 12 (plan 12-06); zero behavior change |
| A unit test's global `get_settings()` read must never be allowed to succeed on ambient developer credentials — three production call sites (`logging.py`, `publish.py`, `runner.py`) needed either a settings-injection seam or test-side patching, closing a class where CI (no `.env`) and local dev (`.env` present) silently diverge | G-11-3: 12 unit/contract tests crashed only in real CI because a CWD-relative `.env` silently supplied `DATABASE_URL` locally; a second, worse instance (`tests/support/live_runtime.py`'s `credential_missing`) aborted collection entirely the moment agent CLIs were on PATH. Root cause: `.planning/debug/resolved/ci-unit-tier-settings-validation-g-11-3.md` | Shipped Phase 11 (gap-closure plan 11-09); a recurrence guard (`tests/unit/test_unit_tier_needs_no_database.py`) reproduces CI's exact selector in a sanitized child process |
| A CI exclusion rationale encoded as BOTH a prose comment AND an executable test assertion becomes self-sealing — fixing it looks like breaking CI, which is why it survives for phases | `.github/workflows/ci.yml` excluded the whole `integration` tier citing "no agent-CLI credentials," while `test_qual01_ci_coverage.py` asserted `not selects_integration`. The premise went false once the three credential-requiring modules got their own `skipif` guards, but nobody could fix it without the assertion flagging red. Measured: only 3 of 193 integration tests need real credentials, and they already skip cleanly. Root cause: `.planning/debug/resolved/integration-tier-excluded-from-ci-credential-free-tests-could-run.md` | Milestone-close fix: `ci.yml` gained a plain `-m integration` job; the forbidding assertion inverted into an enforcing one scanning all jobs, not just `quality`; first real hosted-runner confirmation accepted as residual risk, backfill `timeout-minutes` after the first green run |
| A test asserting a positive-path exit code inside a SHARED harness that also serves negative-path callers is a latent defect waiting for its first execution — give the parameter no default | Two independent instances of this exact class: (1) `test_artifact_scope_enforcement.py`'s `_drive_shipped_config` hardcoded `== 0`, breaking its two tamper/negative callers the first time they ran against a real database (G-08-2); (2) a second occurrence surfaced again at milestone close with the identical shape. Both fixed by making `expected_exit` a required keyword-only parameter, no default, so a future caller cannot silently inherit the wrong expectation | Shipped Phase 8 (plan 08-06) and re-verified at milestone close; `tests/integration/test_exit_codes.py` remains the authoritative D-05 contract guard |
| `FakeWorker`'s zero-config artifact synthesis must thread `context.inputs` through to every downstream artifact, never dispatch on filename alone | Milestone-close debug session found the one BA→QA `AC-1` id "handoff" that looked correct was two independent hardcoded literals coincidentally matching — `verdict.json`'s criterion id never actually derived from `acceptance_criteria.json`. Fixed by extracting criterion ids from upstream content (structural-then-textual) rather than hardcoding. Root cause: `.planning/debug/resolved/fakeworker-placeholder-artifacts.md` | Milestone-close fix; `tests/integration/test_real_pipeline_zero_config.py` now asserts BA's ids reach every downstream artifact |
| A git/filesystem-free module's test coverage must live at the unit tier even when its only tests today are reachable through a DB-bound integration path — partition by what the code *needs*, not by what currently calls it | CR-02's `revert_paths` escape-ordering fix shipped with zero executed regression coverage because its only test path ran through a DB-gated integration harness, and the module itself documents "no database access anywhere." A DB-free unit-tier home (`tests/unit/test_write_scope_revert.py`) already had an established sibling pattern (`test_git_lifecycle.py` et al.) that nobody used for this module. Root cause: `.planning/debug/resolved/cr02-revert-ordering-test-gap.md` | Shipped Phase 5 (plan 05-06) and re-verified at milestone close; revert-check against pre-fix code produces 3/7 failures, proving the suite discriminates |
| A real, previously-unexecuted test asserting on-disk content after a run reaches `COMPLETED` must read from the working branch, never the worktree filesystem D-04 deletes | Same defect class recurred twice (G-05-1, shipped Phase 5; reconfirmed at milestone close with an identical "mutant restores the exact original error" proof) — the design decision was always correct, only the test's medium was wrong | Shipped Phase 5 (plan 05-05) and re-verified at milestone close against real PostgreSQL 17 |

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
*Last updated: 2026-10-26 after v1.0 milestone*
