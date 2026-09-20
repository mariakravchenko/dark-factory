---
schema_version: 1
open_count: 9
waived_count: 0
fixed_count: 1
total_count: 10
last_updated: 2026-09-20T18:05:11.961Z
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
| 10 | 07 | stub | src/dark_factory/workers/claude_code.py | 388 | ClaudeCodeWorker.resume() raises NotImplementedError until plan 07-03 lands the native --resume <session_id> branch (execute() is fully implemented and proven this plan) | open |  | 2026-09-20T18:05:11.961Z |  |

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
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-20T18:05:11.961Z",
    "resolved_at": null
  }
]
````
