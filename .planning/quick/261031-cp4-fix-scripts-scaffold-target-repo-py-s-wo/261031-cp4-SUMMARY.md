---
phase: quick
plan: 261031-cp4
subsystem: scripts/scaffold
tags: [scaffold, ci-workflow, uv, quality-gate, app-int-live-failure]
status: complete
dependency-graph:
  requires:
    - DEFAULT_QUALITY_GATE_COMMANDS (scripts/scaffold_target_repo.py)
    - RESUME_WORKFLOW_TEMPLATE / RUN_WORKFLOW_TEMPLATE (scripts/scaffold_target_repo.py)
  provides:
    - "Install uv" step in both generated CI workflows
    - tests/unit/test_scaffold_target_repo.py (first test module for this script)
  affects:
    - any future scaffold run against a target repository (run.yml / resume.yml Quality Gate step)
tech-stack:
  added: []
  patterns:
    - "structural step-ordering assertion via yaml.safe_load index comparison, never a character-offset/substring check"
    - "action-pin agreement guard: generated template's third-party Action ref asserted equal to this repository's own ci.yml ref, so the two cannot drift"
key-files:
  created:
    - tests/unit/test_scaffold_target_repo.py
  modified:
    - scripts/scaffold_target_repo.py
    - .planning/STATE.md
decisions:
  - "The uv install step is unconditional template text (not rendered conditionally on resolved --quality-gate-command values) -- a deployer whose gate doesn't invoke uv pays ~2s and is told by the step's own comment that they may delete it"
  - "Pinned to astral-sh/setup-uv@v6, read from this repository's own ci.yml (not the task description's illustrative @v3), with a test asserting the two refs stay equal"
  - "No enable-cache: true on the generated step -- that option's cache key globs for a uv.lock a freshly scaffolded target repository may not have"
actuals:
  tokens: 3800
  tasks: 3
  commits: 1
  plan_head_before: "105b18698e7022498b5cc067bcc57289cde5141c"
metrics:
  duration: "~20min"
  completed: "2026-10-31"
---

# Quick Task 261031-cp4: Fix scripts/scaffold_target_repo.py's two generated CI workflows to install uv before dark-factory Summary

Both generated GitHub Actions workflows (`run.yml` / `resume.yml`) now carry an `Install uv` step (`astral-sh/setup-uv@v6`, pinned to match this repository's own `ci.yml`) immediately before the `Install dark-factory` step, closing a live `app-int` Quality Gate failure where a GitHub-hosted runner with no `uv` on PATH died on `FileNotFoundError: No such file or directory: 'uv'` even though `DEFAULT_QUALITY_GATE_COMMANDS` invokes `uv run` by default.

## What Was Built

**Task 1 (tracer, TDD).** Wrote `tests/unit/test_scaffold_target_repo.py` — the first test module this standalone script has ever had — with three tests, confirmed RED (the ordering/action-pin tests failed because the step was absent; the quality-gate-defaults test passed immediately since it exercises pre-existing behavior), then added the step to both `RESUME_WORKFLOW_TEMPLATE` and `RUN_WORKFLOW_TEMPLATE` in `scripts/scaffold_target_repo.py`, confirmed GREEN:

- `test_install_uv_step_precedes_install_dark_factory_step` (parametrized over `render_run_workflow`/`render_resume_workflow`): `yaml.safe_load`s the rendered workflow, asserts exactly one `astral-sh/setup-uv@v\d+` step and exactly one `Install dark-factory` step, and asserts the uv step's **list index** is strictly less than the install step's — never a character-offset comparison, so a future reordering that keeps both strings present still fails this test.
- `test_setup_uv_ref_matches_this_repository_own_ci_workflow`: scans `.github/workflows/ci.yml` for its own `astral-sh/setup-uv@...` ref (asserting exactly one distinct ref exists there), then asserts both generated workflows' refs equal it — so a future major-version bump to one copy without the other fails in the unit tier.
- `test_default_quality_gate_commands_are_the_recorded_reason_uv_is_installed`: asserts `DEFAULT_QUALITY_GATE_COMMANDS` is non-empty and every entry starts with `uv run `, and that `render_dark_factory_yaml` with those defaults produces `quality_gate.commands` equal to that list — binding the install step's justification to the actual default so a future change off uv must land here too.

The added template block (identical in both templates, inserted between `Checkout` and `Install dark-factory`):

```yaml
      # The Quality Gate step (inside `dark-factory resume`) re-runs this
      # repository's own `.dark-factory.yaml` `quality_gate.commands` --
      # the scaffold's generated default pair invokes `uv run`. A
      # GitHub-hosted runner image ships no uv, so without this step the
      # gate fails before executing a single check. `enable-cache` is
      # omitted: its cache key globs for a lockfile a target repository may
      # not have. If your gate commands do not invoke uv, delete this step.
      - name: Install uv
        uses: astral-sh/setup-uv@v6
```

Nothing else in either template was touched — the `permissions:` block, the `pip install` step, the commented-out worker-runtime hint, the step-level `env:` mapping, and the `{{WORKER_CREDENTIAL_ENV}}` token are all byte-identical to before.

**Task 2 (verification only, no code change).** Ran the actual script into a throwaway directory (`--yes --github-owner example-org --github-repo example-repo`), producing all 13 scaffold files; re-read both generated workflow files **from disk** and re-asserted the structural ordering (`SMOKE_OK ['run', 'resume']`) — proving the written file, not just the render-function return value, carries the fix. Then ran `ruff check` / `ruff format --check` on the two touched files (clean), synced dev deps (`uv sync --all-extras --dev`, needed for the `starlette`/`uvicorn` webhook extra to be importable at collection time — an environment step, not a code fix), and ran the full `unit or contract` tier: 889 passed, 0 failed, 430 deselected, zero existing test files edited.

**Task 3 (docs-only, left uncommitted per this quick task's execution constraints).** Appended one OPEN bullet to `.planning/STATE.md`'s `### Blockers/Concerns` recording that README's hand-copyable `<!-- resume-workflow-reference -->` block is a second, independent copy of `resume.yml` that still carries the identical uv gap, deliberately out of this task's scope, with the `261030-mcz` → `261030-mng` split named as precedent for closing it later.

## Deviations from Plan

None. The plan's three decisions (unconditional step, `@v6` pin read from `ci.yml`, no `enable-cache`) were implemented exactly as specified. No file under `src/dark_factory/` was touched; the closed JSON-schema prompt work (`cli_runtime.py`, `domain/artifacts.py`, `artifacts/validation.py`) was not touched.

## Verification Results

- `uv run pytest -q tests/unit/test_scaffold_target_repo.py` → **5 passed** (3 tests, 2 parametrized over run.yml/resume.yml = 5 collected items).
- Real scaffold invocation into a `mktemp -d` target wrote all 13 files; `parse_check` accepted them; re-reading both workflow files from disk and re-running the structural ordering check printed `SMOKE_OK ['run', 'resume']`.
- `uv run ruff check scripts/scaffold_target_repo.py tests/unit/test_scaffold_target_repo.py` → `All checks passed!`
- `uv run ruff format --check scripts/scaffold_target_repo.py tests/unit/test_scaffold_target_repo.py` → `2 files already formatted`.
- `uv run pytest -q -m "unit or contract"` → **889 passed, 430 deselected, 0 failed**, zero existing test files edited (confirmed via `git status --short` showing no diffs beyond the two files committed in Task 1).
- `grep -q '261031-cp4' .planning/STATE.md && grep -q 'resume-workflow-reference' .planning/STATE.md && grep -q '261030-mng' .planning/STATE.md` → `STATE_OK` printed.
- <human-check>Not yet performed in this session: re-scaffolding (or hand-applying the step to) the `app-int` repository's `run.yml` and dispatching a real CI run to confirm the Quality Gate step executes `uv run pytest -q` / `uv run ruff check .` instead of dying with `FileNotFoundError: No such file or directory: 'uv'`. Deferred to `/gsd-verify-work`.</human-check>

## Known Stubs

None — no stub patterns, placeholder text, or unwired data sources were introduced by this change.

## Threat Flags

None — the added step was already fully assessed in the plan's own `<threat_model>` (T-CP4-01 through T-CP4-05, T-CP4-SC), all dispositioned `accept` or `mitigate` with no open gaps; nothing in this plan's implementation diverged from what the threat model covers.

## Self-Check: PASSED

- `scripts/scaffold_target_repo.py` — FOUND
- `tests/unit/test_scaffold_target_repo.py` — FOUND
- Commit `bfe0aea` (Task 1: feat, template edit + new test module) — FOUND in `git log --oneline`
- `plan_head_before` (`105b18698e7022498b5cc067bcc57289cde5141c`) to `HEAD` → `git rev-list --count` reports `1`, matching the single task commit (Task 2 made no code change; Task 3's STATE.md edit is docs-only and intentionally left uncommitted for the orchestrator's docs commit).
