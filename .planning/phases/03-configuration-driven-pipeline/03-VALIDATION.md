---
phase: "3"
slug: "configuration-driven-pipeline"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-10"
updated: "2026-09-11"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `03-RESEARCH.md` § "Validation Architecture". Populated in full by `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`unit` / `db` / `integration` / `contract` markers, registered in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest -m "unit or contract"` (no DB) |
| **Full suite command** | `uv run --env-file .env pytest` (`db`/`integration` need a reachable PostgreSQL 17) |
| **Static gates** | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict), `uv lock --check` |
| **Schema** | autouse `_schema_at_head` runs `alembic upgrade head` — picks up revision `0004` automatically **iff** the planner chooses the new-column snapshot option; no change if `runs.workflow` is reused |
| **Observed audit runtime** | Phase 3 proof set: 102 tests in 5m51s against PostgreSQL; unit/contract remains the fast feedback tier |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m "unit or contract"`
- **After every plan wave:** full `uv run pytest` (with `.env` sourced) + `ruff` + `mypy --strict`
- **Before `/gsd-verify-work`:** full suite green + `tests/integration/test_phase3_acceptance.py` green
- **Max feedback latency:** ~0.2 s (unit/contract tier)

---

## Per-Task / Requirement Verification Map

| Plan / Tasks | Req / SC | Behavior | Test Type | Automated Command | Status |
|--------------|----------|----------|-----------|-------------------|--------|
| 03-03 T1-T2 | SC1 / ORCH-02 / ORCH-03 | reorder and shorten `workflow.roles` changes the executed sequence without an orchestrator/workflow source edit | integration | `uv run --env-file .env pytest tests/integration/test_config_drives_pipeline.py -x` | ✅ COVERED |
| 03-03 T3 | SC1 / ORCH-03 guard | no `RunStatus` role-name literal in `orchestrator/` or `workflows/pipeline.py` | unit | `uv run pytest tests/unit/test_no_role_name_literal.py -x` | ✅ COVERED |
| 03-02 T3-T4; 03-04 T2 | SC2 / CFG-02 / CFG-03 | role YAML edits change fresh-run behavior and instruction text is inlined into the snapshot | integration + db | `uv run --env-file .env pytest tests/integration/test_role_yaml_drives_behaviour.py tests/db/test_snapshot_roundtrip.py -x` | ✅ COVERED |
| 03-04 T2 | SC3 / CFG-05 | a paused run resumes in snapshot order after the live config is reordered | integration | `uv run --env-file .env pytest tests/integration/test_snapshot_survives_edit.py -x` | ✅ COVERED |
| 03-03 T3; 03-04 T2 | SC3 / CFG-05 guard | orchestrator and answer-path transitive imports exclude `dark_factory.config.loader` | unit | `uv run pytest tests/unit/test_orchestrator_no_live_config_read.py -x` | ✅ COVERED |
| 03-03 T3 | SC4 / CFG-01 | malformed or unknown config fails before persistence; CLI exits 2 without a run id or orphan row | db + integration | `uv run --env-file .env pytest tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py -x` | ✅ COVERED |
| 03-01 T1; 03-04 T1 | SC4 / CFG-04 | actions resolve through the registry, hooks bracket the worker, and newly registered actions run without core changes | unit + db | `uv run --env-file .env pytest tests/unit/test_action_registry.py tests/db/test_role_hooks_invoked.py -x` | ✅ COVERED |
| 03-01 T1 | CFG-04 guard | actions cannot construct lifecycle records or assign lifecycle status | unit | `uv run pytest tests/unit/test_single_mutation_path.py -x` | ✅ COVERED |
| 03-01 T2 | WORK-02 | worker names support invoke-free membership and placeholders identify their delivery phase | unit | `uv run pytest tests/unit/test_worker_registry_names.py -x` | ✅ COVERED |
| 03-02 T3 | CFG-01 / config schema | config models forbid unknown keys and unsafe YAML; role values are validated | unit | `uv run pytest tests/unit/test_repo_config_schema.py -x` | ✅ COVERED |
| 03-02 T3 | CFG-01 isolation | repository config modules and secret settings remain import-isolated | unit | `uv run pytest tests/unit/test_config_module_isolation.py -x` | ✅ COVERED |
| 03-01 T3 | ORCH-02 regression | snapshot builder supports N-node and legacy pipelines; lifecycle walks without a count assumption | unit | `uv run pytest tests/unit/test_pipeline_from_snapshot.py tests/unit/test_lifecycle.py -x` | ✅ COVERED |
| 03-04 T3 | SC1-SC4 / all 8 IDs | acceptance gate maps every criterion and requirement to present, substantive proof files | integration | `uv run --env-file .env pytest tests/integration/test_phase3_acceptance.py -x` | ✅ COVERED |

*Status: ✅ COVERED means the test targets the behavior and passed during the 2026-09-11 audit.*

---

## Wave 0 Requirements

- [x] `pyyaml>=6,<7` and its lockfile entry are present (`uv lock --check` passes).
- [x] `src/dark_factory/config/repo_config.py` and `config/loader.py` provide the schema, loader, and `ConfigError`.
- [x] `src/dark_factory/actions/` provides the registry, context, built-ins, and import-time registrations.
- [x] `WorkerRegistry.__contains__` and the three placeholder worker factories are implemented.
- [x] `pipeline_from_snapshot` is implemented and the production orchestrator no longer defaults to `DEFAULT_PIPELINE`.
- [x] The tracked `.dark-factory.yaml`, role YAML, and instruction Markdown example set resolves successfully.
- [x] `.dark-factory/runs/` is ignored without ignoring configuration source files.
- [x] `tests/conftest.py` provides temp config-root builders and the real-repo snapshot fixture.
- [x] `tests/unit/test_lifecycle.py` covers the snapshot-built N-node walk.
- [x] `tests/integration/test_phase3_acceptance.py` provides the non-skipping acceptance gate.
- [x] Snapshot storage reuses `runs.workflow`; the approved 03-02 decision did not require Alembic revision `0004`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | Status |
|----------|-------------|------------|-------------------|--------|
| A human edits `.dark-factory.yaml` / `.dark-factory/roles/*.yaml` in a real checkout and observes a run's behaviour change with no `git diff` in `src/` | SC1, SC2 | The automated tests prove the mechanism with a `tmp_path` config root; the real-checkout experience is a fresh-eyes check. | Run `dark-factory run "<task>"`, reorder `workflow.roles`, run again, and confirm behavior changes while `git diff src/` stays empty. | ✅ Passed in `03-UAT.md` on 2026-09-11 |

No automated requirement is manual-only. The retained row is supplemental user-experience validation.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verification or completed Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verification
- [x] All Wave 0 references exist and pass
- [x] No watch-mode flags
- [x] Fast unit/contract feedback tier available; database proof tier is intentionally slower
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-09-11 — all eight requirement IDs have passing automated verification.

## Validation Audit 2026-09-11

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Audit command: `uv run --env-file .env pytest -q` over all 17 Phase 3 proof files named in this document and their regression companion tests: **102 passed in 351.61s**. Static gates also passed: `ruff check`, `ruff format --check src tests`, `mypy src/dark_factory`, and `uv lock --check`. The repository-wide format check reports two pre-existing `.opencode` Markdown formatting differences outside project source; no Phase 3 source or test file is affected.
