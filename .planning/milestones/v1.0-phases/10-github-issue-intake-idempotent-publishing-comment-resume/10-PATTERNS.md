# Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume - Pattern Map

**Mapped:** 2026-09-26
**Files analyzed:** 14 (create/modify)
**Analogs found:** 12 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/dark_factory/github/client.py` (new) | service (external-API wrapper) | request-response | `src/dark_factory/git/client.py` | exact (same "one thin subprocess/API wrapper per external system" role) |
| `src/dark_factory/github/__init__.py` (new) | utility (error hierarchy) | — | `src/dark_factory/git/__init__.py` | exact |
| `src/dark_factory/input/loaders.py` (`_load_github`, `load()`) | service (loader/transform) | request-response | `_load_spec` in same file | exact (sibling loader in same dispatch dict) |
| `src/dark_factory/orchestrator/runner.py` (publish step insertion) | controller (orchestration step) | event-driven / CRUD | `run_quality_gate` call site, same file (lines ~1106-1170) | exact (identical terminal-role post-worker insertion point) |
| `src/dark_factory/orchestrator/runner.py` (`ROLE_NEEDS_INPUT` clarification-comment posting) | controller (orchestration step) | event-driven | `ROLE_NEEDS_INPUT` branch, same file (lines 1387-1406) | exact |
| `src/dark_factory/orchestrator/publish.py` (new, `run_publish_step`) | service | CRUD / request-response | `src/dark_factory/orchestrator/quality_gate.py` (`run_quality_gate`) | exact (same "orchestrator-only step, no role_executions row, plain function call from runner.py" shape) |
| `src/dark_factory/webhook/app.py` (new) | route/controller (new process) | request-response | none in-repo (first non-CLI process) | no analog — see below |
| `src/dark_factory/webhook/resolve.py` (new) | service (resolution/lookup) | transform | `src/dark_factory/orchestrator/answers.py` (`submit_answer`'s pre-check reads) | role-match |
| `src/dark_factory/persistence/models.py` (`Run.published_commit_sha`, `HumanInteraction.clarification_comment_id`/`github_comment_id`) | model | CRUD | `Run.pr_number`/`pr_url`, `RoleExecution.wip_commit_sha`, same file | exact |
| `src/dark_factory/persistence/mutations.py` (`HumanInteractionWrite` new fields; `apply_transition` new `run_fields`/`PublishFieldsWrite` param) | model/service (write-spec + mutation path) | CRUD | `RoleExecutionWrite.wip_commit_sha` + its `patch`-mode handling | exact |
| `src/dark_factory/config/repo_config.py` (`RepositoryConfig.github_owner`/`github_repo`) | config | CRUD | `RepositoryConfig.base_branch`, same file | exact |
| `src/dark_factory/config/settings.py` (`Settings.github_webhook_secret`) | config | CRUD | `Settings.github_token`, same file | exact |
| `src/dark_factory/events/catalog.py` (`PUBLISH_STARTED`, `PR_CREATED`, `PUBLISH_FAILED`) | config (enum catalog) | event-driven | Phase 9's `QUALITY_GATE_*` block, same file | exact |
| `migrations/versions/000X_github_publishing_columns.py` (new) | migration | batch | most recent Alembic revision under `migrations/versions/` (Phase 5/9 WIP-commit-sha / gate-iteration column migrations) | exact |
| `tests/support/fake_github.py` (new) | test double | request-response | `tests/support/fake_cli.py` (shared fake-CLI generator) / `tests/support/fake_artifacts.py` | role-match |

## Pattern Assignments

### `src/dark_factory/github/client.py` (service, request-response)

**Analog:** `src/dark_factory/git/client.py` (full file, 118 lines — read in one pass)

**Module docstring / framing pattern** (lines 1-14):
```python
"""The one subprocess wrapper for the ``git`` binary (GIT-02, T-05-01, T-05-04,
T-05-10, T-05-11).
...
The child environment is built by comprehension over an explicit allowlist;
the parent process environment is never duplicated wholesale (T-05-04) --
this is precisely how a database URL or a GitHub token would reach a
subprocess that has no business seeing one.
"""
```
Copy this framing for `github/client.py`'s own docstring: "the one `githubkit` wrapper for issue fetch / comment post / PR create (D-03)". State plainly which credential (`Settings.github_token`) is the only one that ever reaches this module, and that it is never logged (mirrors the "no DATABASE_URL, no GITHUB_TOKEN" allowlist framing).

**Error hierarchy pattern** — mirror `src/dark_factory/git/__init__.py`'s `GitCommandError`/`GitPushError`-style typed exceptions: define `GitHubApiError` (base), plus narrow subclasses only if a call site needs to distinguish outcomes (e.g. a `MissingWorkerCredentialError`-style absent-token error, per Settings.md precedent at `config/settings.py` docstring lines 70-80 — "absence only surfaces as a typed error ... when a role actually tries to invoke").

**Function signature convention** (mirrors `run_git`, lines 74-117): one function per external call shape, explicit keyword-only arguments, an explicit `timeout`, raising a typed error on failure rather than letting the underlying SDK's raw exception propagate uncaught:
```python
def run_git(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 120,
    env_extra: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    ...
    if check and result.returncode != 0:
        raise GitCommandError(tuple(args), result.returncode, result.stderr, cwd=cwd)
    return result
```
Apply this shape to `fetch_issue(owner, repo, issue_number)`, `create_comment(owner, repo, issue_number, body)`, `create_pull_request(owner, repo, title, head, base, body)`, `find_pull_request_for_branch(owner, repo, head)` — each wraps one `githubkit.GitHub(...).rest.*` call, catches the SDK's own exception, and raises `GitHubApiError` with the same "captured stderr/response redacted before surfacing" discipline `push_working_branch` uses (see below).

**Credential handling pattern** (`push_working_branch`, `git/diff.py:230-289`, read via non-overlapping range lines 200-289):
```python
The token reaches git **only** through ``GIT_ASKPASS`` and the
call-scoped :data:`GIT_PUSH_TOKEN_ENV_VAR` -- never as a subprocess
argument and never embedded in the remote URL, both of which are
visible to any co-resident process via ``ps`` and tend to be echoed
verbatim in git's own failure output (T-05-21).
...
if token is None:
    return None
```
For `github/client.py`, the equivalent discipline is: build `githubkit.GitHub(settings.github_token.get_secret_value())` once per call (or once per process, cached), never pass the raw token string into any exception message or log line; on `settings.github_token is None`, raise a typed `MissingGitHubCredentialError` at the point of use (mirrors `anthropic_api_key`'s absence-as-typed-error precedent, `config/settings.py` docstring lines 70-80) rather than crashing on a bare `None`-dereference.

**Error redaction pattern** (`git/diff.py:264-275`, same read range):
```python
The push subprocess call is retried up to 3 times with capped
exponential backoff on a :class:`~dark_factory.git.GitCommandError` --
...
the captured stderr is passed through
:func:`~dark_factory.events.redaction.redact` ... before it is folded into a
raised :class:`~dark_factory.git.GitPushError`
```
Every `GitHubApiError` message built from an SDK exception's response body must pass through `dark_factory.events.redaction.redact` with `Settings.known_secret_values()` before it is raised — the same defense-in-depth `push_working_branch` already applies, since a GitHub API error response could theoretically echo back request headers.

---

### `src/dark_factory/input/loaders.py` — `_load_github` implementation (service, request-response)

**Analog:** `_load_spec` in the same file (lines 62-93) — the closest sibling loader (reads external content, builds `NormalizedTask`, raises `UnresolvableSourceError` on failure).

**Full current stub** (lines 96-112, already in context — no re-read needed):
```python
def _load_github(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError(
        "github: sources are not supported until Phase 10 (issue intake)"
    )


_LOADERS: dict[SourceKind, Callable[[str], NormalizedTask]] = {
    SourceKind.TEXT: _load_text,
    SourceKind.SPEC: _load_spec,
    SourceKind.GITHUB: _load_github,
}


def load(kind: SourceKind, locator: str) -> NormalizedTask:
    """Dispatch to the loader registered for ``kind`` and return its task."""
    return _LOADERS[kind](locator)
```

**Core transform pattern to copy** (from `_load_spec`, lines 62-93):
```python
def _load_spec(locator: str) -> NormalizedTask:
    ...
    if not resolved.is_file():
        raise UnresolvableSourceError(f"spec: file not found: {resolved}")

    body = resolved.read_text(encoding="utf-8").strip()
    if not body:
        raise UnresolvableSourceError(f"spec: file is empty: {resolved}")

    first_line = body.splitlines()[0]
    title = _strip_heading_marker(first_line)[:_TITLE_MAX_LEN]
    return NormalizedTask(
        source_kind="spec",
        source_ref=str(resolved),
        title=title,
        body=body,
        metadata={},
    )
```
`_load_github(locator, *, repository=None)` follows the identical shape: validate the locator (issue number), fetch via `GitHubClient.fetch_issue(owner, repo, issue_number)`, raise `UnresolvableSourceError` on a not-found/network error (mirrors "file not found"/"file is empty" refusals), and build `NormalizedTask(source_kind="github", source_ref=f"{owner}/{repo}#{issue_number}", title=issue.title, body=issue.body, metadata={"owner": owner, "repo": repo, "issue_number": issue_number})` — per RESEARCH.md's Open Question 2 recommendation, populate `metadata` with owner/repo/issue_number since it is the field the webhook resolver later queries against.

**Dispatch-signature extension** — RESEARCH.md Pattern 1 gives the exact before/after signatures verified against this file; thread `repository: Mapping[str, Any] | None = None` through `load()` and each loader (existing loaders accept and ignore the new kwarg — no signature break for `_load_text`/`_load_spec`'s call sites or tests).

---

### `src/dark_factory/orchestrator/publish.py` (new) — service, CRUD/request-response

**Analog:** `src/dark_factory/orchestrator/quality_gate.py` (`run_quality_gate`, `QualityGateResult`, `write_quality_gate_result` — read lines 1-80 plus the module docstring)

**Module framing pattern to copy** (lines 1-19):
```python
"""The independent quality gate (D-01, D-09, D-10, D-11; GATE-01..04).

Once the pipeline's terminal role's own attempt transitions to
``ROLE_COMPLETED`` with a PASS ``verdict.json``, ``orchestrator/runner.py``
calls :func:`run_quality_gate` directly -- a plain function call, never
through ``ToolRegistry`` (D-01: the gate is an orchestrator-only step, with
no ``WorkerRegistry`` entry, no role config and no ``role_executions`` row of
its own).
"""
```
`orchestrator/publish.py`'s docstring should state the identical shape: "the publish step (GIT-03/GIT-04/GIT-05), called directly from `orchestrator/runner.py`'s terminal-role block immediately after `QUALITY_GATE_PASSED`, a plain function call, never through `ToolRegistry`, no role_executions row of its own."

**Result-model pattern** (from `QualityGateResult`, a `computed_field`-based PASS/FAIL fold — same file, lines that follow the excerpt above): define `PublishResult` with `pr_number: int | None`, `pr_url: str | None`, `published_commit_sha: str | None`, `error: str | None` as plain fields (never hand-set a derived "success" flag; if a computed status is needed, use `computed_field` exactly as `QualityGateResult.status` does).

**Idempotency-check-before-acting pattern** — this is RESEARCH.md's Pattern 3 (already codebase-grounded via `git/worktree.py:29-34`'s `working_branch_name` and D-06's three-way DB check). Structure `run_publish_step` as: (1) fast DB-flag check (`Run.published_commit_sha`, `Run.pr_number` already set → return early, no API call), (2) commit/push via existing `commit_run_artifacts`/`push_working_branch` (`git/diff.py`, already wired at `runner.py:1176-1188` — reuse verbatim, do not duplicate), (3) GitHub-side existing-PR check via `GitHubClient.find_pull_request_for_branch` before calling `create_pull_request` (the crash-safety net named in RESEARCH.md Pitfall 1).

---

### `src/dark_factory/orchestrator/runner.py` — publish-step insertion (controller, event-driven)

**Analog:** the quality-gate call site in the same file (lines 1071-1170, already read in full above — do not re-read).

**Exact insertion-point pattern to copy** (lines 1127-1148):
```python
if gate_result.status is VerdictStatus.PASS:
    gate_events.append(
        EventWrite(
            type=EventType.QUALITY_GATE_PASSED,
            payload={"role": node.name, "path": gate_path, "exit_codes": exit_codes},
        )
    )
else:
    gate_events.append(
        EventWrite(type=EventType.QUALITY_GATE_FAILED, payload={...})
    )
    signal, counter_increments, bounce_error = _bounce_or_fail(...)
```
Insert the publish step as a new `if gate_result.status is VerdictStatus.PASS:` sibling block, appending `EventType.PUBLISH_STARTED` before calling `run_publish_step(...)`, then `EventType.PR_CREATED` or `EventType.PUBLISH_FAILED` depending on outcome — mirroring the `gate_events` list-append discipline verbatim (never a separate event list; append into the same ordered list the gate already builds, so "role completed, then gate ran, then publish ran" stays one linear audit trail, matching the existing comment at lines 1366-1368: "Audit order: the role finished, then the gate ran (if it ran), then the run bounced").

**Push-token retrieval pattern** already in this file (lines 1176-1188, already in context):
```python
settings = get_settings()
push_token = (
    settings.github_token.get_secret_value()
    if settings.github_token is not None
    else None
)
push_working_branch(work_dir, working_branch=state.working_branch, token=push_token)
```
Reuse this exact `get_settings()` + `SecretStr`-unwrap-only-at-point-of-use pattern for constructing the `GitHubClient` inside `run_publish_step` — never pass a raw `str` token further than one call frame.

---

### `src/dark_factory/orchestrator/runner.py` — `ROLE_NEEDS_INPUT` clarification-comment posting (controller, event-driven)

**Analog:** the `ROLE_NEEDS_INPUT` branch itself, same file (lines 1387-1406, already read above).

**Exact pattern to extend**:
```python
elif signal is Signal.ROLE_NEEDS_INPUT:
    re_status = _ROLE_WAITING_HUMAN
    re_result = outcome
    re_error = None
    events = [
        EventWrite(type=EventType.QUESTION_CREATED, payload={"role": node.name, "questions": list(result.questions)}),
        EventWrite(type=EventType.RUN_PAUSED, payload={"role": node.name}),
    ]
    human_interaction = HumanInteractionWrite(
        mode="ask",
        role_execution_id=latest.id,
        question="\n".join(result.questions),
    )
```
D-08's clarification-comment posting is additive here: when `state.workflow`/`normalized_task` indicates a GitHub-sourced run (`source_kind == "github"`), call `GitHubClient.create_comment(owner, repo, issue_number, body=f"**Dark Factory needs input:**\n\n{question_text}")` *before* constructing `human_interaction`, then thread the returned comment id into a new `HumanInteractionWrite(clarification_comment_id=...)` field (mirrors `RoleExecutionWrite.wip_commit_sha`'s "captured mid-flow, passed into the write-spec model" shape below). D-05's "check `clarification_comment_id` before posting" guard belongs here too, for the resume-after-crash case (a `RESUMING` attempt that already posted must not double-post).

---

### `src/dark_factory/persistence/models.py` — new columns (model, CRUD)

**Analog:** `RoleExecution.wip_commit_sha` and `Run.pr_number`/`pr_url` — same file, lines 133-134 and 180-188 (already read above, no re-read).

**Exact column-declaration pattern to copy**:
```python
# Run
pr_number: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
pr_url: Mapped[str | None] = mapped_column(sa.String, nullable=True)
```
```python
# RoleExecution
wip_commit_sha: Mapped[str | None] = mapped_column(sa.String, nullable=True)
```
Add `Run.published_commit_sha: Mapped[str | None] = mapped_column(sa.String, nullable=True)` immediately alongside `pr_number`/`pr_url`, with a docstring comment in the same voice as the `wip_commit_sha` comment (lines 180-187) explaining it is distinct from `wip_commit_sha` (WIP-recovery-specific) and written at most once by the publish step, patch-mode. Add `HumanInteraction.clarification_comment_id: Mapped[int | None]` and `HumanInteraction.github_comment_id: Mapped[int | None]` (both `sa.BigInteger` — GitHub comment ids exceed 32-bit range) alongside the existing `question`/`answer` columns (lines 270-271), following the same nullable, no-default shape.

---

### `src/dark_factory/persistence/mutations.py` — write-spec + `apply_transition` extension (model/service, CRUD)

**Analog:** `RoleExecutionWrite.wip_commit_sha` + its `patch`-mode handling (module docstring lines 1-38 and `RoleExecutionWrite` class lines 97-123, both already read in full).

**Exact write-spec pattern to copy** (lines 113-123):
```python
class RoleExecutionWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: Literal["insert", "update", "patch"]
    role: str
    worker: str
    status: str
    id: UUID | None = None
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    wip_commit_sha: str | None = None
```
Extend `HumanInteractionWrite` (lines 137-155, already read) with `clarification_comment_id: int | None = None` and `github_comment_id: int | None = None`, following the identical `frozen=True, extra="forbid"`, all-optional-except-mode shape.

**`apply_transition`'s fixed-keyword-surface pattern** (lines 253-267, already read in full) — RESEARCH.md's Open Question 1 recommends, and this pattern map concurs, a new typed `PublishFieldsWrite(pr_number: int | None, pr_url: str | None, published_commit_sha: str | None)` parameter on `apply_transition`, following the exact naming/`frozen=True`/`extra="forbid"` convention every other `*Write` model in this file already uses (`RoleExecutionWrite`, `EventWrite`, `HumanInteractionWrite`, `ArtifactReferenceWrite`) — **not** a generic `Mapping[str, Any]` (that would violate the project's stated preference, per the Open Question's own recommendation, and per this file's established one-typed-model-per-write-target convention).

**Redaction discipline reminder** (module docstring lines 29-33, already read):
```
Redaction (``dark_factory.events.redaction.redact``) is applied *inside* this
module immediately before each ``session.add`` / attribute assignment, at the
single call site, so no caller can persist an unredacted JSONB payload.
```
`clarification_comment_id`/`github_comment_id`/`published_commit_sha`/`pr_url` are numeric/URL identifiers, not free text, so they do not need `redact()` — but any new `EventWrite` payload built around them (e.g. `{"pr_url": pr_url}`) still passes through the existing single redaction call site automatically; no new special-casing is needed there.

---

### `src/dark_factory/config/repo_config.py` — `RepositoryConfig` extension (config, CRUD)

**Analog:** `RepositoryConfig.base_branch`, same file, lines 64-69 (already read in full — 109-line file, one read covers everything).

**Exact pattern to copy**:
```python
class RepositoryConfig(BaseModel):
    """``repository:`` -- the target repo's Git conventions."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    base_branch: str = "main"
```
Add `github_owner: str | None = None` and `github_repo: str | None = None` as sibling fields, same `frozen=True, extra="forbid"` model, defaulting to `None` (optional — a repo not using GitHub intake/publishing needs no config change, mirroring `PublishingConfig.create_pr`'s "stored now, gates PR creation in Phase 10" precedent already in this file at lines 89-94).

---

### `src/dark_factory/config/settings.py` — `github_webhook_secret` field (config, CRUD)

**Analog:** `Settings.github_token: SecretStr | None = None`, same file, line 90 (already read in full excerpt above).

**Exact pattern to copy**:
```python
github_token: SecretStr | None = None
```
Add `github_webhook_secret: SecretStr | None = None` immediately alongside it. No new validator is needed — `known_secret_values()` (lines 150-167, already read) walks `model_fields` for `isinstance(value, SecretStr)` automatically, so the new field is redacted with zero additional code, exactly as D-04 states.

---

### `src/dark_factory/events/catalog.py` — three new `EventType` members (config/enum, event-driven)

**Analog:** Phase 9's `QUALITY_GATE_*`/`ROLE_BOUNCED` block, same file (lines 19-38 docstring + 68-75 enum body, already read in full — 75-line file, fully in context).

**Exact pattern to copy** (docstring precedent, lines 19-25):
```
Phase 9 adds exactly three
more -- QUALITY_GATE_STARTED, QUALITY_GATE_PASSED, QUALITY_GATE_FAILED
(D-02) -- the independent-quality-gate audit tie
``orchestrator/quality_gate.py`` / ``orchestrator/runner.py`` genuinely
write: the gate has no ``role_executions`` row of its own (D-01), so these
purpose-built events are the only durable trace that it ran at all
```
```python
# Phase 9 -- the independent quality-gate audit tie (D-02).
QUALITY_GATE_STARTED = "QUALITY_GATE_STARTED"
QUALITY_GATE_PASSED = "QUALITY_GATE_PASSED"
QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
```
Per D-07, add a new docstring paragraph attributing `PUBLISH_STARTED`/`PR_CREATED`/`PUBLISH_FAILED` to Phase 10 (correcting the misattribution named at lines 32-38, which currently says "still arrive in Phase 12"), then add the three new enum members in the identical `# Phase 10 -- ...` comment-then-members shape:
```python
# Phase 10 -- the idempotent-publishing audit tie (D-07).
PUBLISH_STARTED = "PUBLISH_STARTED"
PR_CREATED = "PR_CREATED"
PUBLISH_FAILED = "PUBLISH_FAILED"
```
Note the existing docstring's own "not-yet-reachable types are deliberately not pre-declared" rule (lines 36-38) — do not add any other Phase-12-destined member here; only these three are reached by this phase's own code.

---

### `migrations/versions/000X_github_publishing_columns.py` (new)

**Analog:** the most recent Alembic revision under `migrations/versions/` that adds a nullable column to an existing table (the Phase 5 `wip_commit_sha` migration or the Phase 9 iteration-counter migration — identify by `ls -t migrations/versions/*.py | head -1` at implementation time and follow its exact `upgrade()`/`downgrade()` `op.add_column(..., nullable=True)` shape, `down_revision` chaining, and revision-id-generation convention). Not read verbatim in this pass (no phase-10 migration exists yet to diff against) — planner should read the actual latest revision file before writing this one.

---

### `tests/support/fake_github.py` (new) — test double

**Analog:** `tests/support/fake_cli.py` (shared fake-subprocess-double generator pattern, already read lines 1-60) and `tests/support/fake_artifacts.py` (in-memory scripted-response double, role-match for "no network/subprocess, purely scripted return values").

**Pattern to follow:** `FakeGitHubClient` should be a plain Python class implementing the same method surface as `GitHubClient` (`fetch_issue`, `create_comment`, `create_pull_request`, `find_pull_request_for_branch`), constructed with scripted return values / call-recording lists (mirrors `FakeWorker`'s "scripted responses, no network" precedent named explicitly in RESEARCH.md's Wave 0 Gaps table) — never a real `githubkit.GitHub(...)` instance pointed at a stub HTTP server, matching this project's existing preference for hand-written fakes over HTTP-level stubbing at the unit/db test tiers (per RESEARCH.md: "pytest-httpx/respx ... for GitHub-integration unit tests only", i.e. not the default here).

---

## Shared Patterns

### One thin wrapper per external system
**Source:** `src/dark_factory/git/client.py` (module docstring, lines 1-14)
**Apply to:** `src/dark_factory/github/client.py`
All `githubkit` calls go through this one module; no call site elsewhere in the codebase imports `githubkit` directly (mirrors "every git subprocess call goes through `run_git`").

### Infrastructure credentials as explicit `SecretStr` `Settings` fields, unwrapped only at point of use
**Source:** `src/dark_factory/config/settings.py:88-97`, `src/dark_factory/orchestrator/runner.py:1178-1183`
**Apply to:** `github/client.py`, `orchestrator/publish.py`, the `ROLE_NEEDS_INPUT` comment-posting addition, `webhook/app.py`
```python
settings = get_settings()
push_token = (
    settings.github_token.get_secret_value()
    if settings.github_token is not None
    else None
)
```
Never `os.environ.copy()`; never pass a raw token string beyond the one call frame that needs it.

### One mutation path — every persisted-identifier write goes through `apply_transition`/`create_run`
**Source:** `src/dark_factory/persistence/mutations.py` (module docstring, lines 1-38); enforced by `tests/unit/test_single_mutation_path.py`
**Apply to:** `orchestrator/publish.py`, `orchestrator/runner.py`'s clarification-comment addition, `webhook/resolve.py`
No new module may construct a `RoleExecutionWrite`/`HumanInteractionWrite`/write to `Run.pr_number`/`published_commit_sha` outside `apply_transition`'s call sites in `orchestrator/`.

### Persisted identifiers checked before acting (idempotency)
**Source:** D-06 (CONTEXT.md), RESEARCH.md Pattern 3, `git/diff.py`'s WIP-recovery precedent (Phase 5)
**Apply to:** `orchestrator/publish.py` (PR creation), `orchestrator/runner.py`'s clarification-comment posting (D-05's `clarification_comment_id` check), `webhook/resolve.py` (D-05's `github_comment_id` dedup)
Fast DB-flag check first; external-system-state check as the crash-safety net before any create-type API call.

### Narrow, purpose-built `EventType`s claimed by the phase that does the work
**Source:** `src/dark_factory/events/catalog.py` (module docstring, Phase 9 precedent)
**Apply to:** `events/catalog.py`'s three new members (D-07)

### Error redaction before any external-error message is raised/logged
**Source:** `src/dark_factory/git/diff.py:264-275` (`push_working_branch`'s redact-before-raise), `dark_factory.events.redaction.redact`
**Apply to:** `github/client.py`'s `GitHubApiError` construction, `webhook/app.py`'s error responses (never echo the raw signature-verification failure detail or a captured payload back to the caller)

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/dark_factory/webhook/app.py` | route/controller | request-response | First non-CLI, non-worker-subprocess deployable process in the codebase — no existing HTTP-server code to pattern-match. Follow RESEARCH.md's Code Examples (`githubkit.webhooks.verify`/`parse`) and Security Domain section (V4/V5 controls) directly; structurally, model the route handler's error-first-then-parse-then-resolve ordering on `submit_answer`'s own precondition-check-before-lease-claim discipline (`orchestrator/answers.py:83-98`, already read in full) even though it isn't itself a webhook. |

## Metadata

**Analog search scope:** `src/dark_factory/{git,orchestrator,persistence,config,events,input}/`, `tests/support/`
**Files scanned:** `input/loaders.py`, `git/client.py`, `git/diff.py` (lines 200-289), `orchestrator/answers.py`, `orchestrator/runner.py` (lines 1040-1440), `orchestrator/quality_gate.py` (lines 1-80), `persistence/models.py` (lines 90-290), `persistence/mutations.py` (lines 1-320), `config/repo_config.py` (full), `config/settings.py` (lines 70-169), `events/catalog.py` (full), `tests/support/fake_cli.py` (lines 1-60)
**Pattern extraction date:** 2026-09-26
