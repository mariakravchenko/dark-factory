---
phase: 07-claude-code-the-first-real-worker
plan: 03
subsystem: workers
tags: [subprocess, claude-code-cli, resume, needs-input, contract-suite, redaction]

# Dependency graph
requires:
  - phase: 07-claude-code-the-first-real-worker
    provides: "07-01: ClaudeCodeWorker.execute() end to end, Settings.anthropic_api_key/worker_timeout_seconds, the fake-claude-on-PATH test technique"
provides:
  - "ClaudeCodeWorker.resume(): native --resume <session_id> branch when previous.worker_session_id is set, context-reconstruction branch (rebuilds the prompt from context + previous.summary/questions + answer) when it is absent -- both behind the identical worker.resume(context, previous, answer) call"
  - "ClaudeCodeWorker.capabilities() now reports native_resume=True, matching the real --resume flag"
  - "NEEDS_INPUT_MARKER/NEEDS_INPUT_PROTOCOL/_NEEDS_INPUT_RE: the D-01 two-sided clarification convention -- a fixed prompt block plus the line-anchored regex that parses it back into WorkerResult(status=NEEDS_INPUT)"
  - "_spawn_and_parse(argv, context): the shared spawn/timeout/redact/parse pipeline execute() and resume() both call, so redaction and the never-raise wrapper cannot drift between entry points"
  - "tests/contract/test_coding_worker_contract.py::WORKER_FACTORIES now runs the shared suite against both FakeWorker and ClaudeCodeWorker, with a fake claude CLI on PATH and no live Anthropic credential"
affects: [07-04 (--allowedTools narrowing), 08-* (CopilotWorker/HermesWorker -- append to WORKER_FACTORIES, same contract)]

# Actuals (#2632)
actuals:
  tokens: 8541
  tasks: 3
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared spawn/timeout/redact/parse pipeline: _spawn_and_parse(argv, context) -> WorkerResult is called by both execute() and resume(), so the redaction finally-block and the never-raise outer wrapper live in exactly one place and cannot diverge between entry points"
    - "Two-sided marker convention: a module constant (NEEDS_INPUT_MARKER) names the token, a fixed prompt block (NEEDS_INPUT_PROTOCOL) states the rule to the agent, and a line-anchored regex (_NEEDS_INPUT_RE, MULTILINE+DOTALL+\\Z) parses it back out -- changing one without the other silently disables clarification, so they are documented as a pair"
    - "_context_prompt_sections(context) factored out of _build_prompt so _build_resume_prompt shares the identical task/instructions/inputs material, appending only the previous-attempt/outstanding-questions/human-answer sections before re-appending the clarification protocol last"

key-files:
  created: []
  modified:
    - src/dark_factory/workers/claude_code.py
    - tests/unit/test_claude_code_worker.py
    - tests/contract/test_coding_worker_contract.py
    - tests/unit/test_worker_registry_names.py

key-decisions:
  - "D-01 marker regex: MULTILINE anchors the marker to the start of a line so ordinary prose mentioning the token mid-sentence never triggers a pause; DOTALL + \\Z captures a multi-line question in one shot with no second delimiter"
  - "_extract_needs_input degrades an empty capture (marker line followed only by whitespace) to None (no marker) rather than an empty-string question, avoiding WorkerResult's empty-question ValidationError firing from inside the adapter and being downgraded to a spurious FAILED"
  - "resume()'s native branch treats previous.worker_session_id as a single opaque argv element after --resume -- never parsed, split, validated or reformatted (HITL-04)"
  - "capabilities() now reports native_resume=True (07-01 deliberately reported False, naming this plan as the one that would flip it)"
  - "worker_timeout_seconds stays the single knob for both execute() and resume() (D-03) -- no second Settings field was added"

patterns-established:
  - "Pattern: shared _spawn_and_parse(argv, context) private method as the single spawn/timeout/redact/parse implementation behind both public entry points -- reusable by 07-04's --allowedTools work and by Phase 8's CopilotWorker/HermesWorker if they adopt the same subprocess shape"

requirements-completed: [WORK-07, HITL-04, HITL-05, QUAL-02]

coverage:
  - id: D1
    description: "A CLI result whose text contains a line-initial NEEDS_INPUT: marker produces WorkerResult(status=NEEDS_INPUT) with exactly one extracted question; a mid-sentence mention or a whitespace-only marker line degrades to COMPLETED, never a spurious FAILED from an empty-question ValidationError (D-01)"
    requirement: "WORK-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_needs_input_marker_produces_needs_input_with_question"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_needs_input_marker_multiline_question_captured_whole"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_needs_input_marker_mid_sentence_does_not_trigger"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_needs_input_marker_followed_by_only_whitespace_degrades_to_completed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_needs_input_result_carries_worker_session_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_prompt_argument_contains_the_needs_input_marker_token"
        status: pass
    human_judgment: false
  - id: D2
    description: "ClaudeCodeWorker().capabilities() accurately reports native_resume=True, session_id=True, structured_output=True, non_interactive=True, emits_changed_files=False (WORK-07)"
    requirement: "WORK-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_capabilities_reports_native_resume_and_all_expected_flags"
        status: pass
    human_judgment: false
  - id: D3
    description: "When previous.worker_session_id is set, resume() emits --resume <id> verbatim as a single opaque argv element, using the answer (or RESUME_CONTINUATION_PROMPT when None) as the -p value (HITL-04)"
    requirement: "HITL-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_uses_native_session_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_with_null_answer_yields_non_empty_prompt_on_both_branches"
        status: pass
    human_judgment: false
  - id: D4
    description: "When previous.worker_session_id is absent, resume() takes the context-reconstruction branch: no --resume element, and the prompt is rebuilt from context plus previous.summary/questions and the answer -- both branches return through the identical worker.resume(context, previous, answer) call site (HITL-05)"
    requirement: "HITL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_without_session_id_reconstructs_context"
        status: pass
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "resume() shares execute()'s entire spawn/timeout/redact/parse pipeline: a timed-out resume() returns FAILED with the partial transcript persisted, a captured transcript is redacted before return, and a missing credential returns FAILED without raising -- one worker_timeout_seconds knob for both (D-03)"
    requirement: "HITL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_timeout_returns_failed_and_persists_partial_log"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_redacts_captured_transcript"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_resume_missing_credential_returns_failed_without_raising"
        status: pass
    human_judgment: false
  - id: D6
    description: "The shared CodingWorker contract suite runs against both FakeWorker and ClaudeCodeWorker (WORKER_FACTORIES) with no live claude binary and no live Anthropic credential; no assertion was weakened, skipped, xfail'ed or made adapter-conditional (QUAL-02)"
    requirement: "QUAL-02"
    verification:
      - kind: integration
        ref: "uv run pytest -m contract -q tests/contract/test_coding_worker_contract.py (13 passed)"
        status: pass
      - kind: integration
        ref: "env -u ANTHROPIC_API_KEY uv run pytest -m contract -q tests/contract/test_coding_worker_contract.py (13 passed)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Registering the name claude-code twice on a WorkerRegistry leaves exactly one bound factory (last registration wins), and default_registry.get(\"claude-code\") is a real ClaudeCodeWorker, never the placeholder"
    requirement: "QUAL-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_duplicate_registration_binds_exactly_one_factory"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_default_registry_claude_code_is_not_the_not_yet_implemented_worker"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-20
status: complete
---

# Phase 7 Plan 3: Pause/Resume Through the Real Claude Code CLI Summary

**`ClaudeCodeWorker.resume()` now resumes natively via `--resume <session_id>` or by rebuilding context when no session id exists, `capabilities()` reports `native_resume=True`, and the shared `CodingWorker` contract suite runs against the real adapter with a faked CLI and no live credential.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-20T18:18:12Z
- **Completed:** 2026-09-20T18:30:12Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- A role attempt can now ask a human a question through the real `claude` CLI: a line-initial `NEEDS_INPUT:` marker in the CLI's own `result` text produces `WorkerResult(status=NEEDS_INPUT, questions=[...])`, while an ordinary mid-sentence mention or a whitespace-only marker line degrades safely to `COMPLETED` -- never a spurious `FAILED` from an empty-question `ValidationError` (D-01)
- A paused role resumes two ways behind the identical `worker.resume(context, previous, answer)` call: natively via `--resume <session_id>` (the id crossing as a single opaque argv element, never parsed or reformatted -- HITL-04), or by context reconstruction when no session id exists (HITL-05) -- both share `execute()`'s entire spawn/timeout/redaction pipeline via a new `_spawn_and_parse()` private method, so a timed-out or credential-less `resume()` fails exactly like `execute()` does, and a captured transcript is redacted before return either way
- `capabilities()` now reports `native_resume=True`, replacing 07-01's honest `False` stub
- `tests/contract/test_coding_worker_contract.py::WORKER_FACTORIES` is now `[FakeWorker, ClaudeCodeWorker]`; an autouse fixture installs a fake `claude` executable on `PATH` plus obviously-fake credentials before any parametrized worker is constructed, so the whole suite (including a run with `ANTHROPIC_API_KEY` unset) proves the real adapter cannot drift from `FakeWorker`'s contract
- `.planning/WINDOWS.md` ledger entry #10 (the `resume()` stub opened by 07-01) is now `fixed`

## Task Commits

Each task was committed atomically (RED/GREEN pairs per `tdd="true"`):

1. **Task 1: A role can ask a human a question through the real CLI (D-01)**
   - `513d1d7` test(07-03): add failing tests for NEEDS_INPUT marker parsing (D-01)
   - `570ee3d` feat(07-03): parse the NEEDS_INPUT marker into WorkerResult(NEEDS_INPUT) (D-01)
2. **Task 2: A paused role resumes -- natively by session id, or by context reconstruction**
   - `1670ea2` test(07-03): add failing tests for resume() and capabilities() (HITL-04/05)
   - `5a972a7` feat(07-03): implement resume() and capabilities() (HITL-04, HITL-05, D-03)
3. **Task 3: The shared contract suite runs against the real adapter (QUAL-02)**
   - `319f736` feat(07-03): run the shared contract suite against ClaudeCodeWorker (QUAL-02)

**Plan metadata:** (this commit, see below)

_Note: Task 3 combined its RED and GREEN cycles into a single `feat` commit -- the new registry unit tests (`test_duplicate_registration_binds_exactly_one_factory`, `test_default_registry_claude_code_is_not_the_not_yet_implemented_worker`) pass with no production code change (`WorkerRegistry.register` already overwrites on re-registration), so there was no genuine RED state to commit separately; they are proof tests pinning existing correct behavior, not bug fixes. Tasks 1 and 2 each show a full `test(...)` -> `feat(...)` split with a genuine intentional RED (verified failing for the target assertion/import, not a collection error) before implementation._

## Files Created/Modified
- `src/dark_factory/workers/claude_code.py` -- `NEEDS_INPUT_MARKER`/`NEEDS_INPUT_PROTOCOL`/`_NEEDS_INPUT_RE`/`_extract_needs_input`, `RESUME_CONTINUATION_PROMPT`, `_context_prompt_sections`/`_build_resume_prompt`, `_spawn_and_parse`, `resume()`/`_resume()`, updated `capabilities()`
- `tests/unit/test_claude_code_worker.py` -- 15 new tests: 6 for D-01 marker parsing, 7 for resume()/capabilities(), 2 for duplicate registration
- `tests/contract/test_coding_worker_contract.py` -- `_fake_claude_cli_on_path` autouse fixture, `WORKER_FACTORIES = [FakeWorker, ClaudeCodeWorker]`, rewritten module docstring
- `tests/unit/test_worker_registry_names.py` -- `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` updated (see deviation below)

## Decisions Made
- D-01 marker regex: `MULTILINE` anchors to line-start so prose mentions never trigger a pause; `DOTALL` + `\Z` captures a multi-line question in one shot with no second delimiter -- both documented inline as load-bearing
- `_extract_needs_input` degrades an empty capture to "no marker" rather than an empty-string question, so the adapter never constructs a `WorkerResult` that would fail `WorkerResult._require_question_for_needs_input`'s validator from the inside
- Factored the entire spawn/timeout/redact/parse pipeline out of `_execute` into `_spawn_and_parse(argv, context)` so `resume()` reuses it verbatim rather than duplicating the `finally`-block redaction and never-raise wrapper -- the two entry points cannot drift
- `resume()`'s native branch treats `previous.worker_session_id` as a single opaque argv element -- never parsed, split or reformatted (HITL-04); the context-reconstruction branch rebuilds the prompt from `_context_prompt_sections(context)` (shared with the fresh-attempt prompt) plus the previous attempt's summary/questions/answer, with the clarification protocol appended last so a reconstructed attempt can pause again
- `capabilities()` now reports `native_resume=True`, the value 07-01 explicitly deferred to this plan

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_worker_registry_names.py` asserted the now-replaced placeholder behavior for `resume()`**
- **Found during:** Task 2 (implementing `resume()`)
- **Issue:** `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` (written in 07-01) asserted `worker.resume({}, None, None)` raises `NotImplementedError` naming `"07-03"` -- true of the stub this plan intentionally replaces, so the test now describes stale behavior rather than a real bug in new code.
- **Fix:** Updated the assertion to call `resume({}, None, None)`, expect no exception, and assert `status is WorkerResultStatus.FAILED` (the credential-gate outcome in that test's environment), matching the file's existing coverage style for `execute()`.
- **Files modified:** `tests/unit/test_worker_registry_names.py`
- **Verification:** `uv run pytest -m unit -q tests/unit/test_worker_registry_names.py` passes; full `unit`+`contract` suite (495 tests) green.
- **Committed in:** `5a972a7` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix in a pre-existing test).
**Impact on plan:** The fix was necessary and in-scope -- the stale test was directly invalidated by this plan's own `resume()` implementation. No scope creep.

### Deviation Note (not a Rule 1-4 code deviation)

**Task 3's `<verify>` `fails_when` threshold assumed a test count that doesn't match the file.** The plan text reads "fewer than 14 tests are collected (7 shared tests x 2 adapters, plus the non-parametrized validator test)" -- i.e. an expectation of >=15. The contract module actually defines 6 shared parametrized tests (`test_execute_returns_a_worker_result`, `test_execute_status_is_a_worker_result_status_member`, `test_worker_session_id_matches_capability_declaration`, `test_needs_input_result_carries_at_least_one_question`, `test_resume_returns_a_worker_result`, `test_resume_accepts_a_null_answer`) plus one intentionally non-parametrized validator (`test_a_needs_input_result_with_no_questions_cannot_be_constructed`) -- verified by `grep -n "^def test_"` against the file both before and after this plan's changes. The correct collected count is therefore `6*2+1=13`, which is exactly what both `pytest -m contract` runs (with and without `ANTHROPIC_API_KEY`) report. This is a planning-artifact miscount from plan authoring, not an implementation gap or a weakened test; no test was added, removed, or altered to chase the number, per the plan's own prohibition on weakening this suite.

## Issues Encountered
None beyond the deviation documented above.

## TDD Gate Compliance

| Task | RED commit | GREEN commit | Notes |
|------|-----------|--------------|-------|
| Task 1 | `513d1d7` | `570ee3d` | Full RED/GREEN split; RED verified as 4 genuine target-assertion/import failures (not collection errors) plus 2 tests correctly passing already (proving absence of premature behavior) |
| Task 2 | `1670ea2` | `5a972a7` | Full RED/GREEN split; RED verified as 7 genuine failures (`NotImplementedError` / capability assertion mismatch) |
| Task 3 | none (no genuine RED existed) | `319f736` | See TDD note above -- the two new registry tests already passed against unmodified production code; not a Rule 1-3 process gap |

## Known Stubs
None remaining from this plan. `.planning/WINDOWS.md` ledger entry #10 (`ClaudeCodeWorker.resume()` stub, opened by 07-01) is now `fixed`.

`--allowedTools` narrowing (Plan 07-04) remains the next planned extension to `_base_argv` -- not a stub, a forward-looking scope boundary this plan did not touch.

## User Setup Required
None -- no external service configuration required. A live `claude` CLI on `PATH` and a real `ANTHROPIC_API_KEY` are needed only for an actual integration-tier/production run; every automated test in this plan fakes both.

## Next Phase Readiness
- Plan 07-04 (`--allowedTools` narrowing) can proceed independently against this adapter -- `_base_argv` is the stated seam.
- Phase 8's `CopilotWorker`/`HermesWorker` can follow the same pattern: append to `WORKER_FACTORIES`, implement `resume()`/`capabilities()` against the same `CodingWorker` contract this plan proved holds for a real subprocess-spawning adapter.
- No blockers.

---
*Phase: 07-claude-code-the-first-real-worker*
*Completed: 2026-09-20*

## Self-Check: PASSED

All key files confirmed present on disk (`src/dark_factory/workers/claude_code.py`,
`tests/unit/test_claude_code_worker.py`, `tests/contract/test_coding_worker_contract.py`,
`tests/unit/test_worker_registry_names.py`). All five task commits (`513d1d7`, `570ee3d`,
`1670ea2`, `5a972a7`, `319f736`) confirmed present in `git log`. Full `unit`+`contract`
suite re-verified green (495 passed), `mypy --strict` and `ruff check` both exit 0, and
the plan's named guards (`tests/unit/test_no_worker_name_leak.py`,
`tests/unit/test_git_ownership_boundary.py`) pass. The plan-level `<verification>` block
(`pytest -m "unit or contract" -q`, `mypy src/dark_factory`, `ruff check .`) re-run clean.
