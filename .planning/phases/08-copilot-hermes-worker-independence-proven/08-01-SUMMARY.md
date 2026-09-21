---
phase: 08-copilot-hermes-worker-independence-proven
plan: 01
subsystem: workers
tags: [copilot-cli, subprocess-worker, cli-adapter, credential-boundary, tdd]

requires:
  - phase: 07-claude-code-the-first-real-worker
    provides: "ClaudeCodeWorker's proven spawn/timeout/redact/NEEDS_INPUT pipeline, MissingWorkerCredentialError shape, and NATIVE_TOOL_CONTRACT's first real consumer pattern -- the literal structural template this plan extracts and reuses."
provides:
  - "CopilotWorker, a real CodingWorker adapter registered as `copilot`, replacing the _NotYetImplementedWorker placeholder"
  - "workers/cli_runtime.py -- the shared NEEDS_INPUT contract, prompt assembly, spawn/timeout/redact pipeline, and declared-artifact reporter every CLI adapter now imports from, instead of duplicating"
  - "Settings.copilot_github_token / Settings.copilot_model -- the Copilot credential boundary (D-01), automatically covered by known_secret_values()"
  - "tests/support/fake_copilot_cli.py -- the faked-executable-on-PATH test harness for Copilot, mirroring fake_claude_cli.py"
  - "cli_runtime.collect_declared_artifacts() -- shared by both ClaudeCodeWorker and CopilotWorker so they cannot drift on artifact reporting"
  - "tests/contract/test_coding_worker_contract.py now runs FakeWorker, ClaudeCodeWorker, and CopilotWorker against a shared fake-CLI fixture"
affects: [08-02-hermes-worker, 08-03-live-integration-suites, 08-04-role-reassignment-sc2]

actuals:
  tokens: 24980
  tasks: 3
  commits: 7

tech-stack:
  added: []
  patterns:
    - "Shared CLI-adapter runtime module (cli_runtime.py): binary-agnostic spawn/timeout/redact pipeline and NEEDS_INPUT pause contract extracted once, imported by every adapter (D-03)."
    - "Deny-by-omission native-tool translation: an adapter-local Mapping[capability, tuple[native_names]] plus a coverage-completeness check against NATIVE_TOOL_CONTRACT, mirrored per adapter."
    - "Declared-artifact reporting on the COMPLETED branch only: a shared helper resolves each declared output filename under the run root and reports a ref only if the file actually exists -- never fabricated."

key-files:
  created:
    - src/dark_factory/workers/cli_runtime.py
    - src/dark_factory/workers/copilot.py
    - tests/support/fake_copilot_cli.py
    - tests/unit/test_copilot_worker.py
  modified:
    - src/dark_factory/workers/claude_code.py
    - src/dark_factory/workers/registry.py
    - src/dark_factory/config/settings.py
    - tests/unit/test_native_tool_contract.py
    - tests/contract/test_coding_worker_contract.py
    - tests/unit/test_claude_code_worker.py
    - tests/unit/test_worker_registry_names.py

key-decisions:
  - "Extracted the binary-agnostic half of ClaudeCodeWorker into cli_runtime.py as a pure, behavior-preserving move before writing any Copilot-specific code, so the 50 pre-existing ClaudeCodeWorker tests double as the refactor's regression proof."
  - "Copilot's artifacts.read/artifacts.write capabilities collapse onto the same unscoped read/write --allow-tool names as repo.read/repo.write (T-08-05, accepted risk) -- the CLI has no path-scoped specifier; enforce_write_scope and the subprocess cwd remain the compensating boundary."
  - "CopilotWorker.resume() has only a context-reconstruction branch and never reads previous.worker_session_id -- native_resume=False is a documented fact from 08-RESEARCH.md, not a placeholder for a future native path."

patterns-established:
  - "Pattern: mirror-then-diverge adapter construction -- copy the proven adapter's structure verbatim, then change only argv construction, the credential name, and output parsing."

requirements-completed: [WORK-05]

coverage:
  - id: D1
    description: "CopilotWorker spawns the copilot CLI non-interactively and normalizes COMPLETED/empty-output results, replacing the registry placeholder"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_execute_returns_completed_with_summary_and_no_session_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_execute_empty_stdout_returns_completed_with_empty_summary"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_default_registry_returns_a_copilot_worker_instance"
        status: pass
    human_judgment: false
  - id: D2
    description: "Native-tool grant translation is deny-by-omission and never emits the four forbidden Copilot flags (blanket tool/path permission, transcript sharing)"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_allowed_tools_argv_for_granted_capabilities"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_argv_disjoint_from_forbidden_flags"
        status: pass
    human_judgment: false
  - id: D3
    description: "Credential-bounded subprocess environment: COPILOT_GITHUB_TOKEN reaches the child, DATABASE_URL/GITHUB_TOKEN never do, and a missing credential fails before spawning"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_subprocess_env_has_credential_and_lacks_infra_secrets"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_missing_credential_returns_failed_and_spawns_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every failure path (timeout with process-group kill, non-zero exit, missing binary) becomes a FAILED WorkerResult, never a raised exception"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_timeout_kills_process_group_and_persists_output"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_non_zero_exit_returns_failed_with_exit_code_and_stderr"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_missing_copilot_binary_returns_failed_without_raising"
        status: pass
    human_judgment: false
  - id: D5
    description: "resume() reconstructs context (no native session branch) and captured transcripts are redacted before persistence"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_resume_reconstructs_context_no_resume_flag"
        status: pass
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_captured_output_is_redacted"
        status: pass
    human_judgment: false
  - id: D6
    description: "The shared CodingWorker contract suite passes for CopilotWorker alongside FakeWorker/ClaudeCodeWorker with no live binary and no live credential"
    requirement: "WORK-05"
    verification:
      - kind: contract
        ref: "tests/contract/test_coding_worker_contract.py (WORKER_FACTORIES, 19 parametrized tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Declared outputs a real CLI adapter's CLI actually wrote are reported as ArtifactRefs on COMPLETED only, shared identically by CopilotWorker and ClaudeCodeWorker"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_copilot_worker.py#test_end_to_end_completed_result_reports_declared_artifacts"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_end_to_end_completed_result_reports_declared_artifact"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-21
status: complete
---

# Phase 8 Plan 1: CopilotWorker -- A Second Real Agent Runtime Summary

**`CopilotWorker` spawns the real `copilot` CLI non-interactively through a shared `cli_runtime.py` pipeline extracted from `ClaudeCodeWorker`, is registered under `"copilot"` replacing the placeholder, and reports its declared artifacts alongside `ClaudeCodeWorker` through one shared helper -- proven against a faked binary with no live credential.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-21T15:20:07+03:00
- **Completed:** 2026-09-21T15:32:29+03:00
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- `CopilotWorker` (`src/dark_factory/workers/copilot.py`) is a real, working `CodingWorker` adapter: spawns `copilot -p "<prompt>" --no-ask-user -s [--allow-tool <name> ...] [--model <pin>]`, normalizes plain-text stdout into a `WorkerResult`, and never raises out of `execute()`/`resume()`.
- Extracted the binary-agnostic half of `ClaudeCodeWorker` into `workers/cli_runtime.py` as a pure, behavior-preserving move (NEEDS_INPUT contract, prompt assembly, spawn/timeout/redact pipeline, run-dir resolution) -- both adapters now share one implementation instead of two copies that could drift.
- Every Copilot failure path (timeout + process-group kill, non-zero exit, missing binary, missing credential) returns `FAILED`, never an exception; `resume()` reconstructs context because `native_resume=False` is a documented fact (08-RESEARCH.md), not a placeholder.
- Captured `copilot` transcripts are redacted through the same `scrub_log_in_place` pipeline `ClaudeCodeWorker` uses, proven by a present-then-absent assertion.
- The shared `CodingWorker` contract suite now runs `FakeWorker`, `ClaudeCodeWorker`, and `CopilotWorker` (19 parametrized tests) against one generalized fake-binary fixture, with no live binary and no live credential -- verified green even with `COPILOT_GITHUB_TOKEN`/`ANTHROPIC_API_KEY` unset in the invoking environment.
- `cli_runtime.collect_declared_artifacts()` reports exactly the declared output files a real adapter's CLI actually wrote (never fabricated), wired into both `CopilotWorker` and `ClaudeCodeWorker`'s `COMPLETED` branches.

## Task Commits

Each task was committed atomically (TDD RED/GREEN per task, plus one preparatory refactor commit):

1. **Preparatory refactor: extract cli_runtime.py** - `aa9d9d6` (refactor)
2. **Task 1: One role runs end to end through the real `copilot` CLI** - `8471297` (test, RED) -> `15ce655` (feat, GREEN)
3. **Task 2: Every Copilot failure path becomes FAILED, resume reconstructs context, contract suite runs the adapter** - `33ab7c6` (test) -> `b47b058` (feat, contract suite wiring)
4. **Task 3: A real adapter reports the artifacts its CLI actually wrote** - `6a066ee` (test, RED) -> `6e0c100` (feat, GREEN)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP, applied by the orchestrator after wave merge -- worktree mode)

_Note: Task 2's failure-path/resume/redaction tests (9 tests) passed immediately on first run -- see Deviations below for why this is a legitimate TDD outcome, not a suppressed RED._

## Files Created/Modified
- `src/dark_factory/workers/cli_runtime.py` - shared CLI-adapter runtime: NEEDS_INPUT contract, prompt assembly, spawn/timeout/redact pipeline, run-dir resolution, declared-artifact reporter
- `src/dark_factory/workers/copilot.py` - `CopilotWorker`, `MissingWorkerCredentialError`, `allowed_tools_for()`, native-tool translation table
- `src/dark_factory/workers/claude_code.py` - now imports the shared runtime from `cli_runtime.py` instead of defining private copies; COMPLETED branch reports declared artifacts
- `src/dark_factory/workers/registry.py` - `"copilot"` now registers the real `CopilotWorker` class
- `src/dark_factory/config/settings.py` - `copilot_github_token: SecretStr | None`, `copilot_model: str | None`
- `tests/support/fake_copilot_cli.py` - faked `copilot` executable-on-PATH test harness
- `tests/unit/test_copilot_worker.py` - full behavior suite for `CopilotWorker` (35 tests)
- `tests/unit/test_native_tool_contract.py` - `copilot.py` added to `_ALLOWED_CONSUMERS`
- `tests/contract/test_coding_worker_contract.py` - `CopilotWorker` added to `WORKER_FACTORIES`; fixture generalized to install both fake CLIs
- `tests/unit/test_claude_code_worker.py` - `_context()` gains `outputs=`; one mirrored end-to-end artifact-reporting test
- `tests/unit/test_worker_registry_names.py` - `copilot` placeholder test replaced with a real-adapter test (Rule 1 fix, see Deviations)

## Decisions Made
- Did the `cli_runtime.py` extraction as its own preparatory commit before any Copilot-specific code, so the pre-existing 50-test `test_claude_code_worker.py` suite proves the refactor is behavior-preserving before new functionality is layered on top.
- Kept `CopilotWorker._resume()` to a single context-reconstruction branch, deliberately never reading `previous.worker_session_id` -- a branch on it would be dead code implying a native resume path this adapter does not have (08-RESEARCH.md Finding 2/Pitfall 1).
- `--model` is appended only when `Settings.copilot_model` is a non-empty string; no default model is pinned, per D-02's decision to defer the live spike.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated a pre-existing test that asserted `copilot` still raised `NotImplementedError`**
- **Found during:** Task 3 full-suite verification (`pytest -m "unit or contract" -q`)
- **Issue:** `tests/unit/test_worker_registry_names.py::test_phase_8_placeholders_resolve_but_every_entry_point_names_phase_8` was parametrized over `["copilot", "hermes"]` and asserted every entry point raised `NotImplementedError` naming "Phase 8" -- an assumption this plan's own registry change (`copilot` now resolves to a real adapter) directly invalidates.
- **Fix:** Removed `"copilot"` from that parametrization (only `"hermes"` remains a genuine Phase 8 placeholder) and added `test_copilot_resolves_to_a_real_adapter_not_a_placeholder`, mirroring the existing `claude-code` real-adapter test exactly.
- **Files modified:** `tests/unit/test_worker_registry_names.py`
- **Verification:** Full `pytest -m "unit or contract" -q` green (545 passed, 1 skipped) after the fix.
- **Commit:** `6e0c100` (part of Task 3's GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug -- outdated test assumption directly caused by this plan's own change)
**Impact on plan:** Necessary correction; no scope creep. The test's assumption became false the moment `registry.py` was edited in Task 1's GREEN commit, but the fix was deferred to Task 3's full-suite run per normal verification cadence and is documented here rather than silently folded into an earlier commit.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. (A live `copilot` binary and a real `COPILOT_GITHUB_TOKEN` are needed only for the live-integration suite 08-03 will add; this plan's entire test surface runs against a faked executable, per D-02.)

## Next Phase Readiness
- `CopilotWorker` is a complete, tested, registered adapter -- ready for 08-02 (`HermesWorker`, following the identical mirror-then-diverge pattern against `cli_runtime.py`) and 08-04 (the SC2 role-reassignment proof, which needs `.dark-factory/roles/ARCHITECTURE.yaml` reassigned to `worker: copilot`).
- `cli_runtime.py`'s shared pipeline and `collect_declared_artifacts()` are now proven by two real adapters, not one -- 08-02's `HermesWorker` inherits both with no new design work.
- The `tests/contract/test_coding_worker_contract.py` fixture is already shaped to accept a third fake CLI (08-02 adds `fake_hermes_cli.py` the same way this plan added `fake_copilot_cli.py`).
- No blockers identified.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-21*

## Self-Check: PASSED

- All 4 `key-files.created` verified present on disk.
- All 7 task commit hashes (`aa9d9d6`, `8471297`, `15ce655`, `33ab7c6`, `b47b058`, `6a066ee`, `6e0c100`) confirmed in `git log --oneline --all`.
- `pytest -m "unit or contract" -q`: 545 passed, 1 skipped (pre-existing, unrelated `mcp` optional-dependency skip).
- `uv run mypy src/dark_factory`: 0 new errors (2 pre-existing errors in an untouched module, `tools/mcp_transport.py`, confirmed byte-identical to the plan's base commit).
- `uv run ruff check .`: all checks passed.
- Plan-level acceptance criteria and `<verification>` block re-passed in full.
