---
phase: 07-claude-code-the-first-real-worker
plan: 01
subsystem: workers
tags: [subprocess, claude-code-cli, redaction, worker-adapter, pydantic-settings]

# Dependency graph
requires:
  - phase: 06-tools-and-permissions
    provides: build_worker_env() credential-bounded subprocess environment, Settings.known_secret_values(), dark_factory.events.redaction.redact()
provides:
  - "ClaudeCodeWorker: a real, working CodingWorker adapter registered as default_registry's \"claude-code\" factory"
  - "Settings.anthropic_api_key (SecretStr | None) and Settings.worker_timeout_seconds (int, default 1800) fields"
  - "tests/support/fake_claude_cli.py: PATH-prepended fake claude executable, the codebase's first fake-executable-on-PATH test technique"
affects: [07-02 (CI wiring), 07-03 (resume()/NEEDS_INPUT marker), 07-04 (--allowedTools narrowing)]

# Actuals (#2632)
actuals:
  tokens: 12343
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stream-to-file subprocess (stdout/stderr as open file objects, never PIPE) + Popen.wait(timeout=...) + os.killpg(SIGKILL) on TimeoutExpired -- avoids buffering the transcript in parent memory (D-04) while reusing tools/env.py's process-group-kill discipline"
    - "Redact-before-return: a worker adapter's own finally block scrubs its captured transcript with the existing redact()/known_secret_values() pipeline before execute() returns, because the downstream git commit step force-adds the whole run tree and never re-scrubs it"
    - "Fake-executable-on-PATH: prepend a directory containing a small generated `claude` script to PATH so build_worker_env()'s verbatim PATH copy resolves the bare command name to the fake -- zero ClaudeCodeWorker code changes needed for testing"

key-files:
  created:
    - src/dark_factory/workers/claude_code.py
    - tests/support/fake_claude_cli.py
    - tests/unit/test_claude_code_worker.py
  modified:
    - src/dark_factory/config/settings.py
    - src/dark_factory/workers/registry.py
    - tests/unit/test_settings.py
    - tests/unit/test_worker_registry_names.py

key-decisions:
  - "D-02/D-03 implemented as planned: anthropic_api_key: SecretStr | None = None (no new required startup config) and worker_timeout_seconds: int = 1800 (env-overridable, validated strictly positive)"
  - "resume()/capabilities() are deliberate stubs this plan -- resume() raises NotImplementedError naming plan 07-03; capabilities() reports native_resume=False honestly rather than the eventual native_resume=True, since the --resume argv branch does not exist yet"
  - "_scrub_log_in_place() runs in a finally block wrapping _run_streamed(), so redaction happens on every exit path (success/non-zero-exit/timeout-kill) and strictly before any later code re-reads the log files for JSON parsing"

patterns-established:
  - "Pattern: fake-claude-on-PATH test technique (tests/support/fake_claude_cli.py) -- reusable by 07-03/07-04 and by the eventual tests/contract/test_coding_worker_contract.py WORKER_FACTORIES addition"

requirements-completed: [WORK-04]

coverage:
  - id: D1
    description: "ClaudeCodeWorker.execute() spawns the claude CLI non-interactively with -p/--output-format json/--permission-mode dontAsk and returns a normalized WorkerResult(COMPLETED) with worker_session_id/summary from the CLI's JSON result"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_execute_returns_completed_with_session_id_and_summary"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_argv_contains_required_flags"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_attempt_log_file_exists_and_contains_the_fake_output"
        status: pass
    human_judgment: false
  - id: D2
    description: "The subprocess environment carries ANTHROPIC_API_KEY and structurally excludes DATABASE_URL/GITHUB_TOKEN even when both are set in the parent process"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_subprocess_env_has_credential_and_lacks_infra_secrets"
        status: pass
    human_judgment: false
  - id: D3
    description: "default_registry.get(\"claude-code\") returns a real ClaudeCodeWorker, replacing the Phase-7 NotImplementedError placeholder"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_default_registry_returns_a_claude_code_worker_instance"
        status: pass
      - kind: unit
        ref: "tests/unit/test_worker_registry_names.py#test_claude_code_resolves_to_a_real_adapter_not_a_placeholder"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every failure mode (hang/timeout, non-zero exit, unparseable output, missing binary, missing credential) returns WorkerResult(FAILED) without execute() ever raising; a hung child is killed with its process group, leaving no grandchild alive, with the pre-kill partial transcript surviving on disk"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_timeout_kills_process_group_and_persists_output"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_non_zero_exit_returns_failed_with_exit_code_and_stderr"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_non_json_stdout_returns_failed_without_raising"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_missing_claude_binary_returns_failed_without_raising"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_missing_credential_returns_failed_and_spawns_nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "[BLOCKING] No captured claude transcript reaches disk (and therefore the PR branch) still carrying a live credential value, on any exit path; a pattern-only secret not registered in Settings is still scrubbed; a raw non-UTF-8 stdout byte never raises"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_captured_output_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_captured_stderr_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_redaction_applies_on_non_zero_exit_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_redaction_applies_on_timeout_kill_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_pattern_only_secret_not_in_settings_is_still_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_non_utf8_stdout_byte_does_not_raise"
        status: pass
    human_judgment: false
  - id: D6
    description: "Settings gains anthropic_api_key (SecretStr | None = None, D-02) and worker_timeout_seconds (int = 1800, env-overridable, validated strictly positive, D-03)"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_settings.py#test_anthropic_api_key_defaults_to_none"
        status: pass
      - kind: unit
        ref: "tests/unit/test_settings.py#test_worker_timeout_seconds_defaults_to_1800"
        status: pass
      - kind: unit
        ref: "tests/unit/test_settings.py#test_non_positive_worker_timeout_is_rejected"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-09-20
status: complete
---

# Phase 7 Plan 1: One Role Runs End to End Through the Real Claude Code CLI Summary

**`ClaudeCodeWorker` spawns the real `claude` CLI non-interactively via a stream-to-file subprocess, redacts its captured transcript before returning, and is now `default_registry`'s live "claude-code" adapter.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-20T17:55:15Z
- **Completed:** 2026-09-20T18:04:27Z
- **Tasks:** 3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- `ClaudeCodeWorker.execute()` genuinely spawns `claude -p "<prompt>" --output-format json --permission-mode dontAsk` with an explicit `list[str]` argv (never `shell=True`), streams stdout/stderr directly to open file objects under `<run_root>/logs/<role>/attempt-<N>.std{out,err}.log` (never buffered via `PIPE`), and normalizes the CLI's single JSON result object into a `WorkerResult`
- Every failure mode -- a hung subprocess, a non-zero exit, garbage stdout, an absent `claude` binary, an absent credential -- returns `WorkerResult(FAILED)` with no exception ever escaping `execute()`; a timed-out subprocess is killed by its whole process group (`os.killpg(..., SIGKILL)`) and leaves no grandchild alive, while its pre-kill partial output survives on disk
- `[BLOCKING]` Both captured log files are rewritten through the existing `redact()`/`Settings.known_secret_values()` pipeline in a `finally` block, on every exit path, before `execute()` returns and before `git.diff.commit_run_artifacts` later force-adds the whole run tree onto the PR branch
- `default_registry.register("claude-code", ClaudeCodeWorker)` replaces the Phase-7 `NotImplementedError` placeholder
- `tests/support/fake_claude_cli.py` establishes the codebase's first fake-executable-on-`PATH` test technique, reusable by plans 07-03/07-04 and the eventual contract-suite addition

## Task Commits

Each task was committed atomically (RED/GREEN pairs per `tdd="true"`):

1. **Task 1: One role runs end to end through the real `claude` CLI**
   - `1d51dc5` test(07-01): add failing tests for ClaudeCodeWorker happy path
   - `0bcce08` feat(07-01): ClaudeCodeWorker spawns the real claude CLI end to end
2. **Task 2: Every failure path becomes a persisted FAILED result, and a hung child dies with its process group**
   - `bd10b0b` feat(07-01): every claude-code failure path returns a persisted FAILED result
3. **Task 3: [BLOCKING] Redact the captured transcript before it can reach the PR branch**
   - `8c17069` feat(07-01): [BLOCKING] redact captured claude transcripts before commit

**Plan metadata:** (this commit, see below)

_Note: Tasks 2 and 3 combined their RED and GREEN cycles into a single `feat` commit each -- the failing tests were verified locally (`pytest -k ...`) before the corresponding implementation was written in the same edit session, but only the passing (GREEN) state was committed. Task 1 alone shows the full `test(...)` -> `feat(...)` split. Documented as a deviation below._

## Files Created/Modified
- `src/dark_factory/workers/claude_code.py` - the new adapter: constants, `MissingWorkerCredentialError`, `attempt_log_paths()`, `_build_prompt()`, `_base_argv()`, `_run_streamed()`, `_scrub_log_in_place()`, `ClaudeCodeWorker`
- `tests/support/fake_claude_cli.py` - `write_fake_claude()` + `fake_claude_env()`, the fake-`claude`-on-`PATH` test technique
- `tests/unit/test_claude_code_worker.py` - 18 tests covering the happy path, every failure path, and redaction on every exit path
- `src/dark_factory/config/settings.py` - `anthropic_api_key: SecretStr | None = None`, `worker_timeout_seconds: int = 1800` + a strictly-positive validator
- `src/dark_factory/workers/registry.py` - `"claude-code"` registration swapped from the placeholder factory to `ClaudeCodeWorker` itself
- `tests/unit/test_settings.py` - coverage for the two new `Settings` fields
- `tests/unit/test_worker_registry_names.py` - `claude-code` assertions updated to describe the real adapter (Rule 1, see below)

## Decisions Made
- Followed D-02/D-03/D-04 exactly as locked in 07-CONTEXT.md/07-RESEARCH.md: optional credential field, single env-overridable timeout knob defaulting to 1800s, log streaming reusing `run_root()`'s existing tree
- `resume()`/`capabilities()` are honest stubs, not silent pass-throughs: `resume()` raises `NotImplementedError` naming plan 07-03 (rather than delegating to `execute()`, which would return a plausible-looking but wrong result); `capabilities()` reports `native_resume=False` (accurate for what this plan implements, not the eventual `True` once 07-03 lands `--resume`)
- `_scrub_log_in_place()` runs in a `finally` around `_run_streamed()` specifically so it fires on every exit path and so the JSON parse afterward only ever reads already-scrubbed text, closing the SEC-01 gap `07-RESEARCH.md` flagged (Pitfall 1)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_worker_registry_names.py`'s `claude-code` assertions described the now-replaced placeholder**
- **Found during:** Task 1 (registry swap)
- **Issue:** `test_claude_code_placeholder_resolves_but_every_entry_point_names_phase_7` asserted `execute()`/`resume()`/`capabilities()` all raise `NotImplementedError` naming "Phase 7" -- true of the placeholder this plan intentionally replaces, so the test now describes stale behavior rather than a real bug in new code.
- **Fix:** Replaced with `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, asserting `isinstance(worker, ClaudeCodeWorker)`, that `execute({})` returns `FAILED` (never raises), that `resume()` still raises `NotImplementedError` naming "07-03", and that `capabilities()` does not raise.
- **Files modified:** `tests/unit/test_worker_registry_names.py`
- **Verification:** `uv run pytest -m unit -q tests/unit/test_worker_registry_names.py` passes; full unit suite (465 tests) green.
- **Committed in:** `0bcce08` (Task 1 GREEN commit)

**2. [TDD process note, not a Rule 1-3 deviation] Tasks 2 and 3 skipped a separate RED commit**
- **Found during:** Tasks 2 and 3
- **Issue:** Per `tdd="true"` discipline, each task's new tests were written and confirmed failing (intentional, assertion-level RED -- verified via `pytest -k <new tests>`) before the corresponding production code was written. However, the RED state was not committed separately before the GREEN implementation for Tasks 2 and 3 (unlike Task 1, which has a standalone `test(07-01)` commit). Both tests and implementation for each of Tasks 2/3 landed in a single `feat(07-01)` commit.
- **Why acceptable:** `workflow.tdd_mode` is not enabled in this project's config, so there is no blocking RED-commit gate; the RED evidence was still genuinely produced and inspected (not skipped), just not separately committed. Flagged here per the `## TDD Gate Compliance` convention for transparency.
- **Impact:** None on correctness -- git history for Tasks 2/3 shows test+implementation together rather than as two commits; Task 1 demonstrates the full split was followed at least once as the tracer's own proof.

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix in a pre-existing test) + 1 TDD-process note.
**Impact on plan:** The Rule 1 fix was necessary and in-scope (the placeholder test was directly invalidated by this plan's own registry swap). No scope creep. The TDD-process note does not affect any acceptance criterion, verification command, or the plan's success criteria.

## TDD Gate Compliance

| Task | RED commit | GREEN commit | Notes |
|------|-----------|--------------|-------|
| Task 1 | `1d51dc5` | `0bcce08` | Full RED/GREEN split, as specified |
| Task 2 | none (RED verified, not committed separately) | `bd10b0b` | See deviation #2 above; `tdd_mode` not enabled |
| Task 3 | none (RED verified, not committed separately) | `8c17069` | See deviation #2 above; `tdd_mode` not enabled |

## Known Stubs

- `ClaudeCodeWorker.resume()` (`src/dark_factory/workers/claude_code.py:388`) raises `NotImplementedError` naming plan 07-03. This is in-scope-as-planned: the plan's own artifact table states "`ClaudeCodeWorker.resume()`/`capabilities()` (07-03)" as work produced by the rest of the phase, not this plan. `execute()` -- this plan's entire deliverable -- is fully implemented and proven end to end. Recorded in `.planning/WINDOWS.md` as ledger entry #10 (kind: stub) so it stays visible until 07-03 resolves it.
- `ClaudeCodeWorker.capabilities()` currently reports `native_resume=False`, which is accurate for what this plan ships (no `--resume` argv branch exists yet) but will become `True` once plan 07-03 lands. Not tracked as a separate ledger entry -- it is the same gap as `resume()` above, viewed from the capabilities side.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required. (A live `claude` CLI on `PATH` and a real `ANTHROPIC_API_KEY` are needed only for an actual integration-tier/production run against the real binary; every automated test in this plan fakes both.)

## Next Phase Readiness
- Plan 07-02 (CI wiring) and 07-04 (`--allowedTools` narrowing) can proceed independently against this adapter.
- Plan 07-03 (native `--resume`, `NEEDS_INPUT` marker parsing) has a clear, explicit seam: `resume()`'s current `NotImplementedError` names it directly, and `_build_prompt()`'s docstring marks the clarification-protocol insertion point.
- No blockers. The `resume()`/`capabilities()` gap is tracked in `.planning/WINDOWS.md` (entry #10), not hidden.

---
*Phase: 07-claude-code-the-first-real-worker*
*Completed: 2026-09-20*

## Self-Check: PASSED

All key files confirmed present on disk (`src/dark_factory/workers/claude_code.py`,
`tests/support/fake_claude_cli.py`, `tests/unit/test_claude_code_worker.py`,
`src/dark_factory/config/settings.py`, `src/dark_factory/workers/registry.py`,
`tests/unit/test_settings.py`, `tests/unit/test_worker_registry_names.py`). All four
task commits (`1d51dc5`, `0bcce08`, `bd10b0b`, `8c17069`) confirmed present in
`git log`. Full unit suite re-verified green (465 passed), `mypy --strict` and
`ruff check` both exit 0, and the plan's named pre-existing guards
(`test_no_worker_name_leak.py`, `test_no_environ_copy.py`,
`test_git_ownership_boundary.py`, `test_single_mutation_path.py`) all pass.
