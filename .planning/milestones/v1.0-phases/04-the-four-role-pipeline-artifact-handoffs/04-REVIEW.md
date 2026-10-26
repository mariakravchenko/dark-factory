---
phase: 04-the-four-role-pipeline-artifact-handoffs
reviewed: 2026-09-13T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/BA.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - src/dark_factory/actions/builtins.py
  - src/dark_factory/artifacts/store.py
  - src/dark_factory/context/builder.py
  - src/dark_factory/roles/registry.py
  - src/dark_factory/workers/fake.py
  - tests/integration/test_phase4_acceptance.py
  - tests/integration/test_real_pipeline_zero_config.py
  - tests/support/fake_artifacts.py
  - tests/unit/test_fake_worker_synthesis.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-09-13T00:00:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

This is an incremental pass over the files changed since the prior `04-REVIEW.md`
(2026-09-12): the 04-05 gap-closure work (`FakeWorker` criterion-id threading —
`cac5b2c`, `48cc03d`, `7e2b69a`, `9a6dfc0`) and the three `fix(04):` commits that
landed after the prior review but were never themselves reviewed (`8d670ee`
CR-01, `c34ee77` WR-01, `b42d6c8` WR-02, plus the standalone flakiness fix
`ca602b3`).

**Prior findings verified as genuinely fixed, not just claimed:**

- **CR-01** (the shipped `.dark-factory.yaml` could not reach `COMPLETED` with
  no explicit script): `FakeWorker._default_script` is now artifact-aware,
  reading `context.outputs` and (as of 04-05) `context.inputs` to synthesize
  schema-valid files per declared output. `tests/integration/test_real_pipeline_zero_config.py`
  now drives the real, repo-root `.dark-factory.yaml` end-to-end with
  `DARK_FACTORY_FAKE_SCRIPT` unset and asserts `COMPLETED`, all four roles'
  declared outputs landing as `ArtifactReference` rows, *and* (04-05's
  addition) that BA's own emitted criterion ids are the ones that actually
  appear in `design.md`, `implementation_summary.json`, `test_report.json`,
  and `verdict.json` — closing the "two independently coinciding literals"
  gap a purely existence-based proof would have left open. Ran locally:
  `tests/unit/test_fake_worker_synthesis.py` — 11/11 pass; `ruff check` and
  `mypy --strict` clean on every file in this review's scope.
- **WR-01** (the `before:`/`after:` role hooks looked configurable but never
  gated anything): `prepare_role_context` and `store_role_artifacts` are
  dropped from every shipped role YAML's `before:`/`after:` list (QA
  correctly retains `collect_test_results`, the one genuine Phase 9
  placeholder), and `actions/builtins.py`'s docstrings now correctly document
  both as permanent no-ops rather than "until Phase N" placeholders.
- **WR-02** (three unused `Role` catalog entries): `roles/registry.py` now
  defines only `ba_role`, the one entry `DEFAULT_PIPELINE` actually consumes;
  `architect_role`/`developer_role`/`qa_role` are gone.

**Carried forward, out of this pass's scope:** the prior review's **IN-01**
(`collect_role_artifacts` hashes the *decoded* string rather than the raw
bytes `read_artifact_text` read) concerns `src/dark_factory/artifacts/validation.py`,
which is not in this incremental file set and was not touched by any commit
reviewed here. It remains open and should be picked up the next time
`validation.py` is in scope.

The 04-05 work itself (`_extract_criterion_ids`'s structural/textual
two-strategy dispatch, the `_is_valid_criterion_id` length/whitespace filter,
the `_MAX_CRITERION_IDS` cap, and threading the extracted id tuple through
every `_synthesize_machine_artifact`/`_synthesize_artifact_content` branch) is
well-designed and well-tested: dedup is correct, ordering is preserved and
verified end-to-end against a real BA-emitted id in
`test_real_pipeline_zero_config.py`, and the capped/rejected paths each have a
dedicated falsification test. One design gap remains, described below.

## Warnings

### WR-03: `FakeWorker`'s zero-config artifact synthesis hardcodes `Path.cwd()` instead of the orchestrator's threaded `repo_root`

**File:** `src/dark_factory/workers/fake.py:279-314` (specifically line 302)
**Issue:**

`_default_script` resolves the run's artifact tree with:

```python
root = run_root(Path.cwd(), UUID(run_id))
```

Every other consumer that needs the run root is handed `repo_root` as an
explicit parameter, independent of the process's current working directory:
`orchestrator/runner.py`'s `_advance_once`/`drive`/`_run_current_role` all
accept an optional `repo_root: Path | None`, defaulting to `Path.cwd()` only
when the caller passes `None` (`runner.py:322`, `:488`); `context/builder.py`'s
`build_role_context(session, repo_root, run_id, ...)` takes `repo_root`
explicitly and never touches `Path.cwd()` itself; `artifacts/validation.py`'s
`collect_role_artifacts(root, ...)` is handed the already-resolved root by its
caller.

`RoleContext` (the object `_default_script` actually receives) carries no
`repo_root` field at all — `context/builder.py`'s `RoleContext` model has
`run_id`, `role`, `outputs`, `artifacts_dir`, etc., but nothing that lets a
worker recover the `repo_root` the orchestrator resolved for this call. So
`_default_script` has no way to do the right thing even if it wanted to; it
silently assumes `Path.cwd() == repo_root`.

That assumption holds today only because every code path that exercises the
true no-script default happens to also make it hold: the CLI never exposes a
`repo_root` override (so `_advance_once`'s default `Path.cwd()` is always
correct), and both `tests/unit/test_fake_worker_synthesis.py` and
`tests/integration/test_real_pipeline_zero_config.py` explicitly `chdir`
(`monkeypatch.chdir(tmp_path)`) or set `cwd=_REPO_ROOT` on the subprocess
before invoking `FakeWorker`. If a future caller ever supplies a `repo_root`
that differs from the process's cwd — the exact scenario the `repo_root`
parameter exists for, and one CLAUDE.md's durability requirement ("any
process on any machine can resume exactly where a previous one stopped")
implies will eventually happen — `_default_script` would write its
synthesized files under `Path.cwd()/.dark-factory/runs/<run_id>/...` while
`collect_role_artifacts` reads them back from
`repo_root/.dark-factory/runs/<run_id>/...`. The write and read would
silently target two different directories: `read_artifact_text` would raise
`MissingArtifactContentError` for every declared output, and the role would
fail with "declares output X but reported no matching artifact" — a confusing
failure mode with no indication the actual cause is a cwd/repo_root mismatch.
This is exactly the class of gap CR-01 closed for the "no explicit script"
case; it now exists one layer deeper, for the "repo_root != cwd" case.

**Fix:** Thread `repo_root` to where `_default_script` can see it — either
add a `repo_root: str` field to `RoleContext` (populated from
`build_role_context`'s own `repo_root` parameter, which it already has) and
have `_default_script` read `getattr(context, "repo_root", None)` before
falling back to `Path.cwd()`, or have `orchestrator/runner.py` pass
`repo_root` as an explicit keyword to `worker.execute`/`worker.resume` so
every worker adapter (not just `FakeWorker`) receives it uniformly. Add a
regression test that calls `FakeWorker().execute(context)` with `repo_root`
(however it's threaded) pointing at a directory that is deliberately *not*
`Path.cwd()`, and asserts the synthesized artifacts land under the supplied
root, not the cwd.

---

_Reviewed: 2026-09-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
