---
phase: "4"
slug: "the-four-role-pipeline-artifact-handoffs"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-12"
updated: "2026-09-13"
---

# Phase 4 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time — all four plans (04-01..04-04) carry a `<threat_model>` block; this file consolidates and verifies them, it does not construct the register retroactively.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| worker → orchestrator | `WorkerResult.artifacts[].path` and the machine-artifact JSON files it names are untrusted, worker-supplied data — parsed and pydantic-validated before any orchestration decision depends on them. Phase 4 grew this from one artifact type (04-01) to seven across four roles (04-03). | Artifact paths, artifact JSON bodies |
| filesystem → orchestrator | Artifact file content, baseline docs, and example files are untrusted input read from disk under a resolved run root. | File bytes |
| operator → orchestrator | The `spec:` locator (04-02) is an operator-supplied filesystem path, read at the same trust level as an inline `text:` body. | Spec file path + bytes |
| repo config → orchestrator | `.dark-factory/roles/*.yaml` `inputs`/`outputs` filenames are repo-controlled, `yaml.safe_load`-parsed and membership-validated (Phase 3 lineage); used only as dictionary keys, never as filesystem paths outside the run root. | Role config filenames |
| QA verdict → transition | `verdict.json`'s declared `status` is worker-supplied and is checked against a fold over its own criteria/issues before the run's outcome is committed (04-03). | Verdict JSON |
| orchestrator → Neon | Every JSONB write, including `artifacts.metadata` and the expanding set of role-execution payloads, crosses the single `redact()` call site inside `apply_transition`. | Persisted JSONB |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Tampering / Info Disclosure | `artifacts/paths.py::resolve_under_run_root` | high | mitigate | `Path.is_relative_to(run_root)` guard after `.resolve()`; reject, never clamp. Proven: `tests/unit/test_artifact_paths.py`. | closed |
| T-04-02 | Denial of Service | `artifacts/store.py::read_artifact_text` | medium | mitigate | 256 KiB cap enforced before `json.loads`/`model_validate`. Proven: `tests/unit/test_artifact_paths.py`. | closed |
| T-04-03 | Spoofing / Tampering | `context/builder.py`, `artifacts/store.py` | medium | mitigate | Missing referenced artifact raises `MissingArtifactContentError` naming the path; never silently treated as absent. Proven: `tests/unit/test_context_builder.py`. | closed |
| T-04-04 | Info Disclosure | `persistence/mutations.py::_write_artifact_references` | high | mitigate | `metadata` passes through the single `redact()` call site inside `apply_transition`; confirmed present at multiple call sites in `mutations.py`. | closed |
| T-04-05 | Tampering | `context/builder.py` baseline-doc reads | low | mitigate | Fixed three-name tuple under `repo_root`, same `is_relative_to` guard + byte cap; no configurable baseline path. Proven: `tests/unit/test_context_builder.py`. | closed |
| T-04-06 | Elevation of Privilege | `context/builder.py` example reads (CTX-03) | medium | mitigate | Examples read as inert text only; build fails on any `exec`/`eval`/`compile`/`importlib.import_module`/`__import__` in `dark_factory.context`/`dark_factory.artifacts`. Proven: `tests/unit/test_no_tree_walk.py`. | closed |
| T-04-07 | Info Disclosure | `input/loaders.py::_load_spec` | low | accept | `spec:` names any path the invoking operator can already read — grants no capability beyond process ownership; confining it to the repo would break a legitimate use case. Documented in 04-02-PLAN.md. | closed |
| T-04-08 | Info Disclosure | `persistence/mutations.py::create_run` | medium | mitigate | `scrub_known_values` on `normalized_task` inside `create_run` (D-18) already scrubs known secret values before persistence; `redact()` covers `RUN_CREATED`. No new write path — `_load_spec` returns the same `NormalizedTask` type as `_load_text`. | closed |
| T-04-09 | Denial of Service | `input/loaders.py::_load_spec` | low | accept | File is operator-supplied, not attacker-supplied; 100 KB body round-trips per `tests/db/test_schema_shape.py`. A cap would be arbitrary; revisit at Phase 10 GitHub intake. Documented in 04-02-PLAN.md. | closed |
| T-04-10 | Tampering | `domain/artifacts.py::Verdict` | high | mitigate | After-validator rejects a declared `status` that disagrees with the fold over criteria/issues (`computed_status`). Proven: `tests/unit/test_artifact_models.py`. | closed |
| T-04-11 | Tampering | `domain/artifacts.py` duplicate-id validators | medium | mitigate | `Verdict` and `AcceptanceCriteriaDocument` reject repeated `criterion_id`, naming the offending id. Proven: `tests/unit/test_artifact_models.py`. | closed |
| T-04-12 | Spoofing | `domain/artifacts.py` minimum-length rules | medium | mitigate | Minimum length one on `Verdict.criteria`, `AcceptanceCriteriaDocument.criteria`, `TestReport.cases`, `ConstraintsDocument.constraints` — an empty list cannot fold to a vacuous PASS. Proven: `tests/unit/test_artifact_models.py`. | closed |
| T-04-13 | Info Disclosure | `tests/db/test_artifact_persistence.py` body-text sweep | high | mitigate | Sweep asserts absence of artifact body text across all four tables for the run, and first asserts the searched substring is genuinely present in source (non-vacuous). | closed |
| T-04-14 | Elevation of Privilege | `.dark-factory/roles/DEVELOPMENT.yaml` `tools`/`permissions.write_scope` | medium | accept | Developer role's tool grants/write scope are stored, not enforced, until Phase 6 (TOOL-03) / Phase 5 (ROLE-05). Accepted because no real worker runs yet and `FakeWorker` performs no filesystem writes outside its fixture helper. Documented in 04-03-PLAN.md. | closed |
| T-04-15 | Spoofing | `orchestrator/runner.py` artifact-validation gate | high | mitigate | A worker reporting `COMPLETED` with reassuring prose but an invalid/inconsistent `verdict.json` does not advance the run — the JSON contract decides, not the prose. Proven: `tests/db/test_artifact_schema_violation_fails_role.py`. | closed |
| T-04-16 | Tampering | `context/builder.py` attempt selection | high | mitigate | D-03 query selects only the highest-numbered `COMPLETED` attempt; content-based assertion so a coincidentally-correct row selection still fails. Proven: `tests/db/test_context_builder_retry_isolation.py`. | closed |
| T-04-17 | Repudiation | `run_events` enum stability | medium | mitigate | Ten-member `EventType` enum count + subset assertion trips on any silent addition made to satisfy an unrelated test. Proven: `tests/db/test_artifact_schema_violation_fails_role.py`. | closed |
| T-04-18 | Repudiation | `tests/integration/test_phase4_acceptance.py` | medium | mitigate | Acceptance gate is asserted free of every opt-out call, treats a missing proof as a failure naming the criterion, and is drift-guarded against `04-VALIDATION.md`. | closed |
| T-04-19 | Tampering | criterion-id extraction in `workers/fake.py` (gap closure G-04-1, plan 04-05) | medium | mitigate | Only extracted ids cross the upstream-artifact -> downstream-artifact boundary, never an input's body. Every candidate id must be a single whitespace-free token of at most 64 characters (`_MAX_CRITERION_ID_LENGTH`, `_is_safe_criterion_id`) so upstream content cannot inject newlines, Markdown structure, or JSON fragments into a downstream document. Proven: `tests/unit/test_fake_worker_synthesis.py` (bounded/defensive cases). | closed |
| T-04-20 | Information disclosure | synthesized artifact content in `workers/fake.py` (plan 04-05) | low | mitigate | The same no-body-echo rule (T-04-19) bounds credential leakage: a credential-shaped value sitting in an upstream artifact cannot be copied into a downstream artifact, since only short id tokens are ever forwarded. Artifact files stay repo-local (ART-03); the existing `redact()` path over events/results/logs is untouched. | closed |
| T-04-21 | Denial of service | synthesized artifact content size in `workers/fake.py` (plan 04-05) | low | mitigate | `_MAX_CRITERION_IDS = 20` caps how many criterion ids one synthesis call uses, applied after de-duplication, bounding every generated document regardless of how many carrier lines or criteria an input declares. Proven: `tests/unit/test_fake_worker_synthesis.py` (bounded/defensive cases). | closed |
| T-04-22 | Elevation of privilege | role-agnostic dispatch in `workers/fake.py` (plan 04-05) | low | accept | Extraction (`_extract_criterion_ids`) dispatches on input content shape only and never on `context.role` (D-08), so no role can obtain another role's synthesis behavior. Accepted with no further control: the worker performs no privileged action, and write-scope enforcement remains deferred (T-04-14 / Phase 5-6, ROLE-05). | closed |
| T-04-SC | Tampering (supply chain) | `pyproject.toml` / `uv.lock` | low | accept | No plan in this phase installs a new package or modifies `pyproject.toml`; `04-RESEARCH.md` § "Package Legitimacy Audit" records "not applicable" for the original four plans, and plan 04-05 (gap closure) likewise touches one source file, test files, and planning docs only — confirmed via `git diff --stat` showing `pyproject.toml`/`uv.lock` untouched. `uv lock --check` is asserted clean. No `[ASSUMED]`/`[SUS]` package exists, so no legitimacy checkpoint is triggered. Applies to 04-01 through 04-05. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (high) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-07 | Operator-supplied `spec:` path grants no capability beyond process ownership. | plan author (04-02-PLAN.md) | 2026-09-12 |
| AR-04-02 | T-04-09 | Spec files are operator-supplied, not attacker-supplied; a size cap would be arbitrary at this phase. | plan author (04-02-PLAN.md) | 2026-09-12 |
| AR-04-03 | T-04-14 | Tool grants/write scope enforcement is explicitly deferred to Phase 5/6; no real worker runs yet in Phase 4. | plan author (04-03-PLAN.md) | 2026-09-12 |
| AR-04-04 | T-04-SC | No package installs in any Phase 4 plan (04-01 through 04-05); legitimacy audit recorded not-applicable. | plan author (all 04-0x-PLAN.md) | 2026-09-13 |
| AR-04-05 | T-04-22 | Extraction dispatch is role-agnostic by construction (D-08); write-scope enforcement remains deferred to Phase 5/6 (ROLE-05), same as T-04-14. | plan author (04-05-PLAN.md) | 2026-09-13 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-12 | 19 (18 numbered + T-04-SC) | 19 | 0 | gsd-secure-phase orchestrator pass (register authored at plan time, ASVS L1 — grep-depth verification against existing plan/summary evidence; short-circuit rule applied, no auditor subagent spawned) |
| 2026-09-13 | 23 (22 numbered + T-04-SC) | 23 | 0 | gsd-secure-phase orchestrator pass, re-run after gap closure plan 04-05 (G-04-1). Merged 04-05's own `<threat_model>` block (T-04-19..T-04-22) into the register; grep-level verified each mitigation directly against `src/dark_factory/workers/fake.py` (`_MAX_CRITERION_ID_LENGTH`/`_is_safe_criterion_id`, `_MAX_CRITERION_IDS`, role-agnostic `_extract_criterion_ids`) and confirmed `pyproject.toml`/`uv.lock` untouched via `git diff --stat`. Register authored at plan time, ASVS L1 — short-circuit rule applied, no auditor subagent spawned. |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-12 — all 18 numbered threats plus the shared supply-chain entry are closed; 14 by proven mitigation (named test files, all present and part of the 541-test green suite reported in `04-VALIDATION.md`), 5 by documented accepted risk with rationale traceable to the originating plan.
