---
phase: quick
plan: 261030-op0
subsystem: workers
tags: [cli_runtime, claude_code, prompt-construction, artifacts, regression-test]
status: complete
dependency-graph:
  requires: []
  provides:
    - "context_prompt_sections emits a worktree-relative ## Expected outputs destination"
  affects:
    - src/dark_factory/workers/cli_runtime.py
    - tests/support/fake_cli.py
tech-stack:
  added: []
  patterns:
    - "Prompt destination mirrors _base_argv's `if run_id and artifacts_dir` guard exactly so the two cannot diverge on the degenerate case"
key-files:
  created: []
  modified:
    - src/dark_factory/workers/cli_runtime.py
    - tests/support/fake_cli.py
    - tests/unit/test_claude_code_worker.py
    - .planning/STATE.md
decisions:
  - "Fixed the prompt, not the grant -- five independent sites (native.py's NATIVE_TOOL_CONTRACT, git/scope.py's pathspec, collect_declared_artifacts, tools/registry.py's _artifacts_read, test_git_diff.py) all agree the .dark-factory/runs/<run_id>/ prefix is required and correct; the prompt was the one component naming a different (run-root-relative) path"
  - "fake_cli.py's declared-outputs step now resolves the parsed destination relative to its own cwd (the fake's cwd is the worktree, same as a real agent's) instead of discovering a run root by globbing and double-prefixing"
metrics:
  duration: "~25min"
  completed: 2026-10-31
actuals:
  tokens: 2150
  tasks: 3
  commits: 2
  plan_head_before: a5585fb9297abc717c9d84ffbf053d237842cc66
---

# Quick Task 261030-op0: Fix the Expected-outputs prompt path to match the granted Write glob Summary

Made `context_prompt_sections`'s `## Expected outputs` prompt destination byte-identical
to the worktree-relative glob `_base_argv` grants via `Write(<glob>/**)`, closing a silent
permission-denial gap found live against two real `app-int` CI runs.

## What Was Built

`context_prompt_sections` in `src/dark_factory/workers/cli_runtime.py` previously told a
role to write its declared outputs under the raw, run-root-relative `RoleContext.artifacts_dir`
value (e.g. `artifacts/BA`). But the agent's cwd at spawn is the *worktree*
(`cwd=work_dir`), and the `--allowedTools` grant it receives covers the worktree-relative
glob `.dark-factory/runs/<run_id>/artifacts/BA/**`. A role that wrote exactly where the
prompt told it to was therefore silently denied by the real `claude` CLI under
`--permission-mode dontAsk` (no prompt to learn from), and had to rediscover the real path
by trial and error against denials -- sometimes giving up instead.

The fix is entirely in the prompt text: `context_prompt_sections` now reads `run_id` via
`getattr(context, "run_id", None)` alongside the existing `artifacts_dir`, and emits
`.dark-factory/runs/<run_id>/<artifacts_dir>` as the destination whenever both are truthy --
mirroring `_base_argv`'s own `if run_id and artifacts_dir` guard exactly so the two values
cannot diverge on the degenerate (no `run_id`) case, where the destination degrades cleanly
to the bare `artifacts_dir` rather than emitting a literal `None`.

`tests/support/fake_cli.py` (the shared fake-CLI generator all three fake adapters delegate
to) was updated in the same commit so the whole suite stays green: its declared-outputs
step previously discovered a run root by globbing `.dark-factory/runs/*` and joined the
parsed destination onto it, which would now double the prefix. It now resolves the parsed
destination directly relative to the process's own cwd -- exactly how a real agent's native
write tool resolves it -- and the now-unnecessary glob/run-root-discovery guard was removed.

A new regression test, `test_expected_outputs_prompt_path_is_identical_to_granted_write_glob`
in `tests/unit/test_claude_code_worker.py`, proves for one `_context(role="BA",
tools=["artifacts.write"])`: the prompt's parsed destination (via the shared
`OUTPUT_BULLET_RE`) and the glob inside `_base_argv`'s granted `Write(<glob>/**)` specifier
are byte-identical.

**`src/dark_factory/workers/claude_code.py` and `src/dark_factory/tools/native.py` were not
touched** -- `git diff --stat` confirms zero lines changed in either file. The grant's
`.dark-factory/runs/<run_id>/` prefix was already correct; only the prompt's advertised
destination was wrong.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - blocking] `ruff check` import-sort on the new test**
- **Found during:** Task 2's scoped lint gate
- **Issue:** The new test's `from tests.support.fake_cli import OUTPUT_BULLET_RE` import
  left a blank line separating it from the preceding two imports, which `ruff check`'s
  import-sort rule (`I001`) flagged as un-sorted.
- **Fix:** `ruff check --fix` on the three touched files; `ruff check` and `ruff format
  --check` both report clean afterward.
- **Files modified:** `tests/unit/test_claude_code_worker.py`
- **Commit:** `279ca9e`

No other deviations -- Task 1's behavior, Task 2's gate results, and Task 3's STATE.md
record all matched the plan as written.

## Live UAT Finding Carried Forward (Phase 10 finding (2) -- NOT resolved by this task)

Per the plan's explicit instruction, this task deliberately left Phase 10 UAT finding (2)
open and untouched. Carrying it forward verbatim from STATE.md's `[Phase 10]` Blockers/Concerns
bullet, since it is a real, separate gap:

> The same prompt section gives a role only a bare output *filename*, never the JSON schema
> it must match — a role operating on a real target repo (with no access to Dark Factory's
> own `domain/artifacts.py` source) has no way to discover the exact pydantic shape and will
> invent a plausible-but-wrong one.

This remains an open concern in `.planning/STATE.md`'s Blockers/Concerns section and is worth
a future hardening pass (its own quick task or phase plan). Not addressed here because it is
explicitly out of this task's scope per the PLAN.md objective.

## Verification

- `uv run pytest tests/unit/test_claude_code_worker.py tests/unit/test_fake_cli_declared_outputs.py -q`
  -- 65 passed (new regression test + all 10 `test_fake_cli_declared_outputs.py` tests
  unchanged, confirming the destination-equivalence claim in the plan's `<done>` criterion).
- `uv run pytest -m "unit or contract" -q` -- 882 passed, 0 failed (after `uv sync
  --all-extras --dev` to make the `webhook` optional extra's `starlette`/`uvicorn`
  available locally for test collection -- an environment setup step, not a code fix).
- `uv run ruff check` / `ruff format --check` on the three touched files -- all clean.
- `uv run mypy src/dark_factory/workers/cli_runtime.py tests/support/fake_cli.py` -- zero
  errors.
- `uv run mypy tests/unit/test_claude_code_worker.py` -- exactly 10 pre-existing `arg-type`
  errors on `ClaudeCodeWorker.resume` calls (same count cited in the plan as the ceiling;
  not raised by this task's new test).
- `git diff --stat src/dark_factory/workers/claude_code.py src/dark_factory/tools/native.py`
  -- empty (no diff), confirming the grant and the native-tool contract were not touched.

## Self-Check

- FOUND: `src/dark_factory/workers/cli_runtime.py`
- FOUND: `tests/support/fake_cli.py`
- FOUND: `tests/unit/test_claude_code_worker.py`
- FOUND commit `c2bf996` (Task 1: prompt fix + fake-CLI update + regression test)
- FOUND commit `279ca9e` (Task 2: import-sort fix after the full-tier/lint/mypy gate)

## Self-Check: PASSED
