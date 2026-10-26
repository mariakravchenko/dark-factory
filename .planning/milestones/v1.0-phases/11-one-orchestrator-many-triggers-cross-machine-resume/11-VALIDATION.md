---
phase: "11"
slug: "one-orchestrator-many-triggers-cross-machine-resume"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-29"
validated: "2026-10-01"
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (confirmed installed, matches `pyproject.toml` pin) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (markers: `unit`, `db`, `integration`, `contract`) |
| **Quick run command** | `uv run pytest -q -m "unit or contract"` |
| **Full suite command** | `uv run pytest -q` (all tiers; needs a reachable PostgreSQL 17) |
| **Estimated runtime** | ~15s (unit+contract), ~5min (full with db, testcontainers cold start ~3s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "unit or contract"` (falls back from `db` tier only in a dev sandbox with no Postgres rung available, per the existing probe ladder's hard-fail design)
- **After every plan wave:** Run `uv run pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green, plus `.github/workflows/ci.yml`'s `db`-tier selection green
- **Max feedback latency:** ~15s (unit+contract tier)

---

## Per-Task Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|--------------------|-------------|--------|
| TRIG-01 | CLI/webhook/CI all funnel into `advance(run_id)`, no CI-only path | unit + db | `uv run pytest -q -m "unit or db" tests/unit/test_trigger_carries_no_lifecycle_logic.py tests/db/test_cross_machine_resume.py` | ✅ | ✅ green |
| TRIG-04 | Run continues across local→CI boundary via Neon alone | db + unit (doc guard) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py`; `uv run pytest -q -m unit tests/unit/test_resume_workflow_reference_doc.py` | ✅ | ✅ green |
| HITL-06 | Resume on a different machine/process than the one that started it | db (extends existing SC2 idiom) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py` | ✅ | ✅ green |
| HITL-06 (dispatch half) | Webhook receiver dispatches a real `workflow_dispatch` after `submit_answer` | db | `uv run pytest -q -m db tests/db/test_webhook_dispatches_resume.py` | ✅ (6 tests, all 4 dispatch outcomes) | ✅ green |
| HITL-06 (doc guard, G-11-2) | Reference `resume.yml` documents every registered worker's binary + credential before `dark-factory resume` runs | unit | `uv run pytest -q -m unit tests/unit/test_resume_workflow_reference_doc.py` | ✅ (9 tests, parametrized over `LIVE_RUNTIMES`) | ✅ green |
| QUAL-01 | Role transitions | db (existing) | `uv run pytest -q -m db tests/db/test_four_role_pipeline.py tests/db/test_transition_atomic.py` | ✅ | ✅ green |
| QUAL-01 | Artifact handoffs | db (existing) | `uv run pytest -q -m db tests/db/test_artifact_handoff.py` | ✅ | ✅ green |
| QUAL-01 | Pause/resume | db (existing) | `uv run pytest -q -m db tests/db/test_pause_mechanism_generic.py tests/db/test_resume_first_advance.py` | ✅ | ✅ green |
| QUAL-01 | QA rejection | db (existing) | `uv run pytest -q -m db tests/db/test_qa_bounce.py` | ✅ | ✅ green |
| QUAL-01 | Developer retries | db (existing) | `uv run pytest -q -m db tests/db/test_feedback_reaches_developer.py` | ✅ | ✅ green |
| QUAL-01 | Quality-gate retries | db (existing) | `uv run pytest -q -m db tests/db/test_quality_gate_gates_the_run.py` | ✅ | ✅ green |
| QUAL-01 | Retry exhaustion | db (existing) | `uv run pytest -q -m db tests/db/test_iteration_cap_exhaustion.py tests/db/test_loop04_adjacency.py` | ✅ | ✅ green |
| QUAL-01 | Publishing | db (existing) | `uv run pytest -q -m db tests/db/test_publish_step.py tests/db/test_publish_idempotency.py` | ✅ | ✅ green |
| QUAL-01 | "runs green in CI, no external AI calls, no live worker credentials" | CI config (D-05) | `.github/workflows/ci.yml` `db`-tier selection | ✅ dedicated "Database tier (FakeWorker orchestration suite, QUAL-01)" step runs `uv run pytest -q -m db` | ✅ green |
| QUAL-01 (import guard, G-11-1) | `dark_factory.webhook.app` and every package module import with no database reachable | unit | `uv run pytest -q -m unit tests/unit/test_webhook_import_needs_no_database.py` | ✅ (4 tests, package-wide sweep + positive control) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/db/test_cross_machine_resume.py` — covers TRIG-01/TRIG-04/HITL-06 (D-06's SC1 two-subprocess proof), reusing `tests/support/subprocess_runner.py`'s `spawn`/`child_env` — built in 11-03, 2 tests, `pytest.mark.db`
- [x] `tests/db/test_webhook_dispatches_resume.py` — covers HITL-06 (dispatch half), sibling of `tests/db/test_webhook_resolves_answer.py` — built in 11-01, extended in 11-02, 6 tests covering all 4 dispatch outcomes
- [x] `tests/support/fake_github.py` — scripted `dispatch_workflow()` method + call-log entry present (lines 135-150), mirrors its existing four methods
- [x] `tests/unit/test_settings.py` — `dispatch_github_token`-specific tests present (3 tests), mirroring the existing `github_webhook_secret` test set
- [x] `.github/workflows/ci.yml` — dedicated "Database tier (FakeWorker orchestration suite, QUAL-01)" step runs `uv run pytest -q -m db`; `Unit and contract tiers` step unaffected (still `-m "unit or contract"`, intentionally no `DATABASE_URL` — see 11-06/G-11-1)

*Wave 0 also inherits Phase 10's `db`-tier test suite (177 test functions / 41 files) as already-passing coverage for QUAL-01 — no new stubs needed there, only CI wiring. All 5 items above independently confirmed present on disk during the 2026-10-01 audit (see Validation Audit log below) — not merely claimed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real GitHub Actions `workflow_dispatch` fires and `resume.yml` runs on a real repo | TRIG-01, TRIG-04, HITL-06 | Requires a real target repo with `resume.yml` installed and a real `dispatch_github_token` (fine-grained PAT, `Actions: Read and write`) | 1. Add `resume.yml` (D-04) to a real target repo. 2. Set `dispatch_github_token`. 3. Trigger a `WAITING_HUMAN` run via a real GitHub issue, reply to it. 4. Confirm the Actions tab shows a dispatched run and the Dark Factory run reaches its next state. |

*Manual-only for the live GitHub Actions dispatch; the cross-machine resume property itself (SC1) has full automated coverage via the two-subprocess `db`-tier proof (D-06) — this row is deployment-credential-bound, not a coverage gap.*

---

## Validation Audit 2026-10-01

| Metric | Count |
|--------|-------|
| Requirements audited | 4 (TRIG-01, TRIG-04, HITL-06, QUAL-01) |
| COVERED | 4 |
| PARTIAL | 0 |
| MISSING | 0 |
| Gap-closure plans folded in | 2 (11-06 → G-11-1, 11-07 → G-11-2) |

All 7 plans' PLAN/SUMMARY files read; every claimed test file confirmed present on disk via `ls`; test-function counts independently cross-checked against SUMMARY claims (exact match); `dispatch_workflow()` and dispatch-token tests confirmed in source; `ci.yml`'s `db`-tier step confirmed directly. No automated test run performed as part of this audit (relied on each plan's own reported pytest results, cross-checked against file existence/content) — the `db` tier takes over an hour against the real remote Neon rung and was already run twice (11-05, 11-06) within this execution.

One out-of-scope caveat carried forward, not a gap against this phase's requirements: `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this sandbox because a real `claude` CLI + credentials are on `PATH` — a sandbox artifact, unrelated to TRIG-01/04/HITL-06/QUAL-01.

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-10-01 — phase 11 is Nyquist-compliant; every requirement has automated coverage.
