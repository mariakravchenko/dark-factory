---
phase: "6"
slug: "tools-permissions-the-credential-boundary"
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Estimated runtime** | Unit: measured 15.47s this session (373 passed, 292 deselected) — baseline green before Phase 6 work starts. Full suite: not measured this session (requires `.env`); budget accordingly. |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m unit -q`
- **After every plan wave:** Run `set -a; . .env; set +a; uv run pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (unit suite currently ~15s; leaves headroom for Phase 6 additions before this needs revisiting)

---

## Per-Task Verification Map

*Task ID / Plan / Wave are set by the planner when PLAN.md is created — rows below are seeded at requirement granularity from 06-RESEARCH.md's Validation Architecture section.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | TOOL-01 | T-06-?? (V4) | `ToolRegistry.invoke()` denies unlisted capability before dispatch | unit | `uv run pytest tests/unit/test_tool_registry.py -x` | ❌ Wave 0 |
| TBD | TBD | TBD | TOOL-02 | — | Synthetic capability addable without editing a role executor | unit | `uv run pytest tests/unit/test_tool_registry_extensibility.py -x` | ❌ Wave 0 |
| TBD | TBD | TBD | TOOL-03 | T-06-?? (V4) | Deny-by-default per role, matching current `tools:` grants (incl. QA's new `repo.write_tests`/`shell.execute` grants) | unit + integration | `uv run pytest tests/unit/test_tool_registry.py tests/integration/test_real_pipeline_zero_config.py -x` | ❌ / ✓ (existing file extended) |
| TBD | TBD | TBD | TOOL-04 | T-06-?? (V6/credential) | Subprocess env dump shows no `DATABASE_URL`/`GITHUB_TOKEN` | integration (real OS subprocess) | `uv run pytest tests/integration/test_worker_env_boundary.py -x` | ❌ Wave 0 |
| TBD | TBD | TBD | TOOL-05 | T-06-?? (V4, elevation-of-privilege) | MCP transport proves list/call + deny-by-default; import-graph guard proves removability | unit (guard) + optional-dep-gated module | `uv run pytest tests/unit/test_no_mcp_import_in_core.py tests/unit/test_mcp_adapter.py -x` | ❌ Wave 0 |
| TBD | TBD | TBD | SEC-01 | T-06-?? (information disclosure) | Grep every artifact/prompt/event/log/report for known secrets — zero hits | integration | `uv run pytest tests/integration/test_phase6_acceptance.py -x` | ❌ Wave 0 |
| TBD | TBD | TBD | SEC-03 | T-06-?? (information disclosure) | Worker subprocess never inherits the full parent env | integration (same as TOOL-04) | `uv run pytest tests/integration/test_worker_env_boundary.py -x` | ❌ Wave 0 (same file as TOOL-04) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_tool_registry.py` — covers TOOL-01/TOOL-03
- [ ] `tests/unit/test_tool_registry_extensibility.py` — covers TOOL-02
- [ ] `tests/integration/test_worker_env_boundary.py` — covers TOOL-04/SEC-03 (real subprocess env dump, mirrors `tests/support/subprocess_runner.py`'s technique)
- [ ] `tests/unit/test_no_mcp_import_in_core.py` — covers TOOL-05's removability half (D-14); must pass whether or not `mcp` is installed (proves the import doesn't exist, not that it's skipped)
- [ ] `tests/unit/test_mcp_adapter.py` (or `tests/integration/`) — covers TOOL-05's transport half (D-12); gated with `pytest.importorskip("mcp")` per D-13 — note this project's `uv sync --all-extras --dev` installs every optional group, so in ordinary dev/CI this module is never actually skipped
- [ ] Framework install: `uv add --optional mcp "mcp>=2.2,<3"` — the one new runtime dependency this phase needs (flag with `checkpoint:human-verify` per the Package Legitimacy Audit in 06-RESEARCH.md — automated checker returned SUS on `too-new`/`unknown-downloads`, both false positives per manual verification, but the protocol still requires the checkpoint)

---

## Manual-Only Verifications

*All phase behaviors have automated verification per 06-RESEARCH.md's Validation Architecture — no manual-only items identified.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
