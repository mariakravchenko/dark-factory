# Pitfalls Research

**Domain:** Durable orchestration of external AI engineering agent CLIs (Python + Neon Postgres), with cross-process resume, human-in-the-loop, independent quality gate, and idempotent GitHub PR publishing
**Researched:** 2026-09-06
**Confidence:** HIGH for durable-execution and Neon/PgBouncer operational facts (official Neon docs + established durable-execution literature); MEDIUM for per-worker CLI behavior (Claude Code / Copilot / Hermes differ and change frequently — verify against the installed CLI versions during implementation)

This document is opinionated and specific to Dark Factory. Generic advice ("write tests", "handle errors") is omitted. Every pitfall below is a way this specific system silently corrupts the durable-run thesis or produces an unsafe external side effect.

---

## Critical Pitfalls

### Pitfall 1: Non-atomic "store result + transition state + create interaction" sequence

**What goes wrong:**
A role finishes and the orchestrator does, in separate transactions: (1) write `role_executions.result` JSONB, (2) update `runs.status` / `current_role`, (3) insert a `human_interactions` row, (4) insert `run_events`. The process is killed (OOM, CI timeout, SIGTERM, laptop lid) between any two of these. On resume, Neon shows a run whose `status` disagrees with its latest `role_execution`, or a `WAITING_HUMAN` run with no pending interaction row, or a completed role with no artifact references. The run is now unresumable or resumes into the wrong branch of the pipeline.

**Why it happens:**
Developers reach for "save as you go" because each write is individually simple, and because the agent call that precedes them is long and they want to checkpoint progress. ORM lazy-flush and autocommit hide the transaction boundaries.

**How to avoid:**
- Define **one** state-mutation function per lifecycle event (e.g. `complete_role_execution(...)`, `pause_run_for_human(...)`, `record_qa_verdict(...)`). Each opens a single SQLAlchemy transaction, performs *all* related row writes (result JSONB + `runs` row + interaction + `run_events`), and commits once. No caller writes lifecycle rows directly.
- Every such function is a pure function of `(current persisted state, new inputs)` → it can be re-run safely if the commit's ack was lost (see Pitfall 5).
- The `run_events` insert is part of the same transaction as the state change it describes — never a fire-and-forget log after commit. If it is not in the transaction, the audit trail lies, and "durability == observability" is already broken.
- Model states as an explicit enum + a table of legal transitions; the mutation function asserts the transition is legal before writing.

**Warning signs:**
- Any code path that calls `session.commit()` more than once while handling a single role result.
- `run_events` written via a logging handler or a separate session.
- A `status` column updated by a bare `UPDATE runs SET status=...` anywhere outside the central mutation module.
- Tests that kill the process mid-pipeline don't exist.

**Phase to address:**
Persistence schema & durable-state core (the earliest persistence phase). This is the load-bearing invariant; nothing else works if it's wrong.

---

### Pitfall 2: State that cannot be reconstructed without the original process's memory

**What goes wrong:**
The orchestrator builds up in-memory context during a run — the `NormalizedTask`, the resolved workflow, the accumulated artifact list, the base commit SHA it captured at start, the working-branch name it generated, the retry counters, the "which acceptance criteria already passed" set — and only *some* of it is persisted. Resume in a fresh process (the explicit core value: `dark-factory resume <run-id>` from any machine) rebuilds a *different* context: a different branch name, a re-normalized task, a reset retry counter, lost "already passed" state. The run diverges from where it actually was.

**Why it happens:**
It's natural to compute things once at run start and pass them down the call stack. Persisting every derived value feels redundant while the process is alive.

**How to avoid:**
- Treat the process as disposable from day one. Rule: **if `resume()` needs a value, it is a column or a JSONB field, not a local variable.** Includes: normalized task, resolved workflow definition (snapshot, not a reference to current config — see Pitfall 20), working branch name, base branch, base commit SHA, per-loop retry counters, QA per-criterion pass/fail ledger, current role + current step, worker id per role.
- Build the resume path *first*, before the happy path. Write an integration test that runs role 1, throws away the process, starts a new process, and resumes role 2 — on day one of the orchestrator.
- Add a `reconstruct_run_context(run_id) -> RunContext` function that is the *only* way any orchestrator entry point (fresh `run`, `resume`, webhook, CI pickup) obtains context. The initial `run` command calls it too, right after inserting the run row.

**Warning signs:**
- `resume` code that accepts parameters other than `run_id` and the human answer.
- Branch name or commit SHA computed with `datetime.now()` / `uuid4()` outside a persisted write.
- Retry counters that live on an orchestrator object.
- The happy-path `run` and the `resume` path share no common context-loading function.

**Phase to address:**
Orchestrator core + resume (build them as one phase, not "orchestrator now, resume later").

---

### Pitfall 3: Two processes resume the same run simultaneously (lost updates on `status`)

**What goes wrong:**
A delayed human answer arrives via GitHub webhook at the same moment a CI job or a local `dark-factory resume` picks up the same run. Both read `status = WAITING_HUMAN`, both start executing the developer role, both spawn an agent, both push commits, both try to open a PR. Or subtler: two workers write `runs.status` and the second overwrites the first's transition (`UPDATE runs SET status='QA'` clobbers a concurrent `UPDATE runs SET status='FAILED'`).

**Why it happens:**
The spec forbids a distributed-lock service, so developers assume "Postgres handles it" without choosing a concrete mechanism. Read-then-write on the status column without row locking is a classic lost update.

**How to avoid:**
- **Claim, don't check.** Acquire a run with a conditional atomic update:
  `UPDATE runs SET owner_token = :tok, owner_expires_at = now() + interval '15 min', status = :running_status WHERE id = :id AND (owner_token IS NULL OR owner_expires_at < now()) RETURNING *`.
  If zero rows returned, another process owns it — exit quietly. This is the lease.
- Alternatively/additionally use `SELECT ... FROM runs WHERE id = :id FOR UPDATE` at the top of every state-mutating transaction so concurrent mutators serialize instead of clobbering.
- Every write to `runs.status` goes through the central mutation function (Pitfall 1) and includes the expected current status in its `WHERE` clause (optimistic concurrency): `... WHERE id = :id AND status = :expected`. Zero rows updated → someone else moved the run → abort and reload.
- Heartbeat the lease during long agent calls; on resume, a lease whose `owner_expires_at` is in the past is reclaimable.
- **Advisory-lock caveat (Neon-specific):** if you use `pg_advisory_lock` (session-scoped) through Neon's pooled connection string, PgBouncer runs in **transaction pooling mode** — the session lock stays attached to a backend that gets handed to the next client, leaking the lock and causing "ghost" contention that never reproduces locally. Use `pg_advisory_xact_lock` (transaction-scoped, auto-released at COMMIT/ROLLBACK) **only**, or take locks over the unpooled connection. Prefer the row-lease approach above and avoid advisory locks entirely.

**Warning signs:**
- Any `SELECT status ...` followed later by `UPDATE ... status` in different statements without `FOR UPDATE` or a conditional `WHERE`.
- No `owner_token` / lease column on `runs`.
- `pg_advisory_lock(` anywhere in the codebase.
- Webhook handler and CLI resume don't share the claim function.
- Test suite has no "two resumers race" test.

**Phase to address:**
Concurrency & run-claiming (part of the persistence/orchestrator core). Neon connection-mode decision belongs to the persistence phase.

---

### Pitfall 4: A transaction (or DB connection) held open across a long agent CLI call

**What goes wrong:**
The orchestrator opens a transaction / checks out a pooled connection, marks the role `RUNNING`, then blocks for 3–20 minutes on `subprocess` while Claude Code works. The connection is idle-in-transaction the whole time. Against Neon this: holds a PgBouncer server slot out of the ~0.9 × max_connections pool, blocks autovacuum, and — if the compute autosuspends after 5 minutes idle or the pooler drops idle server connections — the connection is dead when the agent returns, so the "mark COMPLETED" write throws and the successful agent run is lost.

**Why it happens:**
"Mark running, do work, mark done" reads naturally as one transaction. ORM session scoping (e.g. a request/run-scoped session) keeps the connection checked out for the whole run.

**How to avoid:**
- **Transaction boundary rule:** a DB transaction never spans an agent call or any subprocess. Pattern: `txn { mark RUNNING, snapshot inputs } → (no DB) run agent → txn { store result, transition }`.
- Acquire connections lazily and return them immediately (`NullPool` or short-lived engine checkout). Neon's own guidance for non-JS ORMs is: use the **pooled** connection string for normal traffic and let Neon's PgBouncer pool; keep the app-side SQLAlchemy pool tiny or `NullPool`.
- Use the **unpooled/direct** connection string for Alembic migrations, `LISTEN/NOTIFY`, and anything needing session state — never route those through `-pooler`.
- Set `statement_timeout` and `idle_in_transaction_session_timeout` on the app role so a bug surfaces as an error, not a silent stuck backend.
- Assume every connection may be cold: wrap DB access in a retry-once-on-`OperationalError` helper to absorb the 300–800 ms Neon cold start after autosuspend.
- Keep the agent's own wall-clock timeout (Pitfall 8) well under the lease TTL so a hung agent loses the lease cleanly.

**Warning signs:**
- A single `with Session() as s:` (or `s.begin()`) enclosing the `worker.execute()` call.
- SQLAlchemy engine created with a large `pool_size` / `max_overflow`.
- Alembic `sqlalchemy.url` pointing at a `-pooler` host.
- `psycopg.OperationalError: server closed the connection unexpectedly` / `connection was closed in the middle of operation` appearing after long roles.
- Neon dashboard shows sustained "idle in transaction".

**Phase to address:**
Persistence phase (connection strategy, timeouts, retry helper) + orchestrator phase (transaction boundary discipline).

---

### Pitfall 5: Losing `worker_session_id` — resume silently starts a fresh agent conversation

**What goes wrong:**
A worker returns `NEEDS_INPUT` with an opaque `worker_session_id` (Claude Code session id, etc.). It's kept in memory, or written outside the same transaction as the `WAITING_HUMAN` transition, or written to the wrong `role_executions` row (the current attempt vs. a new one). On resume the adapter can't find it, so instead of `worker.resume(session_id, answer)` it does a cold `worker.execute()` — the agent loses all prior context, re-asks the same question, or redoes work. The human sees an incoherent conversation and the run burns a retry.

**Why it happens:**
The session id is "just a string in the result"; its criticality isn't obvious. Adapters that support native resume and adapters that don't get handled by the same code, so the id gets dropped for all of them.

**How to avoid:**
- `worker_session_id` is a first-class column on `role_executions`, written in the **same transaction** as the pause transition (Pitfall 1).
- The `WorkerCapabilities` model explicitly flags `native_resume: bool` and `session_id: bool`. The resume path branches on capability, never on worker name (Pitfall 6): if `native_resume` and a stored id exists → `worker.resume(id, answer)`; else → context-reconstruction resume (rebuild the full prompt from persisted artifacts + the human answer and call `execute()` again).
- Both resume strategies must be behind the identical external signature `worker.resume(role_execution, answer) -> WorkerResult` so the orchestrator is agnostic.
- Test with `FakeWorker` configured both ways: `native_resume=True` (asserts the scripted session id is passed back) and `native_resume=False` (asserts the reconstructed context contains the prior artifacts + answer).
- Persist enough to reconstruct even when native resume *is* available — native resume can break (agent CLI upgraded, session expired server-side). Context reconstruction is the fallback for every worker.

**Warning signs:**
- `worker_session_id` assigned to `self.` / a local.
- The pause code path writes the session id in a different `commit()` than the status change.
- Resume code contains `if worker_type == "claude-code"`.
- No test asserts the session id round-trips through a fresh process.

**Phase to address:**
Worker abstraction phase (capabilities model, resume contract) + human-in-the-loop/pause-resume phase.

---

### Pitfall 6: The worker abstraction leaks — `if worker == "claude"` creeps into the orchestrator

**What goes wrong:**
Claude Code, Copilot CLI, and Hermes differ in real ways (native resume vs none, JSON output vs prose, flag names, how they signal "I need input", how they report changed files). The first divergence gets patched with `if worker_type == "copilot": ...` in the orchestrator or role executor. Six months later the orchestrator has branches for three CLIs, adding a fourth means editing core code, and the "any role → any worker" promise is dead.

**Why it happens:**
Adding a branch is a 2-line fix; extending the capability model is a 30-line refactor. Under deadline the branch wins every time.

**How to avoid:**
- The orchestrator and role executors may read **only** `WorkerCapabilities` fields and `WorkerResult` fields — never a worker id/name for behavioral decisions. Enforce with a lint/grep test in CI: fail the build if `claude|copilot|hermes` appears as a string literal outside `dark_factory/workers/` and config.
- Every real runtime difference must be named as an explicit capability: `native_resume`, `session_id`, `structured_output`, `noninteractive_flag`, `mcp_transport`, `max_prompt_bytes`, `emits_changed_files`. If a difference can't be expressed as a capability, the capability model is incomplete — extend it, don't branch.
- `WorkerResult` is normalized *inside* the adapter: `status ∈ {COMPLETED, NEEDS_INPUT, FAILED}`, `summary`, `questions[]`, `artifacts[]`, `changed_files[]`, `worker_session_id`, `metadata`. The orchestrator never parses raw stdout.
- `FakeWorker` implements the same contract; if `FakeWorker` can express a behavior the real adapters express, the contract is honest.

**Warning signs:**
- String literals `"claude-code"`, `"copilot"`, `"hermes"` outside the workers package.
- `WorkerCapabilities` has < ~6 fields (probably under-modeled).
- Adapter code returns raw `subprocess` output up the stack.
- A new worker requires touching `orchestrator/`.

**Phase to address:**
Worker abstraction phase. Add the CI grep-guard in the same phase.

---

### Pitfall 7: Brittle parsing of unstructured agent stdout

**What goes wrong:**
The adapter greps the agent's prose for "PASS", a file list, or a question ("does the CLI print `? ` when it wants input"). The agent phrases things differently next run (or after a model/CLI update), the regex misses, and the orchestrator concludes the role failed, or missed the clarification request, or lost the changed-files list — then commits an incomplete diff or loops.

**Why it happens:**
Not every CLI has a `--output-format json`, so scraping prose is the path of least resistance for at least one of the three adapters.

**How to avoid:**
- Prefer structured output where the CLI supports it (Claude Code `--output-format json` / stream-json; check each CLI's current flags). Mark `structured_output: true` in capabilities.
- Where structured output is unavailable, do **not** infer state from prose. Instead: (a) instruct the role (via role instructions) to write its machine-readable decision to a known artifact path (`artifacts/<role>/verdict.json`, `implementation_summary.json`), and (b) derive `changed_files` from **git** (`git status --porcelain`, `git diff --name-only`) not from the agent's narration, and (c) treat "needs input" as: the agent wrote a `questions.json` artifact OR exited non-zero with a known sentinel — not a stdout pattern.
- The agent's stdout/stderr is captured verbatim to `logs/` for humans and for the Developer feedback loop, but is never the orchestration signal.
- Contract test: feed the adapter a recorded "weird phrasing" transcript and assert it still extracts the right `WorkerResult` (because it's reading artifacts + git, not prose).

**Warning signs:**
- Regexes over `result.stdout` in adapter code.
- `changed_files` populated from anything but git.
- "Needs input" detection that depends on an interactive prompt string.

**Phase to address:**
Worker abstraction phase + context/artifacts phase (defining the artifact contract each role must emit).

---

### Pitfall 8: Subprocess management — zombies, PIPE-buffer deadlock, no timeout, unbounded buffers

**What goes wrong:**
- The agent emits > ~64 KB to stdout while the parent isn't reading (parent is blocked writing to the agent's stdin, or waiting on `proc.wait()`): the OS pipe buffer fills, the agent blocks on write, the parent blocks — **deadlock**, run hangs forever, lease never released.
- No wall-clock timeout: a wedged agent (waiting on a network call, or an interactive prompt the `--non-interactive` flag didn't actually suppress) hangs the run indefinitely.
- Parent is killed; the agent subprocess (and *its* children — MCP servers, language servers, `node`) are orphaned and keep running, holding file locks in the worktree, or continuing to write files.
- Multi-hundred-MB stdout buffered into a Python string → OOM kill → Pitfall 1.

**Why it happens:**
`subprocess.run(cmd, capture_output=True)` is the obvious call and works fine in dev with small outputs and fast agents.

**How to avoid:**
- Never `capture_output=True` for agent calls. Stream stdout/stderr line-by-line to files under `logs/` on separate reader threads (or `asyncio`), so the pipe never backpressures. Keep only a bounded tail in memory (last N KB) for error surfacing.
- Always pass `timeout=` (per-role, from config) and on `TimeoutExpired` escalate SIGTERM → wait grace → SIGKILL.
- Start the agent in its **own process group** (`start_new_session=True` / `preexec_fn=os.setsid`) and kill the whole group on timeout/cancel so MCP servers and language-server children die too.
- Register an `atexit` / signal handler that terminates any live child groups when the orchestrator is asked to stop.
- Explicitly close/redirect stdin (`stdin=DEVNULL` unless you're feeding the answer) so the agent can't block waiting for terminal input.
- Cap total captured log size per role; truncate with a marker rather than growing unbounded.

**Warning signs:**
- `capture_output=True` or `stdout=PIPE` + `proc.communicate()` with no size thought on agent calls.
- No `timeout=` on the agent subprocess.
- `ps` shows `claude` / `node` / `copilot` processes after a run ended.
- Runs that "hang" with the CPU idle.

**Phase to address:**
Worker abstraction phase (a shared `subprocess` runner utility all adapters use).

---

### Pitfall 9: Non-interactive flags that still prompt

**What goes wrong:**
The adapter passes `--non-interactive` / `--yes`, but the CLI still stops for: a first-run auth/onboarding prompt, a "trust this directory?" prompt, a telemetry consent prompt, a "Node version" warning that expects Enter, or git asking for credentials mid-operation. With `stdin` closed it may EOF-loop; with `stdin` inherited it blocks on the terminal. Either way the run hangs until the timeout, every time, on CI.

**Why it happens:**
Each CLI has a different set of prompts and a different flag surface; "non-interactive" is not uniformly complete. Dev machines are already authed and trusted, so it only shows up in fresh CI containers.

**How to avoid:**
- Per adapter, assemble a full non-interactive posture, not one flag: the CLI's own non-interactive/print flag **plus** environment (`CI=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/true`, `NO_COLOR=1`, CLI-specific `*_NONINTERACTIVE` / config-dir vars), **plus** pre-seeded config/trust files where the CLI supports them, **plus** `stdin=DEVNULL`.
- Encode "this CLI is safe to run unattended in a clean container" as a capability that the per-adapter **integration test** actually verifies by running in a container with no prior CLI state.
- Detect the failure fast: if the agent produces zero output for M seconds, treat as wedged and kill — don't wait for the full role timeout.

**Warning signs:**
- Integration tests only pass on a developer machine that has already logged the CLI in.
- Runs hang for exactly the role-timeout duration on CI.
- First CI run after a base-image bump hangs.

**Phase to address:**
Worker abstraction phase; the per-adapter integration-test suite is where "clean environment" must be proven.

---

### Pitfall 10: Secrets leaking into prompts, artifacts, events, logs, comments, test reports

**What goes wrong:**
`DATABASE_URL` (with Neon password), `GITHUB_TOKEN`, and worker API keys end up somewhere a human or the agent can read them: the agent subprocess inherits the parent's full `os.environ`; a role prompt includes "the environment" for debugging; an error path serializes `os.environ` or a config object into `run_events` JSONB; `subprocess` stderr containing a token echo is copied into `logs/` and then quoted verbatim into a GitHub clarification comment; a failing test prints `os.environ` into `test_report.json`.

**Why it happens:**
Environment inheritance is the `subprocess` default. "Dump everything" is the fastest debugging move. JSONB makes it trivial to persist an entire object without thinking about its contents.

**How to avoid:**
- **Never** pass `env=None` (inherit) to an agent subprocess. Build the child env explicitly from an allowlist: `PATH`, `HOME`, `LANG`, a scoped work dir, and the **single** credential that role's worker needs (its own model API key) — nothing else. `DATABASE_URL` and `GITHUB_TOKEN` are never in a worker env.
- Git/GitHub operations (branch, commit, push, PR, comment) are done by **Dark Factory**, in a separate code path that has `GITHUB_TOKEN`, not by the agent. The agent never needs it.
- A single `redact(text) -> text` scrubber (regex for known token shapes: `ghp_`, `github_pat_`, `sk-`, `postgres://user:pass@`, plus exact-match on every value in the loaded secret set) is applied at every egress boundary: prompt assembly, artifact write, `run_events` payload, log line, GitHub comment body, test-report ingestion.
- `run_events` and artifact writers accept only explicitly-constructed dicts — never `vars(obj)` / `obj.__dict__` / `os.environ`.
- Config objects hold secrets in a `SecretStr`-style wrapper whose `__repr__`/`__str__`/JSON encoder returns `***`.
- Test: assert each known secret value is absent from every artifact file, every `run_events.payload`, and every outbound comment, in an end-to-end run with real-shaped fake secrets.

**Warning signs:**
- `subprocess.Popen(cmd, ...)` with no `env=` kwarg.
- `json.dumps` of a config/context object into a persisted column.
- Any log/comment built by string-concatenating raw subprocess output without `redact()`.
- `GITHUB_TOKEN` readable from a role's `RoleContext`.

**Phase to address:**
Security-boundary phase (env allowlist, redaction scrubber) — must land **before** the first real worker adapter and before GitHub integration. Retrofitting redaction after leaks are already in the DB is a data-scrubbing incident.

---

### Pitfall 11: Retrying publish opens a second PR (idempotency of external side effects)

**What goes wrong:**
`publish` = collect diff → commit → push → `POST /pulls`. The process dies after `POST /pulls` succeeds but before `runs.pr_number` is committed (classic dual-write). Resume re-runs publish → a second PR for the same branch, or a `422` that's mishandled as fatal → run stuck. Same class of bug: re-pushing duplicate commits, posting a second identical clarification comment, re-running quality-gate commands that have side effects (e.g. a migration, a deploy, a `npm publish --dry-run` that isn't dry).

**Why it happens:**
The "write the identifier after the side effect" ordering feels correct but leaves a gap. GitHub's create-PR isn't idempotent by default.

**How to avoid:**
- **Check-before-create, keyed by persisted identifier**, for every external action:
  - PR: before `POST /pulls`, query `GET /pulls?head=<owner>:<branch>&state=all`. If one exists, adopt its number/URL and skip creation. Only then create. Persist `pr_number`, `pr_url`, and the head commit SHA in the same transaction.
  - Clarification comment: persist `clarification_comment_id` per `human_interaction`. Before posting, if the id exists, skip. Optionally embed a hidden marker `<!-- dark-factory:run=<id>:interaction=<n> -->` and search for it as a second guard.
  - Commit: check `git log` for a commit whose message carries the run id / step marker before committing again; use a deterministic commit message containing `run=<id> step=<step>`.
  - Push: `git push` is naturally idempotent for the same commits; guard against force-push.
- Model publish as a small state machine with its own sub-states persisted (`DIFF_COLLECTED`, `COMMITTED@<sha>`, `PUSHED`, `PR_CREATED@<n>`) so resume knows exactly which steps already happened.
- Quality-gate commands must be assumed **non-idempotent from the framework's POV** — but the gate itself should only run read-only verification commands (test/lint/typecheck). If a repo configures a gate command with side effects, that's the repo's problem, but the framework must still enforce the retry cap (Pitfall 13) so it can't loop.
- Give the GitHub client an idempotency-aware wrapper and a bounded retry with backoff for `5xx`/secondary-rate-limit, distinct from "the operation already happened".

**Warning signs:**
- `POST /pulls` with no preceding "does a PR already exist for this head" check.
- `pr_number` written in a different transaction than the run's `PUBLISHING → COMPLETED` transition.
- Comment posting with no persisted `comment_id`.
- Publish is a single function with no sub-state, re-run wholesale on resume.

**Phase to address:**
GitHub integration / publishing phase. The publish sub-state machine is part of that phase's core design, not a follow-up.

---

### Pitfall 12: Trusting agent self-reports as system truth

**What goes wrong:**
The Developer says "all tests pass, lint clean"; the QA agent says `verdict: PASS`. The orchestrator transitions toward publish on those words. In reality the Developer ran a subset, or a different Python, or skipped the failing file; QA "verified" by reading the diff and reasoning, not by executing. A broken PR gets published with a green story attached.

**Why it happens:**
The agents produce confident structured output that looks authoritative. Re-running everything independently feels redundant and slow.

**How to avoid:**
- The **independent Quality Gate** is non-negotiable and runs *after* QA PASS: Dark Factory itself executes `quality_gate.commands` from repo config (`pytest`, `ruff check .`, `mypy .`, build) in the run's worktree, in a controlled environment, and reads **exit codes**, not agent prose. Result → `verification/quality_gate.json`.
- Agent self-validation output is retained (it's useful signal and audit) but is explicitly labeled non-authoritative; the state machine transitions on the gate's exit codes only.
- QA's `verdict.json` is treated as a *proposal*; publish requires `QA.verdict == PASS` **AND** `quality_gate.status == PASS`, both persisted, checked in the transition guard.
- The gate runs the exact commands from config, no "equivalent" substitution.

**Warning signs:**
- A transition to `PUBLISHING` whose guard reads a field written by an agent.
- No `quality_gate.json` in the artifact tree, or it's written by a role rather than the framework.
- Quality gate parses stdout for "passed" instead of checking `returncode == 0`.

**Phase to address:**
Independent quality-gate phase (distinct from the QA role phase).

---

### Pitfall 13: Retry limits not enforced → infinite feedback loop; flaky tests bounce forever

**What goes wrong:**
QA fails → Developer fixes → QA re-checks → fails again (or a flaky test fails 1-in-5) → Developer → QA … forever, or until the cloud bill / API quota is gone. Same for quality-gate ↔ Developer. A subtly-wrong retry counter (reset on resume per Pitfall 2, or incremented in the wrong loop) makes the cap ineffective.

**Why it happens:**
The counter lives in memory or is incremented at the wrong place; "it'll converge" optimism; flaky tests make "did it actually fail" ambiguous so the loop doesn't recognize non-progress.

**How to avoid:**
- `retry.qa_developer_max_iterations` and `retry.quality_gate_max_iterations` from repo config; counters are **persisted columns** on the run (or a `feedback_loops` table), incremented in the same transaction as the loop transition (Pitfall 1), and read back on resume — never in-memory.
- The transition guard checks the persisted counter *before* dispatching another Developer attempt. On exhaustion → `FAILED`, with every attempt's actual failure output persisted (Pitfall 14).
- Add a **no-progress** detector: hash the set of failing acceptance criteria / failing test node-ids each iteration; if the failure set is identical two iterations running, stop early (the agent isn't converging) rather than spending the full budget.
- Flaky-test handling: the quality gate is the arbiter, and it runs once per gate invocation. Don't auto-retry gate commands to "get past" flakiness — that hides real failures. If a repo's suite is flaky, surface it (persist the flake) and let the cap end the run rather than looping.
- `FakeWorker` tests: scripted sequence that never converges → assert run ends `FAILED` at exactly the configured cap, with N persisted attempts.

**Warning signs:**
- Retry counter is a local variable or an attribute on the orchestrator.
- Counter incremented after dispatch instead of checked before.
- Resuming a run mid-loop resets the count.
- No test that a non-converging loop terminates.

**Phase to address:**
Feedback-loop & retry-policy phase.

---

### Pitfall 14: Not persisting the *actual* failure output for the Developer

**What goes wrong:**
QA or the quality gate fails, but only a summary ("3 tests failed") or the agent's paraphrase is stored. The Developer's next attempt gets a vague hint, not the stack traces / assertion diffs / lint messages, so it guesses, and the loop wastes iterations. Or the output was streamed to a log file that a fresh resume process can't correlate to the attempt.

**Why it happens:**
Full output is large and awkward to store; the summary looks sufficient in the demo where failures are simple.

**How to avoid:**
- On any QA FAIL or gate FAIL, persist the **raw** command output (stdout+stderr, per command, with exit codes) as an artifact (`verification/quality_gate.json` + `logs/quality_gate_<attempt>.log`) and record an `ArtifactReference` row tying it to the specific `role_execution` / iteration.
- QA FAIL additionally emits a structured issues artifact: `[{severity, acceptance_criterion, description, evidence}]` — where `evidence` points at the concrete failing test/line, not a vibe.
- The `ContextBuilder` for the Developer's retry **must** include the latest failure artifact for the current loop, and must **exclude** stale failure artifacts from prior, already-resolved iterations (Pitfall 16).
- Truncate sanely (head+tail with a marker) but keep enough to be actionable; store the full log on the filesystem, reference it in Neon.

**Warning signs:**
- Feedback artifact contains only counts / a one-line summary.
- Developer retry context has no test output in it.
- Failure logs aren't linked to an attempt id.

**Phase to address:**
Feedback-loop phase + context-builder phase.

---

### Pitfall 15: Role permission boundaries not enforced — QA edits production code, BA/Architect write source

**What goes wrong:**
The spec says BA/Architect are read-only on source, Developer writes code+tests, QA writes **tests/fixtures only** and cannot publish. If this is enforced only by *prompt instructions*, a capable agent will "helpfully" fix a bug during QA, or the Architect will scaffold files. Now QA is no longer independent (it modified the thing it's verifying), the diff contains changes no Developer attempt produced, and the audit trail misattributes work.

**Why it happens:**
Prompt-only enforcement is easy; real enforcement needs a tool/permission layer and post-hoc diff checking. Agents are eager.

**How to avoid:**
- Enforce at the **tool layer**: the `ToolRegistry` grants each role only its capabilities (`repo.read/search` for BA/Architect; `repo.write` + `shell.execute` for Developer; `repo.write_tests` + `shell.execute` for QA; nobody but the framework gets publish). A role physically cannot call a tool it wasn't granted.
- Belt-and-braces for workers that touch the filesystem directly (agent CLIs edit files without going through your tools): after each role, run a **post-role diff check** (`ensure_role_diff_within_bounds` action) — compare `git diff --name-only` against an allowlist of path globs for that role (QA: only `tests/**`, `conftest.py`, fixtures). Out-of-bounds change → fail the role, revert the offending paths (`git checkout -- <path>`), persist the violation as an event, and either retry with a sharper instruction or fail the run. Don't silently keep the change.
- BA/Architect: after their role, assert `git diff` touches **no** source and no test — only their artifact files (which live under `.dark-factory/`, outside the repo tree) should exist.
- Persist the enforced boundary decision as an event so "QA stayed independent" is provable.

**Warning signs:**
- Role permissions exist only as sentences in `instructions/*.md`.
- No `git diff` inspection between roles.
- QA attempts show up in `git blame` on non-test files.
- The final PR diff includes files no Developer `implementation_summary` mentions.

**Phase to address:**
Tools & permissions phase (capability enforcement) + actions phase (post-role diff guard).

---

### Pitfall 16: Stale artifacts / worktree state from a previous attempt bleeding into a retry

**What goes wrong:**
Developer attempt 2 starts, but its `RoleContext` still contains attempt-1's `implementation_summary.json` and attempt-1's QA feedback that's already been addressed; or the worktree still has attempt-1's uncommitted edits mixed with a partial revert; or a previous role's scratch files are still on disk. The agent gets contradictory inputs and produces a Frankenstein diff.

**Why it happens:**
Artifacts are append-only by run, and "latest" resolution is fuzzy. Worktree isn't reset between attempts. Resume re-hydrates *all* artifacts for the run.

**How to avoid:**
- Artifacts are namespaced by `(run_id, role, attempt)`. `ContextBuilder` resolves "the relevant prior artifact" as *the latest committed one for the specific upstream role*, and for feedback loops, *only the current iteration's* feedback — via explicit queries, not "load all artifacts for run".
- Between roles / attempts run `ensure_clean_worktree`: assert `git status --porcelain` is empty at role entry; if a prior attempt left changes, they were either committed (Developer success) or reverted (Developer failure / boundary violation) — never carried implicitly.
- Each attempt operates from a known base: either the last good commit (loop restart) or the branch head; recorded per attempt.
- Clear per-role scratch dirs at role start.
- Test: run Developer→QA-FAIL→Developer again with `FakeWorker`, assert attempt 2's context contains attempt 2's feedback and **not** attempt 1's, and the worktree at attempt-2 entry is clean.

**Warning signs:**
- `ContextBuilder` does `SELECT * FROM artifacts WHERE run_id = ?` with no role/attempt filter.
- No `git status` assertion at role boundaries.
- Retry diffs that partially undo and redo the same lines.

**Phase to address:**
Context-builder phase + git-lifecycle phase.

---

### Pitfall 17: Dumping the whole repo into prompts / prompt size blowups

**What goes wrong:**
`ContextBuilder` inlines the repository (or "all the relevant files", or every prior artifact, or full test logs) into the role prompt. Prompt exceeds the model/CLI context window → hard error or silent truncation of the *end* (where the actual task instruction often is). Costs balloon. Different workers have different limits so it works for one and breaks another.

**Why it happens:**
"Give the agent everything" feels safe. The agent CLIs *can* explore the repo themselves but that's less obviously reliable than pasting.

**How to avoid:**
- Per the spec: context does **not** copy the repo. `RoleContext` = task + role instructions + *pointers to* prior artifacts (paths) + key docs (README/AGENTS.md/CLAUDE.md/architecture docs) + human answers + constraints + permitted capabilities. The agent reads files itself via `repo.read`.
- Budget the prompt: compute assembled size, compare against `WorkerCapabilities.max_prompt_bytes`, and if over, degrade deterministically (summaries/pointers instead of inline content) and log it — never blind-truncate.
- Feed failure logs as head+tail excerpts + an artifact path, not the full multi-MB log.
- Include few-shot examples by reference from role config, treated as context data, not code.

**Warning signs:**
- `ContextBuilder` walks the repo tree and reads file contents into a string.
- Prompt assembly has no size check.
- Cost per role varies 10x by repo size.
- One worker errors on "context length" while others don't.

**Phase to address:**
Context-builder phase.

---

### Pitfall 18: GitHub webhook resume — wrong run, new run instead of continue, webhook/local race

**What goes wrong:**
An issue comment arrives. The handler: can't map it to a run (no persisted linkage), so it **creates a new run** from the issue; or maps it to the run but not to the specific pending `human_interaction` (there could be several historically); or stores the answer and resumes while a local `dark-factory resume` is *also* resuming the same run (Pitfall 3); or processes the same webhook delivery twice (GitHub retries) and answers/resumes twice.

**Why it happens:**
The linkage from "GitHub issue/comment" back to "run + interaction" isn't designed up front. Webhook at-least-once delivery is forgotten.

**How to avoid:**
- When Dark Factory posts a clarification comment, persist the full linkage: `run_id`, `human_interaction.id`, `issue_number`, `clarification_comment_id`, and embed a hidden marker in the comment body (`<!-- dark-factory:run=<id>:interaction=<n> -->`).
- Webhook handler resolves the target by: (1) the reply's `in_reply_to` / thread, or the marker in the quoted/parent comment, or (2) latest `human_interaction` with `status=WAITING` for the run linked to that issue. If none found → **do nothing / log**, never create a run.
- Dedupe deliveries by GitHub's `X-GitHub-Delivery` id (persist processed ids); the "store answer" write is conditional (`UPDATE human_interactions SET answer=?, status='ANSWERED' WHERE id=? AND status='WAITING'`) so a duplicate is a no-op.
- The webhook path stores the answer, then **enqueues/claims** the run through the *same* claim mechanism as CLI resume (Pitfall 3) — it does not itself run the pipeline inline while holding an HTTP request open. A local resumer and the webhook contend for the one lease; loser backs off.
- Ignore comments authored by the Dark Factory bot account (don't answer your own question).

**Warning signs:**
- Webhook handler has a code path that inserts into `runs`.
- No persisted `clarification_comment_id` / delivery-id table.
- `human_interactions` answered unconditionally.
- Webhook handler calls the orchestrator run loop synchronously.

**Phase to address:**
GitHub integration phase (issue-as-source + webhook resume) — depends on human-in-the-loop and concurrency phases already existing.

---

### Pitfall 19: Git lifecycle — dirty worktree, detached HEAD, branch collisions, lost uncommitted changes

**What goes wrong:**
- Role B starts on a worktree Role A left dirty; B's agent's changes and A's uncommitted changes are indistinguishable.
- A checkout by SHA leaves detached HEAD; the Developer's commits land on no branch and are lost after the next checkout.
- The generated working branch name collides with an existing branch (re-run of the same task, or a name derived from issue number) → push rejected or, worse, pushed onto someone else's branch.
- Process dies after the agent edits files but before Dark Factory commits → resume does `ensure_clean_worktree` naively, `git checkout -- .`, and **deletes the agent's work** that cost 10 minutes and API spend.

**Why it happens:**
Git state is implicit global mutable state in a directory; multiple roles + resume + retries all touch it. "Clean the worktree" and "don't lose work" are in tension and the naive resolution picks one.

**How to avoid:**
- Dark Factory owns all git actions (spec). Working branch created once from configured base, name includes run id (guaranteed unique, e.g. `dark-factory/run-<id>`), existence checked before create; on collision, fail loudly (don't guess).
- Always operate on a named branch; assert `git symbolic-ref -q HEAD` succeeds (not detached) at every role boundary.
- **Resume rule for a dirty worktree:** dirty + last event is `ROLE_STARTED` for a role that can write (Developer/QA) → the changes are that role's in-progress output. Options, in order: (a) if the role can be considered complete enough, capture the diff as an artifact and let the role's post-actions run; (b) otherwise commit them to a WIP commit on the working branch (recoverable) *then* reset, so nothing is ever `checkout -- .`'d away; (c) only for roles that must be read-only (BA/Architect) is an unexpected dirty worktree safe to hard-reset — and that itself is a logged anomaly.
- `ensure_clean_worktree` never runs a destructive command without first stashing/WIP-committing to a ref that's persisted in `run_events`.
- Per-run isolation: dedicate a worktree/clone per run (`git worktree add`) so concurrent runs never share a checkout.

**Warning signs:**
- `git checkout -- .` / `git reset --hard` / `git clean -fd` anywhere without a preceding stash/WIP-commit whose ref is persisted.
- Branch name with no run id.
- No detached-HEAD assertion.
- Two runs pointed at the same working directory.

**Phase to address:**
Git-lifecycle phase (branch/commit/push ownership) + resume phase (dirty-worktree recovery rule).

---

### Pitfall 20: Workflow / role config resolved late — a run's meaning changes under it

**What goes wrong:**
A run is paused for two days waiting on a human. Meanwhile `.dark-factory.yaml` is edited (a role removed, order changed, a role's worker swapped, quality-gate commands changed). Resume reads *current* config → the run now has a different pipeline than it started with; `current_step` indexes into a list that changed; retry caps differ; the run resumes into a role that no longer exists or skips one.

**Why it happens:**
Config is loaded fresh each process as "the source of truth". Snapshotting it per run isn't the obvious default.

**How to avoid:**
- At run creation, **snapshot** the resolved workflow (role list, per-role definition incl. worker + tools + permissions + hooks + retry caps + quality-gate commands) into `runs.workflow` JSONB. The orchestrator executes the snapshot, not the live file, for the life of the run.
- `resume` / webhook / CI pickup all read the snapshot. Live config changes affect only *new* runs.
- Store `current_role` as an identifier (role name), not a positional index, so list edits can't misalign it even in the snapshot.
- Version the config schema; refuse to start a run against an unknown version.

**Warning signs:**
- Orchestrator reads `.dark-factory.yaml` during `resume`.
- `runs` has no `workflow` snapshot column, or it stores a version string / path instead of the resolved content.
- `current_step` is an integer index into a runtime-loaded list.

**Phase to address:**
Configuration phase + persistence schema phase (the `workflow` JSONB column).

---

### Pitfall 21: Clock / timestamp skew across processes and machines

**What goes wrong:**
Timestamps written with the *application* clock (`datetime.now()` on a laptop, a CI runner, a webhook host) drift by seconds-to-minutes. Event ordering in the audit trail goes non-monotonic ("ROLE_COMPLETED" before "ROLE_STARTED"); lease-expiry math (`now() > owner_expires_at`) computed against the wrong clock reclaims a live lease or never reclaims a dead one; "delayed human answer" duration is nonsense.

**Why it happens:**
`datetime.now()` / `datetime.utcnow()` is the reflex. Different hosts, no NTP guarantee, timezone-naive values.

**How to avoid:**
- **All** timestamps and all "is it expired" comparisons use the **database** clock: `server_default=func.now()`, `onupdate=func.now()`, and lease checks done in SQL (`WHERE owner_expires_at < now()`) — never computed in Python and compared.
- Store timezone-aware UTC (`TIMESTAMPTZ`).
- Event ordering relies on a DB-generated monotonic sequence (`BIGSERIAL` / identity column), not on the timestamp, for "what happened next".
- If the app must stamp a time (rare), fetch `SELECT now()` rather than trusting the host clock.

**Warning signs:**
- `datetime.now()` / `datetime.utcnow()` feeding a persisted column or a lease comparison.
- `run_events` ordered by `created_at` in queries.
- Naive datetimes in the schema.

**Phase to address:**
Persistence schema phase.

---

### Pitfall 22: Alembic migrations unsafe under concurrent CI + local; JSONB blobs unbounded

**What goes wrong:**
- CI and a developer both run `alembic upgrade head` against the *same* Neon branch at once → duplicate DDL, half-applied migration, `alembic_version` race. Or a migration takes a lock that blocks live runs.
- Migrations routed through the `-pooler` (transaction-mode PgBouncer) connection → `CREATE INDEX CONCURRENTLY`, advisory locks, and multi-statement session assumptions misbehave.
- `role_executions.result` / `run_events.payload` JSONB grows without limit — a chatty agent's full transcript, huge `changed_files` lists, embedded logs — table bloats, queries slow, backups balloon.

**Why it happens:**
"Just run migrations on deploy" without a single owner. Neon's two connection strings aren't obviously different. JSONB feels free.

**How to avoid:**
- **One** migration runner. Migrations run via the **direct/unpooled** Neon connection string (`DATABASE_URL_UNPOOLED`), never the pooler. Guard `alembic upgrade` with a `pg_advisory_xact_lock` on a fixed key (over the direct connection) so concurrent runners serialize; second one no-ops.
- CI applies migrations as a dedicated step that other jobs depend on; local dev applies explicitly. App startup does **not** auto-migrate (or if it does, behind the same advisory lock, and it's a deliberate decision).
- Migrations are additive/backward-compatible (expand-contract): add nullable column → backfill → switch code → drop later. Never a destructive change in the same migration as code that depends on it.
- Use Neon **branch** databases for CI so CI never migrates the shared dev DB.
- Cap JSONB: store large content (transcripts, logs, full diffs) on the **filesystem** as artifacts (per the spec's Neon-isn't-a-document-store principle) and keep only references + small structured summaries in JSONB. Enforce a max serialized size on `run_events.payload`; truncate with a marker and an artifact pointer.

**Warning signs:**
- `alembic.ini` / env `sqlalchemy.url` uses a `-pooler` host.
- App process calls `command.upgrade` on boot with no lock.
- Migration files with `DROP COLUMN` next to new dependent code.
- `run_events` / `role_executions` row sizes in the MB range.

**Phase to address:**
Persistence schema & migrations phase (Neon connection split, migration lock, expand-contract policy).

---

### Pitfall 23: FakeWorker diverges from the real adapter contract; integration tests need real AI creds in CI

**What goes wrong:**
`FakeWorker` returns a `WorkerResult` shape (or status semantics, or session-id behavior, or `changed_files` provenance) that the real adapters don't actually produce. Orchestration tests are all green; the first real run fails on a contract mismatch the fakes hid. Separately: the per-adapter integration tests need live Claude/Copilot/Hermes credentials, so they can't run in CI, so the real adapters are effectively untested on every change.

**Why it happens:**
The fake is written to make orchestration tests pass, then drifts as adapters evolve. Real-credential tests are awkward to wire into CI safely.

**How to avoid:**
- Define the `CodingWorker` contract as an explicit spec (Protocol/ABC + a shared `contract_test` suite parametrized over *every* worker, fake included). `FakeWorker` must pass the exact same contract tests as `ClaudeCodeWorker`. If a contract test can only pass for the fake, the contract is under-specified.
- Record real adapter interactions once (captured transcripts / fixtures) and replay them in CI as "recorded integration" tests — real parsing, real `WorkerResult` normalization, no live creds. Refresh recordings deliberately.
- Keep true end-to-end live-credential tests as a separate, manually/nightly-triggered suite (not on the PR critical path), with credentials from CI secrets scoped to a throwaway model key, never inherited into any worker subprocess env (Pitfall 10).
- Contract test asserts the invariants that matter: status enum only ever `{COMPLETED, NEEDS_INPUT, FAILED}`; `changed_files` reflects git, not narration; `worker_session_id` present iff `capabilities.session_id`; `NEEDS_INPUT` always carries `questions`.

**Warning signs:**
- `FakeWorker` has its own bespoke test, not the shared contract suite.
- Adapters have no CI coverage (only "run locally with your key").
- `WorkerResult` fields the fake sets that no real adapter sets, or vice versa.
- Contract changes don't force a fake update (no shared suite).

**Phase to address:**
Worker abstraction phase (contract + FakeWorker + shared contract suite) + a testing-strategy phase (recorded-integration approach).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Enforce role permissions via prompt instructions only, not the tool layer | Skip building `ToolRegistry` capability gating | QA silently edits source; independence claim is false; audit misattributes changes; retrofitting is a security/correctness review | Never — this is a core value ("independent verification"). Tool-layer gate + post-role diff guard from the first Developer/QA phase |
| Auto-run `alembic upgrade` on app startup, no lock | One less deploy step | Concurrent CI+local corruption of `alembic_version`; migration lock stalls live runs | Only single-developer, single-process local dev, behind an advisory lock, with a plan to remove |
| Store agent transcripts / full diffs / logs in JSONB | No filesystem artifact plumbing yet | Table bloat, slow queries, fat backups, contradicts "Neon isn't a document store" | Only for tiny structured summaries; large content must go to filesystem artifacts before the first real worker |
| Parse agent stdout for verdicts / file lists / questions | Works without each CLI's structured-output mode | Breaks on phrasing/model/CLI changes; wrong transitions; missed clarifications | Only as a *logged, non-authoritative* signal; truth comes from artifacts + git + exit codes |
| In-memory retry counters / accumulated context on the orchestrator object | Simpler control flow | Resume in a fresh process resets loops → infinite ping-pong; divergent runs | Never — every resume-relevant value is persisted from day one |
| Single transaction wrapping `mark running → agent call → mark done` | Reads naturally | Idle-in-transaction against Neon; pool slot held; dead connection after autosuspend loses the result | Never for agent calls; transaction boundaries must not span subprocesses |
| One working directory shared by all runs | No per-run worktree setup | Concurrent runs corrupt each other's git state | Only while strictly one run at a time is possible; add `git worktree` per run before concurrency is real |
| Skip the "does a PR/comment already exist" check, write the id after the API call | Less code | Duplicate PRs / duplicate comments on any retry or crash-after-side-effect | Never for external side effects; check-before-create keyed by persisted id |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Neon (pooled vs direct) | Using the `-pooler` connection string for migrations, `LISTEN/NOTIFY`, session advisory locks, or long session state | Pooled string for normal short queries; **direct/unpooled** string for Alembic, `LISTEN/NOTIFY`, `CREATE INDEX CONCURRENTLY`, session-scoped locks |
| Neon (transaction-mode PgBouncer) | `pg_advisory_lock` (session-scoped) over the pooler — lock leaks to the next client on the shared backend | Use `pg_advisory_xact_lock` only, or don't use advisory locks — prefer a row-lease (`owner_token` + conditional `UPDATE`) |
| Neon (autosuspend / scale-to-zero, default 5 min) | Assuming a warm DB; first query after idle throws or adds 300–800 ms; connection cached across the gap is dead | Retry-once-on-`OperationalError` wrapper; short-lived connections / `NullPool`; expect cold starts; consider raising the suspend timeout for active dev |
| Neon (connection budget ~0.9 × max_connections per role/db) | Large app-side SQLAlchemy `pool_size` + long checkouts exhausts the server pool under a few concurrent runs | Tiny or `NullPool` app pool; never hold a connection across an agent call; let Neon's PgBouncer do the pooling |
| GitHub create-PR | `POST /pulls` with no existence check → second PR on retry | `GET /pulls?head=owner:branch&state=all` first; adopt existing; persist `pr_number`/`pr_url`/head SHA in the same txn as the state transition |
| GitHub issue comments (clarification) | Re-posting the question on resume; answering the bot's own comment; treating webhook delivery as exactly-once | Persist `clarification_comment_id` + hidden run/interaction marker; dedupe on `X-GitHub-Delivery`; conditional answer write (`WHERE status='WAITING'`); ignore bot-authored comments |
| GitHub webhook → resume | Handler creates a new run when it can't map the comment; runs the pipeline inline in the HTTP handler | Resolve run+interaction via marker/thread or latest `WAITING` interaction for the issue's run; if unresolved, no-op; store answer then hand off to the shared claim/resume mechanism |
| Agent CLI (Claude Code / Copilot / Hermes) | Assuming identical flags, output format, resume support, and "non-interactive" completeness | Model every difference as a `WorkerCapabilities` field; per-adapter non-interactive posture proven by an integration test in a clean container; `env` allowlist per worker |
| Agent CLI subprocess | `capture_output=True`, no timeout, inherit parent env, kill only the direct child | Stream to files on reader threads; per-role `timeout=`; explicit `env` allowlist; own process group + group-kill; `stdin=DEVNULL` |
| Quality-gate command execution | Running gate commands in the wrong cwd / wrong Python / wrong venv, or trusting stdout text | Run in the run's dedicated worktree with a controlled, explicit environment; decide on **exit codes**; persist raw per-command output as an artifact |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| DB connection held across agent calls | Neon "idle in transaction"; `too many connections`; dead-connection errors after long roles | Transaction never spans a subprocess; `NullPool` / short checkouts; statement + idle-txn timeouts | 2–5 concurrent runs, or the first role longer than the autosuspend window |
| Whole-repo / all-artifacts context stuffing | Context-length errors on some workers; per-role cost scales with repo size; end-of-prompt truncation | Pointers not payloads; the agent reads files itself; prompt-size budget vs `max_prompt_bytes` with deterministic degradation | Any real-world repo (thousands of files) or a long feedback history |
| Unbounded JSONB (`run_events.payload`, `role_executions.result`) | Slow `runs`/`events` queries; multi-MB rows; slow/large backups | Large content → filesystem artifacts + references; cap payload size; truncate with marker | Dozens of runs with chatty agents |
| Unbounded feedback loop (QA↔Dev, gate↔Dev) | API spend climbs; run never finishes; identical failure set each iteration | Persisted retry caps checked *before* dispatch; no-progress detector on failing-set hash | First non-converging task or first flaky suite |
| Streaming agent output fully into memory | RSS spikes; OOM kill mid-role → lost result | Bounded in-memory tail; full stream to file | Any agent that prints a large diff or verbose logs |
| Per-run full `git clone` instead of worktree | Disk fills; slow role startup | `git worktree add` per run from one local clone; GC old worktrees | Many runs against a large repo on a small CI runner |
| `run_events` scanned/ordered by timestamp | Non-deterministic ordering; slow audit rendering | Monotonic sequence column + index on `(run_id, seq)` | As soon as two processes write events for one run |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Agent subprocess inherits full `os.environ` | `DATABASE_URL`, `GITHUB_TOKEN`, other keys readable by the agent (and anything it runs / any MCP server it spawns) | Explicit `env` allowlist per worker; only that worker's own model key + `PATH`/`HOME`/`LANG`/workdir |
| Giving the agent `GITHUB_TOKEN` so "it can open the PR" | Token in prompt/log/artifact; agent can push anywhere the token allows | Dark Factory performs all git/GitHub actions in a separate path; the agent never gets the token |
| Serializing config/context/`os.environ` into `run_events` or artifacts on an error path | Secrets persisted in Neon and on disk forever; visible in `status`/`events` output | `run_events`/artifact writers take explicit dicts only; `SecretStr` wrapper with redacting `repr`; `redact()` at every egress |
| Copying raw subprocess stderr into a GitHub comment or `test_report.json` | A token echoed by a tool leaks into a public PR comment or a committed report | `redact()` applied to every outbound comment body and every ingested test report; scrub before persist and before send |
| DB connection string with password in error messages / stack traces / logs | Full Neon creds in log aggregation | Redact `postgres://user:pass@` pattern globally; construct engine from parts; never log the URL |
| Neon `DATABASE_URL` for a role that "just needs to read an issue" | Over-broad blast radius if that worker is compromised | Roles get zero infra creds; issue reading is a Dark Factory tool call, not an agent capability |
| Trusting the agent's report that it didn't touch forbidden paths | Compromised independence, unreviewed changes in the PR | Tool-layer permission denial + post-role `git diff` path-allowlist check with revert-on-violation |
| Migrations / DDL run with the app's least-privilege role failing silently, then run as superuser everywhere | Broad privileges on the runtime connection | Separate migration role (direct connection) vs. runtime role (pooled, DML only) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| `status <run>` can't explain where a paused run actually is | User can't tell if resume is safe; the core promise ("if it can't explain where a run is, it can't resume it") visibly fails | `status` renders state + active role + worker + session id + attempt + role history + artifacts + open questions + gate results + PR info + full transition history, all from Neon |
| Clarification question posted to GitHub with no context / no run link | Human doesn't know which task, which repo, what's being asked | Comment includes task summary, run id, the specific decision needed, and a hidden machine marker; the reply flow is obvious |
| Resume that silently cold-starts the agent (lost session) | Agent re-asks the same question or redoes work; user loses trust | Native resume when capable; otherwise reconstruct full context incl. the prior answer; tell the user which path was used |
| Run fails at the retry cap with only "FAILED" | User can't tell if it's their task, a flaky suite, or a framework bug | Persist every attempt + its raw failure output; `status`/`events` show the progression and the last real error |
| Duplicate PRs / duplicate comments after a crash-then-resume | User sees noise on the issue/PR, distrusts automation | Idempotent publish + comment keyed by persisted ids; check-before-create |
| Long silent role (agent working for 15 min, no output) | User assumes it hung, kills it, loses progress | Stream agent output to a tailable log; emit a heartbeat event; document expected durations |

## "Looks Done But Isn't" Checklist

- [ ] **Resume:** Kill the process mid-role (SIGKILL) and resume in a *fresh* process on a *different* working copy — verify identical branch name, retry counters, QA per-criterion ledger, and no lost agent work.
- [ ] **Concurrency:** Start two `resume` processes on the same run at the same instant — verify exactly one executes, the other exits cleanly, and `runs.status` is never clobbered.
- [ ] **Atomicity:** Inject a crash between "store result" and "transition" — verify the run is still consistent and resumable (no `WAITING_HUMAN` without an interaction row; no completed role without artifacts).
- [ ] **Idempotent publish:** Run publish, kill after `POST /pulls` returns but before the txn commits, resume — verify **one** PR, `pr_number` persisted.
- [ ] **Idempotent clarification:** Resume a `WAITING_HUMAN` run twice via webhook (duplicate delivery) — verify one comment, one answer stored, one resume.
- [ ] **Secret hygiene:** Grep every artifact file, every `run_events.payload`, every outbound comment, and every log for each known secret value after a full run — zero hits.
- [ ] **Worker env:** Assert the agent subprocess's `environ` contains no `DATABASE_URL` / `GITHUB_TOKEN` / unrelated keys (spawn a fake worker that dumps its env to an artifact).
- [ ] **Permission boundary:** Script QA (FakeWorker) to "edit" a source file — verify the change is rejected/reverted and logged, QA independence preserved.
- [ ] **Retry cap:** Script an endless QA↔Developer disagreement — verify the run ends `FAILED` at exactly the configured iteration count with all attempts persisted.
- [ ] **Quality gate is independent:** Have the Developer/QA agents *claim* pass while the real `pytest` exits non-zero — verify the run does **not** publish.
- [ ] **Config snapshot:** Pause a run, edit `.dark-factory.yaml` (reorder roles), resume — verify the run follows its original snapshot, not the new file.
- [ ] **Neon cold start:** Let the compute autosuspend (or simulate a dropped connection), then resume — verify the retry wrapper absorbs it.
- [ ] **Migrations:** Run `alembic upgrade head` twice concurrently (two shells) — verify no corruption of `alembic_version`.
- [ ] **Contract parity:** `FakeWorker` passes the *same* shared contract-test suite as every real adapter.
- [ ] **Subprocess hygiene:** After a timed-out role, `ps` shows no orphaned `claude`/`node`/`copilot`/MCP processes.
- [ ] **Git state:** After every role boundary, `git status --porcelain` is empty and HEAD is a named branch (not detached).
- [ ] **Webhook can't fork a run:** Send an issue comment that matches no pending interaction — verify no new run is created.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Inconsistent persisted state (status vs. last role_execution disagree) after a non-atomic crash | MEDIUM | Add a `reconcile(run_id)` that recomputes canonical status from the latest `role_execution` + events; run before every resume; if ambiguous, move to `WAITING_HUMAN` / `FAILED` with an event rather than guessing |
| Duplicate PR already opened | LOW | Adopt the lowest-numbered open PR for the head branch, close the extras with a comment, persist the kept `pr_number`; add the missing check-before-create |
| Secrets already written to Neon `run_events` / artifacts | HIGH | Rotate the exposed credentials immediately; scrub affected rows/files; add `redact()` at egress; audit all historical rows; treat as an incident |
| Advisory-lock leak on Neon pooler causing phantom contention | MEDIUM | Switch to `pg_advisory_xact_lock` or the row-lease mechanism; restart the pooler/compute to clear leaked locks; add a test that runs claiming through the pooled string |
| Infinite feedback loop discovered in prod (bill spike) | MEDIUM | Kill the run; add persisted caps checked before dispatch + no-progress detector; replay the transcript through `FakeWorker` to confirm termination |
| Lost agent work from a naive `git reset --hard` on resume | HIGH (rerun the role, re-spend API budget) | Change `ensure_clean_worktree` to WIP-commit to a persisted ref before any destructive op; recover from reflog if within gc window |
| Orphaned agent subprocesses holding worktree locks | LOW | Kill the process group by stored PGID; add process-group start + group-kill + `atexit` reaper |
| JSONB bloat degrading queries | MEDIUM | Migrate large payloads to filesystem artifacts + references; add size cap; `VACUUM FULL` / table rewrite on the affected tables (off-peak) |
| Run wedged in `RUNNING` with an expired lease (process vanished) | LOW | Lease TTL + `owner_expires_at < now()` reclaim path makes it self-healing; a `runs` sweeper can also flip stale `RUNNING` back to its resumable state with an event |

## Pitfall-to-Phase Mapping

Phase names are indicative — align with the actual ROADMAP. "Persistence core" = the phase that builds the Neon schema + durable-state module; "Orchestrator core" = deterministic role pipeline + resume; etc.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Non-atomic result+transition+interaction | Persistence core | Crash-injection test between sub-writes leaves a consistent, resumable run |
| 2. State not reconstructable without process memory | Orchestrator core + resume (one phase) | Kill-and-resume-in-fresh-process test: branch name, counters, QA ledger identical |
| 3. Two processes resume same run | Concurrency / run-claiming (in persistence or orchestrator core) | Race test: exactly one executes; `status` never clobbered |
| 4. Transaction across agent call / pool exhaustion | Persistence core (conn strategy) + orchestrator core (txn discipline) | Long-role test shows no idle-in-transaction; connection count flat under N concurrent runs |
| 5. Lost `worker_session_id` | Worker abstraction + pause/resume | Session id round-trips through a fresh process for `native_resume=True`; context reconstruction verified for `False` |
| 6. Worker abstraction leaks (`if worker ==`) | Worker abstraction | CI grep-guard fails on worker-name literals outside `workers/`; new worker added with zero orchestrator edits |
| 7. Brittle stdout parsing | Worker abstraction + artifacts contract | Recorded "weird phrasing" transcript still yields correct `WorkerResult`; `changed_files` sourced from git |
| 8. Subprocess: zombies / PIPE deadlock / no timeout / buffers | Worker abstraction (shared subprocess runner) | Large-output agent doesn't deadlock; timeout kills the process group; no orphans in `ps` |
| 9. Non-interactive flags still prompt | Worker abstraction (per-adapter integration tests) | Each adapter runs unattended in a clean container with no prior CLI state |
| 10. Secret leakage / env inheritance | Security boundary (before first real worker + before GitHub) | Grep for secret values across artifacts/events/comments/logs = 0; worker env dump has no infra creds |
| 11. Retry publish → second PR; duplicate comments | GitHub integration / publishing | Crash-after-`POST /pulls` resume yields one PR; duplicate webhook yields one comment |
| 12. Trusting agent self-reports | Independent quality gate | Agents claim PASS while `pytest` fails → run does not publish |
| 13. Retry limits unenforced → infinite loop | Feedback loop & retry policy | Non-converging FakeWorker script ends `FAILED` at exact cap |
| 14. Actual failure output not persisted for Developer | Feedback loop + context builder | Developer retry context contains the current iteration's raw test output, not a summary |
| 15. Role permission boundaries not enforced | Tools & permissions + actions (post-role diff guard) | QA editing source is rejected/reverted/logged |
| 16. Stale artifacts / worktree bleed into retry | Context builder + git lifecycle | Retry context = current iteration only; worktree clean at attempt entry |
| 17. Whole-repo prompt stuffing / size blowup | Context builder | Prompt size checked vs `max_prompt_bytes`; degrades deterministically; agent reads repo itself |
| 18. Webhook resume: wrong run / new run / race | GitHub integration (webhook) | Unmatched comment creates no run; duplicate delivery is a no-op; webhook and CLI resume contend on one lease |
| 19. Git lifecycle: dirty worktree / detached HEAD / branch collision / lost work | Git lifecycle + resume (dirty-worktree rule) | Role boundaries: clean worktree, named branch; resume WIP-commits before any destructive op |
| 20. Late-resolved config changes a run's meaning | Configuration + persistence schema (`workflow` JSONB) | Editing config during a pause doesn't change the resumed run's pipeline |
| 21. Clock / timestamp skew across processes | Persistence schema | All timestamps `func.now()`; lease checks in SQL; events ordered by sequence column |
| 22. Alembic unsafe concurrently; JSONB unbounded | Persistence schema & migrations | Concurrent `alembic upgrade` doesn't corrupt; migrations use direct connection + advisory lock; large content on filesystem |
| 23. FakeWorker diverges; integration tests need live creds | Worker abstraction + testing strategy | Shared contract suite runs over fake + all real adapters; recorded-integration tests run in CI without creds |

## Sources

- Neon Docs — Connection pooling (PgBouncer transaction mode, 10k client limit, `pool_size = 0.9 × max_connections`, `-pooler` hostname): https://neon.com/docs/connect/connection-pooling — HIGH
- Neon Docs — Choosing your connection method (pooled for app traffic; direct/unpooled for migrations, `LISTEN/NOTIFY`, session state, replication): https://neon.com/docs/connect/choose-connection — HIGH
- Neon Docs — Connection latency and timeouts / scale-to-zero (default 5 min autosuspend, 300–800 ms cold start, configurable): https://neon.com/docs/connect/connection-latency — HIGH
- SQLAlchemy pooling for serverless (NullPool + external pooler pattern): https://davidmuraya.com/blog/sqlalchemy-connection-pooling-for-serverless-fastapi/ — MEDIUM
- Postgres advisory locks + PgBouncer transaction pooling (session-lock leak to shared backend; use `pg_advisory_xact_lock`): https://www.snowinch.com/en/blog/postgres-advisory-lock-connection-pool-leak — MEDIUM; corroborated by PgBouncer FAQ guidance and https://github.com/ClosureTree/with_advisory_lock/issues/43 — MEDIUM
- Temporal — Idempotency and durable execution (workflow id as idempotency key; side effects in activities; activities must be idempotent): https://temporal.io/blog/idempotency-and-durable-execution — HIGH
- Temporal — Error handling in distributed systems (retry policy, non-progress, poison tasks): https://temporal.io/blog/error-handling-in-distributed-systems — HIGH
- Jack Vanlightly — Demystifying determinism in durable execution (deterministic control flow vs. non-deterministic side effects; replay hazards): https://jack-vanlightly.com/blog/2025/11/24/demystifying-determinism-in-durable-execution — MEDIUM
- DBOS Docs — Workflows (durable steps, exactly-once semantics, recovery): https://docs.dbos.dev/typescript/tutorials/workflow-tutorial — MEDIUM
- Durable Execution for LLM Agents (applying durable-execution patterns to agent pipelines): https://vadim.blog/durable-execution-llm-agents/ — LOW/MEDIUM
- Python `subprocess` known hazards (PIPE-buffer deadlock without concurrent reads, process-group kill, `stdin=DEVNULL`, `timeout=`): established platform behavior / official `subprocess` docs — HIGH
- GitHub REST API — Pulls (create-PR is not idempotent; list by `head` to detect existing): docs.github.com/rest/pulls — HIGH
- Dark Factory PROJECT.md (spec constraints: durability == observability, Role ≠ Worker, secret boundary, idempotency, publishing policy, Neon-not-a-document-store) — HIGH

---
*Pitfalls research for: durable AI-agent delivery orchestration (Python + Neon)*
*Researched: 2026-09-06*
