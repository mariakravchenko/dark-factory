---
schema_version: 1
open_count: 3
waived_count: 0
fixed_count: 0
total_count: 3
last_updated: 2026-09-09T18:00:16.383Z
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
  }
]
````
