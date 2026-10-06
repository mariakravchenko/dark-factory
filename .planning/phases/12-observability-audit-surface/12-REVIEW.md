---
phase: 12-observability-audit-surface
reviewed: 2026-10-06T05:46:41Z
depth: standard
files_reviewed: 32
files_reviewed_list:
  - src/dark_factory/artifacts/store.py
  - src/dark_factory/cli.py
  - src/dark_factory/domain/views.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/events/reader.py
  - src/dark_factory/git/__init__.py
  - src/dark_factory/git/client.py
  - src/dark_factory/git/committed.py
  - src/dark_factory/git/diff.py
  - src/dark_factory/git/errors.py
  - src/dark_factory/git/lifecycle.py
  - src/dark_factory/git/scope.py
  - src/dark_factory/git/worktree.py
  - src/dark_factory/observability/render.py
  - src/dark_factory/observability/run_detail.py
  - src/dark_factory/orchestrator/runner.py
  - tests/db/test_artifact_created_event.py
  - tests/db/test_artifacts_show_reads_committed_content.py
  - tests/db/test_clarification_comment_is_redacted.py
  - tests/db/test_events_reader_sees_every_bounce.py
  - tests/db/test_qa_verdict_events.py
  - tests/db/test_run_report.py
  - tests/db/test_secret_redaction_e2e_full_pipeline.py
  - tests/integration/test_artifacts_cli.py
  - tests/integration/test_cli_commands_are_reads.py
  - tests/integration/test_events_cli.py
  - tests/integration/test_redaction_interactions.py
  - tests/integration/test_runs_cli.py
  - tests/integration/test_status_cli.py
  - tests/support/git_repo.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_global_settings_reads_are_declared.py
  - tests/unit/test_observability_import_graph.py
findings:
  critical: 0
  warning: 4
  info: 1
  total: 5
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-10-06T05:46:41Z
**Depth:** standard
**Files Reviewed:** 32 (16 source + 16 test)
**Status:** issues_found

## Summary

Phase 12 adds the observability/audit surface: `dark-factory status/runs/events/artifacts` CLI commands, their DTOs (`domain/views.py`), their renderers (`observability/render.py`), their readers (`observability/run_detail.py`, `events/reader.py`), the `ARTIFACT_CREATED`/`QA_FAILED`/`QA_PASSED` event ties in `orchestrator/runner.py`, a new artifact-content scrub step (`artifacts/store.py::scrub_artifact_text_in_place`), and a `dark_factory.git.errors` leaf-module split to break a circular import.

This codebase is unusually well-defended: the test suite includes AST-level structural guards (no `RunStatus` comparisons in CLI command bodies, a declared inventory of every `get_settings()` call site, an events-free import-closure sweep for `observability/`), a text/JSON key-set parity test, and a full seeded-secret sweep across every persistence sink and all four new CLI surfaces. I traced the actual diff against `953fef04ac5c0e8241ae55053cf8bf02e927e961^` (not just the full files) and cross-checked every new code path against its own test file. I could not find a BLOCKER-grade bug (no injection, no credential leak, no crash, no data-loss path) in the new code — the redaction architecture (`redact()`'s recursive mapping/list walk, the `_GIT_OBJECT_KEYS` exemption for `wip_commit_sha`/`commit`/`sha`, the generic per-event redaction inside `apply_transition`) correctly covers every new sink I checked, including ones the existing tests don't directly assert on (e.g. the JSON `roles` section's nested `wip_commit_sha`).

What I did find is a cluster of real WARNING-grade quality/observability gaps, all in the brand-new rendering/reading code, none of which any existing test catches because the test suite's parity guard operates at the *section-key* level, not the *nested-field* level, and because the "never hide a failure" acceptance criterion is checked by substring presence rather than readability.

## Warnings

### WR-01: `render_run_report`'s roles table silently drops `wip_commit_sha`, breaking text/JSON parity at the field level

**File:** `src/dark_factory/observability/render.py:251-270`
**Issue:** `RoleAttemptRow` (`domain/views.py:174-191`) declares `wip_commit_sha: str | None`, and `RunReport.as_json()` includes it verbatim for every role attempt (it rides straight through `detail_dump["roles"]`). But `render_run_report`'s `roles_table` only declares columns for `role`, `worker`, `attempt`, `status`, `worker_session_id`, `created_at` — `wip_commit_sha` is never added as a column and never appears anywhere in the text rendering. An operator using `dark-factory status` (text mode) can never see that a WIP-recovery commit (A-05-06, `WIP_COMMIT_CREATED`) landed on a given attempt, while an operator using `--json` can. `tests/integration/test_status_cli.py::test_json_key_set_equals_the_text_field_set` only asserts the nine top-level `SECTION_KEYS` strings appear as substrings in the text output — it has no visibility into a field *within* one of those sections, so this asymmetry passes every existing test.
**Fix:**
```python
roles_table.add_column("wip_commit_sha", min_width=40)
...
for role_row in report.detail.roles:
    wip_commit_sha = role_row.wip_commit_sha
    if redactor is not None and wip_commit_sha is not None:
        wip_commit_sha = redactor(wip_commit_sha)
    roles_table.add_row(
        role_row.role,
        role_row.worker,
        str(role_row.attempt),
        role_row.status,
        NULL_MARKER if worker_session_id is None else str(worker_session_id),
        NULL_MARKER if wip_commit_sha is None else str(wip_commit_sha),
        role_row.created_at.isoformat(timespec="seconds"),
    )
```

### WR-02: `read_run_detail`'s `errors` list is a Python `str()` dict-repr, not a readable error message

**File:** `src/dark_factory/observability/run_detail.py:252-254`
**Issue:** `errors = [str(attempt.error) for attempt in attempts if attempt.error is not None]`. `RoleExecution.error` (`persistence/models.py:188`) is a `JSONB` column holding a dict — e.g. `{"status": "FAILED", "summary": "", "error": "<actual message>"}` from `_fail_role_before_worker`, or the *entire* `WorkerResult.model_dump()` (summary, questions, artifacts, worker_session_id, …) from the generic `ROLE_FAILED` arm in `runner.py`. `str()` on that dict produces a Python-repr blob (single-quoted keys, nested structures) rather than the extracted `error["error"]` message or even a clean `json.dumps`. `tests/db/test_run_report.py::test_a_failed_run_shows_its_error_text` only asserts the message substring is present somewhere in the string, so it passes even though the surfaced text is noisy repr output rather than the clean message OBS-01's "never hide a failure" section promises. This directly undercuts the phase's own stated goal: the failure *is* visible, but buried in clutter an operator has to parse by eye.
**Fix:**
```python
def _error_text(error: dict[str, Any]) -> str:
    message = error.get("error")
    return str(message) if message is not None else json.dumps(error)

errors = [
    _error_text(attempt.error) for attempt in attempts if attempt.error is not None
]
```

### WR-03: `read_quality_gate`'s blanket `except GitError: return None` cannot distinguish "wrong working directory" from "gate hasn't run yet"

**File:** `src/dark_factory/observability/run_detail.py:328-336`
**Issue:** `run_artifact_text` raises `GitCommandError` (a `GitError` subclass) both when the repository at `repo_root` simply isn't the run's repository (operator ran `status` from the wrong directory — "not a git repository" / "unknown revision") and when the run's working branch genuinely has no `verification/quality_gate.json` yet (a legitimate, common state: a run that never reached its terminal role). Both collapse to the identical rendered output: `Panel("no gate result\n-", title="quality_gate")`. An operator who runs `dark-factory status <id>` from the wrong directory gets no indication that the absence is a usage error rather than a fact about the run — exactly the "operator loses trust in the report" failure mode OBS-01 exists to prevent. The CLI docstring documents this as "by design," but it is still a usability trap with no distinguishing signal anywhere in the output.
**Fix:** At minimum, distinguish "no working branch" (already a separate `None` return) from a path/ref-resolution failure, e.g. by checking `repo_root` is a git repository (`git rev-parse --is-inside-work-tree`) before attempting the read, and surfacing a distinct marker (`"gate check skipped: not run from inside the run's repository"`) rather than silently reusing the "no gate result" wording used for the genuinely-not-run-yet case.

### WR-04: `scrub_artifact_text_in_place` can silently corrupt non-UTF-8 artifact content before it is committed

**File:** `src/dark_factory/artifacts/store.py:110-116`
**Issue:** `raw = path.read_text("utf-8", errors="replace")` replaces any invalid UTF-8 byte sequence with U+FFFD before redaction runs; if redaction changes anything (even unrelated to the invalid bytes), the file is rewritten with the replacement characters baked in (`path.write_text(scrubbed, encoding="utf-8")`), permanently losing the original bytes before `collect_role_artifacts` computes the checksum that is committed onto the PR branch (D-09/D-11). This mirrors `workers/cli_runtime.py::scrub_log_in_place`'s established convention for a *log* (where lossy decoding is an acceptable tradeoff), but here it is applied to a role's declared *artifact content*, which is expected to end up verbatim in a PR diff a human reviews. Every artifact type this phase's tests actually exercise is JSON/Markdown (safely UTF-8), so this is latent rather than exercised, but nothing in `collect_role_artifacts` or this function rejects a binary/non-UTF-8 artifact before the silent, unannounced rewrite happens.
**Fix:** Either reject non-UTF-8 artifact content outright (raise, so the role fails loudly instead of having its content silently altered) or skip the scrub (and log a warning) when `errors="replace"` actually introduced a replacement character, e.g.:
```python
raw_bytes = path.read_bytes()
try:
    raw = raw_bytes.decode("utf-8")
except UnicodeDecodeError:
    _log.warning("artifacts.scrub_skipped_non_utf8", path=str(path))
    return
```

## Info

### IN-01: `artifacts --show` has no size cap, unlike every other content-reading path in this project

**File:** `src/dark_factory/cli.py:433-441`, `src/dark_factory/git/committed.py:41-59`
**Issue:** `read_artifact_text` (the filesystem path) enforces `_MAX_ARTIFACT_BYTES` (256 KiB) and `collect_pr_diff` enforces `MAX_DIFF_BYTES` (1 MiB) with an explicit truncation marker. `run_artifact_text`/`read_committed` (the `git show` path this phase's `--show` flag uses) has no equivalent cap — `git show <branch>:<path>` returns the full blob regardless of size, and `cli.py` echoes it verbatim. An artifact that somehow grew very large (e.g. a role bug that appended to its own output across several attempts before the schema check caught it, or a future artifact type with no size validation) would dump an unbounded amount of text to the terminal/pipe. Low severity since this is an operator-invoked, single-target read, not an automated or adversary-triggered path, but it is an inconsistency worth closing given how deliberately every other content-reading path in this codebase caps its output.
**Fix:** Consider applying the same truncate-with-marker treatment `collect_pr_diff` already uses, or re-validate against `_MAX_ARTIFACT_BYTES` after the `git show` read and truncate with a visible marker rather than relying on terminal/pipe behavior to cope.

---

_Reviewed: 2026-10-06T05:46:41Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
