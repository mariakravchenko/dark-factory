# Phase 5: Isolated Workspace & Git Lifecycle - Pattern Map

**Mapped:** 2026-09-14
**Files analyzed:** 18 (new + modified)
**Analogs found:** 15 / 18

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `src/dark_factory/git/client.py` (new) | utility (subprocess wrapper) | request-response (git CLI) | `tests/support/subprocess_runner.py` (`spawn`/`popen`/`child_env`) | role-match (subprocess-invocation discipline, not git-specific) |
| `src/dark_factory/git/worktree.py` (new) | service | CRUD (create/reuse/remove worktree) | `src/dark_factory/artifacts/paths.py` (`ensure_run_tree`, `run_root`) | role-match (idempotent filesystem-tree creation) |
| `src/dark_factory/git/lifecycle.py` (new) | service | event-driven (detect state, react) | `src/dark_factory/orchestrator/lease.py` (typed exceptions, no DB) | role-match (typed exception raised by a non-DB check consumed by the orchestrator) |
| `src/dark_factory/git/diff.py` (new) | service | transform (diff/commit) | `src/dark_factory/artifacts/validation.py::collect_role_artifacts` | role-match (pure function, raises typed error, no DB) |
| `src/dark_factory/git/scope.py` (new) | service | transform (glob match + revert) | `src/dark_factory/artifacts/paths.py::resolve_under_run_root` | role-match (path-safety containment guard pattern, T-04-01) |
| `src/dark_factory/actions/builtins.py` (modify: `ensure_clean_worktree`, `collect_diff`) | action (dispatcher) | request-response (thin call into `git/`) | same file, other builtins (`store_role_artifacts`/`prepare_role_context` docstrings) | exact (same file, same no-op-becomes-dispatcher pattern) |
| `src/dark_factory/actions/__init__.py` | config/registration | — | itself (already registers both names) | exact (no change needed — already wired) |
| `src/dark_factory/persistence/models.py` (add `role_executions.wip_commit_sha`) | model | CRUD (schema) | `Run.owner_token` / `Run.lock_expires_at` (nullable lease columns added in 0003) | exact |
| `src/dark_factory/persistence/mutations.py` (extend `RoleExecutionWrite`, `_write_role_execution`) | mutation-path model + writer | CRUD (sticky/compare-and-set update) | `_write_role_execution`'s existing update branch (same file) | exact (extend in place) |
| `migrations/versions/0005_wip_commit_sha.py` (new) | migration | schema (DDL) | `migrations/versions/0003_pause_resume_lease.py` (`op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))`) | exact |
| `src/dark_factory/config/loader.py` (validate `write_scope` patterns) | config validator | request-response (fail loud) | `load_effective_config`'s existing `ConfigError` raises (instructions-path / unknown-worker checks) | exact |
| `.dark-factory/roles/DEVELOPMENT.yaml`, `.dark-factory/roles/QA.yaml` (set real `write_scope`) | config | — | `.dark-factory/roles/DEVELOPMENT.yaml` itself (current `write_scope: []` placeholder + comment naming Phase 5) | exact |
| `src/dark_factory/domain/artifacts.py` (no schema change; `changed_files` populated by caller) | model (unchanged) | transform | `ImplementationSummary.changed_files` docstring (already names Phase 5) | exact — no code change here, only a caller (git/diff.py + runner.py) populating it |
| `src/dark_factory/orchestrator/runner.py` (wire worktree/WIP/write-scope) | orchestrator (wiring point) | event-driven / request-response | `_run_current_role`'s existing `ArtifactError`/D-09 catch (same file, lines ~552-563) | exact (same control-flow shape reused for D-08/D-13) |
| `src/dark_factory/events/catalog.py` (optional new `WIP_COMMIT_CREATED` member) | model (enum) | — | existing Phase 2 additions (`QUESTION_CREATED`, `RUN_PAUSED`, etc.) | exact |
| `tests/support/git_repo.py` (new) | test fixture factory | file-I/O (real throwaway repo) | `tests/support/subprocess_runner.py` (allowlist env, real subprocess discipline) | role-match |
| `tests/unit/test_git_worktree.py`, `tests/unit/test_write_scope.py`, `tests/unit/test_git_ownership_boundary.py` (new) | test | unit | `tests/unit/test_artifact_paths.py` (T-04 style path-safety unit tests) / `tests/unit/test_single_mutation_path.py` (AST-guard style for `test_git_ownership_boundary.py`) | exact |
| `tests/integration/test_worktree_lifecycle.py`, `tests/integration/test_artifact_cross_clone.py`, `tests/integration/test_write_scope_enforcement.py` (new) | test | integration | existing `tests/integration/` suite driving `advance()`/`drive()` (not read in full this session; same `drive`/`advance` entry points as `runner.py`) | role-match |
| `tests/db/test_role_executions_wip_commit_sha_schema.py` (new) | test | db (schema) | `tests/db/test_human_interactions_schema.py` | exact |

## Pattern Assignments

### `src/dark_factory/git/client.py` (new — subprocess wrapper)

**Analog:** `tests/support/subprocess_runner.py`

**Env-allowlist pattern** (lines 40-57, 60-91 — do NOT `os.environ.copy()`):
```python
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "TEMP", "TMP",
    "VIRTUAL_ENV", "PYENV_ROOT", "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
)

def child_env(pg_url: str, *, crash_after: str | None = None, ...) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env["DATABASE_URL"] = pg_url
    ...
    return env
```
Per RESEARCH Pitfall 6, `dark_factory.git.client._run_git()` should build its own minimal explicit `env` (PATH, HOME, optionally `GIT_AUTHOR_*`/`GIT_COMMITTER_*`) rather than inheriting the parent process — same discipline, git never needs `DATABASE_URL`/`GITHUB_TOKEN` so those must never be passed.

**Argument-list invocation pattern** (lines 94-116 — never `shell=True`):
```python
def spawn(args: list[str], env: dict[str, str], *, timeout: int = 120, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "dark_factory", *args],
        capture_output=True, text=True, env=env,
        cwd=str(cwd) if cwd is not None else str(REPO_ROOT),
        timeout=timeout, check=False,
    )
```
`git/client.py`'s `_run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]` should mirror this exactly: explicit arg list, explicit `cwd`, explicit `env`, `check=False` (so the caller inspects `returncode` and raises a typed `GitError`, never lets `CalledProcessError` leak raw).

---

### `src/dark_factory/git/worktree.py` (new — idempotent create/reuse/remove)

**Analog:** `src/dark_factory/artifacts/paths.py`

**Idempotent-creation pattern** (lines 27-37):
```python
def run_root(repo_root: Path, run_id: UUID) -> Path:
    return repo_root / ".dark-factory" / "runs" / str(run_id)

def ensure_run_tree(root: Path) -> None:
    """... Re-running on an existing tree is not an error (ART-01)."""
    for child in ("input", "artifacts", "verification", "logs"):
        (root / child).mkdir(parents=True, exist_ok=True)
```
`ensure_worktree(main_repo_root, run_id, base_branch) -> Path` should follow the identical "compute the deterministic path, check existence, only act if missing" idiom (RESEARCH Pitfall 4): check `Path(worktree_path).is_dir()` and `(worktree_path / ".git").exists()` before calling `git worktree add -b ...` — never call `add` unconditionally.

**One-shot git invocation** (RESEARCH Pattern 1, verified this session):
```bash
git -C <main-repo> worktree add -b dark-factory/run-<run_id> \
    ../dark-factory-runs/<run_id> <base_branch>
```

**Cleanup** (RESEARCH Pattern 1 / D-04):
```bash
git worktree remove --force ../dark-factory-runs/<run_id>
```

---

### `src/dark_factory/git/lifecycle.py` (new — detached-HEAD + WIP commit)

**Analog:** `src/dark_factory/orchestrator/lease.py` (typed-exception, no-DB pattern — not fully read this session, but the pattern is directly confirmed by RESEARCH: "a new typed `dark_factory.git.lifecycle.DetachedHeadError` (git-only, no DB)").

**Detached-HEAD check** (RESEARCH Pattern 2, verified):
```bash
git symbolic-ref -q HEAD
# exit 0 attached (prints refs/heads/<branch>); exit 1 detached (prints nothing)
```

**Dirty check + WIP commit** (RESEARCH Pattern 2, verified):
```bash
git status --porcelain=v1 --untracked-files=all   # empty stdout = clean
git add -A
git commit -m "wip(dark-factory): recover uncommitted changes from <role> attempt <N>"
git rev-parse HEAD   # -> SHA to persist as role_executions.wip_commit_sha
```

**Error-shape analog** — `ArtifactError` raised by `collect_role_artifacts` and caught in `runner.py::_run_current_role` (see below) is the exact model for `DetachedHeadError`: a plain typed exception, no DB writes inside the raising module (`artifacts/validation.py`, `WR-01` constraint).

---

### `src/dark_factory/git/diff.py` (new — artifact commit + PR-bound diff)

**Analog:** `src/dark_factory/artifacts/validation.py::collect_role_artifacts` (pure function returning writer specs, no DB — pattern confirmed by `runner.py`'s call-site shape at lines 552-563).

**Artifact-content commit** (RESEARCH Pattern 3, D-09, verified):
```bash
git add -A -- .dark-factory/runs/<run_id>/
git commit -m "chore(dark-factory): <ROLE> artifacts (run <run_id>)"
```

**PR-bound diff, artifact-excluded** (RESEARCH Pattern 3, D-10, verified — `...` not `..`):
```bash
git diff <base_branch>...<working_branch> -- . ':(exclude).dark-factory'
git diff --name-only <base_branch>...<working_branch> -- . ':(exclude).dark-factory'
```

---

### `src/dark_factory/git/scope.py` (new — write_scope glob match + revert)

**Analog:** `src/dark_factory/artifacts/paths.py::resolve_under_run_root` (lines 47-66) — the T-04-01 containment-guard pattern to mirror for defense-in-depth on every diff-derived path before revert/delete:
```python
def resolve_under_run_root(root: Path, relative_path: str) -> Path:
    from dark_factory.artifacts import ArtifactPathError
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ArtifactPathError(
            f"artifact path escapes run root {resolved_root}: {relative_path!r} "
            f"resolved to {candidate}"
        )
    return candidate
```

**Zero-tolerance glob match** (RESEARCH Pattern 4, D-12/D-14 — verified `fnmatch.fnmatchcase`, NOT `pathlib.PurePath.match`):
```python
import fnmatch

def is_out_of_scope(path: str, write_scope: list[str]) -> bool:
    return not any(fnmatch.fnmatchcase(path, pattern) for pattern in write_scope)
```

**Revert, branched on HEAD membership** (RESEARCH Pitfall 2, verified):
```bash
# tracked/existing-in-HEAD path:
git restore --source=HEAD --staged --worktree -- <path>
# new/untracked path:
git restore --staged -- <path>   # if staged
git clean -f -- <path>
```

---

### `src/dark_factory/actions/builtins.py` (`ensure_clean_worktree`, `collect_diff` become real)

**Analog:** same file — the module's own established "permanent no-op vs. real dispatcher" pattern, and the docstring rule that an action never opens a `Session` (lines 7-21):
```python
def ensure_clean_worktree(ctx: ActionContext) -> None:
    """No-op until Phase 5 (GIT-01): asserts the run worktree is clean."""
    return None

def collect_diff(ctx: ActionContext) -> None:
    """No-op until Phase 5 / Phase 9: collects the role's working-tree diff."""
    return None
```
Both bodies become thin dispatchers into `dark_factory.git.*` (worktree ensure + `lifecycle.check_head`/`wip_commit_if_dirty` for the first; `diff.collect_diff` for the second) — **never** open a `Session`, never construct `RunEvent`/`RoleExecution` (guarded by `tests/unit/test_single_mutation_path.py`, see Shared Patterns below). `ActionContext` (imported from `dark_factory.actions.context`, `TYPE_CHECKING`-only import at module top, lines 25-28) supplies `run_id`, `role`, `attempt`; the action needs the worktree path derived the same way `run_root(repo_root, run_id)` is derived in `artifacts/paths.py`.

---

### `src/dark_factory/persistence/models.py` (`role_executions.wip_commit_sha`)

**Analog:** `Run.owner_token` / `Run.lock_expires_at` — the existing nullable-lease-column pattern (lines 129-132):
```python
owner_token: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)
lock_expires_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True
)
```
Add to `RoleExecution` (after `error`, before `created_at`, ~line 179):
```python
wip_commit_sha: Mapped[str | None] = mapped_column(sa.String, nullable=True)
```
NULL means "no WIP commit for this attempt" — exactly the "NULL = unclaimed" idiom already documented for the lease columns (module docstring, "Retry counters are columns, never derived (D-19)" section applies analogously here: this is a git fact, not a derived value).

---

### `src/dark_factory/persistence/mutations.py` (`RoleExecutionWrite` + `_write_role_execution`)

**Analog:** the same file's existing `RoleExecutionWrite` model (lines 96-110) and `_write_role_execution`'s update branch (lines 367-376).

**Add the field** (frozen, `extra="forbid"` — matches every other boundary model in this module):
```python
class RoleExecutionWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["insert", "update"]
    role: str
    worker: str
    status: str
    id: UUID | None = None
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    wip_commit_sha: str | None = None   # NEW — sticky, see below
```

**CRITICAL — the sticky/compare-and-set fix (RESEARCH Pattern 2, "Pitfall inside that last step").** The current update branch is a blind full overwrite:
```python
if spec.id is None:
    raise ValueError("RoleExecutionWrite(mode='update') requires id")
row = session.get(RoleExecution, spec.id, with_for_update=True)
if row is None:
    raise LookupError(spec.id)
row.status = spec.status
row.worker_session_id = spec.worker_session_id
row.result = result
row.error = error
row.updated_at = func.now()
```
Adding `wip_commit_sha` the same blind way would let the *later* completion-time `RoleExecutionWrite(mode="update", ...)` call in `runner.py` (line ~632, which never mentions `wip_commit_sha`) silently null out the SHA a mid-attempt update just set. Required fix — compare-and-set, never clear:
```python
if spec.wip_commit_sha is not None:
    row.wip_commit_sha = spec.wip_commit_sha
```
This is the one line that makes D-07 correct instead of a silent data-loss bug (A2 in RESEARCH's Assumptions Log).

---

### `migrations/versions/0005_wip_commit_sha.py` (new)

**Analog:** `migrations/versions/0003_pause_resume_lease.py` (lines 92-96, 99-101) — direct structural match:
```python
op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))
```
becomes:
```python
"""wip commit sha -- role_executions.wip_commit_sha

Revision ID: 0005_wip_commit_sha
Revises: 0004_artifacts
Create Date: 2026-09-14
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0005_wip_commit_sha"
down_revision: str | Sequence[str] | None = "0004_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "role_executions", sa.Column("wip_commit_sha", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("role_executions", "wip_commit_sha")
```
Single nullable column, no server default, no backfill — verify `down_revision` against whatever the actual latest head is (`0004_artifacts` per RESEARCH; confirm at plan time it hasn't moved).

---

### `src/dark_factory/config/loader.py` (`write_scope` validation)

**Analog:** the same file's existing `ConfigError`-raising checks — e.g. the instructions-path escape guard (lines 135-140):
```python
instr_path = (role_path.parent / rd.instructions).resolve()
if not instr_path.is_file() or not instr_path.is_relative_to(root):
    raise ConfigError(
        f"{role_path}: instructions file not found under the repo root: "
        f"{instr_path}"
    )
```
`RolePermissions.write_scope` (lines 62-67) already exists:
```python
class RolePermissions(BaseModel):
    """``permissions:`` on a role -- stored in the snapshot, enforced in Phase 5."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    write_scope: list[str] = Field(default_factory=list)
```
Add a `@model_validator` (or an explicit loop in `load_effective_config`) that raises `ConfigError` for a malformed pattern — per RESEARCH A3, "malformed" = absolute (leading `/`) or containing `..` or empty string (there is no `fnmatch` syntax-error class to validate against). Follow the exact "raise `ConfigError` before `create_run`" fail-loud convention this module already uses everywhere else — never defer the check to diff time.

---

### `.dark-factory/roles/DEVELOPMENT.yaml` / `.dark-factory/roles/QA.yaml` (`write_scope` patterns)

**Analog:** `DEVELOPMENT.yaml` itself (lines 23-24) already names this exact phase:
```yaml
permissions:
  write_scope: []
```
Per D-12, change to real glob patterns, e.g.:
```yaml
permissions:
  write_scope: ["src/**"]     # DEVELOPMENT.yaml
permissions:
  write_scope: ["tests/**"]   # QA.yaml
```
`BA.yaml` / `ARCHITECTURE.yaml` keep `write_scope: []` unchanged (D-14 zero-tolerance is the *intended* value there, not a placeholder to fill in).

---

### `src/dark_factory/orchestrator/runner.py` (wiring point)

**Analog:** the same file's existing D-09 schema-violation catch inside `_run_current_role` (lines 547-563) — this is the exact shape D-08 (detached HEAD) and D-13 (write-scope violation) must reuse:
```python
artifact_writes: list[ArtifactReferenceWrite] = []
if signal is Signal.ROLE_COMPLETED:
    try:
        artifact_writes = collect_role_artifacts(
            run_dir, node.name, latest.id,
            list(role_def.get("outputs", [])), list(result.artifacts),
        )
    except ArtifactError as exc:
        signal = Signal.ROLE_FAILED
        outcome = {**outcome, "error": str(exc)}
```
And the `_run_hooks` closure that currently has no failure seam (lines 510-525):
```python
def _run_hooks(hook_phase: Literal["before", "after"]) -> None:
    for action_name in role_def.get(hook_phase, []):
        action_registry.get(action_name)(ActionContext(...))

_run_hooks("before")
if latest.status == _ROLE_RESUMING:
    ...
```
Per RESEARCH's "Recommended shape" (Pattern 2): wrap `_run_hooks("before")` in `try/except DetachedHeadError`, on catch skip straight to synthesizing `signal = Signal.ROLE_FAILED` and falling into the existing `elif signal is Signal.ROLE_FAILED:` branch (lines 587-600) — reuses `EventType.ROLE_FAILED` / `EventType.RUN_FAILED`, no new failure pathway (D-08). For the WIP-commit case, after a successful `_run_hooks("before")`, do a read-only `git rev-parse HEAD` and, if it differs from the attempt's previously-stored `wip_commit_sha`, issue one extra `apply_transition` self-transition call (mirroring `_enter_role`'s `next_status == expected_status == state.status` shape at lines 392-445) carrying `RoleExecutionWrite(mode="update", ..., wip_commit_sha=<sha>)`.

**Final completion-time update site** (line ~623-646) is the one that must *not* clear `wip_commit_sha` — it currently builds `RoleExecutionWrite(mode="update", id=latest.id, role=latest.role, worker=latest.worker, status=re_status, worker_session_id=..., result=..., error=...)` with no `wip_commit_sha` argument; the sticky compare-and-set fix in `mutations.py` (above) is what makes leaving it unset here safe.

---

## Shared Patterns

### WR-01 — actions never open a database session
**Source:** `src/dark_factory/actions/builtins.py` module docstring (lines 6-21) + enforced by `tests/unit/test_single_mutation_path.py`
**Apply to:** `src/dark_factory/git/*.py` (all five new modules) and both modified `actions/builtins.py` bodies — none may construct `RunEvent`/`RoleExecution`/`HumanInteraction`/`ArtifactReference` or assign `.status`; every persistence write for this phase's new state (`wip_commit_sha`, the D-08/D-13 failure events) must funnel through `orchestrator/runner.py` calling `persistence/mutations.py::apply_transition`.
```python
# tests/unit/test_single_mutation_path.py — the AST guard every new src/ module must pass
_LIFECYCLE_CTORS = {"RunEvent", "RoleExecution", "HumanInteraction", "ArtifactReference"}
# any construction of these, or any `.status = ...` assignment, outside
# persistence/mutations.py fails test_mutations_py_is_the_sole_lifecycle_writer
```
`tests/unit/test_git_ownership_boundary.py` (new, per RESEARCH's Wave-0 gap list) should mirror this exact AST-walk style, scoped to `src/dark_factory/git/` and `actions/builtins.py`, to prove no git mutation escapes the intended module boundary (GIT-02).

### Subprocess credential-boundary discipline
**Source:** `tests/support/subprocess_runner.py` lines 40-91 (`_ENV_ALLOWLIST`, `child_env`)
**Apply to:** `src/dark_factory/git/client.py`'s `_run_git()` — explicit minimal `env`, never `os.environ.copy()`, argument-list `subprocess.run`, never `shell=True` (also guarded project-wide by `tests/unit/test_no_environ_copy.py`, referenced in `subprocess_runner.py`'s own docstring).

### Path-containment guard before any destructive operation
**Source:** `src/dark_factory/artifacts/paths.py::resolve_under_run_root` (lines 47-66), proven by `tests/unit/test_artifact_paths.py`'s T-04-01 suite
**Apply to:** `src/dark_factory/git/scope.py` — every path from `git diff --name-only` must be resolved against the worktree root and rejected if it escapes, before `git restore`/`git clean -f` acts on it.

### Fail-loud config validation before any row is created
**Source:** `src/dark_factory/config/loader.py::load_effective_config` (raises `ConfigError` throughout, e.g. lines 135-140)
**Apply to:** `write_scope` pattern validation in `config/loader.py` — malformed patterns must raise `ConfigError` at load time, never surface as a silent runtime no-match at diff time.

### Migration structure
**Source:** `migrations/versions/0003_pause_resume_lease.py` (`op.add_column`, single nullable column, no backfill, reversible `downgrade`)
**Apply to:** `migrations/versions/0005_wip_commit_sha.py`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/integration/test_worktree_lifecycle.py`, `tests/integration/test_artifact_cross_clone.py`, `tests/integration/test_write_scope_enforcement.py` | test | integration | Existing `tests/integration/` files driving `drive()`/`advance()` against a real subprocess exist (per `tests/support/subprocess_runner.py`'s docstring) but were not read in full this session — planner should locate the closest existing `tests/integration/test_*.py` for the exact fixture/assertion shape (likely built on `tests/support/config.py` + `subprocess_runner.py`) before writing these three. |
| `tests/unit/test_git_ownership_boundary.py` | test | unit (AST guard) | No git-specific AST guard exists yet — closest analog is `tests/unit/test_single_mutation_path.py`'s AST-walk technique (Shared Patterns above), which is a *technique* match, not a pre-existing git-scoped file. |

## Metadata

**Analog search scope:** `src/dark_factory/{actions,artifacts,config,domain,events,orchestrator,persistence}/`, `migrations/versions/`, `.dark-factory/roles/`, `tests/{support,unit,db}/`
**Files scanned:** 14 read in full this session (builtins.py, actions/__init__.py, mutations.py, models.py, runner.py, config/loader.py, domain/artifacts.py, artifacts/paths.py, DEVELOPMENT.yaml, test_single_mutation_path.py, events/catalog.py, subprocess_runner.py, 0003 migration, test_human_interactions_schema.py) + 1 partial (test_artifact_paths.py)
**Pattern extraction date:** 2026-09-14
