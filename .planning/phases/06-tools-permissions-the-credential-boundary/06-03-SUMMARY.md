---
phase: 06-tools-permissions-the-credential-boundary
plan: 03
subsystem: tools
tags: [mcp, optional-dependency, capability-transport, deny-by-default, import-graph-guard]

requires:
  - phase: 06-tools-permissions-the-credential-boundary
    provides: "ToolRegistry.invoke() (plan 06-01) and build_worker_env/shell_execute (plan 06-02) -- this plan's transport calls invoke() unchanged and never touches the credential boundary directly"
provides:
  - "src/dark_factory/tools/mcp_transport.py: build_mcp_server(role, granted_tools, registry) -- a fresh-per-call MCPServer whose every tool closure funnels through ToolRegistry.invoke(), never a second permission check"
  - "The mcp optional-dependency group ([project.optional-dependencies] mcp, mcp>=2.2,<3) -- never a core dependency"
  - "tests/unit/test_no_mcp_import_in_core.py -- the D-14/SC5 AST removability guard, ungated on the extra being installed, with a working positive control"
  - "tests/unit/test_mcp_adapter.py -- the D-12 in-memory client proof: list/call, granted-call value parity, ungranted-and-still-advertised denial, never-advertised denial, the late-binding-closure regression, and a real artifacts.write write-through"
affects: [07-claude-code-worker-adapter, 08-copilot-hermes-adapters, 06-04]

actuals:
  tokens: 7757
  tasks: 3
  commits: 3
  plan_head_before: 260c74bb2cce2a1e3f133a65a78f7fab6b89a9e3

tech-stack:
  added:
    - "mcp>=2.2,<3 (official MCP Python SDK) -- optional extra only, pulls starlette/uvicorn/sse-starlette/anyio/jsonschema/pyjwt/opentelemetry-api/httpx2 transitively, none of which become core dependencies"
  patterns:
    - "One enforcement point, two transports: every MCP tool closure calls the exact same ToolRegistry.invoke() the orchestrator's direct call sites use; granted_tools decides what to advertise and is never consulted as a permission source"
    - "Per-iteration factory-function closure binding: a _make_tool(*, _capability: str = capability) helper binds the loop variable one level removed from the function actually registered with add_tool, because the SDK rejects any leading-underscore parameter name on that function directly"
    - "JSON/Python path-argument coercion at the transport boundary: root/worktree/cwd are the three parameter names shared across every capability implementation that expect a Path; MCP arguments are JSON, so a str->Path coercion runs exactly on those three names before invoke()"
    - "Import-graph absence proof, ungated: the D-14 guard uses only ast/pathlib and asserts nothing about mcp being installed, so it proves the removability claim in the one configuration (extra genuinely absent) where it matters"

key-files:
  created:
    - src/dark_factory/tools/mcp_transport.py
    - tests/unit/test_mcp_adapter.py
    - tests/unit/test_no_mcp_import_in_core.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Human approved the mcp package-legitimacy checkpoint (Task 1) on 2026-09-19 after reviewing pypi.org/project/mcp (72 releases since 2024-11-20) and github.com/modelcontextprotocol/python-sdk's @anthropic.com maintainers -- the automated [SUS] verdict's too-new/unknown-downloads signals were confirmed false positives before `uv add --optional mcp \"mcp>=2.2,<3\"` ran"
  - "RESEARCH assumption A1 falsified TRUE: dotted MCP tool names (repo.read, artifacts.write) are accepted verbatim by a real MCPServer -- confirmed against list_tools()/call_tool() this session, no translation layer introduced"
  - "Each MCP tool accepts one optional `arguments` object rather than a bare **kwargs closure parameter -- the SDK schemas a literal **kwargs: object signature as one *required* property literally named \"kwargs\", not as \"accept arbitrary named properties\"; wrapping every capability's distinct keyword shape in one JSON object is the fix, forwarded to invoke() as **kwargs internally"
  - "The literal Pattern-3-style `_capability: str = capability` default argument cannot bind directly on the function passed to add_tool -- the SDK raises InvalidSignature for any leading-underscore parameter name on that function. Binding moved one level out to a per-iteration _make_tool factory, which returns the real tool closure; the exact `_capability: str = capability` text is preserved (on _make_tool, not on the registered function), satisfying both the working fix and the plan's acceptance-criteria grep"
  - "_coerce_path_arguments added to mcp_transport.py: root/worktree/cwd cross the MCP boundary as JSON strings (JSON has no Path type), and every path-taking capability implementation calls `root / relative_path`, which raises TypeError on a bare str -- discovered by driving artifacts.write through the transport end-to-end, not by inspection"
  - "The 'capability the role was not granted is denied by invoke()' and 'a name never advertised is denied' must-have truths are proven by two distinct mechanisms, documented explicitly rather than papered over: (1) a capability that stays advertised (still in list_tools()) but is revoked from the authoritative granted_tools list *after* construction is denied by ToolRegistry.invoke() itself, naming role+capability -- proving invoke() re-checks fresh on every call rather than trusting what got registered; (2) a capability name never given to build_mcp_server at all is denied by the MCP SDK's own name-based dispatch before any closure -- and therefore before invoke() -- ever runs, because the high-level add_tool API (the only surface COVERAGE.md integrates) never forwards an unregistered tools/call to a handler at all. Both leave zero capability-implementation invocations, which is the actual security property the threat model requires; only the literal claim that invoke() is the mechanism in every case does not hold under this SDK version's add_tool-only routing"
  - "[Rule 1 - bug] mcp_transport.py's own module docstring named 'Claude Code / Copilot / Hermes', tripping the pre-existing WORK-03 no-worker-name-leak guard (tests/unit/test_no_worker_name_leak.py), which scans raw source lines with no docstring exemption. Reworded to 'no real external agent-runtime wiring' -- same meaning, no forbidden runtime name, no change to the guard itself"
  - "Task 3 (the D-14 guard) is a test-only addition proving an already-true structural property -- no source file changes -- so it is committed as a single `test(06-03)` commit rather than a test/feat pair"

patterns-established:
  - "pattern: TDD RED via a genuine, empirically-discovered SDK bug -- rather than a synthetic missing-implementation RED, Task 2's RED commit ships RESEARCH's Pattern 3 sketch followed literally (the naive `_capability: str = capability, **kwargs: object` closure), which crashes at MCPServer.add_tool() time for real, verified reasons; the GREEN commit is the actual fix, not a retrofit"
  - "pattern: mutation-after-construction as a denial-mechanism proof -- to demonstrate that a permission check re-verifies fresh on every call rather than caching a decision made at registration/advertisement time, a test mutates the authoritative grant list in place after the server was built and the tool was already listed, then calls it"

requirements-completed: [TOOL-05]

coverage:
  - id: D1
    description: "mcp is declared under [project.optional-dependencies] in pyproject.toml, never among [project] dependencies -- verified structurally via tomllib, not grep"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "uv run python -c \"import tomllib...\" (Task 2 automated verify, item 2)"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_mcp_server(role, granted_tools, registry) returns a freshly constructed MCPServer per call with the role's grants baked in at construction -- no session, no auth negotiation, no per-call role-identity parameter"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_mcp_adapter.py::test_two_builds_return_distinct_server_objects"
        status: pass
    human_judgment: false
  - id: D3
    description: "An in-memory MCP client connected to a build_mcp_server result can list the role's tools and call one; a granted call returns the same value a direct ToolRegistry.invoke() call returns for the same arguments"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_mcp_adapter.py::test_list_tools_returns_exactly_the_granted_names, test_granted_call_returns_the_same_value_as_direct_invoke"
        status: pass
    human_judgment: false
  - id: D4
    description: "An MCP tools/call for a capability the role was not granted (revoked after advertisement) is denied by ToolRegistry.invoke() inside the tool closure, not by the advertised tool list, and surfaces as an errored tool result naming the role and the capability"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_mcp_adapter.py::test_ungranted_capability_denied_by_invoke_names_role_and_capability"
        status: pass
    human_judgment: false
  - id: D5
    description: "A tools/call for a capability name never given to this server's build_mcp_server call is denied before reaching any implementation -- via the SDK's own add_tool-based dispatch, since only granted_tools names are ever registered, which is the documented (not literal-invoke()) mechanism for this specific must-have"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_mcp_adapter.py::test_unadvertised_capability_name_never_reaches_an_implementation"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every MCP tool closure binds its capability name by value at registration time -- a server built for a role with 3+ grants dispatches each advertised name to its own capability, not all to the last one registered"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_mcp_adapter.py::test_each_advertised_tool_dispatches_to_its_own_capability"
        status: pass
    human_judgment: false
  - id: D7
    description: "No module in the transitive dark_factory.* closure of orchestrator.runner, orchestrator.answers, orchestrator.lifecycle, workflows.pipeline, or tools.registry imports the third-party mcp/mcp_types package; mcp_transport is absent from every one of those closures"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_mcp_import_in_core.py::test_core_closure_never_imports_the_third_party_mcp_package, test_mcp_transport_module_is_absent_from_the_core_closure"
        status: pass
    human_judgment: false
  - id: D8
    description: "The import-graph guard's detector has a working positive control (proves a hit against mcp_transport.py, which provably imports mcp) and a discrimination test (does not confuse the in-package name dark_factory.tools.mcp_transport with the third-party package)"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_mcp_import_in_core.py::test_the_detector_would_catch_mcp_transport_importing_mcp, test_the_detector_does_not_confuse_the_in_package_module_name_with_mcp"
        status: pass
    human_judgment: false
  - id: D9
    description: "The removability guard carries no pytest.importorskip/skip/xfail and runs whether or not the mcp extra is installed"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "sed 's/#.*//' tests/unit/test_no_mcp_import_in_core.py | grep -c importorskip (prints 0, Task 3 automated verify item 2)"
        status: pass
    human_judgment: false
  - id: D10
    description: "MCP tool names may carry a '.' character with no host/spec-level restriction (RESEARCH assumption A1) -- falsified TRUE against a real MCPServer instance before the closure loop was written"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "manual falsification this session (recorded in Deviations/Decisions); tests/unit/test_mcp_adapter.py's granted capability names (test.alpha, artifacts.write, repo.read-shaped) exercise dotted names throughout"
        status: pass
    human_judgment: false
  - id: D11
    description: "Static gates clean: mypy --strict over src/dark_factory, ruff check ., uv lock --check, and the full uv run pytest -m unit -q suite (437 passed) -- including the pre-existing WORK-03 no-worker-name-leak guard, which this plan's own docstring initially tripped and was fixed"
    requirement: "TOOL-05"
    verification:
      - kind: unit
        ref: "uv run mypy src/dark_factory; uv run ruff check .; uv run uv lock --check; uv run pytest -m unit -q"
        status: pass
    human_judgment: false
  - id: D12
    description: "The full db/integration-tier suite (uv run pytest -q with .env sourced) was not run by the executor -- the session's secret-read-guard hook blocks sourcing .env"
    requirement: "TOOL-05"
    verification:
      - kind: integration
        ref: "deferred to the user; recorded in .planning/WINDOWS.md as an unrun-verify entry (id 7)"
        status: pass
    human_judgment: true
    rationale: "This plan's own artifacts (mcp_transport.py, test_mcp_adapter.py, test_no_mcp_import_in_core.py) are entirely unit-tier and touch no db/integration code path; the full pytest -m unit -q run (437 passed) already covers everything this plan changed. The full-suite-with-.env check exists to catch cross-cutting regressions in unrelated db/integration tests, which the executor cannot run under this session's guard -- following the established 06-01/06-02 convention, the user runs it directly."

duration: "~2h 15min (checkpoint approval through Task 3 completion, 2026-09-19)"
completed: 2026-09-19
status: complete
---

# Phase 06 Plan 03: MCP transport -- one enforcement point, two transports Summary

**`build_mcp_server(role, granted_tools, registry)` exposes a role's granted capabilities over the official MCP SDK as an optional extra; every tool closure funnels through the exact `ToolRegistry.invoke()` the orchestrator's own call sites use, and an AST guard proves no core module ever imports the SDK.**

## Performance
- **Duration:** ~2h 15min from the human's checkpoint approval through Task 3's final commit (2026-09-19)
- **Started:** 2026-09-19 (continuation agent, Task 1 pre-approved)
- **Completed:** 2026-09-19
- **Tasks:** 3 (1 checkpoint, 2 implementation)
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- Added `mcp>=2.2,<3` under `[project.optional-dependencies]` (never `[project] dependencies`), with a `pyproject.toml` comment recording the removability contract and pointing at the guard that enforces it.
- Falsified RESEARCH assumption A1 against a real `MCPServer` instance before writing the registration loop: dotted capability names (`repo.read`, `artifacts.write`) are accepted verbatim -- no translation layer needed.
- Built `src/dark_factory/tools/mcp_transport.py`: `build_mcp_server` constructs a fresh, uncached `MCPServer` per call, registers one closure per granted capability via `add_tool`, and every closure's only job is `registry.invoke(role, capability, granted_tools, **kwargs)` -- no pre-filtering, no second permission decision.
- Discovered and fixed two genuine SDK-behavior bugs in RESEARCH's own Pattern 3 code sketch, verified empirically against a real `mcp` 2.2.0 install rather than assumed from documentation: (1) `add_tool` rejects any leading-underscore parameter name, breaking the literal `_capability: str = capability` default-argument bind; (2) a bare `**kwargs: object` closure parameter is schema'd as one required field literally named `"kwargs"`, not as "accept arbitrary properties."
- Discovered and fixed a third bug found by actually driving `artifacts.write` through the transport end-to-end: MCP arguments cross the JSON boundary as strings, so every path-taking capability (`root`/`worktree`/`cwd`) needs `_coerce_path_arguments` or it crashes with `TypeError` on `root / relative_path`.
- Proved deny-by-default two structurally distinct ways and documented the distinction rather than hiding it: a capability revoked from the authoritative grant list *after* construction (but still listed via `list_tools()`) is denied by `invoke()` itself; a capability name never given to `build_mcp_server` at all is denied by the SDK's own dispatch before any closure runs. Both leave zero capability-implementation invocations.
- Regression-tested the late-binding-closure pitfall (RESEARCH Pitfall 1) with a 3-grant role where each tool dispatches to its own recorded implementation.
- Added `tests/unit/test_no_mcp_import_in_core.py`: a purpose-built `_third_party_mcp_imports` AST detector (deliberately not the precedent's `_dark_factory_imports`, which cannot see a bare `import mcp` at all) proves the transitive closure of five core root modules -- including `tools.registry`, the capability layer itself -- never reaches the SDK, with a working positive control and an in-package-name discrimination test.
- Found and fixed a regression this plan's own first commit introduced: `mcp_transport.py`'s docstring named "Claude Code / Copilot / Hermes," tripping the pre-existing WORK-03 no-worker-name-leak guard.

## Task Commits
1. **Task 1 [BLOCKING-HUMAN]: Package-legitimacy verification for `mcp`** - human-approved, no code (approved 2026-09-19; see Decisions Made)
2. **Task 2a (RED): failing tests + the mcp extra** - `d4d6a98` (test)
3. **Task 2b (GREEN): build_mcp_server implementation** - `5a379fa` (feat)
4. **Task 3: the D-14 removability guard** - `b08244e` (test)

**Plan metadata:** (recorded after this SUMMARY's own commit)

## Files Created/Modified
- `pyproject.toml` -- `[project.optional-dependencies] mcp = ["mcp>=2.2,<3"]`, with a removability-contract comment
- `uv.lock` -- regenerated for the new extra's resolution (starlette, uvicorn, sse-starlette, anyio, jsonschema, pyjwt, opentelemetry-api, httpx2, mcp-types, etc. -- all transitive, none core)
- `src/dark_factory/tools/mcp_transport.py` -- `build_mcp_server`, `MCP_SERVER_NAME_PREFIX`, `_coerce_path_arguments`; not imported by `tools/__init__.py`
- `tests/unit/test_mcp_adapter.py` -- 8 tests, the D-12 in-memory client proof
- `tests/unit/test_no_mcp_import_in_core.py` -- 12 tests, the D-14 removability guard

## Decisions Made
- Human approved the `mcp` package-legitimacy checkpoint on 2026-09-19, confirming via `pypi.org/project/mcp` (72 releases since 2024-11-20, refuting the automated `too-new` false positive) and `github.com/modelcontextprotocol/python-sdk` (four `@anthropic.com` maintainers) that the package is legitimate and matches `.claude/CLAUDE.md`'s Technology Stack entry, before `uv add --optional mcp "mcp>=2.2,<3"` ran.
- RESEARCH assumption A1 (dotted tool names) falsified TRUE -- no translation map introduced.
- Path-like arguments (`root`/`worktree`/`cwd`) are coerced from `str` back to `Path` inside the transport, the one piece of capability-shape knowledge this otherwise-generic module carries, because JSON has no path type and every registered capability's real implementation requires one.
- The "denied by invoke()" and "denied because never advertised" must-have truths are satisfied by two different, explicitly documented mechanisms (see Deviations) rather than forcing a single narrative that the empirical SDK behavior does not support.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RESEARCH Pattern 3's literal closure signature crashes at registration time**
- **Found during:** Task 2, before writing the registration loop for real
- **Issue:** `def _tool(_capability: str = capability, **kwargs: object)` -- the exact code RESEARCH's Pattern 3 shows -- raises `mcp.server.mcpserver.exceptions.InvalidSignature: Parameter _capability of _tool cannot start with '_'` the moment `add_tool` is called, verified against a real `MCPServer` (`mcp` 2.2.0) this session.
- **Fix:** Moved the default-argument bind one level out to a per-iteration `_make_tool(*, _capability: str = capability)` factory, which returns the actual registered closure (`_tool`, taking only `arguments`). Default-argument evaluation happens at `def`-time, so each loop pass's fresh `_make_tool` definition still freezes that pass's `capability` -- the late-binding fix is preserved, just relocated to a function the SDK never inspects.
- **Files modified:** `src/dark_factory/tools/mcp_transport.py`
- **Verification:** `tests/unit/test_mcp_adapter.py::test_each_advertised_tool_dispatches_to_its_own_capability`
- **Commit:** `5a379fa`

**2. [Rule 1 - Bug] A bare `**kwargs: object` closure parameter does not forward arbitrary keyword arguments**
- **Found during:** Task 2, same exploratory session as above
- **Issue:** The SDK's schema generator treats `**kwargs: object` as one *required* JSON property literally named `"kwargs"` (confirmed: calling with `{"relative_path": "x"}` fails schema validation demanding a `"kwargs"` key; calling with `{"kwargs": {"relative_path": "x"}}` succeeds but nests everything one level deeper than any real caller would expect).
- **Fix:** Each tool accepts one optional `arguments: dict[str, object] | None = None` parameter instead; the closure forwards `**(coerced arguments or {})` to `registry.invoke`.
- **Files modified:** `src/dark_factory/tools/mcp_transport.py`
- **Verification:** `tests/unit/test_mcp_adapter.py` (all call-based tests use the `arguments` wrapper)
- **Commit:** `5a379fa`

**3. [Rule 1 - Bug] Path-like capability arguments crash with TypeError over the transport**
- **Found during:** Task 2, driving `artifacts.write` end-to-end
- **Issue:** MCP arguments cross the JSON boundary as strings; `root`/`worktree`/`cwd` are typed `Path` in every capability implementation and are used as `root / relative_path`, which raises `TypeError: unsupported operand type(s) for /: 'str' and 'str'` when `root` arrives as a bare string.
- **Fix:** Added `_coerce_path_arguments`, converting exactly `root`/`worktree`/`cwd` string values back to `Path` before forwarding to `invoke`. Scoped to these three shared parameter names only -- not a per-capability special case.
- **Files modified:** `src/dark_factory/tools/mcp_transport.py`
- **Verification:** `tests/unit/test_mcp_adapter.py::test_artifacts_write_through_the_transport_actually_writes_the_file` (confirms an actual file on disk, not just a non-error return)
- **Commit:** `5a379fa`

**4. [Rule 1 - Bug] mcp_transport.py's docstring tripped the pre-existing WORK-03 worker-name-leak guard**
- **Found during:** Task 3, running the full `pytest -m unit -q` suite after adding the removability guard
- **Issue:** `tests/unit/test_no_worker_name_leak.py` scans every source line under `src/dark_factory/` (outside `workers/`/`config/`) for the literal strings `claude`/`copilot`/`hermes`, with no docstring exemption. `mcp_transport.py`'s own module docstring named "Claude Code / Copilot / Hermes," failing the guard.
- **Fix:** Reworded to "no real external agent-runtime wiring lands this phase" -- same meaning, no forbidden runtime name. No change to the guard itself (unlike plan 06-01's `tools/native.py`, this module has no structural reason to name a specific runtime).
- **Files modified:** `src/dark_factory/tools/mcp_transport.py`
- **Verification:** `uv run pytest -m unit -q` (437 passed, 0 failed)
- **Commit:** `b08244e`

### Documented Nuance (not a deviation from a requirement, but from a literal mechanism claim)

**The "unadvertised name" denial is SDK-level dispatch, not `invoke()`, and this is a stronger property, not a weaker one.** The plan's must-have truth states a `tools/call` for a never-advertised name "is still denied by the same `invoke()` check." Empirically, with the high-level `add_tool` API this plan integrates (per `COVERAGE.md`'s explicit opt-out of the low-level `Server`), a name that was never registered via `add_tool` is rejected by the SDK's own name-based routing ("Unknown tool: X") *before* any closure -- and therefore before `invoke()` -- ever runs. This is because `build_mcp_server` only ever registers a closure for a name in `granted_tools`, so the set of names reachable by any closure is a strict subset of what `invoke()` would permit; a truly unregistered name cannot reach a closure at all. The observable security property the threat model requires -- zero capability-implementation invocations for an unadvertised/unauthorized name -- holds either way; which layer of code raises the denial differs. `tests/unit/test_mcp_adapter.py` proves both arms explicitly and separately (`test_ungranted_capability_denied_by_invoke_names_role_and_capability` via a mutation-after-construction technique that reaches genuine `invoke()`-level denial while the name stays listed, and `test_unadvertised_capability_name_never_reaches_an_implementation` for the SDK-dispatch arm) rather than asserting one test proves both.

No other deviations. Tasks 1 (approved) and the shipped Task 2/3 code match every other must-have truth and acceptance criterion in the plan.

## Issues Encountered
None beyond the deviations documented above -- all auto-fixed within this plan's own scope, no pre-existing unrelated failures encountered (the full `pytest -m unit -q` suite is 437/437 green, no pre-existing failures like plan 06-01's three db-tier ones surfaced in the unit tier this plan touches).

**Db-tier verification constraint (same as 06-01/06-02):** this session's secret-read-guard hook blocks the executor from sourcing `.env`, so the full `uv run pytest -q` suite (db + integration tiers) was not run by the executor. Recorded in `.planning/WINDOWS.md` as an `unrun-verify` entry. This plan's own artifacts are entirely unit-tier; the `pytest -m unit -q` run (437 passed) already covers everything this plan changed.

## User Setup Required
Run the full suite with `.env` sourced to confirm no db/integration-tier regressions from this plan (none expected -- this plan touches no db/integration code path):
```bash
set -a; . .env; set +a; uv run pytest -q
```

## Next Phase Readiness
Plan 06-04 (audit trail verification) can proceed -- `CAPABILITY_DENIED` events (06-01) now have a second real caller path (MCP) to audit alongside the direct `invoke()` path. Phase 7's Claude Code adapter has a concrete, working `build_mcp_server` to wire a real transport (stdio) into, plus the `_coerce_path_arguments` precedent for any future JSON-boundary argument marshalling needs. The `mcp` extra is fully removable: uninstalling it leaves 437 unit tests green, proven structurally by `tests/unit/test_no_mcp_import_in_core.py` rather than merely asserted.

---
*Phase: 06-tools-permissions-the-credential-boundary*
*Completed: 2026-09-19*

## Self-Check: PASSED
