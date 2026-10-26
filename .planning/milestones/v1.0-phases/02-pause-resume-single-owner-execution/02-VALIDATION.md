---
phase: "2"
slug: "pause-resume-single-owner-execution"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-09"
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `02-RESEARCH.md` § "Validation Architecture". Populated in full by `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`unit` / `db` / `integration` / `contract` markers, registered in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest -m "unit or contract"` (~0.2 s, no DB) |
| **Full suite command** | `set -a; . ./.env; set +a && uv run pytest` (`db`/`integration` need `DARK_FACTORY_TEST_DATABASE_URL`) |
| **Static gates** | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict) |
| **Schema** | autouse `_schema_at_head` runs `alembic upgrade head` → picks up revision `0003` with no fixture change |
| **Estimated runtime** | unit/contract ~0.2 s; the two heartbeat/expiry integration tests are the slowest at ~7 s each (bounded by design — short injected TTLs, no real minutes) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m "unit or contract"` (~0.2 s)
- **After every plan wave:** full `uv run pytest` (with `.env` sourced)
- **Before `/gsd-verify-work`:** full suite green + `ruff` + `mypy --strict`
- **Max feedback latency:** ~0.2 s (unit/contract tier)

---

## Per-Task / Requirement Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STATE-04 | `human_interactions` row shape, enum CHECK, partial unique index rejects a 2nd `WAITING` | db | `uv run pytest tests/db/test_human_interactions_schema.py -x` | ❌ Wave 0 |
| HITL-01 | any pipeline node returning `NEEDS_INPUT` pauses via the same code (parametrize over a 2-node test pipeline) | db | `uv run pytest tests/db/test_pause_mechanism_generic.py -x` | ❌ Wave 0 |
| HITL-02 | pause path persists all 5 things (result, session id, current_role, interaction, events) in one txn; lease cleared; exit 0 | db + integration | `uv run pytest tests/db/test_pause_path_atomic.py tests/integration/test_pause_exit_zero.py -x` | ❌ Wave 0 |
| HITL-03 | `resume <id> --answer` from a fresh subprocess → same run, same attempt, `worker.resume` path, interaction `ANSWERED` | integration | `uv run pytest tests/integration/test_resume_with_answer.py -x` | ❌ Wave 0 |
| HITL-07 | two racing processes → exactly one advances; loser exits 0, no status change, no duplicate `ROLE_COMPLETED` | integration | `uv run pytest tests/integration/test_single_owner_race.py -x` | ❌ Wave 0 |
| HITL-07 | N threads call `claim_lease` concurrently → exactly one token | db | `uv run pytest tests/db/test_lease_claim_atomic.py -x` | ❌ Wave 0 |
| HITL-08 | no `idle in transaction` backend during the worker call (`pg_stat_activity` by `application_name`) | integration | `uv run pytest tests/integration/test_no_txn_across_worker.py -x` | ❌ Wave 0 |
| SC4 | killed owner → lease not stolen before expiry; reclaimed after (forced-past-expiry SQL + one real short sleep) | integration | `uv run pytest tests/integration/test_lease_expiry_reclaim.py -x` | ❌ Wave 0 |
| SC5 | slow step (short TTL, sleeping fake) heartbeats; competing process never claims during the step; `lock_expires_at` advances ≥ 3× | integration | `uv run pytest tests/integration/test_heartbeat_slow_step.py -x` | ❌ Wave 0 |
| SC5 | heartbeat failure (token stolen mid-step) → main thread aborts, nothing persisted, exit ≠ 0; `apply_transition` `LeaseLost` fence | db | `uv run pytest tests/db/test_lease_lost_aborts_step.py -x` | ❌ Wave 0 |
| SEC-01/02 | fake secret seeded in question **and** answer → zero occurrences in `human_interactions`, events, logs | integration + unit | `uv run pytest tests/integration/test_redaction_interactions.py tests/unit/test_single_mutation_path.py -x` | ⚠️ extend existing `test_single_mutation_path.py` |
| regression | `transition()` `ROLE_NEEDS_INPUT` arm; `advance()` early-returns on `WAITING_HUMAN`; `STOP_STATUSES` membership | unit | `uv run pytest tests/unit/test_lifecycle.py tests/unit/test_domain_enums.py -x` | ⚠️ extend existing |
| contract | `FakeWorker.resume()` returns a valid `WorkerResult` | contract | `uv run pytest -m contract -x` | ⚠️ extend `tests/contract/test_coding_worker_contract.py` |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Properties covered by the existing FakeWorker orchestration suite (extended, not new files)

- Transition-graph legality with the new `ROLE_NEEDS_INPUT` arm — `tests/unit/test_lifecycle.py`.
- Drive-loop stop on `WAITING_HUMAN` — `tests/db/test_terminal_advance_noop.py` (extend: `WAITING_HUMAN` is a stop, not terminal).
- Fresh-process resume mechanics (attempt unchanged, no new run) — `tests/integration/test_fresh_process_resume.py` proves the no-answer path; the `--answer` path is a sibling test.
- Crash-consistency of the pause transition — reuse the `after_cursor_execute` injection recipe from `tests/db/test_transition_atomic.py`, parametrized over the interaction-insert and the runs-update sub-writes.

---

## Wave 0 Requirements

- [ ] Alembic revision `0003_pause_resume_lease.py` — `human_interactions` table + `runs.owner_token` / `runs.lock_expires_at` (Wave 0 **blocking** — every `db` test needs the schema)
- [ ] `Settings.lease_ttl_seconds` (default 900) + `Settings.lease_heartbeat_seconds` (default 300) + a test override fixture (mirror `use_fake_secrets`)
- [ ] `FakeWorker` slow knob: `DARK_FACTORY_FAKE_SLEEP_MS` env var (and/or a `sleep_ms` field on the scripted `WorkerResult` metadata) + a `fake_worker_registry` variant that honors it
- [ ] `application_name=dark-factory` in the engine `connect_args` so the `pg_stat_activity` assertion can filter
- [ ] `tests/support/subprocess_runner.py` — lift `_ENV_ALLOWLIST` / `_child_env` / `_spawn` out of `tests/integration/test_fresh_process_resume.py` into a shared helper, add a `fake_sleep_ms` param
- [ ] `tests/conftest.py` fixture: `force_lease_expiry(run_id)` → `UPDATE runs SET lock_expires_at = now() - interval '1 second'`
- [ ] Extend `tests/unit/test_single_mutation_path.py` AST guard to include `HumanInteraction` construction
- [ ] `migrations/env.py` `_OWNED_TABLES` += `"human_interactions"` (otherwise `alembic check` proposes to drop it)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lease TTL / heartbeat behavior against a real Neon PgBouncer transaction-pooled endpoint (production TTL values, not injected 2 s) | HITL-07, HITL-08, SC5 | Production TTL is 900 s; an end-to-end real-minute test is impractical in CI. The injected-short-TTL integration tests prove the mechanism; the production-scale timing is an operator smoke check. | Pause a run, kill the owner, confirm a second process does not claim before `lock_expires_at`, then claims after; run a deliberately slow step and confirm `lock_expires_at` advances while it runs. |

*Populated fully by `/gsd-validate-phase`.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
