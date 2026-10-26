---
phase: 03-configuration-driven-pipeline
reviewed: 2026-09-10T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - src/dark_factory/actions/__init__.py
  - src/dark_factory/actions/registry.py
  - src/dark_factory/actions/context.py
  - src/dark_factory/actions/builtins.py
  - src/dark_factory/workers/registry.py
  - src/dark_factory/workflows/pipeline.py
  - src/dark_factory/config/loader.py
  - src/dark_factory/config/repo_config.py
  - src/dark_factory/cli.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - .dark-factory.yaml
  - .dark-factory/roles/BA.yaml
  - .dark-factory/roles/QA.yaml
  - .dark-factory/instructions/ba.md
  - .dark-factory/instructions/qa.md
findings:
  critical: 0
  warning: 3
  info: 5
  total: 8
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-09-10
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 3 wires configuration-driven pipeline construction: `.dark-factory.yaml` +
role YAML + instruction Markdown are resolved by `config/loader.load_effective_config`
into a JSON snapshot, persisted to `runs.workflow` at run creation, and replayed
on every resume via `pipeline_from_snapshot`. The `ActionRegistry` /
`WorkerRegistry` allowlists gate hook and worker names by membership.

The core invariants hold up well:

- **YAML safety:** all parsing goes through `_safe_load_mapping` → `yaml.safe_load`;
  no `yaml.load` / Loader argument anywhere.
- **Snapshot determinism:** `cli.run` is the only caller of `load_effective_config`;
  `cli.resume`, `drive`, `advance`, and `_advance_once` rebuild the pipeline from
  `state.workflow` and never touch a config file. `orchestrator/*` and
  `workflows/pipeline.py` do not import `config.loader`.
- **Role ≠ Worker:** no role-name branching was reintroduced. `_role_definition`
  is a lookup keyed on the role value; `_run_current_role` branches only on
  `Signal` and on the persisted `RESUMING` marker.
- **Credential boundary:** the snapshot is redacted on write inside `create_run`
  (`redact(workflow, ...)`); worker/action contexts carry only run/role/worker/
  attempt/task/answer, no environment.

Findings below are hardening gaps and robustness defects, not invariant breaks.
The highest-value items: `roles_dir` is not defended against path traversal even
though the sibling instruction-path check is (WR-01), and duplicate
`workflow.roles` entries are silently accepted and produce a run that loops until
the drive loop aborts (WR-02).

## Warnings

### WR-01: `roles_dir` and the role-YAML path are not defended against `..` / absolute-path traversal

**File:** `src/dark_factory/config/loader.py:116-121`
**Issue:** `roles_dir = root / repo.roles_dir` and
`role_path = roles_dir / f"{role_name}.yaml"` are passed straight to
`_safe_load_mapping` with no containment check. `repo.roles_dir` is a
repo-controlled string with no validator in `RepoConfig` (default
`.dark-factory/roles`). If it is absolute (`roles_dir: /etc`) Python's `/`
operator discards `root` entirely; if it is relative-with-dotdot
(`roles_dir: ../../../../some/dir`) the OS resolves `..` at `read_text` time.
Either way the loader reads and YAML-parses an arbitrary `*.yaml` file outside
the repo root (file must be named after a `RunStatus` role value, e.g.
`BA.yaml`, and parse as a mapping to progress; a `ValidationError` on it is
reflected back into the `ConfigError` message on stderr). The module docstring
explicitly claims the opposite posture ("confirmed to be a file *under the repo
root* (no `..` escape)") and the instruction path *is* checked with
`is_relative_to(root)` at line 135 — `roles_dir` is the inconsistent gap. This
matters because `.dark-factory.yaml` is validated "as if external" per the
module's own contract.
**Fix:** resolve and contain the roles directory and each role path before
reading, mirroring the instruction-path check:
```python
roles_dir = (root / repo.roles_dir).resolve()
if not roles_dir.is_dir() or not roles_dir.is_relative_to(root):
    raise ConfigError(f".dark-factory.yaml: roles_dir escapes the repo root: {roles_dir}")
...
role_path = (roles_dir / f"{role_name}.yaml").resolve()
if not role_path.is_file() or not role_path.is_relative_to(root):
    raise ConfigError(f"role file not found under the repo root: {role_path}")
```

### WR-02: duplicate `workflow.roles` entries are accepted and hang the run

**File:** `src/dark_factory/config/repo_config.py:52-61`, `src/dark_factory/workflows/pipeline.py:43-48,95-101`
**Issue:** `WorkflowConfig._roles_are_legal_statuses` validates that each entry
is a legal `RunStatus` value but never checks uniqueness. `roles: [BA, BA]`
passes, `load_effective_config` emits a two-entry snapshot, and
`pipeline_from_snapshot` builds `nodes=(RoleNode("BA"), RoleNode("BA"))`.
`Pipeline.index_of("BA")` always returns `0`, so `next_node(pipeline, "BA")`
returns `nodes[1]` — another `"BA"` — and `transition()` computes
`next_status = RunStatus("BA")`. The run never leaves `BA`: `_run_current_role`
re-invokes the worker every iteration, updating the same `role_executions` row,
until `drive` hits `_MAX_DRIVE_ITERATIONS` and raises `DriveLoopExhausted` (or the
shared `FakeWorker` script exhausts and raises `ScriptExhaustedError`). A config
mistake should be rejected at load, not turned into a spinning run.
**Fix:** reject duplicates in the validator:
```python
@field_validator("roles")
@classmethod
def _roles_are_legal_and_unique(cls, value: list[str]) -> list[str]:
    bad = [r for r in value if r not in _LEGAL_ROLE_VALUES]
    if bad:
        raise ValueError(...)
    dupes = sorted({r for r in value if value.count(r) > 1})
    if dupes:
        raise ValueError(f"workflow.roles has duplicate entries: {dupes}")
    return value
```
(`current_step` ordinal arithmetic in the pure transition function also assumes
distinct role names, so uniqueness is a precondition, not a nicety.)

### WR-03: instruction file is fully read into memory before the size cap is enforced

**File:** `src/dark_factory/config/loader.py:140-144`
**Issue:** `text = instr_path.read_text("utf-8")` loads the entire
repo-controlled instruction file before `len(text.encode("utf-8")) >
_MAX_INSTRUCTION_BYTES` is checked. The 64 KiB cap exists "so the snapshot row
stays small" but does nothing to stop a multi-gigabyte `instructions:` target
from being read into memory first (a malformed/hostile repo can point
`instructions:` at any file under the root, including a large binary or a
generated artifact). The `.encode("utf-8")` round-trip on an already-decoded
string also double-allocates and can disagree with the on-disk byte count under
Unicode normalization.
**Fix:** check size before reading:
```python
if instr_path.stat().st_size > _MAX_INSTRUCTION_BYTES:
    raise ConfigError(f"{instr_path}: instruction file exceeds {_MAX_INSTRUCTION_BYTES} bytes")
text = instr_path.read_text("utf-8")
```

## Info

### IN-01: dead `except` clause — `start_run` cannot raise `ConfigError`

**File:** `src/dark_factory/cli.py:178-182`
**Issue:** `except (UnresolvableSourceError, SourceNotSupportedError, ConfigError)`
wraps the `start_run` call, but `start_run` only runs `classify` / `load` /
`create_run` and imports nothing from `config.loader`; `ConfigError` is already
handled by the preceding `try` around `load_effective_config`. The clause is
harmless (it would exit 2, which is correct) but misleading about where config
errors originate.
**Fix:** drop `ConfigError` from the second tuple, or add a comment noting it is
defensive-only.

### IN-02: registry `register()` silently overwrites an existing name

**File:** `src/dark_factory/actions/registry.py:36-37`, `src/dark_factory/workers/registry.py:53-54`
**Issue:** both `register` implementations do `self._map[name] = fn` with no
collision check. A duplicated or typo'd registration (e.g. two plugins both
claiming `"collect_diff"`, or `actions/__init__.py` re-imported in a test that
also registers) silently wins last-write with no diagnostic — the opposite of
the "reject at run creation rather than becoming an arbitrary import surface"
intent stated in the module docstring.
**Fix:** raise on re-registration of an already-present name (or log a warning),
so a collision is visible.

### IN-03: `RepoConfig.version` accepts any integer

**File:** `src/dark_factory/config/repo_config.py:102`
**Issue:** `version: int = 1` with no validator. `version: 2` (a future,
possibly incompatible schema) is accepted, snapshotted verbatim, and executed as
if understood. A forward-incompatible config should fail closed at load.
**Fix:** `version: Literal[1] = 1`, or a `field_validator` that rejects unknown
versions with a clear "unsupported .dark-factory.yaml version" message.

### IN-04: snapshot-wide `redact()` can silently rewrite operational config values

**File:** `src/dark_factory/persistence/mutations.py:183`, `src/dark_factory/config/loader.py:145-158`
**Issue:** `create_run` runs `redact(workflow, ...)` with `patterns=True` over the
*entire* effective-config snapshot, including operationally-significant strings:
`quality_gate.commands`, `repository.base_branch`, and each role's inlined
`instruction_text`. The pattern table (`events/redaction.py`) will, for example,
rewrite any bare 40- or 64-hex string in an instruction file to
`[redacted:github_token]` (unless preceded by `commit`/`sha`/`revision`), and
rewrite a `token: <value>` / `postgres://user:pass@host` substring in a
quality-gate command. Redaction is one-way and there is no signal, so a
false-positive silently changes what Phase 9 executes or what a worker reads —
on every resume, since the mangled value is what was persisted. The shipped
config is unaffected (commands are `uv run pytest -q` / `uv run ruff check .`;
"tokens," in the instruction prose is not a `\btoken\b:` match), so this is a
latent hazard for future configs rather than a current defect.
**Fix:** either scope `patterns=True` redaction to the free-text/payload
sub-trees and use exact-value-only `scrub_known_values` for `quality_gate` /
`repository` / `retry` / `publishing`, or add a load-time assertion that
`redact(snapshot) == snapshot` for the non-instruction fields and fail with a
"config value collides with a secret pattern" `ConfigError`.

### IN-05: `before` hooks re-run on every resume and every retry attempt

**File:** `src/dark_factory/orchestrator/runner.py:414-434`
**Issue:** `_run_hooks("before")` executes unconditionally each time
`_run_current_role` is entered — including a post-answer `RESUMING` resume and a
second/third attempt of the same role. The hooks are no-ops in Phase 3 so there
is no present bug, but the structure bakes in "before actions are not
idempotent-by-construction": when `prepare_role_context` becomes real (Phase 4)
a resumed role will re-run its context preparation. Worth a deliberate decision
(guard on `latest.status`, or document that before-hooks must be idempotent)
before Phase 4 builds on it.
**Fix:** none required now; note the resume/retry semantics in the hook contract
or gate the `before` pass on first entry to the attempt.

---

## Narrative Findings (AI reviewer)

All findings above are narrative (direct code review). No `<structural_findings>`
block was supplied with this review.

---

_Reviewed: 2026-09-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
