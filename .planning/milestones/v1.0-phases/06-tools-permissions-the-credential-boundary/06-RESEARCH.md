# Phase 6: Tools, Permissions & the Credential Boundary - Research

**Researched:** 2026-09-17
**Domain:** Capability-gated tool invocation, subprocess credential isolation, optional MCP transport
**Confidence:** HIGH for the settled areas (D-01–D-11: spot-checked against real source); MEDIUM for the MCP adapter (D-12–D-15: verified against the official SDK's own docs and source, but this codebase has never integrated it)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Capability enforcement model**
- **D-01:** `ToolRegistry.invoke(role, capability, ...)` is a real, callable Python API — not a declarative-only permission validator. Deny-by-default is checked on every call. This is what makes SC1 ("a role invoking a capability it was not granted is denied by the registry") literally true, and what makes the MCP transport (D-13) meaningful: MCP becomes another transport calling the same `invoke()`.
- **D-02:** The registry governs Dark-Factory-initiated tool calls and MCP-exposed calls; it does not intercept a real CLI worker's own native filesystem/shell tools (Dark Factory can't literally do that for an external process). Phase 6 additionally documents (design-level, not implemented) the per-worker translation contract a future adapter must follow to derive its native-tool restriction from a role's `tools:` grants (e.g. a documented mapping to Claude Code's `--allowedTools`) — **Reversibility:** reversible — this is a documentation/design-contract decision, not code; Phase 7 can refine the mapping without touching Phase 6's registry.
- **D-03:** Existing artifact I/O (`store_role_artifacts` / `collect_role_artifacts` from Phase 4, currently unconditional) is migrated onto `registry.invoke('artifacts.read'/'artifacts.write', ...)` using each role's granted `tools:` list — giving real production call sites so SC1's deny-by-default is provable end-to-end, not only via a direct unit test, for `artifacts.read`/`artifacts.write`.
- **D-04:** Only the 7 capabilities current role YAMLs actually grant are registered and implemented this phase (`repo.read/search/write/write_tests`, `shell.execute`, `artifacts.read/write`). `git.status/diff/history` and `github.issue.read`/`github.comments.read` are **not** registered yet — they land when Phase 9/10 actually grants them to a role. TOOL-02's extensibility (SC3: "a new capability is added... without editing any role executor") is proven with a synthetic test capability, not a real future one.

**Denial event & failure shape**
- **D-05:** A denied `registry.invoke()` call always fails the role attempt immediately — reuses the exact Phase 4/5 failure shape (persisted `FAILED` `role_execution` + `run_events` error entry + immediate `FAILED` transition), the same pattern already used for schema-violation (04-CONTEXT.md D-09) and write-scope-violation (05-CONTEXT.md D-13) failures. No new failure pathway, no "denied but continue" branch.
- **D-06:** `registry.invoke()` is session-free (consistent with WR-01 — actions never open a DB session) and raises a typed `CapabilityDeniedError` on denial; `runner.py`'s mutation-path code catches it alongside the existing `except GitError` block (D-16 pattern from Phase 5) and produces the standard `FAILED` shape.
- **D-07:** A denial gets its own `CAPABILITY_DENIED` `EventType` — a distinct, auditable fact SC1 explicitly names, following the existing pattern of narrow purpose-built event types (`QUESTION_CREATED`, `RUN_PAUSED`, etc. added in Phase 2). This deviates from Phase 5's own no-new-event-type precedent (D-16's git-push failure), which was a deliberate choice there to avoid growing failure vocabulary for a *transient* failure; a capability denial is a *contract violation*, closer in kind to the events Phase 2 already added.
- **D-08:** `CAPABILITY_DENIED` is emitted **in addition to** the usual `ROLE_FAILED`/`RUN_FAILED` events, not instead of them — `dark-factory status`/observability code needs zero special-casing to recognize "this run failed"; it just gets one extra informative event in the trail.

**Credential boundary — proving SEC-03 pre-Phase-7**
- **D-09:** `build_worker_env(role, env_var_name: str, value: SecretStr | None)` is a generic, explicit-allowlist function mirroring `git_env()`/`child_env()` exactly (`PATH`, `HOME`, a temp `XDG_*`, plus only the named credential variable if a value is supplied; never `os.environ.copy()`). No new `Settings` fields this phase — the credential is an explicit caller-supplied parameter, mirroring D-16's git-push pattern (Phase 5) where `Settings.github_token` is read once by the caller and passed as a plain value into a config-ignorant package. Phase 7 adds `Settings.anthropic_api_key` (or similar) when `ClaudeCodeWorker` actually needs one — Phase 6 doesn't guess at a name that might not match.
- **D-10:** SC2 is proven by spawning a real OS subprocess (a tiny "dump `os.environ`" script, the same technique `tests/support/subprocess_runner.py` already uses from Phases 1–2) with `build_worker_env()`'s output and asserting `DATABASE_URL`/`GITHUB_TOKEN`/unrelated keys are absent. `FakeWorker` is not changed to spawn subprocesses — it stays in-process, documented as having no external call, per its existing contract. The credential-boundary function is proven standalone; Phase 7 wires `ClaudeCodeWorker` to actually call it when spawning `claude`.
- **D-11:** `shell.execute`'s real implementation runs the command via `subprocess.Popen` with `env=build_worker_env(role, ...)` — a genuine production call site proving SEC-03 through real code, not only the synthetic harness (D-10). No current pipeline role invokes it yet (Developer/QA are still `FakeWorker`), so it's exercised via direct tests today; the implementation itself is real and is reused unchanged once Phase 7+ roles actually shell out.

**MCP transport scope**
- **D-12:** Phase 6 ships a minimal skeleton MCP adapter, not a full-featured server. It exposes the registered capabilities (D-04's 7 tools) via the official `mcp` SDK, enough for a test/fake MCP client to list and call them and observe the same deny-by-default behavior as direct `registry.invoke()`. No real Claude Code / Copilot / Hermes integration this phase.
- **D-13:** `mcp` is an **optional** dependency (a `uv`/`pyproject.toml` optional-dependencies group, e.g. `[project.optional-dependencies] mcp = [...]`), not a regular always-installed one — matching CLAUDE.md's own "the orchestrator must never import it on a core path" guidance literally: uninstalling the extra leaves the core fully functional, not just import-graph-clean. The dedicated MCP adapter test module is skipped when the extra isn't installed.
- **D-14:** SC5's "removing MCP entirely leaves the orchestrator fully functional" is proven by an import-graph guard test, mirroring the existing AST-based guards (`test_no_role_name_literal.py`, `test_orchestrator_no_live_config_read.py`) — asserting zero `mcp` imports anywhere on the core (non-adapter) import closure.
- **D-15:** The MCP adapter is a factory — `build_mcp_server(role, granted_tools)` — instantiated fresh per role invocation, with the role's grants baked in at construction. No session/auth negotiation, no per-call role-identity parameter. This mirrors the existing "nothing persists across role attempts unless it's a durable artifact" discipline (e.g. `RoleContext` built fresh per attempt in Phase 4's `ContextBuilder`).

### Claude's Discretion
- Exact `CapabilityDeniedError` message format and the fields carried on the `CAPABILITY_DENIED` event payload (role, capability, reason) — left to planning, as long as it's enough to answer "who tried what and was denied why" from the audit trail alone.
- Exact shape of the documented native-tool-restriction translation contract (D-02) — a docstring/module comment vs. a small typed mapping table — left to planning discretion as long as it's concrete enough for Phase 7 to implement without re-deriving the mapping from first principles.
- Exact synthetic test capability used to prove TOOL-02 extensibility (D-04) — implementation detail.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. Native-CLI tool restriction (`--allowedTools` wiring), `git.*`/`github.*` capability implementations, and full MCP server build-out were all explicitly identified as later-phase concerns during discussion (Phase 7, Phase 9/10, and "when a real MCP client exists" respectively) rather than raised as new capabilities — captured as scope boundaries in CONTEXT.md's `<domain>` section, not as a backlog list.

**Phase boundary (from CONTEXT.md `<domain>`):** Out of scope this phase: real per-adapter native-tool restriction (e.g. Claude Code's `--allowedTools` flag construction) — Phase 6 defines the translation contract a future adapter must follow, but doesn't build or wire it; that's Phase 7. `git.status/diff/history` and `github.issue/comments.read` capabilities — registered when a phase actually grants them to a role (Phase 9/10). A full-featured MCP server matching every possible capability — Phase 6 ships a minimal skeleton proven with a fake/test client. Real Claude Code / Copilot / Hermes MCP integration — Phase 7+.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|---------------------|
| TOOL-01 | A `ToolRegistry` provides the capability layer (`repo.read/search/write/write_tests`, `shell.execute`, `git.status/diff/history`, `github.issue.read`, `github.comments.read`, `artifacts.read/write`) | Architecture Patterns Pattern 1 (deny-by-default check shape); D-04 scopes this phase's registered subset to the 7 capabilities current role YAMLs actually grant — `git.*`/`github.*` are deferred, confirmed against `.dark-factory/roles/*.yaml` this session |
| TOOL-02 | New tools can be added to the registry without modifying every role executor | Don't Hand-Roll / registry idiom mirrors `WorkerRegistry`/`ActionRegistry` (existing in-repo pattern, spot-checked in `src/dark_factory/workers/registry.py`); proven via a synthetic capability per D-04 |
| TOOL-03 | Each role receives only its explicitly configured tools; grants are deny-by-default (BA/Architect read-only on code; Developer write + shell; QA write_tests + shell, no publish) | Pattern 1; Open Question 1 flags a real discrepancy between ROADMAP SC1's QA-shell wording and current QA.yaml that must be resolved before this requirement can be proven as literally stated |
| TOOL-04 | A worker's subprocess environment is built from an explicit allowlist; infrastructure credentials (`DATABASE_URL`, `GITHUB_TOKEN`, worker credentials) are never passed to a worker | Pattern 2, directly mirroring `git_env()`/`child_env()`, both read and verified this session |
| TOOL-05 | MCP is supported as one optional transport adapter for exposing tools to compatible workers; the orchestrator has no internal dependency on MCP | Patterns 3 & 4 (SDK `add_tool()` + in-memory `Client`), Package Legitimacy Audit, Pitfall 4 (the import-graph-guard shape needed, which differs from the closest in-repo precedent) |
| SEC-01 | `DATABASE_URL`, GitHub credentials, and worker credentials never appear in role artifacts, worker prompts, Neon event payloads, GitHub comments, logs, or test reports | Security Domain threat-pattern table (`CAPABILITY_DENIED` payload shape); reuses the existing `redact()`/SEC-02 mechanism, no new redaction path needed |
| SEC-03 | A worker subprocess does not inherit the full Dark Factory process environment; it receives only the minimum required for its role | Pattern 2; Validation Architecture's `test_worker_env_boundary.py` row |
</phase_requirements>

## Summary

Most of this phase is not really "research" — 06-CONTEXT.md's fifteen decisions already name the exact files to mirror, and every one of them checks out against the current source tree: `git_env()`/`GIT_ENV_ALLOWLIST` (`src/dark_factory/git/client.py`) and `child_env()` (`tests/support/subprocess_runner.py`) are both real, both build a child environment by comprehension over an explicit allowlist from an empty dict, and neither has drifted since the phase discussion. The `except GitError as exc:` block D-06 names as the `CapabilityDeniedError` attachment site is real and sits in `orchestrator/runner.py` around the `commit_run_artifacts`/`push_working_branch` call (line ~857). `EventType` is a ten-member `StrEnum` with a documented "don't pre-declare unreachable types" discipline that `CAPABILITY_DENIED` fits cleanly. One spot-check surfaced a genuine gap the planner needs to resolve (see Open Questions): `collect_role_artifacts`/`store_role_artifacts` are not symmetric the way D-03's phrasing implies — only the **read** side has a real orchestrator-owned call site today; there is no orchestrator-owned **write** call site for artifact content at all (a real worker writes its own files; `FakeWorker` stands in for that write today, outside the registry's natural reach).

The genuinely open technical work is the MCP transport (D-12–D-15). The official SDK shipped a major v2 rework (current PyPI release: `mcp` 2.2.0, 2026-09-07) that replaced the old low-level-handler-first API with an ergonomic `MCPServer` class — `@mcp.tool()` is sugar over `MCPServer.add_tool(fn, name=..., description=...)`, and `add_tool` is exactly the programmatic, loop-friendly registration primitive `build_mcp_server(role, granted_tools)` needs: construct a fresh `MCPServer(name=...)`, loop over `granted_tools`, and `add_tool` one closure per capability that calls `registry.invoke(role, capability, ...)`. Sync `def` tool functions are natively supported — the SDK runs them in a thread — so `ToolRegistry.invoke()` staying 100% synchronous is not a blocker. Testing is answered directly by the SDK's own docs: `Client(server_instance, raise_exceptions=True)` connects **in-memory**, no subprocess, no port — exactly what D-12 asks for. The dependency footprint is heavier than CLAUDE.md's framing suggests: `mcp` 2.2.0 pulls in `starlette`, `uvicorn`, `sse-starlette`, `jsonschema`, `pyjwt`, `opentelemetry-api`, and (oddly-named but genuinely official) `httpx2` as hard dependencies — all the more reason it must stay behind an optional-dependencies group. `anyio`, also a hard dependency, self-registers a `pytest11` plugin (`anyio.pytest_plugin`), so `@pytest.mark.anyio` tests work the moment `mcp` is installed — no `pytest-asyncio` needed, keeping the async surface confined to the one adapter test module as CLAUDE.md directs.

**Primary recommendation:** Implement `ToolRegistry`/`build_worker_env`/`CAPABILITY_DENIED` exactly as D-01–D-11 specify (all confirmed against current source); build the MCP adapter as `MCPServer(name=...)` + `add_tool()` in a loop over `granted_tools`, each tool a closure catching `CapabilityDeniedError` and re-raising as `mcp.server.mcpserver.exceptions.ToolError` so a denial is legible in `result.is_error`/`result.content`, not just an opaque crash; prove it with the SDK's in-memory `Client`; pin `mcp>=2.2,<3` as a `[project.optional-dependencies]` group; resolve the QA-shell-grant discrepancy (Open Questions) before finalizing D-04's capability list.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Capability enforcement (`ToolRegistry.invoke`) | Orchestrator (API/Backend equivalent — this project has no web tier) | — | Deny-by-default must be checked by the same process that owns lifecycle state; delegating it to a worker subprocess would make the check bypassable by construction (explicit invariant in ROADMAP.md) |
| Credential-boundary env building (`build_worker_env`) | Orchestrator | — | Only the orchestrator process ever holds `DATABASE_URL`/`GITHUB_TOKEN`; it is the sole party that can construct a safe subprocess environment |
| MCP transport adapter | Orchestrator (optional adjunct) | — | A pure protocol translation over the same `registry.invoke()` — it adds no new authority, it exposes existing authority over a second wire format |
| `shell.execute` capability | Orchestrator-mediated subprocess | — | The subprocess itself is a worker-tier concern (a real worker's shell), but the credential boundary and the permission check both live in the orchestrator's `ToolRegistry`, not in the worker |
| Artifact I/O (`artifacts.read/write`) | Orchestrator (filesystem tier) | — | ART-01/ART-03: filesystem holds content, Neon holds references; both sides of that split are orchestrator-owned code today |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `mcp` | PyPI | First published 2024-11-20 (72 releases through 2.2.0 on 2026-09-07) [VERIFIED: PyPI JSON API `pypi.org/pypi/mcp/json`, full release history] | Not resolvable via the automated check (`weeklyDownloads: null`) | `github.com/modelcontextprotocol/python-sdk` [VERIFIED: PyPI project_urls + repo `pyproject.toml` `[project.urls]`] | **SUS** per `gsd-tools query package-legitimacy check` (reasons: `too-new`, `unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify` before the install task |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `mcp` — see below.

**Why this is very likely a false positive, for the human-verify checkpoint's benefit:** the automated verdict's `too-new` signal reads `publishedAt` as the *latest version's* upload date (2026-09-07, ~10 days before this research), not the package's actual age. Manually walking the full PyPI release history shows the package has existed for **22 months** with **72 releases**, starting at `0.9.1` on 2024-11-20 [VERIFIED: PyPI JSON API, computed from `releases` map]. The repository's `pyproject.toml` lists four named maintainers with `@anthropic.com` addresses [VERIFIED: `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/pyproject.toml`], the package is the official SDK for a protocol Anthropic itself specified, and it is already the exact package CLAUDE.md's own Technology Stack names (pinned there at `2.1.1`; `2.2.0` is now current). `unknown-downloads` is a lookup gap in the checker, not a zero-download signal. None of this exempts the phase from the protocol's literal instruction — flag it, gate the install behind `checkpoint:human-verify` — but the checkpoint reviewer should expect to confirm quickly, not investigate a real typosquat candidate.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` | `2.2.0` current on PyPI as of 2026-09-07 [VERIFIED: `pip index versions mcp`, cross-checked against PyPI JSON API] | Official MCP Python SDK — server + client, used only for the optional transport adapter | Anthropic-maintained, spec-canonical implementation; CLAUDE.md already names it (at the slightly older `2.1.1`) as the only acceptable MCP dependency |

No other new runtime dependency is required — `ToolRegistry`, `build_worker_env`, and the `CAPABILITY_DENIED` event use only stdlib (`subprocess`, `os`) and the project's existing pydantic v2 / structlog stack.

### Supporting

None beyond what ships transitively with `mcp` (see Package Legitimacy Audit — `starlette`, `uvicorn`, `sse-starlette`, `anyio`, `jsonschema`, `pyjwt`, `opentelemetry-api`, `httpx2`, `typing-extensions`, `typing-inspection`, `mcp-types`). None of these are direct project dependencies; they arrive only when the `mcp` extra is installed, and D-13 requires they stay confined to that extra.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SDK's high-level `MCPServer` + `add_tool()` | SDK's low-level `Server` (raw `on_list_tools=`/`on_call_tool=` constructor handlers, hand-written JSON Schema) | Low-level gives exact control over the schema and result shape, but D-15's per-role dynamic tool set is naturally a loop over `add_tool()` calls; the low-level API would require hand-writing dispatch-by-name logic `add_tool` already provides for free. Reach for low-level only if a future phase needs schema control `add_tool`'s type-hint-derived schema can't express. |
| Optional `[project.optional-dependencies] mcp = [...]` group | A separate `pyproject.toml` / sub-package with its own dependency manifest | Unnecessary complexity for one dependency; `uv`'s optional-dependency groups are the standard mechanism and are what CLAUDE.md and D-13 already specify |

**Installation:**
```bash
# Adds mcp to [project.optional-dependencies] under a new "mcp" group.
uv add --optional mcp "mcp>=2.2,<3"
```

**Version verification:** `pip index versions mcp` returned `2.2.0` as latest on this research date; the SDK's own README explicitly warns that `mcp` on PyPI now means v2 ("keep a `<2` upper bound... until you've migrated" for anyone still on v1), which is the basis for recommending the `>=2.2,<3` bound — it pins inside the v2 line the way the project's other dependencies pin inside a major (`sqlalchemy>=2.0.40,<2.1`, `psycopg[binary]>=3.2,<4`).

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │        orchestrator/runner.py            │
                    │   _run_current_role() / artifact commit   │
                    └───────────────┬───────────────────────────┘
                                    │ registry.invoke(role, capability, **kwargs)
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │          tools/registry.py                │
                    │        ToolRegistry.invoke()               │
                    │  1. look up role's granted capabilities    │
                    │     (from the persisted config snapshot)   │
                    │  2. deny-by-default: not granted ->         │
                    │     raise CapabilityDeniedError             │
                    │  3. granted -> dispatch to the registered   │
                    │     implementation callable                 │
                    └───────┬──────────────────────┬─────────────┘
                            │ granted                │ denied
                            ▼                        ▼
              ┌──────────────────────┐   ┌────────────────────────────┐
              │ capability impl       │   │ except CapabilityDeniedError│
              │ (repo.read/search/    │   │  -> ROLE_FAILED/RUN_FAILED  │
              │  write/write_tests,   │   │  -> CAPABILITY_DENIED event │
              │  shell.execute,       │   └────────────────────────────┘
              │  artifacts.read/write)│
              └──────────┬─────────────┘
                         │ shell.execute only
                         ▼
              ┌──────────────────────┐
              │ build_worker_env()    │
              │ (allowlist from {})   │
              └──────────┬─────────────┘
                         ▼
              subprocess.Popen(..., env=build_worker_env(...))


  ── optional, only when the "mcp" extra is installed ──

                    ┌─────────────────────────────────────────┐
                    │   tools/mcp_transport.py (or tools/mcp/)  │
                    │   build_mcp_server(role, granted_tools)   │
                    │   -> fresh MCPServer(name=...) per call   │
                    │   -> add_tool() once per granted tool,    │
                    │      each closure calling                 │
                    │      registry.invoke(role, name, ...)     │
                    └───────────────┬───────────────────────────┘
                                    │ in-memory (tests) / stdio (a real worker)
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │      mcp.Client  (list_tools/call_tool)   │
                    └─────────────────────────────────────────┘
```

A reader tracing SC1: a role's worker (or, once Phase 7 lands, a real Claude Code subprocess) asks to perform a capability; every path into that capability funnels through `ToolRegistry.invoke()`, which is the single deny-by-default checkpoint whether the caller is Dark-Factory-owned code (`collect_role_artifacts` migrated per D-03), a direct unit test, or an MCP `tools/call` request.

### Recommended Project Structure
```
src/dark_factory/
├── tools/
│   ├── __init__.py          # error hierarchy (CapabilityDeniedError), matching git/__init__.py's pattern
│   ├── registry.py          # ToolRegistry, invoke(), the 7 capability implementations (D-01, D-04)
│   ├── env.py                # build_worker_env() (D-09) — or keep it in registry.py if small
│   └── mcp_transport.py      # OR a mcp/ subpackage — build_mcp_server(), isolated per D-13/D-14
```
Nesting the MCP adapter under `tools/` (rather than a top-level `dark_factory.mcp` package) keeps D-14's import-graph guard scoped to one subtree and avoids a top-level module name that visually collides with the third-party `mcp` package — a real but purely cosmetic risk (see Common Pitfalls).

### Pattern 1: Deny-by-default capability check
**What:** `ToolRegistry.invoke(role: str, capability: str, **kwargs)` looks up the role's granted capability list (sourced from the persisted config snapshot, the same `role_def["tools"]` list `config/loader.py`'s `RoleDefinition.tools` already carries into the snapshot per plan) and raises `CapabilityDeniedError` immediately if `capability` is not in that list, before ever touching the implementation callable.
**When to use:** Every capability call, with no exceptions — this is the literal mechanism SC1 requires.
**Example (registry shape, following the project's existing name-to-callable idiom in `WorkerRegistry`/`ActionRegistry`):**
```python
# Source: pattern mirrored from src/dark_factory/workers/registry.py (WorkerRegistry)
# and src/dark_factory/actions/registry.py (ActionRegistry) — this codebase's own
# established name-to-callable registry idiom, not an external reference.
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

### Pattern 2: Explicit-allowlist child environment
**What:** `build_worker_env(role, env_var_name, value)` builds `{name: os.environ[name] for name in ALLOWLIST if name in os.environ}` and layers in exactly one named credential — never `os.environ.copy()`.
**When to use:** Every subprocess spawn that could reach a worker or a worker-adjacent tool (`shell.execute`).
**Example:**
```python
# Source: src/dark_factory/git/client.py::git_env() — the direct template (VERIFIED,
# read this session, lines 60-71 of that file).
def git_env() -> dict[str, str]:
    return {
        name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ
    } | GIT_IDENTITY_ENV
```
`build_worker_env` is the same shape with a generic credential parameter instead of the git-specific identity dict.

### Pattern 3: Programmatic MCP tool registration
**What:** `MCPServer.add_tool(fn, name=..., description=...)` registers one tool without decorator syntax — the exact primitive `build_mcp_server(role, granted_tools)` needs to loop over a dynamic list.
**When to use:** D-15's per-role, freshly-constructed MCP server.
**Example:**
```python
# Source: mcp.server.mcpserver.server.MCPServer.add_tool, read from
# raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/server/mcpserver/server.py
# (lines 609-647 of that file, this session) [VERIFIED: SDK source, official repo]
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

def build_mcp_server(role: str, granted_tools: list[str], registry: "ToolRegistry") -> MCPServer:
    server = MCPServer(name=f"dark-factory-{role}")
    for capability in granted_tools:
        def _tool(_capability: str = capability, **kwargs: object) -> object:
            try:
                return registry.invoke(role, _capability, granted_tools, **kwargs)
            except CapabilityDeniedError as exc:
                raise ToolError(str(exc)) from exc
        server.add_tool(_tool, name=capability)
    return server
```
The `_capability: str = capability` default-argument closure trick is required — a `for` loop that closes over `capability` directly would have every registered tool call `registry.invoke` with the *last* loop value (the classic late-binding-closure pitfall; see Common Pitfalls).

### Pattern 4: In-memory MCP test client
**What:** `mcp.Client` connects directly to a server object with no subprocess and no port.
**When to use:** D-12's proof that "a test/fake MCP client can list and call [the registered capabilities] and observe the same deny-by-default behavior as direct `registry.invoke()`".
**Example:**
```python
# Source: docs/get-started/testing.md,
# raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/get-started/testing.md
# [VERIFIED: official SDK docs, fetched this session]
import pytest
from mcp import Client

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

@pytest.fixture
async def client(built_server):
    async with Client(built_server, raise_exceptions=True) as c:
        yield c

@pytest.mark.anyio
async def test_denied_capability_surfaces_as_tool_error(client):
    result = await client.call_tool("repo.write", {...})
    assert result.is_error is True
```
`raise_exceptions=True` matters only for crashes *outside* a tool body (protocol-level failures); a `ToolError` raised *inside* a tool always surfaces as `result.is_error=True` regardless of the flag (see docs/servers/handling-errors.md, fetched this session).

### Anti-Patterns to Avoid
- **Trusting the MCP-exposed tool list as the enforcement boundary:** listing only `granted_tools` in `add_tool()` calls looks like enforcement, but a buggy or malicious client can still issue `tools/call` for a name it was never advertised (the low-level docs note the SDK "will happily forward a `tools/call` for a name you never listed" to a handler that doesn't check). The actual enforcement is `registry.invoke()`'s deny-by-default check running *inside* every tool closure — never skip the check there on the theory that "it's not in the exposed list anyway."
- **Letting `CapabilityDeniedError` fall through uncaught in the MCP closure:** an uncaught exception is treated as a generic SDK crash — `is_error=True` with only `"Error executing tool <name>"`, no reason. That still technically satisfies "denied," but it throws away exactly the "who tried what and was denied why" audit-trail requirement CONTEXT.md's Claude's-Discretion note asks for. Catch it explicitly and re-raise as `ToolError(str(exc))`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol framing (JSON-RPC, `tools/list`/`tools/call`, schema generation) | A hand-rolled JSON-RPC handler over stdio | `mcp.server.mcpserver.MCPServer` | The protocol has a real spec with a 2026-07-28 revision and a maintained reference implementation; hand-rolling it duplicates exactly what CLAUDE.md already names as the required dependency |
| Input-schema validation for MCP tool arguments | Manual `dict.get()` + type checks in each tool closure | Type-hint-derived Pydantic validation `MCPServer` already performs before a tool function runs | The high-level `MCPServer` rejects a malformed call against the generated JSON Schema before your function executes; re-validating inside the closure duplicates work the SDK already does for free |
| Async test harness for the MCP adapter | Custom event-loop bootstrapping | `anyio`'s self-registering `pytest11` plugin (arrives automatically once `mcp` is installed) + `@pytest.mark.anyio` | No `pytest-asyncio` dependency needed; verified the entry point ships in the `anyio` wheel itself |

**Key insight:** The temptation in this phase is to treat the MCP layer as *another* place capability grants live. It should not: `granted_tools` at MCP-server-construction time is a convenience list (what to advertise), not a second source of truth. The only source of truth is `ToolRegistry.invoke()`'s deny-by-default check, called from inside every MCP tool closure exactly as it is called from `orchestrator/runner.py`'s direct call sites — one enforcement point, two transports.

## Common Pitfalls

### Pitfall 1: Late-binding closures in the `add_tool()` loop
**What goes wrong:** `for capability in granted_tools: server.add_tool(lambda **kw: registry.invoke(role, capability, ...))` — every closure captures the *variable* `capability`, not its value at loop-iteration time; after the loop, all closures see the final value.
**Why it happens:** Standard Python closure semantics; well-known but easy to miss under review since the code "looks right."
**How to avoid:** Bind the loop variable as a default argument (`def _tool(_capability: str = capability, ...)`), shown in Pattern 3 above.
**Warning signs:** A test that grants two or more capabilities to one role and calls each by name gets the same result (or the same capability invoked) regardless of which tool name it called.

### Pitfall 2: `dark_factory.mcp` name shadowing (cosmetic, not a real Python bug)
**What goes wrong:** A submodule named `dark_factory.mcp` does **not** actually collide with the top-level third-party `mcp` package — Python 3's import system resolves `import mcp` and `from dark_factory.mcp import ...` unambiguously by full dotted path. But it reads confusingly in diffs, greps, and error tracebacks (`ModuleNotFoundError: No module named 'mcp'` inside a file literally named `mcp/__init__.py` is a common false start for a reviewer).
**Why it happens:** Naming a package after the protocol it adapts is the obvious first instinct.
**How to avoid:** Prefer `tools/mcp_transport.py` (a single module) or `tools/mcp/` nested one level under the existing `tools/` package, not a top-level `dark_factory/mcp/`.
**Warning signs:** None functional — purely a readability call, safe to override at planning discretion.

### Pitfall 3: Treating `add_tool`'s auto-generated JSON Schema as validation-complete for capability-specific constraints
**What goes wrong:** The SDK validates argument *types* against the function's type hints before the tool body runs, but any capability-specific constraint (e.g., a `repo.write` path staying inside a role's `write_scope`) is **not** something `add_tool`'s auto-schema expresses — that enforcement still has to live inside the capability implementation (or, per D-02, be documented as the future per-adapter translation contract), not be assumed away because "the schema validated the call."
**Why it happens:** The SDK's promise ("Nothing is checked for you" applies to the low-level `Server`, and the opposite framing — "the SDK validates it for you" — applies to `MCPServer`) is easy to over-generalize past type-checking into semantic/permission checking.
**How to avoid:** Keep `write_scope`/permission enforcement exactly where D-01–D-11 already put it (inside `ToolRegistry.invoke()` and the post-worker `enforce_write_scope` pass), never inside the MCP schema.
**Warning signs:** A capability implementation with no `ToolRegistry.invoke()`-level check, relying only on the MCP-advertised schema shape.

### Pitfall 4: Assuming a bare `import mcp` inside `tests/` trips the D-14 import-graph guard
**What goes wrong:** D-14's guard (mirroring `test_orchestrator_no_live_config_read.py`) must walk the **`dark_factory.*`** import graph from core roots and check each reachable module's own AST for a top-level `import mcp` / `from mcp import ...` / `from mcp_types import ...` statement. The existing `test_orchestrator_no_live_config_read.py` helper (`_dark_factory_imports`) only *collects* `dark_factory.*`-prefixed imports for its own transitive-closure walk — it does not, as written, detect a **third-party** import like `mcp` at all. A guard copy-pasted verbatim from that file would silently pass even if core code imported `mcp` directly.
**Why it happens:** The precedent guard was built to prove "config loader is unreachable from the resume path," a same-package check; this phase's guard needs "a third-party package is unreachable," a different check shape layered on the same transitive-closure walker.
**How to avoid:** Reuse `_transitive_closure`'s walking logic (compute the set of `dark_factory.*` modules reachable from the core roots) but write a **second** small AST helper that scans each reachable module's *own* source for `ast.Import`/`ast.ImportFrom` nodes whose name is `mcp` or starts with `mcp.` (and, for extra rigor, `mcp_types`) — not `dark_factory.mcp`.
**Warning signs:** The guard test passes even after a deliberately-inserted `import mcp` at the top of `orchestrator/runner.py` (write this as the guard's own "sanity: the walk would catch it" companion test, mirroring `test_the_walk_resolves_imports_via_the_cli`'s pattern in the precedent file).

## Code Examples

### `ToolRegistry.invoke()` deny-by-default check
```python
# Pattern, not a verbatim source quote — this codebase has no tools/ package yet.
# Shape follows the existing WorkerRegistry/ActionRegistry idiom in this repo.
if capability not in granted:
    raise CapabilityDeniedError(f"role {role!r} invoked {capability!r} without a grant")
```

### Building a per-role MCP server
```python
# Source: mcp.server.mcpserver.MCPServer.__init__ / .add_tool
# (raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/server/mcpserver/server.py,
# lines 158-186 and 609-647) [VERIFIED: SDK source, read this session]
server = MCPServer(name=f"dark-factory-{role}")
server.add_tool(some_fn, name="repo.read", description="Read a file under the run worktree")
```

### In-memory client for the D-12 proof
```python
# Source: docs/get-started/testing.md [VERIFIED: official SDK docs, fetched this session]
async with Client(server, raise_exceptions=True) as c:
    result = await c.call_tool("repo.write", {"path": "x"})
    assert result.is_error is True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| MCP Python SDK v1 low-level `Server` with `list_tools()`/`call_tool()` decorator handlers as the primary API | v2's `MCPServer` + `@mcp.tool()`/`add_tool()` as the primary API; `Server` demoted to an "advanced" escape hatch | v2.0.0 (the SDK's own README calls this "a major rework... to support the 2026-07-28 MCP specification... and to fix long-standing architectural issues") | CLAUDE.md's guidance (written referencing `mcp` 2.1.1, itself already v2) is current; do not reach for v1-era `Server(...)` patterns found in older blog posts or pre-2.0 training data — they still exist (as the low-level API) but are no longer the recommended default path |

**Deprecated/outdated:** `mcp` v1.x (`<2`) still receives critical fixes on a separate branch but is not the installed-by-default line; any code sample using `from mcp.server.fastmcp import FastMCP` (the v1 name for the high-level server) is stale — v2 renamed it to `mcp.server.MCPServer`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MCP tool names may safely contain a `.` character (e.g. `repo.read`, `shell.execute`) with no host/spec-level restriction | Architecture Patterns, Code Examples | If wrong, capability names would need a translation layer (e.g. `repo_read`) between the internal `ToolRegistry` key and the MCP-advertised tool name — a small but real extra piece of plumbing. Not verified against the MCP spec or SDK validation source this session; low effort to check by constructing one `add_tool(fn, name="repo.read")` call against a real `MCPServer` instance during planning/Wave 0. |
| A2 | `MCPServer(name=...)` construction is cheap enough (no I/O, no network) to instantiate fresh per role invocation as D-15 requires | Architecture Patterns Pattern 3 | If construction turns out to have meaningful overhead, D-15's "fresh per invocation" discipline would need reconsidering (e.g., cache by role+grant-set). The constructor body read this session shows only in-memory object construction (`ToolManager`, `ResourceManager`, a `Server` wrapper) — no I/O observed — so this is a reasonable inference from source, not a runtime-timed measurement. |

**If this table is empty:** N/A — two low-risk items above; both are cheap to falsify in Wave 0 before any production code depends on them.

## Open Questions

1. **QA's shell-execute grant contradicts the current role YAML**
   - What we know: ROADMAP.md's Phase 6 SC1 states verbatim "QA can write tests and shell but cannot publish." D-04 locks "only the 7 capabilities current role YAMLs actually grant are registered and implemented this phase," and `shell.execute` is one of the 7. But `.dark-factory/roles/QA.yaml`'s `tools:` list today is `[repo.read, repo.search, artifacts.read, artifacts.write]` — no `shell.execute` [VERIFIED: `.dark-factory/roles/QA.yaml`, read this session, full file quoted above the `tools:` key].
   - What's unclear: whether SC1's wording is aspirational (describing the eventual QA role once quality-gate/test-running lands, e.g. Phase 9's GATE work) or literally scoped to this phase, in which case QA.yaml needs a one-line edit adding `shell.execute` to make SC1 demonstrably true this phase.
   - Recommendation: surface this explicitly at planning time rather than silently resolving it either way — it is a discrepancy between two locked/near-locked sources (ROADMAP.md success criteria vs. current role config), not a research judgment call.

2. **D-03's "real production call site for `artifacts.write`" may not currently exist**
   - What we know: `collect_role_artifacts` (called unconditionally from `orchestrator/runner.py` after every `ROLE_COMPLETED` signal) is a real, unconditional **read** call site — it calls `read_artifact_text` for every declared output to validate schema [VERIFIED: `src/dark_factory/artifacts/validation.py`, read this session]. `context/builder.py`'s `build_role_context` is a second real **read** call site (prior-artifact assembly into `RoleContext.inputs`) [VERIFIED: `src/dark_factory/context/builder.py`, read this session]. `write_artifact_text` — the only content-write function in `artifacts/store.py` — is called **only** from `workers/fake.py`'s artifact-synthesis path [VERIFIED: grep across `src/` and `tests/`, cross-checked against `artifacts/store.py` and `workers/fake.py` this session]; there is no orchestrator-owned call site that writes artifact content today. `actions/builtins.py`'s `store_role_artifacts` — the function CONTEXT.md's canonical_refs names alongside `collect_role_artifacts` as what D-03 migrates — is explicitly a **permanent no-op** by its own docstring, not real I/O.
   - What's unclear: whether D-03 intends `artifacts.write`'s "real production call site" proof to route through `FakeWorker`'s synthesis (which would mean threading a `ToolRegistry` into `FakeWorker`, a dependency it does not have today and which a real worker adapter would never need — a real worker writes its own files directly, never through Dark Factory's registry), or whether `artifacts.write`'s production-call-site claim should be descoped to match what `artifacts.read` can prove, with `artifacts.write` proven only via the synthetic-capability unit test TOOL-02 already requires.
   - Recommendation: decide this explicitly during planning — it changes whether `FakeWorker` gains a new constructor parameter this phase.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All phase code | ✓ | 3.12.7 (matches `.python-version` pin `3.12`) | — |
| `mcp` (PyPI) | D-12–D-15 MCP adapter | ✗ (not currently installed; `pip show mcp` finds nothing) | latest on PyPI: 2.2.0 | Must be added via `uv add --optional mcp "mcp>=2.2,<3"` in Wave 0 before the adapter package can be imported |
| `git` (CLI) | Already required by Phase 5; unaffected by this phase | ✓ | 2.50.1 | — |
| `uv` | Dependency management | ✓ | 0.12.7 | — |

**Missing dependencies with no fallback:** none — `mcp` simply needs to be added to the optional-dependencies group as part of this phase's own work (it is not a pre-existing gap, it is this phase's deliverable).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x [VERIFIED: `pyproject.toml` `[dependency-groups] dev = ["pytest>=9,<10", ...]`, read this session] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` |
| Quick run command | `pytest -m unit` |
| Full suite command | `pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| TOOL-01 | `ToolRegistry.invoke()` denies/grants correctly for the 7 capabilities | unit | `pytest tests/unit/test_tool_registry.py -x` | ❌ Wave 0 |
| TOOL-02 | A synthetic capability is addable without editing a role executor | unit | `pytest tests/unit/test_tool_registry_extensibility.py -x` | ❌ Wave 0 |
| TOOL-03 | Deny-by-default per role, matching current `tools:` grants | unit + a real-pipeline integration proof (D-03) | `pytest tests/unit/test_tool_registry.py tests/integration/test_real_pipeline_zero_config.py -x` | ❌ / ✓ (existing file, extended) |
| TOOL-04 | Subprocess env dump shows no infra credential | integration (real OS subprocess, mirrors `tests/support/subprocess_runner.py`) | `pytest tests/integration/test_worker_env_boundary.py -x` | ❌ Wave 0 |
| TOOL-05 | MCP transport proves list/call + deny-by-default; import-graph guard proves removability | unit (guard) + a dedicated, optional-dependency-gated module | `pytest tests/unit/test_no_mcp_import_in_core.py tests/unit/test_mcp_adapter.py -x` (the second skipped if `mcp` absent) | ❌ Wave 0 |
| SEC-01 | Grep every artifact/prompt/event/log/report for known secrets, zero hits | integration (extends Phase 1's SC5-style sweep) | `pytest tests/integration/test_phase6_acceptance.py -x` | ❌ Wave 0 |
| SEC-03 | Worker subprocess never inherits the full parent env | same as TOOL-04 | (same command) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest -m unit`
- **Per wave merge:** `pytest` (full suite, including the `mcp`-gated module when the extra is installed)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_tool_registry.py` — covers TOOL-01/TOOL-03
- [ ] `tests/unit/test_tool_registry_extensibility.py` — covers TOOL-02
- [ ] `tests/integration/test_worker_env_boundary.py` — covers TOOL-04/SEC-03 (real subprocess env dump, mirroring `tests/support/subprocess_runner.py`'s technique)
- [ ] `tests/unit/test_no_mcp_import_in_core.py` — covers TOOL-05's removability half (D-14); must NOT be gated on the `mcp` extra being installed — it needs to pass (by finding nothing) whether or not `mcp` is present, since it is a "the import doesn't exist" proof
- [ ] `tests/unit/test_mcp_adapter.py` (or `tests/integration/`) — covers TOOL-05's transport half (D-12); gated with `pytest.importorskip("mcp")` per D-13, but note: this project's standard dev workflow runs `uv sync --all-extras --dev`, which installs every optional-dependencies group including `mcp` — so in ordinary CI/dev runs this module is never actually skipped, and the acceptance-gate's historical "zero `pytest.skip`" precedent (Phase 2/3) is not actually violated in practice. Confirm this explicitly in the plan rather than leaving it implicit.
- [ ] Framework install: `uv add --optional mcp "mcp>=2.2,<3"` — the one new dependency this phase needs

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | No new authentication surface — MCP transport carries no session/auth negotiation per D-15 (explicitly out of scope this phase) |
| V3 Session Management | no | `build_mcp_server` is stateless-per-call by design (D-15); no session state to manage |
| V4 Access Control | **yes** | `ToolRegistry.invoke()`'s deny-by-default check IS the access-control mechanism this phase implements (TOOL-03) |
| V5 Input Validation | yes | MCP `MCPServer`'s auto-generated JSON Schema validates tool-call arguments before a capability implementation runs (see Don't Hand-Roll); `shell.execute`'s own argument handling must still avoid shell injection (never `shell=True`, always an explicit argv list, matching `git/client.py`'s and `subprocess_runner.py`'s existing discipline) |
| V6 Cryptography | no | No new cryptographic material this phase; `build_worker_env` moves credential *values*, never derives or stores new secrets |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Credential leakage into a worker subprocess via `os.environ.copy()` | Information Disclosure | `build_worker_env`'s explicit allowlist-from-empty-dict, exactly mirroring `git_env()`/`child_env()` — never wildcard-copy the parent environment (already guarded by `tests/unit/test_no_environ_copy.py`, which this phase's new module must also satisfy) |
| Shell-injection via `shell.execute`'s command argument | Tampering | `subprocess.Popen([...])` with an explicit argv list, never `shell=True`, matching the project's existing `run_git`/`popen` discipline; the capability implementation must not concatenate untrusted strings into a single command string |
| Capability escalation via an MCP client calling an unadvertised tool name | Elevation of Privilege | Deny-by-default lives inside `registry.invoke()`, called from *every* MCP tool closure — the exposed tool list is a convenience, not the enforcement boundary (see Don't Hand-Roll's Key Insight) |
| Secret leakage into a denial's audit event payload (`CAPABILITY_DENIED`) | Information Disclosure | The event payload should carry `{role, capability, reason}` only — never raw `kwargs` that could contain user-supplied content resembling a secret; reuse the existing `redact()` pass (SEC-02) at the single `apply_transition` call site the way every other event payload already does — no special-casing needed if the payload shape stays narrow |

## Sources

### Primary (HIGH confidence)
- `pypi.org/pypi/mcp/json` and `pypi.org/pypi/mcp/2.1.1/json` — version history, `requires_dist`, `requires_python` — read this session via direct HTTP fetch
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/pyproject.toml` — canonical dependency list (dynamic-dependencies block), maintainer identities — read this session
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/server/mcpserver/server.py` — `MCPServer.__init__`, `.add_tool()`, `.tool()` signatures — read this session
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/get-started/testing.md` — in-memory `Client` testing pattern — fetched this session
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/servers/tools.md` — programmatic vs. decorator tool registration, sync/async support — fetched this session
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/servers/handling-errors.md` — `ToolError` vs `MCPError` vs uncaught-exception semantics — fetched this session
- `raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/advanced/low-level-server.md` — low-level `Server` API, "nothing checked for you", "two tools one handler" dispatch pattern — fetched this session
- `anyio` 4.15.1 wheel `dist-info/entry_points.txt` — confirms `[pytest11] anyio = anyio.pytest_plugin` self-registration — downloaded and inspected this session
- This repo's own source: `src/dark_factory/git/client.py`, `tests/support/subprocess_runner.py`, `src/dark_factory/orchestrator/runner.py`, `src/dark_factory/artifacts/{validation,store,__init__,paths}.py`, `src/dark_factory/context/builder.py`, `src/dark_factory/actions/builtins.py`, `src/dark_factory/config/{loader,settings,repo_config}.py`, `src/dark_factory/events/catalog.py`, `src/dark_factory/git/{__init__,diff}.py`, `.dark-factory/roles/*.yaml`, `tests/unit/{test_orchestrator_no_live_config_read,test_no_role_name_literal,test_no_environ_copy,test_single_mutation_path}.py`, `pyproject.toml` — all read directly this session, line numbers cited inline where load-bearing

### Secondary (MEDIUM confidence)
- `gsd-tools query package-legitimacy check --ecosystem pypi mcp` — automated verdict (SUS), cross-checked and contextualized against the primary PyPI/GitHub sources above

### Tertiary (LOW confidence)
- None retained — every claim above is either sourced directly or logged in the Assumptions table.

## Metadata

**Confidence breakdown:**
- Standard stack (D-01–D-11, non-MCP): HIGH — every named file/function was read this session and matches CONTEXT.md's description exactly
- MCP adapter (D-12–D-15): MEDIUM — verified against the official SDK's current source and docs (not training-data recall, which would describe the superseded v1 API), but this is the codebase's first integration, so no in-repo precedent exists to cross-check against
- Pitfalls: HIGH for the closure-binding and import-graph-guard pitfalls (both derived directly from reading this repo's own precedent test and the SDK's own documented dispatch behavior); MEDIUM for the MCP tool-naming pitfall (logged as Assumption A1, unverified against spec/validation source)

**Research date:** 2026-09-17
**Valid until:** 30 days for the settled D-01–D-11 areas (stable, in-repo patterns); 14 days for the MCP-specific findings (fast-moving SDK — v2 was itself a "major rework," and `2.2.0` shipped the week before this research)
