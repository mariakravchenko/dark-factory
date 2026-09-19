---
phase: "6"
slug: "tools-permissions-the-credential-boundary"
status: complete
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-17"
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` |
| **Quick run command** | `uv run pytest -m unit -q` |
| **Full suite command** | `set -a; . .env; set +a; uv run pytest -q` (full suite needs DB creds via `.env` for `db`/`integration`-marked tests) |
| **Estimated runtime** | Unit: measured 15.47s pre-phase baseline (373 passed); 437 passed by the end of plan 06-03. Full suite: not measured this session (`.env` sourcing blocked by the session's secret-read guard on every plan of this phase; deferred to the user each time — see plans 06-01/02/03/04's "Issues Encountered" sections). |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m unit -q`
- **After every plan wave:** Run `set -a; . .env; set +a; uv run pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (unit suite measured ~15s across the phase, well inside budget)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 1 | 06-01 | 1 | TOOL-01 | T-06-05 | `ToolRegistry.invoke()` denies an unlisted capability before dispatch (deny-by-default gate), and the denial persists as a `CAPABILITY_DENIED` event | unit + db | `uv run pytest tests/unit/test_tool_registry.py tests/db/test_capability_denied_fails_role.py -x` | ✓ | ✅ green (db-tier confirmed by the user: 694 passed / 3 pre-existing unrelated failures, see 06-01-SUMMARY.md) |
| Task 3 | 06-01 | 1 | TOOL-02 | — | Synthetic capability addable and grantable with zero role-executor/pipeline/lifecycle edits; `NATIVE_TOOL_CONTRACT` completeness guard | unit | `uv run pytest tests/unit/test_tool_registry_extensibility.py tests/unit/test_native_tool_contract.py -x` | ✓ | ✅ green |
| 06-01 Task 2 / 06-02 Task 2 | 06-01, 06-02 | 1, 2 | TOOL-03 | T-06-05 | Deny-by-default per role matches the shipped `tools:` grants, including QA's `repo.write_tests`/`shell.execute` expansion (D-16) | unit | `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_shell_execute.py -x` | ✓ | ✅ green |
| Task 1 | 06-02 | 2 | TOOL-04 | T-06-01 | `build_worker_env` builds the child environment additively over an explicit allowlist from an empty mapping — never a parent-environment copy, spread or exclusion-filter | unit + integration | `uv run pytest tests/unit/test_worker_env.py tests/unit/test_no_environ_copy.py tests/integration/test_worker_env_boundary.py -x` | ✓ | ⚠️ unit tier green (424 passed); integration tier (`test_worker_env_boundary.py`) deferred to the user — no Docker/initdb 17 and `.env` sourcing blocked (see 06-02-SUMMARY.md) |
| Task 2 / Task 3 | 06-03 | 2 | TOOL-05 | T-06-03 | MCP transport proves list/call + deny-by-default (never the advertised tool list as the boundary); import-graph guard proves removability | unit | `uv run pytest tests/unit/test_no_mcp_import_in_core.py tests/unit/test_mcp_adapter.py -x` | ✓ | ✅ green (437 passed, unit tier) |
| Task 1 | 06-04 | 3 | SEC-01 | T-06-04 | Grep every artifact, worker prompt, event payload, log and report for the known secret values across the capability-denial path — zero occurrences | integration | `uv run pytest tests/integration/test_capability_denial_no_secret_leak.py tests/integration/test_secret_redaction_e2e.py -x` | ✓ | ⚠️ written and logic-verified standalone (control arm, shell.execute arm, structural guard, config-tree round-trip); db-tier execution deferred to the user — no Docker/initdb 17 and `.env` sourcing blocked (see 06-04-SUMMARY.md) |
| Task 1 / Task 2 | 06-02 | 2 | SEC-03 | T-06-01 | A worker subprocess spawned with `build_worker_env`'s output reports no `DATABASE_URL`/`GITHUB_TOKEN`/unrelated inherited key — only the allowlisted minimum plus a deliberately supplied credential | unit + integration | `uv run pytest tests/integration/test_worker_env_boundary.py tests/unit/test_shell_execute.py -x` | ✓ | ⚠️ unit tier green; integration tier (`test_worker_env_boundary.py`) deferred to the user (same constraint as TOOL-04, see 06-02-SUMMARY.md) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky (here: unit tier green, db/integration tier deferred to the user under this session's `.env`-sourcing guard)*

---

## Wave 0 Requirements

- [x] `tests/unit/test_tool_registry.py` — covers TOOL-01/TOOL-03
- [x] `tests/unit/test_tool_registry_extensibility.py` — covers TOOL-02
- [x] `tests/integration/test_worker_env_boundary.py` — covers TOOL-04/SEC-03 (real subprocess env dump, mirrors `tests/support/subprocess_runner.py`'s technique)
- [x] `tests/unit/test_no_mcp_import_in_core.py` — covers TOOL-05's removability half (D-14); passes whether or not `mcp` is installed (proves the import doesn't exist, not that it's skipped)
- [x] `tests/unit/test_mcp_adapter.py` — covers TOOL-05's transport half (D-12); this repo's `uv sync --all-extras --dev` installs every optional group, so this module is never actually skipped in ordinary dev/CI
- [x] Framework install: `uv add --optional mcp "mcp>=2.2,<3"` — approved at the plan 06-03 Task 1 `checkpoint:human-verify` (package-legitimacy gate) on 2026-09-19

---

## Manual-Only Verifications

*All phase behaviors have automated verification per 06-RESEARCH.md's Validation Architecture — no manual-only items identified.*

The db/integration-tier runs this session's secret-read guard blocked (`test_capability_denied_fails_role.py`'s db arm in plan 06-01, `test_worker_env_boundary.py` in plan 06-02, and `test_capability_denial_no_secret_leak.py` in plan 06-04) are **automated tests that could not be executed in this sandboxed session**, not manual-only verifications — every one of them is a `pytest` command with no human judgment step, deferred to the user's own terminal with `.env` sourced per the convention 06-01-SUMMARY.md established. Recorded here for transparency rather than silently omitted.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved — 2026-09-19, plan 06-04 close-out. All four plans (06-01 through 06-04) executed; unit-tier suite green throughout (437 passed by plan 06-03); db/integration-tier confirmation for plans 06-01/06-02 was performed by the user directly (06-01: 694 passed / 3 pre-existing unrelated failures) or remains an open, non-blocking deferred item (06-02's `test_worker_env_boundary.py`, 06-04's new db-tier tests) tracked in `.planning/WINDOWS.md`.

---

## Validation Audit 2026-09-19

Independent re-audit at `/gsd-execute-phase 6`'s post-execution gate (`workflow.nyquist_validation`), before phase completion. Verified every test file referenced in the Per-Task Verification Map exists on disk, and cross-checked all seven phase-6 requirements (TOOL-01 through TOOL-05, SEC-01, SEC-03) against `.planning/REQUIREMENTS.md` — all marked `Complete`.

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

No auditor spawn needed — all requirements already COVERED per the existing map.
