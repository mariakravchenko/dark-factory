---
phase: 06-tools-permissions-the-credential-boundary
reviewed: 2026-09-20T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/dark_factory/config/loader.py
  - src/dark_factory/tools/env.py
  - src/dark_factory/tools/mcp_transport.py
  - tests/unit/test_mcp_adapter.py
  - tests/unit/test_repo_config_schema.py
  - tests/unit/test_shell_execute.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 06: Code Review Report

**Reviewed:** 2026-09-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** clean

## Summary

This is a follow-up review scoped to exactly the files touched by the three code-review fix
commits applied since the phase's last review (`51ddbb6`): `4790430` (CR-01, `roles_dir`
containment), `258f1a9` (WR-01, `ProcessLookupError` race in `shell_execute`'s timeout-kill
path), and `5c87e6b` (WR-02, `UnknownCapabilityError` reshaping over MCP).

All three fixes were re-verified independently against the current state of the source and
against the diff each commit actually introduced (`git diff 51ddbb6..HEAD`), not just the
commit message's claim:

- **CR-01** (`src/dark_factory/config/loader.py:139-150`): `roles_dir` is now resolved and
  checked with `is_relative_to(root)` *before* any role YAML under it is read, mirroring the
  pre-existing `instructions:` containment check. Verified the check correctly rejects
  `roles_dir: ../outside` (test `test_roles_dir_escaping_the_repo_root_is_rejected`) and does
  not regress the in-root case (`test_roles_dir_within_the_repo_root_still_loads`). Manually
  confirmed `Path.is_relative_to` semantics hold for the `roles_dir == root` (default `.`)
  edge case as well as the `../` escape case.
- **WR-01** (`src/dark_factory/tools/env.py:217-224`): `os.killpg(os.getpgid(proc.pid),
  signal.SIGKILL)` is now wrapped in `contextlib.suppress(ProcessLookupError)`. Confirmed the
  suppression scope covers both `os.getpgid` and `os.killpg` (either can raise
  `ProcessLookupError` if the child has already exited), and that the function still returns a
  well-formed `ShellResult(timed_out=True, exit_code=None, ...)` afterward rather than letting
  the race propagate as an unhandled crash. Regression test
  `test_timeout_kill_race_where_the_child_already_exited_does_not_raise` stubs `os.killpg` to
  raise and proves the function still returns cleanly.
- **WR-02** (`src/dark_factory/tools/mcp_transport.py:148-176`): the per-tool closure now
  catches `(CapabilityDeniedError, UnknownCapabilityError)` (previously only the former) and
  reshapes both into the MCP SDK's `ToolError` with the original message preserved verbatim.
  Confirmed `UnknownCapabilityError`'s message-forwarding is exact (no truncation, no generic
  "Error executing tool" fallback) via
  `test_granted_but_unregistered_capability_is_reshaped_not_opaque`, which explicitly asserts
  the message no longer equals the SDK's bare opaque form.

No new bugs, security gaps, or quality regressions were introduced by any of the three fix
commits — each change is minimal, additive, and scoped exactly to its stated defect. No debug
artifacts (`TODO`/`FIXME`/`console.log`/bare `except:`) were found in the reviewed files. The
credential-boundary discipline in `env.py` (explicit allowlist construction, no
`os.environ.copy()`, argument-list `Popen` with no shell) and the single-enforcement-point
discipline in `mcp_transport.py` (`invoke()` re-checked fresh on every call, `granted_tools`
never used as a second, silent gate) remain intact and are exercised by the existing test
suite.

All reviewed files meet quality standards. No issues found.

---

_Reviewed: 2026-09-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
