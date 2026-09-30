---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
verified: 2026-09-30T15:40:00Z
status: human_needed
score: 27/29 must-haves verified (2 backstop truths abstained — no evidence a real GitHub Actions run or a live GitHub PAT dispatch has yet occurred)
covered_files:
  - ".env.example"
  - ".github/workflows/ci.yml"
  - ".planning/REQUIREMENTS.md"
  - ".planning/ROADMAP.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-01-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-01-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-02-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-02-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-03-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-03-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-04-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-04-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-CONTEXT.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-COVERAGE.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-DISCUSSION-LOG.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-PATTERNS.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-RESEARCH.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-REVIEW.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-VALIDATION.md"
  - "README.md"
  - "src/dark_factory/config/settings.py"
  - "src/dark_factory/github/client.py"
  - "src/dark_factory/webhook/app.py"
  - "tests/db/test_cross_machine_resume.py"
  - "tests/db/test_webhook_dispatches_resume.py"
  - "tests/support/fake_github.py"
  - "tests/unit/test_ci_enforces_worker_name_guard.py"
  - "tests/unit/test_dispatch_token_never_reaches_a_worker.py"
  - "tests/unit/test_qual01_ci_coverage.py"
  - "tests/unit/test_resume_workflow_reference_doc.py"
  - "tests/unit/test_settings.py"
  - "tests/unit/test_trigger_carries_no_lifecycle_logic.py"
  - "tests/unit/test_webhook_signature.py"
covered_digest: "v1:sha256:be5d53668043cc9aab379b728d7bc8b151b4f7618bc66a2599808bf84ab7c15d"
behavior_unverified: 0
overrides_applied: 0
behavior_unverified_items: []
human_verification:
  - test: "Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner."
    expected: "The `Database tier (FakeWorker orchestration suite, QUAL-01)` step reports the `testcontainers` rung in `pytest_report_header` (confirming Docker is genuinely available on `ubuntu-latest`, not just assumed), the ~205-test `db` tier passes, and both the step's and the job's wall-clock durations sit comfortably inside their `[ASSUMED]` `timeout-minutes: 20` / `30` budgets. Replace the `[ASSUMED]` comments in `ci.yml` with measured values per 11-04-PLAN.md's own `<human-check>`."
    why_human: "No CI run exists yet for any Phase 11 commit — the branch is 23 commits ahead of `origin` and has never been pushed (confirmed via `git status` and `gh run list`, whose most recent runs on this branch predate Phase 11 entirely). This is the literal 'complete lifecycle is provable in CI' half of the phase goal and the ROADMAP's SC3, and it can only be closed by an actual GitHub Actions execution, not by anything runnable inside this local sandbox (which itself has no Docker daemon — every db-tier check in this verification ran through the `external`/Neon rung, never the `testcontainers` rung the phase goal specifically claims for CI)."
  - test: "Provision a real fine-grained GitHub PAT (`Actions: Read and write`, scoped to one target repository), add the documented `resume.yml` to that repository, pause a real run on a GitHub issue, answer the clarifying comment, and watch the repository's Actions tab."
    expected: "Exactly one `workflow_dispatch` run of `resume.yml` starts, carrying the run id, and `dark-factory resume <run_id>` inside that job resumes the run to its next state (per must_haves.truths in 11-01-PLAN.md, tier `backstop`, and 11-RESEARCH.md Assumption A2)."
    why_human: "This is a live third-party GitHub API side effect requiring a real repository, a real provisioned credential and a real Actions run. No FakeWorker/DB-fixture proxy exists for it, and 11-05-SUMMARY.md confirms it was never tested against a real provisioned token — the dispatch-outcome table's event names were read from source, not observed live."
---

# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume Verification Report

**Phase Goal:** A run started on a laptop finishes in CI (and the reverse) through Neon alone, and the complete lifecycle is provable in CI without a single AI call.
**Verified:** 2026-09-30T15:40:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All db-tier evidence below is **fresh** — run live by this verification pass against the project's real Neon PostgreSQL test branch (`DARK_FACTORY_TEST_DATABASE_URL`), not taken from SUMMARY.md claims. Structural claims (AST guards, grep-level absence checks) were independently re-derived from the current source tree, not from plan prose.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 (ROADMAP): a run started and paused locally is picked up by a different process with no local state carried over, and completes correctly | ✓ VERIFIED | `uv run pytest -m db tests/db/test_cross_machine_resume.py::test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over` — **1 passed in 63.01s**, run fresh by this verifier against real PostgreSQL with two genuine OS subprocesses and the worktree/artifact tree deleted between them |
| 2 | SC2 (ROADMAP): CLI, webhook and CI entrypoints all funnel into the same `advance(run_id)`; no separate CI orchestrator, no CI-only code path | ✓ VERIFIED | Structural: `grep -n "^def advance\|^def drive"` → only `orchestrator/runner.py`; the only other call site of either name anywhere under `src/dark_factory/` is `cli.py:149`'s `drive(...)` call — independently confirmed by this verifier, not only by the AST guard |
| 3 | SC3 (ROADMAP, mechanical half): the `FakeWorker` suite covers all 8 named scenarios, is selected by CI's `db` marker, with no external AI call and no live worker credential in the workflow | ✓ VERIFIED | `.github/workflows/ci.yml` contains `run: uv run pytest -q -m db`, no `services:`/secrets; `tests/unit/test_qual01_ci_coverage.py` (4 tests) independently re-run and passing, its 8-scenario map's 12 modules independently confirmed on disk and each carrying `pytest.mark.db` |
| 4 | SC3 (ROADMAP, live-CI half): the `db` tier actually runs green on a real GitHub-hosted Actions runner | ⚠️ insufficient_spec | No CI run exists for any Phase 11 commit (branch unpushed — see Human Verification #1). This is a `verification: backstop` truth in 11-04-PLAN.md and its own `<human-check>` is explicitly still open per 11-04-SUMMARY.md |
| 5 | D-01: a resolvable `issue_comment` reply causes exactly one `workflow_dispatch` call after `submit_answer` commits, carrying only the run id | ✓ VERIFIED | `uv run pytest -m db tests/db/test_webhook_dispatches_resume.py` — **8 passed in 215.94s**, run fresh; whole-dict equality assertion on the dispatch call args |
| 6 | D-02: dispatch target comes from the run's persisted `workflow["repository"]` snapshot, never from task metadata or a new config field | ✓ VERIFIED | `src/dark_factory/webhook/app.py:317-320` reads `state.workflow.get("repository")`; same db-tier test suite (#5) asserts the exact owner/repo/branch values match the persisted snapshot |
| 7 | D-03: `dispatch_github_token` is a distinct `SecretStr` field, unwrapped at exactly one frame, covered by the generic redaction walk | ✓ VERIFIED | `src/dark_factory/config/settings.py:118`, `src/dark_factory/github/client.py:171-183` (`for_dispatch`); `tests/unit/test_settings.py -k dispatch` — 3 passed, fresh |
| 8 | D-03: the credential is structurally absent from every worker-facing environment and has an exact, named reader set | ✓ VERIFIED | `tests/unit/test_dispatch_token_never_reaches_a_worker.py` re-run fresh, passing; `grep dispatch_github_token src/dark_factory/tools/env.py` → no match |
| 9 | TRIG-01 module boundary: `webhook/` never references `advance`/`drive`, import allowlist unwidened | ✓ VERIFIED | `grep -rn "advance\|drive" src/dark_factory/webhook/` → only docstring mentions; `tests/unit/test_webhook_process_boundary.py` re-run fresh, passing |
| 10 | HITL-06 fail-soft: a `GitHubError` from the dispatch call is caught, logged already-redacted, delivery still answers 200, answer stays committed | ✓ VERIFIED | `src/dark_factory/webhook/app.py:373-394` (`except GitHubError`); included in the 8-test fresh db-tier run (#5) |
| 11 | HITL-06 degraded config: an unconfigured repository records the answer, answers 200, logs `webhook.dispatch.skipped` (`repository_not_configured`) | ✓ VERIFIED | `app.py:312-334`; included in fresh db-tier run (#5) |
| 12 | HITL-06 degraded credential: an unconfigured `DISPATCH_GITHUB_TOKEN` records the answer, answers 200, logs `webhook.dispatch.skipped` (`dispatch_github_token_not_configured`) | ✓ VERIFIED | `app.py:336-353`; included in fresh db-tier run (#5), exercising the real `GitHubClient.for_dispatch` path (not an injected fake) |
| 13 | D-02 never-over-dispatch: an ignored/unsigned/self-authored delivery makes zero dispatch calls | ✓ VERIFIED | `test_an_ignored_or_unsigned_delivery_never_dispatches[...]` (3 parametrized cases) — included in fresh db-tier run (#5) |
| 14 | SC1/TRIG-04 (D-06): two real OS processes, worktree + artifact tree deleted between them, second process finishes the run to `COMPLETED` | ✓ VERIFIED | Same as #1 — fresh, real subprocesses via `tests.support.subprocess_runner.spawn`, real `git worktree` removal via `remove_worktree(force=True)` |
| 15 | SC1 no-local-state: the resuming process's environment contains neither `DARK_FACTORY_FAKE_SCRIPT` nor `DARK_FACTORY_CRASH_AFTER` | ✓ VERIFIED | Same test as #1 asserts this explicitly before spawning process B; confirmed by reading `tests/db/test_cross_machine_resume.py` lines around the `resume_env` construction |
| 16 | TRIG-04 re-materialization: the worktree exists again at the deterministic path after resume, rebuilt from persisted columns + git | ✓ VERIFIED | Same test as #1, asserted mid-flight via `popen`+`wait_for` before the `COMPLETED` cleanup removes it again |
| 17 | HITL-06 cross-process: same run, same `role_executions` row and `attempt`, no second `runs` row | ✓ VERIFIED | Same test as #1 |
| 18 | SC2/TRIG-01 behavioural: a two-process run and a single-process control run reach identical terminal status and identical ordered `run_events` sequence | ✓ VERIFIED | `uv run pytest -m db tests/db/test_cross_machine_resume.py::test_the_two_process_run_and_a_single_process_run_are_indistinguishable` — **1 passed in 81.19s**, run fresh |
| 19 | TRIG-01 structural: `advance`/`drive` defined in exactly one module, called only from a verified allowlist, guard cannot pass vacuously | ✓ VERIFIED | `tests/unit/test_trigger_carries_no_lifecycle_logic.py` re-run fresh (3 tests, passing); independently cross-checked against source (#2) |
| 20 | D-05: `ci.yml` selects `db`, declares no `services:` block, no new secret | ✓ VERIFIED | `.github/workflows/ci.yml` read directly; matches claims exactly |
| 21 | QUAL-01 scenario coverage: all 8 scenario nouns map to existing, `db`-marked modules | ✓ VERIFIED | `tests/unit/test_qual01_ci_coverage.py` re-run fresh (4 tests); all 12 mapped modules independently confirmed to exist and carry `pytest.mark.db` |
| 22 | D-05: `integration` stays excluded for a credential reason, stated in the workflow comment, not a database-availability reason | ✓ VERIFIED | `ci.yml` comment reviewed verbatim, matches the required framing |
| 23 | HITL-06/D-04: README gives a deployer everything to add `resume.yml`, provision `DISPATCH_GITHUB_TOKEN`, and set Actions secrets | ✓ VERIFIED | README.md "Finish a run in CI" section (lines 276–420) reviewed in full; sentinel-bracketed block matches `tests/unit/test_resume_workflow_reference_doc.py`'s extraction contract |
| 24 | D-04: deployment model documented — pip-installable package, deployer never clones Dark Factory's own repo, `dark-factory init` gap named as a deferral | ✓ VERIFIED | README.md lines 288–302 |
| 25 | TRIG-01 documented: reference workflow does exactly 3 steps and carries no run-state branch | ✓ VERIFIED | README.md reference workflow block (lines 331–365); `test_the_reference_workflow_resumes_exactly_once` / `test_the_reference_workflow_carries_no_run_state_branch` re-run fresh, passing |
| 26 | D-03 least privilege documented: fine-grained PAT named before the classic-token fallback | ✓ VERIFIED | README.md lines 392–400 |
| 27 | Operability: all 4 dispatch outcomes and their exact log event/reason strings are documented | ✓ VERIFIED | README.md table (lines 409–416) cross-checked verbatim against the constants and `_log.*` call sites in `src/dark_factory/webhook/app.py` |
| 28 | QUAL-01/SC3 documented: README's test-tier statement matches `ci.yml` | ✓ VERIFIED | README.md lines 449–454 match `ci.yml`'s comment and step selectors exactly |
| 29 | Backstop (11-01, D-05): a real `workflow_dispatch` against a live GitHub repository with a real fine-grained PAT starts a real Actions run of `resume.yml` and resumes the run | ⚠️ insufficient_spec | 11-05-SUMMARY.md itself records this was never tested against a real provisioned token; no FakeWorker/DB proxy can stand in for a live third-party API side effect |

**Score:** 27/29 truths verified (2 abstained as `insufficient_spec` — both are `verification: backstop` items the plans themselves flagged as requiring live infrastructure no local sandbox run can produce)

### Doc-drift and structural guards re-run fresh by this verifier

| Command | Result |
|---|---|
| `pytest -m unit -q tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_resume_workflow_reference_doc.py tests/unit/test_dispatch_token_never_reaches_a_worker.py tests/unit/test_webhook_process_boundary.py tests/unit/test_ci_enforces_worker_name_guard.py` | **37 passed** |
| `pytest -m unit -q tests/unit/test_settings.py tests/unit/test_webhook_signature.py -k "dispatch or Dispatch"` | **4 passed** |
| `pytest -m db -q tests/db/test_cross_machine_resume.py::test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over` | **1 passed, 63.01s** |
| `pytest -m db -q tests/db/test_cross_machine_resume.py::test_the_two_process_run_and_a_single_process_run_are_indistinguishable` | **1 passed, 81.19s** |
| `pytest -m db -q tests/db/test_webhook_dispatches_resume.py` | **8 passed, 215.94s** |
| `gsd_run query check.decision-coverage-verify` | 7/7 CONTEXT.md decisions (D-01–D-07) honored |
| `gsd_run query verify.artifacts` (all 5 plans) | 14/14 artifacts pass all three levels |
| `gsd_run query verify.key-links` (all 5 plans) | 12/12 key links verified |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/github/client.py` | `dispatch_workflow` / `for_dispatch` | ✓ VERIFIED | Present, wired, matches acceptance criteria |
| `src/dark_factory/config/settings.py` | `dispatch_github_token` field | ✓ VERIFIED | Present, redaction-covered |
| `src/dark_factory/webhook/app.py` | Dispatch block, `dispatch_client_factory` seam | ✓ VERIFIED | Present, wired, all 4 outcomes implemented |
| `tests/support/fake_github.py` | `FakeGitHubClient.dispatch_workflow` | ✓ VERIFIED | Present |
| `tests/db/test_webhook_dispatches_resume.py` | 8 db-tier tests | ✓ VERIFIED | All 8 re-run fresh, passing |
| `tests/unit/test_dispatch_token_never_reaches_a_worker.py` | Structural guard | ✓ VERIFIED | Re-run fresh, passing |
| `tests/db/test_cross_machine_resume.py` | SC1/SC2 proof | ✓ VERIFIED | Both tests re-run fresh, passing |
| `tests/unit/test_trigger_carries_no_lifecycle_logic.py` | TRIG-01 structural guard | ✓ VERIFIED | Re-run fresh, passing |
| `.github/workflows/ci.yml` | `db`-tier CI step | ✓ VERIFIED | Present, correct selectors |
| `tests/unit/test_qual01_ci_coverage.py` | QUAL-01 coverage guard | ✓ VERIFIED | Re-run fresh, passing |
| `README.md` | Local→CI handoff section | ✓ VERIFIED | Present, matches all acceptance criteria |
| `tests/unit/test_resume_workflow_reference_doc.py` | Doc-drift guard | ✓ VERIFIED | Referenced by fresh unit-tier sweep (37 passed) |

### Key Link Verification

All 12 key links declared across the 5 plans (`gsd_run query verify.key-links`) verified programmatically — `dispatch_workflow(` pattern found at each claimed call site, `load_run_state(` read confirmed, `except GitHubError` confirmed, `yaml.safe_load` confirmed in both CI-tier and doc-drift guards, `worktree_path(`/AST `runner.py` guard confirmed. 0 NOT_WIRED, 0 PARTIAL.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| HITL-06 | 11-01, 11-02, 11-03, 11-05 | Run resumable on a different machine/process (local→CI, webhook, delayed human answer) | ✓ SATISFIED | Truths #1, #5, #10-18, #23-27 |
| TRIG-01 | 11-01, 11-03 | One orchestration implementation; triggers carry zero lifecycle logic | ✓ SATISFIED | Truths #2, #9, #19, #25 |
| TRIG-04 | 11-03 | Local→CI boundary crossed through Neon alone, no separate CI code path | ✓ SATISFIED | Truths #1, #14, #16 |
| QUAL-01 | 11-04, 11-05 | `FakeWorker` orchestration suite tested end-to-end, in CI, no AI calls | ⚠️ SATISFIED (mechanical) / live-CI unconfirmed | Truths #3, #20-22, #28; #4 open |

No orphaned requirements — REQUIREMENTS.md maps exactly these four IDs to Phase 11, and all four are claimed in at least one plan's frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/dark_factory/webhook/app.py` | 293-394 (dispatch block) | No catch-all `except Exception` around the dispatch block, unlike the `submit_answer` block immediately above it (lines 265-285) and unlike this module's own docstring promise ("any unexpected exception is logged... and returns a fixed 500, never echoed") | ⚠️ Warning | A DB error from `load_run_state` (line 295), a non-`MissingGitHubCredentialError` exception constructing the dispatch client (line 346), or a non-`GitHubError` exception from `dispatch_workflow` (line 374) would propagate unhandled through `run_in_threadpool` instead of degrading fail-soft to 200 as every *tested* dispatch-failure path does. Independently confirmed by this verifier reading the current source (matches `11-REVIEW.md`'s WR-01 finding, still open — no `11-REVIEW-FIX.md` exists). Does not block the phase goal: `submit_answer` has already committed by this point in every case, and the documented manual fallback (`dark-factory resume <run_id>`) is unaffected. None of Phase 11's own `must_haves.truths` require blanket exception handling — only `GitHubError` specifically — so this is not a must-have failure, but it is a real gap against the module's own stated contract and untested by any of the 8 db-tier dispatch tests. |
| `src/dark_factory/config/settings.py` | 141-163 | `LEASE_HEARTBEAT_SECONDS` accepts non-positive values (`_lease_intervals_are_coherent` never checks `> 0`) | ℹ️ Info | Pre-existing since Phase 2, unmodified by any Phase 11 diff. `11-REVIEW.md`'s WR-02. Reachable from Phase 11's own new `tests/db/test_cross_machine_resume.py` fixtures (which pass `lease_heartbeat_seconds` through), but the defect itself is not Phase 11 scope. Noted for completeness, not counted against this phase. |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any of the 16 files this phase created or modified. No `TODO`/`HACK`/`PLACEHOLDER` patterns found in the three core production files (`settings.py`, `client.py`, `app.py`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| SC1: cross-machine resume completes | `pytest -m db tests/db/test_cross_machine_resume.py::test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over` | 1 passed, 63.01s | ✓ PASS |
| SC2: two-process/single-process indistinguishability | `pytest -m db tests/db/test_cross_machine_resume.py::test_the_two_process_run_and_a_single_process_run_are_indistinguishable` | 1 passed, 81.19s | ✓ PASS |
| HITL-06 dispatch (all 8 outcomes/degraded paths) | `pytest -m db tests/db/test_webhook_dispatches_resume.py` | 8 passed, 215.94s | ✓ PASS |
| TRIG-01/QUAL-01/doc-drift structural guards | `pytest -m unit -q <6 modules>` | 37 passed | ✓ PASS |
| `advance`/`drive` single-definition, single-call-site | `grep -rn "^def advance\|^def drive"` / `grep -rn "advance(\|drive("` over `src/dark_factory/` | Matches guard's claimed sets exactly | ✓ PASS |

### Decision Coverage

`gsd_run query check.decision-coverage-verify` — **7/7** CONTEXT.md decisions (D-01 through D-07) honored by shipped artifacts. No unhonored decisions.

### Human Verification Required

#### 1. A real GitHub Actions run of `ci.yml`'s expanded `quality` job

**Test:** Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner.
**Expected:** The `Database tier (FakeWorker orchestration suite, QUAL-01)` step's `pytest_report_header` reports the `testcontainers` rung (confirming Docker is genuinely available on `ubuntu-latest`), the ~205-test `db` tier passes, and both the step's and the job's durations sit comfortably inside the `[ASSUMED]` `timeout-minutes: 20` / `30` budgets. Replace the `[ASSUMED]` comments with measured values.
**Why human:** No CI run exists yet for any Phase 11 commit — this branch is 23 commits ahead of `origin` and has never been pushed (`git status`, `gh run list` both confirm the most recent CI runs on this branch predate Phase 11). Every db-tier check this verifier ran used the `external`/Neon rung (`DARK_FACTORY_TEST_DATABASE_URL`), never the `testcontainers` rung the phase's own D-05 premise and ROADMAP SC3 specifically claim for CI. This is the literal "provable in CI" half of the phase goal.

#### 2. A live `workflow_dispatch` against a real GitHub repository

**Test:** Provision a real fine-grained PAT (`Actions: Read and write`, scoped to one repository), add the documented `resume.yml`, pause a real run on a GitHub issue, answer the clarifying comment, and watch the repository's Actions tab.
**Expected:** Exactly one `workflow_dispatch` run of `resume.yml` starts, carrying the run id, and resumes the run.
**Why human:** A live third-party GitHub API side effect. 11-05-SUMMARY.md itself records this was never tested against a real provisioned token.

### Gaps Summary

No must-have truth FAILED, no artifact is MISSING/STUB, no key link is NOT_WIRED, and no BLOCKER-severity anti-pattern was found — the phase's implementation, wiring, and documentation are all genuinely present and independently re-verified fresh against real infrastructure wherever a local proxy exists (real PostgreSQL, real OS subprocesses, real git worktrees). The two open items are both `verification: backstop` truths the plans' own authors flagged as requiring live infrastructure (a real GitHub Actions run, a real provisioned PAT) that this local sandbox cannot produce — they are not code defects, they are un-collected evidence. One code-review Warning (WR-01, no catch-all exception handler around the dispatch block) remains open with no `11-REVIEW-FIX.md`; it does not block any must-have truth but is a real gap against the module's own documented fail-soft contract and is recommended for a follow-up fix or an explicit override decision before the next phase builds on this dispatch path.

---

_Verified: 2026-09-30T15:40:00Z_
_Verifier: Claude (gsd-verifier)_
