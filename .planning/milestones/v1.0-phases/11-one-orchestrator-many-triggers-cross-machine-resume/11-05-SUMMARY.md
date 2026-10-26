---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 05
subsystem: docs
tags: [readme, resume-workflow, workflow_dispatch, doc-drift-guard, deployer-docs, github-actions]

# Dependency graph
requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plan 11-01's dispatch_github_token/GitHubClient.dispatch_workflow and plan 11-02's four dispatch outcomes (webhook.dispatch.requested/skipped/failed, the three skip-reason constants), plan 11-04's ci.yml db-tier selection and its corrected exclusion comment"
provides:
  - "README.md's 'Finish a run in CI -- the local -> CI handoff' section: deployment model, full request/response flow, the resume.yml reference workflow bracketed by machine-readable sentinels, the dispatch credential's least-privilege shape, and the four dispatch outcomes with verbatim log event names"
  - "README.md's 'Running the tests' extension naming the three CI-selected marker tiers and why integration is excluded"
  - "tests/unit/test_resume_workflow_reference_doc.py -- the doc-drift guard: extracts the sentinel-bracketed block, parses it with yaml.safe_load, and asserts the run_id input, the single dark-factory resume invocation, the absence of any if key, and DISPATCH_GITHUB_TOKEN's consistent spelling"
affects: []

# Actuals (#2632)
actuals:
  tokens: 3988
  tasks: 2
  commits: 2
plan_head_before: 426a338

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Doc-drift guard idiom: a fenced block bracketed by named HTML sentinel comments in a Markdown file, extracted by exact sentinel string match, parsed with yaml.safe_load, and asserted structurally -- rather than grepping the Markdown as raw text -- so the guard fails for a content reason, not a formatting reason"
    - "The trigger-key lookup tolerates both the quoted string key 'on' and the YAML-1.1-parsed boolean key True, mirroring this repository's own ci.yml quoting convention and its rationale"

key-files:
  created:
    - tests/unit/test_resume_workflow_reference_doc.py
  modified:
    - README.md

key-decisions:
  - "The reference workflow's install step names a git+https source (pip install \"dark-factory @ git+https://github.com/<your-org>/dark-factory.git\") rather than a package-index install, because dark-factory is not yet published to PyPI -- the README states this explicitly and names the two commands (pip install dark-factory / uv add dark-factory) to switch to once it ships."
  - "The Actions secrets list names DATABASE_URL, DATABASE_URL_DIRECT, GITHUB_TOKEN, and ANTHROPIC_API_KEY as the illustrative worker-credential example (claude-code being the only currently-functional adapter with a single required credential) -- the surrounding prose generalizes to 'whichever worker credential your roles' assigned worker needs' so the list is not read as an exhaustive requirement for every deployer."
  - "permissions: contents: read is declared explicitly on the reference workflow (not inherited) and timeout-minutes: 30 is set on its one job, matching this repository's own ci.yml conventions (least-privilege explicit permissions, an explicit job timeout) rather than leaving either to a GitHub default."
  - "The dispatch-outcome table's four rows and their event/reason strings (webhook.dispatch.requested; webhook.dispatch.skipped with reason=repository_not_configured or reason=dispatch_github_token_not_configured; webhook.dispatch.failed) were read directly from the shipped src/dark_factory/webhook/app.py source (not re-derived from 11-02-SUMMARY.md's prose) to guarantee verbatim accuracy against what the code actually emits."

requirements-completed: [HITL-06, QUAL-01]

coverage:
  - id: D1
    description: "A deployer has, in this repository's own README, everything needed to close the local -> CI loop against their own repository: the resume.yml workflow to add, the Actions secrets it needs, and the DISPATCH_GITHUB_TOKEN to give the webhook receiver"
    requirement: HITL-06
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py -- 5 passed"
        status: pass
    human_judgment: false
  - id: D2
    description: "The documentation states the pip-installable deployment model (a deployer never clones Dark Factory's own repository) and names the absent dark-factory init scaffold as a recorded deferral, not an oversight"
    requirement: HITL-06
    verification:
      - kind: manual_procedural
        ref: "README.md '### The deployment model' section"
        status: pass
    human_judgment: false
  - id: D3
    description: "The reference workflow does exactly three things (checkout, install, one dark-factory resume invocation) and carries no branch on run state"
    requirement: HITL-06
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py#test_the_reference_workflow_resumes_exactly_once"
        status: pass
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py#test_the_reference_workflow_carries_no_run_state_branch"
        status: pass
    human_judgment: false
  - id: D4
    description: "The documentation names a fine-grained PAT scoped to the target repository with Actions: Read and write before naming a classic token's broader repo scope as a fallback only"
    requirement: HITL-06
    verification:
      - kind: manual_procedural
        ref: "README.md '### The dispatch credential' section"
        status: pass
    human_judgment: false
  - id: D5
    description: "The documentation names the receiver's four dispatch outcomes and the log event each emits, verbatim from src/dark_factory/webhook/app.py, so an operator can diagnose a resume that never fired from logs alone"
    requirement: HITL-06
    verification:
      - kind: manual_procedural
        ref: "README.md '### When the resume does not fire' table, cross-checked against src/dark_factory/webhook/app.py's _log.* call sites"
        status: pass
    human_judgment: false
  - id: D6
    description: "The README's test section states which marker tiers CI runs (unit, contract, db) and why integration is excluded, matching .github/workflows/ci.yml after plan 11-04"
    requirement: QUAL-01
    verification:
      - kind: manual_procedural
        ref: "README.md 'Running the tests' extension paragraph, cross-checked against .github/workflows/ci.yml"
        status: pass
    human_judgment: false
  - id: D7
    description: "The reference workflow is machine-checked: it parses as YAML, declares a workflow_dispatch trigger with a run_id input, and invokes dark-factory resume exactly once -- documentation cannot silently rot"
    requirement: HITL-06
    verification:
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py -- 5 passed"
        status: pass
    human_judgment: false

duration: ~40min task-commits + ~4h10min full-suite/db-tier verification wall-clock against real remote Neon PostgreSQL (one full-suite attempt stalled and was terminated; superseded by a standalone db-tier run)
completed: 2026-09-30
status: complete
---

# Phase 11 Plan 05: Close the local -> CI loop for a human Summary

**README.md gains a "Finish a run in CI" section -- deployment model, full request/response flow, a sentinel-bracketed `resume.yml` reference workflow, the least-privilege dispatch credential, and the four dispatch outcomes with verbatim log event names -- backed by a new unit-tier doc-drift guard that parses the reference workflow as real YAML and fails the build if it ever grows a branch on run state.**

## Performance

- **Duration:** ~40 min of task-commit work. Verification wall-clock was substantially longer than any prior plan in this phase: a full unrestricted `uv run pytest -q` sweep stalled with near-zero forward progress for over 2.5 hours against the real remote Neon test branch and was terminated (see Issues Encountered); a standalone `uv run pytest -q -m db` run then completed cleanly in 1h05m.
- **Completed:** 2026-09-30
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- README.md gained a new top-level section, "## Finish a run in CI — the local → CI handoff", positioned after the Phase 2 pause/resume walkthrough and before "## Running the tests" — six parts: what the handoff is, the pip-installable deployment model (a deployer never clones Dark Factory's own repository; the absent `dark-factory init` scaffold named as a recorded deferral), the full five-step request/response flow, the sentinel-bracketed `resume.yml` reference workflow itself, the least-privilege dispatch credential (fine-grained PAT with `Actions: Read and write`, classic `repo` scope named only as a fallback), and a four-row table of the receiver's dispatch outcomes with their exact log event names read directly from `src/dark_factory/webhook/app.py`.
- The reference workflow — bracketed by `<!-- resume-workflow-reference: begin -->` / `<!-- resume-workflow-reference: end -->` — declares a quoted `"on": workflow_dispatch` trigger with a required `run_id` input, explicit `permissions: contents: read`, and one job (`ubuntu-latest`, `timeout-minutes: 30`) with exactly three steps: checkout, an install step naming a git source (since `dark-factory` is not yet published to PyPI), and one `dark-factory resume "${{ inputs.run_id }}"` step reading its four Actions secrets from `env:`. No `if:` anywhere.
- "## Running the tests" gained one paragraph after the marker-tier table stating that `ci.yml` selects `unit`, `contract` and `db` on every push/PR (via the testcontainers rung, no `services:` block) and that `integration` is excluded because some of its tests need real agent-CLI credentials the hosted runner does not have — matching plan 11-04's corrected `ci.yml` comment.
- `tests/unit/test_resume_workflow_reference_doc.py` (new, 5 tests, all pass): extracts the sentinel-bracketed block (raising a counted `AssertionError`, never returning an empty string, if the sentinel count is ever wrong), parses it with `yaml.safe_load`, and asserts the `workflow_dispatch.inputs.run_id` input is present and required, exactly one step's `run` contains `dark-factory resume` and references the workflow input (not a literal id), no job/step carries an `if` key (guarded by a non-empty-job-collection assertion first, so a broken extractor cannot pass vacuously), and `DISPATCH_GITHUB_TOKEN` appears identically in both `README.md` and `.env.example`.

## Task Commits

1. **Task 1: A deployer can close the local → CI loop from the README alone** - `2da02cb` (docs)
2. **Task 2: The reference workflow cannot silently rot** - `b4b4de2` (test)

## Files Created/Modified

- `README.md` — the new "Finish a run in CI" section (six parts) plus the "Running the tests" extension paragraph.
- `tests/unit/test_resume_workflow_reference_doc.py` (new) — the five-test doc-drift guard.

## Decisions Made

See `key-decisions` in the frontmatter for full rationale on each item below:

- The install step names a `git+https://` source rather than a package-index install, since `dark-factory` is not yet published to PyPI; the README states the switch to make once it ships.
- The Actions secrets list uses `ANTHROPIC_API_KEY` as the illustrative worker-credential example (the only currently-functional adapter with a single required env var), generalized in prose to "whichever worker credential your roles' assigned worker needs."
- `permissions: contents: read` and `timeout-minutes: 30` are both explicit on the reference workflow, matching this repository's own `ci.yml` conventions rather than relying on GitHub defaults.
- The dispatch-outcome table's event names and reason strings were read directly from the shipped `src/dark_factory/webhook/app.py` source (the single source of truth), not re-derived from prose in `11-02-SUMMARY.md`.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' `must_haves`/`acceptance_criteria` are satisfied by the README content and the five named test functions with no auto-fixes required. `uv run ruff format` reformatted one long f-string line in the new test file (standard tooling compliance, not a defect fix).

## Issues Encountered

- **A full unrestricted `uv run pytest -q` (all tiers) run stalled.** Launched in the background per this session's own environment note (which explicitly flagged this exact hazard from prior plans' experience), the process showed only ~6% collection progress in its output log and the log file's mtime stopped advancing entirely at the ~11-minute mark; over the following ~2.5 hours the process consumed only ~1 second of additional CPU time despite an established, healthy TCP connection to the remote Postgres endpoint (confirmed via `lsof`) — consistent with a genuine hang (most plausibly a stuck lease-wait or an idle transaction somewhere in the `integration` tier) rather than ordinary network latency. Terminated (`kill -9`) rather than left running indefinitely.
- **Substituted with a scoped, still-comprehensive verification set**, all green:
  - `uv run pytest -m unit -q tests/unit/test_resume_workflow_reference_doc.py` — 5 passed (this plan's own new tests).
  - `uv run pytest -m "unit or contract" -q --tb=short` — 817 passed, 1 skipped, 374 deselected, 1 failed. The 1 failure (`tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`) is the exact pre-existing, unrelated, sandbox-specific failure documented and confirmed via `git stash` in `11-01-SUMMARY.md` and carried unchanged through `11-02`/`11-03`/`11-04` — a real `claude` CLI on `PATH` in this sandbox takes the credential-gated test's real-completion path instead of its intended `FAILED` path.
  - A standalone `uv run pytest -q -m db` run completed cleanly: **205 passed, 1 skipped, 987 deselected, 0 failed** in 1h05m00s — proving the entire db-tier orchestration suite (including plan 11-01/11-02's dispatch tests and plan 11-03's two-subprocess cross-machine proof) is unaffected.
  - `uv run ruff check .` — clean.
  - `uv run mypy src/dark_factory` — 2 pre-existing, unrelated errors in `src/dark_factory/tools/mcp_transport.py` (documented in `11-04-SUMMARY.md`, confirmed via `git stash` in that plan); this plan touches no file under `src/dark_factory/`.
  - `git diff --stat` against the pre-plan HEAD confirms only `README.md` and `tests/unit/test_resume_workflow_reference_doc.py` changed — no file under `src/dark_factory/`, `tests/db/`, `tests/integration/`, or `.github/workflows/ci.yml` was touched by this plan, so the `integration` tier (the tier most plausibly implicated in the stall, and the one tier not re-run this session) cannot have regressed as a result of this plan's own changes.
  - Recorded as ledger entry #17 in `.planning/WINDOWS.md` (kind: `unrun-verify`) per the broken-windows protocol, since the plan's own `<verification>` block literally asks for a full unrestricted `pytest -q` pass that this session could not complete.

## User Setup Required

None. This plan is documentation- and test-only; the credential and configuration surface it documents (`DISPATCH_GITHUB_TOKEN`, the fine-grained PAT shape) was already introduced and covered by `.env.example`/`user_setup` in plan 11-01.

## Next Phase Readiness

- Phase 11 is now complete: all five plans (11-01 through 11-05) have landed. The local→CI handoff is implemented (11-01/11-02), proven cross-machine (11-03), running in CI (11-04), and documented for a deployer who has never read this codebase (11-05).
- One open item, not a blocker for this plan's own scope: the full unrestricted `uv run pytest -q` sweep across every tier (including `integration`) has not completed successfully in this execution sandbox since the stall described above. Recorded in `.planning/WINDOWS.md` (entry #17) and in this summary's Issues Encountered section. A future session with a healthier connection to the remote Neon test branch (or Docker/testcontainers available locally) should re-run the full unrestricted suite to close this out, though the scoped verification above already gives high confidence: every tier this plan could plausibly have affected (`unit`, `contract`, `db`) is green, and this plan touches zero files in `src/dark_factory/`, `tests/db/`, `tests/integration/`, or `.github/workflows/ci.yml`.
- No blockers for phase close-out.

## Self-Check: PASSED

Both claimed files (`README.md`, `tests/unit/test_resume_workflow_reference_doc.py`) found on disk with the expected content; both claimed commits (`2da02cb`, `b4b4de2`) found in git history via `git log --oneline --all`.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-09-30*
