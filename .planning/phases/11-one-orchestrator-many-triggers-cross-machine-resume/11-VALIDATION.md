---
phase: "11"
slug: "one-orchestrator-many-triggers-cross-machine-resume"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-29"
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
| TRIG-01 | CLI/webhook/CI all funnel into `advance(run_id)`, no CI-only path | db (new) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py` | ❌ W0 | ⬜ pending |
| TRIG-04 | Run continues across local→CI boundary via Neon alone | db (new) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py` | ❌ W0 | ⬜ pending |
| HITL-06 | Resume on a different machine/process than the one that started it | db (new, extends existing SC2 idiom) | `uv run pytest -q -m db tests/db/test_cross_machine_resume.py` | ❌ W0 (sibling: `tests/integration/test_fresh_process_resume.py`) | ⬜ pending |
| HITL-06 (dispatch half) | Webhook receiver dispatches a real `workflow_dispatch` after `submit_answer` | db (new) | `uv run pytest -q -m db tests/db/test_webhook_dispatches_resume.py` | ❌ W0 (sibling: `tests/db/test_webhook_resolves_answer.py`) | ⬜ pending |
| QUAL-01 | Role transitions | db (existing) | `uv run pytest -q -m db tests/db/test_four_role_pipeline.py tests/db/test_transition_atomic.py` | ✅ | ⬜ pending |
| QUAL-01 | Artifact handoffs | db (existing) | `uv run pytest -q -m db tests/db/test_artifact_handoff.py` | ✅ | ⬜ pending |
| QUAL-01 | Pause/resume | db (existing) | `uv run pytest -q -m db tests/db/test_pause_mechanism_generic.py tests/db/test_resume_first_advance.py` | ✅ | ⬜ pending |
| QUAL-01 | QA rejection | db (existing) | `uv run pytest -q -m db tests/db/test_qa_bounce.py` | ✅ | ⬜ pending |
| QUAL-01 | Developer retries | db (existing) | `uv run pytest -q -m db tests/db/test_feedback_reaches_developer.py` | ✅ | ⬜ pending |
| QUAL-01 | Quality-gate retries | db (existing) | `uv run pytest -q -m db tests/db/test_quality_gate_gates_the_run.py` | ✅ | ⬜ pending |
| QUAL-01 | Retry exhaustion | db (existing) | `uv run pytest -q -m db tests/db/test_iteration_cap_exhaustion.py tests/db/test_loop04_adjacency.py` | ✅ | ⬜ pending |
| QUAL-01 | Publishing | db (existing) | `uv run pytest -q -m db tests/db/test_publish_step.py tests/db/test_publish_idempotency.py` | ✅ | ⬜ pending |
| QUAL-01 | "runs green in CI, no external AI calls, no live worker credentials" | CI config (D-05) | `.github/workflows/ci.yml` `db`-tier selection | ❌ W0 (CI never selects `db` tier today) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/db/test_cross_machine_resume.py` — covers TRIG-01/TRIG-04/HITL-06 (D-06's SC1 two-subprocess proof), reusing `tests/support/subprocess_runner.py`'s `spawn`/`child_env`
- [ ] `tests/db/test_webhook_dispatches_resume.py` — covers HITL-06 (dispatch half), sibling of `tests/db/test_webhook_resolves_answer.py`
- [ ] `tests/support/fake_github.py` — add a scripted `dispatch_workflow()` method + call-log entry (mirrors its existing four methods)
- [ ] `tests/unit/test_settings.py` — add `dispatch_github_token`-specific tests mirroring the existing `github_webhook_secret` test set
- [ ] `.github/workflows/ci.yml` — comment correction + `-m "unit or contract"` → `-m "unit or contract or db"`, `timeout-minutes` reviewed

*Wave 0 also inherits Phase 10's `db`-tier test suite (177 test functions / 41 files) as already-passing coverage for QUAL-01 — no new stubs needed there, only CI wiring.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real GitHub Actions `workflow_dispatch` fires and `resume.yml` runs on a real repo | TRIG-01, TRIG-04, HITL-06 | Requires a real target repo with `resume.yml` installed and a real `dispatch_github_token` (fine-grained PAT, `Actions: Read and write`) | 1. Add `resume.yml` (D-04) to a real target repo. 2. Set `dispatch_github_token`. 3. Trigger a `WAITING_HUMAN` run via a real GitHub issue, reply to it. 4. Confirm the Actions tab shows a dispatched run and the Dark Factory run reaches its next state. |

*Manual-only for the live GitHub Actions dispatch; the cross-machine resume property itself (SC1) has full automated coverage via the two-subprocess `db`-tier proof (D-06) — this row is deployment-credential-bound, not a coverage gap.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
