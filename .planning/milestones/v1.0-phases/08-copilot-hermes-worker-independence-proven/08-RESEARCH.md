# Phase 8: Copilot & Hermes — Worker Independence Proven - Research

**Researched:** 2026-09-21
**Domain:** Non-interactive invocation of two external agent CLIs (GitHub Copilot CLI, NousResearch Hermes Agent CLI), normalized into the existing `CodingWorker` contract; skip-guarded live-credential integration testing.
**Confidence:** MEDIUM — every flag/env-var claim below is grounded in official documentation (docs.github.com, hermes-agent.nousresearch.com, github.com/NousResearch/hermes-agent) fetched this session, not training memory, but neither CLI was actually run (D-02) so exact JSON/JSONL field shapes and a few flag *combinations* remain unconfirmed and are marked accordingly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (Copilot credential boundary):** `Settings` gains a new, separate optional credential field for the Copilot CLI (e.g. `copilot_github_token: SecretStr | None = None`), distinct from Dark Factory's own `github_token`. Absence only surfaces as a clear, typed error when a run actually tries to invoke a `copilot` role, and the value flows to the subprocess exclusively through `build_worker_env(role, env_var_name=..., value=...)` — never through `os.environ.copy()`.
- **D-02 (CLI access & spike approach):** Neither `copilot` nor `hermes` is installed in this environment. Both adapters are implemented this phase against CLAUDE.md's already-documented, already-researched invocation patterns rather than from a live hands-on spike. Each adapter's integration test suite is written and `pytest.mark.skipif`-guarded on CLI/credential absence. Contract-suite coverage is proven against a faked CLI executable on `PATH`, never a live binary — see `tests/support/fake_claude_cli.py` for the exact pattern to mirror.
- **D-03 (NEEDS_INPUT signal reuse):** `CopilotWorker` and `HermesWorker` reuse Claude Code's exact pause-signal convention verbatim — the same `NEEDS_INPUT_MARKER` literal (`"NEEDS_INPUT:"`), the same `NEEDS_INPUT_PROTOCOL` prompt text, and (where practical) the same `_NEEDS_INPUT_RE` extraction regex from `workers/claude_code.py`. Planning decides whether the marker constant/regex is extracted to a shared module or duplicated per adapter.
- **D-04 (Role-reassignment proof scenario, WORK-09/SC2):** The SC2 proof uses ROADMAP.md's own literal example: Architect on `copilot`, Developer on `claude-code`, QA on `hermes` (BA's worker is planning's discretion). Requires `.dark-factory/roles/*.yaml` `worker:` fields updated for `ARCHITECTURE`→`copilot` and `QA`→`hermes`.

### Claude's Discretion

- Exact `Settings` field name for the Copilot credential beyond "distinct from `github_token`" — and the exact typed error class/message on first missing use, mirroring `MissingWorkerCredentialError`'s existing shape.
- Whether Hermes needs its own `Settings` credential field at all, and what it's named — **this research resolves this, see Finding 1 below.**
- Whether the `NEEDS_INPUT` marker/regex (D-03) is extracted to a shared module or duplicated per adapter file.
- Exact module/class names (`CopilotWorker`, `HermesWorker`) and file locations (`workers/copilot.py`, `workers/hermes.py`).
- Per-adapter `WorkerCapabilities` values (`native_resume`, `session_id`, `non_interactive`, `structured_output`) — **this research resolves this, see Finding 2 below.**
- Whether Copilot's and Hermes's `NATIVE_TOOL_CONTRACT` entries need any adjustment once the adapters are actually built.
- Exact skip condition/message for each adapter's integration suite (D-02) — e.g. `shutil.which` on `PATH` vs. checking the credential env var vs. both.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. The live hands-on spike of the real `copilot`/`hermes` CLIs (D-02) is explicitly deferred to whenever those CLIs are actually installed — not a backlog item, since QUAL-03's skip-when-absent integration tests already accommodate it without blocking this phase's completion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORK-05 | `CopilotWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | Finding 3 (auth/flag matrix) + Code Examples give the exact argv/env shape to mirror `ClaudeCodeWorker`'s `_spawn_and_parse` pipeline for `copilot` |
| WORK-06 | `HermesWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | Finding 1 (credential model) + Finding 4 (flag matrix) give the exact argv/env shape for `hermes` |
| WORK-09 | Any role can be assigned to any supported worker via configuration with no change to workflow code | Already-decided mechanism (D-04); no new research needed — registry/config wiring is unchanged from Phase 3/7 |
| QUAL-03 | Each real worker adapter (ClaudeCode, Copilot, Hermes) has its own integration test suite, skipped when credentials are absent | **Load-bearing finding, see "Scope Correction" below** — QUAL-03 is entirely mapped to Phase 8, so `ClaudeCodeWorker`'s own skip-guarded live suite does not exist yet either and must be added this phase, not just Copilot's/Hermes's |
</phase_requirements>

## Scope Correction (read this first)

`ROADMAP.md` maps **QUAL-03 to Phase 8 only** — Phase 7's requirement set was `WORK-04, WORK-07, HITL-04, HITL-05, QUAL-02, QUAL-04` (confirmed by re-reading `.planning/ROADMAP.md`'s Phase 7 section this session — `QUAL-03` does not appear there). `grep -rln "skipif" tests/` in the current tree returns **zero matches** — no `pytest.mark.skipif`-guarded suite exists anywhere in the repo yet, including for `claude-code`. Phase 7 proved `ClaudeCodeWorker` entirely against a faked CLI on `PATH` (`tests/support/fake_claude_cli.py`), which is a different thing from "an integration suite that runs for real when the live binary + credential are present, and skips otherwise."

**Consequence for planning:** this phase must add **three** skip-guarded integration suites — `claude-code`, `copilot`, and `hermes` — not two. The fake-CLI/contract-suite pattern (D-02, already covers Copilot/Hermes) stays as-is; a *new*, additional suite per adapter (e.g. `tests/integration/test_claude_code_live.py`, `test_copilot_live.py`, `test_hermes_live.py`) is needed to literally satisfy QUAL-03's "skipped — not failed — when credentials are absent" wording, closing a gap Phase 7 left open under a different (but adjacent-sounding) name.

## Summary

Both new CLIs are invoked the same shape `ClaudeCodeWorker` already established — spawn non-interactively via `subprocess.Popen` with a credential-bounded `build_worker_env()` environment, stream stdout/stderr to files, kill on timeout by process group, parse the captured text for a `NEEDS_INPUT:` marker, and normalize to `WorkerResult`. The two CLIs differ from Claude Code (and from each other) in exactly the four `WorkerCapabilities` axes WORK-07 names, and this research pins each axis with a documentation citation rather than an assumption:

- **Copilot** authenticates via `COPILOT_GITHUB_TOKEN` (highest-precedence, Copilot-specific env var — a fine-grained PAT with the `Copilot Requests` permission, owned by a personal account, never a classic `ghp_` token). Non-interactive execution is `-p "<prompt>" --no-ask-user` plus one `--allow-tool` per granted capability (never `--allow-all-tools`); tools not explicitly allowed are refused, not silently permitted — confirming `NATIVE_TOOL_CONTRACT`'s existing deny-by-default claim. `--resume` exists only as an *interactive* session picker in the general docs and is entirely absent from the CLI's own programmatic-reference page, so `native_resume=False` is a documented fact, not a guess.
- **Hermes** has **no single mandatory credential** — it is multi-provider and reads whichever of 20+ provider API-key env vars is configured (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, …), sourced from the process environment or `~/.hermes/.env`. Since `Settings.anthropic_api_key` already exists, **Hermes needs no new Settings field** — the adapter reuses `anthropic_api_key`, injected as `ANTHROPIC_API_KEY` via `build_worker_env`, the same way Claude Code does. Non-interactive execution is `hermes chat -q "<prompt>" --oneshot` (the CLAUDE.md pattern is already correct); `--oneshot` is additionally *implied automatically* whenever stdin is not a TTY, so a subprocess spawned with `stdin=DEVNULL` degrades safely even if a flag were dropped.
- Both CLIs expose a JSON/JSONL structured-output mode (`--output-format=json` for Copilot; `--format stream-json` for Hermes), but neither's field schema is documented, and neither invocation is part of CLAUDE.md's already-locked pattern. **Recommendation: do not adopt either structured mode this phase** — parse plain stdout text with the shared `NEEDS_INPUT:` regex, exactly as Claude Code's own summary-text extraction works, and declare `structured_output=False` for both adapters (this reflects what the adapter actually does, not what the CLI could theoretically do).

**Primary recommendation:** structurally clone `ClaudeCodeWorker`'s `_spawn_and_parse` pipeline for each adapter, changing only argv-construction and env-var name; declare `WorkerCapabilities(native_resume=False, session_id=False, non_interactive=True, structured_output=False, emits_changed_files=False)` for **both** Copilot and Hermes; and budget a third skip-guarded integration suite for `claude-code` alongside the two new ones (Scope Correction above).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Copilot/Hermes CLI subprocess invocation | Worker adapter (`workers/copilot.py`, `workers/hermes.py`) | — | Same tier `ClaudeCodeWorker` already occupies; adapters never import orchestrator/workflow/persistence code |
| Credential storage & redaction | Config (`Settings`) | Worker adapter (reads at call time) | `known_secret_values()` walks `model_fields` automatically; no new redaction wiring needed for a new `SecretStr` field |
| Role→worker assignment | Configuration (`.dark-factory/roles/*.yaml`) | Registry (`workers/registry.py`) | D-04 — pure config edit + registry factory swap, zero orchestrator code change (WORK-09) |
| Native tool restriction (allow/deny) | Worker adapter (translates `NATIVE_TOOL_CONTRACT` to CLI flags) | `ToolRegistry` (governs Dark-Factory-initiated calls only) | A CLI's own native filesystem/shell access is outside `ToolRegistry.invoke()`'s reach; each adapter must translate the grant itself |
| Live-credential integration test skip logic | Test suite (`tests/integration/`) | — | New tier this phase — no existing skip-guarded suite precedent in the repo (Scope Correction) |

## Standard Stack

No new Python packages are introduced by this phase. Both `copilot` and `hermes` are external CLI binaries invoked via `subprocess`, exactly like `claude` in Phase 7 — they are not `pip`/`npm` dependencies of this project and do not appear in `pyproject.toml`. `shutil` (stdlib) is the only new import surface, for the integration-suite skip condition (`shutil.which("copilot")` / `shutil.which("hermes")`).

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `subprocess` (stdlib) | 3.12 | Spawn `copilot`/`hermes` non-interactively | Identical pattern already proven for `claude` in `workers/claude_code.py` |
| `shutil` (stdlib) | 3.12 | `shutil.which()` binary-presence check for the QUAL-03 skip condition | No existing precedent in the repo (`grep -rn shutil.which` returns nothing) — this phase's first use |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Plain-text stdout parsing + `NEEDS_INPUT:` marker | `--output-format=json` (Copilot) / `--format stream-json` (Hermes) | Structured modes exist but their field schemas are undocumented and untested this phase (D-02); adopting them now risks a parser built against a guessed shape. Revisit once the live spike (post-Phase-8) confirms the real JSON/JSONL fields. |
| Reusing `Settings.anthropic_api_key` for Hermes | A new dedicated `Settings.hermes_api_key` mapped to, e.g., `OPENROUTER_API_KEY` | A dedicated field gives Hermes a credential failure independent of Claude Code's, which is a genuine "worker independence" argument — but it is not required by any documentation constraint (Hermes accepts `ANTHROPIC_API_KEY` natively) and adds a field with no D-01-style ambiguity to resolve. Flagged as [ASSUMED] discretion, not a hard call. |

**Installation:** none — no new package-manager dependency.

## Package Legitimacy Audit

Not applicable this phase. No new PyPI/npm/crates package is installed; `copilot` and `hermes` are externally-provisioned CLI binaries invoked via `subprocess.Popen`, the same category as `claude` in Phase 7 — none of the three are project dependencies declared in `pyproject.toml`/`uv.lock`, so the Package Legitimacy Gate (registry/downloads/postinstall-script checks) has no applicable target.

## Architecture Patterns

### System Architecture Diagram

```
 role config (.dark-factory/roles/ARCHITECTURE.yaml: worker: copilot)
         |
         v
 WorkerRegistry.get("copilot") -----> CopilotWorker()            (same for "hermes" -> HermesWorker())
         |
         v
 orchestrator/runner.py: worker.execute(context) / worker.resume(context, previous, answer)
         |
         v
 CopilotWorker._execute / ._resume
   |-- _base_argv(context): translate context.tools -> --allow-tool entries via NATIVE_TOOL_CONTRACT
   |-- build_worker_env(role, env_var_name="COPILOT_GITHUB_TOKEN", value=settings.copilot_github_token)
   |-- subprocess.Popen([...], cwd=work_dir, env=env, stdin=DEVNULL, stdout/stderr->log files, start_new_session=True)
   |-- on timeout: os.killpg(...) -> FAILED WorkerResult
   |-- on exit!=0: FAILED WorkerResult (stderr excerpt)
   |-- on exit==0: scrub logs -> _extract_needs_input(stdout_text)
   |        |-- marker found -> NEEDS_INPUT WorkerResult(questions=[...])
   |        `-- no marker    -> COMPLETED WorkerResult(summary=stdout_text)
   v
 WorkerResult (status, summary, questions, worker_session_id=None, metadata)
         |
         v
 orchestrator persists role_executions row, applies transition (unchanged — worker-agnostic)
```

`HermesWorker` is the identical diagram with `hermes chat -q "<prompt>" --oneshot` in place of the `copilot` invocation and `env_var_name="ANTHROPIC_API_KEY"` (reusing `Settings.anthropic_api_key`) in place of the Copilot credential.

### Recommended Project Structure

```
src/dark_factory/workers/
├── claude_code.py     # existing (Phase 7) — unchanged
├── copilot.py         # new — CopilotWorker, mirrors claude_code.py's shape
├── hermes.py           # new — HermesWorker, mirrors claude_code.py's shape
└── needs_input.py      # new, OPTIONAL (Claude's Discretion, D-03) — shared
                         # NEEDS_INPUT_MARKER / NEEDS_INPUT_PROTOCOL / _NEEDS_INPUT_RE
                         # if planning chooses to extract rather than duplicate
tests/support/
├── fake_claude_cli.py  # existing (Phase 7) — template
├── fake_copilot_cli.py # new — mirrors fake_claude_cli.py exactly
└── fake_hermes_cli.py  # new — mirrors fake_claude_cli.py exactly
tests/integration/
├── test_claude_code_live.py  # new — closes the Scope-Correction gap (QUAL-03 for claude-code)
├── test_copilot_live.py       # new — skipif(no `copilot` on PATH or no copilot_github_token)
└── test_hermes_live.py        # new — skipif(no `hermes` on PATH or no anthropic_api_key)
```

### Pattern 1: Skip-guarded live integration test

**What:** A test module marked `pytest.mark.integration` whose tests are individually or module-wide `pytest.mark.skipif`-guarded on both binary presence (`shutil.which`) and credential presence, so it **collects** in every environment but only **executes** where both are true.
**When to use:** For QUAL-03's literal requirement — one such module per real adapter (`claude-code`, `copilot`, `hermes`).
**Example:**
```python
# Source: pattern synthesized from QUAL-03's literal wording ("skipped — not
# failed — when that runtime's credentials are absent") — no existing
# in-repo precedent (grep -rn "skipif" tests/ returns nothing as of Phase 7).
import shutil

import pytest

from dark_factory.config.settings import get_settings

pytestmark = pytest.mark.integration

_BINARY_MISSING = shutil.which("copilot") is None
_CREDENTIAL_MISSING = get_settings().copilot_github_token is None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _BINARY_MISSING,
        reason="copilot CLI not found on PATH",
    ),
    pytest.mark.skipif(
        _CREDENTIAL_MISSING,
        reason="Settings.copilot_github_token is not configured",
    ),
]


def test_copilot_worker_executes_a_trivial_role() -> None:
    """Runs only when both the binary and credential are present -- this is
    the real spike D-02 defers, executed automatically the day the CLI is
    installed, with zero code change required to make it run."""
    ...
```

### Anti-Patterns to Avoid

- **`--allow-all-tools` / `--allow-all-paths` (Copilot):** Both bypass the deny-by-default translation `NATIVE_TOOL_CONTRACT` already specifies. `--allow-all-paths` in particular disables Copilot's own path-confinement check — the rough native analogue of Claude Code's `cwd=<worktree>` confinement — so passing it would widen the worktree boundary the same way `--dangerously-skip-permissions` would for Claude Code.
- **`--share` / `--share-gist` (Copilot):** Exports the session transcript to a file or a GitHub gist *outside* Dark Factory's own log/artifact storage. A transcript exported this way bypasses `_scrub_log_in_place`'s redaction pass entirely — a live secret value could reach a public or org-visible gist. Never pass either flag (SEC-01).
- **Assuming Hermes needs a `NOUS_API_KEY`-shaped credential:** No such single variable is documented. Gating `HermesWorker` behind a nonexistent credential name would make every Hermes-assigned role fail with a misleading error. Use `Settings.anthropic_api_key` (already present) instead.
- **Adopting `--output-format=json`/`--format stream-json` without having tested the field shape:** Both are real, documented flags, but their exact output schema is not documented anywhere found this session. Parsing an assumed schema against an unverified real CLI is a rewrite-causing mistake this phase can avoid entirely by staying on plain-text + marker parsing, consistent with D-02.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Credential-bounded subprocess environment | A second/third ad hoc `env` dict per adapter | `build_worker_env(role, env_var_name=..., value=...)` (already exists) | Third and fourth application of the same allowlist-from-empty-dict discipline (TOOL-04, SEC-03) — no new design needed |
| NEEDS_INPUT pause signal | A new marker/regex per adapter | `claude_code.py`'s `NEEDS_INPUT_MARKER`/`_NEEDS_INPUT_RE`, reused verbatim (D-03) | One shared pause contract; the shared contract suite pins it once instead of three times |
| Native tool restriction mapping | Deriving Copilot's/Hermes's `--allow-tool` translation from first principles | `NATIVE_TOOL_CONTRACT` (`tools/native.py`) — already fully specified for both | Design work is already done; this phase is the first *real* consumer for these two runtimes, same as `claude_code.py` was for Claude Code |
| Skip-guarded live test scaffolding | A bespoke ad hoc `if shutil.which(...): pytest.skip(...)` per test function | One shared `skipif`-marker pattern per adapter module (Pattern 1 above) | Keeps the skip condition/message consistent across all three adapters, since none existed to mirror before this phase |

**Key insight:** Nothing about this phase requires new infrastructure — every mechanism (credential-bounded env, marker-based pause, native-tool translation) was already built generically enough in Phases 6–7 to be reused verbatim for two more adapters. The only genuinely new piece of infrastructure is the skip-guarded live-integration-test pattern (Scope Correction), which has zero precedent in the repo to copy from.

## Common Pitfalls

### Pitfall 1: Treating "documented flag exists" as "adapter should use it"
**What goes wrong:** Both CLIs document a `--resume`-shaped flag and a JSON/JSONL output flag. It is tempting to reach for the most feature-rich invocation.
**Why it happens:** The flags are real and well-documented individually; only their *combination* with `--oneshot`/non-interactive mode and their *output schema* are undocumented.
**How to avoid:** For Copilot, `--resume` is documented only as an interactive session picker in general docs and is entirely absent from the CLI's dedicated programmatic-reference page — treat this as confirmation of `native_resume=False`, not a gap to fill in. For Hermes, `--resume <session-id>` does take an explicit id, but whether `hermes chat --resume <id> -q "<answer>" --oneshot` completes headlessly without hanging was not confirmed in any fetched doc — implement the context-reconstruction (HITL-05) branch only for both adapters this phase, and leave native resume as a documented-but-not-adopted enhancement for the post-Phase-8 live spike.
**Warning signs:** A `WorkerCapabilities(native_resume=True)` declaration for either adapter with no corresponding contract-suite proof driving it down the native branch (the way `ClaudeCodeWorker`'s `--resume <session_id>` branch is proven in `test_claude_code_worker.py`).

### Pitfall 2: Gating Hermes on a nonexistent credential name
**What goes wrong:** Adding `Settings.hermes_api_key` and mapping it to an env var name that Hermes does not actually read (e.g., inventing `HERMES_API_KEY`, which is not among the 20+ documented provider-key variables).
**Why it happens:** Every other adapter (Claude Code, Copilot) has an adapter-specific credential field, so it is tempting to pattern-match a third one into existence.
**How to avoid:** Hermes is multi-provider by design; its own environment-variables reference lists `ANTHROPIC_API_KEY` as one of the recognized provider keys. Reuse `Settings.anthropic_api_key` and inject it as `ANTHROPIC_API_KEY` via `build_worker_env` — no new `Settings` field required (see Finding 1).
**Warning signs:** `MissingWorkerCredentialError` firing for a `hermes` role even though `Settings.anthropic_api_key` is configured and `ClaudeCodeWorker` itself works fine.

### Pitfall 3: Forgetting `HERMES_HOME` isolation
**What goes wrong:** Hermes defaults its config/state directory to `~/.hermes` (SQLite `state.db`, `.env`), which is the *operator's* home directory, not a role-scoped disposable directory — unlike the `XDG_*` isolation `build_worker_env` already provides for other adapters.
**Why it happens:** `build_worker_env` sets `XDG_CONFIG_HOME`/`XDG_CACHE_HOME`/etc., but Hermes does not documentedly follow the XDG spec — it follows its own `HERMES_HOME` override.
**How to avoid:** Set `HERMES_HOME` explicitly in the adapter's env construction (pointing at the same role-scoped `xdg_root` `build_worker_env` already computes), so a spawned Hermes process never writes into or reads from the real operator's `~/.hermes` directory — this matters doubly in the "clean container with no pre-existing CLI state" success criterion (SC1), where a stray `~/.hermes/.env` from a prior run must not leak a credential into an unrelated role's attempt.
**Warning signs:** Two different runs' Hermes-assigned roles behaving inconsistently depending on what a previous run happened to leave in `~/.hermes`.

### Pitfall 4: Assuming Copilot CLI needs no first-run bootstrap
**What goes wrong:** Assuming `COPILOT_GITHUB_TOKEN` alone is sufficient for a truly first-ever invocation in a container with zero prior Copilot CLI state (no accepted terms, no cached config).
**Why it happens:** The authentication docs are explicit that env-var auth bypasses the OAuth/keychain flow, but no fetched source explicitly confirms there is no separate first-run consent/telemetry-prompt step independent of authentication.
**How to avoid:** Treat this as unconfirmed rather than assumed-safe; the real spike (D-02, deferred) is the actual falsification opportunity. Until then, keep the adapter's error handling generic enough that an unexpected first-run prompt surfaces as a normal non-zero-exit `FAILED` result (which `_spawn_and_parse`'s existing exit-code handling already does) rather than crashing the adapter.
**Warning signs:** A `copilot` invocation that hangs past `worker_timeout_seconds` on its very first run in a fresh container but succeeds on every subsequent run in the same container.

## Code Examples

### Finding 1 — Hermes credential model (resolves Claude's Discretion item 2)

Hermes is multi-provider; there is no single mandatory NousResearch-branded credential. Its own environment-variables reference [CITED: hermes-agent.nousresearch.com/docs/reference/environment-variables] documents `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIREWORKS_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `NVIDIA_API_KEY`, `BEDROCK_*`, and 10+ more, each read directly from the process environment or from `~/.hermes/.env`. There is no `NOUS_API_KEY`-shaped credential — `NOUS_BASE_URL`/`NOUS_INFERENCE_BASE_URL`/`HERMES_PORTAL_BASE_URL` are documented as *endpoint overrides*, not authentication tokens, and the Nous Portal path (`hermes setup --portal`) is an interactive OAuth device flow, not an env-var credential [CITED: same page].

**Recommendation:** do not add a new `Settings` field for Hermes. Reuse `Settings.anthropic_api_key` (already present, already redaction-covered via `known_secret_values()`), passed to `build_worker_env(role, env_var_name="ANTHROPIC_API_KEY", value=settings.anthropic_api_key)` exactly as `ClaudeCodeWorker` already does for its own spawn. `HermesWorker`'s own missing-credential error can be a thin adapter-local class with the identical shape as `ClaudeCodeWorker.MissingWorkerCredentialError`, naming `ANTHROPIC_API_KEY` and `Settings.anthropic_api_key` in its message (not a new field name).

```python
# Source: synthesized pattern, following claude_code.py's own
# MissingWorkerCredentialError shape verbatim (workers/claude_code.py:121-136)
class MissingWorkerCredentialError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "ANTHROPIC_API_KEY is not configured -- set "
            "Settings.anthropic_api_key before running a role whose worker "
            "is 'hermes' (Hermes has no dedicated credential; it reuses the "
            "same Anthropic key Claude Code uses)"
        )
```

[ASSUMED]: whether the planner instead prefers a dedicated `Settings.hermes_api_key` (e.g. mapped to `OPENROUTER_API_KEY` for genuine cross-provider independence) is a legitimate discretionary alternative — see "Alternatives Considered" above — but is not required by any documentation constraint found this session.

### Finding 2 — Per-adapter `WorkerCapabilities` recommendation (resolves Claude's Discretion item 5)

| Capability axis | Copilot | Hermes | Evidence |
|---|---|---|---|
| `native_resume` | `False` | `False` | Copilot: `--resume` is documented only as an interactive picker in general docs [CITED: docs.github.com/copilot/how-tos/copilot-cli/use-copilot-cli/overview] and is absent from the dedicated programmatic-reference page [CITED: docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference]. Hermes: `--resume <session-id>` exists and takes an explicit id [CITED: github.com/NousResearch/hermes-agent/.../cli-commands.md], but headless completion of `--resume <id>` combined with `--oneshot`/`-q` was not confirmed in any fetched source — [ASSUMED] to be unsafe to adopt without the live spike; recommend `False` for MVP, matching CONTEXT.md's original conservative default. |
| `session_id` | `False` | `False` | Copilot: no field in `--output-format=json`'s (undocumented) schema confirmed to carry a session id [no observation — docs describe only that the format exists, not its fields]. Hermes: session ids are internally tracked (SQLite `state.db`, format `YYYYMMDD_HHMMSS_<hex>`) but no fetched source confirms one is printed to stdout during a `--oneshot` run for a caller to capture [no observation]. |
| `non_interactive` | `True` | `True` | Copilot: `-p "<prompt>" --no-ask-user` is the CLI's own documented non-interactive contract [CITED: docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically]. Hermes: `--oneshot` (`-q`) exits after one turn and is additionally *implied automatically* whenever stdin is not a TTY [CITED: hermes-agent.nousresearch.com/docs/reference/cli-commands] — no PTY is required for either CLI. |
| `structured_output` | `False` (recommended) | `False` (recommended) | Both CLIs document a JSON/JSONL mode (`--output-format=json`; `--format stream-json`) [CITED, same sources as above], but neither's field schema is documented, and neither is part of CLAUDE.md's already-locked invocation pattern this phase builds from (D-02). Declaring `True` while the adapter parses plain text would misrepresent what the adapter actually does — recommend `False` and revisit post-live-spike. |
| `emits_changed_files` | `False` | `False` | Same rationale as `ClaudeCodeWorker` — `git/diff.py::collect_diff` computes the authoritative diff from git after any worker returns; no adapter should invent its own changed-file list. |

### Finding 3 — Copilot CLI exact flag/env matrix

```
# Source: docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli
#         docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference
#         docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically
#         docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools

# Credential (env var precedence, highest first):
#   COPILOT_GITHUB_TOKEN > GH_TOKEN > GITHUB_TOKEN > OAuth keychain > gh CLI fallback
# Token requirements: fine-grained PAT (github_pat_*) owned by a PERSONAL account
# (not an org) with the "Copilot Requests" account-level permission, OR an OAuth
# token (gho_*), OR a GitHub App user-to-server token (ghu_*).
# Classic PATs (ghp_*) are rejected/ignored.
# Recommendation: build_worker_env(role, env_var_name="COPILOT_GITHUB_TOKEN",
#                                   value=settings.copilot_github_token)
# -- the highest-precedence, Copilot-specific name avoids any ambiguity with
# GH_TOKEN/GITHUB_TOKEN used elsewhere.

copilot \
  -p "<prompt>" \
  --no-ask-user \
  --allow-tool 'read' \
  --allow-tool 'write' \
  --allow-tool 'shell(pytest)' \
  --model <pin> \
  -s
  # -s: "suppress stats and decoration" -- optional, recommended for clean
  #     log capture (mirrors why ClaudeCodeWorker streams raw stdout to a
  #     file rather than parsing decorated output)

# NEVER pass: --allow-all-tools, --allow-all-paths, --share, --share-gist
# --deny-tool takes precedence over --allow-all-tools/--allow-tool -- useful
# as a defense-in-depth belt for a capability the role must never have,
# though NATIVE_TOOL_CONTRACT's existing "omit from allow-list" approach is
# sufficient on its own (deny-by-default was confirmed: a tool absent from
# --allow-tool is refused, not silently permitted, when --no-ask-user is set).
```

### Finding 4 — Hermes CLI exact flag/env matrix

```
# Source: hermes-agent.nousresearch.com/docs/reference/cli-commands
#         hermes-agent.nousresearch.com/docs/reference/environment-variables
#         github.com/NousResearch/hermes-agent/.../website/docs/reference/cli-commands.md

# Credential: reuse Settings.anthropic_api_key (see Finding 1) --
# ANTHROPIC_API_KEY is one of Hermes's own documented provider-key env vars.
# Recommendation: build_worker_env(role, env_var_name="ANTHROPIC_API_KEY",
#                                   value=settings.anthropic_api_key)

hermes chat -q "<prompt>" --oneshot -Q
  # -q / --query : seed the prompt
  # --oneshot    : answer and exit (also implied automatically whenever
  #                stdin is not a TTY -- pass it explicitly anyway for
  #                determinism regardless of stdin plumbing)
  # -Q / --quiet : "programmatic mode: suppress banner/spinner/tool
  #                previews" -- recommended for clean log capture

# Recommended additional isolation (not in CLAUDE.md's original pattern,
# added by this research -- Pitfall 3):
#   env["HERMES_HOME"] = <role-scoped xdg_root>  # keeps state.db/.env out
#                                                  # of the operator's real
#                                                  # ~/.hermes directory
#   --ignore-user-config  # "use built-in defaults... for isolated CI runs"
#                          # -- prevents a host machine's personal Hermes
#                          # config from bleeding into a run

# Exit codes (one-shot): 0 completed, 1 failed/partial/iteration-budget-hit,
# 130 interrupted, 2 usage error (bad flags), 75 temporary/rate-limited.
# NEVER pass: --tui (forces interactive mode)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Hermes single-query mode as the only non-interactive shape | `--oneshot` flag introduced as an explicit non-interactive mode distinct from "seed an interactive session" (docs describe it as "the pre-0.21 single-query behavior") | Hermes CLI ≥0.21 (exact version/date not confirmed in fetched sources) | Bare `-q` alone now seeds an *interactive* session on a real TTY; `--oneshot` is required for a guaranteed answer-and-exit, though it is automatically implied when stdin is not a TTY (which a subprocess spawn already satisfies) |

**Deprecated/outdated:** none identified specific to this phase's scope; both CLIs are actively documented as current as of this research date (2026-09-21).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `--resume <session-id>` combined with `--oneshot`/`-q` completes headlessly for Hermes without hanging on a TTY prompt | Finding 2, Pitfall 1 | If wrong in the *optimistic* direction (i.e. it actually works fine), the phase merely under-uses a capability — `native_resume=False` is the conservative default and costs nothing but a future refinement. If wrong in the *pessimistic* direction and someone adopts it anyway, a resume call could hang until `worker_timeout_seconds` |
| A2 | Reusing `Settings.anthropic_api_key` for Hermes (rather than a dedicated `hermes_api_key`) is the preferred design | Finding 1, Summary | If the planner disagrees, a dedicated field is a low-cost alternative already described in "Alternatives Considered" — reversible with no schema impact |
| A3 | Copilot CLI has no separate first-run consent/bootstrap step beyond authentication | Pitfall 4 | If wrong, the first live-spike invocation in a genuinely clean container could hang past `worker_timeout_seconds` rather than fail fast; the existing timeout-then-FAILED handling contains the blast radius but the run would still take the full timeout to fail |
| A4 | Neither CLI's JSON/JSONL structured-output mode field schema needs confirming this phase because it is not being adopted | Architecture Patterns, Don't Hand-Roll | If a future phase adopts `--output-format=json`/`--format stream-json` without first confirming the schema against a real invocation, the same "designed against an assumed shape" risk this phase is deliberately avoiding would resurface then |

## Open Questions

1. **Does `hermes chat --resume <id> -q "<answer>" --oneshot` actually complete non-interactively?**
   - What we know: each of `--resume <id>`, `-q`, and `--oneshot` is independently documented and Hermes's CLI design is generally compositional (flags combine freely elsewhere in the docs).
   - What's unclear: no fetched source shows this exact three-flag combination, and Hermes's own docs distinguish "seeds an interactive session" (bare `-q`) from "answer and exit" (`--oneshot`) as genuinely different code paths — it is not certain `--resume` doesn't reopen an interactive shell regardless of `--oneshot`.
   - Recommendation: implement `native_resume=False` (context-reconstruction only) for MVP; treat this as the first thing to falsify in the deferred live spike (D-02), since a positive result would let a later phase upgrade `HermesWorker.capabilities()` with no architecture change.

2. **What does Copilot's `--output-format=json` / Hermes's `--format stream-json` output actually contain field-by-field?**
   - What we know: both flags exist and are documented to emit JSON/JSONL; neither's schema (error field, cost, turns, session id, etc.) is documented in any fetched source.
   - What's unclear: whether either schema includes a capturable session/conversation id that would upgrade `session_id` to `True`.
   - Recommendation: leave both adapters on plain-text parsing this phase (Finding 2); revisit once the live spike can inspect real output.

3. **Does Copilot CLI require any first-run interactive consent/telemetry step independent of `COPILOT_GITHUB_TOKEN` authentication?**
   - What we know: env-var authentication is documented to bypass the OAuth/keychain login flow entirely.
   - What's unclear: whether a *separate* first-invocation prompt (e.g., terms acceptance) exists independent of authentication, which SC1's "clean container with no pre-existing CLI state" scenario would trigger.
   - Recommendation: no code change needed — the existing timeout-then-FAILED path already contains this risk; flag it as the first thing a human checks when the live spike runs in a genuinely fresh container.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `copilot` CLI binary | `CopilotWorker` live execution | ✗ (not installed in this sandbox) | — | Contract/unit tests run against a faked `copilot` executable on `PATH` (mirrors `fake_claude_cli.py`); the live integration suite (Pattern 1) `skipif`s cleanly |
| `hermes` CLI binary | `HermesWorker` live execution | ✗ (not installed in this sandbox) | — | Same — faked executable for contract/unit tests, `skipif`-guarded live suite |
| `claude` CLI binary | Retroactive `ClaudeCodeWorker` live suite (Scope Correction) | ✗ (not installed in this sandbox) | — | Same faked-executable pattern already exists (`fake_claude_cli.py`) for the contract suite; only the *new* skip-guarded live suite is missing |
| A Copilot-scoped GitHub credential (`COPILOT_GITHUB_TOKEN`) | `CopilotWorker`'s live suite | ✗ | — | Suite skips; `Settings.copilot_github_token is None` is the credential half of the skip condition |
| An Anthropic (or other provider) API key for Hermes | `HermesWorker`'s live suite | Present in this sandbox only as `Settings.anthropic_api_key` for `ClaudeCodeWorker`'s own use — no dedicated Hermes credential expected (Finding 1) | — | Suite skips identically to Copilot's when absent |

**Missing dependencies with no fallback:** none — every missing dependency above has a documented fallback (fake-CLI unit/contract testing, or a clean `skipif`).

**Missing dependencies with fallback:** `copilot`, `hermes`, and (retroactively) `claude` binaries; the Copilot credential; treated identically to how Phase 7 already treated the absent `claude` binary/credential for its own contract-suite testing.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` |
| Quick run command | `pytest -m "unit or contract" -q` |
| Full suite command | `pytest -q` (requires reachable PostgreSQL 17 for `db`-marked tests; `integration`-marked live-credential tests skip cleanly when binaries/credentials are absent, per this phase's new suites) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| WORK-05 | `CopilotWorker` executes non-interactively, returns normalized `WorkerResult` | unit + contract | `pytest tests/unit/test_copilot_worker.py -x` / `pytest tests/contract/test_coding_worker_contract.py -k Copilot -x` | ❌ Wave 0 |
| WORK-06 | `HermesWorker` executes non-interactively, returns normalized `WorkerResult` | unit + contract | `pytest tests/unit/test_hermes_worker.py -x` / `pytest tests/contract/test_coding_worker_contract.py -k Hermes -x` | ❌ Wave 0 |
| WORK-09 | Role reassignment across all three real runtimes needs no workflow-code change | integration (config-driven run) | `pytest tests/integration/test_role_reassignment_sc2.py -x` | ❌ Wave 0 |
| QUAL-03 | Each of `claude-code`/`copilot`/`hermes` has a skip-guarded live integration suite | integration | `pytest tests/integration/test_claude_code_live.py tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py -v` | ❌ Wave 0 (all three, per Scope Correction) |

### Sampling Rate
- **Per task commit:** `pytest -m "unit or contract" -q`
- **Per wave merge:** `pytest -q` (full suite; live-credential suites skip in this sandbox, run for real wherever the CLIs are later installed)
- **Phase gate:** Full suite green (with documented skips) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_copilot_worker.py` — covers WORK-05
- [ ] `tests/unit/test_hermes_worker.py` — covers WORK-06
- [ ] `tests/support/fake_copilot_cli.py` — mirrors `fake_claude_cli.py`
- [ ] `tests/support/fake_hermes_cli.py` — mirrors `fake_claude_cli.py`
- [ ] `tests/integration/test_claude_code_live.py` — closes the QUAL-03 gap for `claude-code` (Scope Correction)
- [ ] `tests/integration/test_copilot_live.py` — covers QUAL-03 for `copilot`
- [ ] `tests/integration/test_hermes_live.py` — covers QUAL-03 for `hermes`
- [ ] `tests/integration/test_role_reassignment_sc2.py` (or equivalent) — covers WORK-09/SC2's literal Architect→Copilot/Developer→Claude-Code/QA→Hermes scenario

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | `COPILOT_GITHUB_TOKEN` fine-grained PAT with the minimum `Copilot Requests` permission; `ANTHROPIC_API_KEY` reused from existing Settings — neither credential is ever logged (SecretStr + `known_secret_values()`) |
| V3 Session Management | no | This phase introduces no user-facing session; `worker_session_id` continues to be an opaque per-adapter value the orchestrator never interprets (HITL-04) |
| V4 Access Control | yes | `NATIVE_TOOL_CONTRACT`'s per-capability `--allow-tool`/deny-by-default translation is this phase's access-control surface — confirmed (Finding: Copilot refuses ungranted tools when `--no-ask-user` is set, not silently permits them) |
| V5 Input Validation | yes | Prompt text assembly reuses `_context_prompt_sections`-equivalent logic; no new user-controlled input path is introduced beyond what Phase 4/7 already validate |
| V6 Cryptography | no | No new cryptographic primitive introduced; `SecretStr` storage is unchanged from existing Settings pattern |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Credential leak via `--share`/`--share-gist` externalizing a Copilot transcript | Information Disclosure | Never pass either flag (Pitfall 1 in Architecture Patterns); rely exclusively on the existing `_scrub_log_in_place`-equivalent redaction pass over locally-captured log files |
| A role's own subprocess reading the operator's real `~/.hermes` credentials/state | Information Disclosure / Elevation of Privilege | Set `HERMES_HOME` to the role-scoped `xdg_root` `build_worker_env` already computes (Pitfall 3) |
| Classic GitHub PAT (`ghp_*`) mistakenly configured for Copilot | Authentication bypass attempt (rejected, not a real threat per docs, but a misconfiguration trap) | Document the requirement (fine-grained PAT, `Copilot Requests` permission, personal-account-owned) directly in the `Settings.copilot_github_token` field docstring and the missing-credential error message |
| Tool use beyond a role's granted capability set via CLI-native execution | Elevation of Privilege | `NATIVE_TOOL_CONTRACT`'s translation, confirmed deny-by-default for Copilot; Hermes has no native per-tool restriction flag at all — per the contract's own honest note, **the adapter must refuse to spawn Hermes for any role that does not hold every capability Hermes cannot natively scope down** (already specified in `tools/native.py`, not new to this phase) |

## Sources

### Primary (HIGH confidence)
None — no source this session was both tool-confirmed and independently cross-verified against a second authoritative source; all findings are single-source `CITED` (see below). In-repo code reads (`claude_code.py`, `native.py`, `settings.py`, `registry.py`, `env.py`, `fake_claude_cli.py`, `test_coding_worker_contract.py`, `test_native_tool_contract.py`, `pyproject.toml`, `ROADMAP.md`) were read directly this session and are the load-bearing basis for the Scope Correction and Architectural Responsibility Map.

### Secondary (MEDIUM confidence — CITED, official documentation fetched this session)
- [Authenticating GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli) — env var precedence, token type/permission requirements
- [GitHub Copilot CLI programmatic reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference) — `-p`, `--no-ask-user`, `--allow-tool`, `--allow-all-tools`, `--deny-tool`, `--model`, `--output-format`, `--share`/`--share-gist`, absence of `--resume`/session-id in this specific page
- [Running GitHub Copilot CLI programmatically](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically) — recommended CI invocation pattern
- [Allowing and denying tool use](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools) — deny-by-default confirmation, `--deny-tool` precedence over `--allow-all-tools`
- [Using GitHub Copilot CLI overview](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview) — `--resume` as interactive-only session picker
- [Hermes Agent CLI Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) and [github.com/NousResearch/hermes-agent .../reference/cli-commands.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md) — `-q`, `--oneshot`, `-Q`, `--format stream-json`, `--resume`/`-r`, `--continue`/`-c`, exit codes
- [Hermes Agent CLI Interface user guide](https://hermes-agent.nousresearch.com/docs/user-guide/cli) — session storage, installation
- [Hermes Agent Environment Variables Reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) and [github.com/NousResearch/hermes-agent .../reference/environment-variables.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/environment-variables.md) — full provider-key env var list, `HERMES_HOME`, absence of a single mandatory credential
- [Hermes Agent Sessions guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/sessions.md) — session id format, resume syntax

### Tertiary (LOW confidence — general web search, cross-referenced against the primary docs above where possible)
- devleader.ca headless-Copilot-CLI blog post — corroborates the `-p ... -s --allow-tool=... --no-ask-user` invocation pattern already found in official docs; not authoritative on its own
- Various Medium/DEV.to/cheat-sheet pages surfaced by WebSearch — used only to locate the correct official doc URLs, never cited as a standalone claim source

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, verified by reading `pyproject.toml` and the existing adapter code directly
- Architecture: MEDIUM — the spawn/parse pipeline is a direct, in-repo-verified clone of `ClaudeCodeWorker`; the two CLIs' own flag/env details are CITED from official docs but never run
- `WorkerCapabilities` values: MEDIUM for `non_interactive`/`native_resume` (directly evidenced); LOW for `session_id`/`structured_output` (absence-of-evidence, not a positive falsification — see Assumptions Log A1/A4)
- Pitfalls: MEDIUM — each pitfall is grounded in a specific documented flag or omission, not speculation
- Scope Correction (QUAL-03 gap): HIGH — directly confirmed by reading `ROADMAP.md`'s Phase 7 requirement list and grepping the test tree for `skipif` (zero matches)

**Research date:** 2026-09-21
**Valid until:** 30 days (2026-10-21) for the architectural/scope findings; the CLI flag/env details should be re-verified against the actual installed binaries the moment D-02's deferred live spike happens, since both CLIs are actively evolving (Hermes explicitly notes a `--oneshot` behavior change "since 0.21").
