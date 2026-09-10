---
status: testing
phase: 03-configuration-driven-pipeline
source: [03-VERIFICATION.md]
started: 2026-09-11T00:00:00Z
updated: 2026-09-11T00:00:00Z
---

## Current Test

number: 1
name: Whole Phase 1-3 suite against real Neon PostgreSQL 17
expected: |
  All db + integration tests pass; the ~15 mechanically-updated in-process
  start_run call sites still green with snapshot=DEFAULT_TEST_SNAPSHOT.
awaiting: user response

## Tests

### 1. Whole Phase 1-3 suite against real Neon PostgreSQL 17
command: `set -a; . ./.env; set +a; uv run pytest -q`
expected: All db + integration tests pass; the ~15 mechanically-updated in-process `start_run` call sites still green with `snapshot=DEFAULT_TEST_SNAPSHOT`.
why_human: The execution sandbox has no Docker / local initdb / DARK_FACTORY_TEST_DATABASE_URL and `.env` is behind a secret-read guard; conftest raises `pytest.UsageError`. Confirmed during verification: `uv run pytest tests/db/test_snapshot_roundtrip.py` → UsageError "No PostgreSQL 17 is reachable".
result: [pending]

### 2. SC1 end-to-end — config drives the executed pipeline
command: `uv run pytest -q tests/integration/test_config_drives_pipeline.py`
expected: `test_run_resolves_pipeline_from_config` emits CREATED→BA / BA→COMPLETED and persists the resolved snapshot; `test_reorder_and_shorten_workflow_roles_changes_the_executed_pipeline` shows [BA,QA] → [QA,BA] → [BA] each drive a different transition sequence, with `git diff --stat` over `orchestrator/` + `workflows/` empty.
why_human: Needs a real `dark-factory run` subprocess against PostgreSQL. Structural half (pipeline_from_snapshot builds from snapshot, no DEFAULT_PIPELINE / no role-name literal in orchestrator, transition() walks N nodes) verified via unit tests + spot-checks.
result: [pending]

### 3. SC2 end-to-end — role YAML drives behaviour
command: `uv run pytest -q tests/integration/test_role_yaml_drives_behaviour.py`
expected: Editing `BA.yaml` `after:` / `instructions:` / `worker:` changes the next run's persisted `runs.workflow` snapshot; instruction bytes inlined verbatim; `worker: copilot` reaches dispatch and fails with the Phase 8 `NotImplementedError`; SHA-256 of `src/dark_factory/**/*.py` unchanged across every edit.
why_human: Needs a real run subprocess + PostgreSQL to read back `runs.workflow`. Loader-side resolution/inlining verified against the real repo config.
result: [pending]

### 4. SC3 end-to-end — snapshot survives a config edit during pause
command: `uv run pytest -q tests/integration/test_snapshot_survives_edit.py`
expected: Pause [BA,QA] on NEEDS_INPUT, reorder `.dark-factory.yaml` to [QA,BA], `resume --answer` from a fresh process → transition lines continue BA→QA→COMPLETED (creation-snapshot order), same run id, exactly one `runs` row.
why_human: Needs subprocess pause/edit/resume against PostgreSQL. Structural half (`test_the_resume_path_can_never_reach_the_config_loader`) passes as a pure import-graph walk.
result: [pending]

### 5. SC4 — invalid config fails at run creation with no orphan run
command: `uv run pytest -q tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py`
expected: Each of 8 bad-config shapes raises `ConfigError` before `create_run` with the `runs` row count unchanged; a bad-config `dark-factory run` exits 2 with empty stdout line 1, stderr naming the offending file/field, `runs` count unchanged.
why_human: Needs PostgreSQL to count `runs` rows before/after. `ConfigError` raised for unknown worker / action / role name / unknown key / empty / non-mapping YAML — verified via direct `load_effective_config` + `RepoConfig` spot-checks; CLI maps `ConfigError`→`Exit(2)` before `start_run` (code inspection).
result: [pending]

### 6. CFG-04 runtime — before/after hooks fire through the ActionRegistry
command: `uv run pytest -q tests/db/test_role_hooks_invoked.py`
expected: before → worker → after invocation order; identical `ActionContext` remainder across two roles (no per-role branch); a newly-registered action referenced from a role's `after:` runs with zero orchestrator change; a legacy `{roles:[BA]}` snapshot invokes no hooks and still drives to COMPLETED.
why_human: Needs real commits against PostgreSQL. Invocation site verified by code inspection: `_run_hooks('before')/('after')` bracket the worker call in `_run_current_role`, outside `with session.begin()`, resolving names via `action_registry.get()`; `action_registry` threaded through `advance`/`drive`/`_advance_once`.
result: [pending]

### 7. CFG-05 round-trip — snapshot persists and reloads byte-equal
command: `uv run pytest -q tests/db/test_snapshot_roundtrip.py`
expected: `create_run` → `load_run_state`: `RunState.workflow` deep-equals `redact(snapshot)` incl. ordered roles + each `instruction_text` + repository/quality_gate/retry/publishing; a legacy `{roles:[BA]}` snapshot still round-trips and still builds a pipeline.
why_human: JSONB round trip needs PostgreSQL.
result: [pending]

### 8. Real-repo human walkthrough (carried from Phase 1/2/3-03)
command: In a real checkout, edit `.dark-factory.yaml` `workflow.roles` and a `.dark-factory/roles/*.yaml` field, run `dark-factory run`, observe the executed pipeline / role behaviour change with `git diff src/` empty.
expected: Behaviour changes with no source edit; a config edit during a WAITING_HUMAN pause does not affect the resumed run.
why_human: End-user-observable CLI behaviour against a real database and repository.
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
