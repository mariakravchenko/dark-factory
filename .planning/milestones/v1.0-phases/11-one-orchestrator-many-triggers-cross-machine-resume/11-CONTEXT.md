# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Phase Boundary

A run started on one machine (local CLI) finishes on another (a CI runner), and
the reverse, with zero lifecycle logic carried between them — everything that
matters is re-materialized from Neon (+ a fresh git checkout/worktree). Two
things prove this: (1) a real production trigger that automatically resumes a
run after a human answers a GitHub webhook-sourced question, and (2) a
`FakeWorker` orchestration test suite covering the full role-pipeline behavior
matrix, running green in CI with no external AI calls and no live worker
credentials.

This phase does not add new pipeline roles, new worker adapters, or new
observability surface (CLI `status`/`runs`/`events` polish is Phase 12).

</domain>

<decisions>
## Implementation Decisions

### CI trigger mechanism (TRIG-01, TRIG-04, HITL-06)
- **D-01:** After `submit_answer` succeeds, the webhook receiver dispatches a
  real GitHub Actions run via the `workflow_dispatch` API, passing the run id
  as an input. This is a new, real production code path — not just a test
  harness/proof — for this MVP phase.
- **D-02:** The dispatch target repo is **not** a new config field. It is read
  straight off the run's own persisted `repository.github_owner`/`github_repo`
  (already stored per-run since Phase 10). Every deployer runs Dark Factory
  against their own target repo, and the workflow that gets dispatched lives
  in that same target repo (see "Deployment model" under `<specifics>`).
  Rejected: hardcoding the dispatch target to Dark Factory's own upstream repo
  (wrong for an open-source tool other people self-host), and a separate
  `Settings.dispatch_repo` field naming a distinct "ops" repo (unnecessary
  once the target-repo-owns-its-own-workflow model was confirmed).
- **D-03:** The receiver needs a new, narrowly-scoped credential to call the
  dispatch API: `Settings.dispatch_github_token` (`SecretStr`), scoped to
  `actions: write` on the target repo only. — **Reversibility:** costly —
  this is a new secret-boundary field; removing it later means re-auditing
  every place `Settings` fields are enumerated for the credential-boundary
  guard (SEC-01/QUAL-04-style structural tests) and updating deployer docs
  and `.env.example`. Kept deliberately separate from `github_token` (per-run
  PR/comment operations) and `github_webhook_secret` (inbound HMAC
  verification) — the existing pattern of one field per credential purpose
  established in `config/settings.py` (Phase 8/10), so a dispatch-only token
  never needs to flow anywhere near worker-facing code.
- **D-04:** The dispatched workflow (`resume.yml`, added by each deployer to
  their own target repo, not shipped/enforced by Dark Factory itself) checks
  out the target repo fresh, installs `dark-factory` (`uv sync` or
  `pip install dark-factory`), and runs `dark-factory resume <run_id>` using
  that repo's own GitHub Actions secrets (`DATABASE_URL`, `GITHUB_TOKEN`,
  worker credentials). It is documentation/reference content for this phase,
  not something Dark Factory's own CI enforces exists.

### CI database for tests (QUAL-01, SC1)
- **D-05:** The `db`-tier test suite (and the cross-machine proof below) runs
  in `ci.yml` via the existing `tests/conftest.py` **testcontainers** probe
  rung — GitHub-hosted `ubuntu-latest` runners already have a Docker daemon,
  so this needs no `services:` block and no new secret. `ci.yml`'s current
  comment claiming "the hosted runner provides neither a Postgres 17 instance
  nor agent-CLI credentials" becomes half-wrong and must be corrected: it now
  gets Postgres via testcontainers, still no agent-CLI credentials (unrelated
  — the `integration` tier stays excluded from CI for that reason).
  Rejected: a `services: postgres` block (works but duplicates what
  testcontainers already does for local dev, per WHY column in
  `.claude/CLAUDE.md`'s stack table) and a persistent Neon test branch
  (unnecessary once the cross-machine proof was scoped to one job).

### Cross-machine proof shape (SC1)
- **D-06:** SC1 ("a run started and paused locally is picked up by a CI job
  on a different machine with no local state carried over") is proven with
  **two `dark-factory` CLI subprocesses inside one CI job**, both pointed at
  the same testcontainers Postgres: process A starts a run and drives it to a
  paused/waiting state, the local worktree and any process-local state are
  then deleted/reset, and process B (a fresh subprocess, no shared Python
  process state) resumes and finishes it. This is deterministic and needs no
  second GitHub Actions job or a durable cross-job database. It does not
  prove two *physically separate* machines — it proves "no local state
  carried over," which is the property SC1 actually cares about.
  Rejected: two dependent GitHub Actions jobs (`needs:`), which would need a
  database that outlives a single ephemeral per-job testcontainers instance
  (i.e. would force the Neon-test-branch option back in) for no proportional
  gain in what the test demonstrates.

### QUAL-01 FakeWorker suite scope
- **D-07:** No new consolidated orchestration test file. Most of the required
  scenario list (role transitions, artifact handoffs, pause/resume, QA
  rejection, Developer retries, quality-gate retries, retry exhaustion,
  publishing) already exists as separate `tests/db/` tests from Phases 4–10
  (`test_four_role_pipeline.py`, `test_qa_bounce.py`,
  `test_iteration_cap_exhaustion.py`, `test_quality_gate_gates_the_run.py`,
  `test_publish_idempotency.py`, `test_feedback_reaches_developer.py`, etc.).
  This phase's job is to (a) get the `db` marker tier actually running in CI
  (D-05 makes this possible), and (b) audit that list against QUAL-01's exact
  scenario wording to find and close any real coverage gaps — not rewrite
  what already passes.

### Claude's Discretion
- Exact GitHub Actions API call shape (`workflow_dispatch` via `githubkit`'s
  existing typed client vs. a raw REST call) — follow whatever
  `src/dark_factory/github/` already established for outbound calls in
  Phase 10.
- Where in the webhook receiver's existing `submit_answer` call site the
  dispatch call is wired in, and its failure-mode (fail-soft vs. fail-loud) —
  should mirror the existing fail-soft pattern used for the Phase 10
  clarification-comment posting (`GitHubError` doesn't abort the state
  mutation that already succeeded).
- Exact db-tier scenario gap analysis against QUAL-01's wording — a research/
  planning-time task, not decided here.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase boundary and requirements
- `.planning/ROADMAP.md` §"Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume" (lines ~465-479) — goal, success criteria, invariants
- `.planning/REQUIREMENTS.md` — TRIG-01, TRIG-04, HITL-06, QUAL-01 (full requirement text)

### Existing invariants this phase must not violate
- `src/dark_factory/webhook/__init__.py` and `src/dark_factory/webhook/app.py` (module docstrings) — "must never reference `advance`/`drive`" (D-02, T-10-21); the new dispatch call must preserve this by calling out to GitHub, not calling `advance`/`drive` itself
- `.github/workflows/ci.yml` — current db/integration-tier exclusion comment to be corrected (D-05)
- `tests/conftest.py` — the testcontainers/pytest-postgresql/external probe ladder this phase reuses as-is

### Credential boundary precedent
- `src/dark_factory/config/settings.py` — existing per-purpose `SecretStr` field pattern (`github_token`, `github_webhook_secret`, `copilot_github_token`) that `dispatch_github_token` (D-03) follows

### Config shape the dispatch target reads from
- `.dark-factory.yaml` — `repository.github_owner`/`repository.github_repo` fields (Phase 10), persisted per-run and read by D-02's dispatch logic

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/dark_factory/orchestrator/runner.py::drive`/`advance` — the single funnel both `cli.py`'s `run`/`resume` commands and the dispatched CI workflow's `dark-factory resume` call go through unchanged (TRIG-01 already holds; this phase proves it under a new trigger, doesn't rebuild it)
- `tests/conftest.py`'s three-rung probe ladder (testcontainers → pytest-postgresql → external `DARK_FACTORY_TEST_DATABASE_URL`) — reused as-is for the new CI db tier
- `tests/support/fake_github.py` — existing fake for GitHub-facing tests; likely needs an addition for asserting the new `workflow_dispatch` call was made, without a real GitHub API call in tests

### Established Patterns
- One `SecretStr` `Settings` field per credential *purpose*, never reused across purposes (`github_token` vs `github_webhook_secret` vs `copilot_github_token`) — `dispatch_github_token` follows this
- Fail-soft on `GitHubError` around side-channel GitHub calls that follow an already-durable state mutation (Phase 10's clarification-comment posting) — the dispatch call should follow the same shape
- `webhook/` package boundary enforced by a structural import-graph test (`test_no_mcp_import_in_core.py`-style) — any new dispatch code must not violate "webhook package never imports `advance`/`drive`"

### Integration Points
- Webhook receiver's `submit_answer` call site (`src/dark_factory/webhook/` — exact file TBD by researcher) — where the new dispatch call gets wired in, after the answer is durably recorded
- `.github/workflows/ci.yml` — needs its db/integration-tier exclusion comment and job steps updated to run the `db` marker tier via testcontainers

</code_context>

<specifics>
## Specific Ideas

### Deployment model (confirmed during discussion)
Dark Factory is distributed as a pip-installable package (`pyproject.toml`
already declares it with a `dark-factory` console-script entry point) — a
deployer does **not** clone or check out Dark Factory's own git repo. Instead:

1. They install `dark-factory` as a dependency inside their own target repo's
   toolchain (`uv add dark-factory` once published, or equivalent).
2. They hand-author `.dark-factory.yaml` and `.dark-factory/roles/*.yaml` in
   their own repo, modeled on this repo's own shipped versions of those files.
3. They add one small `resume.yml` GitHub Actions workflow to their own repo
   (`workflow_dispatch` trigger, `run_id` input, checks out their repo,
   installs `dark-factory`, runs `dark-factory resume <run_id>`).
4. Their webhook receiver (wherever they host it) is configured with
   `dispatch_github_token` scoped to `actions: write` on that same repo.

There is currently no `dark-factory init` scaffold command to generate steps 2
or 3 — flagged as a real gap but explicitly out of this phase's scope (see
Deferred Ideas).

### Full request/response flow (confirmed during discussion)
1. `dark-factory run github:myorg/myrepo#123` (local) creates the run, drives
   roles, may pause `WAITING_HUMAN` and post a clarifying comment on the issue.
2. Human replies on GitHub → `issue_comment` webhook → receiver verifies HMAC,
   resolves the pending interaction, calls `submit_answer` (Neon-only write).
3. **New this phase**: receiver reads the run's persisted
   `repository.github_owner`/`github_repo`, calls `workflow_dispatch` on that
   repo's `resume.yml`, passing the run id, authenticated with
   `dispatch_github_token`.
4. A fresh GitHub Actions runner (genuinely different machine, no local state
   from step 1) checks out the repo, installs `dark-factory`, runs
   `dark-factory resume <run_id>` — which goes through the identical
   `advance()`/`drive()` funnel as step 1, re-materializing everything from
   Neon plus a fresh git worktree.
5. The run proceeds to `COMPLETED` (possibly publishing a PR) or pauses again,
   potentially bouncing through steps 2-5 repeatedly.

</specifics>

<deferred>
## Deferred Ideas

- **`dark-factory init` scaffold command** — generate `.dark-factory.yaml`, a
  starter `.dark-factory/roles/*.yaml` set, and a starter `resume.yml`
  workflow for a new deployer's target repo. Raised while explaining the
  deployment model; genuinely useful but a new capability, not this phase's
  scope (which is the resume/dispatch mechanism itself, not onboarding
  ergonomics). Candidate for a future phase or a post-milestone polish pass.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (`todo.match-phase` found no
candidates).

</deferred>

---

*Phase: 11-One Orchestrator, Many Triggers — Cross-Machine Resume*
*Context gathered: 2026-09-29*
