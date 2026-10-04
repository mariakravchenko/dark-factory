---
schema_version: 1
open_count: 18
waived_count: 0
fixed_count: 2
total_count: 20
last_updated: 2026-10-04T07:22:45.135Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | src/dark_factory/input/loaders.py | 55 | spec: loader raises SourceNotSupportedError until Phase 4 (plan-sanctioned extension point) | open |  | 2026-09-08T09:41:32.787Z |  |
| 2 | 01 | stub | src/dark_factory/input/loaders.py | 61 | github: loader raises SourceNotSupportedError until Phase 10 (plan-sanctioned extension point) | open |  | 2026-09-08T09:41:32.894Z |  |
| 3 | 02 | deviation | tests/integration/test_fresh_process_resume.py |  | SC2 crash-resume test forces lease expiry before resume (lease introduced by 02-03) | open |  | 2026-09-09T18:00:16.383Z |  |
| 4 | 02 | deviation | tests/integration/test_heartbeat_slow_step.py |  | SC5 heartbeat proof injects 6s TTL / 2s heartbeat instead of the plan's illustrative 2s / 1s: one renewal round-trip against the remote Neon endpoint is ~1.5s, so 2s/1s leaves no margin; Open Decision 2's TTL/3 ratio (the transferable part) is preserved | open |  | 2026-09-10T06:55:24.115Z |  |
| 5 | 02 | deviation | tests/integration/test_no_txn_across_worker.py |  | HITL-08 asserts no dark-factory transaction older than 3s (pg_stat_activity xact_start age) rather than a zero raw idle-in-transaction count: a sub-second heartbeat commit round-trip is transiently visible on the high-latency endpoint; the threat is a held-open transaction | open |  | 2026-09-10T06:55:24.225Z |  |
| 6 | 02 | deviation | tests/db/test_pause_mechanism_generic.py |  | Multi-node pipelines reuse the first node's role_executions row (_run_current_role inserts no RUNNING row for nodes after the first); surfaced building the two-node pause proof, out of scope for 02-06, belongs in Phase 3's config-driven pipeline | fixed |  | 2026-09-10T08:05:27.468Z | 2026-09-12T16:09:22.663Z |
| 7 | 06 | unrun-verify | tests/unit/test_no_mcp_import_in_core.py |  | Task 3's final <verify> item (full 'pytest -q' with .env sourced) was not run by the executor -- session's secret-read-guard hook blocks sourcing .env. All non-db checks (mypy --strict, ruff, uv lock --check, pytest -m unit -q: 437 passed) were run and are clean. User should run the full suite with .env sourced to confirm no db/integration regressions. | open |  | 2026-09-19T05:18:35.949Z |  |
| 8 | 06 | unrun-verify | tests/integration/test_capability_denial_no_secret_leak.py |  | SEC-01/SC4 sweep and its 5 tests: not run this session -- no Docker/initdb 17 reachable and .env sourcing blocked by the secret-read guard. Logic verified standalone (control arm, shell.execute arm, structural guard, config-tree round-trip). User should run 'set -a; . .env; set +a; uv run pytest -q tests/integration/test_capability_denial_no_secret_leak.py' and report back. | open |  | 2026-09-19T06:07:55.859Z |  |
| 9 | 06 | unrun-verify | tests/integration/test_phase6_acceptance.py |  | Phase 6 acceptance gate: presence/non-empty checks verified standalone without pytest's DB-provisioning marker; the pytest-collected run itself (17 tests) and the full-suite 'set -a; . .env; set +a; uv run pytest -q' were not run this session for the same .env-sourcing constraint. | open |  | 2026-09-19T06:07:55.977Z |  |
| 10 | 07 | stub | src/dark_factory/workers/claude_code.py | 388 | ClaudeCodeWorker.resume() raises NotImplementedError until plan 07-03 lands the native --resume <session_id> branch (execute() is fully implemented and proven this plan) | fixed |  | 2026-09-20T18:05:11.961Z | 2026-09-20T18:31:31.040Z |
| 11 | 10 | unrun-verify | tests/integration/test_unsupported_source.py |  | github:152 case updated for real _load_github but not executed against real PostgreSQL in this environment (integration tier, needs pg_url/engine fixtures) | open |  | 2026-09-26T16:30:21.545Z |  |
| 12 | 10 | deviation | src/dark_factory/input/loaders.py |  | Live smoke test of _load_github against a real GitHub issue deferred -- GITHUB_TOKEN absent from environment/.env in this session; unit tier (fakes only) fully proven and gates this plan's <verify> | open |  | 2026-09-26T16:30:21.672Z |  |
| 13 | 10 | unrun-verify | tests/integration/test_real_pipeline_zero_config.py |  | 10-07 plan verification step 5 (real quality gate + four real-CLI-subprocess tests against reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox | open |  | 2026-09-28T08:08:39.359Z |  |
| 14 | 10 | unrun-verify | tests/integration/test_artifact_scope_enforcement.py |  | 10-07 Task 3 human-check (confirm the two tamper cases and no-fake-binaries case still FAIL their run for their own condition against a reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox | open |  | 2026-09-28T08:08:44.277Z |  |
| 15 | 10 | unrun-verify | tests/db/test_loop04_adjacency.py |  | 10-08 Task 1 verify step (db-tier run of the promoted LOOP-04 adjacency test against a reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox; logic verified by static code reading and a standalone interpreter check of the assertions against real runner.py source | open |  | 2026-09-28T09:00:57.930Z |  |
| 16 | 10 | unrun-verify | tests/integration/test_redaction_interactions.py |  | 10-08 Task 2 verify step (pytest -m integration run of the narrowed redaction guard) not run -- the module's session-scoped autouse _schema_at_head fixture forces PostgreSQL provisioning for any collected integration-marked test regardless of whether the test itself requests db fixtures; no PostgreSQL reachable in the execution sandbox. Guard logic verified by a standalone interpreter run of the extraction helper against real runner.py source (both call sites resolve to str(exc), correctly allowlisted; counterexample correctly rejected) | open |  | 2026-09-28T09:00:58.039Z |  |
| 17 | 11 | unrun-verify | .planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-PLAN.md |  | Full unrestricted 'uv run pytest -q' (all tiers) stalled with ~0 forward progress after 2.5h against the real remote Neon test branch and was terminated; substituted with unit tier (incl. 5 new tests), 'unit or contract' sweep (817 passed, 1 pre-existing unrelated failure), and a standalone 'db' tier run (205 passed, 1 skipped, 0 failed) -- integration tier not re-verified this session (excluded from CI; this plan touches no integration/db/src files). | open |  | 2026-09-30T11:26:19.558Z |  |
| 18 | 12 | deviation | tests/unit/test_worker_registry_names.py |  | test_claude_code_resolves_to_a_real_adapter_not_a_placeholder expects FAILED with no ANTHROPIC_API_KEY, but this execution environment has a real credential available so the live adapter completes instead; pre-existing, unrelated to plan 12-01's observability changes | open |  | 2026-10-03T10:51:03.768Z |  |
| 19 | 12 | unrun-verify | tests/unit/test_unit_tier_needs_no_database.py |  | Plan 12-01: full unfiltered 'pytest -m unit' could not complete standalone this session -- this module's own nested 'pytest -m unit or contract' child process did not return in a practical window. A pytest -m unit run with the 18 subprocess-spawning modules excluded passed 594/595 (1 pre-existing unrelated skip/failure) in 26s; the targeted plan-level file set (26 tests) passed cleanly. | open |  | 2026-10-03T10:51:03.880Z |  |
| 20 | 12 | unrun-verify | tests/db |  | 12-04 plan-level verification bullet 'pytest -m db -q' (whole db tier) was not run exhaustively this session -- only the new module plus the 4 pre-existing modules this plan's events touch (test_qa_bounce.py, test_iteration_cap_exhaustion.py, test_artifact_created_event.py, test_artifact_schema_violation_fails_role.py) were run against real PostgreSQL (22 passed). The full db tier historically takes 20min-4h+ per STATE.md phase 11 entries. | open |  | 2026-10-04T07:22:45.135Z |  |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "01",
    "file": "src/dark_factory/input/loaders.py",
    "line": 55,
    "description": "spec: loader raises SourceNotSupportedError until Phase 4 (plan-sanctioned extension point)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-08T09:41:32.787Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "stub",
    "phase": "01",
    "file": "src/dark_factory/input/loaders.py",
    "line": 61,
    "description": "github: loader raises SourceNotSupportedError until Phase 10 (plan-sanctioned extension point)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-08T09:41:32.894Z",
    "resolved_at": null
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "02",
    "file": "tests/integration/test_fresh_process_resume.py",
    "line": null,
    "description": "SC2 crash-resume test forces lease expiry before resume (lease introduced by 02-03)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-09T18:00:16.383Z",
    "resolved_at": null
  },
  {
    "id": 4,
    "kind": "deviation",
    "phase": "02",
    "file": "tests/integration/test_heartbeat_slow_step.py",
    "line": null,
    "description": "SC5 heartbeat proof injects 6s TTL / 2s heartbeat instead of the plan's illustrative 2s / 1s: one renewal round-trip against the remote Neon endpoint is ~1.5s, so 2s/1s leaves no margin; Open Decision 2's TTL/3 ratio (the transferable part) is preserved",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-10T06:55:24.115Z",
    "resolved_at": null
  },
  {
    "id": 5,
    "kind": "deviation",
    "phase": "02",
    "file": "tests/integration/test_no_txn_across_worker.py",
    "line": null,
    "description": "HITL-08 asserts no dark-factory transaction older than 3s (pg_stat_activity xact_start age) rather than a zero raw idle-in-transaction count: a sub-second heartbeat commit round-trip is transiently visible on the high-latency endpoint; the threat is a held-open transaction",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-10T06:55:24.225Z",
    "resolved_at": null
  },
  {
    "id": 6,
    "kind": "deviation",
    "phase": "02",
    "file": "tests/db/test_pause_mechanism_generic.py",
    "line": null,
    "description": "Multi-node pipelines reuse the first node's role_executions row (_run_current_role inserts no RUNNING row for nodes after the first); surfaced building the two-node pause proof, out of scope for 02-06, belongs in Phase 3's config-driven pipeline",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-10T08:05:27.468Z",
    "resolved_at": "2026-09-12T16:09:22.663Z"
  },
  {
    "id": 7,
    "kind": "unrun-verify",
    "phase": "06",
    "file": "tests/unit/test_no_mcp_import_in_core.py",
    "line": null,
    "description": "Task 3's final <verify> item (full 'pytest -q' with .env sourced) was not run by the executor -- session's secret-read-guard hook blocks sourcing .env. All non-db checks (mypy --strict, ruff, uv lock --check, pytest -m unit -q: 437 passed) were run and are clean. User should run the full suite with .env sourced to confirm no db/integration regressions.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-19T05:18:35.949Z",
    "resolved_at": null
  },
  {
    "id": 8,
    "kind": "unrun-verify",
    "phase": "06",
    "file": "tests/integration/test_capability_denial_no_secret_leak.py",
    "line": null,
    "description": "SEC-01/SC4 sweep and its 5 tests: not run this session -- no Docker/initdb 17 reachable and .env sourcing blocked by the secret-read guard. Logic verified standalone (control arm, shell.execute arm, structural guard, config-tree round-trip). User should run 'set -a; . .env; set +a; uv run pytest -q tests/integration/test_capability_denial_no_secret_leak.py' and report back.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-19T06:07:55.859Z",
    "resolved_at": null
  },
  {
    "id": 9,
    "kind": "unrun-verify",
    "phase": "06",
    "file": "tests/integration/test_phase6_acceptance.py",
    "line": null,
    "description": "Phase 6 acceptance gate: presence/non-empty checks verified standalone without pytest's DB-provisioning marker; the pytest-collected run itself (17 tests) and the full-suite 'set -a; . .env; set +a; uv run pytest -q' were not run this session for the same .env-sourcing constraint.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-19T06:07:55.977Z",
    "resolved_at": null
  },
  {
    "id": 10,
    "kind": "stub",
    "phase": "07",
    "file": "src/dark_factory/workers/claude_code.py",
    "line": 388,
    "description": "ClaudeCodeWorker.resume() raises NotImplementedError until plan 07-03 lands the native --resume <session_id> branch (execute() is fully implemented and proven this plan)",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-20T18:05:11.961Z",
    "resolved_at": "2026-09-20T18:31:31.040Z"
  },
  {
    "id": 11,
    "kind": "unrun-verify",
    "phase": "10",
    "file": "tests/integration/test_unsupported_source.py",
    "line": null,
    "description": "github:152 case updated for real _load_github but not executed against real PostgreSQL in this environment (integration tier, needs pg_url/engine fixtures)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T16:30:21.545Z",
    "resolved_at": null
  },
  {
    "id": 12,
    "kind": "deviation",
    "phase": "10",
    "file": "src/dark_factory/input/loaders.py",
    "line": null,
    "description": "Live smoke test of _load_github against a real GitHub issue deferred -- GITHUB_TOKEN absent from environment/.env in this session; unit tier (fakes only) fully proven and gates this plan's <verify>",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T16:30:21.672Z",
    "resolved_at": null
  },
  {
    "id": 13,
    "kind": "unrun-verify",
    "phase": "10",
    "file": "tests/integration/test_real_pipeline_zero_config.py",
    "line": null,
    "description": "10-07 plan verification step 5 (real quality gate + four real-CLI-subprocess tests against reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-28T08:08:39.359Z",
    "resolved_at": null
  },
  {
    "id": 14,
    "kind": "unrun-verify",
    "phase": "10",
    "file": "tests/integration/test_artifact_scope_enforcement.py",
    "line": null,
    "description": "10-07 Task 3 human-check (confirm the two tamper cases and no-fake-binaries case still FAIL their run for their own condition against a reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-28T08:08:44.277Z",
    "resolved_at": null
  },
  {
    "id": 15,
    "kind": "unrun-verify",
    "phase": "10",
    "file": "tests/db/test_loop04_adjacency.py",
    "line": null,
    "description": "10-08 Task 1 verify step (db-tier run of the promoted LOOP-04 adjacency test against a reachable PostgreSQL) not run -- no PostgreSQL reachable in the execution sandbox; logic verified by static code reading and a standalone interpreter check of the assertions against real runner.py source",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-28T09:00:57.930Z",
    "resolved_at": null
  },
  {
    "id": 16,
    "kind": "unrun-verify",
    "phase": "10",
    "file": "tests/integration/test_redaction_interactions.py",
    "line": null,
    "description": "10-08 Task 2 verify step (pytest -m integration run of the narrowed redaction guard) not run -- the module's session-scoped autouse _schema_at_head fixture forces PostgreSQL provisioning for any collected integration-marked test regardless of whether the test itself requests db fixtures; no PostgreSQL reachable in the execution sandbox. Guard logic verified by a standalone interpreter run of the extraction helper against real runner.py source (both call sites resolve to str(exc), correctly allowlisted; counterexample correctly rejected)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-28T09:00:58.039Z",
    "resolved_at": null
  },
  {
    "id": 17,
    "kind": "unrun-verify",
    "phase": "11",
    "file": ".planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-05-PLAN.md",
    "line": null,
    "description": "Full unrestricted 'uv run pytest -q' (all tiers) stalled with ~0 forward progress after 2.5h against the real remote Neon test branch and was terminated; substituted with unit tier (incl. 5 new tests), 'unit or contract' sweep (817 passed, 1 pre-existing unrelated failure), and a standalone 'db' tier run (205 passed, 1 skipped, 0 failed) -- integration tier not re-verified this session (excluded from CI; this plan touches no integration/db/src files).",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-30T11:26:19.558Z",
    "resolved_at": null
  },
  {
    "id": 18,
    "kind": "deviation",
    "phase": "12",
    "file": "tests/unit/test_worker_registry_names.py",
    "line": null,
    "description": "test_claude_code_resolves_to_a_real_adapter_not_a_placeholder expects FAILED with no ANTHROPIC_API_KEY, but this execution environment has a real credential available so the live adapter completes instead; pre-existing, unrelated to plan 12-01's observability changes",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-10-03T10:51:03.768Z",
    "resolved_at": null
  },
  {
    "id": 19,
    "kind": "unrun-verify",
    "phase": "12",
    "file": "tests/unit/test_unit_tier_needs_no_database.py",
    "line": null,
    "description": "Plan 12-01: full unfiltered 'pytest -m unit' could not complete standalone this session -- this module's own nested 'pytest -m unit or contract' child process did not return in a practical window. A pytest -m unit run with the 18 subprocess-spawning modules excluded passed 594/595 (1 pre-existing unrelated skip/failure) in 26s; the targeted plan-level file set (26 tests) passed cleanly.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-10-03T10:51:03.880Z",
    "resolved_at": null
  },
  {
    "id": 20,
    "kind": "unrun-verify",
    "phase": "12",
    "file": "tests/db",
    "line": null,
    "description": "12-04 plan-level verification bullet 'pytest -m db -q' (whole db tier) was not run exhaustively this session -- only the new module plus the 4 pre-existing modules this plan's events touch (test_qa_bounce.py, test_iteration_cap_exhaustion.py, test_artifact_created_event.py, test_artifact_schema_violation_fails_role.py) were run against real PostgreSQL (22 passed). The full db tier historically takes 20min-4h+ per STATE.md phase 11 entries.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-10-04T07:22:45.135Z",
    "resolved_at": null
  }
]
````
