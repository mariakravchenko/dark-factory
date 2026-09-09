---
phase: "1"
slug: "walking-skeleton-one-durable-run"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-07"
validated: "2026-09-09"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `01-RESEARCH.md` § "Validation Architecture". Populated in full by `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`unit` / `db` / `integration` / `contract` markers, registered in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, four markers) |
| **Quick run command** | `uv run pytest -m "unit or contract"` (~0.2 s, no DB) |
| **Full suite command** | `set -a; . ./.env; set +a && uv run pytest` (`db`/`integration` need `DARK_FACTORY_TEST_DATABASE_URL`) |
| **Static gates** | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict) |
| **Measured runtime** | unit+contract ~0.2 s (173 tests); db+integration ~600–640 s against the remote test PostgreSQL (94 tests); full suite **267 passed** |
| **Postgres provisioning** | Rung 3 of the 01-01 probe ladder — externally-supplied `DARK_FACTORY_TEST_DATABASE_URL` (Docker + `initdb` absent on target). Per-test isolation: `Session(bind=conn, join_transaction_mode="create_savepoint")` inside a rolled-back outer transaction. |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m "unit or contract"`
- **After every plan wave:** full `uv run pytest` (with `.env` sourced)
- **Before `/gsd-verify-work`:** full suite green — met (267 passed)
- **Max feedback latency:** ~0.2 s (unit/contract tier)

---

## Per-Task / Success-Criterion Verification Map

| Success Criterion | Test Type | Named test(s) | Status |
|-------------------|-----------|---------------|--------|
| SC1 — `run text:"..."` → Neon → FakeWorker BA → terminal, zero AI | integration (`db`) | `tests/integration/test_walking_skeleton.py`; `tests/integration/test_exit_codes.py` | COVERED |
| SC2 — fresh-process resume from last committed step, no carryover | integration (`db`) | `tests/integration/test_fresh_process_resume.py`; `tests/db/test_resume_first_advance.py` | COVERED |
| SC3 — `status` reads columns, never folds `run_events` | unit + `db` | `tests/db/test_status_from_columns.py`; `tests/unit/test_status_import_graph.py` | COVERED |
| SC4 — crash between transition sub-writes leaves no half-state | `db` | `tests/db/test_transition_atomic.py`; `tests/db/test_state_event_pairing.py` | COVERED |
| SC5 — `DATABASE_URL`-shaped value redacted in every event payload + log line | integration + unit | `tests/integration/test_secret_redaction_e2e.py`; `tests/unit/test_redaction.py`; `tests/unit/test_log_redaction.py` | COVERED |
| Phase acceptance gate — SC1–SC5 each have a named passing test | integration | `tests/integration/test_phase_acceptance.py` | COVERED |

**Requirement IDs (17):** INTAKE-01/04/05, ORCH-01/05/06, STATE-01/02/03/06/07/08, WORK-01/03/08/10, SEC-02 — each has a real code + test basis and a `[x]` in `REQUIREMENTS.md`; confirmed by `01-VERIFICATION.md` (score 5/5 must-haves, status `passed`).

**Cross-cutting invariants:** each enforced by a structural or behavioral test — notably `tests/unit/test_single_mutation_path.py` (AST-proves `persistence/mutations.py` is the sole lifecycle writer), `tests/unit/test_status_import_graph.py`, `tests/unit/test_no_worker_name_leak.py`, `tests/unit/test_no_environ_copy.py`.

---

## Wave 0 Requirements

- [x] Test Postgres provisioning — externally-supplied `DARK_FACTORY_TEST_DATABASE_URL` selected by the 01-01 probe ladder; recorded in `01-01-SUMMARY.md`
- [x] `tests/conftest.py` — session-scoped `pg_url` / `engine` fixtures + `db_session` per-test rollback via native `join_transaction_mode="create_savepoint"`
- [x] `pyproject.toml` — `[tool.pytest.ini_options]` + `unit` / `db` / `integration` / `contract` markers (no `PytestUnknownMarkWarning`)
- [x] `uv` environment sync (`uv sync --all-extras --dev`, `uv.lock` committed)

---

## Manual-Only Verifications

| Verification | Why manual | Status |
|--------------|------------|--------|
| Real-Neon full-stack run (pooled `DATABASE_URL` + direct `DATABASE_URL_DIRECT`, PgBouncer transaction pooling) | External managed service; the pooled-vs-direct endpoint behavior the `engine.py` (`NullPool` + `prepare_threshold=None` + `pool_pre_ping`) and `migrations/env.py` settings target has no automated coverage — the suite only ran against a single-URL throwaway instance | ✓ PASSED — operator ran the documented README command against a real Neon PostgreSQL project on 2026-09-09: `alembic upgrade head` (0001 → 0002) clean via the direct endpoint, `run` drove `CREATED → BA → COMPLETED` twice, `status` + `--json` read `COMPLETED`/`BA`/`attempt 1` via the pooled endpoint, no PgBouncer/prepared-statement error. Recorded in `01-UAT.md`. |

---

## Validation Sign-Off

- [x] All success criteria have `<automated>` verify (named passing tests above); the one environmental check is UAT-verified
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (unit/contract ~0.2 s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-09-09

---

## Validation Audit 2026-09-09

| Metric | Count |
|--------|-------|
| Requirements audited | 17 |
| COVERED | 17 |
| PARTIAL | 0 |
| MISSING | 0 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated (manual-only) | 1 (real-Neon full-stack run — since UAT-verified) |

**Notes:**
- No coverage gaps: `01-VERIFICATION.md` (status `passed`, 5/5 must-haves) already cross-referenced every requirement ID and SC to a named passing test; full suite **267 passed**; `ruff` + `mypy --strict` clean. No `gsd-nyquist-auditor` dispatch required.
- Test-quality note (not a coverage gap): `tests/integration/test_status_cli.py::test_json_key_set_equals_the_text_field_set` carries a hardcoded 120 s subprocess timeout and can time out against the slow remote test DB; passes 8/8 in isolation. Consider raising or removing the fixed timeout.
- Deviation carried from execution: all automated `db`/`integration` runs used PostgreSQL 18.6 (operator-supplied), not Neon-parity PG 17; the version gate was loosened to a "17+ floor" by explicit decision. Assessed in `01-VERIFICATION.md` as not undermining any durability guarantee (standard SQL/MVCC, identical 17↔18); the real-Neon manual check above closes the residual Neon/PgBouncer-specific risk.
