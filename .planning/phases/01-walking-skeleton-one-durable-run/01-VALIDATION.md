---
phase: "1"
slug: "walking-skeleton-one-durable-run"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-07"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `01-RESEARCH.md` § "Validation Architecture". Populated in full by `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`unit` / `integration` / `db` markers) |
| **Config file** | none — Wave 0 installs (`pyproject.toml` `[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -m unit` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds (unit), longer once `db`/`integration` tiers need a Postgres |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m unit`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (unit tier)

---

## Per-Task Verification Map

> Filled by `/gsd-validate-phase` against the finalized `01-PLAN.md` task IDs. Research maps
> the five success criteria to seams as follows:

| Success Criterion | Test Type | Seam |
|-------------------|-----------|------|
| SC1 — `run text:"..."` → Neon → FakeWorker BA → terminal | integration (`db`) | subprocess `python -m dark_factory run` against a real Postgres |
| SC2 — fresh-process resume from last committed step | integration (`db`) | subprocess kill mid-run + `resume`, no in-memory carryover |
| SC3 — `status` reads columns, never folds events | unit + `db` | assert `status` query touches `runs` / latest `role_executions` only |
| SC4 — crash between transition sub-writes leaves no half-state | `db` | `after_cursor_execute` listener raises before COMMIT; assert full rollback |
| SC5 — `DATABASE_URL`-shaped value redacted in every event payload + log line | unit + `db` | real structlog sink (not `capture_logs`); grep known secret value → 0 |

---

## Wave 0 Requirements

- [ ] Test Postgres provisioning — choose testcontainers `postgres:17-alpine` **or** `pytest-postgresql` **or** a Neon test branch (Docker / `initdb` / `DATABASE_URL` all unverified on target — **BLOCKING**)
- [ ] `tests/conftest.py` — session-scoped engine fixture + per-test transaction/SAVEPOINT rollback
- [ ] `pyproject.toml` — `pytest` config + `unit` / `integration` / `db` markers
- [ ] `uv` environment sync (`uv sync --all-extras --dev`)

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
