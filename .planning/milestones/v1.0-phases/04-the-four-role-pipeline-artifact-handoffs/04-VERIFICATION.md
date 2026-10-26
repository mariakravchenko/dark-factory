---
phase: 04-the-four-role-pipeline-artifact-handoffs
verified: 2026-09-13T20:15:00Z
status: passed
score: 20/20 must-haves verified
covered_files: [".dark-factory.yaml", ".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-05-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-05-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW-FIX.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-SECURITY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-UAT.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md", "migrations/env.py", "migrations/versions/0004_artifacts.py", "src/dark_factory/actions/builtins.py", "src/dark_factory/artifacts/__init__.py", "src/dark_factory/artifacts/paths.py", "src/dark_factory/artifacts/store.py", "src/dark_factory/artifacts/validation.py", "src/dark_factory/config/loader.py", "src/dark_factory/context/__init__.py", "src/dark_factory/context/builder.py", "src/dark_factory/domain/artifacts.py", "src/dark_factory/domain/status.py", "src/dark_factory/input/loaders.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/persistence/models.py", "src/dark_factory/persistence/mutations.py", "src/dark_factory/roles/registry.py", "src/dark_factory/workers/fake.py", "tests/conftest.py", "tests/db/test_artifact_handoff.py", "tests/db/test_artifact_persistence.py", "tests/db/test_artifact_schema_violation_fails_role.py", "tests/db/test_context_builder_retry_isolation.py", "tests/db/test_four_role_pipeline.py", "tests/integration/test_phase4_acceptance.py", "tests/integration/test_real_pipeline_zero_config.py", "tests/integration/test_spec_source_starts_a_run.py", "tests/support/fake_artifacts.py", "tests/unit/test_artifact_models.py", "tests/unit/test_artifact_paths.py", "tests/unit/test_context_builder.py", "tests/unit/test_fake_worker_synthesis.py", "tests/unit/test_loaders.py", "tests/unit/test_no_tree_walk.py"]
covered_digest: "v1:sha256:1629598b6842b864c6c8bb593f04d7de97fbdcdae4151f07fa958f6daa6d2438"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 20/20
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 4: The Four-Role Pipeline & Artifact Handoffs Verification Report

**Phase Goal:** BA → Architect → Developer → QA hand off through durable artifacts (a file on disk plus an `ArtifactReference` row in Neon) with machine-readable verdicts, so the pipeline is a sequence of independent role executions rather than one shared agent conversation.
**Verified:** 2026-09-13T20:15:00Z
**Status:** passed
**Re-verification:** Yes — freshness re-run. No source code changed since the prior fully-content-verified pass (`919bace` → `fb8ce12`, `git diff --stat fb8ce12..HEAD -- src/ tests/` is empty). This pass exists solely to confirm the one previously-deferred human-verification item is now closed and to re-fingerprint `04-VERIFICATION.md` against the current state of `.planning/` tracking documents.

## What changed since the prior pass

The prior `04-VERIFICATION.md` (2026-09-13T16:52:13Z) scored 20/20 must-haves — 5/5 ROADMAP success criteria, all 15 requirement IDs, all artifacts and key links — but held overall status at `human_needed` solely because one explicitly-deferred manual item remained open: "Fresh-eyes readability of a real run's artifact tree." No truth, artifact, or key link had failed; the gate was purely the unresolved human checkpoint.

Since that pass, in order, and confirmed by `git log`:

1. **UAT resolution** (`ecf10e3` → `ae543ef`, `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-UAT.md`): the project owner ran `uv run dark-factory run spec:./task.md` against this repository, opened `.dark-factory/runs/<run-id>/artifacts/` by hand, read all seven files, and typed `pass`. `04-UAT.md` frontmatter: `status: complete`; body: `total: 1, passed: 1, issues: 0, pending: 0, skipped: 0, blocked: 0`; the single test's `result: pass`. This is the exact item this verification's Human Verification Required section named — closed.
2. **Validation re-audit** (`191393f`, `04-VALIDATION.md`): re-audited Nyquist coverage; `nyquist_compliant: true`, `status: validated`, "Validation Audit 2026-09-13" section records `Gaps found: 0`, `Resolved: 0`, `Escalated: 0` — already fully covered by plan 04-05's own proofs, no new work triggered.
3. **Security re-audit** (`0867970`, `04-SECURITY.md`): merged plan 04-05's own `<threat_model>` block (T-04-19 through T-04-22, plus T-04-SC scope update) into the phase threat register; `threats_open: 0`, `status: verified`. Security Audit Trail's 2026-09-13 row records grep-level re-verification of each new mitigation directly against `src/dark_factory/workers/fake.py`.

`git diff --stat fb8ce12..HEAD -- src/ tests/` is empty — no `src/` or `tests/` file changed across any of these three steps; only `.planning/` tracking documents (`04-UAT.md`, `04-VALIDATION.md`, `04-SECURITY.md`) were updated to record closure. This verifier independently confirmed that emptiness rather than trusting the SUMMARY/UAT narrative.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

All five carried forward unchanged from the prior fully-verified pass — source files backing each are confirmed byte-identical (`git diff --stat fb8ce12..HEAD` empty for all of `context/builder.py`, `domain/artifacts.py`, `persistence/models.py`, `artifacts/{paths,store,validation}.py`, the migration, and role YAMLs).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | A run started from `spec:./task.md` executes all four roles in order on `FakeWorker` and produces `requirements.md` + `acceptance_criteria.json`, `design.md` + `constraints.json`, `implementation_summary.json`, and `test_report.json` + `verdict.json` under `.dark-factory/runs/<run-id>/`, and the handoff is legible — downstream artifacts carry BA's criterion ids, not id-free placeholders (G-04-1, closed by 04-05). | ✓ VERIFIED | `tests/db/test_four_role_pipeline.py`, `tests/integration/test_spec_source_starts_a_run.py` (structural), `tests/unit/test_fake_worker_synthesis.py` + `tests/integration/test_real_pipeline_zero_config.py`'s content-assertion block (id-derivation). Plus, as of this pass, direct human confirmation via `04-UAT.md`: a person read a real run's seven-file artifact tree end to end and confirmed the handoff is followable — resolving the last open item. |
| SC2 | Every artifact has an `ArtifactReference` row in Neon while its content stays on the filesystem — no artifact body is stored in the database. | ✓ VERIFIED | `tests/db/test_artifact_persistence.py`; `persistence/models.py`/`artifacts/store.py` unchanged since prior pass. |
| SC3 | A role's context contains only the prior artifacts its configuration selects, plus repository document paths and any human answers — never a dump of the repository source tree. | ✓ VERIFIED | `tests/unit/test_context_builder.py`, `tests/unit/test_no_tree_walk.py`; `context/builder.py` unchanged. |
| SC4 | A retried attempt's rebuilt context contains no artifact from the superseded attempt. | ✓ VERIFIED | `tests/db/test_context_builder_retry_isolation.py`; `context/builder.py` unchanged. |
| SC5 | A machine artifact that violates its JSON schema fails the role with a persisted error instead of advancing the run, and the transition after QA is decided by `verdict.json`, never by summary prose. | ✓ VERIFIED | `tests/db/test_artifact_schema_violation_fails_role.py`; `domain/artifacts.py::Verdict` unchanged. |

**Score:** 5/5 ROADMAP success criteria verified, 0 present-but-behavior-unverified.

### Requirements Coverage (15 IDs)

All 15 requirement IDs declared across the five plans (`INTAKE-02` in 04-02; `ORCH-04, ROLE-01, ROLE-02, CTX-01..04, ART-01..03, STATE-05` in 04-01; `ORCH-04, ROLE-01..04, ROLE-06, ART-01..03, STATE-05` in 04-03; the full set of 15 in 04-04; `ORCH-04, ROLE-04, ART-01, ART-02` in 04-05) are **✓ SATISFIED**. Independently re-confirmed this pass: `grep -E "..." .planning/REQUIREMENTS.md | grep -i "phase 4"` returns all 15 IDs (`INTAKE-02, ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04, ROLE-06, CTX-01, CTX-02, CTX-03, CTX-04, ART-01, ART-02, ART-03, STATE-05`), each marked `Complete` and mapped to `Phase 4`, exactly matching the phase's declared requirement list. No orphaned requirements.

### Required Artifacts

Unchanged from the prior pass — no `src/`/`tests/` file touched since. Re-confirmed present, substantive, and wired this pass:

| Artifact | Expected | Status |
|----------|----------|--------|
| `src/dark_factory/workers/fake.py` | Input-aware criterion-id extraction and synthesis (G-04-1) | ✓ VERIFIED — exists, substantive, wired (imported by `orchestrator/runner.py` via the worker registry) |
| `tests/unit/test_fake_worker_synthesis.py` | Derivation + falsification proof | ✓ VERIFIED — exists, substantive |
| `tests/integration/test_real_pipeline_zero_config.py` | Content-assertion regression guard | ✓ VERIFIED — exists, substantive |
| `tests/integration/test_phase4_acceptance.py` | Phase drift guard, both new proof files registered | ✓ VERIFIED — `grep` confirms both files appear in `_VALIDATION_PROOF_FILES` |
| `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md` | Reconciled ledger, re-audited | ✓ VERIFIED — `nyquist_compliant: true`, 2026-09-13 audit row present, 0 gaps |
| `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-SECURITY.md` | Threat register, re-audited | ✓ VERIFIED — `threats_open: 0`, `status: verified`, 2026-09-13 audit row present, 23 threats all closed |
| `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-UAT.md` | Human verification record | ✓ VERIFIED — `status: complete`, 1/1 passed, 0 issues, 0 gaps |
| All artifacts verified in earlier passes (migration, `domain/artifacts.py`, `context/builder.py`, `artifacts/{paths,store,validation}.py`, role YAMLs, `roles/registry.py`, the four `db`-tier proof files) | Unchanged | ✓ VERIFIED — `git diff --stat fb8ce12..HEAD -- src/ tests/` empty |

### Key Link Verification

Unchanged from the prior pass (no source touched):

| From | To | Via | Status |
|------|-----|-----|--------|
| `context.inputs` (resolved upstream artifact content) | criterion-id extraction (`_extract_criterion_ids`) | `_default_script` reads `getattr(context, "inputs", None)` and passes it through structural-then-textual extraction (`fake.py:168-197, 300`) | ✓ WIRED |
| criterion-id extraction | artifact-content synthesis | `_default_script` threads the extracted `criterion_ids` tuple into `_synthesize_artifact_content`/`_synthesize_machine_artifact` for every declared output (`fake.py:300-314`) | ✓ WIRED |
| BA `acceptance_criteria.json` | ARCHITECTURE `design.md` carrier line → DEVELOPMENT textual extraction | `_structural_criterion_ids` then `_textual_criterion_ids` matching the `- Criterion <id> met` carrier line | ✓ WIRED |
| QA's `acceptance_criteria.json` input | `verdict.json`'s `criterion_id` | `_synthesize_machine_artifact`'s `verdict.json` branch (`fake.py:252-261`) builds every `VerdictCriterionResult` from the extracted tuple | ✓ WIRED |
| `04-VALIDATION.md` proof map | `tests/integration/test_phase4_acceptance.py`'s `_VALIDATION_PROOF_FILES` | Both proof files appear in both places | ✓ WIRED |
| `orchestrator/runner.py` | `context/builder.py` | `_run_current_role` calls `build_role_context` | ✓ WIRED |
| `orchestrator/runner.py` | `artifacts/validation.py` | `collect_role_artifacts` runs after a `COMPLETED` result, can force `Signal.ROLE_FAILED` | ✓ WIRED |
| `.dark-factory/roles/QA.yaml` | `.dark-factory/roles/BA.yaml` | QA declares `acceptance_criteria.json` in `inputs`; BA declares it in `outputs`; resolved via snapshot, not adjacency | ✓ WIRED |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Status |
|------|------|---------|----------|--------|
| `src/dark_factory/workers/fake.py` | 302 | `_default_script` resolves the run root via `Path.cwd()` instead of the orchestrator's threaded `repo_root` (WR-03, `04-REVIEW.md`) | ⚠️ WARNING (non-blocking) | Open, tracked in `04-REVIEW.md`. Still present at current `HEAD` (unchanged file). Latent — every real call path currently makes `Path.cwd() == repo_root` hold. Non-blocking, does not affect phase status. |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any file this phase touched. No disabled tests, no circular-fixture patterns, no hollow props.

### Behavioral Spot-Checks

No new spot-checks required this pass — no source changed since the last pass' full run (11/11 gap-closure unit tests, 298/298 unit suite, mypy strict clean, ruff clean, `test_phase4_acceptance.py` collects 24 tests). Re-confirmed static state this pass:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| No source drift since last fully-executed pass | `git diff --stat fb8ce12..HEAD -- src/ tests/` | empty | ✓ PASS |
| Human-checkpoint closure recorded | `04-UAT.md` frontmatter/body | `status: complete`, `passed: 1`, `issues: 0` | ✓ PASS |
| Validation re-audit clean | `04-VALIDATION.md` "Validation Audit 2026-09-13" | `Gaps found: 0`, `Resolved: 0`, `Escalated: 0` | ✓ PASS |
| Security re-audit clean | `04-SECURITY.md` frontmatter + audit trail | `threats_open: 0`, `status: verified`, 23/23 closed | ✓ PASS |
| Requirements traceability | `grep .planning/REQUIREMENTS.md` | all 15 Phase 4 IDs `Complete`, none orphaned | ✓ PASS |

Note: this session, like the prior pass, has no reachable local Postgres (no Docker daemon, no local `initdb`, `.env` blocked by the secret-read guard), so the `db`/`integration` tiers could not be independently re-executed here. This is unchanged from the prior pass's disclosed limitation and is not new to this re-run; it does not affect the status determination because (a) no source changed since those tiers were last run green by the operator (`04-05-SUMMARY.md`'s user-confirmed `24 passed in 4.12s` for the acceptance gate; `04-VALIDATION.md`'s 2026-09-13 audit records `541 passed, 0 failed, 0 skipped` for the full suite), and (b) the unit-tier falsification test already provides dispositive proof of genuine id derivation.

### Decision Coverage

`gsd_run query check.decision-coverage-verify` was already confirmed clean in the prior pass (10/10 `04-CONTEXT.md` decisions honored, `not_honored: []`). No decision-affecting source changed since, so this carries forward unchanged.

## Human Verification Required

None. The one item outstanding from the prior pass — "Fresh-eyes readability of a real run's artifact tree" — is now closed via `04-UAT.md` (`status: complete`, 1/1 passed, 0 issues, result `pass`, recorded 2026-09-13).

## Gaps Summary

No must-have truth, artifact, or key link failed. No new gaps found in this pass. The single item that previously kept status at `human_needed` — the deferred fresh-eyes readability check — is now resolved via completed UAT. `04-VALIDATION.md` and `04-SECURITY.md` re-audits (triggered independently, not by this verification) both confirm zero open gaps and zero open threats, consistent with — not contradicting — this verifier's own findings.

One tracked, non-blocking code-review finding (WR-03: `Path.cwd()` vs. threaded `repo_root` in `FakeWorker`'s zero-config path) remains open in `04-REVIEW.md` as a WARNING; it does not affect phase status.

**Note (informational, non-blocking):** the ROADMAP phase goal ("BA → Architect → Developer → QA execute in sequence...") is not phrased as a `As a ___, I want ___, so that ___.` user story even though the phase's roadmap entry carries `mode: mvp`. `gsd_run query user-story.validate` against the goal text returns `valid: false`. This mismatch predates this verification pass (the prior 20/20 pass used the same goal-backward/ROADMAP-success-criteria methodology without MVP-mode formatting) and is not something this freshness re-run's narrow scope — confirming closure of an already-resolved human item — is positioned to correct. Flagged for awareness; not treated as a gap since it is a phase-definition/methodology question, not evidence the delivered pipeline fails its goal.

Overall status: **passed**. All 20 must-haves (5 ROADMAP success criteria + 15 requirement IDs) remain verified, zero open gaps, zero open blocking anti-patterns, and the human verification section is now empty.

---

_Verified: 2026-09-13T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
