---
phase: "3"
slug: "configuration-driven-pipeline"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-10"
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
| **Quick run command** | `uv run pytest -m "unit or contract"` (~0.2 s, no DB) |
| **Full suite command** | `set -a; . ./.env; set +a && uv run pytest` (`db`/`integration` need a reachable PostgreSQL 17) |
| **Static gates** | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict), `uv lock --check` |
| **Schema** | autouse `_schema_at_head` runs `alembic upgrade head` — picks up revision `0004` automatically **iff** the planner chooses the new-column snapshot option; no change if `runs.workflow` is reused |
| **Estimated runtime** | unit/contract ~0.2 s; config-drives-a-run integration tests dominated by FakeWorker + PG round-trips (~2–7 s each) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m "unit or contract"` (~0.2 s)
- **After every plan wave:** full `uv run pytest` (with `.env` sourced) + `ruff` + `mypy --strict`
- **Before `/gsd-verify-work`:** full suite green + `tests/integration/test_phase3_acceptance.py` green
- **Max feedback latency:** ~0.2 s (unit/contract tier)

---

## Per-Task / Requirement Verification Map

| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| SC1 / ORCH-02 / ORCH-03 | reorder `workflow.roles` and shorten it → executed transition sequence changes; `git diff --stat` of `orchestrator/` + `workflows/` empty across the two runs | integration | `uv run pytest tests/integration/test_config_drives_pipeline.py -x` | ❌ Wave 0 |
| SC1 (guard) | no `RunStatus` role-name literal in `orchestrator/` or `workflows/pipeline.py` | unit | `uv run pytest tests/unit/test_no_role_name_literal.py -x` | ❌ Wave 0 |
| SC2 / CFG-02 / CFG-03 | editing `.dark-factory/roles/BA.yaml` (worker, before/after, instructions path) changes what executes; instruction text is inlined into the snapshot | integration + db | `uv run pytest tests/integration/test_role_yaml_drives_behaviour.py tests/db/test_snapshot_roundtrip.py -x` | ❌ Wave 0 |
| SC3 / CFG-05 | pause a run (FakeWorker `NEEDS_INPUT` script), rewrite `.dark-factory.yaml`, `resume --answer`, assert executed order == snapshot order, not the edited file | integration | `uv run pytest tests/integration/test_snapshot_survives_edit.py -x` | ❌ Wave 0 |
| SC3 (guard) | `dark_factory.orchestrator.*` transitive imports exclude `dark_factory.config.loader` | unit | `uv run pytest tests/unit/test_orchestrator_no_live_config_read.py -x` | ❌ Wave 0 |
| SC4 / CFG-01 | unknown role name / unknown worker / unknown action / missing instruction file → `start_run` raises `ConfigError`, **no `runs` row inserted** (count before == count after), CLI exits 2 with no run id on stdout | db + integration | `uv run pytest tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py -x` | ❌ Wave 0 |
| CFG-04 | `ActionRegistry` resolves a configured hook name to a callable; unknown name → `UnknownActionError`; a newly registered action is usable from config with no orchestrator change | unit | `uv run pytest tests/unit/test_action_registry.py -x` | ❌ Wave 0 |
| CFG-04 (guard) | no module under `src/dark_factory/actions/` constructs `RunEvent` / `RoleExecution` / `HumanInteraction` or assigns `.status` | unit | `uv run pytest tests/unit/test_single_mutation_path.py -x` (already `rglob`s all of `src/`) | ✅ existing (no change) |
| WORK-02 | `WorkerRegistry` contains `claude-code` / `copilot` / `hermes`; `name in registry` works without invoking; invoking a placeholder raises `NotImplementedError` naming the phase | unit | `uv run pytest tests/unit/test_worker_registry_names.py -x` | ❌ Wave 0 |
| config schema | `RepoConfig` / `RoleDefinition` reject unknown keys (`extra="forbid"`), empty file, non-mapping top level, a `roles` entry that is not a `RunStatus` value; `yaml.safe_load` only | unit | `uv run pytest tests/unit/test_repo_config_schema.py -x` | ❌ Wave 0 |
| isolation | `config/repo_config.py` and `config/loader.py` import nothing from `config/settings.py` (and vice versa) | unit | `uv run pytest tests/unit/test_config_module_isolation.py -x` | ❌ Wave 0 |
| regression | `pipeline_from_snapshot` builds an N-node `Pipeline`; `transition()` walks it with no count assumption; a legacy `{"roles":["BA"]}` snapshot still loads | unit | `uv run pytest tests/unit/test_pipeline_from_snapshot.py tests/unit/test_lifecycle.py -x` | ⚠️ extend `test_lifecycle.py` |
| acceptance gate | SC1–SC4 + the 8 requirement IDs each map to a named, non-empty proof file | integration | `uv run pytest tests/integration/test_phase3_acceptance.py -x` | ❌ Wave 0 (sibling of `test_phase_acceptance.py` / `test_phase2_acceptance.py`) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add "pyyaml>=6,<7"`; commit `uv.lock` (Wave 0 **blocking** — the loader needs it)
- [ ] `src/dark_factory/config/repo_config.py` + `config/loader.py` (`ConfigError`) — the `.dark-factory.yaml` / role-YAML pydantic models + loader
- [ ] `src/dark_factory/actions/` package (`registry.py` + `context.py` + `builtins.py` + `__init__.py`) with built-in actions registered at import
- [ ] `WorkerRegistry.__contains__` + `claude-code` / `copilot` / `hermes` placeholder factories in `workers/registry.py`
- [ ] `workflows/pipeline.py::pipeline_from_snapshot`; remove the `DEFAULT_PIPELINE` production default (keep a test fixture)
- [ ] `.dark-factory.yaml` + `.dark-factory/roles/{BA,QA}.yaml` + `.dark-factory/instructions/{ba,qa}.md` — an example set the project can actually run against
- [ ] `.gitignore` += `.dark-factory/runs/`
- [ ] `tests/conftest.py` fixture: a `tmp_path`-based `.dark-factory/` builder (writes a `RepoConfig` + role YAMLs + instruction md into a temp dir, returns the root) — mirrors the `fake_settings` builder pattern
- [ ] extend `tests/unit/test_lifecycle.py` for `pipeline_from_snapshot` + N-node walks
- [ ] `tests/integration/test_phase3_acceptance.py` (sibling gate)
- [ ] if the `config_snapshot` column option is chosen: Alembic revision `0004` + `models.py` + `repositories.py` + `RunState` field + `migrations/env.py::_OWNED_TABLES` review

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A human edits `.dark-factory.yaml` / `.dark-factory/roles/*.yaml` in a real checkout and observes a run's behaviour change with no `git diff` in `src/` | SC1, SC2 | The automated tests prove the mechanism with a `tmp_path` config root; the "edit the real repo files and it just works" experience is a fresh-eyes check. | In a clean checkout, run `dark-factory run "<task>"`, note the transition sequence; reorder `workflow.roles`, run again, confirm the sequence changed and `git diff src/` is empty. |

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
