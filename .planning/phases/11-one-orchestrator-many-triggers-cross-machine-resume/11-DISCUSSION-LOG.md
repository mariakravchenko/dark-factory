# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-29
**Phase:** 11-One Orchestrator, Many Triggers — Cross-Machine Resume
**Areas discussed:** CI trigger mechanism, CI database, cross-machine proof shape, QUAL-01 suite scope, dispatch target repo, dispatch credential, build-vs-defer, deployment model walkthrough

---

## CI trigger mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Webhook dispatches a GH Actions run | Receiver calls the GitHub API to fire `workflow_dispatch` carrying the run id after `submit_answer` | ✓ |
| Scheduled poll job | A cron CI job queries Neon for resumable runs and resumes each | |
| Out of scope — prove via test harness only | Prove the mechanism with a CI test job, defer the real production trigger | |

**User's choice:** Webhook dispatches a GH Actions run.

---

## CI database

| Option | Description | Selected |
|--------|-------------|----------|
| testcontainers via Docker | GitHub-hosted runners already have Docker; reuse `tests/conftest.py`'s existing rung, no ci.yml service config | ✓ |
| Postgres service container in ci.yml | Add `services: postgres:17`, point `DARK_FACTORY_TEST_DATABASE_URL` at it | |
| Persistent Neon test branch | Real Neon branch via secret, shared across jobs | |

**User's choice:** testcontainers via Docker.

---

## Cross-machine proof shape

| Option | Description | Selected |
|--------|-------------|----------|
| Two processes, one job, shared DB | Subprocess A starts+pauses, local state wiped, subprocess B resumes+finishes, same testcontainers DB | ✓ |
| Two dependent GitHub Actions jobs | job A → job B via `needs:`, needs a durable cross-job database | |

**User's choice:** Two processes, one job, shared DB.

---

## QUAL-01 suite scope

| Option | Description | Selected |
|--------|-------------|----------|
| Wire up existing tests, close gaps | Enable `db` tier in CI so existing scattered db-tier tests run; add tests only for real gaps | ✓ |
| Build one new consolidated suite | Write a single new orchestration test file covering the full scenario list | |

**User's choice:** Wire up existing tests, close gaps.

---

## Dispatch target repo (follow-up, after user flagged the initial framing)

**Initial framing rejected by user:** "Dark Factory's own repo" as the dispatch
target — user noted Dark Factory is meant to be open-sourced; other deployers
must not dispatch into the original author's repo.

**Follow-up options presented:**

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable: deployer's own Dark Factory fork/install | New config value naming the deployer's own repo | (initially selected, superseded below) |
| Same repo as the GitHub App/token installation | Derive target from existing webhook installation context | |

**Then, after the assistant explained the actual architecture** (Dark Factory
installs as a pip package into a checkout of the *target* repo, not a
standalone "Dark Factory repo"), a corrected follow-up was asked:

| Option | Description | Selected |
|--------|-------------|----------|
| In the target repo itself | `resume.yml` lives in the same repo the run modifies; dispatch target read from the run's own persisted `repository.github_owner`/`github_repo` — no new config field | ✓ (final) |
| A separate 'ops' repo per deployer | Central orchestrator repo checks out the target repo as a CI workspace; needs a new `Settings.dispatch_repo` field | |

**User's choice:** In the target repo itself. This superseded the earlier
"configurable fork" answer once the actual deployment architecture was
clarified — no new config field needed at all, since `repository.github_owner`/
`github_repo` are already persisted per-run (Phase 10).

**Notes:** User asked "explain the flow" / "do they need clone dark factory or
copy files?" — assistant walked through the actual pip-install + hand-authored
`.dark-factory.yaml` + `.dark-factory/roles/*.yaml` deployment model (no
Dark Factory repo clone involved), which is what surfaced the correction above.

---

## Dispatch auth credential

| Option | Description | Selected |
|--------|-------------|----------|
| New Settings field, PAT/App token | `Settings.dispatch_github_token` (SecretStr), scoped to `actions:write`, kept separate from `github_token`/`github_webhook_secret` | ✓ |
| Reuse an existing token | Reuse whatever token already authenticates GitHub calls elsewhere | |

**User's choice:** New Settings field, PAT/App token.

---

## Build vs. defer the real dispatch wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Build the real dispatch call now | Phase 11 ships the actual webhook→GitHub-API call plus the `resume.yml` reference workflow | ✓ |
| Defer the real call, prove the mechanism only | Test-harness proof only, real call left for a later phase | |

**User's choice:** Build the real dispatch call now.

---

## Claude's Discretion

- Exact GitHub Actions API call shape (`githubkit`'s typed client vs. raw REST).
- Exact wiring point inside the webhook receiver's `submit_answer` call site,
  and fail-soft vs. fail-loud behavior on dispatch failure (lean fail-soft,
  matching the Phase 10 clarification-comment pattern).
- Exact scenario-by-scenario gap analysis of existing `tests/db/` coverage
  against QUAL-01's wording — left for research/planning.

## Deferred Ideas

- **`dark-factory init` scaffold command** — to generate `.dark-factory.yaml`,
  starter role instruction files, and a starter `resume.yml` workflow for a
  new deployer. Surfaced while explaining the deployment model; a real gap,
  but a new capability outside this phase's scope.
