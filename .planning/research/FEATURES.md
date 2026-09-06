# Feature Research

**Domain:** Delivery-orchestration platform for autonomous engineering agents (the execution environment *around* coding agents — intake, role orchestration, durable state, verification, Git/GitHub lifecycle)
**Researched:** 2026-09-06
**Confidence:** MEDIUM (scope items derived from PROJECT.md are HIGH; competitor comparisons rest on secondary/blog + vendor-doc sources, MEDIUM)

---

## Orientation: what class of product this is

Dark Factory is not a coding agent. It is the deterministic outer lifecycle that hires coding agents (Claude Code, Copilot, Hermes) to do bounded engineering work and is judged on whether a run **survives a crash, a machine change, and a delayed human answer and still produces a correctly verified PR**. The feature bar therefore splits three ways:

- **Table stakes** — every credible agent-delivery tool (Devin, GitHub Copilot coding agent, OpenHands, CI PR bots, DMTools) already does these. Missing any one makes Dark Factory look like a toy.
- **Differentiators** — the durable-run thesis, role≠worker independence, the credential boundary, and independent verification. These are exactly where the named competitors are weak or absent.
- **Anti-features** — things adjacent tools do that create rewrites, unauditable behaviour, or scope explosion. The spec already names several; research confirms more.

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Task intake from more than one source (plain text, spec file, GitHub issue) | Copilot coding agent takes issues; Devin takes chat/Slack; every tool takes *something*. A single hard-coded input format reads as a prototype. | MEDIUM | Deterministic source classification (`text:` / `spec:` / `github:` prefix + shape checks) — no LLM. Normalize all three to one `NormalizedTask`. GitHub issue intake pulls title, body, comments, labels, metadata. |
| Decompose the work into phases/roles rather than one prompt | Copilot "plans the work" before coding; Devin plans then executes; users expect a plan step, an implementation step, and a check step. | MEDIUM | Dark Factory's BA→Architect→Developer→QA is a richer version of the same expectation. The minimum credible decomposition is plan / build / verify. |
| Agent runs the repo's own tests, linters, and build during implementation | Copilot "runs automated tests and linters if present, updating tests as needed"; OpenHands iterates "until tests pass". | LOW-MEDIUM | This is *agent self-validation*. Table stakes to do it; a differentiator (below) to not trust it as final truth. |
| Isolated workspace per run (branch + clean worktree) | Agents must not clobber each other or the user's working tree. Copilot pushes only to `copilot/*` branches. | MEDIUM | Explicit working branch from a configured base; all roles share one run repo state; `ensure_clean_worktree` style pre-action. |
| Platform owns Git lifecycle (branch, commit, push) and opens the PR | Copilot, Devin, Sweep/Codegen-style bots all end at "here is a PR". Users expect a reviewable PR, not a patch file or a dirty worktree. | MEDIUM | Agents must *not* own commit/push/PR policy — see differentiators + anti-features. |
| Human review gate before merge; revise-on-feedback loop | Copilot "tags you for review… revises the PR and keeps going until you approve"; four-eyes enforced (assigner ≠ approver). | MEDIUM | Dark Factory keeps the human as PR reviewer; it never auto-merges. Clarification-during-run is separate (differentiator). |
| Bounded iteration when checks fail (don't loop forever) | Every agent retries on failing tests; users expect a ceiling, not an infinite spend. | LOW | Config-driven retry limits; on exhaustion → `FAILED` with every attempt persisted. |
| "Where is this run?" status view | Devin has a session view; Copilot shows work "in real time". A run you can't inspect is unusable. | MEDIUM | `status <run-id>`: run id, task, state, per-role pipeline with worker + attempt count, artifacts, open questions, PR info. |
| Repo-level config file | Copilot uses `.github/` config + `copilot-instructions.md`; DMTools uses job configs; users expect to tune behaviour without forking the tool. | LOW-MEDIUM | `.dark-factory.yaml`: `workflow.roles`, `repository.base_branch`, per-role files, `quality_gate.commands`, retry limits, `publishing.create_pr`. |
| CLI as primary interface | DMTools is CLI-first; developers expect `run` / `status` / `resume` / list commands. | LOW | `run`, `resume`, `status`, `runs`, `artifacts`, `events`. |
| Secrets never surface in agent output, logs, comments, or reports | Baseline security hygiene; any leak is disqualifying for enterprise use. | MEDIUM | Overlaps with the credential-boundary differentiator; the *no-leak-anywhere* guarantee is table stakes on its own. |
| Some audit record of what the run did | DMTools sells "a trail your auditors can read"; CI bots leave PR history. Users expect after-the-fact explainability. | MEDIUM | Dark Factory's event sourcing is a stronger form; a basic append-only run log is the floor. |
| Idempotent external side effects | Retrying publish must not open a second PR; re-posting a comment must not spam the issue. | MEDIUM | Persist `pr_number`, branch, commit SHA, comment id; check before acting. |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Durable run state in Postgres — resume from a brand-new process on any machine** | The core thesis. Devin/Copilot sessions are cloud-ephemeral; OpenHands/SWE-agent hold state in one process. Dark Factory reconstructs the entire run from Neon after a crash, a local→CI handoff, a webhook, or a human answer that arrives hours later. | HIGH | `runs`, `role_executions`, `human_interactions`, `artifacts`, `run_events` tables. No in-memory state from the original process is required to resume. This is the "durability = observability" claim: if the orchestrator can't say where a run is, it can't resume it. |
| **Deterministic outer lifecycle — not one LLM loop** | Devin is an opaque single loop; hard to audit, hard to predict, hard to stop at the right point. Dark Factory keeps "what happens next" under application control and gives the agent freedom only *inside* a role. | MEDIUM | A worker returning `NEEDS_INPUT` never drives a state transition; only Dark Factory mutates orchestration state. Makes runs replayable and testable. |
| **Role ≠ Worker: any role assignable to any agent runtime with zero orchestrator change** | No competitor abstracts across heterogeneous coding CLIs. Copilot is Copilot; Devin is Devin. Dark Factory runs BA on one runtime and Developer on another via config. | HIGH | `CodingWorker` contract (`execute`/`resume`/`capabilities`), `WorkerRegistry`, `WorkerResult` normalization. No `if worker == "claude"` in the orchestrator. |
| **`WorkerCapabilities` model for real runtime differences** | The three target CLIs genuinely differ: native session resume vs none, session ids, non-interactive mode, structured output. Pretending they're identical breaks resume. | MEDIUM | Drives the next feature. Also the reason each adapter needs its own integration test suite. |
| **Dual resume: native session resume OR context reconstruction, behind one `worker.resume()`** | When the runtime supports sessions, pass the opaque `worker_session_id`. When it doesn't, rebuild `RoleContext` from Neon + artifacts and re-enter. Callers can't tell the difference. | HIGH | Depends on `WorkerCapabilities` and on artifact-based handoffs (there is something to reconstruct *from*). |
| **Role-specific tool permissions as an enforced security boundary** | Not advisory. BA/Architect are read-only on code; Developer gets write + shell; QA gets `write_tests` + shell but no publish. Enforced by a `ToolRegistry` capability layer. | MEDIUM-HIGH | Extensible without editing every role executor. This is what makes the next item possible. |
| **Credential isolation from workers** | Workers never receive `DATABASE_URL`, `GITHUB_TOKEN`, or infra credentials — only the minimum env for the role. Worker environments do not inherit the Dark Factory process env. | MEDIUM | A concrete, demoable security story that Devin/Copilot/CI-bots don't articulate (the agent usually runs with broad repo/token scope). |
| **Independent verification (Quality Gate): the platform re-runs the repo's own commands** | Research finding: most orchestration tools "verify" by pattern-matching agent self-reports ("tests passing", "committed 3 files") — which agents emit regardless of reality. Dark Factory runs `quality_gate.commands` (`pytest`, `ruff`, `mypy`, …) itself, in the repo environment, after QA passes. | MEDIUM | Agent self-validation is preserved but explicitly *not* accepted as system truth. Result written to `verification/quality_gate.json`. Publishing requires QA PASS **and** Gate PASS. |
| **Artifact-based handoffs: structured JSON for machine decisions, Markdown for humans** | Not one shared conversation (the multi-agent-chat pattern loses determinism and auditability). Each role emits durable artifacts; the JSON contract wins where orchestration depends on it. | MEDIUM | `requirements.md`/`acceptance_criteria.json`, `design.md`/`constraints.json`, `implementation_summary.json`, `test_report.json`/`verdict.json`. Filesystem holds content; `ArtifactReference` metadata in Neon. |
| **Event-sourced audit trail — full run reconstructable from persisted data** | Stronger than a log file. Every lifecycle event (`ROLE_STARTED`, `QA_FAILED`, `RUN_PAUSED`, `HUMAN_ANSWER_RECEIVED`, `PR_CREATED`, …) is persisted. Powers `status` and `events` and post-mortems. | MEDIUM-HIGH | Directly serves the "durability = observability" thesis. |
| **Human-in-the-loop clarification mid-run, via CLI and via GitHub comments** | Copilot's human loop is *PR review after the work*. Dark Factory lets any role pause mid-run to ask a question, persist `WAITING_HUMAN`, and release the process safely; a later `resume --answer` or a GitHub issue comment continues the *same* `RoleExecution`. | HIGH | Requires durable state + the human_interactions table + the GitHub event handler. The GitHub-comment path is unlocked by GitHub-issue intake. |
| **Bounded feedback loops with real failure payloads** | QA FAIL returns a structured issues artifact (severity, acceptance_criterion, description) to the Developer; Quality-Gate failure returns *actual* failure output, then QA re-evaluates, then the gate re-runs. Configurable iteration caps. | MEDIUM | Distinct transitions, not a generic retry. `retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations`. |
| **Config-driven role pipeline (reorder / shorten without touching Python)** | DMTools-style extensibility: `workflow.roles` list, role YAML (instructions, tools, permissions, hooks, outputs, worker), `ActionRegistry` of deterministic pre/post actions. | MEDIUM | The orchestrator is not "four hard-coded calls". Role behaviour editable in `.dark-factory/` without code. |
| **One orchestrator; environments (CLI / IDE / CI / GitHub) are only triggers** | No separate CI orchestration implementation. A run started locally continues in CI via Neon; a webhook resumes it. | MEDIUM | Contrast with teams maintaining a parallel "CI version" of their automation. |
| **Postgres-native run concurrency (no distributed-lock service)** | Two processes must never execute the same run. Enforced with transactions / row locking / conditional updates on the `runs` row. | MEDIUM | Deliberately avoids adding Redis/Zookeeper/etc. as a dependency. |
| **`FakeWorker` as a first-class deliverable** | Full orchestration behaviour (transitions, handoffs, pause/resume, QA rejection, Developer retries, gate retries, failure limits, publishing) testable with a scripted `WorkerResult` sequence and zero external AI calls. | MEDIUM | Makes the durable-run logic verifiable in CI cheaply — something opaque agents cannot offer. |
| **Idempotent publishing keyed on persisted identifiers** | Retry publish with an existing `pr_number` → no second PR. Branch, commit SHA, PR number/URL, clarification comment id all persisted. | MEDIUM | The safety net that makes cross-process resume trustworthy at the last mile. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Build our own coding agent / autonomous engineering loop** | "We already orchestrate agents, why not write the smart part too?" | Doubles the surface area, competes with Claude Code/Copilot/Hermes on their turf, and destroys the clean responsibility boundary ("what happens next" vs "how the work is done"). | Treat the coding agent as a swappable worker behind `CodingWorker`. Invest in the runtime abstraction, not the model loop. |
| **Generic arbitrary-DAG workflow engine** | "Make the pipeline fully general so any graph works." | Turns a legible ordered role pipeline into an unbounded config language; every feature (resume, verification, feedback loops) now has to handle arbitrary topology. | Keep a clear ordered role pipeline with a small set of explicit feedback transitions (QA→Dev, Gate→Dev). Reorder/shorten, don't arbitrarily branch. |
| **Embedded JavaScript/scripting runtime for actions (DMTools-style scripting)** | "Let users script custom pre/post steps inline." | Ships an interpreter, a sandbox, and a security boundary you now own forever. | `ActionRegistry` of Python implementations referenced by config (`collect_diff`, `store_role_artifacts`, …). Extensible by adding a function, not by evaluating user code. |
| **Separate CI orchestration implementation** | "CI is different, it needs its own runner." | Two codebases drift; resume across the local→CI boundary stops working. | One orchestrator; CI is just another trigger. The run continues via Neon regardless of where the process runs. |
| **Distributed-lock service (Redis/Zookeeper/etcd) for run concurrency** | "Standard way to stop double-execution." | New infra dependency, new failure mode, new ops burden — for a guarantee Postgres already gives you. | Row locking / conditional `UPDATE ... WHERE status = ...` / transactions on the `runs` row. |
| **Turn Neon into a document store for artifact content** | "Everything in one place, queryable." | Bloats the DB, couples orchestration state to large blobs, complicates migrations. | Neon holds state + metadata + `ArtifactReference`s; the filesystem under `.dark-factory/runs/<run-id>/` holds content. |
| **Ship non-core integrations now (Jira, Confluence, TestRail, Figma, Teams, Slack, Azure DevOps, GitLab)** | DMTools has 20+ integrations; "we should match that." | Each integration is an auth flow, a rate-limit story, and a test burden. In Milestone 1 they dilute the durable-run thesis. | Make the integration layer accept new adapters without core changes; ship only GitHub in M1. |
| **Trust the agent's transcript / self-report as verification** | It's free — the agent already says "all tests passing". | Research: agents emit completion language regardless of actual codebase state; ~20% of AI samples even reference non-existent packages. You'd be confirming responsiveness, not correctness. | Independent Quality Gate: the platform re-runs the repo's real commands and cross-references claims against the filesystem. |
| **Let agents own branch/commit/push/PR** | The agent is right there in the repo; simplest path. | Non-deterministic commit hygiene, no idempotency guarantees, secrets (GITHUB_TOKEN) must then reach the agent, retries open duplicate PRs. | Dark Factory owns delivery actions; agents produce a diff, the platform publishes it idempotently. |
| **Copy the whole repository into role prompts** | "Give the agent full context." | Blows the context window, leaks files that should be permission-gated, still goes stale. | `ContextBuilder` gives role-specific context (task, relevant prior artifacts, README/AGENTS.md/CLAUDE.md, constraints, human answers); the agent inspects the repo itself with its own tools. |
| **Multi-agent free-for-all — agents chat to negotiate the outcome** | "Emergent collaboration"; trendy. | Non-deterministic, unauditable, no clean place to pause/resume, hard to test. Research shows single-agent tools already struggle with multi-file reasoning; adding agent-to-agent chatter compounds it. | Fixed role sequence, artifact handoffs, deterministic orchestrator decides transitions. |
| **Auto-merge the PR when the Quality Gate passes** | "Full automation, no human in the loop." | Removes the four-eyes principle Copilot enforces; a green gate is necessary, not sufficient (design/product judgement still needed). | Stop at "verified PR ready for review". Human merges. |
| **Real-time streaming web dashboard in v1** | Devin/Copilot show live progress; feels expected. | Significant frontend + transport work orthogonal to the durable-run thesis; `status`/`events` over the event log already answers "where is this run". | CLI `status` + `events` now; a dashboard is a later read-model over the same event stream. |
| **An eval/benchmark harness for the coding agents themselves** | "We should measure which worker is best." | That's a research project, not orchestration; it competes with SWE-Bench-style efforts. | `WorkerCapabilities` + per-adapter integration tests prove the contract holds. Comparative quality is out of scope. |

---

## Feature Dependencies

```
Durable execution state (runs / role_executions / human_interactions / artifacts / run_events tables)
    ├──enables──> Cross-process / cross-machine resume
    │                 └──requires──> Context reconstruction OR native session resume
    │                                    └──requires──> WorkerCapabilities model
    │                                    └──requires──> Artifact-based handoffs
    ├──enables──> Event-sourced audit trail
    │                 └──enables──> CLI `status` / `events` / observability
    ├──enables──> Pause / resume (WAITING_HUMAN) + human-in-the-loop clarification
    ├──enables──> Postgres-native run concurrency control
    └──enables──> Idempotent publishing (persisted pr_number / SHA / comment id)

Worker abstraction (CodingWorker contract + WorkerRegistry + WorkerResult)
    ├──enables──> Role ≠ Worker independence (any role → any runtime via config)
    ├──enables──> FakeWorker (scripted orchestration tests)
    └──requires──> WorkerCapabilities (to branch resume strategy without orchestrator ifs)

Artifact storage (filesystem content + ArtifactReference metadata in Neon)
    ├──enables──> ContextBuilder / RoleContext
    ├──enables──> Feedback loops (QA issues artifact, quality_gate.json)
    └──enables──> Context-reconstruction resume

Tool permission registry (ToolRegistry capability layer)
    ├──enables──> Role-specific permissions as a security boundary
    └──enables──> Credential isolation from workers

Config-driven role pipeline (workflow.roles + role YAML + ActionRegistry)
    └──enables──> Reorder / shorten pipeline without code change

GitHub issue intake
    ├──enables──> GitHub-comment human clarification (post + ingest reply)
    ├──enables──> GitHub-comment resume (event handler → same RoleExecution)
    └──shares client with──> PR publishing destination

Independent verification (Quality Gate re-runs repo commands)
    ├──requires──> Isolated workspace with the run's git state
    ├──requires──> quality_gate.commands config
    ├──gates──> Publishing (needs QA PASS AND Gate PASS)
    └──feeds──> Quality-Gate → Developer feedback loop

Git lifecycle ownership (branch / commit / push / PR by the platform)
    ├──requires──> Isolated workspace per run
    └──enables──> Idempotent publishing

One orchestrator, environments are triggers
    └──requires──> Durable execution state (run crosses local→CI boundary via Neon)
```

### Dependency Notes

- **Everything downstream requires the persistence layer.** The Neon schema + event log is the true foundation phase; resume, audit, concurrency, pause/resume, and observability are all read/write views over it. Build it first and completely.
- **Worker abstraction + FakeWorker must land before the multi-role pipeline is testable.** `FakeWorker` is how the durable-run logic gets verified without paying for AI calls; the orchestrator's transition logic should be built against it.
- **GitHub-issue intake is a keystone.** It unlocks three otherwise-separate capabilities: comment-based clarification, comment-based resume, and it shares the authenticated GitHub client with PR publishing. Sequencing all GitHub work together is efficient.
- **`WorkerCapabilities` gates the resume strategy.** Native resume (opaque `worker_session_id`) vs context reconstruction is chosen from capabilities; without the model you get worker-specific `if` branches in the orchestrator, which the constraints forbid.
- **Independent verification depends on a faithful workspace.** The Quality Gate is only meaningful if it runs against exactly the git state that produced the diff, in the repo's own environment — so workspace management and git lifecycle ownership must precede it.
- **Tool permission registry precedes the credential boundary.** Credential isolation is enforced *through* the capability layer that decides which env vars a role's worker receives; the registry is the mechanism.
- **Feedback loops depend on machine-readable verdicts.** QA→Developer needs `verdict.json` + a structured issues artifact; Gate→Developer needs `quality_gate.json` with real failure output. Markdown-only outputs would break the loop.

---

## MVP Definition

Milestone 1 is explicitly the entire technical specification. "MVP" here means *build order that keeps the system runnable and testable at each step*, not feature cuts.

### Launch With (v1 = Milestone 1)

- [ ] **Persistence foundation** — Neon schema (`runs`, `role_executions`, `human_interactions`, `artifacts`, `run_events`), SQLAlchemy + Alembic, run state machine, event sourcing. Essential: nothing durable works without it.
- [ ] **Worker abstraction + FakeWorker** — `CodingWorker`, `WorkerRegistry`, `WorkerResult`, `WorkerCapabilities`. Essential: makes orchestration testable and proves role≠worker.
- [ ] **Deterministic orchestrator over a config-driven role pipeline** — `workflow.roles`, role YAML, `ActionRegistry`. Essential: the "not one LLM loop" thesis.
- [ ] **Task intake (text / spec / github) + deterministic classification + `NormalizedTask`** — Essential: entry point; `github:` also unlocks the GitHub loop.
- [ ] **Artifacts + handoffs + `ContextBuilder`** — Essential: how roles communicate; prerequisite for reconstruction resume and feedback loops.
- [ ] **Four roles (BA, Architect, Developer, QA) with role-specific tool permissions** — Essential: the delivery pipeline itself + the security boundary.
- [ ] **Credential isolation from workers** — Essential: security story; low incremental cost once the ToolRegistry exists.
- [ ] **Independent Quality Gate** — Essential: the "don't trust the agent" differentiator; gates publishing.
- [ ] **Feedback loops with bounded retries (QA→Dev, Gate→Dev)** — Essential: without them a single failure kills the run.
- [ ] **Pause / resume, cross-process + cross-machine, native + reconstruction** — Essential: the core value proposition.
- [ ] **Human-in-the-loop via CLI and via GitHub comments** — Essential: runs that can't ask questions fail on ambiguous tasks.
- [ ] **Git lifecycle ownership + idempotent PR publishing** — Essential: the run's output artifact.
- [ ] **CLI (`run`, `resume`, `status`, `runs`, `artifacts`, `events`) + observability** — Essential: operability and the "where is this run" guarantee.
- [ ] **CI as a trigger of the same orchestrator** — Essential: proves the local→CI boundary crossing.
- [ ] **Three real worker adapters (Claude Code, Copilot, Hermes) with per-adapter integration tests** — Essential per the key decision; proves worker independence with three genuinely different runtimes.

### Add After Validation (v1.x)

- [ ] **Read-model web dashboard over the event stream** — trigger: users ask for live progress beyond CLI `status`.
- [ ] **Additional worker adapters (e.g. Aider, Cursor CLI, Codex CLI)** — trigger: demand for a runtime not in the initial three; the abstraction already supports it.
- [ ] **Richer retry policy (per-role, per-failure-type budgets; backoff)** — trigger: real runs show the flat iteration cap is too blunt.
- [ ] **MCP tool transport for compatible workers** — trigger: a target worker consumes tools better over MCP; keep it an optional adapter, never an internal dependency.
- [ ] **Parallel role execution where the pipeline allows** — trigger: latency complaints; only if it doesn't compromise determinism/resume.

### Future Consideration (v2+)

- [ ] **Non-core integrations (Jira, Confluence, TestRail, Figma, Teams, Slack, Azure DevOps, GitLab)** — defer: each is an auth + rate-limit + test burden; the integration layer is designed to accept them later without core changes.
- [ ] **Multi-repo / cross-service change coordination** — defer: large state-model expansion; validate single-repo durability first.
- [ ] **Cost/usage accounting and per-run budgets in currency** — defer: needs per-worker billing telemetry; iteration caps are the M1 proxy.
- [ ] **Worker quality comparison / eval harness** — defer: research project, out of scope; risks becoming a benchmark tool.
- [ ] **GitLab / Bitbucket publishing destinations** — defer: mirror of the GitHub work behind the integration abstraction once GitHub is proven.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Persistence foundation + event sourcing | HIGH | HIGH | P1 |
| Worker abstraction + FakeWorker | HIGH | HIGH | P1 |
| Deterministic config-driven orchestrator | HIGH | MEDIUM | P1 |
| Task intake (3 sources) + deterministic classification | HIGH | MEDIUM | P1 |
| Artifacts + handoffs + ContextBuilder | HIGH | MEDIUM | P1 |
| Four roles + role-specific tool permissions | HIGH | HIGH | P1 |
| Credential isolation from workers | HIGH | MEDIUM | P1 |
| Independent Quality Gate | HIGH | MEDIUM | P1 |
| Feedback loops + bounded retries | HIGH | MEDIUM | P1 |
| Cross-process / cross-machine pause + resume | HIGH | HIGH | P1 |
| Human-in-the-loop (CLI + GitHub comments) | HIGH | HIGH | P1 |
| Git lifecycle ownership + idempotent publishing | HIGH | MEDIUM | P1 |
| CLI + observability (`status` / `events`) | HIGH | MEDIUM | P1 |
| CI as a trigger of the one orchestrator | MEDIUM | LOW-MEDIUM | P1 |
| Three real worker adapters + integration tests | HIGH | HIGH | P1 |
| Postgres-native concurrency control | MEDIUM | MEDIUM | P1 (small, do with persistence) |
| Web dashboard read-model | MEDIUM | HIGH | P2 |
| MCP tool transport adapter | LOW-MEDIUM | MEDIUM | P2 |
| Additional worker adapters | MEDIUM | MEDIUM | P2 |
| Richer retry policy | MEDIUM | MEDIUM | P2 |
| Non-core integrations (Jira/Confluence/…) | MEDIUM | HIGH | P3 |
| Multi-repo change coordination | MEDIUM | HIGH | P3 |
| Cost accounting / currency budgets | LOW-MEDIUM | MEDIUM | P3 |
| Worker eval/benchmark harness | LOW | HIGH | P3 (anti-feature-adjacent) |

**Priority key:** P1 = must have for Milestone 1 launch · P2 = add after validation · P3 = future / deferred.

---

## Competitor Feature Analysis

| Feature | Devin (Cognition) | GitHub Copilot coding agent | OpenHands / SWE-agent | DMTools (EPAM) | CI-based AI PR bots (Sweep/Codegen-style) | Dark Factory approach |
|---------|-------------------|-----------------------------|-----------------------|----------------|------------------------------------------|-----------------------|
| Task intake | Chat / Slack / API | GitHub issue assignment | Issue text / CLI prompt (eval-oriented) | Jira / ADO / GitHub tickets via CLI jobs | GitHub issue / label / comment trigger | Three sources (text, spec file, GitHub issue) → one `NormalizedTask`, deterministic classification |
| Role decomposition | Opaque single loop | Plan → implement → self-review (single agent) | Single agent, plan+act loop | Configurable "agents"/jobs per integration | Usually single pass | Explicit BA→Architect→Developer→QA→Gate, config-ordered, artifact handoffs |
| Agent runtime | Fixed (proprietary) | Fixed (Copilot backend) | Pluggable LLM, fixed agent harness | Pluggable AI provider, fixed job logic | Fixed per product | `CodingWorker` abstraction across Claude Code / Copilot / Hermes; any role → any worker via config |
| Durable state / resume | Cloud session, not user-portable | Cloud session, ephemeral; resumes within GitHub context | In-process; lost on crash | Stateless — "installs fresh every run, no agent process alive" | None; re-run from scratch | Full run state in Neon; brand-new process on any machine resumes the exact step; local→CI handoff |
| Verification of agent output | Agent runs its own tests | Agent runs repo tests/linters; human reviews PR | Iterate until tests pass (agent's own) | Job-defined checks | Often trusts transcript / its own run | Independent Quality Gate re-runs the repo's real commands; agent self-validation not accepted as truth |
| Human-in-the-loop | Chat interjection; PR review | PR review + revise-on-feedback; four-eyes enforced | Minimal (eval context) | Ticket comments per job design | PR comments | Mid-run pause (`WAITING_HUMAN`) via CLI *and* GitHub comment; same `RoleExecution` resumes |
| Git / PR ownership | Agent commits & opens PR | Agent pushes to `copilot/*`, opens PR, no `main` write | Agent produces patch / PR | Job pushes changes | Bot opens PR directly | Platform owns branch/commit/push/PR; agents never hold `GITHUB_TOKEN`; idempotent publish |
| Credential model | Broad session scope | Repo-scoped, branch-restricted | Runs with whatever env you give it | Runs under your CLI credentials | CI token scope | Workers get only minimum role env; never `DATABASE_URL`/`GITHUB_TOKEN`; no process-env inheritance |
| Auditability | Limited (opaque) | PR history + logs | Trajectory logs | "A trail your auditors can read" (sold as a feature) | PR history | Event-sourced: entire run reconstructable from Neon; `events` CLI |
| Extensibility model | Closed | GitHub config + instructions files | Fork the agent | Config jobs + (JS-ish) scripting + 320+ tools | Product config | Config-driven roles + Python `ActionRegistry` (DMTools extensibility *without* a JS runtime) |

### What competitors get wrong (and Dark Factory's counter)

- **Devin:** one big undifferentiated LLM loop — hard to audit, hard to predict where it is, hard to resume deterministically, no role/permission separation. Counter: deterministic outer lifecycle, role boundaries, event sourcing.
- **GitHub Copilot coding agent:** strong PR-review loop and governance (four-eyes, branch restriction) but GitHub-only, single fixed runtime, no configurable multi-role pipeline, and its "verification" is the agent's own test run plus a human. Session is cloud-ephemeral — no cross-machine resume of a paused run. Counter: pluggable workers, real independent Quality Gate, durable portable runs. (Adopt its four-eyes / branch-restriction discipline as table stakes.)
- **OpenHands / SWE-agent:** built for benchmarks, not production delivery. State lives in one process; degrade badly on multi-file / evolving codebases (GPT-5 + OpenHands ~21% on SWE-EVO vs ~65% SWE-Bench Verified); no independent oracle separate from the agent; git handled by the agent. Counter: durable state, bounded feedback loops, platform-owned verification and git.
- **DMTools:** closest prior art and the acknowledged influence — configurable roles, tool abstraction, role-specific capabilities, pre/post processing, artifacts, CI execution, integration abstraction, auditable. But it is deliberately *stateless* ("installs fresh every run, no agent process to keep alive"), so there is no durable delivery-run to resume mid-flight, no abstraction across heterogeneous *coding* CLIs, and no independent quality gate as a first-class concept. Counter: keep the DMTools patterns, add the durable delivery run as the central abstraction, plus worker-runtime abstraction and independent verification. Also: replace DMTools-style embedded scripting with a Python `ActionRegistry`.
- **CI-based AI PR bots:** fast to a PR, but typically trust the agent's transcript ("all tests passing"), have no mid-run human-clarification pause, no role separation, and happily open low-quality PRs that shift the whole burden onto review. Counter: independent verification against the filesystem, mid-run clarification, publish only on QA PASS **and** Gate PASS.

---

## Sources

- GitHub Blog / GitHub Docs — Copilot coding agent: issue assignment, plan→PR→test→review flow, `copilot/*` branch restriction, four-eyes approval rule (vendor docs, MEDIUM–HIGH).
- "Devin vs OpenHands vs SWE-agent" comparisons (toolhalla.ai, aicoolies.com, agents-lib.com) and arxiv SWE-EVO (2512.18470) / OpenHands SDK (2511.03690) — capability profiles and multi-file failure modes (secondary + preprint, MEDIUM).
- EPAM DMTools — GitHub `epam/dm.ai`, `dmtools.lab.epam.com`, `IstiN/dmtools-ai-teammate` — CLI orchestrator, 320+ tools / 20+ integrations, stateless fresh-install-per-run, auditability positioning (vendor + repo, MEDIUM–HIGH).
- Temporal blog + durable-execution write-ups (temporal.io, quellixlabs, zylos.ai, niteagent) — event-history replay, checkpoint/resume, non-deterministic side-effect recording, idempotent tools (vendor + secondary, MEDIUM).
- "AI coding agents lie about their work / outcome-based verification" (dev.to moonrunnerkc), "AI Broke the Assumptions Behind CI" (stack72.dev), AI Transfer Lab (Medium) — transcript-trust failure mode, layered independent verification (Spotify pattern), hallucinated-package rate (~20%) (opinion/practitioner, MEDIUM–LOW; corroborated across sources).
- `/Users/maryiakrauchanka/portfolio/dark-factory/.planning/PROJECT.md` — authoritative scope, requirements list, explicit out-of-scope items (project spec, HIGH).

---
*Feature research for: AI-agent delivery-orchestration platform*
*Researched: 2026-09-06*
