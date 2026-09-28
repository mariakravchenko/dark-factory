# Phase 7: Claude Code — the First Real Worker - Pattern Map

**Mapped:** 2026-09-20
**Files analyzed:** 8
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `src/dark_factory/workers/claude_code.py` (new) | service/adapter | request-response (subprocess spawn + parse) | `src/dark_factory/workers/fake.py` (`CodingWorker` shape) + `src/dark_factory/tools/env.py::shell_execute` (subprocess/timeout mechanics) | role-match (structural analog is `fake.py`; I/O-mechanics analog is `shell_execute`) |
| `src/dark_factory/workers/registry.py` (modified) | config/registry | CRUD (swap one factory entry) | itself — existing `"fake"` registration pattern in same file | exact |
| `src/dark_factory/config/settings.py` (modified) | config/model | CRUD (add fields) | itself — existing `github_token` / `lease_ttl_seconds` fields | exact |
| `src/dark_factory/artifacts/paths.py` or a small new `logs`-writer module (log file path helper, if not reusing `run_root` inline) | utility | file-I/O | `src/dark_factory/artifacts/paths.py::run_root`/`role_artifact_dir` | exact |
| `tests/contract/test_coding_worker_contract.py` (modified) | test | request-response | itself — `WORKER_FACTORIES` list | exact |
| `tests/unit/test_claude_code_worker.py` (new) | test | request-response / subprocess | `tests/unit/test_no_worker_name_leak.py` (guard-style unit test) + a fake-`claude`-on-`PATH` fixture (no existing precedent — build fresh, see below) | role-match |
| `tests/support/fake_claude_cli.py` or similar (new fake-binary helper) | test support / utility | file-I/O (writes an executable script) | `src/dark_factory/workers/fake.py`'s `DARK_FACTORY_FAKE_SCRIPT` convention (env-var-driven scripted response) — conceptual analog only, no direct file analog exists | no direct analog — design fresh per RESEARCH.md's guidance |
| `.github/workflows/ci.yml` (new) | config | event-driven (CI trigger) | none in repo (no `.github/workflows/` exists yet) | no analog — see "No Analog Found" |

## Pattern Assignments

### `src/dark_factory/workers/claude_code.py` (new adapter)

**Analogs:** `src/dark_factory/workers/fake.py` (contract shape), `src/dark_factory/tools/env.py` (subprocess/env mechanics), `src/dark_factory/domain/worker.py` (return shape), `src/dark_factory/tools/native.py` (tool-flag translation), `src/dark_factory/events/redaction.py` (log scrubbing), `src/dark_factory/artifacts/paths.py` (log directory placement), `src/dark_factory/config/settings.py` (credential/timeout source).

**`CodingWorker` contract to implement** (`src/dark_factory/workers/base.py:16-32`):
```python
class CodingWorker(ABC):
    @abstractmethod
    def execute(self, context: object) -> WorkerResult: ...
    @abstractmethod
    def resume(self, context: object, previous: WorkerResult, answer: str | None) -> WorkerResult: ...
    @abstractmethod
    def capabilities(self) -> WorkerCapabilities: ...
```

**Capabilities pattern** — mirror `fake.py:406-412`'s shape, but declare `native_resume=True`, `session_id=True` per WORK-07/D-CONTEXT (Pattern 4 in RESEARCH.md):
```python
def capabilities(self) -> WorkerCapabilities:
    return WorkerCapabilities(
        native_resume=True,
        session_id=True,
        structured_output=True,
        non_interactive=True,
        emits_changed_files=False,  # git/diff.py computes the real diff; adapter must not
    )
```

**Never-raise invariant** — every `fake.py` method returns a `WorkerResult`; `ClaudeCodeWorker.execute`/`resume` must do the same for every exit path (timeout, non-zero exit, malformed JSON, `FileNotFoundError` for missing `claude` binary). Wrap the whole body in `try/except Exception` and convert to `WorkerResult(status=WorkerResultStatus.FAILED, error=str(exc), summary=...)` — see RESEARCH.md Pitfall 2. `fake.py` demonstrates the target return shape at `fake.py:294-299` and `fake.py:327-332` (constructing `WorkerResult` with `status=...`, `summary=...`, `worker_session_id=...`).

**Credential-bounded subprocess env** — reuse `build_worker_env()` verbatim, do not reinvent (`src/dark_factory/tools/env.py:69-119`):
```python
env = build_worker_env(
    role,
    env_var_name="ANTHROPIC_API_KEY",
    value=settings.anthropic_api_key,  # SecretStr | None — D-02
)
```

**Subprocess spawn + timeout + process-group kill** — mirror `shell_execute`'s `Popen` shape (`src/dark_factory/tools/env.py:204-224`) but redirect stdout/stderr to open file handles instead of `PIPE`+`communicate()` (D-04 streaming requirement; RESEARCH.md Pattern 1 gives the concrete direct-file-redirect implementation to follow — do NOT copy `shell_execute`'s `PIPE`/`communicate()` I/O mechanism, only its credential/argv/kill discipline):
```python
proc = subprocess.Popen(
    argv,                       # explicit list[str], never a shell string
    cwd=str(work_dir),
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=out_fh,               # open file handle, not PIPE
    stderr=err_fh,
    start_new_session=True,      # heads its own process group
)
try:
    proc.wait(timeout=settings.worker_timeout_seconds)
except subprocess.TimeoutExpired:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    proc.wait()
```
Same `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` idiom as `shell_execute` (`tools/env.py:219-221`), same `start_new_session=True` (`tools/env.py:213`), same never-`shell=True` / explicit-list argv discipline (`tools/env.py:192-198`'s `InvalidShellCommandError` guard shows the project's argv-safety posture even though this adapter builds its own argv rather than accepting a caller-supplied one).

**Log file placement (D-04)** — reuse `run_root()`, not a new path scheme (`src/dark_factory/artifacts/paths.py:27-29`, `:32-37`):
```python
root = run_root(work_dir, UUID(context.run_id))
# ensure_run_tree(root) already creates "logs" alongside "artifacts"/"input"/"verification"
log_dir = root / "logs" / context.role
log_dir.mkdir(parents=True, exist_ok=True)
stdout_path = log_dir / f"attempt-{context.attempt}.stdout.log"
stderr_path = log_dir / f"attempt-{context.attempt}.stderr.log"
```
Note: `ensure_run_tree` (`paths.py:32-37`) **already creates a top-level `logs/` directory** — the adapter only needs the `logs/<role>/` subdirectory, matching the existing `role_artifact_dir` pattern (`paths.py:40-44`) for `artifacts/<role>/`.

**Redact the transcript before returning (SEC-01 gap, RESEARCH.md Pattern 2)** — reuse `redact()` + `Settings.known_secret_values()` verbatim, no bespoke regex (`src/dark_factory/events/redaction.py:179-245`, `src/dark_factory/config/settings.py:98-115`):
```python
from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact

def _scrub_log_in_place(path: Path) -> None:
    settings = get_settings()
    raw = path.read_text("utf-8", errors="replace")
    scrubbed = redact(raw, known_secrets=settings.known_secret_values())
    path.write_text(scrubbed, "utf-8")
```
Call for both stdout and stderr files, on every exit path (success, non-zero exit, timeout-kill) — see RESEARCH.md Pitfall 1.

**`WorkerResult` construction shape** — the frozen, `extra="forbid"` model every adapter must produce (`src/dark_factory/domain/worker.py:55-75`):
```python
class WorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: WorkerResultStatus
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    worker_session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
```
Note the `model_validator` at `worker.py:69-75` — a `NEEDS_INPUT` result MUST carry non-empty `questions`; the D-01 marker-extraction path must populate `questions=[extracted_question]`, never leave it empty.

**NEEDS_INPUT marker extraction (D-01)** — adapter-only parsing logic, no existing direct analog; RESEARCH.md's Code Examples section gives the illustrative regex to adapt:
```python
_NEEDS_INPUT_RE = re.compile(r"^NEEDS_INPUT:\s*(.+)$", re.MULTILINE)

def _extract_needs_input(result_text: str) -> str | None:
    match = _NEEDS_INPUT_RE.search(result_text)
    return match.group(1).strip() if match else None
```

**Native tool translation (Pattern 3, RESEARCH.md)** — consume `NATIVE_TOOL_CONTRACT` from `src/dark_factory/tools/native.py:63-196` (design contract already written; do not re-derive):
```python
_TOOL_NAMES = {
    "repo.read": ["Read", "Glob"],
    "repo.search": ["Grep", "Glob"],
    "repo.write": ["Write", "Edit"],
    "repo.write_tests": ["Write", "Edit"],
    "shell.execute": ["Bash"],
    "artifacts.read": ["Read"],
}
```
Deny-by-omission: a capability not in `context.tools`/`context.permissions` simply has its tool name(s) omitted from `--allowedTools`. Worktree confinement comes from `cwd=work_dir`, not from any `--permission-mode` value — RESEARCH.md Summary finding 1 / Pitfall 3 explicitly warns `tools/native.py`'s own docstring text ("restricting reads to the worktree") does not correspond to a real flag; do not implement a lookup for it.

**Resume via native session id (Pattern 4, RESEARCH.md)** — same spawn/timeout/redact/parse pipeline as `execute()`, with `--resume <session_id>` appended:
```python
def resume(self, context, previous, answer):
    argv = self._base_argv(context)
    argv += ["--resume", previous.worker_session_id, "-p", answer or ""]
    # identical spawn/timeout/redact/parse pipeline as execute()
```

**Credential typed error (D-02)** — mirror the `Settings` optional-field precedent (`config/settings.py:56`: `github_token: SecretStr | None = None`); raise a typed, clear error naming the missing env var inside `execute()`/`resume()` before spawning anything, not at Settings-construction time.

**Argv/subprocess safety discipline** — never `shell=True`, argv always an explicit `list[str]` — same discipline as `InvalidShellCommandError`'s guard in `tools/env.py:122-131,192-203` (the adapter builds its own trusted argv internally, so it does not need the same runtime type-check, but must follow the same "never a joined/shell string" rule).

---

### `src/dark_factory/workers/registry.py` (modified)

**Analog:** itself — existing `"fake"` factory registration (`registry.py:105-112`) and the placeholder being replaced (`registry.py:117-119`).

**Current placeholder to replace:**
```python
default_registry.register(
    "claude-code", lambda: _NotYetImplementedWorker("claude-code", "7")
)
```

**Pattern to follow** — a lambda factory (fresh instance per call), consistent with the "factory hands back a fresh instance every call" option described in the module docstring (`registry.py:7-10`); `ClaudeCodeWorker` should be zero-arg-constructible so `WORKER_FACTORIES` in the contract suite can reference the class directly (`registry.py:34, WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker]` in the contract test — same shape, no constructor args):
```python
from dark_factory.workers.claude_code import ClaudeCodeWorker
...
default_registry.register("claude-code", ClaudeCodeWorker)
```
Note: unlike `"fake"`, `ClaudeCodeWorker` does NOT need the shared-singleton treatment (`_shared_fake_worker()`, `registry.py:105-109`) — it carries no per-call cursor state; a fresh instance per `registry.get()` call is fine, and matches the zero-arg-constructible requirement `WORKER_FACTORIES` needs.

---

### `src/dark_factory/config/settings.py` (modified — new fields)

**Analog:** itself — the existing `github_token: SecretStr | None = None` precedent (`settings.py:56`) and `lease_ttl_seconds`/`lease_heartbeat_seconds` (`settings.py:58-59`).

**Pattern for the new credential field (D-02)** — optional, no eager validation, automatically covered by `known_secret_values()`'s `model_fields` walk (`settings.py:98-115`, no extra wiring needed):
```python
anthropic_api_key: SecretStr | None = None
```

**Pattern for the new timeout field (D-03)** — plain overridable int, mirroring `lease_ttl_seconds`'s shape (`settings.py:58`), NOT a `SecretStr` (it is not a credential):
```python
worker_timeout_seconds: int = 1800  # generous default per RESEARCH.md Open Question 1
```
If a positivity/coherence check is warranted, mirror the `@model_validator(mode="after")` pattern at `settings.py:74-96` (`_lease_intervals_are_coherent`) rather than inventing a new validation style.

---

### `tests/contract/test_coding_worker_contract.py` (modified)

**Analog:** itself.

**One-line additive change** (`test_coding_worker_contract.py:28`):
```python
WORKER_FACTORIES: list[Callable[[], CodingWorker]] = [FakeWorker, ClaudeCodeWorker]
```
Everything else in the file (the `worker` fixture at lines 31-34, and every `test_*` function) is parametrized over `WORKER_FACTORIES` already and needs no further modification — this is what proves QUAL-02. The suite requires the fake-`claude`-on-`PATH` fixture to be active for the whole module (see `tests/support/` pattern below) since `ClaudeCodeWorker()` must construct with zero args and `execute(None)`/`resume(None, ...)` must not require a live `claude` binary or credential.

---

### `tests/support/` fake-`claude`-executable helper (new — no direct precedent)

**No existing analog** — RESEARCH.md's "Faking the `claude` binary" section confirms `tests/support/` has no existing fake-executable-on-`PATH` technique. The closest conceptual analog is `FakeWorker`'s own `DARK_FACTORY_FAKE_SCRIPT` env-var-driven scripted-response convention (`src/dark_factory/workers/fake.py:335-339`, `_script_from_env`) — mirror the *shape* (env var names a JSON script, script exhausts/repeats predictably) for the fake binary's own scripting mechanism, but the delivery mechanism (an executable script prepended to `PATH`) has to be built fresh per RESEARCH.md's guidance:
```python
# tests/support/subprocess_runner.py existing precedent for cross-process
# test technique (child_env(), spawn/popen/wait_for) — read this file's
# existing helpers before adding a new one; do not duplicate its PATH-
# construction logic if it already assembles a similar allowlisted env.
```
Also read `src/dark_factory/tools/env.py:53-66` (`WORKER_ENV_ALLOWLIST`) — confirms `PATH` is the first allowlisted entry, and `build_worker_env()` copies it verbatim from `os.environ` (`env.py:102-104`), so prepending a fake-`claude` directory to the **test process's** `os.environ["PATH"]` before constructing `ClaudeCodeWorker()` is sufficient with zero adapter-code changes.

---

### `.github/workflows/ci.yml` (new — CI wiring for QUAL-04)

**No analog in this repo** — `RESEARCH.md`'s "Open Gap" confirms no `.github/workflows/` directory exists yet. Build minimal from scratch: a workflow that runs `uv run pytest -m unit` (at minimum) on push/PR, so `tests/unit/test_no_worker_name_leak.py` is CI-enforced rather than merely locally passing. No project analog to copy structure from; follow standard GitHub Actions + `uv` conventions (`uv sync --all-extras --dev` then `uv run pytest`, per `.claude/CLAUDE.md`'s Development Tools table).

## Shared Patterns

### Credential-bounded subprocess environment
**Source:** `src/dark_factory/tools/env.py::build_worker_env()` (lines 69-119)
**Apply to:** `ClaudeCodeWorker.execute()` and `.resume()` — the sole channel for `ANTHROPIC_API_KEY` to reach the `claude` subprocess. Never `os.environ.copy()`.

### Process-group timeout kill
**Source:** `src/dark_factory/tools/env.py::shell_execute()` (lines 204-224), specifically `start_new_session=True` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` on `TimeoutExpired`
**Apply to:** the `claude` subprocess spawn inside `ClaudeCodeWorker`, adapted for streamed (file-redirect) I/O instead of `PIPE`/`communicate()`.

### Secret redaction of captured output
**Source:** `src/dark_factory/events/redaction.py::redact()` (lines 179-245) + `Settings.known_secret_values()` (`settings.py:98-115`)
**Apply to:** both `logs/<role>/attempt-N.stdout.log` and `.stderr.log` files, before `execute()`/`resume()` returns, on every exit path — closes the SEC-01 gap RESEARCH.md identifies (un-redacted transcripts get committed onto the PR branch by `commit_run_artifacts`, which force-adds the whole `.dark-factory/runs/<run_id>/` tree).

### Never let an exception escape execute()/resume()
**Source:** `src/dark_factory/workers/fake.py` — every code path returns a `WorkerResult`, never raises (except the documented `ScriptExhaustedError` for the explicit-script-exhaustion case, which is a `FakeWorker`-only test-scaffolding concern, not a general adapter pattern)
**Apply to:** `ClaudeCodeWorker.execute()`/`.resume()` — wrap the whole body in `try/except Exception`, converting every failure (timeout, non-zero exit, malformed JSON, missing binary) into `WorkerResult(status=FAILED, error=..., summary=...)`.

### Frozen, extra="forbid" pydantic boundary models
**Source:** `src/dark_factory/domain/worker.py` (`WorkerResult`, `WorkerCapabilities`, `ArtifactRef`) and `src/dark_factory/tools/native.py::NativeToolGrant`
**Apply to:** any new intermediate domain model this phase introduces (e.g. a parsed Claude CLI result shape, if used) — `model_config = ConfigDict(frozen=True, extra="forbid")`.

### Run-tree path resolution
**Source:** `src/dark_factory/artifacts/paths.py::run_root()` / `role_artifact_dir()` (lines 27-44)
**Apply to:** the new `logs/<role>/` writer — reuse `run_root()` directly; `ensure_run_tree()` already creates the top-level `logs/` directory (line 36), so only a `logs/<role>/` subdirectory needs to be created by the adapter, mirroring `role_artifact_dir`'s `artifacts/<role>/` shape.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.github/workflows/ci.yml` | config | event-driven | No `.github/workflows/` directory exists in this repo at all (confirmed by RESEARCH.md's directory listing) — build from standard GitHub Actions + `uv` conventions, not from a repo analog |
| Fake-`claude`-executable test helper (`tests/support/`) | test support | file-I/O / process-fake | No existing fake-executable-on-`PATH` precedent in `tests/support/` — closest conceptual analog is `FakeWorker`'s `DARK_FACTORY_FAKE_SCRIPT` env-var scripting convention, but the delivery mechanism (an executable script + `PATH` fixture) must be designed fresh |
| `NEEDS_INPUT:` marker parsing logic (D-01) | adapter-internal parsing | transform | Locked to a brand-new convention with no CLI schema dependency by design (D-01); RESEARCH.md's Code Examples give an illustrative regex, not a codebase analog |

## Metadata

**Analog search scope:** `src/dark_factory/workers/`, `src/dark_factory/tools/`, `src/dark_factory/domain/`, `src/dark_factory/config/`, `src/dark_factory/artifacts/`, `src/dark_factory/events/`, `src/dark_factory/context/`, `tests/contract/`, `tests/unit/`, `tests/support/`
**Files scanned:** 11 (all confirmed git-tracked via `git ls-files`)
**Pattern extraction date:** 2026-09-20
