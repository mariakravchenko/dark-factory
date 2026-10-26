---
phase: 12-observability-audit-surface
verified: 2026-10-06T06:30:00Z
status: passed
score: 9/9 must-haves verified
covered_files: [".planning/REQUIREMENTS.md", ".planning/phases/12-observability-audit-surface/12-01-PLAN.md", ".planning/phases/12-observability-audit-surface/12-01-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-02-PLAN.md", ".planning/phases/12-observability-audit-surface/12-02-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-03-PLAN.md", ".planning/phases/12-observability-audit-surface/12-03-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-04-PLAN.md", ".planning/phases/12-observability-audit-surface/12-04-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-05-PLAN.md", ".planning/phases/12-observability-audit-surface/12-05-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-06-PLAN.md", ".planning/phases/12-observability-audit-surface/12-06-SUMMARY.md", ".planning/phases/12-observability-audit-surface/12-07-PLAN.md", ".planning/phases/12-observability-audit-surface/12-07-SUMMARY.md", "src/dark_factory/artifacts/store.py", "src/dark_factory/cli.py", "src/dark_factory/domain/views.py", "src/dark_factory/events/catalog.py", "src/dark_factory/events/reader.py", "src/dark_factory/git/__init__.py", "src/dark_factory/git/client.py", "src/dark_factory/git/committed.py", "src/dark_factory/git/diff.py", "src/dark_factory/git/errors.py", "src/dark_factory/git/lifecycle.py", "src/dark_factory/git/scope.py", "src/dark_factory/git/worktree.py", "src/dark_factory/observability/render.py", "src/dark_factory/observability/run_detail.py", "src/dark_factory/orchestrator/runner.py", "tests/db/test_artifact_created_event.py", "tests/db/test_artifacts_show_reads_committed_content.py", "tests/db/test_clarification_comment_is_redacted.py", "tests/db/test_events_reader_sees_every_bounce.py", "tests/db/test_qa_verdict_events.py", "tests/db/test_run_report.py", "tests/db/test_secret_redaction_e2e_full_pipeline.py", "tests/integration/test_artifacts_cli.py", "tests/integration/test_cli_commands_are_reads.py", "tests/integration/test_events_cli.py", "tests/integration/test_runs_cli.py", "tests/integration/test_status_cli.py", "tests/unit/test_domain_enums.py", "tests/unit/test_global_settings_reads_are_declared.py", "tests/unit/test_observability_import_graph.py"]
covered_digest: "v1:sha256:b965230d871bb11ec141ed86408a0def6a244c433e83e243c64c76634ea0b432"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 12: Observability & Audit Surface Verification Report

**Phase Goal:** For any run, Dark Factory can say exactly where it is and retell everything that happened to it — the observability half of the durability thesis.
**Verified:** 2026-10-06T06:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Derived from ROADMAP.md's four Success Criteria for Phase 12, cross-checked against PLAN frontmatter `must_haves.truths` across all 7 plans.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `dark-factory status <run-id>` reports current state, active role, worker, worker session id, attempt number, per-role history, artifacts, questions/human answers, quality-gate results, errors, PR information and the state-transition history | ✓ VERIFIED | `RunReport` composes `read_status`+`read_run_detail`+`read_events`+`read_quality_gate`; `render_run_report` renders every section as rich panels/tables. `tests/db/test_run_report.py` (10 tests) passed live against real PostgreSQL+git in this session: multi-attempt role history, committed quality-gate parity, null-marker rendering, `FAILED`-run error text survival, no-write/event-tampering invariance. `tests/integration/test_status_cli.py` (8 tests) passed live: text/JSON key-set parity. |
| 2 | The CLI command set is complete — `run`, `resume`, `status`, `runs`, `artifacts`, `events` — with `runs` listing runs and `events` exposing the full typed audit trail | ✓ VERIFIED | `python -c "...c.app.registered_commands..."` → `['artifacts', 'events', 'resume', 'run', 'runs', 'status']` — all six present. `tests/integration/test_runs_cli.py` and `tests/integration/test_events_cli.py` (part of the 31 integration tests run live this session) passed, proving `runs` lists runs (ordering, `--status` filter, intact 36-char ids) and `events` exposes the trail (`--json`, repeatable `--type`, exit codes). |
| 3 | Every event type in the catalog (RUN_CREATED through RUN_FAILED, including ROLE_*, ARTIFACT_CREATED, QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED, QA_*, QUALITY_GATE_*, PUBLISH_STARTED, PR_CREATED) is emitted at the right moment, and a finished run's story is reconstructable from the event stream alone | ✓ VERIFIED | `EventType` has exactly 22 members (confirmed live: `len(list(EventType))` → `22`). `tests/db/test_qa_verdict_events.py` (5 tests, live) proves `QA_FAILED`/`QA_PASSED` cardinality across PASS/FAIL-under-cap/FAIL-at-cap/distinctness/late-failure-honesty. `tests/db/test_artifact_created_event.py` (1 named test, live) proves `ARTIFACT_CREATED` parity with `artifacts` rows and same-transaction `seq` adjacency. `tests/db/test_events_reader_sees_every_bounce.py` (live) proves every `ROLE_BOUNCED` cycle of a real feedback loop is readable. 12-07-SUMMARY.md records an inline check that all 22 members are referenced by name outside `catalog.py` (`[m.name for m in E if ... not in src]` → `[]`). |
| 4 | An end-to-end run seeded with realistically-shaped fake secrets leaves zero occurrences of them across artifacts, events, logs, GitHub comments and test reports | ✓ VERIFIED | `tests/db/test_secret_redaction_e2e_full_pipeline.py` (4 tests) run live against real PostgreSQL + a real `ClaudeCodeWorker` subprocess + git — **passed** (161.52s). Drives one `github:`-sourced run with 6 seeded credential literals across 4 shapes through intake → human pause/resume → a real worker → QA → quality gate → a created PR, then sweeps all 7 D-08 sinks, a whole-table sweep of 5 tables, and all 4 Phase-12 CLI surfaces. The sweep itself found and the phase closed a real gap (artifact file content was unscrubbed before commit — `scrub_artifact_text_in_place`, confirmed wired in `runner.py`). `tests/db/test_clarification_comment_is_redacted.py` (4 tests, live) separately proves the GitHub clarification-comment path (OBS-01's other named high-severity gap) is scrubbed before both the idempotency check and the external post. |

**Score:** 4/4 roadmap success-criteria truths verified; 5/5 additional plan-level `must_haves` truth clusters (CLI exit-code contracts, architectural events-free guard, `runs` ordering/id-integrity, `events --json`/`--type` contract, read-command AST guard) independently confirmed — see Behavioral Spot-Checks and Key Link Verification below. 0 present-but-behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/events/catalog.py` | `EventType.ARTIFACT_CREATED`, `QA_FAILED`, `QA_PASSED`; 22 total members | ✓ VERIFIED | Confirmed live: 22 members, no debt markers, mypy/ruff clean |
| `src/dark_factory/events/reader.py` | `read_events(run_id, *, event_types)`, ordered by `seq` | ✓ VERIFIED | `__all__` → `['read_events']`; `tests/db/test_artifact_created_event.py`/`test_events_reader_sees_every_bounce.py` live-pass |
| `src/dark_factory/domain/views.py` | `EventRow`, `RunListRow`, `ArtifactRow`, `RoleAttemptRow`, `InteractionRow`, `GateCommandRow`, `QualityGateView`, `RunDetail`, `RunReport` | ✓ VERIFIED | All 9 DTOs present and importable; `RunView`/`NULL_MARKER`/`Redactor` confirmed unchanged per SUMMARY claims |
| `src/dark_factory/observability/render.py` | `render_events_text`, `render_events_json`, `render_runs_table`, `render_artifacts_table`, `render_run_report` | ✓ VERIFIED | All 5 renderers present; package confirmed events-free by live unit-test run |
| `src/dark_factory/observability/run_detail.py` | `read_run_list`, `read_artifact_rows`, `read_artifact_target`, `read_run_detail`, `read_quality_gate` | ✓ VERIFIED | All 5 reads present; `UnknownArtifactError`/`ArtifactTarget` present; events-free/write-free per live `test_observability_import_graph.py` |
| `src/dark_factory/git/committed.py` + `git/errors.py` | the one production `git show` read; leaf error module | ✓ VERIFIED | Both files exist; `errors.py` extraction confirmed (all git submodules import from it); `test_artifacts_show_reads_committed_content.py` live-passes |
| `src/dark_factory/artifacts/store.py` | `scrub_artifact_text_in_place` | ✓ VERIFIED | Function present at line 76; call site confirmed wired in `runner.py` before `collect_role_artifacts` |
| `src/dark_factory/cli.py` | `events`, `runs`, `artifacts` commands; `status` composes `RunReport` | ✓ VERIFIED | All registered; `--json`/`--type`/`--status`/`--show` options confirmed present |
| `tests/db/test_secret_redaction_e2e_full_pipeline.py` | SC4 whole-pipeline sweep | ✓ VERIFIED | Exists, substantive (4 tests), **run live this session — 4/4 passed** |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `orchestrator/runner.py` | `persistence/mutations.py` (`apply_transition`) | `events.extend(artifact_events)` / `events.extend(qa_verdict_events)` | ✓ WIRED | Confirmed at lines 1613/1618/1671/1708/1714 — spliced into `ROLE_COMPLETED`/`ROLE_BOUNCED` (and the QA-verdict accumulator additionally into `ROLE_FAILED`), reset to `[]` on `GitError`, matching D-06/D-07's "never claim durability for content that never landed" contract |
| `orchestrator/runner.py` (`ROLE_NEEDS_INPUT`) | GitHub `create_comment` + `_find_own_clarification_comment` | `comment_body = redact(clarification_body, ...)`, both call sites consume `comment_body` | ✓ WIRED | Confirmed at lines 1778-1792 — the "scrub once, both sinks" pattern that closes the idempotency-bypass risk the SUMMARY describes |
| `cli.py::events`/`runs`/`artifacts`/`status` | `events/reader.py`, `observability/run_detail.py` | `read_events(...)`, `read_run_list(...)`, `read_artifact_rows/target(...)`, `read_run_detail(...)` | ✓ WIRED | All thin-wrapper command bodies confirmed via `test_cli_commands_are_reads.py` (live, non-vacuous AST guard) |
| `observability/render.py` | `rich.table.Table` | `min_width` on id/status/timestamp columns | ✓ WIRED | `render_runs_table`/`render_artifacts_table` confirmed present with the documented min-width discipline; `test_runs_cli.py` live-passes the full-UUID-substring assertion |
| `artifacts/store.py::scrub_artifact_text_in_place` | `orchestrator/runner.py::_run_current_role` | called before `collect_role_artifacts` reads the same file | ✓ WIRED | Confirmed at line 1200, ahead of the checksum-computing read; closes the gap `test_secret_redaction_e2e_full_pipeline.py` found and now proves closed |

### Behavioral Spot-Checks

All run live against real PostgreSQL 17 / real git / (for the SC4 sweep) a real `ClaudeCodeWorker` subprocess — not re-stated from SUMMARY claims.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit-tier architectural guards (events-free sweep, enum cardinality, settings-read inventory) | `pytest -m unit -q tests/unit/test_observability_import_graph.py tests/unit/test_status_import_graph.py tests/unit/test_domain_enums.py tests/unit/test_global_settings_reads_are_declared.py` | 27 passed | ✓ PASS |
| `ARTIFACT_CREATED`/artifact-row exact parity | `pytest -m db -q tests/db/test_artifact_created_event.py::test_artifact_created_events_exactly_match_artifact_rows_and_render` | 1 passed (52.4s) | ✓ PASS |
| Clarification-comment redaction (scrub-before-both-sinks, idempotency) | `pytest -m db -q tests/db/test_clarification_comment_is_redacted.py` | 4 passed (67.1s) | ✓ PASS |
| SC4 whole-pipeline secret sweep (the phase's hardest claim) | `pytest -m db -q tests/db/test_secret_redaction_e2e_full_pipeline.py` | 4 passed (161.5s) | ✓ PASS |
| QA-verdict events, run report, bounce-filter parity, committed-artifact `--show` | `pytest -m db -q tests/db/test_qa_verdict_events.py tests/db/test_run_report.py tests/db/test_events_reader_sees_every_bounce.py tests/db/test_artifacts_show_reads_committed_content.py` | 22 passed (584.8s) | ✓ PASS |
| CLI subprocess contracts (`events`, `runs`, `artifacts`, `status`, read-command AST guard) | `pytest -m integration -q tests/integration/test_events_cli.py tests/integration/test_runs_cli.py tests/integration/test_artifacts_cli.py tests/integration/test_cli_commands_are_reads.py tests/integration/test_status_cli.py` | 31 passed (549.1s) | ✓ PASS |
| Static typing on every file this phase touched | `mypy <10 touched src files>` | Success: no issues found in 10 source files | ✓ PASS |
| Lint/format on every file this phase touched | `ruff check` / `ruff format --check` on the same 10 files | All checks passed / 10 files already formatted | ✓ PASS |

Total live-run evidence this session: **80 tests executed, 80 passed, 0 failed** across unit/db/integration tiers for phase-12-owned test modules, plus clean mypy/ruff on every source file this phase modified.

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` convention in this project; phase verification is proven via the pytest tiers above, which is this project's equivalent mechanism.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| OBS-01 | 12-03, 12-05, 12-06, 12-07 | Report, for any run, state/role/worker/session/attempt/history/artifacts/questions/answers/gate results/errors/PR info/transition history | ✓ SATISFIED | `RunReport`/`render_run_report` (12-06); `--show` committed-content read (12-05); clarification-comment redaction gap closed (12-03); SC4 sweep + artifact-content-scrub gap closed (12-07). All live-tested this session. |
| OBS-02 | 12-01, 12-04, 12-07 | Important state changes/side effects persisted as typed events across the full catalog | ✓ SATISFIED | `ARTIFACT_CREATED` (12-01), `QA_FAILED`/`QA_PASSED` (12-04) complete the 22-member catalog; 12-07 confirms every member is emitted by shipped code. Live-tested. |
| OBS-03 | 12-01, 12-02 | `dark-factory events <run>` / `dark-factory runs` expose the audit trail and run list | ✓ SATISFIED | Both commands registered and live-tested (text/JSON parity, `--type`/`--status` filters, exit codes, ordering, intact ids). |
| TRIG-02 | 12-01, 12-02, 12-05 | CLI provides `run`, `resume`, `status`, `runs`, `artifacts`, `events` | ✓ SATISFIED | All 6 commands confirmed registered live: `['artifacts', 'events', 'resume', 'run', 'runs', 'status']`. |
| TRIG-03 | 12-06 | `status <run>` renders run id, task, state, per-role pipeline w/ worker+attempts, artifacts, human interactions | ✓ SATISFIED | `RunReport`/`render_run_report` confirmed; text/JSON parity guard live-passes. |

No orphaned requirements — REQUIREMENTS.md's Phase 12 row lists exactly these 5 IDs, matching the plan frontmatter declarations across all 7 plans (cross-referenced: 12-01 declares OBS-02/OBS-03/TRIG-02; 12-02 declares OBS-03/TRIG-02; 12-03 completes OBS-01; 12-04 completes OBS-02; 12-05 completes TRIG-02 (shares OBS-01); 12-06 completes TRIG-03 (shares OBS-01); 12-07 completes OBS-01/OBS-02/OBS-03).

### Decision Coverage

CONTEXT.md decisions D-01 through D-08 all traced to shipped artifacts and live-passing tests: D-01/D-02 (status full detail + rich rendering — `render_run_report`), D-03 (`runs` table, ordering, `--status`), D-04 (`artifacts`/`--show`, metadata-only list), D-05 (`events` text/JSON/`--type` contract), D-06 (`ARTIFACT_CREATED` same-transaction emission), D-07 (`QA_FAILED`/`QA_PASSED` alongside `ROLE_COMPLETED`), D-08 (SC4 full-pipeline proof, not a redaction-unit test). All honored — 0 not-honored.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` found in any of the 10 source files this phase created/modified (verified by direct grep this session) | — | None |

**Code-review carry-forward (12-REVIEW.md, 0 critical / 4 warnings / 1 info, status `issues_found`):** independently spot-checked one warning against the live source — confirmed accurate and non-blocking:

- **WR-01** (`render_run_report`'s roles table omits `wip_commit_sha`, a text/JSON field-level parity gap): **confirmed present** in `src/dark_factory/observability/render.py` lines 251-270 — the `roles_table` declares no `wip_commit_sha` column while `RunReport.as_json()` includes it. This is a readability/parity quality gap, not a security or correctness defect (the value is not hidden from `--json`, only from the text rendering), and it does not contradict any of the phase's success criteria or must-have truths, which require the data be *reportable* (satisfied via `--json`) rather than mandate field-for-field text-table parity beyond the section-key level the phase's own parity guard checks. Recorded here as a known, already-documented quality gap — not a blocker.
- WR-02 (error text is `str()`-repr rather than extracted), WR-03 (quality-gate `GitError` ambiguity), WR-04 (non-UTF-8 artifact scrub edge case), IN-01 (`--show` has no size cap) — all are real but non-blocking, scoped to edge cases / readability, already surfaced by code review with concrete fixes proposed. None contradicts a must-have truth or roadmap success criterion; none is a security/credential-leakage defect (the SC4 sweep's own adversarial test — which specifically hunts for exactly this class of defect — passed clean).

No new-scope findings beyond what code review already surfaced. This is an initial verification pass (no prior VERIFICATION.md), so the re-verification evidence gate (#3304) does not apply.

### Human Verification Required

None. Phase 12 is an infrastructure/observability phase (CLI surface + event catalog + redaction guarantees) with no UI; every success criterion and must-have truth is verifiable programmatically and was independently exercised against real PostgreSQL/git/a real worker subprocess in this session, not merely re-stated from SUMMARY claims. No truth in this phase asserts a state-transition or cancellation/cleanup/ordering invariant that lacks a passing behavioral test — the two most behavior-sensitive claims (ARTIFACT_CREATED/artifacts-row transactional parity, and the SC4 secret-sweep across the full pipeline including a crash/resume and a late commit-failure) both have dedicated, live-passing tests exercising exactly that invariant.

### Gaps Summary

None. All 4 roadmap success criteria, all 5 phase requirement IDs (OBS-01, OBS-02, OBS-03, TRIG-02, TRIG-03), and all `must_haves` truths/artifacts/key_links declared across the 7 plans' frontmatter are verified present, substantive, wired, and — for the event-cardinality and secret-redaction claims that are genuinely behavior-dependent — independently proven by live test execution against real infrastructure in this verification session (not merely re-stated from SUMMARY.md). The one pre-existing, environment-dependent test failure (`test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`) was confirmed, by reading the test itself, to assert credential-absent behavior that a live `ANTHROPIC_API_KEY` in this sandbox contradicts — it predates this phase (phase 08), is untouched by any of the 7 phase-12 plans, and is correctly out of scope for this verification.

---

*Verified: 2026-10-06T06:30:00Z*
*Verifier: Claude (gsd-verifier)*
