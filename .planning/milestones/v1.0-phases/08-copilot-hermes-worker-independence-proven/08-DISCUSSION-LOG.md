# Phase 8: Copilot & Hermes — Worker Independence Proven - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-21
**Phase:** 8-Copilot & Hermes — Worker Independence Proven
**Areas discussed:** Copilot credential boundary, CLI access & spike approach, NEEDS_INPUT signal reuse, Role-reassignment proof scenario

---

## Copilot credential boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Separate Settings field | Add `Settings.copilot_github_token: SecretStr \| None`, mirroring D-02's `anthropic_api_key` pattern — a distinct, worker-scoped credential separate from Dark Factory's own `github_token`. | ✓ |
| Reuse github_token, scoped down | Let `CopilotWorker` read `Settings.github_token` and pass it through `build_worker_env()` as the worker's credential (same value, different channel). | |
| Defer to Copilot's own ambient auth | Don't pass any credential explicitly — assume the environment already has `gh auth login`/`GITHUB_TOKEN` set up ambiently, outside Dark Factory's env-building path. | |

**User's choice:** Separate Settings field (recommended)
**Notes:** Keeps Dark Factory's infra `GITHUB_TOKEN` (protected by TOOL-04/SEC-01) categorically distinct from whatever GitHub-scoped credential the Copilot CLI itself authenticates with, even though both may be GitHub PATs in practice.

---

## CLI access & spike approach

| Option | Description | Selected |
|--------|-------------|----------|
| Docs-only now, spike later | Build both adapters against CLAUDE.md's documented invocation patterns now; integration suites are `pytest.mark.skipif`-guarded on CLI/credential absence (QUAL-03's own design). Real spike happens whenever the CLIs are installed. | ✓ |
| I'll install the CLIs first | Pause discussion/planning until copilot/hermes are installed so the spike happens for real before or during planning. | |
| Best-effort guess, revisit if wrong | Build on documented flags with no spike planned at all; accept the risk of divergence, fix later. | |

**User's choice:** Docs-only now, spike later (recommended)
**Notes:** Neither `copilot` nor `hermes` is installed in this environment (confirmed via `which`). This doesn't block the phase since QUAL-03 already requires skip-not-fail semantics for absent credentials/CLI.

---

## NEEDS_INPUT signal reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, reuse verbatim | Same `NEEDS_INPUT_MARKER`, same regex extraction, same prompt protocol as `ClaudeCodeWorker` (D-01, Phase 7) — one shared pause contract across all three adapters. | ✓ |
| Adapter-specific, own discretion | Let each adapter derive its own pause-signal convention suited to that CLI's idioms. | |

**User's choice:** Yes, reuse verbatim (recommended)
**Notes:** Keeps HITL-01/02 behavior identical regardless of assigned worker; the shared contract suite pins pause/resume semantics once instead of three times.

---

## Role-reassignment proof scenario

| Option | Description | Selected |
|--------|-------------|----------|
| Roadmap's own example | Architect on Copilot, Developer on Claude Code, QA on Hermes — matches ROADMAP.md's Phase 8 goal wording verbatim. | ✓ |
| Different assignment | A different role→worker mapping than the roadmap's example. | |

**User's choice:** Roadmap's own example (recommended)
**Notes:** BA's worker assignment is left to planning's discretion since it isn't named in the roadmap's example and isn't load-bearing for the independence proof.

---

## Claude's Discretion

- Exact `Settings` field name for the Copilot credential and the typed error class/message on first missing use.
- Whether Hermes needs its own `Settings` credential field at all — CLAUDE.md documents no explicit Hermes credential requirement; research should confirm.
- Whether the `NEEDS_INPUT` marker/regex is extracted to a shared module or duplicated per adapter file.
- Exact module/class names and file locations for the two new adapters (expected: `CopilotWorker`/`workers/copilot.py`, `HermesWorker`/`workers/hermes.py`).
- Per-adapter `WorkerCapabilities` values (native_resume, session_id, non_interactive, structured_output) — derive from actual CLI docs during research, likely `native_resume=False` for both.
- Whether `NATIVE_TOOL_CONTRACT`'s existing Copilot/Hermes entries need adjustment once the adapters are built.
- Exact skip condition/message for each adapter's integration suite (PATH check vs. credential-env check vs. both).

## Deferred Ideas

None — discussion stayed within phase scope. The live hands-on spike of the real `copilot`/`hermes` CLIs is deferred to whenever those CLIs are installed, not treated as a future-phase backlog item.
