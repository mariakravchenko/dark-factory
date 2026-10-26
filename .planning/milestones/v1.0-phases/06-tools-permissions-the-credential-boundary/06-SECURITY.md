---
phase: "6"
slug: "tools-permissions-the-credential-boundary"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-19"
---

# Phase 6 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| role config → orchestrator | A role's `tools:` list is repo-controlled YAML; it decides what a role may do, so a malformed or over-broad entry is an authorization input | capability names |
| orchestrator → capability implementation | `ToolRegistry.invoke()` is the one place a grant is checked; everything past it runs with the role's authority | role identity, capability name, call arguments |
| capability caller → filesystem | `repo.*` / `artifacts.*` arguments are paths that must stay inside the run worktree / run root | file paths, file content |
| Dark Factory process → worker subprocess | The process holding `DATABASE_URL` / `GITHUB_TOKEN` spawns a process that must never see them | environment variables |
| capability caller → spawned command | The command and its arguments for `shell.execute` originate outside this function | argv, captured stdout/stderr |
| MCP client → tool closure | A protocol peer names a tool and supplies arguments; both are untrusted input crossing into orchestrator authority | tool name, JSON arguments |
| PyPI → the build | The `mcp` package and its transitive tree enter the project's supply chain | third-party dependency code |
| orchestrator → persisted audit trail | Every string written to `run_events.payload`, `role_executions.error`, or a log line leaves the process and may be read by a reviewer | event payloads, error strings, log lines |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-05 | Elevation of Privilege | `ToolRegistry.invoke()` grant lookup (06-01) | critical | mitigate | Exact-name set membership against the role's persisted `tools:` snapshot, checked before implementation lookup; no prefix/wildcard/default-allow. Verified directly in `tools/registry.py`; proven by `tests/unit/test_tool_registry.py` | closed |
| T-06-01 | Information Disclosure | `build_worker_env` (06-02) | critical | mitigate | Comprehension over `WORKER_ENV_ALLOWLIST` from an empty dict — no `os.environ.copy()`, spread, or exclusion-filter. Verified directly in `tools/env.py`; structurally guarded by `tests/unit/test_no_environ_copy.py`, behaviorally by `tests/integration/test_worker_env_boundary.py` | closed |
| T-06-07 | Information Disclosure | `repo.read`/`repo.search`/`artifacts.read` path args (06-01) | high | mitigate | Every path resolves through `resolve_under_run_root` or worktree-containment check before any file opens; out-of-bounds raises `ArtifactPathError` | closed |
| T-06-09 | Elevation of Privilege | `repo.write`/`repo.write_tests` path args (06-01) | high | mitigate | Same containment resolution as T-06-07; `enforce_write_scope` (Phase 5) still governs landing location — complementary, neither skipped | closed |
| T-06-02 | Tampering | `shell_execute` argv construction (06-02) | high | mitigate | Command crosses as an explicit argument sequence to `subprocess.Popen`; never joined into a string, never shell-interpreted; a bare string argument is rejected with a typed error | closed |
| T-06-14 | Elevation of Privilege | `shell.execute` invoked without grant (06-02) | high | mitigate | Grant check is `ToolRegistry.invoke()`'s, unchanged from 06-01 — `shell_execute` performs no permission logic of its own. Proven by the ungranted-role arm of `tests/unit/test_shell_execute.py` | closed |
| T-06-15 | Information Disclosure | credential via argv vs. env (06-02) | high | mitigate | `build_worker_env` is the only credential channel; `shell_execute` never accepts or appends a credential parameter to argv | closed |
| T-06-03 | Elevation of Privilege | MCP tool closure (06-03) | high | mitigate | Deny-by-default lives inside `registry.invoke()`, called from every closure; the advertised tool list is never consulted as a permission source. Proven by the unadvertised-name arm of `tests/unit/test_mcp_adapter.py` | closed |
| T-06-SC | Tampering | `mcp` PyPI package supply chain (06-03) | high | mitigate | `[SUS]` package-legitimacy verdict (`too-new`, `unknown-downloads` — both confirmed false positives against PyPI/GitHub history and `.claude/CLAUDE.md`'s own pinned entry) required a `gate="blocking-human"` checkpoint before install. Human-approved 2026-09-19 after visual verification; never auto-approvable | closed |
| T-06-08 | Repudiation | denial with no persisted event (06-01) | medium | mitigate | `CAPABILITY_DENIED` is appended to the same `events` list `apply_transition` writes for `ROLE_FAILED`/`RUN_FAILED`, inside the one mutation transaction | closed |
| T-06-04 | Information Disclosure | `CAPABILITY_DENIED` event payload (06-01, re-verified 06-04) | medium | mitigate | Payload narrowed to `{role, capability, reason}`, never carries invocation kwargs; rides the existing `redact()` pass at the `apply_transition` call site. Verified by the payload-shape assertion in `tests/integration/test_capability_denial_no_secret_leak.py` | closed |
| T-06-10 | Tampering | role `tools:` entry naming an unregistered capability (06-01) | medium | mitigate | Validated by registry membership at config-load time, before `create_run`, raising `ConfigError` → CLI exit 2, no orphan `runs` row | closed |
| T-06-12 | Denial of Service | `shell_execute` unbounded wait (06-02) | medium | mitigate | Every spawn carries an explicit `timeout`; on expiry the whole process group terminates (`start_new_session=True`); result returns `timed_out=True` with partial output | closed |
| T-06-13 | Information Disclosure | captured `shell.execute` stdout/stderr (06-02) | medium | mitigate | Streams are returned to the caller, not logged/persisted by this module; any caller that persists them crosses the single `redact()` pass (SEC-02) | closed |
| T-06-16 | Tampering | MCP tool-call arguments (06-03) | medium | mitigate | `MCPServer` validates arguments against the JSON Schema derived from each closure's type hints before the closure body runs; capability-specific constraints stay in the implementations | closed |
| T-06-17 | Information Disclosure | `ToolError` message to MCP client (06-03) | medium | mitigate | The message is `CapabilityDeniedError`'s own string — names role/capability/grant list, never interpolates invocation kwargs | closed |
| T-06-19 | Information Disclosure | `role_executions.error` on a denied attempt (06-04) | medium | mitigate | Column receives `str(CapabilityDeniedError)`, built from role name, capability name, and grant list only — all config-derived, never worker/repo-supplied. Asserted against the persisted column | closed |
| T-06-20 | Information Disclosure | structured log lines during a denied attempt (06-04) | medium | mitigate | Phase 1's `structlog` secret-redaction processor covers every log line; sweep captures the denied run's log sink and greps for every `Settings.known_secret_values()` entry | closed |
| T-06-21 | Repudiation | a Phase 6 criterion with no reachable proof (06-04) | medium | mitigate | The 17-check acceptance gate fails when a mapped proof file is missing or has no `def test_`, naming the criterion rather than the path | closed |
| T-06-11 | Spoofing | `role` argument passed to `invoke()` (06-01) | low | accept | `role` is supplied by orchestrator-owned code from the persisted snapshot node, never by a worker — no untrusted caller inside this process this phase | closed |
| T-06-06 | Spoofing | `role` identity at `build_mcp_server` construction (06-03) | low | accept | No session/auth negotiation this phase; server constructed in-process by orchestrator-owned code with role baked in. Explicitly reopened in Phase 7 when a real external worker connects over a real transport | closed |
| T-06-18 | Denial of Service | `mcp`'s transitive `starlette`/`uvicorn`/`httpx2` surface (06-03) | low | accept | None reachable this phase — no network transport started, no port bound, only an in-memory client. Extra not installed in a deployment that doesn't want it. Re-assessed in Phase 7 if a transport is actually served | closed |
| T-06-22 | Information Disclosure | a short configured secret excluded from redaction (06-04) | low | accept | `Settings.known_secret_values()` deliberately skips values shorter than 8 characters so `redact()` cannot shred ordinary text — pre-existing Phase 1 behavior, unchanged by this phase, recorded rather than silently inherited | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (currently `high`) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| A-06-E1 | T-06-11 | No untrusted caller can spoof `role` this phase — orchestrator-owned code only | Plan 06-01 authoring | 2026-09-17 |
| A-06-E2 | T-06-06 | No session/auth negotiation this phase; MCP server constructed in-process with role baked in — reopened Phase 7 | Plan 06-03 authoring | 2026-09-17 |
| A-06-E3 | T-06-18 | `mcp`'s network-transport surface is entirely unreachable this phase (in-memory client only, extra not installed by default) — reassessed Phase 7 | Plan 06-03 authoring | 2026-09-17 |
| A-06-E4 | T-06-22 | Pre-existing Phase 1 redaction floor (8-char minimum) — unchanged by this phase, documented rather than silently inherited | Plan 06-04 authoring | 2026-09-19 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-19 | 23 | 23 | 0 | `/gsd-secure-phase 06` — retroactive register built from all four plans' `<threat_model>` blocks (register_authored_at_plan_time: true, asvs_level: 1); short-circuited per the L1/asvs-1 rule after spot-verifying the two critical-severity mitigations (T-06-05, T-06-01) directly against `tools/registry.py` and `tools/env.py` |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-19
