# Phase 8: Copilot & Hermes — Worker Independence Proven - Pattern Map

**Mapped:** 2026-09-21
**Files analyzed:** 11 (2 new adapters, 3 test-support fakes, 3 new integration suites, 3 modified files)
**Analogs found:** 11 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/dark_factory/workers/copilot.py` (new) | service (worker adapter) | request-response (subprocess spawn/parse) | `src/dark_factory/workers/claude_code.py` | exact — explicitly named the literal template in CONTEXT/RESEARCH |
| `src/dark_factory/workers/hermes.py` (new) | service (worker adapter) | request-response (subprocess spawn/parse) | `src/dark_factory/workers/claude_code.py` | exact — same |
| `src/dark_factory/workers/needs_input.py` (new, optional) | utility | transform (regex extraction) | `src/dark_factory/workers/claude_code.py` lines 62-90 (constants + regex) | exact — pure extraction of an existing block |
| `tests/support/fake_copilot_cli.py` (new) | test fixture/utility | file-I/O (writes an executable script) | `tests/support/fake_claude_cli.py` | exact — explicitly named the direct template |
| `tests/support/fake_hermes_cli.py` (new) | test fixture/utility | file-I/O | `tests/support/fake_claude_cli.py` | exact — same |
| `tests/unit/test_copilot_worker.py` (new) | test | request-response | `tests/unit/test_claude_code_worker.py` (not yet read, but same role/flow as adapter under test) | role-match |
| `tests/unit/test_hermes_worker.py` (new) | test | request-response | `tests/unit/test_claude_code_worker.py` | role-match |
| `tests/integration/test_claude_code_live.py` (new) | test | request-response, skip-guarded | no existing precedent (Scope Correction: zero `skipif` in repo) — RESEARCH.md Pattern 1 is the template | no analog — synthesized pattern from RESEARCH.md |
| `tests/integration/test_copilot_live.py` (new) | test | request-response, skip-guarded | RESEARCH.md Pattern 1 | no analog — synthesized pattern |
| `tests/integration/test_hermes_live.py` (new) | test | request-response, skip-guarded | RESEARCH.md Pattern 1 | no analog — synthesized pattern |
| `tests/integration/test_role_reassignment_sc2.py` (new) | test | event-driven / config-driven (full run) | likely an existing `tests/integration/test_*_run*.py`-style full-drive test (not read this pass — planner should grep `tests/integration/` for the closest existing full-pipeline-drive integration test) | role-match (not confirmed) |
| `src/dark_factory/workers/registry.py` (modify) | config/registry | CRUD (register two new factories) | itself — same file, two `_NotYetImplementedWorker` lines swap for real factories, mirroring the `"claude-code"` registration already present | exact (self-analog) |
| `src/dark_factory/config/settings.py` (modify) | config | CRUD (add one field) | itself — `anthropic_api_key` field + docstring paragraph is the direct template for the new `copilot_github_token` field | exact (self-analog) |
| `tests/contract/test_coding_worker_contract.py` (modify) | test | request-response (parametrized contract) | itself — `WORKER_FACTORIES` list append | exact (self-analog) |
| `tests/unit/test_native_tool_contract.py` (modify) | test | CRUD (allowlist append) | itself — `_ALLOWED_CONSUMERS` set append | exact (self-analog) |
| `.dark-factory/roles/ARCHITECTURE.yaml`, `QA.yaml` (modify) | config | CRUD (`worker:` field edit) | `.dark-factory/roles/DEVELOPMENT.yaml` (already `worker: claude-code` since Phase 7) | exact |

## Pattern Assignments

### `src/dark_factory/workers/copilot.py` (service, request-response)

**Analog:** `src/dark_factory/workers/claude_code.py` (entire file — 680 lines, already fully read; primary template per CONTEXT.md/RESEARCH.md)

**Imports pattern** (claude_code.py lines 19-47):
```python
from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path
from uuid import UUID

from dark_factory.artifacts.paths import run_root
from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.events.redaction import redact
from dark_factory.tools.env import build_worker_env
from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
from dark_factory.workers.base import CodingWorker
```
For `copilot.py`: drop the `json`-parsing-of-stdout usage (Copilot output is plain text per D-02/RESEARCH — parse text, not JSON) but keep everything else. Add `MissingWorkerCredentialError` naming `COPILOT_GITHUB_TOKEN` per Finding 3.

**Credential / constants pattern** (claude_code.py lines 62-70, 121-136):
```python
CLAUDE_CREDENTIAL_ENV_VAR = "ANTHROPIC_API_KEY"
CLAUDE_BINARY = "claude"
PERMISSION_MODE = "dontAsk"

NEEDS_INPUT_MARKER = "NEEDS_INPUT:"
NEEDS_INPUT_PROTOCOL = f"""## Clarification protocol
If you cannot proceed without a human decision, end your final message with a
single line that begins with the exact token "{NEEDS_INPUT_MARKER}" followed
by the one question the human must answer. Write nothing after that line.
Never emit this token for any other purpose."""

class MissingWorkerCredentialError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            f"{CLAUDE_CREDENTIAL_ENV_VAR} is not configured -- set "
            "Settings.anthropic_api_key before running a role whose worker "
            "is 'claude-code'"
        )
```
For `copilot.py`: `COPILOT_CREDENTIAL_ENV_VAR = "COPILOT_GITHUB_TOKEN"`, `COPILOT_BINARY = "copilot"`, and `MissingWorkerCredentialError` naming `Settings.copilot_github_token`. Reuse `NEEDS_INPUT_MARKER`/`NEEDS_INPUT_PROTOCOL`/`_NEEDS_INPUT_RE` verbatim (D-03) — either import from `claude_code.py` or a new shared `needs_input.py` (Claude's Discretion).

**Argv construction pattern** (claude_code.py lines 337-376, `_base_argv`):
```python
def _base_argv(context: object) -> list[str]:
    granted = getattr(context, "tools", None) or []
    ...
    argv = [CLAUDE_BINARY, "--output-format", "json", "--permission-mode", PERMISSION_MODE]
    names = allowed_tools_for(granted, artifacts_glob, artifacts_read_glob)
    if names:
        argv.extend(["--allowedTools", ",".join(names)])
    return argv
```
Copilot equivalent per RESEARCH.md Finding 3:
```python
argv = [COPILOT_BINARY, "--no-ask-user", "-s"]
for tool in allowed_tools_for(granted, ...):   # translate via NATIVE_TOOL_CONTRACT["copilot"]
    argv.extend(["--allow-tool", tool])
argv.extend(["--model", COPILOT_MODEL_PIN])
argv.extend(["-p", prompt])
# NEVER --allow-all-tools, --allow-all-paths, --share, --share-gist
```

**Core spawn/parse pipeline** (claude_code.py lines 405-441 `_run_streamed`, 470-584 `_spawn_and_parse`):
```python
def _run_streamed(argv, *, cwd, env, stdout_path, stderr_path, timeout) -> tuple[int | None, bool]:
    with stdout_path.open("wb") as out_fh, stderr_path.open("wb") as err_fh:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            stdout=out_fh, stderr=err_fh, start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
            return None, True
    return proc.returncode, False
```
Copy this function verbatim (binary-agnostic). In `_spawn_and_parse`, replace the `json.loads(stdout_text)` result-object parsing with **plain-text parsing** (RESEARCH.md's explicit MVP recommendation — no `--output-format=json` this phase): `result_text = stdout_text`, then run `_extract_needs_input(result_text)` exactly as claude_code.py line 569 does, and build `WorkerResult(status=COMPLETED, summary=result_text, worker_session_id=None, metadata={})` (no session id — `session_id=False` capability).

**Error handling pattern** (claude_code.py lines 513-534):
```python
if timed_out:
    return WorkerResult(status=FAILED, summary="<name> worker timed out", error=..., metadata={"timed_out": True, "exit_code": None})
if exit_code != 0:
    stderr_text = stderr_path.read_text("utf-8", errors="replace")
    return WorkerResult(status=FAILED, summary="<name> worker exited non-zero", error=f"... {stderr_text[:_MAX_ERROR_EXCERPT]}", metadata={"timed_out": False, "exit_code": exit_code})
```
Copy verbatim, substituting the CLI name in summary strings.

**Never-raise wrapper** (claude_code.py lines 451-465, 615-636):
```python
def execute(self, context: object) -> WorkerResult:
    try:
        return self._execute(context)
    except Exception as exc:
        return WorkerResult(status=FAILED, summary="<name> worker failed", error=str(exc))
```
Copy verbatim for both `execute()` and `resume()`.

**Capabilities** (claude_code.py lines 664-679) — Copilot's value per RESEARCH.md Finding 2:
```python
def capabilities(self) -> WorkerCapabilities:
    return WorkerCapabilities(
        native_resume=False,
        session_id=False,
        structured_output=False,
        non_interactive=True,
        emits_changed_files=False,
    )
```

**Credential env injection** (claude_code.py lines 487-491):
```python
env = build_worker_env(role, env_var_name=CLAUDE_CREDENTIAL_ENV_VAR, value=settings.anthropic_api_key)
```
Copilot: `build_worker_env(role, env_var_name="COPILOT_GITHUB_TOKEN", value=settings.copilot_github_token)`.

**Log scrubbing** (claude_code.py lines 379-402, `_scrub_log_in_place`) — copy verbatim, binary-agnostic.

**`_resolve_dirs`** (claude_code.py lines 586-613) — copy verbatim, binary-agnostic (no `claude`-specific logic in it).

---

### `src/dark_factory/workers/hermes.py` (service, request-response)

**Analog:** same as above, `src/dark_factory/workers/claude_code.py`, with these Hermes-specific deltas from RESEARCH.md Finding 1 / Finding 4:

**Credential** — reuse `Settings.anthropic_api_key`, do **not** add a new Settings field:
```python
HERMES_CREDENTIAL_ENV_VAR = "ANTHROPIC_API_KEY"
HERMES_BINARY = "hermes"

class MissingWorkerCredentialError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "ANTHROPIC_API_KEY is not configured -- set "
            "Settings.anthropic_api_key before running a role whose worker "
            "is 'hermes' (Hermes has no dedicated credential; it reuses the "
            "same Anthropic key Claude Code uses)"
        )
```

**Argv + isolation** (RESEARCH.md Finding 4, Pitfall 3):
```python
argv = [HERMES_BINARY, "chat", "-q", prompt, "--oneshot", "-Q", "--ignore-user-config"]
env["HERMES_HOME"] = str(xdg_root)  # keep state.db/.env out of operator's real ~/.hermes
```
`NEVER pass --tui`.

**Capabilities** — identical shape to Copilot's block above: `native_resume=False, session_id=False, structured_output=False, non_interactive=True, emits_changed_files=False`.

Everything else (spawn/timeout/redact pipeline, error handling, never-raise wrapper, `_resolve_dirs`, `NEEDS_INPUT` parsing) is the same copy-from-`claude_code.py` guidance as the Copilot section above.

---

### `tests/support/fake_copilot_cli.py` / `tests/support/fake_hermes_cli.py` (test fixture, file-I/O)

**Analog:** `tests/support/fake_claude_cli.py` (entire file, already fully read — 136 lines)

Copy the whole module shape verbatim, renaming `claude` → `copilot`/`hermes`:
```python
def write_fake_copilot(
    directory: Path, *, stdout_payload: str | bytes, exit_code: int = 0,
    sleep_seconds: float = 0.0, stderr_text: str = "",
    argv_log: Path | None = None, env_log: Path | None = None,
) -> Path:
    ...
    script_path = directory / "copilot"
    script = f"""#!/usr/bin/env python3
    ... (identical body, baked-literal config via repr())
    """
```
```python
@contextlib.contextmanager
def fake_copilot_env(
    monkeypatch: pytest.MonkeyPatch, directory: Path, *,
    copilot_github_token: str = "github_pat_fake0000000000000000000000000000",
    database_url: str = ..., database_url_direct: str = ...,
) -> Iterator[None]:
    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{existing_path}")
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", copilot_github_token)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL_DIRECT", database_url_direct)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
```
`fake_hermes_env` mirrors this but sets `ANTHROPIC_API_KEY` (Hermes reuses the Claude Code credential — no `hermes_api_key` field exists, per Finding 1) instead of a Hermes-specific var.

---

### `tests/integration/test_claude_code_live.py` / `test_copilot_live.py` / `test_hermes_live.py` (test, skip-guarded live integration)

**Analog:** No in-repo precedent (RESEARCH.md Scope Correction: `grep -rn skipif tests/` returns zero matches). Use RESEARCH.md's own synthesized "Pattern 1" verbatim:
```python
import shutil
import pytest
from dark_factory.config.settings import get_settings

_BINARY_MISSING = shutil.which("copilot") is None
_CREDENTIAL_MISSING = get_settings().copilot_github_token is None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_BINARY_MISSING, reason="copilot CLI not found on PATH"),
    pytest.mark.skipif(_CREDENTIAL_MISSING, reason="Settings.copilot_github_token is not configured"),
]

def test_copilot_worker_executes_a_trivial_role() -> None:
    ...
```
For `claude-code`: binary check `shutil.which("claude")`, credential check `get_settings().anthropic_api_key is None`. For `hermes`: binary check `shutil.which("hermes")`, credential check `get_settings().anthropic_api_key is None` (same credential as Claude Code, per Finding 1).

---

## Shared Patterns

### NEEDS_INPUT pause-signal contract (D-03)
**Source:** `src/dark_factory/workers/claude_code.py` lines 66-90
**Apply to:** `workers/copilot.py`, `workers/hermes.py` — the literal marker string, protocol text, and MULTILINE+DOTALL regex must be identical across all three adapters:
```python
NEEDS_INPUT_MARKER = "NEEDS_INPUT:"
_NEEDS_INPUT_RE = re.compile(
    rf"^{re.escape(NEEDS_INPUT_MARKER)}[ \t]*(.*)\Z", re.MULTILINE | re.DOTALL
)

def _extract_needs_input(result_text: str) -> str | None:
    match = _NEEDS_INPUT_RE.search(result_text)
    if match is None:
        return None
    question = match.group(1).strip()
    return question or None
```
Planning decides whether this is extracted to `workers/needs_input.py` and imported by all three adapters, or duplicated per file — either satisfies D-03 as long as the literal text/semantics match.

### Credential-bounded subprocess environment
**Source:** `src/dark_factory/tools/env.py` — `build_worker_env()` (lines 69-119), `WORKER_ENV_ALLOWLIST` (lines 53-66)
**Apply to:** all worker adapters. Called exactly once per spawn with `env_var_name`/`value` set to the adapter's own credential:
```python
env = build_worker_env(role, env_var_name="COPILOT_GITHUB_TOKEN", value=settings.copilot_github_token)
```
Never `os.environ.copy()`. This is the third/fourth application of the same discipline (git client, `shell.execute`, Claude Code, now Copilot/Hermes).

### Catch-all never-raise wrapper
**Source:** `src/dark_factory/workers/claude_code.py` lines 451-465 and 615-636
**Apply to:** every adapter's public `execute()`/`resume()` — the orchestrator's `advance()` step has no surrounding `try/except`, so an escaping exception strands `role_executions` at RUNNING with no terminal event.

### Timeout-then-process-group-kill
**Source:** `src/dark_factory/workers/claude_code.py` lines 405-441 (`_run_streamed`)
**Apply to:** every adapter — `start_new_session=True` at spawn, `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` on `TimeoutExpired`, reap with a second untimed `proc.wait()`.

### Log redaction before any further read
**Source:** `src/dark_factory/workers/claude_code.py` lines 379-402 (`_scrub_log_in_place`), called in a `finally` block at lines 500-511
**Apply to:** every adapter — `_scrub_log_in_place(stdout_path)`/`_scrub_log_in_place(stderr_path)` must run in a `finally` immediately after `_run_streamed` returns or raises, before anything downstream re-reads the log files (they get committed onto the run's working branch by `git/diff.py`).

### Settings credential field (Copilot only — D-01)
**Source:** `src/dark_factory/config/settings.py` lines 73 (`anthropic_api_key: SecretStr | None = None`) and its docstring paragraph (lines 47-52)
**Apply to:** add `copilot_github_token: SecretStr | None = None` with an analogous docstring paragraph. No redaction wiring needed — `known_secret_values()` (lines 127-144) walks `model_fields` generically. Hermes needs **no** new field (Finding 1 — reuse `anthropic_api_key`).

### Registry registration swap
**Source:** `src/dark_factory/workers/registry.py` lines 114-125
**Apply to:** replace
```python
default_registry.register("copilot", lambda: _NotYetImplementedWorker("copilot", "8"))
default_registry.register("hermes", lambda: _NotYetImplementedWorker("hermes", "8"))
```
with
```python
default_registry.register("copilot", CopilotWorker)
default_registry.register("hermes", HermesWorker)
```
mirroring line 119's existing `default_registry.register("claude-code", ClaudeCodeWorker)` — fresh instance per `get()` call, no shared-singleton treatment (contrast `"fake"`'s singleton pattern), since neither new adapter carries cursor state.

### Contract-suite parametrization
**Source:** `tests/contract/test_coding_worker_contract.py` line 40
```python
WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker, ClaudeCodeWorker]
```
**Apply to:** append `CopilotWorker, HermesWorker`, and add the corresponding `from dark_factory.workers.copilot import CopilotWorker` / `from dark_factory.workers.hermes import HermesWorker` plus `from tests.support.fake_copilot_cli import fake_copilot_env, write_fake_copilot` (and Hermes equivalent) imports, mirroring line 36's existing `from tests.support.fake_claude_cli import fake_claude_env, write_fake_claude`.

### Native tool contract consumer allowlist
**Source:** `tests/unit/test_native_tool_contract.py` — `_ALLOWED_CONSUMERS` (not read this pass; grep confirms the file exists and gates which modules may import `NATIVE_TOOL_CONTRACT`)
**Apply to:** add `"dark_factory.workers.copilot"` and `"dark_factory.workers.hermes"` to `_ALLOWED_CONSUMERS`, mirroring however `"dark_factory.workers.claude_code"` is already listed there.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/integration/test_claude_code_live.py`, `test_copilot_live.py`, `test_hermes_live.py` | test | request-response, skip-guarded | Zero existing `skipif`-guarded suite in the repo (RESEARCH.md Scope Correction, confirmed via `grep -rn skipif tests/`). Use RESEARCH.md's synthesized Pattern 1 (reproduced above under Pattern Assignments) as the template instead of an in-repo analog. |
| `tests/integration/test_role_reassignment_sc2.py` | test | config-driven full-pipeline run | Not confirmed against the actual `tests/integration/` directory this pass — planner/executor should grep for the closest existing "drive a full run end-to-end against real role YAML" integration test (likely exists from Phase 3/4/7) and use that as the structural analog instead of building from scratch. |

## Metadata

**Analog search scope:** `src/dark_factory/workers/`, `src/dark_factory/tools/`, `src/dark_factory/config/`, `tests/support/`, `tests/contract/`, `tests/unit/`
**Files read directly:** `workers/claude_code.py` (680 lines, full), `tests/support/fake_claude_cli.py` (136 lines, full), `workers/registry.py` (126 lines, full), `config/settings.py` (155 lines, full), `tools/env.py` (228 lines, full), `tools/native.py` (grep only, copilot/hermes entries confirmed present), `tests/contract/test_coding_worker_contract.py` (grep only, `WORKER_FACTORIES` location confirmed)
**Pattern extraction date:** 2026-09-21

## PATTERN MAPPING COMPLETE

**Phase:** 8 - Copilot & Hermes — Worker Independence Proven
**Files classified:** 16
**Analogs found:** 14 exact/role-match / 16 total (2 synthesized-from-research, no in-repo precedent)

### Coverage
- Files with exact analog: 13
- Files with role-match analog: 1 (`test_role_reassignment_sc2.py`, unconfirmed)
- Files with no in-repo analog (use RESEARCH.md's synthesized pattern instead): 3 (`test_claude_code_live.py`, `test_copilot_live.py`, `test_hermes_live.py`)

### Key Patterns Identified
- Both new adapters must be near-verbatim structural clones of `claude_code.py`'s `_spawn_and_parse` pipeline (spawn → timeout-kill → redact-in-`finally` → parse → `NEEDS_INPUT` check → `WorkerResult`), differing only in binary name, argv flags, credential env var name, and plain-text-vs-JSON stdout parsing.
- The `NEEDS_INPUT_MARKER`/`_NEEDS_INPUT_RE` pause contract must be reused verbatim (D-03) — planner decides shared-module vs. per-file duplication.
- Hermes needs **no** new `Settings` field (reuses `anthropic_api_key`); Copilot needs exactly one (`copilot_github_token`), following the existing `anthropic_api_key` field as its direct template.
- The fake-CLI-executable-on-`PATH` technique (`fake_claude_cli.py`) is a direct, mechanical template for `fake_copilot_cli.py`/`fake_hermes_cli.py`.
- The skip-guarded live-integration-suite pattern has zero in-repo precedent — this phase introduces it fresh, using RESEARCH.md's own synthesized pattern for all three adapters (including retroactively for `claude-code`, per the Scope Correction).

### File Created
`/Users/maryiakrauchanka/portfolio/dark-factory/.planning/phases/08-copilot-hermes-worker-independence-proven/08-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
