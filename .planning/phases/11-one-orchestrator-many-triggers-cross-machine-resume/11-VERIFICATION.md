---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
verified: 2026-10-01T11:30:00Z
status: human_needed
score: 31/33 must-haves verified (2 live-infrastructure truths abstained — the exact two UAT found broken, now code-fixed and locally re-proven, but not yet re-exercised against a real GitHub Actions runner / a real target repository)
covered_files:
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
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-06-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-06-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-07-PLAN.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-07-SUMMARY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-REVIEW.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-SECURITY.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-UAT.md"
  - ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-VALIDATION.md"
  - "README.md"
  - "src/dark_factory/webhook/__init__.py"
  - "src/dark_factory/webhook/app.py"
  - "tests/unit/test_resume_workflow_reference_doc.py"
  - "tests/unit/test_webhook_import_needs_no_database.py"
covered_digest: "v1:sha256:840a77b8e9398b9df8bce7787e165caa80edb9946989c4ca94331ebf0bfc9ea2"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: "27/29 (2026-09-30 initial verification, pre-UAT)"
  gaps_closed:
    - "G-11-1 (blocker): webhook/app.py no longer builds the ASGI app at module import time — importing the module, and every dark_factory module, now succeeds with no DATABASE_URL/DATABASE_URL_DIRECT and no readable .env. Independently re-confirmed by this verifier with a literal `env -i PATH HOME python -c \"import dark_factory.webhook.app\"` from outside the repo tree."
    - "G-11-2 (major): README's 'Finish a run in CI' section now names, for every registered worker runtime (claude-code, copilot, hermes), the PATH binary and credential variable it needs, with a commented install step at the copy-paste site. Independently re-confirmed by reading README.md lines 331-434."
  gaps_remaining:
    - "The literal UAT-1 symptom (a real GitHub Actions run of ci.yml's quality job reaching and passing the db-tier step) has not been re-observed on a real runner since the fix — the branch carrying the 11-06/11-07 commits has never been pushed. The one CI run that exists for this branch (run 36739796095) predates the fix and failed with the exact pre-fix G-11-1 traceback, now independently confirmed in its logs by this verifier."
    - "The literal UAT-2 symptom (a live `dark-factory resume` inside a dispatched resume.yml job advancing a real run past BA) has not been re-attempted against a real target repository since the README fix landed."
  regressions: []
---

# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume Verification Report

**Phase Goal:** A run started on a laptop finishes in CI (and the reverse) through Neon alone, and the complete lifecycle is provable in CI without a single AI call.
**Verified:** 2026-10-01T11:30:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (plans 11-06, 11-07, closing 11-UAT.md's G-11-1 and G-11-2)

## Goal Achievement

All evidence below marked "fresh" was run live by this verification pass, in this sandbox,
against this repository's current working tree — not taken from SUMMARY.md claims. Where a
claim could only be confirmed by reading source (e.g., README prose, STRIDE tables), that is
stated explicitly rather than implied to be a test run.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | G-11-1 fix: `dark_factory.webhook.app` (and every `dark_factory` module) imports successfully with no `DATABASE_URL`/`DATABASE_URL_DIRECT` and no readable `.env` | ✓ VERIFIED | Independently reproduced fresh: `cd /tmp && env -i PATH="$PATH" HOME="$HOME" python -c "import dark_factory.webhook.app as m; print(m.__all__)"` → `['build_app']`, no exception. Matches the exact failure mode G-11-1 diagnosed (previously a `pydantic_core.ValidationError`) |
| 2 | G-11-1 fix: no module-level `app = build_app()` remains; module exposes only a callable factory | ✓ VERIFIED | Read `src/dark_factory/webhook/app.py` end-to-end — file ends with `build_app`'s own `return Starlette(...)`, no trailing module-level assignment; `__all__` confirmed `['build_app']` by the import above |
| 3 | G-11-1 guard: `tests/unit/test_webhook_import_needs_no_database.py` is non-vacuous (sweep + positive control) and green | ✓ VERIFIED | `uv run pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py` — **4 passed**, run fresh |
| 4 | G-11-1: the three originally-failing modules collect cleanly with no database configured | ✓ VERIFIED | Covered by Test 2 inside the same 4-test module above (child-process `--collect-only` over the three named modules); re-run fresh, passing |
| 5 | G-11-1: WR-02 startup credential diagnostics still fire once per receiver process after the deferral | ✓ VERIFIED | `uv run pytest -m unit -q tests/unit/test_webhook_signature.py tests/unit/test_dispatch_token_never_reaches_a_worker.py` — included in the 37-passed structural sweep below; `build_app`'s body confirmed byte-identical to before (SUMMARY claim), diagnostics block untouched by this verifier's own read of the file |
| 6 | G-11-2 fix: README's "Finish a run in CI" section names, for every registered worker (`claude-code`, `copilot`, `hermes`), the required `PATH` binary and credential variable | ✓ VERIFIED | Read README.md lines 288-434 directly: deployment-model item 5, the "### The worker runtime" subsection, and its 3-row table (`claude`/`ANTHROPIC_API_KEY`, `copilot`/`COPILOT_GITHUB_TOKEN`, `hermes`/`ANTHROPIC_API_KEY` shared) all present |
| 7 | G-11-2 fix: the reference block carries commented (inert) install guidance positioned between "Install dark-factory" and "Resume the run", naming no third-party install command | ✓ VERIFIED | Read README.md lines 354-363 directly: a `# - name: Install the worker runtime` / `# run: ...` pair, fully commented, no install command named, positioned exactly as claimed |
| 8 | G-11-2 fix: the reference block still parses as YAML, still declares `run_id`, still invokes `dark-factory resume` exactly once, no `if:` key | ✓ VERIFIED | `uv run pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` — **13 passed**, run fresh (5 pre-existing assertions + 8 new drift-guard assertions) |
| 9 | G-11-2 guard: a fourth worker adapter would fail the doc guard until documented (drift guard derives expectations from `LIVE_RUNTIMES`, not hand-restated) | ✓ VERIFIED | Same 13-passed run above; tests parametrized over `LIVE_RUNTIMES.values()`, confirmed by reading the test file |
| 10 | SC1/HITL-06: a run paused by one OS process is finished by another, nothing carried over, after the gap-closure refactor | ✓ VERIFIED | `uv run pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py` — **10 passed in 356.42s**, run fresh against real Neon PostgreSQL — confirms the `webhook/app.py` factory refactor introduced no regression in the dispatch or cross-machine-resume behavior this phase's core claim rests on |
| 11 | SC2/TRIG-01: `advance`/`drive` remain single-sourced; webhook module still references neither | ✓ VERIFIED | `uv run pytest -m unit -q tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_webhook_process_boundary.py` — re-run fresh, passing, part of the 37-passed sweep below |
| 12 | SC3 (mechanical half): `FakeWorker` suite's 8 scenarios map to existing `db`-marked modules; `ci.yml` selects the `db` marker, no `services:`/secrets | ✓ VERIFIED | `uv run pytest -m unit -q tests/unit/test_qual01_ci_coverage.py` — re-run fresh, passing; `.github/workflows/ci.yml` read directly, unchanged by 11-06/11-07 per their own scope statements |
| 13 | SC3 (live-CI half): `ci.yml`'s `quality` job — including the now-fixed `Unit and contract tiers` step — actually runs green end-to-end on a real GitHub-hosted Actions runner | ⚠️ insufficient_spec | **Not re-observed.** The branch carrying commits `1f431d7`..`9706d0b` (11-06, 11-07, review/validation/security docs) is 14 commits ahead of `origin/gsd/phase-01-walking-skeleton-one-durable-run` and has never been pushed (`git status`, confirmed fresh). The only CI run that exists for this branch (`gh run view 36739796095`, 2026-09-30T15:50) is for pre-fix commit `50ddc74` and failed during checkout/collection — exactly the G-11-1 symptom UAT reported. No CI run has exercised the fix. |
| 14 | Backstop (11-01, D-05): a real `workflow_dispatch` against a live repository with a real PAT starts a real `resume.yml` run that advances a real run past BA | ⚠️ insufficient_spec | **Not re-attempted.** UAT test 2 ran this live once and it failed with the G-11-2 errno-2 symptom. 11-07-SUMMARY.md explicitly defers the re-run to "the phase's own verification/UAT step" (this pass); no evidence of a second live attempt exists in any phase artifact dated after the README fix (commit `8a92a8e`, 2026-10-01). |
| 15 | Full project regression (unit+contract tier) shows exactly the one documented pre-existing sandbox artifact and no new failures introduced by the gap closure | ✓ VERIFIED | `uv run pytest -q -m "unit or contract"` run fresh in this verification — **1 failed, 829 passed, 1 skipped, 374 deselected in 265.79s** — the single failure is `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, independently confirmed to fail only because this sandbox has a real `ANTHROPIC_API_KEY`/`claude` CLI configured (the test expects `FAILED` with no credentials and gets a real `COMPLETED` response) — matches 11-06-SUMMARY.md, 11-07-SUMMARY.md, and 11-REVIEW.md's identical, independently-dated account exactly |
| 16 | No regression in requirement-mapped behavior from the gap-closure diff | ✓ VERIFIED | Truths #10, #11, #12 above re-confirm the SC1/SC2/SC3-mechanical behaviors this phase's requirements depend on, post-refactor |

**Score:** 14/16 directly-assessed truths VERIFIED in this re-verification pass (2 insufficient_spec, both carried forward from the original UAT and both requiring live infrastructure this sandbox cannot produce); combined with the 17 structural/doc truths from the original 2026-09-30 initial verification that remain unaffected by this diff (truths #2-3, #5-9, #19-28 in that report, all re-spot-checked here via the 37-passed structural sweep and the direct README read), overall **31/33 must-haves verified**.

### Doc-drift and structural guards re-run fresh by this verifier

| Command | Result |
|---|---|
| `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_resume_workflow_reference_doc.py` | **17 passed** |
| `pytest -m unit -q tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_dispatch_token_never_reaches_a_worker.py tests/unit/test_webhook_process_boundary.py tests/unit/test_no_worker_name_leak.py tests/unit/test_worker_registry_names.py` | **37 passed, 1 failed** (the one documented, pre-existing, sandbox-credential-dependent failure) |
| `pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py` | **10 passed, 356.42s**, against real Neon PostgreSQL |
| `pytest -q -m "unit or contract"` (full tier) | **829 passed, 1 skipped, 1 failed, 374 deselected, 265.79s** — matches the claimed full-regression numbers exactly |
| `env -i PATH HOME python -c "import dark_factory.webhook.app"` from `/tmp` | succeeds, `__all__ == ['build_app']` |
| `gh run view 36739796095` (the one real CI run on this branch) | confirms it predates the fix and fails with the exact G-11-1 collection error |
| `git status` / `git log` | branch 14 commits ahead of origin, unpushed; no CI run exists for any gap-closure commit |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/webhook/app.py` | No module-level `build_app()` call; `__all__ = ['build_app']` | ✓ VERIFIED | Confirmed by direct read and fresh import test |
| `src/dark_factory/webhook/__init__.py` | Docstring documents the uvicorn `--factory` invocation | ✓ VERIFIED | Confirmed by direct read |
| `tests/unit/test_webhook_import_needs_no_database.py` | 4-test non-vacuous import guard | ✓ VERIFIED | Present, 4/4 passing fresh |
| `README.md` | Worker-runtime table + commented install step | ✓ VERIFIED | Present, matches all claimed content |
| `tests/unit/test_resume_workflow_reference_doc.py` | 13 assertions (5 original + 8 new) | ✓ VERIFIED | Present, 13/13 passing fresh |

Note: `gsd_run query verify.artifacts`/`verify.key-links` returned 0 total for plans 11-06 and
11-07 because those two plans' `must_haves.artifacts`/`key_links` frontmatter use bare path
strings rather than the `{path, provides, contains}` / `{from, to, via}` object shape the tool
parses (a plan-authoring format inconsistency, not a code defect). All five artifacts and both
plans' key properties were therefore verified manually by direct file reads and fresh test runs,
documented above — not left unverified.

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| uvicorn `--factory` | `build_app()` | receiver startup path | ✓ WIRED | Confirmed: `build_app` is a valid zero-argument callable; docstring in both `app.py` and `__init__.py` document the identical uvicorn command |
| `tests/unit/test_webhook_import_needs_no_database.py` | every `dark_factory.*` module | `pkgutil.walk_packages` sweep | ✓ WIRED | Re-run fresh, 0 offenders, 1 tolerated (`mcp_transport`, uninstalled optional extra) |
| `tests/support/live_runtime.py`'s `LIVE_RUNTIMES` | README's worker-runtime table | parametrized assertion | ✓ WIRED | 13-test suite re-run fresh, passing; table values cross-checked against `tests/support/live_runtime.py` and `src/dark_factory/workers/registry.py` |
| All 12 pre-existing key links from plans 11-01 through 11-05 | (unchanged by this diff) | — | ✓ WIRED | Re-confirmed via `gsd_run query verify.key-links` for all 5 plans — 12/12 verified, 0 NOT_WIRED |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| HITL-06 | 11-01, 11-02, 11-03, 11-05, 11-07 | Run resumable on a different machine/process | ✓ SATISFIED (mechanically) | Truths #10, #6-7; live re-proof (truth #14) still outstanding |
| TRIG-01 | 11-01, 11-03 | One orchestration implementation; zero lifecycle logic in triggers | ✓ SATISFIED | Truth #11 |
| TRIG-04 | 11-03, 11-07 | Local→CI boundary crossed through Neon alone | ✓ SATISFIED (mechanically) | Truths #10, #6-9; live re-proof (truth #14) still outstanding |
| QUAL-01 | 11-04, 11-05, 11-06 | `FakeWorker` suite tested end-to-end, runs green in CI, no AI calls | ✓ SATISFIED (mechanically) / live-CI unconfirmed | Truths #1-5, #12, #15; live re-proof (truth #13) still outstanding |

No orphaned requirements — REQUIREMENTS.md maps exactly TRIG-01, TRIG-04, HITL-06, QUAL-01 to Phase 11, all four marked `[x]` Complete, all four claimed across the phase's 7 plans' frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/dark_factory/webhook/app.py` | dispatch block (~293-394) | No catch-all `except Exception` around the dispatch block (unlike `submit_answer`'s block and unlike the module's own docstring promise) | ⚠️ Warning | Carried forward unchanged from the original 2026-09-30 review (WR-01); independently re-confirmed present in this verifier's own read of the current file (`except Exception` appears only around `resolve_issue_comment`/`submit_answer` at lines 247/284, and `except GitHubError` at line 384 — no outer catch-all around the dispatch block). Does not block any of this phase's must-have truths; a DB error from `load_run_state` or an unexpected exception type from client construction would still propagate unhandled rather than degrading fail-soft. Recommended follow-up, not a phase blocker. |
| `src/dark_factory/config/settings.py` | 141-163 | `LEASE_HEARTBEAT_SECONDS` accepts non-positive values | ℹ️ Info | Pre-existing since Phase 2, unmodified by this phase; carried forward (WR-02), not phase-11 scope |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any of the 5 files this gap-closure round created or modified (`src/dark_factory/webhook/app.py`, `src/dark_factory/webhook/__init__.py`, `tests/unit/test_webhook_import_needs_no_database.py`, `README.md`, `tests/unit/test_resume_workflow_reference_doc.py`). No `TODO`/`HACK`/`PLACEHOLDER` patterns found in those files either.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| G-11-1: module-free-of-database-requirement import | `env -i PATH HOME python -c "import dark_factory.webhook.app"` from `/tmp` | succeeds, `__all__ == ['build_app']` | ✓ PASS |
| G-11-1 guard suite | `pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py` | 4 passed | ✓ PASS |
| G-11-2 doc-drift guard suite | `pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` | 13 passed | ✓ PASS |
| SC1/HITL-06 cross-machine resume + dispatch (post-refactor regression) | `pytest -m db -q tests/db/test_cross_machine_resume.py tests/db/test_webhook_dispatches_resume.py` | 10 passed, 356.42s, real Neon | ✓ PASS |
| Full unit+contract regression | `pytest -q -m "unit or contract"` | 829 passed, 1 skipped, 1 failed (documented pre-existing), 265.79s | ✓ PASS (matches documented baseline exactly) |
| Structural guards (TRIG-01, QUAL-01 coverage, dispatch-token boundary, webhook boundary, worker-name leak) | `pytest -m unit -q <6 modules>` | 37 passed, 1 failed (same documented pre-existing failure) | ✓ PASS |
| Live GitHub Actions run of the fixed `ci.yml` | n/a — requires pushing the branch | not run | ? SKIP — routed to Human Verification #1 |
| Live `workflow_dispatch` + `dark-factory resume` against a real repository | n/a — requires a provisioned live repository | not run | ? SKIP — routed to Human Verification #2 |

### Human Verification Required

#### 1. A real GitHub Actions run of the fixed `ci.yml`'s `quality` job

**Test:** Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner.
**Expected:** The `Unit and contract tiers` step passes (no longer exits 2 at collection — the G-11-1 failure UAT reported), the `Database tier (FakeWorker orchestration suite, QUAL-01)` step is actually reached, its `pytest_report_header` reports the `testcontainers` rung, the ~205-test `db` tier passes, and both step/job durations sit inside their `[ASSUMED]` `timeout-minutes` budgets (20/30). Replace the `[ASSUMED]` comments with the measured values once observed.
**Why human:** This is the literal "provable in CI" half of the phase goal and ROADMAP SC3, and it is the exact scenario UAT test 1 ran and found broken. The code fix (G-11-1) is verified locally in this sandbox with every proxy available (direct database-free import, the new guard suite, the full unit+contract regression), but the branch carrying the fix has never been pushed — the one real CI run that exists for this branch predates the fix and fails exactly as UAT described. No local sandbox run can substitute for a real GitHub-hosted Actions execution.

#### 2. A live `workflow_dispatch` + `dark-factory resume` against a real repository, with the worker runtime installed

**Test:** Copy the corrected reference `resume.yml` block from README into a real target repository, follow the new "### The worker runtime" subsection to install the binary the repository's configured roles need, pause a real run on a GitHub issue, answer the clarifying comment, and watch the Actions tab. Confirm `dark-factory resume <run_id>` inside that job now advances the run past BA instead of recording a `FAILED` role execution with an errno-2 error, and confirm via `dark-factory status <run_id>` that the run reached its next state.
**Why human:** This is the exact live path UAT test 2 ran and found broken (dispatch worked, `dark-factory resume` failed with "no such file or directory: 'claude'"). The documentation fix (G-11-2) is verified locally — the table names the correct binaries and credentials, the install guidance is positioned and inert, and the doc-drift guard derives its expectations from the same registry the live adapters use — but no second live attempt against a real repository has been recorded anywhere in this phase's artifacts since the README fix landed. Only a live re-run proves the documentation is *sufficient* for a deployer to succeed, not merely internally consistent with the registry.

### Gaps Summary

Both gaps UAT found (G-11-1 blocker, G-11-2 major) have real, substantive, well-tested code/doc
fixes that this verifier independently reproduced and confirmed fresh — not taken on the
SUMMARY.md's word. The webhook module genuinely no longer requires a database to import
(reproduced with a literal sanitized-environment import from outside the repo tree), and README
genuinely now names every registered worker's binary and credential at the copy-paste site
(confirmed by direct read). The post-fix cross-machine-resume and dispatch db-tier tests pass
fresh against real Neon PostgreSQL (10/10, no regression from the `webhook/app.py` refactor),
and the full unit+contract regression reproduces exactly the documented baseline (829
passed/1 skipped/1 failed, the one failure being a known, independently-confirmed
sandbox-credential artifact unrelated to this phase's files).

What remains open is not a code defect but un-collected live evidence: both UAT failures were
discovered by actually exercising the system end-to-end against real infrastructure (a real
GitHub Actions runner, a real target repository with a real PAT and a real worker binary), and
neither of those two specific live exercises has been repeated since the fixes landed. The
branch carrying the fix commits has never been pushed, so no CI run has ever seen the corrected
`webhook/app.py`; and no second live `workflow_dispatch`-to-resume attempt against a real
repository is recorded in any phase artifact dated after the README fix. Given that this exact
category of gap (code looks right locally, fails live) is precisely what UAT caught the first
time, closing the phase without re-collecting that live evidence would repeat the same mistake.
Routed to Human Verification rather than FAILED, because the root-cause fixes themselves are
independently verified correct and regression-free by every check this sandbox can run.

---

_Verified: 2026-10-01T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
