---
phase: "11"
slug: "one-orchestrator-many-triggers-cross-machine-resume"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: "2026-10-01"
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

This register is reconstructed from the `<threat_model>` block each of the phase's 7 plans
authored at plan time (11-01 through 11-07) — no SECURITY.md existed before this audit. Every
plan carried a complete STRIDE register with a disposition already assigned, so this is a
**verification pass** (confirm each `mitigate` disposition's control actually shipped), not a
from-scratch threat-modeling exercise.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Dark Factory -> GitHub Actions API (`workflow_dispatch`) | A new outbound call carrying a run id, authenticated with `dispatch_github_token`. Request inputs are publicly visible (to anyone with repository read access) in the dispatched run's Actions UI/logs. | run id (opaque UUID) only |
| Dark Factory -> worker subprocess | `dispatch_github_token` joins `database_url`, `github_token`, `github_webhook_secret` as an infrastructure credential that must never reach a worker's environment, prompt, artifact, event payload, or log. | infrastructure credentials (must never cross) |
| GitHub API error response -> Dark Factory error message | A GitHub error response can echo request headers, including `Authorization`. | potentially the dispatch token, if unredacted |
| Test process -> spawned child processes (db-tier cross-machine proof, 11-03; import-guard proof, 11-06) | Child environments are built from explicit allowlists, never `os.environ.copy()`. | test database URL only, never ambient secrets |
| This documentation (README) -> a deployer's GitHub account / CI environment | README tells a human which token/scope to create and which secrets to inject into their own Actions job. Over-granting here is a real privilege escalation in someone else's account, caused by prose. | credential *names* and *scopes*, never values |
| This documentation -> a deployer's runner | The reference `resume.yml` and 11-07's worker-runtime table tell a deployer which CLI binary must be on `PATH`. Naming a real install command would be an unverifiable supply-chain recommendation. | binary names only, never install commands |
| A deployer's target repository -> `workflow_dispatch` | Anyone with `actions: write` on the target repository can dispatch `resume.yml` with an arbitrary `run_id`. | run id only |
| process startup -> `Settings()` (11-06) | Moving *when* `Settings()` is constructed (eager module import -> lazy factory call) must not remove the WR-02 missing-credential startup diagnostics. | infrastructure credentials, same boundary, different timing |

---

## Threat Register

Consolidated from all 7 plans' plan-time STRIDE registers. A **Plan** column disambiguates:
threat IDs were not allocated from one counter across 11-01–11-05 (a repeat of the Phase 9 ID-reuse
issue noted in STATE.md — see Process Note below); 11-06/11-07 corrected this by continuing
numbering from the phase-wide high-water mark (`T-11-23`). All entries below were already
`mitigate`/`accept` at plan time; none were found `open` during this audit (grep-level, ASVS L1:
each `mitigate` row's cited test file/command was confirmed to exist and its owning plan's
SUMMARY.md reports it passing).

| Threat ID | Plan | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|------|----------|-----------|----------|-------------|------------|--------|
| T-11-01 | 11-01 | Information Disclosure | `GitHubClient.dispatch_workflow` error path | high | mitigate | Reuses `_raise_api_error` → `redact(..., known_secrets=...)` unchanged; `for_dispatch` passes `known_secret_values()` in. | closed |
| T-11-01 | 11-02 | Information Disclosure | `webhook.dispatch.failed` log detail | high | mitigate | Logged `detail` is `str(exc)` on an already-redacted `GitHubApiError`; `tests/unit/test_log_redaction.py` in verify set. | closed |
| T-11-02 | 11-01 | Elevation of Privilege | `dispatch_github_token` reaching a worker subprocess | high | mitigate | `WORKER_ENV_ALLOWLIST` has no reference to the field; `tests/unit/test_dispatch_token_never_reaches_a_worker.py` imports the allowlist as a value and asserts a one-reader set (`github/client.py` only). | closed |
| T-11-03 | 11-01 | Information Disclosure | `workflow_dispatch` inputs | high | mitigate | `inputs` carries exactly one key (`run_id`, opaque UUID); whole-dict equality assertion in Task 1's test fails on any later content addition. | closed |
| T-11-04 | 11-01 | Elevation of Privilege | over-broad dispatch credential provisioned by the deployer | medium | mitigate | Least-privilege shape documented in `user_setup`, `.env.example`, and README (11-05). | closed |
| T-11-04 | 11-05 | Elevation of Privilege | the documented dispatch-credential scope | high | mitigate | README leads with fine-grained PAT / one repo / `Actions: Read and write`; classic PAT named only as a fallback. | closed |
| T-11-05 | 11-01 | Repudiation | a dispatch call failing silently, masking a real outage | medium | mitigate | Success path logs `webhook.dispatch.requested`; startup logs `missing_dispatch_github_token` when unset. | closed |
| T-11-06 | 11-01 | Tampering | the run id crossing into the dispatched workflow | low | accept | `run_id` is a validated UUID; `dark-factory resume` on an unknown/malformed id exits 2 before touching state. Residual: an `actions: write` holder dispatching with an arbitrary uuid — strictly less capability than they already have. | closed (accepted) |
| T-11-06 | 11-02 | Repudiation | a dispatch that silently never fires | high | mitigate | All three non-dispatching branches emit a named, distinct log record; `structlog.testing.capture_logs()` assertions in both plans' verify sets. | closed |
| T-11-07 | 11-02 | Denial of Service | a 5xx on dispatch failure inviting endless GitHub redelivery | medium | mitigate | Failure path returns 200 (answer already committed); redelivery takes the no-op arm, documented inline against a later "fix into a retry loop" mistake. | closed |
| T-11-08 | 11-02 | Spoofing | an unsigned/attacker-authored comment triggering a dispatch | high | mitigate | Dispatch block is structurally placed after signature check + `submit_answer` success; `test_an_ignored_or_unsigned_delivery_never_dispatches` pins an empty call log. | closed |
| T-11-09 | 11-02 | Elevation of Privilege | `MissingGitHubCredentialError` misreported as an API failure | low | mitigate | Credential-missing branch ordered before `except GitHubError`, with distinct event names/reason constants, asserted in acceptance criteria. | closed |
| T-11-10 | 11-03 | Information Disclosure | spawned child processes' environment | high | mitigate | `child_env` builds from a fixed allowlist tuple, never `os.environ.copy()`; guarded project-wide by `tests/unit/test_no_environ_copy.py`. | closed |
| T-11-11 | 11-03 | Information Disclosure | test database URL in captured output | medium | mitigate | URL never printed/asserted/persisted; captured child stdout/stderr already routes through the redacting `structlog` processor chain. | closed |
| T-11-12 | 11-03 | Tampering | a second orchestration implementation appearing silently | high | mitigate | AST guard pins `advance`/`drive` to one defining module + one call-site allowlist, with anti-vacuity assertions (fails on rename, not just removal). | closed |
| T-11-13 | 11-03 | Repudiation | a proof that silently never runs | high | mitigate | `--collect-only` under `-m db` with `fails_when: no tests collected`, so non-selection is a red verify, not an invisible gap. | closed |
| T-11-14 | 11-03 | Denial of Service | a spawned child hanging instead of pausing | low | mitigate | `subprocess.run(timeout=...)`; `TimeoutExpired` absence asserted explicitly. | closed |
| T-11-15 | 11-04 | Repudiation | a coverage claim CI never exercises | high | mitigate | `test_ci_runs_the_database_tier` parses `ci.yml` as YAML and asserts the `db`-marker step exists; guard itself runs in the always-selected `unit` tier. | closed |
| T-11-16 | 11-04 | Elevation of Privilege | agent-CLI credentials pulled into CI via the `integration` tier | high | mitigate | `integration` marker stays excluded from every CI selector; asserted no `run:` string contains the token `integration`. | closed |
| T-11-17 | 11-04 | Tampering | the `postgres:17-alpine` image pulled at CI time | medium | accept | Docker Official image via the pre-existing testcontainers rung, unmodified by this plan; digest-pinning out of scope (shared probe ladder, D-05 explicit "reused as-is"). | closed (accepted) |
| T-11-18 | 11-04 | Denial of Service | the expanded CI job exhausting its time budget | medium | mitigate | `[ASSUMED]` `timeout-minutes: 20` (step) / `30` (job), explicitly flagged for post-first-run calibration via `<human-check>` (still outstanding — see Manual-Only below). | closed (mitigation in place; measured-value follow-up tracked, non-blocking) |
| T-11-19 | 11-04 | Information Disclosure | test database URL in CI logs | low | accept | Ephemeral testcontainers URL on the runner's own loopback, throwaway credential, dies with the job; not an infrastructure secret. | closed (accepted) |
| T-11-20 | 11-05 | Elevation of Privilege | the reference workflow's own `permissions` | medium | mitigate | Reference workflow declares `permissions: contents: read` explicitly rather than inheriting repo defaults. | closed |
| T-11-21 | 11-05 | Information Disclosure | secrets in the reference workflow | medium | mitigate | Every credential referenced as `${{ secrets.NAME }}` via `env:` on the one step needing it; never inlined/echoed. | closed |
| T-11-22 | 11-05 | Spoofing | an arbitrary `run_id` dispatched by anyone with `actions: write` | low | accept | Same rationale as T-11-06/11-01: `dark-factory resume` on an unknown id exits 2 before touching state. | closed (accepted) |
| T-11-23 | 11-05 | Repudiation | documentation drifting away from the code | medium | mitigate | Unit-tier guard asserts the reference workflow's structure and credential-name agreement with `.env.example`; prose sourced verbatim from 11-CONTEXT.md. | closed |
| T-11-24 | 11-06 | Denial of Service | the WR-02 startup credential diagnostics, if construction is deferred | medium | mitigate | `build_app`'s body (incl. 3 startup diagnostics) left byte-unchanged; uvicorn `--factory` still calls `build_app()` once at process startup, so all three records still fire once per process. `tests/unit/test_webhook_signature.py`'s 4 startup-check tests + `test_dispatch_token_never_reaches_a_worker.py` in verify set. | closed |
| T-11-25 | 11-06 | Information Disclosure | the child-process environment built by the new import guard | medium | mitigate | Explicit named allowlist tuple, `DATABASE_URL`/`DATABASE_URL_DIRECT` absent (not blanked); positive control fails if sanitization ever stops working. | closed |
| T-11-26 | 11-06 | Tampering | `dark_factory.webhook.app`'s public module surface | low | accept | Breaking change for any out-of-repo ASGI config pointing at the old attribute; accepted — not published to a package index, only in-repo references (2 docstrings) corrected, wrong target fails loudly at uvicorn startup. | closed (accepted) |
| T-11-27 | 11-06 | Spoofing | `/webhooks/github` signature verification ordering | low | accept | Unchanged by this plan; re-asserted via `tests/unit/test_webhook_signature.py` in verify set. | closed (accepted) |
| T-11-28 | 11-07 | Tampering | install guidance inside README's copied-verbatim reference block | high | mitigate | No install command/package/registry named for any runtime — only the `PATH` binary (derived from `LIVE_RUNTIMES`), pointing at that runtime's own docs. Drift guard (Task 2) binds documented binary names to the registry. | closed |
| T-11-29 | 11-07 | Elevation of Privilege | the reference workflow's step surface | medium | mitigate | New install-guidance step shipped **commented out** — paste-time surface unchanged until a deployer deliberately enables it; no `if:` key added, no second resume invocation. | closed |
| T-11-30 | 11-07 | Information Disclosure | README's worker-runtime credential table | medium | mitigate | Column restricted to variable *names* (upper-cased `Settings` field), never values; guard assertions check only the name spelling. | closed |
| T-11-31 | 11-07 | Repudiation | documentation drift after a fourth worker adapter is added | low | mitigate | Tests A/B parametrized over `LIVE_RUNTIMES.values()` — a new adapter fails the unit tier until README documents its binary + credential. | closed |
| T-11-SC | all 7 plans | Tampering | package-manager installs | low | accept | Asserted independently and consistently in every plan: zero `pip`/`npm`/`cargo`/`uv add` installs anywhere in Phase 11; `uv.lock` never regenerated. `githubkit` (used by 11-01/11-02) was already locked and human-approved in Phase 10. | closed (accepted) |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `high` (this project's `workflow.security_block_on`) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Process note (informational, not a security finding):** `T-11-01` through `T-11-06` were allocated independently by plans 11-01 and 11-02 rather than from one phase-wide counter, so the same ID labels two different threats in three places (`T-11-01` reused for a closely-related redaction concern across both plans — benign; `T-11-06` reused for two *unrelated* threats — Tampering/run-id in 11-01 vs. Repudiation/silent-failure in 11-02 — a genuine ID collision). This is exactly the Phase 9 ID-reuse pattern STATE.md already flags as a blocker; 11-06/11-07 correctly avoided repeating it by continuing numbering from `T-11-23`. No open threat results from the collision — both colliding rows were independently verified `mitigate`/`accept` with working controls — but a future phase revisiting 11-01/11-02 should not assume `T-11-06` names one thing.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-11-1 | T-11-06 (11-01), T-11-22 | An `actions: write` holder on a deployer's target repo can dispatch `resume.yml` with an arbitrary `run_id`. | Plan-time (11-01, 11-05) — residual capability is strictly less than what `actions: write` already grants; `dark-factory resume` exits 2 before touching state on an unknown/malformed id. | 2026-09 (plan authoring) |
| AR-11-2 | T-11-17 | `postgres:17-alpine` pulled unpinned by the existing testcontainers rung in CI. | Plan-time (11-04) — Docker Official image, shared probe ladder unmodified per 11-CONTEXT.md D-05 ("reused as-is"); digest-pinning is a cross-cutting change out of this phase's scope. | 2026-09 (plan authoring) |
| AR-11-3 | T-11-19 | Ephemeral testcontainers-provisioned DB URL appears in CI logs. | Plan-time (11-04) — loopback-only, throwaway credential, dies with the job; not an infrastructure secret under `Settings.known_secret_values()`. | 2026-09 (plan authoring) |
| AR-11-4 | T-11-26 | Removing `webhook/app.py`'s pre-built module attribute is a breaking change for any undiscovered out-of-repo ASGI config. | Plan-time (11-06) — not published to a package index; only in-repo references (corrected); wrong target fails loudly at uvicorn startup rather than degrading silently. | 2026-09-30 (plan authoring) |
| AR-11-5 | T-11-27 | `/webhooks/github` signature-verification ordering is unchanged, carried forward from Phase 10 (T-10-18) rather than re-derived. | Plan-time (11-06) — re-asserted via existing test, not re-proved from scratch; no code in the verification path was touched. | 2026-09-30 (plan authoring) |
| AR-11-6 | T-11-SC | No package installs occur anywhere in Phase 11; `githubkit` (the one third-party surface this phase's dispatch code touches) was already locked and human-approved in Phase 10. | Plan-time (all 7 plans) | 2026-09 to 2026-10-01 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-01 | 35 (31 distinct behavioral threats + T-11-SC asserted per-plan across 7 plans, consolidated to 1 row) | 35 | 0 | Orchestrator (grep-depth / ASVS L1 verification against plan-time STRIDE registers — `register_authored_at_plan_time: true` for all 7 plans, so this was a verify-pass, not a from-scratch audit; no `gsd-security-auditor` subagent spawn needed per the ASVS-L1 + threats_open:0 + plan-time-authored short-circuit) |

---

## Manual-Only / Outstanding (non-blocking)

| Item | Threat Ref | Why Not Automatable | Status |
|------|------------|---------------------|--------|
| Measure real CI wall-clock for the `db`-tier step and the whole `quality` job; replace `ci.yml`'s two `[ASSUMED]` timeout comments with measured values | T-11-18 | Numbers don't exist until a real GitHub-hosted-runner run completes; 11-04/11-05/11-06 all defer this explicitly via `<human-check>` rather than inventing values | Outstanding — tracked in 11-06-SUMMARY.md's deferred-to-human/CI section, not a security gap |
| Re-run UAT test 2's live path end-to-end on the real target repository after 11-07's README fix, confirming `dark-factory resume` now advances past BA instead of recording `FAILED` with an errno-2 | T-11-28/29/30/31 (doc-completeness, not a code threat) | Requires a real target repo + real worker binary installed | Outstanding — tracked in 11-07-SUMMARY.md's human-check; this phase's automated guards prove README and the registry agree, not that a real runner executes a role |

Neither item is a blocking security threat — both are measurement/confirmation follow-ups the plans themselves already flagged as deferred-to-human, not gaps this audit introduces.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-01
