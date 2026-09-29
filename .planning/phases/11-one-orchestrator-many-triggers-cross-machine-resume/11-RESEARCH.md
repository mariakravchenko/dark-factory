# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume - Research

**Researched:** 2026-09-29
**Domain:** GitHub Actions `workflow_dispatch` integration, CI database provisioning, cross-process orchestration proof, test-suite gap analysis
**Confidence:** HIGH

## Summary

This phase adds no new library dependency and no new architectural layer — it wires
one new outbound GitHub API call into an existing, already-tested webhook receiver,
turns on a test tier that already exists but has never run in CI, and writes two new
proof tests (a dispatch-call proof, and a two-subprocess cross-machine proof). Every
integration point named in CONTEXT.md's "Claude's Discretion" and "Also investigate"
sections was read from source this session, not inferred: the exact webhook call site,
the exact fail-soft precedent, the exact `githubkit` typed method, the exact config
path `dispatch_github_token` reads, and the exact set of `tests/db/` files that already
cover QUAL-01's scenario list.

The dispatch call is a straight extension of the pattern `dark_factory/github/client.py`
already established in Phase 10 (`gh.rest.actions.create_workflow_dispatch(owner, repo,
workflow_id, ref=..., inputs={...})` — a typed `githubkit` 0.16.1 method, confirmed
present in the installed package, following the exact keyword-merges-into-JSON-body
idiom `create_comment`/`pulls.create` already use). It is wired into
`webhook/app.py`'s `_resolve_and_act`, immediately after `submit_answer(...)` succeeds
and before the final `return _OK`, reading the dispatch target off
`RunState.workflow["repository"]` (a plain read via the already-webhook-allowed
`dark_factory.persistence.repositories.load_run_state`), and catching `GitHubError`
exactly the way `runner.py`'s clarification-comment post already does — fail soft,
never abort the already-committed `submit_answer` mutation.

The CI change (D-05) is corroborated: GitHub-hosted `ubuntu-latest` runners ship Docker
pre-installed and running, so `tests/conftest.py`'s existing testcontainers rung needs
no `services:` block. The `db`-tier scenario-gap audit (discretion item 3) found no
real content gap — all eight scenario nouns in QUAL-01's exact wording already have a
passing `tests/db/` test; the actual gap is that this 177-test tier has simply never
been selected in `ci.yml`. Two genuinely new pieces of test content are needed: a
dispatch-call assertion (in-process, `db`-tier, sibling of
`tests/db/test_webhook_resolves_answer.py`) and D-06's two-real-subprocess SC1 proof,
which is a real gap in kind (no existing test spawns two `dark-factory` CLI processes
against a testcontainers-provisioned database and asserts zero carryover) — Pitfall 1
below flags a marker-convention tension in this new test that the plan must resolve
explicitly.

**Primary recommendation:** Extend `GitHubClient` with one new method
(`dispatch_workflow`) and one new constructor path (`GitHubClient.for_dispatch(settings)`,
mirroring `from_settings` exactly but reading `dispatch_github_token`); wire the call
into `webhook/app.py._resolve_and_act` after `submit_answer` succeeds; flip `ci.yml`'s
test-selection line from `-m "unit or contract"` to `-m "unit or contract or db"` and
correct its comment; write two new tests (dispatch-call db-tier test, two-subprocess
SC1 proof) rather than rewriting any of the ~177 existing `tests/db/` tests.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trigger dispatch on answer received | API / Backend (webhook receiver process) | — | `webhook/app.py` already owns the one mutation (`submit_answer`); the new GitHub call is a side effect of that same request, not a new service |
| Workflow execution (resume) | CI (GitHub Actions runner) | API / Backend (`dark-factory` CLI as a library) | The CI job is a trigger only — it shells out to the identical `advance`/`drive` funnel the CLI/webhook already use; no CI-specific orchestration code (TRIG-01) |
| Run state re-materialization | Database / Storage (Neon) + Git (fresh worktree) | — | `RunState` is reconstructed from `runs` + `role_executions` columns alone (STATE-08); `ensure_worktree` re-derives the working tree from `base_branch`/`working_branch` columns, never from a carried-over local path |
| CI database provisioning | CI (GitHub Actions runner, Docker daemon) | — | testcontainers spins up `postgres:17-alpine` inside the same job; no external service, no `services:` block |
| Credential boundary for dispatch | API / Backend (`Settings.dispatch_github_token`) | — | A new, narrowly-scoped `SecretStr` field, never passed to a worker subprocess (`WORKER_ENV_ALLOWLIST` is a fixed list, structurally unaffected) |

## Package Legitimacy Audit

No new external package is installed by this phase. The one new outbound API surface
(`workflow_dispatch`) is reached through `githubkit>=0.16,<0.17`, already a locked,
installed dependency since Phase 10 (`10-01`: legitimacy-gate-approved despite a `SUS`
downloads-unknown flag, per `STATE.md`). No new `pip`/`npm`/`cargo` install is required
for this phase's scope — `Settings.dispatch_github_token`, `GitHubClient.dispatch_workflow`,
and the two new tests are all pure additions to already-vetted, already-installed code.

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none new this phase (githubkit's prior `SUS`
flag was human-approved in Phase 10 and is unaffected by this phase's additions).

## Architecture Patterns

### System Architecture Diagram

```
 Human replies on GitHub issue
            │
            ▼
 GitHub sends issue_comment webhook  ──(HMAC-signed)──▶  webhook/app.py
                                                          _handle_issue_comment
                                                                │
                                                    verify() ──▶ parse()
                                                                │
                                                     resolve_issue_comment()
                                                     (pure read, no write)
                                                                │
                                            ResolvedAnswer? ────┴──── UnresolvableComment
                                                   │                        │
                                                   ▼                        ▼
                                          submit_answer()               200 OK, ignored
                                     (one apply_transition write:
                                      WAITING_HUMAN → current_role)
                                                   │
                                          ── NEW THIS PHASE ──
                                                   ▼
                                   load_run_state(run_id)  (pure read)
                                                   │
                               state.workflow["repository"]
                              {github_owner, github_repo, base_branch}
                                                   │
                                                   ▼
                          GitHubClient.for_dispatch(settings)   (dispatch_github_token)
                                       .dispatch_workflow(
                                          owner, repo, "resume.yml",
                                          ref=base_branch,
                                          inputs={"run_id": str(run_id)})
                                                   │
                                    success ─┴─ GitHubError (fail-soft, logged, still 200)
                                                   │
                                                   ▼
                        GitHub Actions runner (fresh machine, workflow_dispatch trigger)
                                    resume.yml (in the DEPLOYER's own target repo)
                                    checkout → install dark-factory → `dark-factory resume <run_id>`
                                                   │
                                                   ▼
                                     cli.py resume() ──▶ drive(run_id)
                                     (identical funnel: same code path the
                                      local `run`/`resume` CLI commands use)
                                                   │
                                    load_run_state (Neon) + ensure_worktree (fresh git checkout)
                                                   │
                                                   ▼
                                COMPLETED (publish) or WAITING_HUMAN again (loop)
```

### Recommended Project Structure

No new top-level modules. All changes land inside existing files/packages:

```
src/dark_factory/
├── github/
│   ├── client.py           # + dispatch_workflow(), + GitHubClient.for_dispatch()
│   └── __init__.py          # (no change — GitHubClient already exported)
├── webhook/
│   └── app.py                # + dispatch call wired into _resolve_and_act, after submit_answer
├── config/
│   └── settings.py           # + dispatch_github_token: SecretStr | None = None
tests/
├── support/
│   └── fake_github.py         # + dispatch_workflow() scripted method + call log
├── db/
│   ├── test_webhook_dispatches_resume.py     # NEW — dispatch-call proof (sibling of test_webhook_resolves_answer.py)
│   └── test_cross_machine_resume.py          # NEW — D-06's two-subprocess SC1 proof
└── unit/
    └── test_settings.py                       # + dispatch_github_token field tests (mirrors github_webhook_secret's)
.github/workflows/
└── ci.yml                     # comment corrected (D-05); test-selection line gains "or db"
```

### Pattern 1: Typed `githubkit` REST call, keyword-merge-into-JSON-body idiom

**What:** Every outbound GitHub call in this codebase goes through the one wrapper
(`GitHubClient` in `src/dark_factory/github/client.py`) and calls a typed
`gh.rest.<group>.<method>(...)` function, letting keyword arguments merge directly into
the JSON request body when `data=` is not supplied.

**When to use:** Any new outbound GitHub REST call this phase adds.

**Example (verified against the installed `githubkit_schemas` v2026_03_10 package,
`.venv/lib/python3.12/site-packages/githubkit_schemas/v2026_03_10/rest/actions.py:18858-18911`,
and `githubkit_schemas/.../models/group_1319.py`):**
```python
# Source: dark_factory/github/client.py's existing create_comment/create_pull_request
# pattern (Phase 10), extended with the actions.create_workflow_dispatch signature
# confirmed present in the installed githubkit==0.16.1 package.
def dispatch_workflow(
    self, owner: str, repo: str, *, workflow_id: str, ref: str, run_id: str
) -> None:
    try:
        self._client.rest.actions.create_workflow_dispatch(
            owner,
            repo,
            workflow_id,
            ref=ref,
            inputs={"run_id": run_id},
        )
    except GitHubException as exc:
        self._raise_api_error(
            exc, endpoint=f"actions.create_workflow_dispatch {owner}/{repo}/{workflow_id}"
        )
```
`workflow_id` accepts either a numeric id or the workflow **file name** (`"resume.yml"`
per D-04) — confirmed in the endpoint's own docstring in the installed package:
"You can replace `workflow_id` with the workflow file name."

The response body is a genuine nuance worth flagging: by default this endpoint returns
`204 No Content` — `[CITED: github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids]`
confirms a **new, optional** `return_run_details` boolean was added 2026-02-19 that, if
passed, returns `200 OK` with `workflow_run_id`/`run_url`/`html_url`. Without it (the
recommended default for this phase — no observability requirement in scope), the call
returns no usable body; treat "did not raise" as the success signal, not `.parsed_data`.

### Pattern 2: Fail-soft on `GitHubError` after an already-committed mutation

**What:** A side-channel GitHub call that follows a durable state mutation must never
undo or fail that mutation — catch the error, log/record it, and return success anyway.

**When to use:** The new dispatch call, following the exact precedent
`orchestrator/runner.py` already established for the clarification-comment post.

**Example (verified — `src/dark_factory/orchestrator/runner.py:1657-1690`, quoted
verbatim above the relevant lines):**
```python
# Source: src/dark_factory/orchestrator/runner.py:1662-1690 (existing, Phase 10)
try:
    client = github_client_factory()
    ...
except GitHubError as exc:
    # Fail soft, never silent (D-08): the pause, the events and
    # the ``ask`` write still commit unchanged -- ...
    question_payload = {**question_payload, "clarification_comment_error": str(redact(...))}
else:
    clarification_comment_id = comment.id
```
The webhook's own new call site (`webhook/app.py`) must mirror this shape locally
(catch `GitHubError`, log via `structlog`, still `return _OK`) — it **cannot** import
`orchestrator/runner.py`'s private helpers (that module is not on the webhook package's
direct-import allowlist), so this is a parallel, independently-written fail-soft block,
not a shared function call.

### Anti-Patterns to Avoid

- **Reading `owner`/`repo` from `NormalizedTask.metadata` for the dispatch target:**
  `_github_issue_ref` (runner.py:208-232) reads `owner`/`repo`/`issue_number` from
  `state.normalized_task.metadata` for the *clarification-comment* GitHub call — this is
  a **different** field than the one D-02 locks for the dispatch target
  (`state.workflow["repository"]["github_owner"/"github_repo"]`, verified in
  `orchestrator/publish.py:287-310`). For a GitHub-sourced run with `repository:`
  configured, the two should agree in practice, but D-02's decision is explicit about
  which one to read — use `state.workflow["repository"]`, not task metadata.
- **Importing `dark_factory.github` (the bare package) instead of `dark_factory.github.client`:**
  the webhook direct-import allowlist (`tests/unit/test_webhook_process_boundary.py::_WEBHOOK_DIRECT_ALLOWED`)
  names `dark_factory.github.client` specifically — `app.py` already imports
  `from dark_factory.github.client import GitHubClient` this exact way; new dispatch code
  must use the identical import path or the guard test fails.
- **Adding `dispatch_github_token` to `WORKER_ENV_ALLOWLIST` or `build_worker_env`:**
  it must never reach a worker subprocess — this field belongs only to the webhook
  receiver process's own `Settings`, exactly like `github_webhook_secret`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Triggering a GitHub Actions run remotely | A raw `httpx.post` to the dispatches endpoint | `gh.rest.actions.create_workflow_dispatch(...)` | Matches every other outbound call in `github/client.py`; gets typed request/response models, auth header handling, and `GitHubException` mapping for free |
| Verifying "did Docker exist on this CI runner" | A new probe or `services:` block | `tests/conftest.py`'s existing testcontainers rung, unmodified | GitHub-hosted `ubuntu-latest` ships Docker Engine pre-installed and running — `[CITED: docs.github.com/en/actions/reference/runners/github-hosted-runners]`, `[CITED: docker.com/blog/running-testcontainers-tests-using-github-actions]` |
| Proving "no local state carried over" | A fabricated two-job GitHub Actions `needs:` pipeline | Two real OS subprocesses (`tests/support/subprocess_runner.py`'s `spawn`/`popen` + `child_env`, already built in Phase 2) inside one CI job, pointed at the same testcontainers Postgres | D-06 explicitly rejects the two-job approach (would need a database outliving one job's testcontainers instance); the existing subprocess harness already proves "shares only the database" for SC2 (`tests/integration/test_fresh_process_resume.py`) and is the direct reusable asset for SC1 |

**Key insight:** every piece of infrastructure this phase needs (typed GitHub client,
subprocess-isolation test harness, testcontainers provisioning ladder, fail-soft
GitHub-error precedent) already exists in this codebase from Phases 1, 2 and 10. This
phase's job is wiring and enabling, not building.

## Common Pitfalls

### Pitfall 1: The new SC1 (D-06) test's marker breaks an established convention — must be resolved explicitly

**What goes wrong:** Every existing test in this codebase that spawns `dark-factory` as
a real OS subprocess (`tests/support/subprocess_runner.py`'s `spawn`/`popen`) lives under
`tests/integration/` and carries `pytestmark = pytest.mark.integration`
(`tests/integration/test_fresh_process_resume.py` is the closest analog to D-06's proof
and is marked `integration`). But `ci.yml`'s `integration` tier stays **excluded** from
CI even after D-05 (CONTEXT.md is explicit: "still no agent-CLI credentials
(unrelated — the `integration` tier stays excluded from CI for that reason)"). D-05 also
explicitly says: "The `db`-tier test suite (**and the cross-machine proof below**) runs
in `ci.yml` via the existing testcontainers probe rung" — grouping the new SC1 proof
with the `db` tier, not `integration`.

**Why it happens:** The two markers' historical differentiator in this codebase is not
strictly "spawns a subprocess" — it is closer to "needs only PostgreSQL" (`db`) vs
"drives the CLI as a subprocess, some of which need real agent-CLI credentials"
(`integration`). D-06's new test needs only PostgreSQL (`FakeWorker`, no agent
credentials) but does spawn two real subprocesses — mechanically identical to an
`integration`-marked test, but requirement-wise it belongs with `db`.

**How to avoid:** Mark the new D-06 test `@pytest.mark.db` (not `integration`), and
place it under `tests/db/` (not `tests/integration/`) — matching D-05's explicit
wording — with a docstring that names this as a deliberate, documented deviation from
the Phase 2 "subprocess ⇒ integration" convention, citing D-05/D-06. Do **not** widen
`ci.yml`'s selection to include `integration` broadly; that would pull in tests that
genuinely need agent-CLI credentials the hosted runner does not have.

**Warning signs:** If the new test is marked `integration`, it silently never runs in
CI (defeating D-06's whole purpose) even though the plan's checklist says "done."

### Pitfall 2: `ci.yml`'s 15-minute job timeout may not survive adding ~180 db-tier tests + testcontainers pull

**What goes wrong:** `ci.yml`'s `quality` job currently has `timeout-minutes: 15` and
runs only `unit`/`contract` tests plus lint/mypy. Adding the `db` marker pulls in the
entire `tests/db/` tree (177 test functions counted this session across 41 files) plus
Alembic migrations, a `postgres:17-alpine` container pull/start, and — per D-06 — two
extra real subprocess spawns for the cross-machine proof.

**Why it happens:** The existing 15-minute budget was sized for a database-free run;
D-05 is a genuine scope increase to what runs in that job.

**How to avoid:** Budget headroom in the plan — either raise `timeout-minutes` on the
`quality` job (a concrete number requires a first real CI run to calibrate; this is an
`[ASSUMED]` risk, not a measured one) or split db-tier execution into its own job/step
with its own timeout. Flag this as a checkpoint for the plan to revisit after the first
green/red CI run, rather than guessing a number now.

### Pitfall 3: `_write_config_tree`'s shared fixture tree has no `repository.github_owner`/`github_repo` by default

**What goes wrong:** `tests/conftest.py::_write_config_tree` (the shared `.dark-factory/`
tree builder ~40 other db tests reuse) writes `repository: {base_branch: main}` with no
`github_owner`/`github_repo` keys — a dispatch-focused test that forgets to overwrite
this block (the established "build-then-overwrite" idiom `test_publish_step.py` and
`test_ask_posts_comment.py` already use) will find `state.workflow["repository"]` has no
owner/repo and the dispatch call is silently skipped (same shape as GIT-03's "no owner
configured" branch in `publish.py`).

**How to avoid:** The new dispatch test must overwrite the generated
`.dark-factory.yaml`'s `repository:` block with `github_owner`/`github_repo` set,
exactly like `test_publish_step.py`/`test_ask_posts_comment.py`/`test_webhook_resolves_answer.py`
already do — this is the established idiom, not a new one to invent.

### Pitfall 4: Confusing the fine-grained PAT permission name with the classic PAT scope

**What goes wrong:** CONTEXT.md's D-03 names the credential's required scope as
`actions: write` — this is the **fine-grained personal access token** permission name.
For a **classic** PAT, GitHub's own REST docs for this endpoint instead require the
broader `repo` scope `[CITED: docs.github.com/en/rest/actions/workflows — "Create a
workflow dispatch event"]`. A deployer who reads D-03 literally and tries to find an
"actions: write" checkbox on a classic-PAT creation screen will not find one.

**How to avoid:** The `resume.yml`/deployer documentation this phase writes (D-04) should
recommend a **fine-grained PAT** scoped to `Actions: Read and write` on the target repo
only (matching D-03's least-privilege intent precisely), and note the classic-PAT
alternative (`repo` scope, broader) only as a fallback.

## Code Examples

### Settings field addition (mirrors the existing `github_webhook_secret` precedent exactly)

```python
# Source: src/dark_factory/config/settings.py (existing pattern, verified read this
# session — dispatch_github_token follows this shape verbatim)
github_webhook_secret: SecretStr | None = None   # existing
dispatch_github_token: SecretStr | None = None    # NEW — same optional-SecretStr shape
```
`known_secret_values()`'s `model_fields` walk (already generic, no hardcoded field list)
covers the new field automatically — no redaction-path code change needed. The env var
name pydantic-settings derives by default is `DISPATCH_GITHUB_TOKEN` (no `env_prefix`
configured on `Settings.model_config`, confirmed by reading the existing
`SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")` — no
prefix key present).

### The exact webhook call site (verified — `src/dark_factory/webhook/app.py:202-223`)

```python
# Source: src/dark_factory/webhook/app.py's _resolve_and_act (existing, quoted verbatim)
try:
    submit_answer(
        outcome.run_id,
        outcome.answer,
        session_factory=session_factory,
        github_comment_id=outcome.github_comment_id,
    )
except (NotWaitingForHuman, NoPendingInteraction) as exc:
    ...
    return _OK
except LeaseNotAcquired:
    return _RETRY_LATER
except Exception:
    ...
    return _SERVER_ERROR
return _OK   # <-- NEW dispatch call goes immediately before this line
```
The new block reads `load_run_state(session_factory(), outcome.run_id)` for
`workflow["repository"]`, constructs a dispatch-scoped `GitHubClient`, calls
`dispatch_workflow(...)`, and catches `GitHubError` — still falling through to
`return _OK` either way, per Pattern 2 above.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `workflow_dispatch` API returns only `204 No Content` | Optional `return_run_details=true` param returns `workflow_run_id`/`run_url`/`html_url` in a `200 OK` body | 2026-02-19 `[CITED: github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids]` | Not required for this phase's MVP scope (no dispatched-run observability requirement); worth a one-line note in the dispatch method's docstring for a future OBS phase (Phase 12) to pick up |

**Deprecated/outdated:** none relevant — `githubkit` 0.16.1's typed surface for this
endpoint is current and already installed.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ci.yml`'s `timeout-minutes: 15` will need raising once the `db` tier + two new subprocess-spawning tests are added | Pitfall 2 | CI job times out mid-run, looks like a flaky failure rather than a budget problem; plan should treat the exact number as a post-first-run calibration, not a locked value |
| A2 | A fine-grained PAT scoped to `Actions: Read and write` is the correct credential shape for `dispatch_github_token`, matching D-03's least-privilege intent | Pitfall 4 | If a deployer instead provisions a classic PAT with the full `repo` scope, dispatch still works (GitHub's docs confirm `repo` scope suffices for classic PATs) but grants more privilege than D-03 intended — a documentation nit, not a functional blocker |

## Open Questions

1. **Should `GitHubClient.dispatch_workflow` request `return_run_details=True` for
   future observability, or omit it entirely?**
   - What we know: the parameter exists (2026-02-19 GitHub API change) and would let a
     future Phase 12 (`OBS-01`/`OBS-02`) surface the dispatched workflow run's URL
     without a second API call.
   - What's unclear: whether `githubkit` 0.16.1's typed `inputs`/body model for this
     endpoint already exposes `return_run_details` as a first-class kwarg or requires
     passing it through the generic `data=` escape hatch — not verified this session
     (out of this phase's scope to resolve; Phase 11 needs no run-id observability).
   - Recommendation: omit it for this phase (simplest correct MVP); leave a one-line
     forward-reference comment for Phase 12 to pick up if it wants dispatched-run
     visibility in `dark-factory status`.

2. **Exact CI job timeout-minutes value for the expanded `quality` job.**
   - What we know: 177 existing `tests/db/` tests, plus Alembic migrations, plus a
     Postgres container pull/start, plus D-06's two extra subprocess spawns, all now run
     where only `unit`/`contract` ran before.
   - What's unclear: the actual wall-clock cost on a GitHub-hosted runner — no measured
     figure exists yet.
   - Recommendation: the plan should include a checkpoint after the first real CI run to
     confirm the timeout is sufficient, rather than guessing a number now.

## Environment Availability

| Dependency | Required By | Available (local dev sandbox, this session) | Version | Fallback |
|------------|------------|:---:|---------|----------|
| Docker daemon | testcontainers rung (`db` tier, local dev) | ✗ (this sandbox) | — | `pytest-postgresql` rung, or `DARK_FACTORY_TEST_DATABASE_URL` |
| Docker daemon | testcontainers rung (`db` tier, **CI**) | N/A (not probed from this sandbox) | — | `[CITED]` GitHub-hosted `ubuntu-latest` ships Docker pre-installed and running — no fallback needed in CI |
| `initdb` (local PostgreSQL 17) | `pytest-postgresql` rung | ✗ | — | testcontainers or external URL |
| `DARK_FACTORY_TEST_DATABASE_URL` | external-Postgres rung | ✗ (unset) | — | — |
| `githubkit` 0.16.1 | dispatch call, all GitHub calls | ✓ (installed in `.venv`) | 0.16.1 (confirmed via `importlib.metadata`) | — |
| `uv` | dependency management | ✓ | 0.12.7 | — |
| GitHub Actions `ubuntu-latest` Docker | D-05/D-06 CI db tier | N/A locally | — | — |

**Missing dependencies with no fallback:** none — every rung in the probe ladder has a
documented fallback, and CI's own rung (testcontainers on a Docker-equipped hosted
runner) needs no fallback per the cited GitHub/Docker documentation.

**Missing dependencies with fallback:** local dev sandbox has neither Docker nor a local
`initdb`; this is expected (matches `01-RESEARCH.md`'s original "Environment
Availability" finding on the same machine) and does not block CI-side work, which is
this phase's actual target.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (confirmed installed, matches `pyproject.toml` pin) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (markers: `unit`, `db`, `integration`, `contract`) |
| Quick run command | `uv run pytest -q -m "unit or contract"` |
| Full suite command | `uv run pytest -q` (all tiers; needs a reachable PostgreSQL 17) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRIG-01 | CLI/webhook/CI all funnel into `advance(run_id)`, no CI-only path | db (new) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py` | ❌ new this phase |
| TRIG-04 | Run continues across local→CI boundary via Neon alone | db (new) | same as above | ❌ new this phase |
| HITL-06 | Resume on a different machine/process than the one that started it | db (new, extends existing SC2 idiom) | same as above | ❌ new this phase (existing sibling: `tests/integration/test_fresh_process_resume.py`) |
| HITL-06 (dispatch half) | webhook receiver dispatches a real `workflow_dispatch` after `submit_answer` | db (new) | `uv run pytest -q -m db tests/db/test_webhook_dispatches_resume.py` | ❌ new this phase (sibling: `tests/db/test_webhook_resolves_answer.py`) |
| QUAL-01 | Role transitions | db (existing) | `uv run pytest -q -m db tests/db/test_four_role_pipeline.py tests/db/test_transition_atomic.py` | ✅ |
| QUAL-01 | Artifact handoffs | db (existing) | `uv run pytest -q -m db tests/db/test_artifact_handoff.py` | ✅ |
| QUAL-01 | Pause/resume | db (existing) | `uv run pytest -q -m db tests/db/test_pause_mechanism_generic.py tests/db/test_resume_first_advance.py` | ✅ |
| QUAL-01 | QA rejection | db (existing) | `uv run pytest -q -m db tests/db/test_qa_bounce.py` | ✅ |
| QUAL-01 | Developer retries | db (existing) | `uv run pytest -q -m db tests/db/test_feedback_reaches_developer.py` | ✅ |
| QUAL-01 | Quality-gate retries | db (existing) | `uv run pytest -q -m db tests/db/test_quality_gate_gates_the_run.py` | ✅ |
| QUAL-01 | Retry exhaustion | db (existing) | `uv run pytest -q -m db tests/db/test_iteration_cap_exhaustion.py tests/db/test_loop04_adjacency.py` | ✅ |
| QUAL-01 | Publishing | db (existing) | `uv run pytest -q -m db tests/db/test_publish_step.py tests/db/test_publish_idempotency.py` | ✅ |
| QUAL-01 | "runs green in CI with no external AI calls, no live worker credentials" | CI config change (D-05) | `.github/workflows/ci.yml` `db`-tier selection | ❌ CI never selects `db` tier today |

### Sampling Rate
- **Per task commit:** `uv run pytest -q -m "unit or contract or db"` (once Docker/testcontainers is
  available locally; falls back to `unit or contract` only in a dev sandbox with no
  Postgres rung available, per the existing probe ladder's own hard-fail design)
- **Per wave merge:** full suite (`uv run pytest -q`)
- **Phase gate:** `.github/workflows/ci.yml`'s `db`-tier selection green, plus a real
  (not simulated) GitHub Actions dispatch — CONTEXT.md D-01 is explicit this is "a new,
  real production code path — not just a test harness/proof."

### Wave 0 Gaps
- [ ] `tests/db/test_webhook_dispatches_resume.py` — covers HITL-06 (dispatch half),
      sibling of `tests/db/test_webhook_resolves_answer.py`
- [ ] `tests/db/test_cross_machine_resume.py` — covers TRIG-01/TRIG-04/HITL-06 (D-06's
      SC1 proof), reusing `tests/support/subprocess_runner.py`'s `spawn`/`child_env`
- [ ] `tests/support/fake_github.py` — add a scripted `dispatch_workflow()` method +
      call-log entry (mirrors its existing four methods exactly)
- [ ] `tests/unit/test_settings.py` — add `dispatch_github_token`-specific tests
      mirroring the existing `github_webhook_secret` test set
      (`test_known_secret_values_maps_*_to_its_field_name`,
      `test_known_secret_values_omits_unset_*`)
- [ ] `.github/workflows/ci.yml` — comment correction + `-m "unit or contract"` →
      `-m "unit or contract or db"`, `timeout-minutes` reviewed (Pitfall 2)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (inbound, unchanged) | HMAC signature verification via `githubkit.webhooks.verify` — already shipped Phase 10, untouched by this phase |
| V3 Session Management | no | stateless webhook request; no session concept |
| V4 Access Control | yes (new, outbound) | `dispatch_github_token` is a narrowly-scoped credential (fine-grained PAT, `Actions: Read and write` only — Pitfall 4), never the same token as `github_token`/`github_webhook_secret`, following the established one-`SecretStr`-per-purpose pattern |
| V5 Input Validation | yes | `run_id` passed into the dispatch `inputs` is already a validated `UUID` object (`outcome.run_id: UUID` on `ResolvedAnswer`) before it is stringified — no free-text injection surface into the dispatched workflow's inputs |
| V6 Cryptography | no new surface | no new cryptographic primitive introduced; HMAC verification unchanged |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Credential leakage via a GitHub API error message echoing request headers | Information Disclosure | `_raise_api_error`'s existing `redact()` call, unchanged pattern, applies automatically to the new `dispatch_workflow` method since it reuses the same `_raise_api_error` helper |
| A dispatch call silently failing and masking a real outage from the operator | Repudiation / availability | Fail-soft (never raise to the caller) but must still `_log.warning`/`_log.error` with the redacted exception text — mirrors `runner.py`'s `question_payload["clarification_comment_error"]` precedent, which records the failure text rather than discarding it silently |
| Overly broad dispatch credential (classic PAT `repo` scope instead of fine-grained `Actions: Read and write`) | Elevation of Privilege | Document the fine-grained PAT path as primary in the `resume.yml` deployer guidance (D-04), classic PAT as a documented fallback only (Pitfall 4) |
| `dispatch_github_token` reaching a worker subprocess | Information Disclosure | Structurally impossible today — `WORKER_ENV_ALLOWLIST` (`src/dark_factory/tools/env.py`) is a fixed, hand-enumerated tuple with no reference to `Settings` field names; verify no plan task adds it there |

## Sources

### Primary (HIGH confidence — read from source this session)
- `src/dark_factory/github/client.py` — `GitHubClient`'s existing wrapper shape, error
  hierarchy, `from_settings` pattern
- `src/dark_factory/webhook/app.py` — exact `_resolve_and_act` call site, `build_app`
  injection seam, fail-soft precedent shape
- `src/dark_factory/webhook/__init__.py` — the "must never reference advance/drive"
  invariant, verbatim
- `src/dark_factory/config/settings.py` — existing `SecretStr` field pattern,
  `known_secret_values()` implementation
- `src/dark_factory/orchestrator/runner.py` (lines 160-234, 960-1719) — `_github_issue_ref`,
  the clarification-comment fail-soft block (quoted verbatim), `default_github_client_factory`
- `src/dark_factory/orchestrator/publish.py` (lines 260-315) — `state.workflow["repository"]`
  field names (`github_owner`, `github_repo`, `base_branch`), quoted verbatim
- `src/dark_factory/orchestrator/answers.py` — `submit_answer`'s exact signature/return type
- `src/dark_factory/persistence/repositories.py` (lines 60-200) — `RunState`/`load_run_state`
  shape, confirming the webhook's read path
- `src/dark_factory/webhook/resolve.py` — `resolve_issue_comment`'s existing repository-field
  source (contrasted with D-02's chosen source, Anti-Pattern note above)
- `src/dark_factory/tools/env.py` (lines 36-67) — `WORKER_ENV_ALLOWLIST`, confirming
  structural independence from `Settings` field additions
- `tests/unit/test_webhook_process_boundary.py` — the exact D-01/D-02 import-graph guard,
  its `_WEBHOOK_DIRECT_ALLOWED` set (confirms `dark_factory.github.client`,
  `dark_factory.persistence.repositories`, `dark_factory.config.settings` are all
  already allowed with zero widening needed)
- `tests/support/fake_github.py` — existing `FakeGitHubClient`'s four-method surface,
  the shape a fifth (`dispatch_workflow`) must follow
- `tests/support/subprocess_runner.py` — `spawn`/`popen`/`child_env`/`run_id_from_stdout`/`wait_for`,
  the reusable asset for D-06's SC1 proof
- `tests/integration/test_fresh_process_resume.py` — the closest existing analog to D-06,
  and the source of the marker-convention tension flagged in Pitfall 1
- `tests/db/test_webhook_resolves_answer.py`, `test_ask_posts_comment.py`,
  `test_publish_step.py`, `test_qa_bounce.py`, `test_feedback_reaches_developer.py`,
  `test_quality_gate_gates_the_run.py`, `test_iteration_cap_exhaustion.py`,
  `test_loop04_adjacency.py`, `test_four_role_pipeline.py`, `test_artifact_handoff.py`,
  `test_publish_idempotency.py`, `test_resume_first_advance.py`,
  `test_pause_mechanism_generic.py`, `test_transition_atomic.py` — docstrings read to
  confirm QUAL-01 scenario coverage
- `tests/conftest.py` — the three-rung provisioning ladder, `_write_config_tree`'s
  default `repository:` block (no `github_owner`/`github_repo` by default — Pitfall 3)
- `.github/workflows/ci.yml` — the exact current comment and job structure (D-05 target)
- `.venv/lib/python3.12/site-packages/githubkit_schemas/v2026_03_10/rest/actions.py`
  (lines 18827-18911) and `.../models/group_1319.py` — `create_workflow_dispatch`'s
  real, installed typed signature, confirmed via `importlib.metadata.version("githubkit") == "0.16.1"`
- `.venv/.../models/group_0316.py` — `WorkflowDispatchResponse`'s fields
- `pyproject.toml` — `githubkit>=0.16,<0.17` pin, `testcontainers[postgres]`/`pytest-postgresql`
  dev deps, `[tool.pytest.ini_options]` marker definitions, `webhook` extra
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`,
  `.planning/phases/11-.../11-CONTEXT.md` — phase scope, requirement text, decisions

### Secondary (MEDIUM confidence — WebSearch, cross-checked against official pages)
- `[CITED: docs.github.com/en/actions/reference/runners/github-hosted-runners]` — GitHub-hosted
  runner images
- `[CITED: docker.com/blog/running-testcontainers-tests-using-github-actions]` — Docker
  pre-installed on `ubuntu-latest`, no `services:` block needed
- `[CITED: docs.github.com/en/rest/actions/workflows]` — "Create a workflow dispatch event":
  classic PAT `repo` scope, GitHub App `actions:write` permission
- `[CITED: github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids]` —
  the `return_run_details` parameter and its 204→200 behavior change

### Tertiary (LOW confidence)
- None — every claim above is either read from installed source this session or backed
  by an official GitHub/Docker page.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; existing `githubkit` 0.16.1 method confirmed
  present in the installed package by direct source inspection
- Architecture: HIGH — every integration point (call site, credential field, import
  allowlist, config-snapshot field names) was read from source this session, not inferred
- Pitfalls: HIGH for Pitfalls 3/4 (directly verified against source/docs); MEDIUM for
  Pitfall 1 (a genuine judgment call the plan must make explicitly, not a verified fact)
  and Pitfall 2 (an `[ASSUMED]` risk with no measured CI timing yet)

**Research date:** 2026-09-29
**Valid until:** 30 days (stable, internal-codebase-driven research; the one external
dependency — GitHub's REST API shape — moves slowly and is version-pinned via `githubkit`)
