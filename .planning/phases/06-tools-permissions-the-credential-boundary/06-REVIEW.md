---
phase: 06-tools-permissions-the-credential-boundary
reviewed: 2026-09-19T06:23:38Z
depth: standard
files_reviewed: 37
files_reviewed_list:
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/BA.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - pyproject.toml
  - src/dark_factory/actions/builtins.py
  - src/dark_factory/artifacts/validation.py
  - src/dark_factory/config/loader.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/tools/__init__.py
  - src/dark_factory/tools/env.py
  - src/dark_factory/tools/mcp_transport.py
  - src/dark_factory/tools/native.py
  - src/dark_factory/tools/registry.py
  - tests/conftest.py
  - tests/db/test_artifact_commit_per_role.py
  - tests/db/test_artifact_handoff.py
  - tests/db/test_artifact_persistence.py
  - tests/db/test_artifact_schema_violation_fails_role.py
  - tests/db/test_capability_denied_fails_role.py
  - tests/db/test_four_role_pipeline.py
  - tests/integration/test_capability_denial_no_secret_leak.py
  - tests/integration/test_phase6_acceptance.py
  - tests/integration/test_pr_diff_excludes_artifacts.py
  - tests/integration/test_role_yaml_drives_behaviour.py
  - tests/integration/test_worker_env_boundary.py
  - tests/integration/test_write_scope_enforcement.py
  - tests/support/env_dump.py
  - tests/unit/test_artifact_paths.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_mcp_adapter.py
  - tests/unit/test_native_tool_contract.py
  - tests/unit/test_no_mcp_import_in_core.py
  - tests/unit/test_no_worker_name_leak.py
  - tests/unit/test_shell_execute.py
  - tests/unit/test_tool_registry.py
  - tests/unit/test_tool_registry_extensibility.py
  - tests/unit/test_worker_env.py
  - uv.lock
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-09-19T06:23:38Z
**Depth:** standard
**Files Reviewed:** 37 (+ uv.lock)
**Status:** issues_found

## Summary

Phase 6's headline mechanisms — `ToolRegistry.invoke()`'s deny-before-dispatch
gate, `build_worker_env`'s additive-allowlist credential boundary, and the MCP
transport's per-capability closure binding — are all correctly implemented and
well covered by targeted unit/integration tests. I read every listed source
file, ran the full non-`db` unit suite (437 passed), drove the MCP transport
interactively against a live `mcp` install to confirm the late-binding and
denial-path claims empirically, and traced `CapabilityDeniedError`'s message
construction end-to-end to confirm no capability keyword argument (e.g. a
`shell.execute` command line) ever reaches an event payload or an error
column.

One finding rises to BLOCKER: `config/loader.py`'s `roles_dir` field is used
to build a filesystem path with **no containment check against the repo
root**, unlike the sibling `instructions:` field three lines below it, which
the same function explicitly confirms stays "under the repo root (no `..`
escape)." I reproduced this empirically — a `.dark-factory.yaml` with
`roles_dir: ../outside` causes the loader to read and fully validate a role
definition (including its `tools:` grant list and `write_scope`) from a
directory entirely outside the repo. Since this is the same file whose
docstring explicitly treats `.dark-factory.yaml` as repo-controlled/untrusted
content, and since the whole Phase 6 deny-by-default model is only as
trustworthy as the `tools:`/`permissions.write_scope` values this loader
reads, this is a genuine gap in the credential-boundary story the phase is
named for, not a hypothetical one.

The remaining findings are two WARNINGs (an unhandled race in `shell_execute`'s
timeout-kill path, and an inconsistency in how the MCP transport handles a
config-bug exception versus an authorization exception) and two INFOs (a
pydantic default-value style nit, and a version-pin drift between
`pyproject.toml` and `CLAUDE.md`'s stack table).

## Critical Issues

### CR-01: `roles_dir` is not containment-checked, letting a role definition be read from outside the repo root

**File:** `src/dark_factory/config/loader.py:139-172`

**Issue:** `load_effective_config` builds `roles_dir = root / repo.roles_dir`
(line 139) and then `role_path = roles_dir / f"{role_name}.yaml"` (line 142)
directly from the `.dark-factory.yaml` document's own `roles_dir: str` field
(`config/repo_config.py`'s `RepoConfig.roles_dir`, an unconstrained string
with no path validator). Neither `roles_dir` nor `role_path` is ever resolved
and checked against `root` the way the *sibling* `instructions:` field is
three lines later — line 166-167 explicitly does
`instr_path = (role_path.parent / rd.instructions).resolve()` followed by
`if not instr_path.is_file() or not instr_path.is_relative_to(root): raise ConfigError(...)`.
This module's own docstring states the security posture this omission
violates: *"A role's `instructions` path is resolved relative to its role
YAML's own directory, confirmed to be a file **under the repo root** (no
`..` escape)"* — the identical guarantee is silently absent for the role
YAML file itself.

Because `.dark-factory.yaml` is explicitly treated elsewhere in this same
module as repo-controlled/untrusted input (`yaml.safe_load` only, worker/
action/capability names validated by membership "never `registry.get`" "for
the same reason" a repo-controlled name "must never become an arbitrary
lookup surface"), a `roles_dir` value that escapes the repo root is exactly
the class of input this module is designed to distrust, and it is not
distrusted here.

**Reproduction** (verified against this checkout, `uv run python`):

```python
# .dark-factory.yaml (inside the repo under review):
#   roles_dir: ../outside
# <repo>/../outside/BA.yaml (OUTSIDE the repo root entirely):
#   name: BA
#   worker: fake
#   instructions: ../repo/.dark-factory/instructions/ba.md   # escapes back in
#   tools: [repo.write, shell.execute, repo.read, repo.search,
#           artifacts.read, artifacts.write]
#   permissions:
#     write_scope: ["**"]
#   before: []
#   after: []
#   inputs: []
#   outputs: []
#   examples: []

from dark_factory.config.loader import load_effective_config
snapshot = load_effective_config(root)
# succeeds -- no ConfigError raised
assert snapshot["roles"][0]["tools"] == [
    "repo.write", "shell.execute", "repo.read", "repo.search",
    "artifacts.read", "artifacts.write",
]
assert snapshot["roles"][0]["permissions"] == {"write_scope": ["**"]}
```

This actually ran and printed the externally-sourced `tools`/`permissions`
values, persisted verbatim into `runs.workflow` by `start_run` (per
`orchestrator/runner.py`'s own docstring, the snapshot is "the only
configuration source thereafter"). A role's entire capability grant list and
write-scope — the exact two things TOOL-01/TOOL-03/ROLE-05 depend on — can
therefore be sourced from a location the repo's own `.gitignore`/branch
protection has no visibility into, by any actor who can get `roles_dir`
merged into `.dark-factory.yaml` (e.g. an external contributor's PR, in
whatever threat model this project runs Dark Factory against untrusted repo
content, as its own comments already assume for the unsafe-YAML-loader and
instructions-path guards).

Even short of a full successful load, a partially-escaping `roles_dir` still
lets `_safe_load_mapping`/`RoleDefinition.model_validate` read and parse an
arbitrary local YAML file's content into a `pydantic.ValidationError` message
that becomes part of `ConfigError`'s string — a lower-severity information
disclosure into the CLI's stderr/exit path if validation fails after the
read.

**Fix:** Resolve and containment-check `roles_dir` immediately after
computing it, mirroring the `instructions:` guard exactly:

```python
roles_dir = (root / repo.roles_dir).resolve()
if not roles_dir.is_relative_to(root):
    raise ConfigError(
        f".dark-factory.yaml: roles_dir escapes the repo root: {repo.roles_dir!r}"
    )
```

and, for defense in depth against any future relaxation of
`WorkflowConfig.roles`'s current enum-membership validator (which is the
only reason `role_name` itself is safe today), apply the same
`.resolve()` + `is_relative_to(root)` check to `role_path` before it is
opened.

## Warnings

### WR-01: `shell_execute`'s timeout-kill path can raise an unhandled `ProcessLookupError`

**File:** `src/dark_factory/tools/env.py:214-221`

**Issue:** On `subprocess.TimeoutExpired`, `shell_execute` calls
`os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` unconditionally. If the
child process (or its process group) exits on its own in the narrow window
between `communicate()` raising `TimeoutExpired` and this line running,
`os.getpgid`/`os.killpg` raises `ProcessLookupError`, which is not caught
anywhere in this function or in `ToolRegistry.invoke()`. That exception
would propagate out of a granted `shell.execute` call as a bare, undocumented
`ProcessLookupError` instead of the typed `ShellResult(timed_out=True, ...)`
every other exit path returns — an unhandled exception a role executor
(`orchestrator/runner.py`'s `_run_current_role`) is not prepared for at that
call site (it only catches `CapabilityDeniedError`/`ArtifactError` around
`collect_role_artifacts`, not around whatever the worker itself does with a
capability), so this would surface as a raw, uncaught crash of the `advance`
step rather than a `ROLE_FAILED` transition.

**Fix:**

```python
except subprocess.TimeoutExpired:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass  # already exited between the timeout and the kill
    stdout, stderr = proc.communicate()
    return ShellResult(exit_code=None, stdout=stdout, stderr=stderr, timed_out=True)
```

### WR-02: The MCP transport reshapes `CapabilityDeniedError` but not `UnknownCapabilityError`, losing the diagnostic asymmetrically

**File:** `src/dark_factory/tools/mcp_transport.py:158-167`

**Issue:** `_tool`'s `try/except` only catches `CapabilityDeniedError` and
re-raises it as a legible `ToolError(str(exc))`; the docstring justifies this
by name ("letting it fall through uncaught would surface to an MCP client as
an opaque `Error executing tool <name>` with no reason, discarding exactly
the... audit answer the denial exists to provide"). `UnknownCapabilityError`
— explicitly documented elsewhere in this package as "a configuration bug,
never an authorization decision" that must not be "confused with a denial"
or "surfaces as a bare `KeyError`" — gets exactly the opaque treatment the
docstring says is unacceptable for a denial, because nothing catches it here.
I confirmed this empirically: calling a capability that is advertised
(`granted_tools`) but has no registered implementation raises
`mcp.server.mcpserver.exceptions.UnexpectedToolError("Error executing tool
<name>")` with no indication a config bug (vs. a real denial, vs. an
implementation crash) occurred. This is an inconsistency in how the two
documented failure classes are surfaced over this transport, not a security
issue (no capability argument is exposed either way), but it undercuts the
stated design goal of a legible audit trail for exactly the case
(config bug) the package's own docstring says is the one that must never be
mistaken for something else.

**Fix:** Catch `UnknownCapabilityError` alongside `CapabilityDeniedError` (or
separately, preserving the distinct message) and re-raise it as `ToolError`
too, so a misconfigured role/registry mismatch is diagnosable over MCP the
same way a denial already is.

## Info

### IN-01: `RoleDefinition.permissions`'s pydantic default is a shared instance, not a `default_factory`

**File:** `src/dark_factory/config/loader.py:94`

**Issue:** `permissions: RolePermissions = RolePermissions()` constructs one
`RolePermissions` instance at class-definition time and reuses it as the
default for every `RoleDefinition` that omits `permissions:`. `RolePermissions`
is `frozen=True`, so this is not an aliasing bug in practice, but it is
inconsistent with every other list-typed field in the same two classes
(`tools`, `before`, `after`, `inputs`, `outputs`, `examples`,
`RolePermissions.write_scope` itself), which all correctly use
`Field(default_factory=...)` specifically to avoid a shared-mutable-default
trap. A future edit that adds a mutable field to `RolePermissions` (or
removes `frozen=True`) would silently reintroduce that trap here with no
warning, because this one field doesn't follow the pattern the rest of the
file established.

**Fix:** `permissions: RolePermissions = Field(default_factory=RolePermissions)`.

### IN-02: `mcp` version pin drifts from the documented stack table

**File:** `pyproject.toml:29-32`

**Issue:** The optional `mcp` extra is pinned `>=2.2,<3`, while
`.claude/CLAUDE.md`'s Technology Stack table (the project's own
stack-of-record) documents `mcp` (official SDK) as version `2.1.1`. `uv.lock`
resolves `mcp==2.2.0`, i.e. the code and lockfile are internally consistent
with `pyproject.toml`, but the stack doc is now stale relative to what is
actually pinned and shipped.

**Fix:** Update `.claude/CLAUDE.md`'s stack table to `mcp >= 2.2, < 3` (or
re-pin `pyproject.toml` to `2.1.x` if `2.1.1` was the deliberate choice) so
the two documents agree.

---

_Reviewed: 2026-09-19T06:23:38Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
