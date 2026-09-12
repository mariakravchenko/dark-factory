---
phase: "4"
slug: "the-four-role-pipeline-artifact-handoffs"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-12"
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `04-RESEARCH.md` § "Validation Architecture". Populated in full by `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9,<10` (`unit` / `db` / `integration` / `contract` markers, registered in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest -m unit -q` |
| **Full suite command** | `set -a; . ./.env; set +a; uv run pytest -q` |
| **Static gates** | `uv run ruff check .`, `uv run mypy src/dark_factory` (strict) |
| **Estimated runtime** | ~6 minutes (Phase 3 audit baseline: 102 tests in 5m51s; this phase adds `db` tests) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -m unit -q`
- **After every plan wave:** full suite (`db` + `integration` + `unit`) + `ruff check` + `mypy --strict`
- **Before `/gsd-verify-work`:** full suite green + `tests/integration/test_phase4_acceptance.py` green
- **Max feedback latency:** ~0.2s (unit tier)

---

## Per-Task / Requirement Verification Map

| Plan / Tasks | Req / SC | Behavior | Test Type | Automated Command | Status |
|--------------|----------|----------|-----------|-------------------|--------|
| TBD | INTAKE-02 | `spec:./task.md` loads a real task | unit | `uv run pytest tests/unit/test_loaders.py -k spec -x` | ⬜ pending (Wave 0 rewrite of `test_spec_loader_names_phase_4`) |
| TBD | INTAKE-02 / SC1 | CLI end-to-end run starts from a spec file | integration | `uv run pytest tests/integration/test_unsupported_source.py -x` (after removing the `spec:` row) + new `test_spec_source_starts_a_run.py` | ⬜ pending |
| TBD | ORCH-04, ROLE-01–04 / SC1 | Four roles run in sequence via `FakeWorker`, producing all 6 artifact files | db | `uv run pytest tests/db/test_four_role_pipeline.py -x` (new) | ⬜ pending |
| TBD | CTX-01, CTX-02, CTX-03 / SC3 | `ContextBuilder` resolves `inputs` to the correct filenames, includes baseline docs, never reads outside named files | unit | `uv run pytest tests/unit/test_context_builder.py -x` (new) | ⬜ pending |
| TBD | CTX-04 / SC4 | A superseded attempt's artifacts never appear in a rebuilt context | db | `uv run pytest tests/db/test_context_builder_retry_isolation.py -x` (new) | ⬜ pending |
| TBD | ART-01, ART-03, STATE-05 / SC2 | Every artifact has a matching `ArtifactReference` row; content is filesystem-only | db | `uv run pytest tests/db/test_artifact_persistence.py -x` (new) + `alembic check` | ⬜ pending |
| TBD | ROLE-06 / SC5 | A malformed `verdict.json` fails the role, not the run's summary prose | db | `uv run pytest tests/db/test_artifact_schema_violation_fails_role.py -x` (new) | ⬜ pending |
| TBD | SC1-SC5 / all 15 IDs | acceptance gate maps every criterion and requirement to present, substantive proof files | integration | `uv run pytest tests/integration/test_phase4_acceptance.py -x` (new, sibling of `test_phase3_acceptance.py`) | ⬜ pending |

*Status: ⬜ pending until the corresponding plan/task exists and its automated command passes. Filled in during `/gsd-validate-phase`.*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_context_builder.py` — covers CTX-01/02/03
- [ ] `tests/db/test_four_role_pipeline.py` — covers ORCH-04, ROLE-01..04, ART-01
- [ ] `tests/db/test_artifact_persistence.py` — covers ART-03, STATE-05
- [ ] Rewrite `tests/unit/test_loaders.py::test_spec_loader_names_phase_4` and the `spec:` row in `tests/integration/test_unsupported_source.py`
- [ ] Add `"ArtifactReference"` to `tests/unit/test_single_mutation_path.py::_LIFECYCLE_CTORS`
- [ ] `tests/integration/test_phase4_acceptance.py` — the phase's own acceptance gate, mapping this phase's 5 success criteria + its 15 requirement IDs

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 1s (unit tier)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
