# Phase 7: Claude Code — the First Real Worker - Research

**Researched:** 2026-09-20
**Domain:** Non-interactive CLI-subprocess agent adapter (Claude Code headless mode), process-group timeout + streamed logging, native tool restriction translation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Clarifying-question signal — real NEEDS_INPUT):** Because Claude
Code's headless `-p` invocation cannot interactively pause mid-run,
`ClaudeCodeWorker` derives `NEEDS_INPUT` from a convention marker in the
CLI's own final result text — the role's instruction prompt tells Claude to
end its turn with a fixed marker line (e.g. a line starting `NEEDS_INPUT:`)
followed by the question, instead of guessing when it needs a human
decision. The adapter parses the CLI's `result` text for that marker:
present → `NEEDS_INPUT` with the question extracted from it; absent →
`COMPLETED`/`FAILED` as usual. This is adapter-only parsing with no new CLI
feature dependency, and is what makes SC2's pause/resume path reachable
through the real adapter, not only via `FakeWorker` configured with a
script. — **Reversibility:** reversible — the marker format lives entirely
inside `ClaudeCodeWorker`'s parsing logic; changing it later touches one
adapter module and the role instruction text, no persisted schema.

**D-02 (Credential handling):** `Settings` gains a new optional credential
field for the Claude Code CLI (e.g. `anthropic_api_key: SecretStr | None`,
mirroring `github_token`'s existing optional shape) — not required at
process startup. Its absence only surfaces when a run actually tries to
invoke a `claude-code` role: `ClaudeCodeWorker.execute()`/`resume()` raise a
clear, typed error naming the missing env var before spawning anything.
This keeps every environment that only ever runs `fake`-worker pipelines
(including CI's existing test suite) working with no new required
configuration, consistent with the existing `github_token: SecretStr | None
= None` precedent. The value flows to the subprocess exclusively through
`build_worker_env(role, env_var_name=..., value=...)` (Phase 6 D-09) —
never through `os.environ.copy()` or any other channel. — **Reversibility:**
reversible — a later phase can tighten this to eager validation without
touching persisted state; it's a Settings-field/validation-timing choice
only.

**D-03 (Timeout policy):** A single `Settings.worker_timeout_seconds` field
(env-overridable int, generous default — planning discretion on the exact
number, but explicitly generous rather than tight, since engineering roles
like DEVELOPMENT can run long) governs every worker subprocess call this
phase. This mirrors the existing `lease_ttl_seconds`/`lease_heartbeat_seconds`
precedent (Phase 2) — one plain `Settings` knob, not a new per-role config
key or a hardcoded constant. Per-role timeout overrides in
`.dark-factory.yaml` are explicitly deferred, not adopted this phase. —
**Reversibility:** reversible — a per-role override can be layered on top
of this single knob later (falling back to it) without breaking existing
callers.

**D-04 (Log streaming target):** A worker subprocess's streamed output is
written under the run's existing artifact tree, in a new `logs/<role>/`
subdirectory alongside `artifacts/<role>/` under
`.dark-factory/runs/<run_id>/` — raw stdout/stderr text, one file per
attempt (e.g. `attempt-<N>.stdout.log` / `attempt-<N>.stderr.log`). This
reuses the existing `run_root()` path helper and the same crash/resume
durability model artifacts already have, with no new persistence concept,
no new schema, and no dependency on structlog's configured sink for what is
fundamentally a per-run worker transcript. — **Reversibility:** reversible
— a later phase can add a structured-JSON-lines format or a live-tail
feature on top of these files without changing where they live.

### Claude's Discretion

- Exact `NEEDS_INPUT:` marker text/format and how multi-line questions are
  extracted from the CLI result text — left to planning, as long as it's
  unambiguous against ordinary prose Claude might otherwise produce.
- Exact `Settings` field name for the Claude Code credential (e.g.
  `anthropic_api_key` vs. another name) and the exact typed error
  class/message raised on missing credential at first use.
- Exact default value of `Settings.worker_timeout_seconds` — generous is
  the stated intent (engineering roles run long); planning picks a concrete
  number (e.g. minutes, not seconds-scale). This research recommends 1800s
  (30 min) as a starting point — see Open Questions.
- Exact log file naming/rotation scheme within `logs/<role>/` beyond "one
  file per attempt, raw stdout/stderr" — e.g. whether stdout and stderr are
  separate files or interleaved.
- Whether `resume()` shares the same timeout value as `execute()` or could
  differ — no signal from the user that these should diverge; default to
  sharing one `Settings.worker_timeout_seconds` value unless research
  surfaces a concrete reason not to (this research found none — see Open
  Questions #2).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. Per-role timeout overrides in
`.dark-factory.yaml` and a structured (JSON-lines) log format were both
explicitly named as possible future refinements during discussion, not
requested now — captured as `Claude's Discretion` / decision rationale
above, not as a backlog list. `CopilotWorker`/`HermesWorker` and
cross-worker independence proofs remain Phase 8's scope per ROADMAP.md,
unchanged by this discussion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORK-04 | `ClaudeCodeWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | Architecture Patterns (system diagram, Pattern 1), Code Examples — full spawn/timeout/parse pipeline documented against the confirmed current CLI flag surface |
| WORK-07 | `WorkerCapabilities` represents runtime differences explicitly (native resume, session id, non-interactive, structured output) | Pattern 4 — `native_resume=True`/`session_id=True` justified by the confirmed `--resume <session_id>` flag semantics |
| HITL-04 | When a worker adapter supports native sessions, resume uses the opaque `worker_session_id`; the orchestrator does not interpret it | Pattern 4, Architectural Responsibility Map — orchestrator call site at `orchestrator/runner.py:826-827` confirmed unchanged regardless of adapter branch |
| HITL-05 | When native resume is unavailable, the adapter resumes by reconstructing context; the orchestrator sees the same `worker.resume(...)` call either way | Pattern 4 — same method signature covers both branches; `FakeWorker`'s existing `native_resume=False` path in the contract suite already proves the orchestrator-side half of this |
| QUAL-02 | A shared `CodingWorker` contract-test suite runs against every adapter (including `FakeWorker`) so `FakeWorker` cannot diverge from real adapter behavior | Environment Availability § "Faking the `claude` binary," Validation Architecture — concrete technique for appending `ClaudeCodeWorker` to `WORKER_FACTORIES` with no live credential needed |
| QUAL-04 | A CI check fails the build if worker-name branching leaks outside the adapters | Validation Architecture § Wave 0 Gaps / Open Gap — existing guard test confirmed, but **no `.github/workflows/` directory exists in this repo yet**; flagged as a concrete gap for the plan to close |

</phase_requirements>

## Summary

`ClaudeCodeWorker` is the first `CodingWorker` adapter that actually spawns an
external process. The Claude Code CLI's headless contract is well-documented
and stable enough to build against directly: `claude -p "<prompt>"
--output-format json` prints exactly one JSON object on stdout whose fields
are `subtype`, `duration_ms`, `duration_api_ms`, `is_error`, `num_turns`,
`session_id`, `total_cost_usd`, `usage`, `result` (the model's final text —
this is where D-01's `NEEDS_INPUT:` marker convention is parsed from),
`structured_output`, and `permission_denials` [CITED:
code.claude.com/docs/en/agent-sdk/python]. `--resume <session-id>` continues
that exact session non-interactively, which is what makes `native_resume=True`
true for this adapter — the orchestrator's `worker.resume(context, previous,
answer)` call becomes `claude -p "<answer-as-next-prompt>" --resume
<worker_session_id> --output-format json` inside the adapter, with no
orchestrator-visible difference from the `execute()` call shape (HITL-04/
HITL-05).

Two research findings materially change how this phase should be planned
versus what the existing `.claude/CLAUDE.md` summary and `tools/native.py`
docstrings imply, and both are called out prominently below because they are
easy to get wrong:

1. **There is no `--permission-mode` value that "restricts reads/writes to the
   worktree."** `tools/native.py`'s own prose says exactly this, but it does
   not correspond to any real flag [CITED:
   code.claude.com/docs/en/permissions#working-directories]. Worktree
   confinement is a property of the subprocess's **working directory**
   (`cwd=`), not a permission mode: file reads are un-prompted *only within
   the working directory and any `--add-dir` directories*, and
   `--permission-mode` instead selects an *approval policy*
   (`default`/`acceptEdits`/`plan`/`auto`/`dontAsk`/`bypassPermissions`). The
   adapter gets worktree scoping for free by spawning `claude` with
   `cwd=work_dir` (the same worktree `ensure_worktree` already returns) — no
   flag translates NATIVE_TOOL_CONTRACT's "restrict to the worktree" clause;
   the *docstring* wording should not be read as naming a real flag.
2. **D-04's "reuse the artifact-tree durability model" has a live SEC-01
   consequence.** `git.diff.commit_run_artifacts` force-adds and commits the
   **entire** `.dark-factory/runs/<run_id>/` tree — not just `artifacts/` —
   onto the run's working branch, which becomes the PR branch (GIT-01/
   GIT-03) [VERIFIED: src/dark_factory/git/diff.py:129 — `relative_path =
   f".dark-factory/runs/{run_id}"`]. D-04's new `logs/<role>/` files sit
   inside that same tree and are therefore committed too, but D-04 explicitly
   opts them out of the existing `redact()`/structlog scrubbing path ("no
   dependency on structlog's configured sink"). Left unaddressed, that is a
   route for un-redacted subprocess output — anything the `claude` process
   echoes — to land in a public PR diff, which directly violates SEC-01
   ("...never appear in ... logs"). This phase must apply the existing
   `dark_factory.events.redaction.redact()` to the captured log text (using
   `Settings.known_secret_values()`) **before** `execute()`/`resume()`
   returns, so the log files on disk are already scrubbed by the time
   `commit_run_artifacts` runs later in the same call.

**Primary recommendation:** Spawn `claude` with stdout/stderr redirected
directly to open file handles under `logs/<role>/` (not `PIPE` +
`communicate()`), call `Popen.wait(timeout=Settings.worker_timeout_seconds)`,
`os.killpg(..., SIGKILL)` on `TimeoutExpired`, then read the file back,
`redact()` it in place, and — on a clean exit — parse the last line as the
`--output-format json` result object. Never let an exception escape
`execute()`/`resume()`; every failure mode (timeout, non-zero exit, malformed
JSON) must become a `WorkerResult(status=FAILED, ...)`, because
`orchestrator/runner.py` calls `worker.execute(context)` / `worker.resume(...)`
with no surrounding `try/except` — an adapter that raises leaves the
`role_executions` row stuck at `RUNNING` with no terminal event, which SC5
requires never to happen.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Spawn the `claude` CLI non-interactively, build its argv/env | Worker adapter (`workers/claude_code.py`) | — | WORK-01/WORK-03: only the adapter knows the runtime's invocation shape |
| Parse `--output-format json` into `WorkerResult` | Worker adapter | — | Normalization is the adapter's whole job (WORK-08); orchestrator only reads `WorkerResult` fields |
| Translate `RoleContext.tools`/`permissions` into `--allowedTools` | Worker adapter, reading `tools/native.py`'s `NATIVE_TOOL_CONTRACT` (design contract) | — | D-02 (Phase 6): the mechanism differs per worker but the grant source (`tools:` config) is the same; `ToolRegistry` cannot intercept a real CLI's own native tools |
| Enforce worktree confinement | OS process (`cwd=` at spawn) | Worker adapter (sets `cwd`) | Confirmed no such thing as a Claude Code "worktree permission mode" — it is a `cwd` property, not a CLI flag |
| Kill a hung subprocess by timeout | Worker adapter (`Popen.wait(timeout=...)` + `os.killpg`) | — | Mirrors `tools/env.py::shell_execute`'s existing process-group-kill pattern, adapted for streamed (not piped) output |
| Persist the terminal role outcome (FAILED/COMPLETED/NEEDS_INPUT) | Orchestrator (`orchestrator/runner.py::apply_transition`) | — | ORCH-05: only the orchestrator writes lifecycle state; the adapter only returns a `WorkerResult` |
| Scrub secret values out of the raw subprocess transcript before it is committed | Worker adapter (calls `dark_factory.events.redaction.redact()`) | — | The commit step (`git.diff.commit_run_artifacts`) runs *after* the adapter returns and force-adds the whole run tree including `logs/`; nothing downstream re-scrubs it |
| Credential-bounded subprocess environment | `tools/env.py::build_worker_env()` (existing, reused) | Worker adapter (supplies `env_var_name="ANTHROPIC_API_KEY"`) | D-09/TOOL-04 precedent already generalizes to this call; no new allowlist needed |

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude` CLI (`@anthropic-ai/claude-code`) | 2.1.278 (npm, published 2026-09-19) [VERIFIED: npm registry] | The subprocess `ClaudeCodeWorker` spawns | It is the runtime this phase adapts; version is a moving target (weekly releases per the changelog notes embedded in the docs above) — pin nothing in Dark Factory's own dependency tree since it is an external CLI, not a Python package, but document the version this research was validated against |
| `subprocess` (stdlib) | Python 3.12 | Spawn, stream-to-file, timeout, process-group kill | Already the project's standing pattern (`tools/env.py`, `git/client.py`); no new dependency |
| `dark_factory.events.redaction.redact()` | existing (Phase 1) | Scrub the captured log transcript before it is committed | Already the SEC-01/SEC-02 mechanism; reuse, do not reinvent |
| `dark_factory.tools.env.build_worker_env()` | existing (Phase 6) | Credential-bounded subprocess environment for the `claude` process itself | D-02 explicitly routes the new credential through this function |
| `dark_factory.tools.native.NATIVE_TOOL_CONTRACT` | existing (Phase 6) | Per-capability `--allowedTools` translation table | Already written for exactly this adapter to consume (design contract, currently inert) |

No new third-party Python package is needed for this phase — everything is
stdlib `subprocess`/`os`/`signal` plus existing project modules. The
**Claude Code CLI itself** is an external system dependency (installed on
`PATH`, authenticated via `ANTHROPIC_API_KEY`), not a Python dependency, and
is out of scope for `pyproject.toml`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct-file-redirect (`stdout=open(path, "wb")`) + `Popen.wait(timeout=...)` | Thread(s) reading `Popen.stdout`/`stderr` (`PIPE`) and writing to disk as they read | The thread approach is strictly more code and reintroduces the exact PIPE-buffer-deadlock risk `communicate()` exists to avoid; the file-redirect approach has the OS write directly to the fd with no Python-side buffering, confirmed correct by the Python docs [CITED: docs.python.org/3/library/subprocess.html] |
| Prose `NEEDS_INPUT:` marker inside the model's final `result` text (D-01, locked) | `--output-format json --json-schema '{...}'` with an explicit `needs_input`/`question` field in the schema | More robust (no prose-parsing ambiguity) but D-01 is already locked to the marker convention specifically because it needs "no new CLI feature dependency"; note this alternative exists for a future hardening pass, do not implement it this phase |
| `--allowedTools` bare tool names (`Write,Edit`) for `repo.write` | Path-scoped rule syntax `Edit(<relative-glob>/**)` for `artifacts.write` specifically | Bare tool names are enough for `repo.write` (whole-worktree grant); `artifacts.write` wants scoping to `artifacts/<role>/` specifically, which requires the gitignore-style specifier syntax (`Edit(.dark-factory/runs/<run_id>/artifacts/**)`), not a second tool name — see Code Examples below |

**Installation:** none — no new Python dependency. The `claude` CLI is
expected on `PATH` in whatever environment runs `claude-code`-worker roles;
its absence should surface as the D-02 typed credential/binary error at first
use, not as an import-time failure.

## Package Legitimacy Audit

No new external packages are installed this phase — `subprocess`, `os`,
`signal`, `json` are stdlib; `dark_factory.events.redaction`,
`dark_factory.tools.env`, `dark_factory.tools.native`,
`dark_factory.config.settings` are already-shipped first-party modules. The
Package Legitimacy Gate does not apply.

**Packages removed due to [SLOP] verdict:** none — no packages evaluated.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
orchestrator/runner.py::_run_current_role
        │
        │  worker = registry.get("claude-code")      (WorkerRegistry, unchanged)
        │  context = build_role_context(...)          (RoleContext, unchanged)
        │
        ├─ latest.status == RESUMING? ──yes──► worker.resume(context, previous, answer)
        │                                              │
        └─ no ─────────────────────────────────────► worker.execute(context)
                                                        │
                                    ┌───────────────────▼────────────────────┐
                                    │        ClaudeCodeWorker (new)          │
                                    │                                        │
                                    │ 1. get_settings(); fail fast if no     │
                                    │    ANTHROPIC_API_KEY (D-02)            │
                                    │ 2. build prompt text from RoleContext  │
                                    │    (instructions+task+inputs+outputs)  │
                                    │ 3. translate context.tools via         │
                                    │    NATIVE_TOOL_CONTRACT → --allowedTools│
                                    │ 4. build_worker_env(role,              │
                                    │    env_var_name="ANTHROPIC_API_KEY",   │
                                    │    value=settings.anthropic_api_key)   │
                                    │ 5. open logs/<role>/attempt-N.std{out, │
                                    │    err}.log; Popen(argv, cwd=work_dir, │
                                    │    env=env, stdout=out_fh,             │
                                    │    stderr=err_fh, start_new_session=   │
                                    │    True)                               │
                                    │ 6. proc.wait(timeout=                  │
                                    │    settings.worker_timeout_seconds)    │
                                    │    → TimeoutExpired: killpg(SIGKILL)   │
                                    │ 7. read log file back; redact() it in  │
                                    │    place (SEC-01 — see Summary)        │
                                    │ 8. parse last JSON line (clean exit)   │
                                    │    or build FAILED result (timeout /   │
                                    │    non-zero exit / bad JSON)           │
                                    │ 9. scan result.result text for the     │
                                    │    NEEDS_INPUT: marker (D-01)          │
                                    │ 10. return WorkerResult — NEVER raise  │
                                    └───────────────────┬────────────────────┘
                                                        │  WorkerResult
                                                        ▼
                                    signal_from_result(result)  (unchanged,
                                    orchestrator reads only .status)
                                                        │
                        ┌───────────────────────────────┴───────────────────┐
                        ▼                                                   ▼
        COMPLETED → artifact validation → git commit/push          FAILED → ROLE_FAILED/RUN_FAILED
        → enforce_write_scope → transition()                       events, no artifacts row
                        │  commit_run_artifacts() force-adds the ENTIRE
                        │  .dark-factory/runs/<run_id>/ tree — including
                        │  logs/<role>/ — onto the working/PR branch. Step 7
                        │  above MUST have already redacted the log content
                        │  by this point.
```

### Recommended Project Structure
```
src/dark_factory/workers/
├── base.py             # CodingWorker ABC — unchanged
├── fake.py             # FakeWorker — unchanged
├── registry.py         # default_registry — "claude-code" factory swapped in
└── claude_code.py       # NEW — ClaudeCodeWorker, all subprocess/prompt/parsing logic
```
No new top-level package is needed; `claude_code.py` under the already-exempt
`workers/` directory satisfies `test_no_worker_name_leak.py`'s
`_EXEMPT_TOP_LEVEL` without any guard change.

### Pattern 1: Stream-to-file subprocess with timeout + process-group kill

**What:** Redirect the child's stdout/stderr directly to open file objects
instead of `PIPE`, then use `Popen.wait(timeout=...)` instead of
`communicate(timeout=...)`.

**When to use:** Any worker-adjacent subprocess whose output must be
durably captured incrementally (D-04) rather than fully buffered in the
parent's memory — the distinguishing requirement from
`tools/env.py::shell_execute`, which buffers via `PIPE` + `communicate()` and
is intentionally NOT reused verbatim here.

**Example:**
```python
# Source: docs.python.org/3/library/subprocess.html (Popen accepts "an
# existing file object with a valid file descriptor" for stdout/stderr —
# the child writes directly to that fd, bypassing Python buffering) +
# tools/env.py's existing start_new_session=True / os.killpg precedent.
import os
import signal
import subprocess
from pathlib import Path

def run_streamed(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
) -> tuple[int | None, bool]:
    """Returns (exit_code, timed_out). exit_code is None iff timed_out."""
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as out_fh, stderr_path.open("wb") as err_fh:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out_fh,
            stderr=err_fh,
            start_new_session=True,  # heads its own process group
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            with __import__("contextlib").suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()  # reap; no PIPE to drain, so this cannot deadlock
            return None, True
    return proc.returncode, False
```

### Pattern 2: Redact the captured transcript before it can be committed

**What:** After the subprocess exits (or is killed), read the log file
content back and rewrite it through the existing `redact()` pipeline before
`execute()`/`resume()` returns.

**When to use:** Always, for every `ClaudeCodeWorker` call — this closes the
SEC-01 gap identified in the Summary.

**Example:**
```python
# Source: src/dark_factory/events/redaction.py (existing, Phase 1) +
# src/dark_factory/config/settings.py::Settings.known_secret_values()
from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact

def scrub_log_in_place(path: Path) -> None:
    settings = get_settings()
    raw = path.read_text("utf-8", errors="replace")
    scrubbed = redact(raw, known_secrets=settings.known_secret_values())
    path.write_text(scrubbed, "utf-8")
```
Call this for **both** the stdout and stderr log files, for both the
success path and the timeout/failure path — a killed process's partial
output is exactly the case SC5 says must be "persisted with the captured
output," and it is exactly the case most likely to contain a raw stack
trace or debug dump.

### Pattern 3: Translating a role's `tools:` grants to `--allowedTools`

**What:** Fold each held capability's `NativeToolGrant.claude_code`
fragment into one `--allowedTools` argument; anything not held is simply
omitted (deny-by-omission — the CLI itself refuses an un-listed tool).

**Example:**
```python
# Source: src/dark_factory/tools/native.py (NATIVE_TOOL_CONTRACT, Phase 6) +
# code.claude.com/docs/en/permissions#permission-rule-syntax (Edit(<glob>)
# path-scoped rule syntax, confirmed current)
_TOOL_NAMES = {
    "repo.read": ["Read", "Glob"],
    "repo.search": ["Grep", "Glob"],
    "repo.write": ["Write", "Edit"],
    "repo.write_tests": ["Write", "Edit"],
    "shell.execute": ["Bash"],
    "artifacts.read": ["Read"],
    # artifacts.write is intentionally scoped narrower than repo.write —
    # see the path-scoped Edit(...) rule below, not a bare tool name.
}

def allowed_tools_for(granted_capabilities: set[str], artifacts_glob: str) -> list[str]:
    names: set[str] = set()
    for capability in granted_capabilities:
        names.update(_TOOL_NAMES.get(capability, []))
    if "artifacts.write" in granted_capabilities:
        names.add(f"Edit({artifacts_glob}/**)")  # path-scoped, not bare "Write"/"Edit"
    return sorted(names)

# claude -p "<prompt>" --allowedTools "Bash,Edit,Glob,Grep,Read" --output-format json
```
`--permission-mode` is a separate, orthogonal flag selecting an *approval
policy* (`default`/`acceptEdits`/`plan`/`auto`/`dontAsk`/`bypassPermissions`)
— for a fully non-interactive role attempt, pair `--allowedTools` with
`--permission-mode dontAsk` (auto-denies anything the allow-list didn't
cover, rather than hanging on a prompt with nobody to answer it) or
`--dangerously-skip-permissions` only inside the already-isolated worktree,
consistent with `.claude/CLAUDE.md`'s existing guidance.

### Pattern 4: Resume via native session id vs. context reconstruction

**What:** `WorkerCapabilities.native_resume=True` for `ClaudeCodeWorker`
because `--resume <session_id>` is a real, documented flag [CITED:
code.claude.com/docs/en/headless#continue-conversations]. `resume()`
therefore builds the same argv-construction path as `execute()`, adding
`--resume <previous.worker_session_id>` and using the human's `answer` text
as the new prompt, instead of rebuilding a from-scratch prompt.

**Example:**
```python
def resume(self, context, previous, answer):
    argv = self._base_argv(context)  # same --allowedTools/--permission-mode
    argv += ["--resume", previous.worker_session_id, "-p", answer or ""]
    ...  # identical spawn/timeout/redact/parse pipeline as execute()
```
This is what makes HITL-04/HITL-05 hold *inside the adapter*: the
orchestrator's call site (`orchestrator/runner.py:826-827`) is unchanged —
`worker.resume(context, previous, state.pending_answer)` — regardless of
which branch the adapter takes internally. A future `native_resume=False`
worker (Copilot/Hermes, Phase 8) takes the *other* branch of this same
method — rebuild a prompt from `context` plus `previous.summary`/`answer` —
behind the identical method signature.

### Anti-Patterns to Avoid
- **Letting a timeout/subprocess exception propagate out of
  `execute()`/`resume()`:** `orchestrator/runner.py` has no `try/except`
  around the worker call (confirmed by reading the call site) — an
  uncaught exception here crashes the whole `advance()` step and leaves the
  `role_executions` row at `RUNNING` with no `ROLE_FAILED` event, directly
  contradicting SC5's "the role failure is persisted."
- **Reusing `tools/env.py::shell_execute()` unmodified for the `claude`
  spawn:** it buffers stdout/stderr in memory via `PIPE` + `communicate()`,
  which is exactly what D-04 says not to do; its credential-boundary and
  timeout/kill *shape* should be mirrored, not its I/O mechanism.
- **Treating `WorkerResult.changed_files` as an authoritative diff:** the
  post-role `collect_diff` action (`git/diff.py`) already computes the real
  diff from git after the worker call returns; `ClaudeCodeWorker` does not
  need to (and should not try to) compute its own changed-file list — leave
  it empty and declare `emits_changed_files=False`, matching the default.
- **Assuming `--permission-mode` can scope file access to a directory:** it
  cannot (see Summary finding 1) — do not implement a `--permission-mode`
  value search for "worktree restriction"; there isn't one.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Credential-bounded subprocess environment | A fourth environment allowlist | `dark_factory.tools.env.build_worker_env()` | Already the D-09/TOOL-04 mechanism; a third/fourth allowlist is explicitly flagged in the codebase as a red flag |
| Secret scrubbing of the captured transcript | A bespoke regex pass | `dark_factory.events.redaction.redact()` | Already covers known-value substitution *and* the D-15 pattern table (bearer tokens, `gh[porsu]_` prefixes, postgres URLs) — a bespoke pass would only catch known values |
| Process-group timeout kill | A signal-handler/alarm-based timeout | `Popen.wait(timeout=...)` + `os.killpg(..., SIGKILL)` on `TimeoutExpired` | Exactly the existing `shell_execute()` pattern, already proven against real subprocesses in this codebase |

**Key insight:** every mechanism this phase needs except the direct-file-
stdout redirect and the `--allowedTools` translation table already exists in
the codebase in a form built for an adjacent purpose (tool-call subprocess
timeout, worker credential boundary, secret redaction). The net-new adapter
code is prompt construction, argv assembly, and JSON-result parsing — not
subprocess plumbing.

## Common Pitfalls

### Pitfall 1: Un-redacted subprocess transcripts committed to the PR branch
**What goes wrong:** `logs/<role>/attempt-N.std{out,err}.log` files are
written with the raw, unscrubbed `claude` process output, and
`commit_run_artifacts` later force-adds and commits the whole run tree
(confirmed: `relative_path = f".dark-factory/runs/{run_id}"`, not scoped to
`artifacts/`) onto the branch that becomes the PR.
**Why it happens:** D-04 deliberately keeps this path independent of
structlog's redaction-equipped sink, and it is easy to read that as "no
redaction needed here" rather than "a different redaction call site is
needed here."
**How to avoid:** Apply `redact()` (Pattern 2 above) to both log files
before `execute()`/`resume()` returns, every time, on every exit path
(success, non-zero exit, timeout-kill).
**Warning signs:** A test that seeds a fake credential into the mocked
`claude` script's stdout and asserts the committed `logs/` file content
contains `[redacted:...]` rather than the raw value — if this phase ships
with no such test, the gap is unproven, not closed.

### Pitfall 2: An adapter exception aborts the whole `advance()` call
**What goes wrong:** Any unhandled exception inside `execute()`/`resume()`
(a `FileNotFoundError` because `claude` isn't on `PATH`, a `PermissionError`
opening the log file, a `json.JSONDecodeError` parsing a malformed result)
propagates straight out of `orchestrator/runner.py`'s call site, which has
no surrounding `try/except`.
**Why it happens:** It is tempting to let "unexpected" errors raise and
assume some outer layer catches them — none does, by design (ORCH-05: only
the orchestrator writes lifecycle state, and it does so from a
`WorkerResult`, not from catching adapter exceptions).
**How to avoid:** Wrap the entire body of `execute()`/`resume()` in a
broad `try/except Exception` that converts anything unexpected into
`WorkerResult(status=FAILED, error=str(exc), summary=...)`. Combine with the
explicit timeout/non-zero-exit/bad-JSON handling from Pattern 1 so every
exit path is a `WorkerResult`, never an exception.
**Warning signs:** A `role_executions` row stuck at status `RUNNING` after a
`dark-factory run` process has already exited.

### Pitfall 3: Assuming `--permission-mode` provides path scoping
**What goes wrong:** Implementing a lookup from "restrict to worktree" to
some imagined `--permission-mode <value>` that does not exist in the current
CLI.
**Why it happens:** `tools/native.py`'s own Phase 6 docstring says
"`--permission-mode` restricting reads to the worktree" — written before
this phase's research confirmed the real mechanism.
**How to avoid:** Rely on `cwd=work_dir` (already true whenever the adapter
spawns inside the run's worktree) for the default worktree confinement of
reads, and on path-scoped `--allowedTools` specifiers (`Edit(<glob>/**)`)
for anything narrower than "the whole worktree," per Pattern 3.
**Warning signs:** A CI/local run where a role with only `repo.read` can
somehow write files elsewhere in the repository because the adapter set a
nonexistent restrictive flag and silently fell through to no restriction.

### Pitfall 4: Reintroducing PIPE-buffering by using `communicate()` "for
safety"
**What goes wrong:** Copy-pasting `shell_execute()`'s `PIPE` +
`communicate(timeout=...)` shape for the `claude` spawn because it is the
existing, tested pattern in this codebase.
**Why it happens:** It is the closest existing precedent and looks like the
safe, "don't reinvent" choice.
**How to avoid:** `communicate()` fully buffers output in the parent's
memory and returns it only once the process ends (or times out) — this
directly violates D-04's "streamed to the run's log files rather than
buffered." Use Pattern 1 (direct file redirect + `Popen.wait()`) instead;
it is simpler, not more complex, and has no PIPE-deadlock risk to begin with
because there is no PIPE.

## Code Examples

### Parsing the `--output-format json` result object
```python
# Source: code.claude.com/docs/en/agent-sdk/python (ResultMessage dataclass,
# confirmed current 2026-09-20) — CITED, not independently executed this
# session (no `claude` binary invoked; field names are quoted verbatim from
# official docs, not run against a live subprocess).
import json

def parse_result(raw_stdout: str) -> dict:
    """--output-format json prints exactly one JSON object; on a clean exit
    it is the entire (whitespace-trimmed) stdout content."""
    obj = json.loads(raw_stdout.strip())
    # obj keys per the documented ResultMessage dataclass:
    #   subtype: str            ("success" | "error_max_turns" |
    #                             "error_during_execution" | ...)
    #   duration_ms: int
    #   duration_api_ms: int
    #   is_error: bool
    #   num_turns: int
    #   session_id: str
    #   total_cost_usd: float
    #   usage: Usage
    #   result: str              # the model's final text — parse the
    #                            # NEEDS_INPUT: marker out of THIS field
    #   structured_output: Any | None
    #   permission_denials: list
    return obj
```

### The NEEDS_INPUT marker extraction (D-01)
```python
# D-01 (locked): the role's instruction prompt tells Claude to end its turn
# with a fixed marker line. Exact marker text is this phase's own choice
# (CONTEXT.md "Claude's Discretion") — shown here as one concrete option.
import re

_NEEDS_INPUT_RE = re.compile(r"^NEEDS_INPUT:\s*(.+)$", re.MULTILINE)

def extract_needs_input(result_text: str) -> str | None:
    match = _NEEDS_INPUT_RE.search(result_text)
    return match.group(1).strip() if match else None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `claude --print` unstructured text output only | `--output-format json` / `stream-json`, `--json-schema` for enforced structured output | Documented as of the current (2026-09) CLI; `--json-schema` requires a reasonably recent version | This phase only needs plain `--output-format json`; `--json-schema` is a future-hardening option for D-01's marker parsing, not required now |
| `-p` loading full interactive-session context (hooks, MCP servers, `CLAUDE.md`, plugins) by default | `--bare` flag skips all of that for deterministic CI-style runs | Documented as the "recommended mode for scripted and SDK calls" and slated to become `-p`'s default in a future release | Worth flagging for planner discretion: `--bare` gives more deterministic non-interactive behavior (no host `.claude/settings.json` hooks silently firing) at the cost of also needing `ANTHROPIC_API_KEY` explicitly (bare mode never reads OAuth/keychain credentials) — which D-02 already provides |
| `--permission-mode manual`/`default` interactive prompts | `--permission-mode dontAsk` / `--permission-prompts none` for unattended runs | Documented current behavior | Use one of these for a `-p` invocation with nobody available to answer a prompt — otherwise an un-covered tool call could hang indefinitely, defeating the very timeout this phase adds |

**Deprecated/outdated:** none identified — the CLI surface researched here
is the shipping, current one as of 2026-09-20 (`@anthropic-ai/claude-code`
2.1.278, published 2026-09-19).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact `NEEDS_INPUT:` marker text/regex shown in Code Examples is illustrative, not mandated — CONTEXT.md leaves the exact format to planning discretion | Code Examples | Low — self-contained inside the adapter, changing it later touches one module per D-01's own reversibility note |
| A2 | A default `Settings.worker_timeout_seconds` of roughly 1800s (30 min) is "generous" enough for a DEVELOPMENT-role attempt (build+test+iterate) without being unbounded | Standard Stack / Code Examples (not shown as a hard number above) | Medium — too short truncates legitimate long Developer attempts (spurious FAILED runs); too long delays detecting a genuinely hung process. No authoritative number found in Claude Code's own docs for "typical role duration"; this is an estimate, not measured |
| A3 | `--bare` mode is *not* adopted this phase (full `-p` context loading is used) | State of the Art | Low — reversible, but if a role's `.dark-factory/roles/*.md` instructions rely on repo `CLAUDE.md` being auto-loaded rather than passed explicitly via `RoleContext.baseline_docs`, switching to `--bare` later would silently drop that unless the prompt already includes it explicitly (which it should, per CTX-01 — `RoleContext` already carries `baseline_docs` independent of what Claude Code auto-loads) |
| A4 | `--dangerously-skip-permissions` / `bypassPermissions` is not needed given `--allowedTools` + `--permission-mode dontAsk` is sufficient for a fully unattended role | Pattern 3 | Low — `.claude/CLAUDE.md` already scopes `--dangerously-skip-permissions` to "only inside a sandboxed worktree," consistent with this |

## Open Questions

1. **Exact `Settings.worker_timeout_seconds` default value**
   - What we know: CONTEXT.md D-03 requires "a generous default... explicitly
     generous rather than tight" and explicitly defers the exact number to
     planning.
   - What's unclear: No documented "typical" role-attempt duration exists to
     anchor the number against.
   - Recommendation: 1800 seconds (30 minutes) as a starting default,
     overridable via env (`WORKER_TIMEOUT_SECONDS`), following the same
     `Settings` pattern as `lease_ttl_seconds`. Flag for human confirmation
     at the plan-check/discuss stage if the actual DEVELOPMENT-role test
     suites in this repo (pytest + real Postgres 17) are known to run
     longer than that.

2. **Whether `resume()` should widen `--allowedTools` if the paused role's
   grants haven't changed**
   - What we know: `RoleContext` is rebuilt identically for a resumed
     attempt (same `role_def`, same `tools`); the native-tool translation
     (Pattern 3) is a pure function of `context.tools`.
   - What's unclear: Nothing — this resolves itself for free, since
     `resume()` calls the same `_base_argv(context)` helper as `execute()`.
     Recorded here only to confirm no special-casing is needed.
   - Recommendation: No action needed; call out as a confirmation, not a gap.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `claude` CLI on `PATH` | `ClaudeCodeWorker.execute()`/`resume()` at runtime | Not probed this session (research is code-facing, not this machine's tool inventory) | `@anthropic-ai/claude-code` 2.1.278 is current on npm as of 2026-09-19 [VERIFIED: npm registry] | Contract-suite / unit tests must fake the `claude` binary (see below) so CI never needs a real install or a live `ANTHROPIC_API_KEY` |
| `ANTHROPIC_API_KEY` | Real (integration-tier) `ClaudeCodeWorker` runs | Not probed — a live credential is out of scope for this research pass and must never be required for the unit/contract test tiers | — | `pytest.mark.integration`, skipped when the credential is absent, per QUAL-03's precedent even though QUAL-03 itself is Phase 8 scope |
| Docker / local Postgres 17 for the `db`/`integration` test tiers | Already established (Phase 1 `conftest.py` probe ladder) | Unchanged by this phase | — | Unchanged — this phase adds no new database dependency |

**Missing dependencies with no fallback:** none for the tiers this phase's
own automated tests must pass (unit + contract, no live `claude` binary
needed if the contract-suite fakes it — see below).

**Missing dependencies with fallback:** `claude` CLI / `ANTHROPIC_API_KEY` —
both fall back to a skipped/faked path for automated tests; only a genuinely
live end-to-end human-verification pass needs the real binary and a real
key.

### Faking the `claude` binary for the contract suite (Specific research item #4)

The codebase has **no existing precedent** for a fake-executable-on-`PATH`
technique (checked: no such pattern in `tests/support/`). The cleanest fit
with the existing credential-boundary design is: prepend a test-only
directory containing an executable script named `claude` to the **parent
test process's** `PATH` before constructing `ClaudeCodeWorker()`.
`build_worker_env()` copies `PATH` from `os.environ` verbatim when present
[VERIFIED: src/dark_factory/tools/env.py:102-104 — `env = {name:
os.environ[name] for name in WORKER_ENV_ALLOWLIST if name in os.environ}`,
and `PATH` is the first entry of `WORKER_ENV_ALLOWLIST` at line 54-66], and
`subprocess.Popen` resolves a bare command name (`"claude"`, not an absolute
path) against the `env["PATH"]` passed to it on POSIX [CITED:
docs.python.org/3/library/subprocess.html]. A fake `claude` script (a small
Python or shell script, executable bit set) that reads a scripted-response
env var — mirroring `FakeWorker`'s own `DARK_FACTORY_FAKE_SCRIPT` convention
— and prints the corresponding `--output-format json` JSON blob to stdout is
therefore sufficient with **zero changes** to `ClaudeCodeWorker`'s own code
or to the `Callable[[], CodingWorker]` shape `WORKER_FACTORIES` requires:

```python
# tests/contract/test_coding_worker_contract.py — additive change
WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker, ClaudeCodeWorker]
```
with a session/module-scoped fixture that prepends a fake-`claude`-bearing
directory to `os.environ["PATH"]` for the duration of the contract-suite
run (a `monkeypatch.setenv("PATH", ...)`-style fixture, or a
`pytest.fixture(autouse=True)` scoped to the test module). This needs no
`subprocess.Popen` monkeypatching and no dependency injection into
`ClaudeCodeWorker`'s constructor — it stays zero-arg-constructible, matching
the existing `WORKER_FACTORIES` type.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.x [VERIFIED: pyproject.toml — `pytest>=9,<10`] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -m unit` |
| Full suite command | `uv run pytest` (includes `db`/`integration`/`contract` tiers per the existing probe-ladder `conftest.py`) |

### Phase Requirement → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WORK-04 | `ClaudeCodeWorker.execute()` spawns `claude` non-interactively, returns a normalized `WorkerResult` | unit + contract | `uv run pytest tests/unit/test_claude_code_worker.py tests/contract/test_coding_worker_contract.py -m "unit or contract"` | ❌ Wave 0 |
| WORK-07 | `WorkerCapabilities` for `ClaudeCodeWorker` declares `native_resume=True, session_id=True` accurately | unit | `uv run pytest tests/unit/test_claude_code_worker.py::test_capabilities -m unit` | ❌ Wave 0 |
| HITL-04 | Resume through `worker_session_id` uses `--resume`; orchestrator never inspects the id | unit (fake-`claude` asserts `--resume <id>` in the observed argv) | `uv run pytest tests/unit/test_claude_code_worker.py::test_resume_uses_native_session_id -m unit` | ❌ Wave 0 |
| HITL-05 | Same `worker.resume(...)` call shape works when `native_resume=False` (existing `FakeWorker` behavior, unaffected) | contract (already covers `FakeWorker`) | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ✅ existing |
| QUAL-02 | Shared contract suite passes against both `FakeWorker` and `ClaudeCodeWorker` | contract | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ⚠️ existing file, needs `ClaudeCodeWorker` appended to `WORKER_FACTORIES` |
| QUAL-04 | CI fails the build on a worker-name leak outside adapter modules | unit (guard already exists) + **new CI wiring** | `uv run pytest tests/unit/test_no_worker_name_leak.py -m unit` | ✅ guard exists; ❌ no `.github/workflows/*.yml` exists in this repo yet — see Open Gap below |
| SC5 (timeout+streaming+kill) | A hung subprocess is killed by process-group timeout; output streamed to `logs/<role>/`; failure persisted with captured output | unit (fake `claude` script that sleeps past a short injected timeout) | `uv run pytest tests/unit/test_claude_code_worker.py::test_timeout_kills_process_group_and_persists_output -m unit` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -m unit`
- **Per wave merge:** `uv run pytest -m "unit or contract"` (this phase adds
  no new `db`-tier requirement, but re-run the full suite before the phase
  gate regardless, per existing project convention)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/support/` — a fake-`claude`-executable helper (script content +
      a `PATH`-prepending fixture), the missing precedent identified above
- [ ] `tests/unit/test_claude_code_worker.py` — the new adapter's own unit
      suite (argv construction, timeout/kill, redaction-before-return,
      NEEDS_INPUT marker parsing, never-raises invariant)
- [ ] `tests/contract/test_coding_worker_contract.py` — append
      `ClaudeCodeWorker` to `WORKER_FACTORIES` (existing file, one-line
      addition plus whatever fixture wiring the fake binary needs)

**Open Gap (flag for planner, not a Wave 0 test file):** this repository has
**no `.github/workflows/` directory at all** — confirmed by directory
listing. The ROADMAP's own design-invariant table already lists "No
worker-name branching outside adapters (**CI-enforced**)" against "Phase 1
(guard from Phase 7)," implying SC4 ("A CI check fails the build...")
expects an actual CI pipeline to exist by the end of this phase, not merely
a local pytest file. The unit-test guard (`test_no_worker_name_leak.py`)
already exists and passes locally; it is not yet wired into any CI system.
Planning should include a minimal `.github/workflows/ci.yml` (or equivalent)
that runs at least `uv run pytest -m unit` on push/PR so SC4 is literally
true — "a CI check fails the build" requires a CI check to exist.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | This phase adds a worker *credential* (`ANTHROPIC_API_KEY`), not end-user authentication |
| V3 Session Management | no | `worker_session_id` is an opaque Claude Code session handle, not an application session |
| V4 Access Control | partial | Native tool restriction (`--allowedTools`) is defense-in-depth *only* — `enforce_write_scope` (ROLE-05, post-hoc git-diff based) remains the actual authorization boundary, unchanged by this phase |
| V5 Input Validation | yes | `argv` passed to `subprocess.Popen` as an explicit list (never `shell=True`, never string-joined) — same discipline as `shell_execute`/`run_git`; prompt text built from `RoleContext` fields, never raw untrusted external input interpolated into a shell string |
| V6 Cryptography / secrets | yes | `ANTHROPIC_API_KEY` handled as `SecretStr` on `Settings`, flows to the subprocess only via `build_worker_env(env_var_name=..., value=...)` — never `os.environ.copy()`, never logged (existing `known_secret_values()` mechanism picks it up automatically per its own docstring) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Un-redacted subprocess transcript committed to a public PR branch (this phase's own Pitfall 1) | Information Disclosure | `redact()` the captured log content in-process before `execute()`/`resume()` returns, using `Settings.known_secret_values()` plus the existing D-15 pattern table — see Pattern 2 |
| Prompt injection from repo/artifact content steering the agent into destructive shell commands | Elevation of Privilege / Tampering | Defense-in-depth: `--allowedTools` narrows what the CLI's own tools can do natively; `enforce_write_scope` (ROLE-05) independently rejects any resulting diff outside the role's declared `write_scope` regardless of what the agent attempted |
| Credential leakage into the worker subprocess environment | Information Disclosure | `build_worker_env()`'s explicit allowlist (existing, reused verbatim) — `DATABASE_URL`/`GITHUB_TOKEN` are structurally absent from the constructed environment, proven by the existing cross-process test (`tests/integration/test_worker_env_boundary.py`) |
| Command injection via unsanitized argv construction | Tampering | `subprocess.Popen` called with an explicit `list[str]` argv, never a shell string — same discipline `shell_execute`/`run_git` already enforce; no `shell=True` anywhere in this adapter |
| An adapter exception silently aborting the role without a persisted failure (this phase's own Pitfall 2) | Denial of Service (of observability) | Catch-all `try/except Exception` inside `execute()`/`resume()` converting every failure mode to a `WorkerResult(status=FAILED, ...)`, per SC5 |

## Sources

### Primary (HIGH confidence)
- npm registry (`npm view @anthropic-ai/claude-code version` / `time.modified`) — confirmed `@anthropic-ai/claude-code` 2.1.278, published 2026-09-19 [VERIFIED: npm registry]
- Direct file reads this session of `src/dark_factory/workers/{base,fake,registry}.py`, `src/dark_factory/domain/worker.py`, `src/dark_factory/context/builder.py`, `src/dark_factory/tools/{env,native}.py`, `src/dark_factory/config/settings.py`, `src/dark_factory/artifacts/paths.py`, `src/dark_factory/orchestrator/runner.py` (lines 760-1000), `src/dark_factory/domain/signal.py`, `src/dark_factory/git/diff.py`, `src/dark_factory/events/redaction.py`, `tests/contract/test_coding_worker_contract.py`, `tests/unit/test_no_worker_name_leak.py`, `tests/support/subprocess_runner.py` — every `[VERIFIED: <path>:<lines>]` claim above is grounded in these reads

### Secondary (MEDIUM confidence — official docs, fetched this session)
- `code.claude.com/docs/en/headless` — `-p`/`--print`, `--output-format`, `--bare`, SIGTERM/exit-code behavior, `--continue`/`--resume` semantics
- `code.claude.com/docs/en/cli-reference` — full flag table (`--allowedTools`, `--disallowedTools`, `--permission-mode` values, `--dangerously-skip-permissions`, `--session-id`, `--max-turns`, `--model`)
- `code.claude.com/docs/en/agent-sdk/python` — `ResultMessage` dataclass field list (`subtype`, `duration_ms`, `duration_api_ms`, `is_error`, `num_turns`, `session_id`, `total_cost_usd`, `usage`, `result`, `structured_output`, `permission_denials`)
- `code.claude.com/docs/en/permissions` — permission rule syntax (`Tool(specifier)`, gitignore-style path patterns, `Edit(<glob>/**)`), working-directory confinement, `--add-dir`
- `docs.python.org/3/library/subprocess.html` — `Popen` file-object stdout/stderr behavior, `wait(timeout=...)` vs `communicate(timeout=...)`, `os.killpg` interaction

### Tertiary (LOW confidence)
- A1/A2/A3/A4 in the Assumptions Log — the specific `worker_timeout_seconds` default value and the `--bare`-mode adoption question are estimates, not measured or documented facts

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new third-party dependency; CLI flag surface confirmed against current official docs and cross-checked against the live npm registry version
- Architecture: HIGH — every integration point (registry, `RoleContext`, orchestrator call site, `commit_run_artifacts` path, `WORKER_ENV_ALLOWLIST`, `redact()`) verified by reading the actual source this session, not inferred
- Pitfalls: HIGH for Pitfalls 1/2/3 (each traced to a specific confirmed source-line or a specific official-docs statement); MEDIUM for Pitfall 4 (a design-quality judgment, not a confirmed bug)

**Research date:** 2026-09-20
**Valid until:** 2026-09-27 (7 days — the Claude Code CLI ships roughly weekly per the version-gated notes embedded throughout its own docs; re-verify flag names/JSON schema before implementation if more than a week has passed)
