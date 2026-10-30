---
phase: quick
plan: 261030-mcz
subsystem: infra
tags: [github-actions, permissions, scaffold, ci]

requires:
  - phase: 261029-p12
    provides: scripts/scaffold_target_repo.py generates both run.yml and resume.yml workflows
provides:
  - RUN_WORKFLOW_TEMPLATE and RESUME_WORKFLOW_TEMPLATE now grant contents, issues and pull-requests write
  - README Scaffolding steps 2 and 3 subsection explains all three permission keys
affects: [scaffold-target-repo, github-actions-workflows, readme-docs]

actuals:
  tokens: 683
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns: ["GitHub Actions workflow permissions block scoped to exactly the REST calls the job makes"]

key-files:
  created: []
  modified:
    - scripts/scaffold_target_repo.py
    - README.md

key-decisions:
  - "Added issues: write and pull-requests: write to both generated workflow templates, in that order after contents: write, matching the confirmed REST calls (rest.issues.create_comment, rest.pulls.create)"
  - "Did not add actions: write — the only actions-scoped call (dispatch_workflow) runs from the webhook receiver on a separate DISPATCH_GITHUB_TOKEN, never inside these generated jobs"
  - "Left the README resume-workflow-reference sentinel block (README.md:384-428) untouched per plan's explicit out-of-scope instruction — see Unresolved Findings below"

patterns-established:
  - "Explanatory comment precedes each permissions block in generated workflow templates, naming what each scope buys, rather than relying on yaml.dump (consistent with this module's existing template style)"

requirements-completed: [QUICK-MCZ]

coverage:
  - id: D1
    description: "Both generated workflows (run.yml and resume.yml) declare a permissions block parsing to exactly contents: write, issues: write, pull-requests: write"
    requirement: "QUICK-MCZ"
    verification:
      - kind: other
        ref: "uv run python /tmp/df-261030-mcz-verify.py (stage_permissions: parses both generated workflows via yaml.safe_load and asserts exact mapping equality)"
        status: pass
    human_judgment: false
  - id: D2
    description: "README's '#### Scaffolding steps 2 and 3' subsection explains all three permission keys without drifting from what the script emits, and the resume-workflow-reference sentinel block stays byte-identical"
    requirement: "QUICK-MCZ"
    verification:
      - kind: other
        ref: "uv run python /tmp/df-261030-mcz-verify.py (stage_readme: region-scoped key-mention assertions + SHA-1 digest check against pre-task value 7333ea66ca7f46be14d8a2ca76a76aa86a29427c)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py (13 passed)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-10-30
status: complete
---

# Quick Task 261030-mcz: Grant issues/pull-requests write in scaffolded workflow permissions

**Fixed under-scoped `permissions:` blocks in both generated GitHub Actions workflows (`run.yml`, `resume.yml`) so Dark Factory's clarification comments and PR creation no longer 403 against the Actions auto-token, and brought README's explanation of those scopes in sync.**

## Performance

- **Duration:** 20 min
- **Completed:** 2026-10-30T14:14:18Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `RUN_WORKFLOW_TEMPLATE` and `RESUME_WORKFLOW_TEMPLATE` in `scripts/scaffold_target_repo.py` now emit a three-key `permissions:` block (`contents`, `issues`, `pull-requests`, all `write`) instead of `contents: write` alone, with an explanatory comment preceding each block
- README's `#### Scaffolding steps 2 and 3` subsection now explains all three keys (what each unblocks) and states explicitly why `actions: write` is deliberately absent
- Verified via a standalone harness (`/tmp/df-261030-mcz-verify.py`) that invokes the scaffold script as a subprocess, `yaml.safe_load`s both generated workflow files, and asserts the parsed `permissions` mapping equals exactly `{"contents": "write", "issues": "write", "pull-requests": "write"}` — plus a SHA-1 digest check proving the README's `resume-workflow-reference` sentinel block is byte-identical to its pre-task content
- `tests/unit/test_resume_workflow_reference_doc.py` (13 tests, pre-existing, unrelated to this change's scope) still passes

## Task Commits

Each task was committed atomically:

1. **Task 1: Grant issues and pull-requests write in both generated workflow templates** - `18463e6` (feat)
2. **Task 2: Explain all three permission keys in README's Scaffolding steps 2 and 3** - `31c86fa` (docs)

## Files Created/Modified
- `scripts/scaffold_target_repo.py` - `RESUME_WORKFLOW_TEMPLATE` and `RUN_WORKFLOW_TEMPLATE` permissions blocks extended from `contents: write` to `contents`/`issues`/`pull-requests`, each `write`, preceded by an explanatory comment
- `README.md` - `#### Scaffolding steps 2 and 3` paragraph rewritten to cover all three keys and the deliberate absence of `actions: write`; everything from `### The full flow` onward (including the `resume-workflow-reference` sentinel block and its surrounding prose) left byte-identical

## Decisions Made
- Added `issues: write` and `pull-requests: write` in that order after `contents: write`, matching the confirmed REST calls (`rest.issues.create_comment` needs `issues: write`, `rest.pulls.create` needs `pull-requests: write`) rather than guessing at scope names
- Did not add `actions: write` and did not collapse to `permissions: write-all` — both forbidden by the plan and unnecessary, since the only `actions`-scoped call (`dispatch_workflow`) runs from the webhook receiver using the separate `DISPATCH_GITHUB_TOKEN`, never inside either generated job
- Kept the README's `resume-workflow-reference` sentinel block and its surrounding `permissions` reasoning paragraphs untouched, per the plan's explicit out-of-scope instruction (verified via SHA-1 digest match against the pre-task value)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- A repository freshly scaffolded by `scripts/scaffold_target_repo.py` now gets correctly-scoped `run.yml` and `resume.yml` workflows; the clarification-comment and PR-publication 403s this task fixes are resolved for that path.
- See "Unresolved Findings" below for a separate, still-open gap on the README's reference-workflow path (not fixed by this task, as instructed).

## Unresolved Findings (flagged by the plan — must reach the user)

**MANDATORY per the plan's `<flagged_finding>` — reproduced below, verbatim:**

> The README reference workflow inside the `resume-workflow-reference` sentinel block
> (README.md:384-428) **has the identical permissions gap**: it declares
> `permissions:` / `contents: write` and nothing else. The ~18 lines of reasoning that
> follow it (README.md:436-453) justify `contents: write` in depth and never mention the
> issue-comment or pull-request scopes at all.
>
> Consequence: a deployer who follows the documented path of copying that reference
> block — which the README explicitly instructs ("Copy the block below into your own
> repository at `.github/workflows/resume.yml`") — gets an under-scoped workflow even
> after this task ships, because the fix here only reaches repositories scaffolded by
> the script. The two paths now disagree.
>
> Accuracy note on the guard: `tests/unit/test_resume_workflow_reference_doc.py` asserts
> sentinel count, fenced-block presence, YAML-mapping parse, the required `run_id`
> input, exactly-one-resume-invocation, absence of run-state branching, and
> dispatch-credential naming. It does **not** assert on `permissions`, so adding the two
> keys would not, by itself, fail that test — the block is out of scope here by
> instruction and because its surrounding prose would also need rewriting, not because
> the test mechanically blocks it.
>
> Decision for the user: either (a) a follow-up quick task that adds the two keys to the
> sentinel block and extends the `permissions` reasoning prose to cover all three scopes,
> or (b) an explicit decision to leave the reference block minimal and have the prose say
> so. Doing nothing leaves the README internally inconsistent.

---
*Phase: quick*
*Completed: 2026-10-30*
