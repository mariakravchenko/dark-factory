---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 07
subsystem: docs
tags: [documentation, worker-runtime, resume-workflow, drift-guard, gap-closure]

requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "11-05's reference resume.yml block and its sentinel-bracketed doc-drift guard (test_resume_workflow_reference_doc.py); 08-01/08-02's real CopilotWorker/HermesWorker adapters and tests/support/live_runtime.py's LIVE_RUNTIMES registry"
provides:
  - "README 'Finish a run in CI' section states the worker-runtime requirement at the copy-paste site: a deployment-model list item, commented install guidance inside the reference block, and a new 'The worker runtime' subsection with a binary/credential table"
  - "A parametrized drift guard deriving required binary/credential names from LIVE_RUNTIMES, so a fourth worker adapter fails the unit tier until README documents it"
affects: [11-ship, future-worker-adapters, deployer-onboarding]

actuals:
  tokens: 2800
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Doc-drift guards derive expected strings from the registry (LIVE_RUNTIMES) via pytest parametrization rather than restating them by hand, so registering a new adapter fails the guard until documentation catches up"
    - "Supply-chain-sensitive guidance in a copy-paste reference artifact is included as a fully-commented step (name + run lines both commented) rather than omitted or made live -- present at the point of need, inert on paste, no invented install command"

key-files:
  created: []
  modified:
    - README.md
    - tests/unit/test_resume_workflow_reference_doc.py

key-decisions:
  - "Resolved G-11-2's open scope question as 'both, commented': the reference resume.yml block carries an inert, fully-commented install step at the exact point a deployer needs it, plus prose explaining why it is commented -- not prose-only (already failed once) and not an active step (would hardcode one worker runtime against CLAUDE.md's Role != Worker constraint and D-04's reference-content framing)"
  - "Named no third-party install command, package, or registry for any runtime (T-11-28) -- the table and guidance name only the PATH binary, derived from LIVE_RUNTIMES, and point to that runtime's own documentation"
  - "Test C (install-guidance-precedes-resume) keys on the stable substring 'Install the worker runtime' (the commented step's own -name: line) matched by line-index comparison on raw block text, not parsed YAML, because yaml.safe_load discards comments -- chosen so ordinary comment rewording doesn't break the guard but deleting/renaming the step does"
  - "LIVE_RUNTIMES (claude-code, copilot, hermes) is confirmed the complete set of registered worker runtimes needing documentation: default_registry (src/dark_factory/workers/registry.py) registers exactly four names -- fake, claude-code, copilot, hermes -- and LIVE_RUNTIMES covers all three real adapters, deliberately excluding 'fake' which needs neither a binary nor a credential. WorkerRegistry names no runtime that LIVE_RUNTIMES omits."

requirements-completed: [TRIG-04, HITL-06]

coverage:
  - id: D1
    description: "README's 'Finish a run in CI' section names, for every worker runtime in LIVE_RUNTIMES, the PATH binary and credential environment variable"
    requirement: "TRIG-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py::test_the_ci_handoff_section_names_every_worker_binary[claude-code|copilot|hermes]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py::test_the_ci_handoff_section_names_every_worker_credential[claude-code|copilot|hermes]"
        status: pass
    human_judgment: false
  - id: D2
    description: "The reference block carries commented worker-runtime install guidance positioned before the dark-factory resume step, naming no third-party install command/package/registry"
    requirement: "TRIG-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py::test_the_install_guidance_precedes_the_resume_step"
        status: pass
    human_judgment: false
  - id: D3
    description: "The reference block still parses as YAML, still declares a required run_id input, still invokes dark-factory resume exactly once, and still carries no if: key (pre-existing guards unaffected)"
    requirement: "TRIG-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py (5 pre-existing assertions, unchanged)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The section extractor is proven non-vacuous (a silently-empty section would make the binary/credential checks pass against nothing)"
    requirement: "TRIG-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py::test_the_ci_handoff_section_extractor_is_non_vacuous"
        status: pass
    human_judgment: false
  - id: D5
    description: "A real deployer on a real target repository can copy the corrected reference block, follow the new worker-runtime subsection, and have dark-factory resume advance the run past BA instead of recording a FAILED role execution with an errno-2 binary-not-found error"
    requirement: "HITL-06"
    verification: []
    human_judgment: true
    rationale: "Requires re-running UAT test 2's live path against a real GitHub repository and Actions runner -- the automated guards above prove the README and LIVE_RUNTIMES registry agree with each other, not that a real runner equipped per the new guidance can execute a role. The plan's own <verify> block designates this a <human-check>."

duration: 9min
completed: 2026-10-01
status: complete
---

# Phase 11 Plan 07: Worker-Runtime Documentation for the CI Handoff Summary

**README's reference `resume.yml` now names, at the copy-paste site, the worker-runtime binary and credential every registered adapter needs — closing the gap where a live run dispatched and authenticated correctly, then failed with an undocumented errno-2 "no such file or directory".**

## Performance
- **Duration:** 9min
- **Started:** 2026-10-01T07:20:37Z
- **Completed:** 2026-10-01T07:29:21Z
- **Tasks:** 2 completed
- **Files modified:** 2 (README.md, tests/unit/test_resume_workflow_reference_doc.py)

## Accomplishments
- README's "Finish a run in CI" section now states the worker-runtime requirement in three places: a fifth deployment-model list item, a commented-out install step inside the reference `resume.yml` block positioned between "Install dark-factory" and "Resume the run", and a new "### The worker runtime" subsection carrying a table of every registered worker's `PATH` binary and credential environment variable.
- `tests/unit/test_resume_workflow_reference_doc.py` gained a drift guard that derives its expectations from `tests/support/live_runtime.py`'s `LIVE_RUNTIMES` by parametrization — a fourth worker adapter will fail the unit tier until its binary and credential are documented, rather than silently rotting the way this gap did.
- G-11-2's deliberately-open scope question (prose-only vs. an active install step vs. a commented one) is resolved as "both, commented": the install guidance lives at the exact point a deployer needs it, is inert on paste, and names no third-party install command, package, or registry (T-11-28).

## Task Commits
1. **Task 2 (RED): failing tests for worker-runtime documentation guard** - `1a49301` (test)
2. **Task 1 (GREEN): document worker-runtime requirements in README** - `8a92a8e` (feat)
3. **Task 2 (REFACTOR): apply ruff formatting to the drift-guard tests** - `2b8edc8` (refactor)

Executed in TDD order per the plan's own ordering note: Task 2's new assertions were written and confirmed RED against the unmodified README first (Tests A/B failed for `copilot`/`hermes` binaries and `copilot`'s credential; Test C failed because no install guidance existed yet), then Task 1's README edit turned them GREEN, then a `ruff format` pass on the test file (REFACTOR) made `ruff format --check .` clean for the files this plan touches.

## Files Created/Modified
- `README.md` — Added deployment-model item 5 (worker-runtime availability), commented install-guidance step inside the reference `resume.yml` block, and a new "### The worker runtime" subsection with the binary/credential table, placed before "### The dispatch credential".
- `tests/unit/test_resume_workflow_reference_doc.py` — Added `_ci_handoff_section()` helper plus module-level heading constants; added `test_the_ci_handoff_section_extractor_is_non_vacuous`, parametrized `test_the_ci_handoff_section_names_every_worker_binary` / `..._credential` over `LIVE_RUNTIMES`, and `test_the_install_guidance_precedes_the_resume_step`. All 5 pre-existing tests unchanged and still pass.

## Load-Bearing Details (per plan's `<output>` instructions)

**Test C's load-bearing substring:** `"Install the worker runtime"` — the `- name:` line of the commented-out install step in README's reference block. `test_the_install_guidance_precedes_the_resume_step` matches this as a substring of a line (not whole-line equality) against the raw extracted block text (not parsed YAML, since `yaml.safe_load` discards comments), so ordinary rewording of the step's explanatory comments does not break the guard, but deleting the step or renaming it away from "worker runtime" does. Recorded in the test's own docstring for the next README editor.

**Worker-runtime table shape and registry completeness:** The table has three rows (`claude-code` → `claude` / `ANTHROPIC_API_KEY`; `copilot` → `copilot` / `COPILOT_GITHUB_TOKEN`; `hermes` → `hermes` / `ANTHROPIC_API_KEY`, noted as shared with `claude-code` since Hermes has no dedicated credential) plus a parenthetical note that `fake` needs neither. Confirmed by reading `src/dark_factory/workers/registry.py`: `default_registry` registers exactly four names — `fake`, `claude-code`, `copilot`, `hermes` — and `LIVE_RUNTIMES` covers all three real adapters. `LIVE_RUNTIMES` is the complete set of registered worker runtimes needing documentation; `WorkerRegistry` names no runtime that `LIVE_RUNTIMES` omits.

**G-11-2's scope question resolution:** Resolved as "both, commented" (as the gap context anticipated but deliberately left to this plan). Prose-only was the approach that already failed once (the credential paragraph existed and the deployer still hit the errno-2 failure). An active, uncommented install step would hardcode one agent runtime into a worker-agnostic block, against CLAUDE.md's "Role != Worker" constraint and D-04's framing of `resume.yml` as reference content Dark Factory's own CI does not enforce. A fully-commented step (both its `- name:` and `run:` lines prefixed with `#`) sits exactly where the deployer is pasting, is inert, and leaves every pre-existing structural guard satisfied — a YAML comment is not a step, so "exactly one `dark-factory resume` step" and "zero `if:` keys" both still hold.

## Decisions Made
See `key-decisions` in frontmatter. No decisions required escalation (Rule 4) — all were already resolved by the plan's gap context and threat model.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - formatting] `ruff format` reformatted two lines in the new test file**
- **Found during:** Task 2's final verification pass (`ruff format --check .`)
- **Issue:** A long parametrize-decorated function signature and a long list-comprehension line in the newly-added test code exceeded the line-length the project's `ruff format` enforces.
- **Fix:** Ran `ruff format tests/unit/test_resume_workflow_reference_doc.py`; re-ran the 13 tests to confirm no behavior change.
- **Files modified:** `tests/unit/test_resume_workflow_reference_doc.py`
- **Verification:** `uv run ruff format --check tests/unit/test_resume_workflow_reference_doc.py` clean; `uv run pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` — 13 passed.
- **Commit:** `2b8edc8`

**Total deviations:** 1 auto-fixed (1 formatting, Rule 1).
**Impact on plan:** None — purely cosmetic, no behavior change, isolated to the file this plan already modifies.

### Out-of-Scope Discoveries (not fixed, logged)

**`tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this sandbox.** The test assumes no `ANTHROPIC_API_KEY`/`claude` binary are configured in the test environment and asserts a `FAILED` result; this sandbox has both configured, so `ClaudeCodeWorker.execute({})` makes a real live call and returns `COMPLETED`. Unrelated to this plan's files (README.md, test_resume_workflow_reference_doc.py) and pre-existing. Logged to `.planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/deferred-items.md` per the scope-boundary rule; not fixed. `mypy src/dark_factory` also reports 2 pre-existing import-not-found errors in `src/dark_factory/tools/mcp_transport.py` (last touched in phase 06), and `ruff format --check .` lists 19 other pre-existing unformatted files outside this plan's scope — neither touched.

## Issues Encountered
None beyond the deviation and out-of-scope items documented above.

## User Setup Required
None — no external service configuration required. The plan's `<human-check>` (re-running UAT test 2's live path against a real target repository and GitHub Actions runner) is recorded as coverage item D5, requiring human judgment, and is deferred to the phase's own verification/UAT step rather than performed inline here.

## Next Phase Readiness
G-11-2 is closed: README's reference `resume.yml` no longer silently omits the worker-runtime requirement, and a registry-derived drift guard prevents the documentation from rotting as new adapters are added. This was the last incomplete plan in Phase 11 — phase 11 execution is complete and ready for verification (`/gsd-verify-work`), including re-running UAT test 2's live path per coverage item D5.

## TDD Gate Compliance
All three gates present and correctly ordered: RED (`1a49301`, `test(11-07): ...`) before GREEN (`8a92a8e`, `feat(11-07): ...`) before REFACTOR (`2b8edc8`, `refactor(11-07): ...`). RED was genuine: 4 of 13 assertions failed against the unmodified README for the intended reason (missing `copilot`/`hermes` binary mentions, missing `copilot` credential, missing install guidance) — not a collection error, fixture crash, or unrelated failure.

## Self-Check: PASSED

- FOUND: README.md
- FOUND: tests/unit/test_resume_workflow_reference_doc.py
- FOUND: commit 1a49301 (test(11-07): add failing tests for worker-runtime documentation guard)
- FOUND: commit 8a92a8e (feat(11-07): document worker-runtime requirements in README)
- FOUND: commit 2b8edc8 (refactor(11-07): apply ruff formatting to the drift-guard tests)

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-10-01*
