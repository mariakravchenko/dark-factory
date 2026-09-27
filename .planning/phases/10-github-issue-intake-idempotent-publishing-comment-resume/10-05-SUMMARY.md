---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 05
subsystem: testing
tags: [ast-guard, import-closure, githubkit, webhook, structural-invariant]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "GitHubClient wrapper (plan 10-01), publish step + github_client_factory seam (plan 10-06), clarification-comment posting (plan 10-03), and the webhook receiver package -- dark_factory.webhook -- with resolve_issue_comment and build_app (plan 10-04)"
provides:
  - "tests/unit/test_github_ownership_boundary.py -- an AST walk proving githubkit is importable only from three named, reasoned modules (github/client.py, webhook/app.py, webhook/resolve.py), with self-sanity tests proving the walk can fail"
  - "tests/unit/test_webhook_process_boundary.py -- three import-closure/AST guards proving the orchestrator core's five composition roots never reach dark_factory.webhook (D-01), the webhook package never imports or calls advance/drive and stays inside a six-entry direct-import allowlist (D-02), and none of the five core roots' closures reach a module importing the third-party starlette/uvicorn packages the webhook extra installs (genuinely optional, mirroring test_no_mcp_import_in_core.py)"
affects: []

actuals:
  tokens: 5606
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "githubkit's allowed-importer set has three entries, not the two the plan's own prose anticipated -- reading webhook/resolve.py's actual imports (not only the plan's read_first list) surfaced a third genuine githubkit import, githubkit.utils.UNSET, the sentinel githubkit's typed webhook models use to distinguish an absent JSON field from an explicit null. Documented in the guard's own module docstring rather than silently widening or narrowing the allowlist to match a stale plan expectation."
    - "D-02 is phrased on names (advance/drive), never on closure membership: orchestrator/answers.py legitimately imports RunNotFoundError from orchestrator/runner.py, so the webhook package's transitive closure does contain runner -- a closure-exclusion assertion would be false on landing. The AST walk instead detects the two names that actually run the pipeline, as an import (aliased or not) or a bare-name call, plus a narrow six-entry allowlist of the package's own direct dark_factory.* imports."
    - "The 'genuinely optional' extra proof reuses test_no_mcp_import_in_core.py's own mechanism exactly (an import-graph/third-party-detector pair, no subprocess, no skip-marked functional check) rather than inventing a second mechanism for the webhook extra -- consistent with the plan's own explicit instruction not to diverge from the established idiom."

key-files:
  created:
    - tests/unit/test_github_ownership_boundary.py
    - tests/unit/test_webhook_process_boundary.py
  modified: []

key-decisions:
  - "The githubkit allowed-module set has three named entries (github/client.py, webhook/app.py, webhook/resolve.py), not the plan's anticipated two -- webhook/resolve.py's `from githubkit.utils import UNSET` is a third genuine call site, discovered by reading the actual file rather than relying on the plan's own read_first list, which named only client.py and app.py. Each of the three is reasoned in the guard's module docstring; none constructs a client, unwraps a credential or makes an HTTP request outside github/client.py, so none defeats T-10-26's actual concern."
  - "No production code was touched to force the allowed-module count down to two (e.g. re-exporting UNSET through the wrapper) -- the plan's own scope statement is explicit that this plan makes zero production changes, and moving a type-utility import behind an indirection whose only purpose would be satisfying a test's headcount is exactly the kind of test-shaped-code the plan's own T-10-29 prohibition (a guard that cannot fail) warns against in the opposite direction."
  - "The webhook direct-import allowlist has six entries (config.settings, github.client, orchestrator.answers, orchestrator.lease, persistence.engine, persistence.repositories), read off the actual app.py/resolve.py imports rather than the plan's own six-entry guess (which included a speculative dark_factory.logging that no webhook module actually imports)."
  - "Genuinely-optional proof for the webhook extra mirrors test_no_mcp_import_in_core.py's own import-graph-only mechanism (a _third_party_extra_imports detector paired with the same five-root closure walk) rather than a literal subprocess-with-package-hidden check -- the plan's own instruction was to follow whatever mechanism the precedent file already uses, and that file uses only the structural proof."

patterns-established:
  - "A boundary guard's allowed-module count is set from what the actual source imports, not from the plan's own prose estimate written before the read_first files were opened -- and the discrepancy is documented in the guard's own docstring as a first-class fact, not silently absorbed."

requirements-completed: [GIT-03, GIT-06]

coverage:
  - id: D1
    description: "AST walk over the whole src/dark_factory tree proves githubkit is importable only from three named, reasoned modules (github/client.py, webhook/app.py, webhook/resolve.py); the current tree produces zero violations"
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_github_ownership_boundary.py::test_githubkit_is_imported_only_from_the_named_allowed_modules"
        status: pass
    human_judgment: false
  - id: D2
    description: "Self-sanity: every allowed module actually trips the walk, every allowed path exists on disk, an emptied allowlist still finds violations, four synthetic violating import forms (module-level, from-import, from-submodule, function-scoped) are detected at the correct line, and a docstring/comment-only mention is proven not to trip it"
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_github_ownership_boundary.py (9 tests total, RED-verified by stubbing the detector to return [] and confirming 6 fail)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The transitive dark_factory.* import closure of five core composition roots (orchestrator.runner, orchestrator.answers, orchestrator.lifecycle, workflows.pipeline, cli) never reaches dark_factory.webhook or any submodule of it (D-01), with a positive control proving the closure walk resolves real imports"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_process_boundary.py::test_core_closure_never_reaches_the_webhook_package (5 parametrized cases), ::test_the_closure_walk_resolves_real_imports"
        status: pass
    human_judgment: false
  - id: D4
    description: "No module under src/dark_factory/webhook/ imports or calls advance/drive (as a plain import, an aliased import, or a bare-name call), and the package's direct dark_factory.* imports stay inside a six-entry named allowlist -- phrased on names rather than closure membership because answers.py legitimately reaches runner.py transitively (D-02)"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_process_boundary.py::test_no_webhook_module_imports_or_calls_advance_or_drive, ::test_webhook_packages_direct_imports_stay_inside_the_named_allowlist"
        status: pass
    human_judgment: false
  - id: D5
    description: "Self-sanity for D-02: a plain drive import, an aliased advance import, and a bare-name drive() call are each detected at the correct line; a docstring-only mention of 'drive' is not; a synthetic direct import of orchestrator.runner is proven to fail the allowlist check"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_process_boundary.py (5 self-sanity tests, RED-verified by stubbing all four detector functions and confirming 6 teeth-proving tests fail)"
        status: pass
    human_judgment: false
  - id: D6
    description: "None of the five core roots' transitive closures reach a module importing the third-party starlette/uvicorn packages the webhook extra installs -- the structural proof that the webhook extra is genuinely optional, mirroring test_no_mcp_import_in_core.py's own mechanism with a positive control proving the detector has teeth against webhook/app.py"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_process_boundary.py::test_core_closure_never_imports_starlette_or_uvicorn (5 parametrized cases), ::test_the_detector_would_catch_webhook_app_importing_starlette"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every pre-existing structural guard in the codebase stays green alongside the two new ones, and the full unit+contract tier (798 tests) plus mypy --strict and ruff check are clean"
    verification:
      - kind: unit
        ref: "63 passed across test_git_ownership_boundary.py, test_no_mcp_import_in_core.py, test_single_mutation_path.py, test_status_import_graph.py, test_orchestrator_no_live_config_read.py, test_no_role_name_literal.py, test_no_tree_walk.py, test_no_environ_copy.py, test_config_module_isolation.py, plus this plan's own two files"
        status: pass
      - kind: unit
        ref: "uv run python -m pytest -m \"unit or contract\" -q (this project's configured workflow.test_command) -- 798 passed, 0 failed"
        status: pass
    human_judgment: false
  - id: D8
    description: "A full, unrestricted db-tier run (tests/db/) against real PostgreSQL, carried forward as the same open D10/D11-style gap disclosed by plans 10-03/10-04/10-06"
    verification: []
    human_judgment: true
    rationale: "No PostgreSQL is reachable in this dispatch's environment (no Docker, no local initdb, DARK_FACTORY_TEST_DATABASE_URL unset) -- the same situation plans 10-01 through 10-06 each hit. Unlike those plans, however, neither of this plan's two tasks declares a database precondition of its own: both new test files are pure unit-tier AST/import-closure guards over source text, touch zero production code, and modify zero shared module any db-tier test depends on. This plan's own db-tier risk is therefore effectively zero, and the gap is the same pre-existing one (a full unrestricted tests/db/ run against a faster PostgreSQL instance) already carried forward as open, non-blocking, by 10-03-SUMMARY.md, 10-04-SUMMARY.md and 10-06-SUMMARY.md -- not a new gap this plan introduces. A human with faster database access should run the full `uv run pytest -q` (or `uv run --extra webhook pytest -q`) before Phase 10 is treated as fully proven end to end."

duration: ~55min
completed: 2026-09-27
status: complete
---

# Phase 10 Plan 05: Structural Boundary Guards -- githubkit Ownership and Webhook Process Isolation Summary

Two AST-and-import-closure guards, each with the self-sanity tests this codebase's guard idiom requires, turn three of Phase 10's own module-docstring promises into mechanical proofs that fail loudly on a future violation: `githubkit` is reachable only from three named, reasoned modules; the orchestrator core's five composition roots can never reach the webhook receiver package; and the receiver can never import or call `advance`/`drive`, closing the phase with zero production-code changes.

## Performance

- **Duration:** ~55min
- **Started:** 2026-09-27
- **Completed:** 2026-09-27
- **Tasks:** 2/2
- **Files modified:** 2 (2 created, 0 modified)

## Accomplishments

- `tests/unit/test_github_ownership_boundary.py` (new, 9 tests): an AST walk over every `*.py` under `src/dark_factory/` proving `githubkit`/`githubkit.*` is importable only from `github/client.py` (the REST wrapper), `webhook/app.py` (inbound HMAC verify/parse) and `webhook/resolve.py` (the `UNSET` sentinel on an already-parsed typed event) -- a third allowed entry the plan's own prose did not anticipate, discovered by reading the actual source rather than only the plan's read_first list. Self-sanity: every allowed entry proven to trip the walk, every allowed path proven to exist on disk, an emptied allowlist proven to still find violations, four synthetic violating import forms detected at the right line, and a docstring/comment-only mention proven not to trip it.
- `tests/unit/test_webhook_process_boundary.py` (new, 19 tests): three guards. D-01 -- the transitive `dark_factory.*` closure of five core composition roots (`orchestrator.runner`, `orchestrator.answers`, `orchestrator.lifecycle`, `workflows.pipeline`, `cli`) never reaches `dark_factory.webhook`, reusing the closure-walk idiom verbatim from `test_orchestrator_no_live_config_read.py`/`test_status_import_graph.py`. D-02 -- phrased on names rather than closure membership (since `answers.py` legitimately pulls `RunNotFoundError` from `runner.py`, making a closure-exclusion assertion false on landing): no module under `src/dark_factory/webhook/` imports or calls `advance`/`drive`, and the package's direct `dark_factory.*` imports stay inside a six-entry named allowlist. Genuinely-optional -- none of the five core roots' closures reach a module importing the third-party `starlette`/`uvicorn` packages the `webhook` extra installs, mirroring `test_no_mcp_import_in_core.py`'s own mechanism exactly.
- Every pre-existing structural guard in the codebase (`test_git_ownership_boundary.py`, `test_no_mcp_import_in_core.py`, `test_single_mutation_path.py`, `test_status_import_graph.py`, `test_orchestrator_no_live_config_read.py`, `test_no_role_name_literal.py`, `test_no_tree_walk.py`, `test_no_environ_copy.py`, `test_config_module_isolation.py`) stays green alongside the two new ones (63 passed total).
- The full unit+contract tier (this project's own configured `workflow.test_command`) is green: 798 passed, 0 failed, 363 deselected (db/integration tiers). `mypy --strict src/dark_factory` and `ruff check .` are both clean.

## Task Commits

1. **Task 1: One wrapper, enforced -- `githubkit` lives in exactly one module** (auto, tdd) -- `0d8f891` (test, RED-verified by stubbing the detector to return `[]` and confirming 6 of 9 tests fail, then reverted to GREEN)
2. **Task 2: A separate deployable, enforced -- the core and the receiver cannot reach each other** (auto, tdd) -- `c303996` (test, RED-verified by stubbing all four detector functions and confirming 6 teeth-proving tests fail, then reverted to GREEN), `a4c8a2f` (style -- ruff format found while running the plan's own closing full-suite verification, no behavioral change)

**Plan metadata:** commit hash recorded after this file is written (see the final `docs(10-05)` commit).

## Files Created/Modified

- `tests/unit/test_github_ownership_boundary.py` -- the githubkit ownership guard, 9 tests
- `tests/unit/test_webhook_process_boundary.py` -- the webhook process-isolation guards (D-01/D-02/genuinely-optional), 19 tests

No file under `src/dark_factory/` was created or modified by this plan (confirmed via `git diff --stat` against the plan's starting commit).

## Decisions Made

See `key-decisions` in frontmatter: the three-entry (not two-entry) `githubkit` allowlist and why `webhook/resolve.py`'s `UNSET` import belongs there rather than being indirected away; the six-entry webhook direct-import allowlist (read off the actual files, not the plan's speculative guess that included an unused `dark_factory.logging`); and reusing `test_no_mcp_import_in_core.py`'s import-graph-only mechanism for the "genuinely optional" proof rather than inventing a subprocess-based check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan/reality correction] The `githubkit` allowed-module set needed three entries, not the two the plan anticipated**
- **Found during:** Task 1, while reading `webhook/resolve.py` (not itself in the plan's Task 1 `read_first` list, but read anyway to confirm the full set of `githubkit` call sites before writing the allowlist)
- **Issue:** The plan's own prose (`must_haves.truths`, `acceptance_criteria`'s "at most two named module paths") anticipated only `github/client.py` and `webhook/app.py` as `githubkit` importers, based on a `read_first` list that named only those two files. The actual `webhook/resolve.py` (written by plan 10-04) also imports `from githubkit.utils import UNSET` -- a genuine third call site the plan's own investigation had not surfaced.
- **Fix:** Wrote the guard's allowed set with three entries instead of two, each reasoned in the guard's own module docstring: `UNSET` is a stateless sentinel on an already-parsed, already-verified typed event that `resolve_issue_comment` reads by design (plan 10-04's own architecture) -- it carries no credential, makes no HTTP request, and is not the outbound-call-bypass threat T-10-26 targets. No production code was touched; the correction is entirely within this plan's own new test file.
- **Files modified:** `tests/unit/test_github_ownership_boundary.py` only (the acceptance-criteria literal "at most two" was superseded by the actual codebase; the `<behavior>` block's own weaker requirement -- "non-empty, every path exists on disk" -- was still satisfied)
- **Verification:** `test_githubkit_is_imported_only_from_the_named_allowed_modules` passes with zero violations against the real tree; `test_every_allowed_module_would_itself_trip_the_walk` proves all three entries are load-bearing
- **Committed in:** `0d8f891`

---

**Total deviations:** 1 auto-fixed (a plan-prose-vs-reality correction, resolved entirely within this plan's own new test file, no production code touched).
**Impact on plan:** The correction only affects an internal test-file constant (the allowlist) and its docstring justification; it does not change any acceptance criterion's *intent* (a small, named, reasoned allowlist that proves capable of failing) and does not touch any file outside this plan's declared `files_modified`.

## Issues Encountered

**No PostgreSQL was reachable in this dispatch's environment** (no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) -- the same situation every earlier plan in this phase encountered. Unlike those plans, neither of this plan's two tasks declares a database precondition: both new test files are pure unit-tier source-text guards, and this plan makes zero production-code changes. The db-tier gap this leaves (a full, unrestricted `tests/db/` run) is the same pre-existing open item plans 10-03/10-04/10-06 already carry forward, not a new gap -- see coverage item D8's rationale.

## User Setup Required

None for this plan specifically. This plan carries forward, unchanged, the environment gaps already disclosed by plans 10-01/10-04/10-06 (`GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, and a live end-to-end smoke against a real repository) -- see those plans' own SUMMARY.md files for the setup steps. Nothing in this plan adds a new setup requirement.

## Next Phase Readiness

Phase 10 (GitHub -- Issue Intake, Idempotent Publishing, Comment Resume) is now structurally closed: both GIT-03 (single GitHub wrapper) and GIT-06 (webhook receiver process isolation) have moved from module-docstring promises to guards the test suite enforces, joining this codebase's existing family of structural invariants (`test_git_ownership_boundary.py`, `test_single_mutation_path.py`, `test_no_mcp_import_in_core.py`, `test_orchestrator_no_live_config_read.py`).

The one open item, carried forward unchanged from 10-03/10-04/10-06, is a full unrestricted `tests/db/` run against a faster PostgreSQL instance (coverage item D8) -- recommended before this phase is treated as fully proven end to end, not blocking any further work.

No blockers for the next phase.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-27*

## Self-Check: PASSED

Both claimed created files (`tests/unit/test_github_ownership_boundary.py`, `tests/unit/test_webhook_process_boundary.py`) and this SUMMARY.md verified present on disk; all three claimed commit hashes (`0d8f891`, `c303996`, `a4c8a2f`) verified present in `git log`.
