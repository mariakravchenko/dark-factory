---
phase: 06-tools-permissions-the-credential-boundary
verified: 2026-09-20T13:00:00Z
status: passed
score: 5/5 truths verified
covered_files: [".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/debug/resolved/phase4-artifact-commit-bugs.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-01-PLAN.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-01-SUMMARY.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-02-PLAN.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-02-SUMMARY.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-03-PLAN.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-03-SUMMARY.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-04-PLAN.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-04-SUMMARY.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-UAT.md", ".planning/phases/06-tools-permissions-the-credential-boundary/06-VALIDATION.md", ".planning/phases/06-tools-permissions-the-credential-boundary/COVERAGE.md", "pyproject.toml", "src/dark_factory/actions/builtins.py", "src/dark_factory/artifacts/validation.py", "src/dark_factory/config/loader.py", "src/dark_factory/events/catalog.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/tools/__init__.py", "src/dark_factory/tools/env.py", "src/dark_factory/tools/mcp_transport.py", "src/dark_factory/tools/native.py", "src/dark_factory/tools/registry.py", "tests/conftest.py", "tests/db/test_artifact_commit_per_role.py", "tests/db/test_capability_denied_fails_role.py", "tests/integration/test_capability_denial_no_secret_leak.py", "tests/integration/test_phase6_acceptance.py", "tests/integration/test_pr_diff_excludes_artifacts.py", "tests/integration/test_worker_env_boundary.py", "tests/support/env_dump.py", "tests/unit/test_mcp_adapter.py", "tests/unit/test_native_tool_contract.py", "tests/unit/test_no_mcp_import_in_core.py", "tests/unit/test_no_worker_name_leak.py", "tests/unit/test_shell_execute.py", "tests/unit/test_tool_registry.py", "tests/unit/test_tool_registry_extensibility.py", "tests/unit/test_worker_env.py", "uv.lock"]
covered_digest: "v1:sha256:6d24e0fbcdbf0125c96877efd6c2da59f37998b69a36f7e691b84a4aa0c6f33a"
behavior_unverified: 0
overrides_applied: 0
coincidental_reliance_items: []
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  gaps_closed:
    - "SC1 db-tier tracer proof (tests/db/test_capability_denied_fails_role.py) — now executed against real PostgreSQL 17 and passing, per 06-UAT.md item 1 and the user's full-suite run."
    - "SC2 cross-process env-dump proof (tests/integration/test_worker_env_boundary.py) — now executed against real PostgreSQL 17 and passing, per 06-UAT.md item 2 and the user's full-suite run."
    - "SC4 db-tier sweep arms (tests/integration/test_capability_denial_no_secret_leak.py, all 6 tests) — now executed against real PostgreSQL 17 and passing, per 06-UAT.md item 3 and the user's full-suite run."
    - "Full db+integration+unit suite regression — user ran the complete suite (`set -a; source ./.env; set +a; uv run pytest -q`) against real PostgreSQL 17: 763 passed, 0 failed, matching this session's own `pytest --collect-only` count of 763 exactly."
    - "The 3 previously-documented pre-existing phase-4/5 failures (tests/db/test_artifact_commit_per_role.py x2, tests/integration/test_pr_diff_excludes_artifacts.py x1) are now also fixed — root-caused as stale write_scope test fixtures (predating phase 5's D-14 enforcement) in a separate debug session (.planning/debug/resolved/phase4-artifact-commit-bugs.md, commit ffc333f), zero production code changed, confirmed by the user's full-suite run."
  gaps_remaining: []
  regressions: []
---

# Phase 6: Tools, Permissions & the Credential Boundary Verification Report

**Phase Goal:** A role receives exactly the capabilities its configuration grants and nothing more, and a worker subprocess can never reach an infrastructure credential.
**Verified:** 2026-09-20
**Status:** passed
**Re-verification:** Yes — after gap closure (all 4 prior human-verification items now confirmed passing with live execution evidence)

## What Changed Since the Prior (Stale) VERIFICATION.md

1. All 4 previously-open human-verification items (db-tier and integration-tier tests requiring real PostgreSQL 17) were run by the user directly against real PostgreSQL 17 and confirmed passing — `.planning/phases/06-tools-permissions-the-credential-boundary/06-UAT.md`, all 4 items `result: pass`, dated 2026-09-20.
2. A separate, unrelated debug session found and fixed 3 long-standing pre-existing test failures (`tests/db/test_artifact_commit_per_role.py` x2, `tests/integration/test_pr_diff_excludes_artifacts.py` x1) — a stale-fixture defect (`write_scope: []` fixtures that predated phase 5's D-14 zero-tolerance enforcement), zero production code changed. Root cause, evidence, and elimination of alternative hypotheses are documented in `.planning/debug/resolved/phase4-artifact-commit-bugs.md`; the fix is commit `ffc333f`, which touches only `tests/db/test_artifact_commit_per_role.py` and `tests/integration/test_pr_diff_excludes_artifacts.py` (`git show --stat ffc333f` confirms zero `src/` files touched).
3. The user ran the FULL test suite against real PostgreSQL 17: `set -a; source ./.env; set +a; uv run pytest -q` → `763 passed in 4390.33s (1:13:10)`, 0 failed. This session's own `uv run pytest --collect-only -q` independently confirms the repository currently collects exactly 763 tests — the user's reported count is not just plausible, it matches the current tree exactly.
4. `COVERAGE.md`'s api-coverage gate (reasons must be ≤200 chars) was fixed — verified in this session: no reason row in `COVERAGE.md` exceeds 200 characters.

## Goal Achievement

### Observable Truths (ROADMAP Phase 6 Success Criteria, verbatim)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | A role invoking a capability it was not granted is denied by the registry (deny-by-default) and the denial is persisted as an event; BA and Architect cannot write source, Developer can write and shell, QA can write tests and shell but cannot publish. | ✓ VERIFIED | Unit-tier grant/deny matrix re-confirmed this session (`uv run pytest -m unit -q` → 442 passed). Deny-before-lookup ordering and `.dark-factory/roles/*.yaml` grants unchanged since prior verification (`git log` shows no commits touching `src/dark_factory/tools/`, `orchestrator/runner.py`, or the role YAMLs since `5c87e6b`, and `git status --porcelain -- src/` is clean). The db-tier persistence proof (`tests/db/test_capability_denied_fails_role.py`) — previously code-reviewed only — is now confirmed EXECUTED and PASSING against real PostgreSQL 17, per `06-UAT.md` item 1 (`result: pass`) and the user's full-suite run (763 passed, 0 failed, which includes this file). |
| SC2 | Dumping a worker subprocess environment shows no `DATABASE_URL`, no `GITHUB_TOKEN`, and no unrelated key inherited from the Dark Factory process — only the allowlisted minimum plus that worker's own credential. | ✓ VERIFIED | `src/dark_factory/tools/env.py::build_worker_env` unchanged and re-confirmed at the unit tier (`tests/unit/test_worker_env.py`, `tests/unit/test_shell_execute.py`'s real-subprocess-spawn tests, both in the 442-passed unit run). The dedicated cross-process integration proof (`tests/integration/test_worker_env_boundary.py`) — previously blocked by an unrelated autouse Postgres fixture — is now confirmed EXECUTED and PASSING, per `06-UAT.md` item 2 (`result: pass`) and the full-suite run. |
| SC3 | A new capability is added to the `ToolRegistry` and granted to one role without editing any role executor. | ✓ VERIFIED | `tests/unit/test_tool_registry_extensibility.py` re-confirmed passing this session (part of the 442-test unit run, unchanged since prior verification). Extension seam (`default_registry.register`) unchanged. |
| SC4 | Grepping every role artifact, worker prompt, event payload, log and report for the known secret values returns zero occurrences. | ✓ VERIFIED | The 3 DB-free arms were already independently confirmed in the prior verification pass. All 6 tests in `tests/integration/test_capability_denial_no_secret_leak.py`, including the 3 that drive a real run through Postgres and assert persisted rows/log sink, are now confirmed EXECUTED and PASSING, per `06-UAT.md` item 3 (`result: pass`) and the full-suite run. |
| SC5 | Tools are exposed to a compatible worker over the optional MCP transport, and removing MCP entirely leaves the orchestrator fully functional — core code imports nothing from MCP. | ✓ VERIFIED | `pyproject.toml` unchanged (`mcp` still only under `[project.optional-dependencies]`). `tests/unit/test_mcp_adapter.py` (10 tests) and `tests/unit/test_no_mcp_import_in_core.py` (4 tests) re-confirmed passing this session as part of the 442-test unit run. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

All five truths are now backed by actual execution against a real PostgreSQL 17 instance — not code review alone. The prior verification's residual gap was purely an execution-environment constraint (this sandboxed session has no Docker, no local `initdb` 17, no reachable `DATABASE_URL`); that gap is closed by the user's own terminal run, recorded with exact expected/actual output in `06-UAT.md`, and corroborated by this session's independent `pytest --collect-only` count (763) matching the user's reported pass count (763) exactly.

### Plan-Level must_haves (06-01 through 06-04) — Regression Spot Checks

Re-confirmed unchanged from the prior verification (no source files modified since):
- `ToolRegistry.invoke()` exposes no accessor returning a raw implementation callable.
- `default_registry.names()` returns exactly the 7 D-04 capabilities, no `git.*`/`github.*`.
- `NATIVE_TOOL_CONTRACT` completeness guard holds.
- `collect_role_artifacts` reads through `tool_registry.invoke(role, "artifacts.read", granted, ...)`.
- `config/loader.py` rejects an unregistered capability name.
- No `os.environ.copy()`/`shell=True`/`Session(` pattern in `src/dark_factory/tools/`.
- `mypy --strict` on `src/dark_factory` and `ruff check .` both re-run this session and clean.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/tools/__init__.py` | Error hierarchy + re-exports | ✓ VERIFIED | Unchanged since prior verification; `git status --porcelain -- src/` clean. |
| `src/dark_factory/tools/registry.py` | `ToolRegistry.invoke` deny-by-default gate + capability implementations | ✓ VERIFIED | Unchanged; deny-before-lookup ordering holds. |
| `src/dark_factory/tools/env.py` | `build_worker_env`, `shell_execute`, `ShellResult` | ✓ VERIFIED | Unchanged; additive-from-empty-dict construction holds. |
| `src/dark_factory/tools/native.py` | `NATIVE_TOOL_CONTRACT` (D-02) | ✓ VERIFIED | Unchanged; completeness guard passes. |
| `src/dark_factory/tools/mcp_transport.py` | `build_mcp_server` (D-12, D-15) | ✓ VERIFIED | Unchanged. |
| `tests/unit/test_tool_registry.py` | SC1 grant/deny matrix + edge probes | ✓ VERIFIED | 13 tests, re-run this session, pass. |
| `tests/db/test_capability_denied_fails_role.py` | SC1 tracer db proof | ✓ VERIFIED | 2 tests — now confirmed EXECUTED and PASSING against real PostgreSQL 17 (`06-UAT.md` item 1; user's full-suite run). |
| `tests/integration/test_worker_env_boundary.py` | SC2 cross-process proof | ✓ VERIFIED | 3 tests — now confirmed EXECUTED and PASSING (`06-UAT.md` item 2; user's full-suite run). |
| `tests/unit/test_mcp_adapter.py` | SC5 in-memory client proof | ✓ VERIFIED | 10 tests, re-run this session, pass. |
| `tests/unit/test_no_mcp_import_in_core.py` | SC5 removability guard | ✓ VERIFIED | 4 tests, re-run this session, pass. |
| `tests/integration/test_capability_denial_no_secret_leak.py` | SC4 sweep | ✓ VERIFIED | 6 tests total — now confirmed EXECUTED and PASSING (`06-UAT.md` item 3; user's full-suite run). |
| `tests/integration/test_phase6_acceptance.py` | Phase 6 acceptance gate | ✓ VERIFIED | Included in the full-suite 763-passed run. |
| `tests/db/test_artifact_commit_per_role.py` | Phase 4 artifact-commit db proof (pre-existing, unrelated to phase 6) | ✓ VERIFIED (fixed) | 2 previously-failing tests fixed via stale-fixture repair (commit `ffc333f`), zero production change; now green per the full-suite run. |
| `tests/integration/test_pr_diff_excludes_artifacts.py` | Phase 5 PR-diff exclusion proof (pre-existing, unrelated to phase 6) | ✓ VERIFIED (fixed) | 1 previously-failing test fixed via the same stale-fixture repair; now green per the full-suite run. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `artifacts/validation.py::collect_role_artifacts` | `tools/registry.py` | `tool_registry.invoke(role, "artifacts.read", granted, ...)` | ✓ WIRED | Unchanged; confirmed by source read this session. |
| `orchestrator/runner.py::_run_current_role` | `tools/registry.py` | `tool_registry` threaded through `drive → advance → _advance_once → _run_current_role`; `CapabilityDeniedError` caught ahead of `ArtifactError` | ✓ WIRED | Unchanged. |
| `orchestrator/runner.py` | `events/catalog.py` | `EventType.CAPABILITY_DENIED` prepended in the `ROLE_FAILED` events arm | ✓ WIRED | Unchanged; now confirmed via live db-tier execution (`06-UAT.md` item 1), not code review alone. |
| `config/loader.py::load_effective_config` | `tools/registry.py` | membership validation (`capability not in tool_registry`) raising `ConfigError` | ✓ WIRED | Unchanged. |
| `tools/mcp_transport.py` | `tools/registry.py` | every tool closure calls `registry.invoke(role, capability, granted_tools, **kwargs)` | ✓ WIRED | Unchanged. |
| `pyproject.toml` | `tools/mcp_transport.py` | `mcp` importable only when the optional extra is installed | ✓ WIRED, removable | Unchanged. |

### Data-Flow Trace (Level 4)

Not applicable in the UI-rendering sense. As in the prior verification: `collect_role_artifacts`'s `artifacts.read` call reaches `read_artifact_text` only after `invoke()`'s grant check passes, and `shell_execute`'s spawned environment genuinely originates from `build_worker_env()`'s allowlist comprehension — both unchanged and now additionally confirmed via live cross-process execution (`06-UAT.md` item 2).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit-tier full regression | `uv run pytest -m unit -q` | 442 passed, 0 failed, 19.05s | ✓ PASS |
| Full suite collection count | `uv run pytest --collect-only -q` | 763 tests collected | ✓ PASS (matches user's 763-passed report exactly) |
| Static gates | `uv run mypy src/dark_factory && uv run ruff check .` | clean | ✓ PASS |
| Debt-marker scan on changed test files + debug artifact | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` | zero hits | ✓ PASS |
| `git status --porcelain -- src/` | clean tree | no output | ✓ PASS (no untracked/uncommitted production changes) |
| COVERAGE.md reason-length gate | `awk` length check on the reason column | zero rows > 200 chars | ✓ PASS |
| DB/integration-tier tests | Full suite, real PostgreSQL 17 (user-executed, this session has no reachable Postgres) | `763 passed in 4390.33s (1:13:10)`, 0 failed | ✓ PASS (per `06-UAT.md`, all 4 items `result: pass`) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TOOL-01 | 06-01 | `ToolRegistry` provides the capability layer | ✓ SATISFIED (scoped) | 7 of 11 named capabilities registered per documented D-04/A-06-01 scope decision (git.*/github.* deferred to Phase 9/10, disclosed inline in the acceptance gate). `tests/unit/test_tool_registry.py`, `tests/db/test_capability_denied_fails_role.py` (now confirmed executed). |
| TOOL-02 | 06-01 | New tools addable without modifying every role executor | ✓ SATISFIED | `tests/unit/test_tool_registry_extensibility.py`, `tests/unit/test_native_tool_contract.py`. |
| TOOL-03 | 06-01/06-02 | Deny-by-default per-role grants matching SC1 | ✓ SATISFIED | `tests/unit/test_tool_registry.py`, `tests/unit/test_shell_execute.py`, shipped role YAMLs. |
| TOOL-04 | 06-02 | Worker subprocess env built from explicit allowlist | ✓ SATISFIED | `tests/unit/test_worker_env.py`, cross-process proof now confirmed executed (`tests/integration/test_worker_env_boundary.py`, `06-UAT.md` item 2). |
| TOOL-05 | 06-03 | MCP as optional transport, no orchestrator dependency | ✓ SATISFIED | `tests/unit/test_mcp_adapter.py`, `tests/unit/test_no_mcp_import_in_core.py`. |
| SEC-01 | 06-04 | No credential in artifacts/prompts/payloads/comments/logs/reports | ✓ SATISFIED | `tests/integration/test_capability_denial_no_secret_leak.py`, all 6 arms now confirmed executed (`06-UAT.md` item 3). |
| SEC-03 | 06-02 | Worker subprocess doesn't inherit full env | ✓ SATISFIED | `tests/integration/test_worker_env_boundary.py` (now confirmed executed), `tests/unit/test_shell_execute.py`. |

No orphaned requirements: `REQUIREMENTS.md` maps exactly TOOL-01 through TOOL-05, SEC-01, SEC-03 to Phase 6 (all marked `[x]` / `Complete`), and all seven appear in at least one plan's `requirements:` frontmatter.

### Anti-Patterns Found

None. `src/dark_factory/` files this phase created or modified are unchanged since the prior clean scan (`git status --porcelain -- src/` empty). The two test files touched by the unrelated debug-session fix (`tests/db/test_artifact_commit_per_role.py`, `tests/integration/test_pr_diff_excludes_artifacts.py`) were re-scanned for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` — zero hits. `COVERAGE.md`'s reason column re-scanned — zero rows exceed 200 characters.

### Human Verification Required

None. All 4 items from the prior verification are now closed with live execution evidence, recorded in `06-UAT.md`:

| # | Item | Prior status | Now |
|---|------|--------------|-----|
| 1 | SC1 db-tier tracer proof | Human-verification pending | `result: pass` (06-UAT.md item 1), confirmed by the 763-passed full-suite run |
| 2 | SC2 cross-process env-dump proof | Human-verification pending | `result: pass` (06-UAT.md item 2), confirmed by the 763-passed full-suite run |
| 3 | SC4 db-tier sweep arms | Human-verification pending | `result: pass` (06-UAT.md item 3), confirmed by the 763-passed full-suite run |
| 4 | Full suite regression | Human-verification pending | `result: pass` (06-UAT.md item 4) — exceeded expectation: 763 passed, 0 failed, including the 3 previously-documented pre-existing failures now also fixed |

### Gaps Summary

No gaps. Every artifact this phase's plans claim to have built exists, is substantive, and is wired into the production call sites the plans specify. Every one of the five ROADMAP success criteria and all seven requirement IDs now has passing, non-stub proof executed against a real PostgreSQL 17 instance — the prior verification's sole open item (db/integration-tier execution, blocked by this sandboxed environment's lack of a reachable database) is closed by the user's own terminal run, cross-checked in this session by an independent `pytest --collect-only` count (763) that matches the reported pass count (763) exactly, and by direct inspection of `06-UAT.md`'s per-item expected/actual/result records. The 3 previously-tracked pre-existing failures (phase-4/5-owned, unrelated to phase 6) are also now resolved via a test-fixture-only fix with zero production code change, confirmed by `git show --stat ffc333f` and the debug session's documented root-cause analysis. Phase 6's goal — a role receives exactly the capabilities its configuration grants and nothing more, and a worker subprocess can never reach an infrastructure credential — is verified true in the codebase, not merely claimed in a SUMMARY.

---

*Verified: 2026-09-20*
*Verifier: Claude (gsd-verifier)*
