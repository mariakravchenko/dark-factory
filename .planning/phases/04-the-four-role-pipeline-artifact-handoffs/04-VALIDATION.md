---
phase: "4"
slug: "the-four-role-pipeline-artifact-handoffs"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-12"
updated: "2026-09-13"
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
| **Static gates** | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict), `uv run alembic check` |
| **Estimated runtime** | ~40-50 minutes for the `db`/`integration` tiers against remote Neon (each `advance()`/`drive()` step opens several short-lived `NullPool` sessions -- see 04-03-SUMMARY.md's Issues Encountered); unit tier stays sub-second |

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
| 04-02 T1 | INTAKE-02 | `spec:./task.md` loads a real task (`NormalizedTask` field set, heading-marker stripping, path resolution, missing/empty-file errors) | unit | `uv run pytest tests/unit/test_loaders.py -k spec -x` | ✅ COVERED |
| 04-02 T1 | INTAKE-02 / SC1 | CLI end-to-end run starts and drives from a spec file | integration | `uv run pytest tests/integration/test_spec_source_starts_a_run.py -x` | ✅ COVERED |
| 04-01 T1 | ORCH-04, ART-02 | BA hands `acceptance_criteria.json` to ARCHITECTURE through the `artifacts` table; a malformed artifact fails the role with zero `artifacts` rows | db | `uv run pytest tests/db/test_artifact_handoff.py -x` | ✅ COVERED |
| 04-01 T2 | CTX-01, CTX-02, CTX-03 / SC3 | `ContextBuilder` resolves `inputs` via the snapshot's `outputs` lists, includes capped baseline docs, loads examples as inert text, is idempotent, and never walks the source tree | unit | `uv run pytest tests/unit/test_context_builder.py tests/unit/test_no_tree_walk.py -x` | ✅ COVERED |
| 04-01 T3 | ART-01 | Artifact path resolution rejects traversal/absolute/symlink escapes; the size cap precedes any parse | unit | `uv run pytest tests/unit/test_artifact_paths.py -x` | ✅ COVERED |
| 04-03 T1 | ROLE-01, ROLE-06 | All five D-10 machine-artifact models are frozen/extra-forbid/min-length; `Verdict.computed_status` folds criteria+issues order-independently and rejects a declared/computed disagreement or a duplicate id | unit | `uv run pytest tests/unit/test_artifact_models.py -x` | ✅ COVERED |
| 04-03 T3 | ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04 / SC1 | BA -> ARCHITECTURE -> DEVELOPMENT -> QA run in pipeline order, one `COMPLETED` `role_executions` row per role, all seven SC1 files on disk, QA's `RoleContext` resolves inputs by declared filename (not pipeline adjacency) | db | `uv run pytest tests/db/test_four_role_pipeline.py -x` | ✅ COVERED |
| 04-03 T3 | ART-01, ART-03, STATE-05 / SC2 | Exactly seven `artifacts` rows, `role_execution_id`-attributed, checksum round-trips, `metadata={}`; no database column holds any artifact body text; a duplicate `(role_execution_id, path)` insert raises `IntegrityError` | db | `uv run pytest tests/db/test_artifact_persistence.py -x` | ✅ COVERED |
| 04-04 T1 | CTX-04 / SC4 | A superseded attempt's `ArtifactReference` row is never selected into a rebuilt context (content-based assertion) but survives on its own row for audit; a failed later attempt does not hide an earlier COMPLETED result; an in-flight-only attempt raises `MissingArtifactContentError` naming the role and filename; `build_role_context` writes no `artifacts` row | db | `uv run pytest tests/db/test_context_builder_retry_isolation.py -x` | ✅ COVERED |
| 04-04 T2 | ROLE-06, ART-02 / SC5 | An invalid/schema-violating/unreported machine artifact fails the role with a complete persisted error trail (status, error naming the filename, `ROLE_FAILED`+`RUN_FAILED` events, run `FAILED`, zero `artifacts` rows) and the artifact file (where one exists) remains on disk; Markdown completes unvalidated; misleading `WorkerResult` prose never changes the QA transition in either direction -- only `verdict.json`'s JSON contract does; `run_events` never leaves the ten-member `EventType` enum | db | `uv run pytest tests/db/test_artifact_schema_violation_fails_role.py -x` | ✅ COVERED |
| 04-04 T3 | SC1-SC5 / all 15 IDs | Acceptance gate maps every criterion and requirement id to present, substantive proof files with no opt-out call, drift-guarded against this document | integration | `uv run pytest tests/integration/test_phase4_acceptance.py -x` | ✅ COVERED |
| 04-05 T1-T2 (gap closure G-04-1) | ORCH-04, ROLE-04, ART-01, ART-02 / SC1 | Zero-config artifact synthesis derives criterion ids from the role's resolved `context.inputs` (never a second independent literal): `acceptance_criteria.json` -> `design.md` -> `implementation_summary.json` -> `test_report.json`/`verdict.json` all name the same ids, and renaming the origin id moves every downstream id with no other code change | unit + integration | `uv run pytest tests/unit/test_fake_worker_synthesis.py -q` and `set -a; . ./.env; set +a; uv run pytest tests/integration/test_real_pipeline_zero_config.py -x -q` | ✅ COVERED |

*Status: ✅ COVERED means the test targets the behavior and passed during the 2026-09-12 audit (this plan's own verification run).*

---

## Wave 0 Requirements

- [x] `tests/unit/test_context_builder.py` — covers CTX-01/02/03
- [x] `tests/db/test_four_role_pipeline.py` — covers ORCH-04, ROLE-01..04, ART-01
- [x] `tests/db/test_artifact_persistence.py` — covers ART-03, STATE-05
- [x] Rewrote `tests/unit/test_loaders.py::test_spec_loader_names_phase_4` and the `spec:` row in `tests/integration/test_unsupported_source.py` (04-02)
- [x] Added `"ArtifactReference"` to `tests/unit/test_single_mutation_path.py::_LIFECYCLE_CTORS` (04-01)
- [x] `tests/integration/test_phase4_acceptance.py` — the phase's own acceptance gate, mapping this phase's 5 success criteria + its 15 requirement IDs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | Status |
|----------|-------------|------------|-------------------|--------|
| A person who has never seen this codebase follows the handoff from `acceptance_criteria.json` through `design.md` to `verdict.json` in a real run's `.dark-factory/runs/<run-id>/artifacts/` tree and sees which criterion ids line up | SC1, ART-01 | The id-alignment half is machine-asserted (gap G-04-1, closed by plan 04-05: `tests/integration/test_real_pipeline_zero_config.py` proves BA's criterion ids appear in `design.md`, in `implementation_summary.json`'s summary, in `test_report.json`'s case names, and as `verdict.json`'s ordered `criterion_id` list). The readability judgment itself is not something a test decides. | Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files. | ✅ Readability re-check passed via `/gsd-verify-work 04` UAT (2026-09-13); id-alignment ✅ COVERED (G-04-1, plan 04-05) |

No other Phase 4 requirement is manual-only; every SC/requirement pairing above has a passing automated command.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 1s (unit tier)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-09-12 — all fifteen requirement IDs and all five success criteria have passing automated verification; the one manual-only row is explicitly deferred to `/gsd-verify-work`, matching the Phase 2/3 precedent for fresh-eyes UX checks.

## Validation Audit 2026-09-12

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

## Validation Audit 2026-09-13

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Re-audit after gap G-04-1 closure (plan 04-05) and the deferred readability UAT item passing. All fifteen requirement IDs and five success criteria remain fully covered; no new gaps introduced by the gap-closure plan.

Audit command: `set -a; . ./.env; set +a; uv run pytest -q` over the full suite (`unit` + `db` + `integration` + `contract`, all four phases): **541 passed, 0 failed, 0 skipped in 2796.02s (46m36s)**. Static gates also passed: `uv run alembic check` ("No new upgrade operations detected"), `uv run mypy src/dark_factory` (strict, 52 source files, no issues), `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (459 files already formatted). `tests/integration/test_phase4_acceptance.py`'s own 24 tests are included in the 541.
