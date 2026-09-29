# Phase 11: One Orchestrator, Many Triggers — Cross-Machine Resume - Pattern Map

**Mapped:** 2026-09-29
**Files analyzed:** 9 (all edits/additions from CONTEXT.md D-01–D-07 and RESEARCH.md's "Recommended Project Structure")
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/dark_factory/github/client.py` (+`dispatch_workflow`, +`GitHubClient.for_dispatch`) | service (outbound API wrapper) | request-response | same file, `create_comment`/`create_pull_request`/`from_settings` (existing methods in the same class) | exact |
| `src/dark_factory/webhook/app.py` (+dispatch call in `_resolve_and_act`) | controller (webhook route handler) | event-driven → request-response | same file, `submit_answer` call block (lines 202-223) | exact |
| `src/dark_factory/config/settings.py` (+`dispatch_github_token`) | config | CRUD (field add) | same file, `github_webhook_secret: SecretStr \| None = None` field | exact |
| `tests/support/fake_github.py` (+`dispatch_workflow` method) | test fixture / fake | request-response | same file, `create_comment`/`create_pull_request` methods | exact |
| `tests/db/test_webhook_dispatches_resume.py` (NEW) | test | request-response | `tests/db/test_webhook_resolves_answer.py` | exact |
| `tests/db/test_cross_machine_resume.py` (NEW) | test | event-driven / process-boundary | `tests/integration/test_fresh_process_resume.py` | role-match (marker deviates per Pitfall 1 — stays `db`, not `integration`) |
| `tests/unit/test_settings.py` (+`dispatch_github_token` tests) | test | CRUD | same file, `github_webhook_secret` test block (lines 274-303) | exact |
| `.github/workflows/ci.yml` (comment fix + `-m` selection change) | config | batch (CI pipeline) | same file, `quality` job's `Unit and contract tiers` step | exact |
| `resume.yml` (deployer-facing reference doc content, not shipped/enforced) | config (documentation) | event-driven | none in this repo (new deployment artifact, lives in deployer's own target repo) | no analog — use RESEARCH.md's flow diagram + D-04 wording |

## Pattern Assignments

### `src/dark_factory/github/client.py` (service, request-response)

**Analog:** same file — `create_comment` (lines 206-223) and `from_settings` (lines 134-145)

**Imports pattern** (lines 46-58, already present, no new import needed beyond what's there):
```python
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from githubkit import GitHub
from githubkit.exception import GitHubException
from pydantic import BaseModel, ConfigDict
from dark_factory.events.redaction import redact
from dark_factory.github import GitHubApiError, MissingGitHubCredentialError
if TYPE_CHECKING:
    from dark_factory.config.settings import Settings
```

**Constructor-from-settings pattern to clone for `for_dispatch`** (lines 134-145):
```python
@classmethod
def from_settings(cls, settings: Settings) -> GitHubClient:
    """Build a client from ``Settings.github_token`` -- the single
    frame where the token is unwrapped from ``SecretStr``."""
    if settings.github_token is None:
        raise MissingGitHubCredentialError(
            "GITHUB_TOKEN is not configured (Settings.github_token is None)"
        )
    return cls(
        token=settings.github_token.get_secret_value(),
        known_secrets=settings.known_secret_values(),
    )
```
`GitHubClient.for_dispatch(settings)` mirrors this exactly, substituting `settings.dispatch_github_token` for `settings.github_token`, and raising the same `MissingGitHubCredentialError` when unset (research already specifies this constructor path by name).

**Core request-response pattern to clone for `dispatch_workflow`** (lines 206-223, `create_comment`):
```python
def create_comment(
    self, owner: str, repo: str, *, issue_number: int, body: str
) -> GitHubComment:
    try:
        response = self._client.rest.issues.create_comment(
            owner, repo, issue_number, body=body
        )
    except GitHubException as exc:
        self._raise_api_error(
            exc, endpoint=f"issues.create_comment {owner}/{repo}#{issue_number}"
        )
        raise  # pragma: no cover - _raise_api_error always raises
    comment = response.parsed_data
    return GitHubComment(
        id=comment.id,
        author=_comment_author(comment.user),
        body=comment.body or "",
    )
```
`dispatch_workflow` follows the identical try/except-`GitHubException`/`_raise_api_error` shape, but calls `self._client.rest.actions.create_workflow_dispatch(owner, repo, workflow_id, ref=ref, inputs={"run_id": run_id})` and, per RESEARCH.md Pattern 1, treats "did not raise" as success (endpoint returns 204 by default) rather than reading `.parsed_data`.

**Error handling pattern** (lines 147-162, `_raise_api_error` — reused unchanged, no new error-handling code needed):
```python
def _raise_api_error(self, exc: Exception, *, endpoint: str) -> None:
    status_code: int | None = None
    detail = str(exc)
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        text = getattr(response, "text", None)
        if isinstance(text, str) and text:
            detail = text
    message = redact(
        f"GitHub API call failed ({endpoint}): {detail}",
        known_secrets=self._known_secrets,
    )
    raise GitHubApiError(
        message, status_code=status_code, endpoint=endpoint
    ) from exc
```

---

### `src/dark_factory/webhook/app.py` (controller, event-driven → request-response)

**Analog:** same file, `_resolve_and_act`'s `submit_answer` block (lines 202-223)

**Exact insertion point** (verified, lines 202-223):
```python
try:
    submit_answer(
        outcome.run_id,
        outcome.answer,
        session_factory=session_factory,
        github_comment_id=outcome.github_comment_id,
    )
except (NotWaitingForHuman, NoPendingInteraction) as exc:
    _log.info(
        "webhook.issue_comment.already_resolved",
        run_id=str(outcome.run_id),
        reason=type(exc).__name__,
    )
    return _OK
except LeaseNotAcquired:
    return _RETRY_LATER
except Exception:
    _log.exception(
        "webhook.issue_comment.unexpected_error", run_id=str(outcome.run_id)
    )
    return _SERVER_ERROR
return _OK   # <-- NEW dispatch call goes immediately before this line
```

**Fail-soft pattern to clone** (from `src/dark_factory/orchestrator/runner.py`, verified lines 1657-1690, quoted in RESEARCH.md Pattern 2 — cannot be imported directly, must be re-written locally in `app.py` since `orchestrator/runner.py` is not on the webhook package's `_WEBHOOK_DIRECT_ALLOWED` import list):
```python
try:
    client = github_client_factory()
    ...
except GitHubError as exc:
    # Fail soft, never silent: the pause, the events and
    # the ``ask`` write still commit unchanged -- ...
    question_payload = {**question_payload, "clarification_comment_error": str(redact(...))}
else:
    clarification_comment_id = comment.id
```
The webhook's own new block must: (1) call `load_run_state(session_factory(), outcome.run_id)` (a pure read, already on the webhook's allowlist per `tests/unit/test_webhook_process_boundary.py::_WEBHOOK_DIRECT_ALLOWED`), (2) read `state.workflow["repository"]["github_owner"/"github_repo"]` (NOT `state.normalized_task.metadata` — see RESEARCH.md Anti-Pattern), (3) construct `GitHubClient.for_dispatch(settings_factory())`, (4) call `dispatch_workflow(...)`, (5) catch `GitHubError`, log via `_log.warning`/`_log.exception` with redacted text, and (6) still `return _OK` either way — never abort the already-committed `submit_answer` mutation.

**Module-boundary invariant this file's docstring already states** (lines 47-48, must not be violated):
```
This module -- and everything it imports -- must never reference ``advance``
or ``drive``: the receiver's only mutation is ``submit_answer`` (D-02, T-10-21).
```
The dispatch call is an outbound GitHub API call, not a call into `advance`/`drive` — safe to add, but any new import here must be checked against `tests/unit/test_webhook_process_boundary.py::_WEBHOOK_DIRECT_ALLOWED`.

---

### `src/dark_factory/config/settings.py` (config, CRUD field add)

**Analog:** same file, `github_webhook_secret` field (line 104) and its docstring block (lines 84-92)

**Exact pattern to clone**:
```python
github_webhook_secret: SecretStr | None = None
dispatch_github_token: SecretStr | None = None    # NEW — same optional-SecretStr shape
```
Add a docstring paragraph (mirroring lines 84-92's `github_webhook_secret` paragraph) explaining `dispatch_github_token` is distinct from `github_token`/`github_webhook_secret` — a dispatch-only credential, never passed to a worker subprocess. No change needed to `known_secret_values()` (lines 165-182) — its `model_fields` walk is already generic.

---

### `tests/support/fake_github.py` (test fixture, request-response)

**Analog:** same file, `create_comment` (lines 80-95) and `create_pull_request` (lines 97-116)

**Pattern to clone for a fifth scripted method**:
```python
def create_comment(
    self, owner: str, repo: str, *, issue_number: int, body: str
) -> GitHubComment:
    self.calls.append(
        (
            "create_comment",
            {
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
                "body": body,
            },
        )
    )
    self._maybe_raise("create_comment")
    return GitHubComment(id=1, author="dark-factory", body=body)
```
`dispatch_workflow(self, owner, repo, *, workflow_id, ref, run_id)` should append `("dispatch_workflow", {...})` to `self.calls`, call `self._maybe_raise("dispatch_workflow")`, and return `None` (the real method returns `None` on success per the 204 no-content contract) — add a `raises: dict[str, Exception]` entry the same way the other four do, no constructor change needed beyond that.

---

### `tests/db/test_webhook_dispatches_resume.py` (NEW test, db-tier)

**Analog:** `tests/db/test_webhook_resolves_answer.py` (578 lines — read via Grep/targeted sections recommended at plan time; not fully re-read here since the file list/scenario shape is already confirmed by RESEARCH.md's "Wave 0 Gaps" and Pitfall 3)

**Key idiom to copy** (per RESEARCH.md Pitfall 3, confirmed against `tests/conftest.py::_write_config_tree`): this new test must overwrite the generated `.dark-factory.yaml`'s `repository:` block with `github_owner`/`github_repo` set — `_write_config_tree`'s default has only `{base_branch: main}`, no owner/repo — exactly like `test_publish_step.py`/`test_ask_posts_comment.py`/`test_webhook_resolves_answer.py` already do (the "build-then-overwrite" idiom named explicitly in RESEARCH.md).

Use `build_app(session_factory=..., settings_factory=..., authenticated_login=...)`'s injection seam (already read above in `webhook/app.py`) to inject a `FakeGitHubClient`-backed dispatch, and assert `("dispatch_workflow", {...})` appears in `fake.calls` after posting a signed webhook payload through Starlette's `TestClient`.

---

### `tests/db/test_cross_machine_resume.py` (NEW test, db-tier — deliberate marker deviation)

**Analog:** `tests/integration/test_fresh_process_resume.py` (full file read above, 184 lines)

**Reusable helpers to import unchanged** (`tests/support/subprocess_runner.py`, full file read above):
```python
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    run_id_from_stdout,
    spawn,
)
```

**Two-process pattern to clone** (from `test_killed_after_first_commit_then_resumed_by_a_separate_process`, lines 54-138):
```python
p1 = spawn(
    ["run", "text:carry nothing between processes"],
    child_env(pg_url, crash_after=_CRASH_AT_FIRST_TRANSITION),
    cwd=config_root,
)
...
run_id = run_id_from_stdout(p1.stdout)
...
resume_env = child_env(pg_url)
p2 = spawn(["resume", str(run_id)], resume_env, cwd=config_root)
assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"
```
D-06's proof drives process A to a `WAITING_HUMAN`/paused state (not a crash hook this time — a real pause, e.g. via `submit_answer` or a scripted `FakeWorker` ask), deletes/resets any local worktree state between the two `spawn()` calls, then process B (`resume`) finishes it — asserting same run id, no second run created (`_count_runs`-style helper), and the local worktree/process state was genuinely discarded.

**CRITICAL marker deviation (RESEARCH.md Pitfall 1):** this file lives in `tests/db/`, not `tests/integration/`, and is marked `pytestmark = pytest.mark.db`, NOT `pytest.mark.integration` — despite spawning two real subprocesses exactly like `test_fresh_process_resume.py` does. This is a deliberate, documented deviation from the Phase 2 "subprocess ⇒ integration" convention (D-05/D-06 explicitly group this test with the `db` tier so it actually runs in CI). Include a docstring note citing D-05/D-06 explaining this, exactly as flagged in RESEARCH.md.

Compare to the analog's own marker (line 40):
```python
pytestmark = pytest.mark.integration   # <- the OLD convention; do NOT copy this line verbatim
```

---

### `tests/unit/test_settings.py` (unit test, CRUD)

**Analog:** same file — the `github_webhook_secret` test block (lines 274-303)

**Pattern to clone verbatim, substituting field name**:
```python
def test_github_webhook_secret_defaults_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    assert Settings(_env_file=None).github_webhook_secret is None


def test_known_secret_values_maps_github_webhook_secret_to_its_field_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    fake_webhook_secret = "whsec_fake0000000000000000000000000000"
    _set_env(monkeypatch, GITHUB_WEBHOOK_SECRET=fake_webhook_secret)
    known = Settings(_env_file=None).known_secret_values()

    assert known[fake_webhook_secret] == "github_webhook_secret"


def test_known_secret_values_omits_unset_github_webhook_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import Settings

    _set_env(monkeypatch)
    known = Settings(_env_file=None).known_secret_values()

    assert "github_webhook_secret" not in known.values()
```
Three sibling tests for `dispatch_github_token` (`test_dispatch_github_token_defaults_to_none`, `test_known_secret_values_maps_dispatch_github_token_to_its_field_name`, `test_known_secret_values_omits_unset_dispatch_github_token`), plus adding `"DISPATCH_GITHUB_TOKEN": None` to `_set_env`'s default-clear dict (lines 22-42) alongside `GITHUB_WEBHOOK_SECRET`/`ANTHROPIC_API_KEY`/`COPILOT_GITHUB_TOKEN`, for the same "don't depend on ambient environment" reason already documented there.

---

### `.github/workflows/ci.yml` (config, batch/CI pipeline)

**Analog:** same file — the `Unit and contract tiers` step and its preceding comment (lines 43-50)

**Current content to replace**:
```yaml
      # The `db` and `integration` tiers are deliberately excluded here:
      # tests/conftest.py's probe ladder needs a reachable PostgreSQL 17
      # (Docker, a local `initdb`, or DARK_FACTORY_TEST_DATABASE_URL) and the
      # `integration` tier drives the CLI as a real subprocess. The hosted
      # runner provides neither a Postgres 17 instance nor agent-CLI
      # credentials, so only the `unit` and `contract` tiers run here.
      - name: Unit and contract tiers
        run: uv run pytest -q -m "unit or contract"
```
Per D-05: correct the comment (GitHub-hosted `ubuntu-latest` ships Docker pre-installed, so the `db` tier now runs via testcontainers with no `services:` block; only `integration` stays excluded, for the unrelated reason that it needs agent-CLI credentials), and change the `-m` selector to `"unit or contract or db"`. Also review `timeout-minutes: 15` (line 18) per RESEARCH.md Pitfall 2 — raise it or split db-tier execution into its own step/job; treat the exact number as a post-first-CI-run calibration, not a value to guess now.

---

## Shared Patterns

### Fail-soft on `GitHubError` after an already-committed mutation
**Source:** `src/dark_factory/orchestrator/runner.py` (clarification-comment post, ~lines 1657-1690 per RESEARCH.md)
**Apply to:** `webhook/app.py`'s new dispatch call — never undo/fail the already-committed `submit_answer` mutation; catch `GitHubError`, log, still return success (`_OK`).

### One `SecretStr` `Settings` field per credential purpose
**Source:** `src/dark_factory/config/settings.py` (`github_token`, `github_webhook_secret`, `copilot_github_token` — all separate fields, none reused across purposes)
**Apply to:** `dispatch_github_token` — never conflated with `github_token`/`github_webhook_secret`, never added to `WORKER_ENV_ALLOWLIST` (`src/dark_factory/tools/env.py`, verified structurally independent per RESEARCH.md).

### Typed `githubkit` REST call, keyword-merge-into-JSON-body idiom
**Source:** `src/dark_factory/github/client.py` (`create_comment`, `create_pull_request`, `find_pull_request_for_branch` — every method funnels through `self._client.rest.<group>.<method>(...)` inside a `try`/`except GitHubException`/`self._raise_api_error(...)` block)
**Apply to:** `dispatch_workflow` — same wrapper class, same error path, no new error-handling code.

### Explicit env allowlist, never `os.environ.copy()`
**Source:** `tests/support/subprocess_runner.py::_ENV_ALLOWLIST` / `child_env`
**Apply to:** `test_cross_machine_resume.py` — reused unchanged; no new env-building code needed.

### Real OS subprocess pairs for "no local state carried over" proofs
**Source:** `tests/integration/test_fresh_process_resume.py` (full pattern: `spawn`, `run_id_from_stdout`, force-lease-expiry-style helpers, asserting run count unchanged and same run id)
**Apply to:** `test_cross_machine_resume.py` — same shape, but marked `db` not `integration` (Pitfall 1 deviation, documented).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `resume.yml` (deployer-facing reference content, D-04) | config (CI workflow, lives in deployer's own target repo) | event-driven | Not a file in this repo at all — it's documentation/reference content this phase writes (e.g. in `docs/` or a README section) describing what a deployer must add to their own repo. No existing `.github/workflows/*.yml` in this repo is a `workflow_dispatch`-triggered resume workflow to copy structurally; use RESEARCH.md's flow diagram and D-04's exact wording (checkout → install `dark-factory` → `dark-factory resume <run_id>`) as the content source instead of a codebase analog. |

## Metadata

**Analog search scope:** `src/dark_factory/github/`, `src/dark_factory/webhook/`, `src/dark_factory/config/`, `tests/support/`, `tests/db/`, `tests/unit/`, `tests/integration/`, `.github/workflows/`
**Files scanned:** 9 (all fully read, all ≤ 2000 lines, single-pass reads, no re-reads)
**Pattern extraction date:** 2026-09-29
