---
phase: "08"
slug: "copilot-hermes-worker-independence-proven"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-21"
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`uv run pytest`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -m "unit or contract" -q` |
| **Full suite command** | `uv run pytest -m integration -q` (plus `-m db` for the live-Postgres tier) |
| **Estimated runtime** | ~260s quick (unit/contract) · ~350s per integration file group · ~30min for the full `-m db` tier |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m "unit or contract" -q` (fast, no external Postgres)
- **After every plan wave:** the plan's own `<verification>` block — typically the same unit/contract run plus the relevant `-m integration` file group
- **Before `/gsd-verify-work`:** Full integration suite green against a real PostgreSQL instance
- **Max feedback latency:** ~5 min (integration tests spawn real CLI subprocesses; the `-m db` tier is slower and reserved for full-phase closure, not per-task sampling)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | WORK-05 | unit | `pytest -m unit -q tests/unit/test_copilot_worker.py tests/unit/test_claude_code_worker.py tests/unit/test_settings.py tests/unit/test_native_tool_contract.py` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | WORK-05 | unit + contract | `pytest -m contract -q tests/contract/test_coding_worker_contract.py` | ✅ | ✅ green |
| 08-01-03 | 01 | 1 | WORK-05 | unit | `pytest -m "unit or contract" -q` | ✅ | ✅ green |
| 08-02-01 | 02 | 2 | WORK-06 | unit | `pytest -m unit -q tests/unit/test_hermes_worker.py tests/unit/test_native_tool_contract.py` | ✅ | ✅ green |
| 08-02-02 | 02 | 2 | WORK-06 | unit + contract | `pytest -m contract -q tests/contract/test_coding_worker_contract.py` | ✅ | ✅ green |
| 08-03-01 | 03 | 3 | QUAL-03 | integration | `pytest -q -rs tests/integration/test_copilot_live.py` (skips with reason when CLI absent) | ✅ | ✅ green |
| 08-03-02 | 03 | 3 | QUAL-03 | integration | `pytest -q -rs tests/integration/test_claude_code_live.py tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py` | ✅ | ✅ green |
| 08-03-03 | 03 | 3 | QUAL-03 | unit | `pytest -m unit -q tests/unit/test_worker_capabilities_match_behaviour.py` | ✅ | ✅ green |
| 08-04-01 | 04 | 3 | WORK-09 | unit | `pytest -m unit -q tests/unit/test_fake_cli_declared_outputs.py tests/unit/test_fake_worker_synthesis.py` | ✅ | ✅ green |
| 08-04-02 | 04 | 3 | WORK-09 | integration | `pytest -q tests/integration/test_real_pipeline_zero_config.py` | ✅ | ✅ green |
| 08-04-03 | 04 | 3 | WORK-09 | integration | `pytest -q tests/integration/test_role_reassignment_sc2.py` | ✅ | ✅ green |
| 08-05-01 | 05 | 4 | WORK-05, WORK-06, ROLE-05 | unit + integration | `pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py` | ✅ | ✅ green |
| 08-05-02 | 05 | 4 | WORK-05, WORK-06, ROLE-05 | integration | `pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py tests/integration/test_role_reassignment_sc2.py tests/integration/test_write_scope_enforcement.py tests/integration/test_real_pipeline_zero_config.py` | ✅ | ✅ green |
| 08-05-03 | 05 | 4 | TOOL-03 | unit | `pytest -m unit -q tests/unit/test_native_tool_contract.py tests/unit/test_copilot_worker.py tests/unit/test_hermes_worker.py` | ✅ | ✅ green |
| 08-06-01 | 06 | 5 | WORK-05, WORK-06, ROLE-05 | integration | `pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py` | ✅ | ✅ green |
| 08-06-02 | 06 | 5 | WORK-05, WORK-06, ROLE-05 | integration | `pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_exit_codes.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Every task across all six plans carries at least one `<automated>` verify command
(47 automated command invocations across 16 implementation tasks + 1
`checkpoint:decision` task in plan 08-02, which is a decision point, not an
implementation task, and carries no independent requirement verification of its
own). No `MISSING` gaps were found: every requirement this phase declares (WORK-05,
WORK-06, QUAL-03, WORK-09, ROLE-05, TOOL-03) has direct, currently-green automated
test coverage, confirmed by re-running the relevant commands during plan 08-06's
execution (2026-09-22): `pytest -m "unit or contract" -q` — 640 passed; the full
integration UAT set (10 tests, including the two files plan 08-06 repaired) — 10
passed, 0 failed.

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. No Wave 0 stub tests were needed — every plan shipped with its own automated `<verify>` commands from the start.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification. Phase 08's own UAT (`08-UAT.md`) recorded one human-judgment item during execution (already resolved — see `08-04-SUMMARY.md`/`08-05-SUMMARY.md` `coverage[].human_judgment: true` entries), which is a deliverable-level judgment call, not a missing per-task automated verify.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none found)
- [x] No watch-mode flags
- [x] Feedback latency < 5 min for the standard sampling loop (quick run + per-wave integration group)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-22

## Validation Audit 2026-09-22

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

This file existed as an unfilled `status: draft` template (seeded at plan-phase time,
2026-09-21) and was never populated during phase 08's six-plan execution. Audited and
filled retroactively from the six plans' `<automated>` verify commands and their
SUMMARY files' recorded results, cross-referenced against a live re-run of the
phase's test suites during plan 08-06's execution — no `gsd-nyquist-auditor` spawn
was needed since discovery found zero gaps to fill.
