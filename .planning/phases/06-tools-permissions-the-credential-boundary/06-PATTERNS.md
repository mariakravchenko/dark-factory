# Phase 6: Tools, Permissions & the Credential Boundary - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 9 (new) + 3 (modified)
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/dark_factory/tools/__init__.py` | error-hierarchy module | request-response | `src/dark_factory/git/__init__.py` (error hierarchy shape, not read this session but referenced by `git/client.py`'s `from dark_factory.git import GitCommandError`) / `src/dark_factory/artifacts/__init__.py` (error classes co-located with package) | role-match |
| `src/dark_factory/tools/registry.py` (`ToolRegistry`, `invoke()`, 7 capability impls) | service / registry | request-response, deny-by-default gate | `src/dark_factory/workers/registry.py` (`WorkerRegistry`) and `src/dark_factory/actions/registry.py` (`ActionRegistry`) | exact (registry idiom) |
| `src/dark_factory/tools/env.py` (`build_worker_env()`) | utility | file-I/O adjacent / subprocess env construction | `src/dark_factory/git/client.py::git_env()` | exact |
| `src/dark_factory/tools/env.py` (`shell.execute` implementation, `subprocess.Popen`) | service | process-spawn / request-response | `src/dark_factory/git/client.py::run_git()` | exact |
| `src/dark_factory/tools/mcp_transport.py` (`build_mcp_server()`) | provider / adapter (optional) | event-driven (MCP tool calls) | no direct in-repo analog — first MCP integration; use RESEARCH.md Pattern 3 code example as primary source, structured like a registry factory (`WorkerRegistry`-style name-to-callable, but building a third-party `MCPServer` object instead of a dict) | no analog (new territory) |
| `src/dark_factory/events/catalog.py` (add `CAPABILITY_DENIED` member) | model / enum | event-driven | same file, existing `QUESTION_CREATED`/`RUN_PAUSED` additions (Phase 2) and `WIP_COMMIT_CREATED` (Phase 5) | exact |
| `src/dark_factory/orchestrator/runner.py` (catch `CapabilityDeniedError` alongside `except GitError`) | controller / orchestration | request-response, error-handling | same file's existing `except GitError as exc:` block at line 857 (and the worktree-cleanup one at line 609) | exact |
| `src/dark_factory/artifacts/validation.py` / `src/dark_factory/artifacts/store.py` call sites (migrate `collect_role_artifacts` reads onto `registry.invoke('artifacts.read', ...)`) | service | CRUD (read) | same files, current `read_artifact_text` / `collect_role_artifacts` call sites | exact (modification, not new file) |
| `tests/unit/test_tool_registry.py` | test | request-response | `tests/unit/test_no_environ_copy.py` (guard-style unit test) + a CRUD-style grant/deny table test | role-match |
| `tests/unit/test_tool_registry_extensibility.py` | test | request-response | same as above; synthetic-capability registration proof, mirrors `WorkerRegistry.register()` tests if any exist, else modeled directly on `ActionRegistry`'s `register()`/`get()` shape | role-match |
| `tests/integration/test_worker_env_boundary.py` | test (integration, real subprocess) | process-spawn | `tests/support/subprocess_runner.py::child_env()` + its usage pattern (spawn a real child, inspect its env) | exact |
| `tests/unit/test_no_mcp_import_in_core.py` | test (AST import-graph guard) | static-analysis | `tests/unit/test_orchestrator_no_live_config_read.py` (`_transitive_closure`, `_dark_factory_imports`) — **must be extended, not copied verbatim** (see Pitfall 4 in RESEARCH.md: needs a second AST helper that scans for third-party `import mcp` inside each reachable module's own source, not just `dark_factory.*` prefixed imports) | role-match (needs adaptation) |
| `tests/unit/test_mcp_adapter.py` (or `tests/integration/`) | test (optional, `mcp`-gated) | event-driven | RESEARCH.md Pattern 4 (`mcp.Client` in-memory testing) — no in-repo analog | no analog (new territory) |
| `pyproject.toml` (`[project.optional-dependencies] mcp = [...]`) | config | — | existing `[dependency-groups]` / `[project.optional-dependencies]` structure already in `pyproject.toml` | exact |

## Pattern Assignments

### `src/dark_factory/tools/registry.py` (service/registry, request-response)

**Analog:** `src/dark_factory/workers/registry.py` (`WorkerRegistry`) and `src/dark_factory/actions/registry.py` (`ActionRegistry`)

**Imports pattern** (`workers/registry.py` lines 33-38):
```python
from collections.abc import Callable
from typing import NoReturn

from dark_factory.domain.worker import WorkerCapabilities, WorkerResult
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker
```
Follow the same shape: `from collections.abc import Callable`, TYPE_CHECKING-guarded imports for payload types (mirrors `actions/registry.py` lines 17-21 using `TYPE_CHECKING` for `ActionContext`).

**Core registry pattern — name-to-callable dict, membership check via `__contains__`, typed `KeyError` subclass for lookup failure** (`workers/registry.py` lines 43-67, and `actions/registry.py` lines 26-47):
```python
class UnknownWorkerError(KeyError):
    """Raised by WorkerRegistry.get for a name with no registered factory."""

class WorkerRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], CodingWorker]] = {}

    def register(self, name: str, factory: Callable[[], CodingWorker]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> CodingWorker:
        try:
            factory = self._factories[name]
        except KeyError:
            raise UnknownWorkerError(name) from None
        return factory()

    def __contains__(self, name: object) -> bool:
        return name in self._factories
```
`ToolRegistry.invoke()` should follow this exact dict-lookup discipline but add the deny-by-default grant check *before* dispatch (RESEARCH.md Pattern 1, quoted verbatim there):
```python
class CapabilityDeniedError(RuntimeError):
    """Raised by ToolRegistry.invoke() when `role` was not granted `capability`."""

class ToolRegistry:
    def invoke(self, role: str, capability: str, granted: list[str], **kwargs: object) -> object:
        if capability not in granted:
            raise CapabilityDeniedError(
                f"role {role!r} invoked {capability!r} without a grant"
            )
        return self._impls[capability](**kwargs)
```

**Extensibility pattern (TOOL-02)** — `default_registry.register("name", fn)` at import time requires zero orchestrator change (`workers/registry.py` lines 112-121, `actions/registry.py` line 49 `default_registry = ActionRegistry()`): a module-level `default_registry = ToolRegistry()` plus per-capability `default_registry.register(...)` calls at the bottom of `registry.py`.

**Error handling pattern:** typed exception subclassing a builtin (`UnknownWorkerError(KeyError)`, `UnknownActionError(KeyError)`) — `CapabilityDeniedError` should subclass `RuntimeError` per RESEARCH.md Pattern 1 (a denial is a runtime authorization failure, not a lookup-miss).

---

### `src/dark_factory/tools/env.py` — `build_worker_env()` (utility, subprocess-env construction)

**Analog:** `src/dark_factory/git/client.py::git_env()` (lines 60-71) — this is the exact, named template per D-09/D-13 and RESEARCH.md Pattern 2.

**Full extraction (git/client.py lines 30-71):**
```python
GIT_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "TMPDIR", "TEMP", "TMP", "SSL_CERT_FILE", "SSL_CERT_DIR", "SYSTEMROOT",
)

def git_env() -> dict[str, str]:
    """... built by comprehension over the allowlist; the parent process
    environment is never duplicated wholesale."""
    return {
        name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ
    } | GIT_IDENTITY_ENV
```
`build_worker_env(role, env_var_name, value)` should mirror this shape exactly: comprehension over an explicit allowlist tuple, `|` (or a conditional key-set) to layer in exactly one named credential when `value is not None`, **never** `os.environ.copy()` (guarded by `tests/unit/test_no_environ_copy.py` — any new module must not trip its `_FORBIDDEN_SNIPPETS` list, see below).

**A second close analog for the "add named extras conditionally" idiom:** `tests/support/subprocess_runner.py::child_env()` (lines 60-91) — shows the pattern for adding *optional* named values one at a time (`if crash_after is not None: env["..."] = crash_after`), which is exactly the shape `build_worker_env`'s single optional `env_var_name`/`value` pair needs.

**Guard to satisfy:** `tests/unit/test_no_environ_copy.py` — greps all of `src/dark_factory/**/*.py` for `os.environ.copy(`, `{**os.environ`, `dict(os.environ)`, etc. `build_worker_env()` must use the comprehension form, never any of these forbidden snippets.

---

### `src/dark_factory/tools/env.py` — `shell.execute` capability implementation (service, process-spawn)

**Analog:** `src/dark_factory/git/client.py::run_git()` (lines 74-117)

**Core pattern (explicit argv list, `subprocess.run`/`Popen`, no `shell=True`, explicit timeout):**
```python
def run_git(args, *, cwd, check=True, timeout=120, env_extra=None):
    env = git_env()
    if env_extra:
        env = {**env, **env_extra}
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitCommandError(tuple(args), result.returncode, result.stderr, cwd=cwd)
    return result
```
`shell.execute`'s implementation should call `subprocess.Popen`/`subprocess.run` with an explicit argv list (never a concatenated string, never `shell=True`) and `env=build_worker_env(role, ...)`, matching this exact discipline (D-11, RESEARCH.md Security Domain "Shell-injection" row).

---

### `src/dark_factory/orchestrator/runner.py` — `CapabilityDeniedError` catch (controller, error-handling)

**Analog:** same file, existing `except GitError as exc:` block (line 857 onward):
```python
except GitError as exc:
    signal = Signal.ROLE_FAILED
    outcome = {**outcome, "error": str(exc)}
    # Mirror the ArtifactError branch above: a role that fails at
    # the commit/push step must not leave `artifacts` rows
    # referencing content whose durability guarantee ... never
    # actually landed ...
    artifact_writes = []
```
D-06 attaches `except CapabilityDeniedError` alongside this exact block, producing the same `Signal.ROLE_FAILED` / outcome-dict-with-`error`-key shape. D-07/D-08 additionally require emitting a `CAPABILITY_DENIED` event *in addition to* `ROLE_FAILED`/`RUN_FAILED` — follow whatever single `apply_transition`/event-emission call site already appends events for `GitError` (trace this call site during planning; it is the same one this except-block feeds into).

---

### `src/dark_factory/events/catalog.py` — add `CAPABILITY_DENIED` (model/enum)

**Analog:** same file — Phase 2's addition of `QUESTION_CREATED`/`RUN_PAUSED`/etc. (lines 35-39) and Phase 5's single-member addition of `WIP_COMMIT_CREATED` (lines 41-42):
```python
class EventType(StrEnum):
    """Append-only run_events.type values. Value equals name."""
    RUN_CREATED = "RUN_CREATED"
    ...
    # Phase 5 -- the WIP-recovery audit tie (A-05-06).
    WIP_COMMIT_CREATED = "WIP_COMMIT_CREATED"
```
Add `CAPABILITY_DENIED = "CAPABILITY_DENIED"` as a new commented block (`# Phase 6 -- ...`), following the module docstring's own rule: **only pre-declare a member that this phase's own code genuinely reaches** — do not add speculative `git.*`/`github.*` denial types.

---

### `src/dark_factory/artifacts/*` — migrating `artifacts.read`/`artifacts.write` onto `registry.invoke()` (D-03)

**Analog:** `src/dark_factory/artifacts/validation.py::collect_role_artifacts()` (lines 48-106) — the real, unconditional **read** call site:
```python
text = read_artifact_text(root, ref.path)
```
This line is the D-03 migration target for `artifacts.read`: replace the direct `read_artifact_text(root, ref.path)` call with `registry.invoke(role, "artifacts.read", granted, root=root, relative_path=ref.path)`, where the registered `artifacts.read` implementation's body is exactly today's `read_artifact_text` (`artifacts/store.py` lines 23-47).

**Important gap flagged by RESEARCH.md Open Question 2:** there is **no** real orchestrator-owned **write** call site for artifact content today. `write_artifact_text` (`artifacts/store.py` lines 50-68) is called only from `workers/fake.py`'s synthesis path and test scaffolding — `actions/builtins.py::store_role_artifacts` (lines 112-119) is an explicit **permanent no-op** by its own docstring (WR-01 discipline: actions may never open a session or write mutation-path state). Planning must decide explicitly whether `artifacts.write`'s "real production call site" threads through `FakeWorker` or is proven only via the synthetic-capability unit test — do not silently assume the write side mirrors the read side's call-site structure.

---

## Shared Patterns

### Credential-boundary allowlist (build_worker_env / shell.execute)
**Source:** `src/dark_factory/git/client.py::git_env()` + `tests/support/subprocess_runner.py::child_env()`
**Apply to:** `tools/env.py`'s `build_worker_env()` and `shell.execute`'s subprocess spawn.
```python
def git_env() -> dict[str, str]:
    return {
        name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ
    } | GIT_IDENTITY_ENV
```
Never `os.environ.copy()` — guarded structurally by `tests/unit/test_no_environ_copy.py`.

### Name-to-callable registry idiom (deny-by-default overlay)
**Source:** `src/dark_factory/workers/registry.py::WorkerRegistry`, `src/dark_factory/actions/registry.py::ActionRegistry`
**Apply to:** `tools/registry.py::ToolRegistry`.
```python
class ToolRegistry:
    def __init__(self) -> None:
        self._impls: dict[str, Callable[..., object]] = {}
    def register(self, name: str, fn: Callable[..., object]) -> None:
        self._impls[name] = fn
    def __contains__(self, name: object) -> bool:
        return name in self._impls
```
`invoke()` layers the grant check on top of this base lookup shape (see Pattern Assignments above).

### Single mutation-path / error-handling attach point
**Source:** `src/dark_factory/orchestrator/runner.py` `except GitError as exc:` block (line 857) and the WIP-cleanup one (line 609)
**Apply to:** the new `except CapabilityDeniedError` branch (D-06) — same `Signal.ROLE_FAILED` outcome-dict shape, same "no artifact_writes on this failure path" discipline.

### AST-based import-graph guard
**Source:** `tests/unit/test_orchestrator_no_live_config_read.py` (`_transitive_closure`, `_dark_factory_imports`, `_module_to_path`)
**Apply to:** `tests/unit/test_no_mcp_import_in_core.py` (D-14) — **reuse `_transitive_closure`'s walking logic verbatim**, but add a **second, new** AST helper that scans each reachable module's own source for third-party `import mcp` / `from mcp import ...` / `from mcp_types import ...` (NOT `dark_factory.mcp` — see RESEARCH.md Pitfall 4). The existing `_dark_factory_imports` helper only collects `dark_factory.*`-prefixed names and will not, as written, catch a bare `import mcp`.

### Session-free / WR-01 discipline
**Source:** `src/dark_factory/actions/builtins.py` module docstring + `tests/unit/test_single_mutation_path.py` (referenced, not re-read — already covered by CONTEXT.md D-06's citation)
**Apply to:** `ToolRegistry.invoke()` must never open a `Session` — consistent with every existing action/tool-adjacent module in this codebase.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/dark_factory/tools/mcp_transport.py` (`build_mcp_server()`) | provider/adapter | event-driven | First MCP integration in this codebase — no in-repo precedent. Use RESEARCH.md's Pattern 3 code example (`MCPServer` + `add_tool()` loop with the late-binding-closure fix) as the primary source instead of an in-repo analog; structurally it is closest in *spirit* to `WorkerRegistry`'s factory idiom (fresh construction, name-to-callable), but the concrete API surface (`mcp.server.MCPServer`) is entirely external. |
| `tests/unit/test_mcp_adapter.py` | test | event-driven, async | No in-repo async test exists. Use RESEARCH.md Pattern 4 (`mcp.Client` in-memory testing, `anyio` self-registering pytest plugin, `@pytest.mark.anyio`) verbatim as the template. |

## Metadata

**Analog search scope:** `src/dark_factory/{git,workers,actions,artifacts,events,orchestrator}/`, `tests/{unit,support}/`
**Files scanned:** `git/client.py`, `tests/support/subprocess_runner.py`, `workers/registry.py`, `actions/registry.py`, `actions/builtins.py`, `artifacts/store.py`, `artifacts/validation.py`, `events/catalog.py`, `orchestrator/runner.py` (targeted grep + read), `config/loader.py` (targeted grep), `tests/unit/test_no_environ_copy.py`, `tests/unit/test_orchestrator_no_live_config_read.py`
**Pattern extraction date:** 2026-09-17
