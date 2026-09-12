---
phase: 04-the-four-role-pipeline-artifact-handoffs
reviewed: 2026-09-12T00:00:00Z
depth: standard
files_reviewed: 54
files_reviewed_list:
  - .dark-factory.yaml
  - .dark-factory/instructions/architecture.md
  - .dark-factory/instructions/development.md
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/BA.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - migrations/env.py
  - migrations/versions/0004_artifacts.py
  - src/dark_factory/artifacts/__init__.py
  - src/dark_factory/artifacts/paths.py
  - src/dark_factory/artifacts/store.py
  - src/dark_factory/artifacts/validation.py
  - src/dark_factory/config/loader.py
  - src/dark_factory/context/__init__.py
  - src/dark_factory/context/builder.py
  - src/dark_factory/domain/artifacts.py
  - src/dark_factory/domain/status.py
  - src/dark_factory/input/loaders.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/roles/registry.py
  - src/dark_factory/workers/fake.py
  - tests/conftest.py
  - tests/db/test_artifact_handoff.py
  - tests/db/test_artifact_persistence.py
  - tests/db/test_artifact_schema_violation_fails_role.py
  - tests/db/test_context_builder_retry_isolation.py
  - tests/db/test_four_role_pipeline.py
  - tests/db/test_human_interactions_schema.py
  - tests/db/test_migrations.py
  - tests/db/test_pause_mechanism_generic.py
  - tests/integration/test_exit_codes.py
  - tests/integration/test_fresh_process_resume.py
  - tests/integration/test_heartbeat_slow_step.py
  - tests/integration/test_lease_expiry_reclaim.py
  - tests/integration/test_no_txn_across_worker.py
  - tests/integration/test_phase4_acceptance.py
  - tests/integration/test_resume_with_answer.py
  - tests/integration/test_single_owner_race.py
  - tests/integration/test_spec_source_starts_a_run.py
  - tests/integration/test_status_cli.py
  - tests/integration/test_unsupported_source.py
  - tests/integration/test_walking_skeleton.py
  - tests/support/fake_artifacts.py
  - tests/unit/test_artifact_models.py
  - tests/unit/test_artifact_paths.py
  - tests/unit/test_context_builder.py
  - tests/unit/test_loaders.py
  - tests/unit/test_no_tree_walk.py
  - tests/unit/test_no_worker_name_leak.py
  - tests/unit/test_persistence.py
  - tests/unit/test_single_mutation_path.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-09-12T00:00:00Z
**Depth:** standard
**Files Reviewed:** 54
**Status:** issues_found

## Summary

The four-role pipeline (BA → ARCHITECTURE → DEVELOPMENT → QA), the `artifacts`
table + filesystem tier, `ContextBuilder`, and `spec:` intake are all
internally consistent and well-covered by the 13 repointed pre-existing tests,
which correctly use the new `config_root_factory(roles=...)` fixture and the
`tests/support/fake_artifacts.py` helpers. The D-09 schema-validation gate
(`collect_role_artifacts`), the D-06 verdict-authoritative-over-prose
invariant, and the CTX-02 no-tree-walk guard are all exercised thoroughly and
correctly.

The one serious defect is architectural rather than local: this repo's own
shipped `.dark-factory.yaml` (the four-role pipeline with machine-artifact
outputs on every role) cannot actually be driven to completion by
`dark-factory run <source>` run with no `DARK_FACTORY_FAKE_SCRIPT` set —
`FakeWorker`'s true zero-config default result reports no artifacts, so the
first role's D-09 validation gate fails it immediately. Every integration test
that exercises a real CLI invocation is aware of this and deliberately
substitutes a throwaway one-role config tree to route around it (see the
repeated "the unscripted FakeWorker cannot satisfy" comments across
`tests/integration/*.py`), which means the scenario CLAUDE.md's own quality
bar names — "genuinely runnable against a real repository" — is never
actually exercised against this repository. See CR-01.

## Critical Issues

### CR-01: The shipped `.dark-factory.yaml` cannot be driven to completion by the documented zero-config path

**File:** `src/dark_factory/workers/fake.py:14-18` (also `.dark-factory.yaml:10-18`, `.dark-factory/roles/BA.yaml:17`)
**Issue:**

`FakeWorker`'s module docstring makes an explicit, load-bearing claim:

> "Phase 4 ships a multi-role pipeline (`.dark-factory.yaml`'s
> `workflow.roles`), and an operator running `dark-factory run ...` with no
> `DARK_FACTORY_FAKE_SCRIPT` must be able to drive every role to completion
> with no explicit script."

This is false for the pipeline this repo actually ships. `_default_script()`
(`fake.py:53-60`) returns a `WorkerResult` with `artifacts=[]` (the
`WorkerResult.artifacts` field's default). This repo's `.dark-factory.yaml`
declares `workflow.roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]`, and `BA.yaml`
declares `outputs: [requirements.md, acceptance_criteria.json]`. When the true
default (no explicit script, no `DARK_FACTORY_FAKE_SCRIPT`) is used, the BA
step's `WorkerResult` reports `COMPLETED` with zero artifacts;
`orchestrator/runner.py`'s `_run_current_role` then calls
`collect_role_artifacts` (`artifacts/validation.py:48-106`), which raises
`ArtifactContractError` for the first declared output filename with no
matching reported artifact, forcing the signal to `ROLE_FAILED`
(`runner.py:552-563`). The run ends `FAILED` and the CLI exits 1.

This is not a hypothetical edge case: every integration test that spawns the
real CLI against this repo's config explicitly avoids it. For example
`tests/integration/test_walking_skeleton.py:53-57`:

```python
# A throwaway one-role [BA] config tree, not this repo's own shipped
# .dark-factory.yaml (Phase 4 ships a real two-role pipeline whose BA
# declares machine-artifact outputs the true-default FakeWorker cannot
# satisfy).
```

and the same comment (worded per-file) recurs in
`test_exit_codes.py:50-53`, `test_fresh_process_resume.py:60-63`,
`test_heartbeat_slow_step.py:184-187`, `test_lease_expiry_reclaim.py:115-118`,
`test_no_txn_across_worker.py:136-138`, `test_resume_with_answer.py:84-86`,
`test_single_owner_race.py:122-124`, `test_spec_source_starts_a_run.py:60`.
No test in the suite drives this repo's real `.dark-factory.yaml` end-to-end
through `drive()`/the CLI with the true default (unscripted) `FakeWorker`.
`repo_config_snapshot` (`tests/conftest.py:394-399`) only loads and asserts
the snapshot resolves — it is never handed to `start_run`/`drive`.

Given `fake` is presently the *only* registered worker (Claude Code /
Copilot / Hermes adapters land in later phases), this means the primary,
documented, zero-setup invocation of the tool against its own repository —
exactly the scenario CLAUDE.md's "Quality bar: ... genuinely runnable against
a real repository" names — is broken today, and the docstring's claim about
it is simply incorrect.

**Fix:** Either (a) correct the docstring's claim to scope it honestly (e.g.
"an operator running against a pipeline whose roles declare no machine
artifact outputs" or "against the throwaway single-role example tree"), or
(b) make `_default_script()` artifact-aware: instead of one fixed
`WorkerResult`, look up the current role's declared `outputs` from the
context passed to `execute()` and synthesize a minimal, schema-valid file per
declared machine-artifact filename (writing it under
`context.artifacts_dir` and returning matching `ArtifactRef`s), the same way
`tests/support/fake_artifacts.py::four_role_script` already does by hand.
Whichever fix is chosen, add one test that runs `dark-factory run` against
this repo's actual `.dark-factory.yaml` (not a throwaway tree) with
`DARK_FACTORY_FAKE_SCRIPT` unset and asserts it reaches `COMPLETED` — the gap
this review found is exactly that no such test currently exists.

## Warnings

### WR-01: `before`/`after` role hooks are declared everywhere but do not gate the behavior they name

**File:** `src/dark_factory/orchestrator/runner.py:499-525`
**Issue:** Every shipped role YAML declares `before: [prepare_role_context]`
and `after: [store_role_artifacts]` (`.dark-factory/roles/BA.yaml:13-14`,
`ARCHITECTURE.yaml:13-14`, `DEVELOPMENT.yaml:26-27`, `QA.yaml:14-15`), and a
reader of the config would reasonably conclude that removing
`prepare_role_context` from a role's `before:` list disables context
assembly, or that removing `store_role_artifacts` from `after:` disables
artifact persistence. Neither is true: `build_role_context` is called
unconditionally at `runner.py:504-508`, *before* `_run_hooks("before")` ever
runs (`runner.py:525`), and `collect_role_artifacts` /
`apply_transition(..., artifact_references=...)` run unconditionally after
`_run_hooks("after")` (`runner.py:542-563`, `623-646`) regardless of whether
`store_role_artifacts` is even present in that role's `after:` list. The
named actions are permanently no-op stubs. The result is a config surface
that looks configurable but is not: a role YAML author who deletes these hook
names (or a future contributor who "implements" `store_role_artifacts` in
`actions/builtins.py` expecting it to be the actual write path) will be
surprised.
**Fix:** Either wire the actual context-build / artifact-collection calls
through the named action hooks (so the config genuinely controls them), or
drop the two hook names from the shipped role YAMLs and document plainly that
context assembly and artifact persistence are unconditional orchestrator
behavior, not something roles opt into.

### WR-02: `roles/registry.py`'s three new `Role` objects have no consumer

**File:** `src/dark_factory/roles/registry.py:44-70`
**Issue:** This phase added `architect_role`, `developer_role`, and
`qa_role` beside the pre-existing `ba_role`, and the module docstring frames
this as "Phase 4 has now added Architect, Developer and QA beside it." A
repo-wide search shows only `ba_role` is ever imported
(`src/dark_factory/workflows/pipeline.py:17,51`, for `DEFAULT_PIPELINE`); the
three new objects are referenced nowhere in `src/` or `tests/`. The module's
own docstring says the real source of truth is
`.dark-factory/roles/*.yaml` ("`.dark-factory/roles/*.yaml` is what actually
resolves their instructions, tools and artifact contracts"), which makes
these three additions pure dead weight this phase introduced with no
functional purpose, and a future drift risk: nothing keeps this catalog's
`name`/`worker`/`description` triples in sync with the YAML files that are
actually authoritative.
**Fix:** Either delete the three unused `Role` objects (keep only `ba_role`,
which `DEFAULT_PIPELINE` genuinely needs), or give the catalog a real
consumer (e.g. a `dark-factory roles` listing command) so it stops being
inert documentation duplicated from the YAML files.

## Info

### IN-01: `checksum` recomputation trusts a decode/re-encode round trip rather than the original bytes

**File:** `src/dark_factory/artifacts/validation.py:85-101`
**Issue:** `collect_role_artifacts` computes the persisted `checksum` from
`checksum(text.encode("utf-8"))`, where `text` is the *decoded* string
`read_artifact_text` returned (`store.py:23-47`), rather than hashing the raw
bytes read from disk directly. For well-formed UTF-8 without a byte-order
mark this round-trips losslessly, so today's behavior is correct, but the
checksum path is one indirection away from the actual file bytes for no
functional benefit — a future change to `read_artifact_text` (e.g. BOM
stripping, newline normalization) would silently change what gets hashed
without anyone touching `validation.py`. `write_artifact_text` (`store.py:60-64`)
already hashes the raw bytes it writes, so the two checksum computations use
different code paths for what should be the same value.
**Fix:** Not urgent given current behavior is correct; consider having
`read_artifact_text` return (or `collect_role_artifacts` separately read) the
raw bytes for hashing, so both write and read paths hash the same
representation through one code path.

---

_Reviewed: 2026-09-12T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
