---
phase: 07-claude-code-the-first-real-worker
reviewed: 2026-09-20T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - .github/workflows/ci.yml
  - src/dark_factory/config/settings.py
  - src/dark_factory/tools/native.py
  - src/dark_factory/workers/claude_code.py
  - src/dark_factory/workers/registry.py
  - tests/contract/test_coding_worker_contract.py
  - tests/support/fake_claude_cli.py
  - tests/unit/test_ci_enforces_worker_name_guard.py
  - tests/unit/test_claude_code_worker.py
  - tests/unit/test_native_tool_contract.py
  - tests/unit/test_settings.py
  - tests/unit/test_worker_registry_names.py
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-09-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the `ClaudeCodeWorker` adapter (WORK-04), its native-tool translation
consumption of `NATIVE_TOOL_CONTRACT`, `Settings`'s new `anthropic_api_key`/
`worker_timeout_seconds` fields, the worker registry wiring, the CI
worker-name-guard test, and the associated unit/contract test suites.

The subprocess-spawn discipline itself is solid: explicit `list[str]` argv, no
`shell=True`, an allowlisted credential-free child environment, timeout +
process-group kill, streamed-to-file capture (never `PIPE`), and a
redact-in-`finally` step that runs on every exit path (success, non-zero
exit, and timeout-kill) — all of this is implemented as documented and is
well covered by tests.

The most significant defect is a **capability-scope bug**: `artifacts.read`
is translated to the bare `Read` native tool (full-worktree read access)
instead of the path-scoped `Read(<artifacts-glob>/**)` specifier that
`NATIVE_TOOL_CONTRACT` itself explicitly documents for that capability —
the *identical* narrowing `artifacts.write` correctly receives in the same
function. A role granted only `artifacts.read` therefore ends up with
unrestricted native filesystem read access, not the narrow "read this run's
artifacts" access the grant is supposed to authorize. This is pinned as
"correct" by an existing unit test, so it will not be caught by CI as
currently written.

Several smaller correctness/quality gaps are noted below (a metadata-drop on
the `is_error` early-return path, an unused/misleading completeness-guard
function, and a couple of narrow-but-real edge cases in the redact-then-parse
ordering and the resume answer/marker handling).

## Critical Issues

### CR-01: `artifacts.read` is translated to an unscoped `Read` grant, not the documented path-scoped specifier

**File:** `src/dark_factory/workers/claude_code.py:165-172` (`_TOOL_NAMES`), `src/dark_factory/workers/claude_code.py:186-209` (`allowed_tools_for`)

**Issue:**
`src/dark_factory/tools/native.py:162-183` defines the `artifacts.read` grant
and is explicit that it must **not** be a bare `Read` grant:

```python
"artifacts.read": NativeToolGrant(
    ...
    claude_code=(
        "--allowedTools "
        "'Read(.dark-factory/runs/<run_id>/artifacts/**)' -- a "
        "path-scoped rule specifier over the run's artifacts subtree, "
        "not a bare Read grant; ..."
    ),
    ...
```

`claude_code.py`'s own comment directly above `_TOOL_NAMES` acknowledges this
exact principle for the sibling grant, `artifacts.write`:

```python
# "artifacts.write" is deliberately absent -- the whole
# point of that grant is a scope narrower than repo.write, so a bare tool
# name here would silently widen it to the entire worktree. It is handled
# separately in `allowed_tools_for()` as a path-scoped specifier instead.
```

But `artifacts.read` is present in `_TOOL_NAMES` mapped to a bare `"Read"`:

```python
_TOOL_NAMES: Mapping[str, tuple[str, ...]] = {
    "repo.read": ("Read", "Glob"),
    ...
    "artifacts.read": ("Read",),
}
```

and `allowed_tools_for()` only special-cases `artifacts.write` for
path-scoping — `artifacts.read` falls through the generic `_TOOL_NAMES.get()`
branch and contributes a bare, worktree-wide `Read`:

```python
def allowed_tools_for(granted, artifacts_glob):
    names: set[str] = set()
    for capability in granted:
        names.update(_TOOL_NAMES.get(capability, ()))
    if "artifacts.write" in granted and artifacts_glob is not None:
        names.add(f"Edit({artifacts_glob}/**)")
    return sorted(names)
```

Concretely: a role granted only `artifacts.read` (e.g. to read a prior
role's artifact without also holding `repo.read`) gets unrestricted native
`Read` access to the *entire worktree*, not the narrow "this run's
artifacts subtree" access the capability is documented to grant. This is a
real over-authorization: the whole point of `--allowedTools` deny-by-omission
in this design (per the module docstring's "own worktree confinement"
model) is that a role's native filesystem access should track its `tools:`
grants exactly — this is the one capability where it silently doesn't.

The gap is masked, not caught, by the existing tests: `test_tool_names_
cover_every_native_contract_capability` (`tests/unit/test_claude_code_worker.
py:942-948`) only checks that every contract *key* has a translation entry —
it does not check that the translation matches the contract's documented
path-scoped semantics. `test_allowed_tools_for_artifacts_read` (`tests/unit/
test_claude_code_worker.py:902-905`) actively pins the buggy behavior:

```python
def test_allowed_tools_for_artifacts_read() -> None:
    from dark_factory.workers.claude_code import allowed_tools_for
    assert allowed_tools_for({"artifacts.read"}, None) == ["Read"]
```

**Fix:**
Treat `artifacts.read` the same way `artifacts.write` is already treated:
remove it from `_TOOL_NAMES` and add a path-scoped branch in
`allowed_tools_for()`. Note the correct glob for *read* is broader than the
current role's own `artifacts_dir` (which is scoped to `artifacts/<role>/`
for writing) — reading a *prior* role's artifact requires scoping over the
whole run's `artifacts/` subtree, e.g.:

```python
_TOOL_NAMES: Mapping[str, tuple[str, ...]] = {
    "repo.read": ("Read", "Glob"),
    "repo.search": ("Grep", "Glob"),
    "repo.write": ("Write", "Edit"),
    "repo.write_tests": ("Write", "Edit"),
    "shell.execute": ("Bash",),
    # artifacts.read / artifacts.write are both path-scoped -- see below.
}


def allowed_tools_for(granted, artifacts_glob, run_artifacts_glob=None):
    names: set[str] = set()
    for capability in granted:
        names.update(_TOOL_NAMES.get(capability, ()))
    if "artifacts.read" in granted and run_artifacts_glob is not None:
        names.add(f"Read({run_artifacts_glob}/**)")
    if "artifacts.write" in granted and artifacts_glob is not None:
        names.add(f"Edit({artifacts_glob}/**)")
    return sorted(names)
```

where `run_artifacts_glob` is built from `run_id` alone (e.g.
`.dark-factory/runs/{run_id}/artifacts`), not from the per-role
`artifacts_dir`. Update `_base_argv`, `_tool_names_cover_native_contract`,
and the corresponding tests (including the one currently pinning `["Read"]`)
to match.

## Warnings

### WR-01: The `is_error` early-return path silently drops parsed metadata

**File:** `src/dark_factory/workers/claude_code.py:535-545`

**Issue:** When `parsed.get("is_error")` is truthy, the method returns
immediately without populating `metadata`:

```python
if parsed.get("is_error"):
    return WorkerResult(
        status=WorkerResultStatus.FAILED,
        summary="claude reported an error",
        error=str(parsed.get("result", "")),
        worker_session_id=parsed.get("session_id"),
    )

metadata = {
    key: parsed[key] for key in _RESULT_METADATA_KEYS if key in parsed
}
```

`metadata` (duration, cost, turn count, `permission_denials`, etc.) is
computed *after* this early return, so it is never attached to the
`is_error` `FAILED` result even though it was already present in `parsed`
and would be exactly the diagnostic information useful for debugging why a
role failed. The `exit_code != 0` and timeout `FAILED` paths do populate a
(smaller) `metadata` dict; this path is the odd one out.

**Fix:** Compute `metadata` once, before the `is_error` check, and include
it in both `FAILED` branches:

```python
metadata = {key: parsed[key] for key in _RESULT_METADATA_KEYS if key in parsed}

if parsed.get("is_error"):
    return WorkerResult(
        status=WorkerResultStatus.FAILED,
        summary="claude reported an error",
        error=str(parsed.get("result", "")),
        worker_session_id=parsed.get("session_id"),
        metadata=metadata,
    )
```

### WR-02: `_tool_names_cover_native_contract()` is dead code with a misleading docstring

**File:** `src/dark_factory/workers/claude_code.py:175-183`

**Issue:** This module-level function is defined but never called — not from
production code (it is not exported in `__all__`), and not from any test.
Its docstring claims it exists "so a future capability added to the contract
without a translation fails a unit test" — but no test invokes it; the
actual guard (`tests/unit/test_claude_code_worker.py:942-948`,
`test_tool_names_cover_every_native_contract_capability`) independently
re-derives the same set-equality check by importing `_TOOL_NAMES` directly
rather than calling this function. The function gives the appearance of a
wired safety net that doesn't actually run, which is exactly the kind of
inconsistency this review's substrate found (an unused private helper whose
name and docstring both assert a guarantee it does not itself provide).

**Fix:** Either delete `_tool_names_cover_native_contract()` and keep the
existing inline test, or have the test call the function directly instead of
re-deriving the same expression, so the production helper is the guard
rather than dead prose:

```python
def test_tool_names_cover_every_native_contract_capability() -> None:
    from dark_factory.workers.claude_code import _tool_names_cover_native_contract
    assert _tool_names_cover_native_contract()
```

### WR-03: Redacting the log file before re-reading it for JSON parsing risks corrupting structured fields used downstream

**File:** `src/dark_factory/workers/claude_code.py:483-546`

**Issue:** `_scrub_log_in_place(stdout_path)` runs (in `finally`) *before*
`stdout_text = stdout_path.read_text(...)` is read back and parsed as JSON.
This means every structured field extracted from `parsed` (`session_id`,
`result`, `duration_ms`, etc.) is derived from the **already pattern-redacted**
text, not from the CLI's raw output. `_redact_str`'s D-15 pattern table
performs plain substring/regex substitution on the raw file bytes with no
awareness of JSON structure or field semantics — it happens to preserve
validity in the tested cases (the tested payload only redacts within a
string value), but nothing prevents a `result` string that legitimately
contains something pattern-shaped (a commit SHA outside the exempted
`commit:`/`sha:` phrasing, a `token=...`-shaped fragment in ordinary prose)
from being silently rewritten before it is parsed into `WorkerResult.
summary`. Concretely, if a real (non-UUID-formatted) `session_id` value ever
matched the 40/64-hex token pattern, `worker_session_id` would come back as
the literal string `"[redacted:github_token]"` instead of the real session
id, and a subsequent `resume()` call would pass that corrupted string to
`claude --resume`, breaking HITL-04's native resume path silently (no
exception, just a resume that fails against a nonexistent session).

**Fix:** Parse the JSON result from the *raw* captured stdout before
redaction, and only redact the on-disk log copy (which is what actually
needs scrubbing before the git commit step). E.g. read `stdout_path` once
for parsing, then call `_scrub_log_in_place` on the file separately (order
doesn't matter for the file-scrub side effect, only for what feeds
`WorkerResult` construction):

```python
raw_stdout = stdout_path.read_text("utf-8", errors="replace")
finally:
    _scrub_log_in_place(stdout_path)
    _scrub_log_in_place(stderr_path)
...
parsed = json.loads(raw_stdout.strip())
```

(with the existing redaction of `WorkerResult.summary`/`error` still handled
by the orchestrator's lifecycle-write redaction path, per
`events/redaction.py`'s stated design).

### WR-04: `_resolve_dirs` silently creates a non-worktree directory when the expected worktree is missing

**File:** `src/dark_factory/workers/claude_code.py:569-596`

**Issue:** For a UUID `run_id`, `_resolve_dirs` does
`work_dir.mkdir(parents=True, exist_ok=True)` unconditionally before
returning `work_dir` as the subprocess `cwd`. The comment explains this is
meant to be a "defensive no-op" because the directory should already exist
as a git worktree `ensure_worktree` created. If that precondition is ever
violated by an orchestrator-side bug (e.g. `execute()` invoked before the
worktree is created, or the worktree was cleaned up out of band), this
adapter does not fail loudly — it creates an empty plain directory and
spawns `claude` inside it with `cwd` pointing at a directory with no git
repository and no source tree at all. The agent would then either fail in a
confusing way or, worse, start writing files into an untracked scratch
directory that no downstream diff/commit step will ever pick up, with no
signal that anything went wrong at the adapter layer.

**Fix:** Consider asserting the directory is a real git worktree (e.g.
`(work_dir / ".git").exists()`) before spawning when `parsed_run_id is not
None`, and returning a `FAILED` `WorkerResult` with a clear message if not —
turning a silent no-op into a visible, diagnosable failure.

## Info

### IN-01: An empty-string resume answer is treated as absent

**File:** `src/dark_factory/workers/claude_code.py:634-636`

**Issue:** `answer or RESUME_CONTINUATION_PROMPT` (native-resume branch) and
the equivalent `answer or "(no answer was supplied)"` in
`_build_resume_prompt` both treat `answer == ""` the same as `answer is
None`, discarding a legitimate (if degenerate) empty-string human answer
and substituting the generic continuation prompt/placeholder instead.

**Fix:** If an empty string is a meaningful distinct value upstream (vs.
`None`), use `answer if answer is not None else ...` instead of `or`.

### IN-02: `_extract_needs_input` matches the *first* line-initial marker, not the last

**File:** `src/dark_factory/workers/claude_code.py:88-90, 139-156`

**Issue:** `_NEEDS_INPUT_RE.search(...)` finds the leftmost line-initial
occurrence of `NEEDS_INPUT:`, then (via `DOTALL` + `\Z`) captures everything
from there to the end of the string as the question. The prompt instructs
the agent to emit the marker only once, as the last line — but nothing
enforces that. If the CLI's `result` text ever contained two line-initial
`NEEDS_INPUT:` occurrences (e.g. echoed from injected repo/tool content
before the agent's own final marker), the captured "question" would include
everything after the first occurrence, including the second literal marker
line, rather than isolating the agent's actual final question.

**Fix:** Consider anchoring to the *last* line-initial occurrence (e.g. via
`re.findall` and taking the final match, or a greedy pattern search from the
end) if this scenario is a real concern; otherwise no action needed beyond
noting the assumption is enforced only by prompt convention, not parsing.

---

_Reviewed: 2026-09-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
