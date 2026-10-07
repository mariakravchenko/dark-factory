---
status: resolved
trigger: "G-11-3: `Unit and contract tiers` CI step fails in real GitHub Actions (no DATABASE_URL configured, by design) because 12 tests across 4 files construct a bare `Settings()` somewhere in their call path, which requires `database_url`/`database_url_direct` and raises `pydantic_core.ValidationError`."
created: 2026-10-01T00:00:00Z
updated: 2026-10-07T00:00:00Z
resolved: 2026-10-07T00:00:00Z
follow_up_sessions:
  - claude-cli-test-spawns-real-binary-with-key-present
  - log-sink-conditional-override-unpinned
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

bug_class: Bohrbug — fully deterministic once the three AND-conditions hold; reproduced 3/3 with an identical 12-test failure set.
status: RESOLVED (2026-10-07) — human-confirmed. The fix set was already applied
by plan 11-09 while this session was paused; this resume VERIFIED it rather than
re-applying it. All 12 node ids pass under CI's own sanitized conditions, the
revert-mutant reproduces the original failures exactly, and the recurrence
guard's positive control proves the harness is not passing vacuously. The
human-verify checkpoint was answered "Confirmed + both follow-ups" on
2026-10-07, closing this session and opening two follow-ups (see
`follow_up_sessions` in the frontmatter).

hypothesis (CONFIRMED): A three-condition AND. (1) A production frame calls the
process-global `get_settings()` on a branch the unit test actually reaches;
(2) the test supplies no settings override for that frame; (3) the process has
neither `DATABASE_URL`/`DATABASE_URL_DIRECT` in env nor a readable `./.env`.
Removing any one condition makes the symptom vanish — proven by control runs.
Three production sinks account for all 12; the 4 offending test files are the
only unit-tier files that adopted NEITHER of the two 14-site-strong established
settings-override idioms.

test: (a) reproduced from a `.env`-free CWD with the two vars unset — exact 12;
(b) control with fake `DATABASE_URL` in the same CWD — 43/43 pass;
(c) sibling-branch control — passing siblings in the same files take the arm
that never reaches the `get_settings()` call.
expecting: all three confirmed. See Evidence.

next_action: NONE — session closed. Archived to
`.planning/debug/resolved/ci-unit-tier-settings-validation-g-11-3.md` with a
knowledge-base entry. Two follow-ups were opened from this session's incidental
findings and are the only remaining work:
`claude-cli-test-spawns-real-binary-with-key-present` (billable real `claude`
CLI call from a unit test when `ANTHROPIC_API_KEY` is present) and
`log-sink-conditional-override-unpinned` (the SINK A conditional is correct but
pinned by no test, because a pattern rule masks the exact-value path).
HISTORICAL NOTE ON RESUME: the file's `fix: NOT APPLIED` was stale — a survey of
the tree on resume found every recommended change already present in source
(plan 11-09 applied them after this session was paused), so the resume verified
rather than re-applied, and changed no source.

reasoning_checkpoint:
  hypothesis: "12 unit tests fail because a production frame on a conditionally-taken branch calls the process-global get_settings(), the test injects no settings override, and CI has no DATABASE_URL and no .env — all three simultaneously."
  confirming_evidence:
    - "Reproduced the exact 12-failure set (and only those 12) from a .env-free CWD with both vars unset; `--tb=native` frame aggregation names exactly 3 production sinks: logging.py:37 (x5), publish.py:272 (x6), runner.py:1685 (x1)."
    - "Control: identical command with fake DATABASE_URL/DATABASE_URL_DIRECT exported -> 43 passed, 0 failed. Condition (3) is necessary."
    - "Sibling-branch control inside test_publish_idempotency.py: the 3 failing tests use `_install_git_spies` (commit returns a SHA) with `published_commit_sha` unset -> publish.py:269 is True -> reaches line 272. The 3 passing siblings use `_install_failing_git_spies` with `published_commit_sha=_COMMIT_SHA` -> takes the else arm -> never reaches 272. Condition (1) is necessary."
    - "Inventory: 11 unit test files + 3 tests/support helpers already apply Idiom A (setenv DATABASE_URL + get_settings.cache_clear) or Idiom B (monkeypatch.setattr(module, 'get_settings', ...)). The 4 offending files apply neither. Condition (2) is a consistency gap, not a novel problem."
  falsification_test: "If condition (1) were false, the failures would be file-shaped (whole files red) rather than branch-shaped. They are branch-shaped: in each file only the tests on one specific arm fail. If condition (3) were false, the control run with fake DB URLs would still have failed. Neither falsifier fired."
  fix_rationale: "Not applicable — diagnose-only mode. Scope table in Resolution distinguishes the test-only fixes from the two production seam inconsistencies."
  blind_spots:
    - "`runner.py:1415` (the push-token read after commit_run_artifacts) is a FOURTH sink on the same `_run_current_role` path test_clarification_comment.py already drives; it did not fire only because commit_run_artifacts returned None (the fake worker wrote no artifacts). A fix that patches only line 1685 leaves it armed."
    - "Did not audit `git/diff.py:314`, `workers/cli_runtime.py:250`, `input/loaders.py:185`, `cli.py:250`, `orchestrator/lease.py:204`, `persistence/engine.py:66` for unit-tier reachability beyond observing that no currently-collected unit test reaches them unguarded."
    - "Did not verify behaviour under pytest-randomly or `-p xdist`: `get_settings` is `lru_cache(maxsize=1)`, so a differently-ordered run in which an Idiom-A test populates the cache first could mask some of the 12. CI's observed count matched exactly, so ordering did not matter there."
  candidate_causes:
    - "code (test-infrastructure): 4 Phase-10 test files adopted neither established settings-override idiom — the dominant cause for 11 of 12."
    - "code (production): `run_publish_step` already takes an injected `known_secrets` parameter but reaches back to the global `get_settings()` for the push token in the same function; `_run_current_role` has four injection seams but three un-injected `get_settings()` calls."
    - "config: `Settings.model_config` uses `env_file=\".env\"` — a CWD-relative path — so the repo's git-ignored `.env` silently satisfies both required fields on every local run. This is the MASKING mechanism, not the defect."
    - "environment: the GitHub Actions `ubuntu-latest` runner has no agent CLIs on PATH, which is the only reason two `tests/integration/*_live.py` modules did not ALSO abort collection in CI (see Evidence entry 7)."
    - "process/gate: no gate ran the unit tier under a sanitized environment. 11-06's guard sweeps `dark_factory` package imports and `--collect-only` for three named modules — by construction it cannot catch a runtime `get_settings()` on a conditionally-taken branch inside `tests/`."
  and_gate: "YES — three conditions must hold simultaneously (see hypothesis). This is why the blast radius is 12 tests and not 840, why the distribution is branch-shaped rather than file-shaped, and why every local run has been green since Phase 10. Any single-cause framing (e.g. 'the tests are wrong' or 'CI is misconfigured') is incomplete and would produce an under-scoped fix."

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: The `Unit and contract tiers` CI step (marker-selected `unit or contract`, deliberately run with NO `DATABASE_URL` configured) passes with no database-related failures — the same no-database constraint G-11-1 established for the webhook module, generalized to every test this tier selects.

actual: 12 tests failed with `pydantic_core.ValidationError: 2 validation errors for Settings` (database_url, database_url_direct — both "Field required") on a real GitHub Actions run (https://github.com/mariakravchenko/dark-factory/actions/runs/36850439597):
  - tests/unit/test_clarification_comment.py::test_raising_create_comment_still_pauses_with_no_id_recorded (traceback: tests/unit/test_clarification_comment.py:404 -> _drive_needs_input (:175) -> runner_module._run_current_role (src/dark_factory/orchestrator/runner.py:1685) -> get_settings() (src/dark_factory/config/settings.py:206) -> Settings())
  - tests/unit/test_publish_idempotency.py::test_nothing_recorded_commits_pushes_checks_then_creates_in_order
  - tests/unit/test_publish_idempotency.py::test_existing_pr_on_a_different_head_branch_is_not_adopted
  - tests/unit/test_publish_idempotency.py::test_no_client_call_besides_find_or_create[point-a-nothing-recorded]
  - tests/unit/test_publish_step_unit.py::test_create_pr_true_returns_pushed_sha_and_pr_identifiers_from_one_call
  - tests/unit/test_publish_step_unit.py::test_pr_body_links_the_source_issue_and_carries_no_execution_scoped_data
  - tests/unit/test_publish_step_unit.py::test_create_pull_request_raising_github_api_error_does_not_re_raise
  - tests/unit/test_webhook_signature.py::test_missing_github_token_logs_loudly_at_construction
  - tests/unit/test_webhook_signature.py::test_missing_github_webhook_secret_logs_loudly_at_construction
  - tests/unit/test_webhook_signature.py::test_fully_configured_settings_log_no_startup_warning
  - tests/unit/test_webhook_signature.py::test_missing_dispatch_github_token_logs_a_warning_not_an_error
  - tests/unit/test_webhook_signature.py::test_injected_authenticated_login_skips_the_startup_check
  828 passed, 12 failed, 374 deselected, 1 warning in 36.81s.

errors: pydantic_core._pydantic_core.ValidationError: 2 validation errors for Settings / database_url: Field required [type=missing, input_value={}, input_type=dict] / database_url_direct: (same)

reproduction: Run `uv run pytest -q -m "unit or contract"` in an environment with NO .env file and NO DATABASE_URL/DATABASE_URL_DIRECT set. A local run will NOT reproduce it if `.env` exists at the repo root (pydantic-settings resolves `env_file=".env"` relative to CWD).

started: Discovered during UAT test 1 for phase 11 (verifying gap-closure plan 11-06's fix for G-11-1), on 2026-10-01, the first time this branch was ever pushed to real GitHub Actions CI.

## Eliminated
<!-- APPEND only - prevents re-investigating -->

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-10-01T00:00:00Z
  checked: src/dark_factory/config/settings.py
  found: `Settings` has `model_config = SettingsConfigDict(env_file=".env", ...)`; `database_url: SecretStr` and `database_url_direct: SecretStr` are REQUIRED (no default). `get_settings()` is `functools.lru_cache(maxsize=1)`-wrapped and constructs a bare `Settings()`.
  implication: `env_file=".env"` is a RELATIVE path, resolved against the process CWD. Any local run from the repo root silently satisfies both required fields from the git-ignored `.env`; CI has no `.env`, so the two required fields are missing and construction raises. This is the exact invisibility mechanism. Also: the `lru_cache` means test ordering matters — if any earlier test in the same process populates the cache with a valid Settings, later tests inherit it.

- timestamp: 2026-10-01T00:05:00Z
  checked: Reproduction. Ran the four failing modules with `-m "unit or contract"` from a scratch CWD (no `.env`) with `env -u DATABASE_URL -u DATABASE_URL_DIRECT -u GITHUB_TOKEN`, using `-c <repo>/pyproject.toml` so markers/rootdir resolve.
  found: `12 failed, 31 passed` — byte-for-byte the same 12 node ids CI reported, same `ValidationError`.
  implication: Faithful local reproduction obtained with zero mutation of the working tree (no `.env` rename). The gap is fully deterministic (Bohrbug), not flaky.

- timestamp: 2026-10-01T00:08:00Z
  checked: `--tb=native` frame aggregation across all 12 failures (`grep 'File ".../src|tests' | uniq -c`).
  found: Exactly THREE distinct production sinks, 12/12 accounted for, all terminating at `config/settings.py:206 get_settings -> Settings()`:
    (A) `src/dark_factory/logging.py:37` `_configured_level()` reached from `logging.py:58` `configure_logging()` reached from `tests/support/log_sink.py:30` `real_log_sink()` — 5 failures (all of `test_webhook_signature.py`'s).
    (B) `src/dark_factory/orchestrator/publish.py:272` `run_publish_step` (the push-token read) — 6 failures (3 in `test_publish_idempotency.py` + 3 in `test_publish_step_unit.py`).
    (C) `src/dark_factory/orchestrator/runner.py:1685` `_run_current_role` (the `except GitHubError` fail-soft redaction in the NEEDS_INPUT arm) — 1 failure (`test_clarification_comment.py`).
  implication: These are RUNTIME calls on conditionally-taken branches, NOT import-time. Confirms the investigation guidance's framing and explains why 11-06's import-time guard could not have caught any of them.

- timestamp: 2026-10-01T00:11:00Z
  checked: Sink A in detail — `tests/support/log_sink.py` + `src/dark_factory/logging.py`.
  found: `real_log_sink()` calls `configure_logging(logger_factory=...)`. `configure_logging` has a `logger_factory` injection seam but NO settings seam, and reads settings TWICE: `_configured_level()` (line 37, fires at configure time) and `_redaction_processor` (line 28, fires per log event). The 5 failing tests in `test_webhook_signature.py` are exactly the 5 that call `real_log_sink()`; all of them already inject `settings_factory=lambda: _FakeSettings(...)` into `build_app`, so the author DID reason about settings injection — `real_log_sink()` is an independent, invisible SECOND settings consumer in the same test body.
  implication: Sink A is test-support-layer, fixable without touching production. Fixing only `_configured_level`'s caller would be insufficient — `_redaction_processor` needs valid settings too, so the override must cover the whole `real_log_sink()` context.

- timestamp: 2026-10-01T00:14:00Z
  checked: Sink B in detail — `run_publish_step`'s signature vs its body, and the runner call site.
  found: `run_publish_step(*, run_id, state, work_dir, client, create_pr, known_secrets: Mapping[str, str])` ALREADY takes a settings-derived value as an injected parameter — `known_secrets`, used at lines 331 and 358 for redaction. The caller (`runner.py:1340-1348`) computes it from `gate_settings = get_settings()` (`runner.py:1271`) and passes `gate_settings.known_secret_values()`. Yet line 272 inside the same function reaches back to the global `get_settings()` for `settings.github_token`.
  implication: Sink B is a genuine PRODUCTION design inconsistency, not merely a test gap. The function's own contract already says "settings-derived values arrive as parameters"; the token read is the one value that violates it. The caller already holds a `Settings` object (`gate_settings`) at the moment of the call, so threading a `push_token: str | None` (or a `settings`) parameter requires no new plumbing and makes all 6 tests pass with zero mocking.

- timestamp: 2026-10-01T00:17:00Z
  checked: Sink C in detail — `_run_current_role`'s signature and all its `get_settings()` calls.
  found: `_run_current_role` already has FOUR keyword injection seams (`action_registry`, `repo_root`, `tool_registry`, `github_client_factory`) but no settings seam, and calls the global `get_settings()` at THREE places: 1271 (quality-gate timeout + known_secrets), 1415 (push token after `commit_run_artifacts`), 1685 (clarification-failure redaction).
  implication: Line 1415 is a FOURTH armed landmine on the very path `test_clarification_comment.py` already drives — it did not fire only because `commit_run_artifacts` returned `None` (that test's fake worker writes no artifacts). Any fix must cover all three `_run_current_role` sinks, not just 1685, or the next unit test that drives `_run_current_role` with artifacts re-opens the gap.

- timestamp: 2026-10-01T00:21:00Z
  checked: Inventory of established settings-override idioms across the unit tier (`grep 'setattr(.*"get_settings"|setenv("DATABASE_URL"|get_settings.cache_clear' tests/unit tests/support`).
  found: TWO idioms, already applied at 14 sites:
    Idiom A (env + cache clear): `monkeypatch.setenv("DATABASE_URL", <fake>)` [+ `DATABASE_URL_DIRECT`] + `get_settings.cache_clear()` before AND after — `test_log_redaction.py`, `test_persistence.py`, `test_git_push.py`, `test_settings.py`, `test_shell_execute.py`, `test_worker_env.py`, `test_git_worktree.py`, `test_claude_code_worker.py`, `test_copilot_worker.py`, `test_hermes_worker.py`, and `tests/support/fake_{claude,copilot,hermes}_cli.py`.
    Idiom B (module-attribute patch): `monkeypatch.setattr(<module>, "get_settings", lambda: <fake>)` — `test_load_github.py:40` and `tests/conftest.py:309` (`use_fake_secrets` -> `mutations.get_settings`).
    `tests/conftest.py` also ships `fake_settings` (a real `Settings` built with `_env_file=None` + fake values) and `use_fake_secrets`, but `use_fake_secrets` patches ONLY `persistence.mutations.get_settings` — it is not a general-purpose override, and nothing is autouse.
    The 4 offending files reference NONE of `get_settings` / `fake_settings` / `use_fake_secrets`.
  implication: This is an "established pattern was not applied consistently" root cause for 11 of the 12 (Sinks A and C), layered on a production seam inconsistency for Sink B. There is no autouse fixture and no shared helper that makes the property automatic, so each new test file has to rediscover the requirement.

- timestamp: 2026-10-01T00:25:00Z
  checked: Phase provenance of the 4 offending files vs the pattern-applying files, from module docstrings.
  found: ALL FOUR offenders are Phase 10 — `test_publish_idempotency.py` (plan 10-02), `test_clarification_comment.py` (10-03), `test_webhook_signature.py` (10-04), `test_publish_step_unit.py` (10-06). The SAME phase's plan 10-01 (`test_load_github.py`) DID apply Idiom B. Three of the four offenders' docstrings open with an explicit "No database:" claim.
  implication: The oversight has a precise shape — "No database" was read as "opens no PostgreSQL connection" (true for all four: they never connect), when the binding constraint is "`Settings` CONSTRUCTION requires `DATABASE_URL` to be present in the environment". Requiring a URL string is not the same as requiring a reachable server. Plan 10-01 got it right; 10-02/03/04/06 did not carry it forward.

- timestamp: 2026-10-01T00:29:00Z
  checked: Control run (falsification of condition 3) — identical command, same `.env`-free CWD, with `DATABASE_URL`/`DATABASE_URL_DIRECT` exported as fake values.
  found: `43 passed, 0 failed`.
  implication: Condition (3) is necessary AND is the sole masking mechanism. Nothing about the tests or production code changed between the two runs.

- timestamp: 2026-10-01T00:32:00Z
  checked: Sibling-branch control (falsification of condition 1) inside `test_publish_idempotency.py`.
  found: The 3 FAILING tests use `_install_git_spies` (its `_commit` always returns `_COMMIT_SHA`) with `published_commit_sha` unset -> `publish.py:269 if state.published_commit_sha is None` is True -> `artifact_sha is not None` -> line 272 `get_settings()`. The PASSING siblings (`test_pushed_but_unrecorded_pr_adopts_an_existing_pull_request`, `test_pushed_but_unrecorded_pr_creates_when_none_found`, `..._besides_find_or_create[point-b-pushed-unrecorded]`, `test_create_pr_false_short_circuits...`) use `_install_failing_git_spies` and/or set `published_commit_sha=_COMMIT_SHA` -> take the `else` arm or the `create_pr=False` early return -> never reach 272.
  implication: The failure distribution is BRANCH-shaped, not file-shaped. Condition (1) is necessary. This also means test-count is a poor proxy for exposure: the arm, not the file, decides.

- timestamp: 2026-10-01T00:36:00Z
  checked: Full `-m "unit or contract"` tier over all of `tests/` from the sanitized CWD, with agent CLIs removed from PATH to mirror the hosted runner.
  found: `12 failed, 818 passed, 1 skipped, 374 deselected` — the 12 failing node ids and the `374 deselected` count both match CI exactly.
  implication: Scope is exactly 12 under CI conditions — no further hidden runtime failures in this tier. The fix target set is closed.

- timestamp: 2026-10-01T00:40:00Z
  checked: LATENT SIBLING (found incidentally) — the same full-tier run WITH `claude`/`copilot` present on PATH.
  found: `Interrupted: 2 errors during collection` — `tests/integration/test_claude_code_live.py` and `tests/integration/test_copilot_live.py` raise the SAME `ValidationError` at MODULE IMPORT time via `test_claude_code_live.py:35 -> tests/support/live_runtime.py:108 skip_reason -> :89 credential_missing -> get_settings()`. `skip_reason` checks `binary_missing` FIRST and returns early, so on the GitHub-hosted runner (no agent CLIs on PATH) `get_settings()` is never reached — which is the only reason CI reported 12 test failures instead of a total collection abort.
  implication: A second, strictly worse instance of the identical class, currently masked by a THIRD condition (agent CLIs absent from the runner). `ci.yml:56-60` explicitly contemplates provisioning those credentials/CLIs later; the moment anyone does, the entire `unit or contract` selector aborts at collection with 0 tests run. This is also invisible to 11-06's guard, which sweeps `dark_factory` package modules via `pkgutil.walk_packages` and never imports anything under `tests/`. Note `credential_missing`'s docstring deliberately reads through `get_settings()` "so an operator's `.env` file counts" — the behaviour is intentional; only its unconditional reachability is the defect.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  A three-condition AND (no single cause is sufficient):

  (1) PRODUCTION — three frames call the process-global `get_settings()` on
      conditionally-taken branches that unit tests legitimately reach:
      `logging.py:37` + `:28` (via `configure_logging`, which has a
      `logger_factory` seam but no settings seam);
      `publish.py:272` (the push-token read inside `run_publish_step`, which
      already receives the settings-derived `known_secrets` as a parameter —
      so the token is the one value violating the function's own contract);
      `runner.py:1685` (plus un-fired siblings at `:1271` and `:1415` inside
      `_run_current_role`, which already has four other injection seams).

  (2) TEST INFRASTRUCTURE — the four Phase-10 test files that reach those
      branches adopted NEITHER of the two settings-override idioms already in
      use at 14 sites across the unit tier (Idiom A: `setenv DATABASE_URL` +
      `get_settings.cache_clear()`; Idiom B: `monkeypatch.setattr(module,
      "get_settings", ...)`). Three of the four docstrings assert "No
      database" — correct about never opening a PostgreSQL connection, wrong
      about `Settings` CONSTRUCTION requiring `DATABASE_URL` to be *present*.
      Requiring a URL string is not the same as requiring a reachable server.
      The same phase's plan 10-01 applied Idiom B correctly; 10-02/03/04/06
      did not carry it forward. Nothing is autouse and no shared helper makes
      the property automatic, so each file must rediscover it.

  (3) ENVIRONMENT — `Settings.model_config` sets `env_file=".env"`, a
      CWD-relative path. Every local run from the repo root silently satisfies
      both required fields from this repo's git-ignored `.env`; the hosted
      runner has neither the vars nor a `.env`. This is the MASKING
      mechanism — the reason the defect survived Phase 10, Phase 11 and
      gap-closure plan 11-06 untouched until this branch's first real CI push.

  Remove any one condition and all 12 failures disappear (proven by control
  runs). The AND structure explains the blast radius (12, not 840), the
  branch-shaped rather than file-shaped distribution, and the invisibility.

  WHY 11-06 DID NOT COVER IT: 11-06's guard proves an IMPORT-TIME property
  over the `dark_factory` package (`pkgutil.walk_packages` sweep) plus
  `--collect-only` for three named modules. By construction it cannot observe
  a `get_settings()` call that happens during test EXECUTION on a
  conditionally-taken branch, and it never imports anything under `tests/`.
  11-06 was correctly scoped to G-11-1 and is not at fault; the runtime
  analogue of its property simply never existed.

fix: |
  APPLIED — but NOT by this debug session. On resume (2026-10-06) a survey of
  the working tree found every recommended change already present in committed
  source, applied by gap-closure plan 11-09 after this session was paused. This
  session's job on resume was therefore VERIFICATION, not re-application. The
  `NOT APPLIED` text below is the original diagnose-only recommendation,
  preserved verbatim for provenance; see `verification` for what was actually
  confirmed against the tree, and the per-item status markers added inline.

  STATUS OF EACH RECOMMENDED ITEM, as observed in the tree on resume:
    SINK B        — DONE. `run_publish_step` now takes `push_token: str | None`
                    (publish.py:127), consumed at :275. No global read remains.
    SINK C        — DONE via the test-side option (Idiom B), not a
                    `settings_factory` seam; `grep settings_factory
                    src/dark_factory/orchestrator/runner.py` returns nothing.
                    The runner's remaining `get_settings()` calls (now at
                    :1198, :1327, :1476, :1781, :1806 after drift) are covered
                    at the test boundary. The blind spot about `:1415` is
                    retired: the guard below exercises the whole tier, so an
                    un-overridden sibling would fail it.
    SINK A        — DONE. `tests/support/log_sink.py` supplies the two fake
                    vars only when absent, clears + restores the lru_cache.
    LATENT SIBLING— DONE. `tests/support/live_runtime.py:104-105` wraps
                    `get_settings()` in `try/except ValidationError`.
    RECURRENCE GUARD — DONE. `tests/unit/test_unit_tier_needs_no_database.py`,
                    3 tests: the sanitized full-tier child (reading the marker
                    expression out of `ci.yml` rather than restating it), the
                    stub-binary-on-PATH collection adversary for the latent
                    sibling, and the unguarded-`get_settings()` positive
                    control.

  ORIGINAL RECOMMENDATION (preserved verbatim):
  Recommended scope for the gap-closure plan, in dependency order:

  SINK B — PRODUCTION (6 failures, `publish.py:272`). Add the missing
    parameter to `run_publish_step` (e.g. `push_token: str | None`) and
    thread it from `runner.py:1340`, which already holds `gate_settings`
    and already passes `gate_settings.known_secret_values()` three lines
    later. Removes the hidden global read and makes all 6 tests pass with
    no mocking at all. This is the only change that improves production
    design rather than only the tests.

  SINK C — PRODUCTION or TEST (1 failure, `runner.py:1685`). Either add a
    `settings_factory` keyword seam to `_run_current_role` (consistent with
    its four existing seams) covering ALL THREE sites — `:1271`, `:1415`,
    `:1685` — or apply Idiom B in the test
    (`monkeypatch.setattr(runner_module, "get_settings", lambda: fake_settings)`),
    which also covers all three. Do NOT patch only `:1685`: `:1415` is armed
    on the same path and currently survives only because
    `commit_run_artifacts` returns `None` there.

  SINK A — TEST SUPPORT (5 failures, `logging.py:37`/`:28`). Prefer fixing
    the shared helper `tests/support/log_sink.py::real_log_sink` once rather
    than the 5 call sites, so every current and future caller inherits the
    property. The override must span the whole context manager (both
    `_configured_level` at configure time and `_redaction_processor` per
    event). CONSTRAINT: `tests/unit/test_log_redaction.py` deliberately sets
    its own `FAKE_LIVE_DB_URL` and asserts it is scrubbed from the sink — the
    helper must supply fake values only when the vars are ABSENT, never
    override an already-set value, or those three tests become vacuous.

  LATENT SIBLING — TEST SUPPORT (0 current failures, 2 collection aborts on
    any machine with `claude`/`copilot` on PATH).
    `tests/support/live_runtime.py:89 credential_missing` calls
    `get_settings()` at module-import time via `skip_reason`. Make the
    credential probe tolerate an unconstructible `Settings` (treat it as
    "credential missing") rather than propagating `ValidationError`. Fix this
    in the same plan: it is the same class, strictly worse (aborts the whole
    selector, 0 tests run), and `ci.yml:56-60` explicitly contemplates
    provisioning those CLIs later.

  RECURRENCE GUARD (the actual G-11-3 deliverable, the runtime analogue of
    11-06's import-time guard). A test that spawns a child `pytest -m "unit or
    contract"` with `cwd=tmp_path` (no readable `.env`) and an explicit env
    ALLOWLIST that omits `DATABASE_URL`/`DATABASE_URL_DIRECT` — reusing
    `tests/unit/test_webhook_import_needs_no_database.py`'s own
    `_ENV_ALLOWLIST` / `_sanitized_env` idiom — and asserts exit code 0. Must
    include a positive control (a throwaway test that calls `get_settings()`
    unguarded, proving the harness has teeth) mirroring that file's Test 4.
    Also sanitize PATH or assert on collection errors, so the latent sibling
    above cannot hide behind CLI absence.

verification: |
  guardrail_verdict: accepted (one signal qualified — see MUTANT 1 below)
  oracle_type: specified (the guard asserts a stated contract: the CI selector
    exits 0 under CI's own environment conditions), backed by a positive
    control that makes a vacuous pass detectable.

  SIGNAL 1 — original issue no longer occurs: PASS.
    `tests/unit/test_unit_tier_needs_no_database.py` — 3 passed in 251.63s.
    Test 1 runs the full `unit or contract` selector (read out of `ci.yml`)
    in a child with no `DATABASE_URL`/`DATABASE_URL_DIRECT` and a `tmp_path`
    CWD with no readable `.env` — exactly CI's condition. All 12 originally
    failing node ids now pass.

  SIGNAL 2 — regression test has teeth: PASS.
    Guard Test 3 (positive control) spawns a throwaway test calling
    `get_settings()` unguarded and asserts non-zero exit + `ValidationError`
    in output. It passes, so Tests 1 and 2 cannot be passing merely because
    sanitization silently stopped working.

  SIGNAL 3 — bug returns on revert: PASS (directly demonstrated).
    MUTANT 2: replaced `tests/support/log_sink.py`'s `supplied` list with
    `[]` (supply nothing — a faithful revert of the SINK A fix) and ran
    `tests/unit/test_webhook_signature.py` from a sanitized CWD. Result:
    `5 failed, 14 passed`, and the 5 are byte-for-byte the five
    `test_webhook_signature.py` node ids in this file's Symptoms block, with
    the same `pydantic_core.ValidationError`. The fix is load-bearing for the
    symptom. File restored; `git diff` over `src/` and `tests/` is empty.

  SIGNAL 4 — not a deletion-only diff: PASS. The fix set is additive —
    a new `push_token` parameter, a new `try/except ValidationError`, a new
    conditional env supply, and a new 3-test guard module.

  SIGNAL 5 — broader suite: PASS with one unrelated, pre-existing failure.
    `-m "unit or contract"` unsanitized from the repo root:
    `1 failed, 842 passed, 1 skipped, 430 deselected in 418.79s`.
    The single failure is
    `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
    — NOT a regression from this fix (which touches only `log_sink.py`,
    `publish.py`'s push token, `live_runtime.py` and test-side overrides) and
    NOT present in CI. See SIBLING FINDING below.

  MUTANT 1 — SURVIVED (honest qualification, and it CORRECTS a claim this
    file made above). Dropping the absence guard in `log_sink.py` (making the
    fake-value override unconditional) left `tests/unit/test_log_redaction.py`
    fully green — 4 passed. So this file's earlier CONSTRAINT text ("...or
    those three tests become vacuous") is WRONG as written: the tests do not
    become vacuous and, more importantly, nothing detects the clobbering.
    Mechanism, observed not inferred: `src/dark_factory/events/redaction.py:120`
    carries a PATTERN rule
    `(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s@]+@\S+` -> `[redacted:database_url]`
    that matches `FAKE_LIVE_DB_URL` regardless of `known_secrets`. The
    pattern layer therefore masks the exact-value layer for any
    postgres-shaped URL. The conditional in `log_sink.py` is still correct and
    worth keeping, but it is currently unpinned by any test, and
    `test_log_redaction.py`'s DB-URL assertions prove pattern redaction only —
    not known-secret exact-value redaction. Recorded as a test-sensitivity gap,
    not a blocker: the G-11-3 property itself is pinned by Signals 1-3.

  SIBLING FINDING (same root-cause class, opposite polarity, pre-existing).
    `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` asserts
    `worker.execute({}).status is FAILED`, relying on a comment-stated premise
    that "no ANTHROPIC_API_KEY [is] configured in this test's environment".
    It injects no settings override, so the premise is ambient. Measured both
    ways: from a sanitized CWD (no `.env`) the file is `6 passed in 0.14s`;
    from the repo root, where `.env` supplies the key, the credential gate
    OPENS and `execute({})` spawns the real `claude` CLI — the assertion fails
    and the tier takes 418.79s instead of ~37s. A unit test is making a real,
    billable external CLI call whenever a developer has credentials
    configured. This is the identical root-cause class as G-11-3 — a unit test
    whose outcome depends on ambient environment rather than an injected
    settings override — mirrored: G-11-3 broke when the environment was
    EMPTY, this breaks when it is POPULATED. CI is unaffected (no key there),
    which is why it has stayed invisible. NOT fixed here: out of G-11-3's
    scope, and the fix changes what the test proves, so it warrants its own
    GSD plan.

  HUMAN CONFIRMATION (2026-10-07). The human-verify checkpoint was answered
    "Confirmed + both follow-ups". G-11-3 is accepted as fixed and this session
    is closed. Both qualifications above were converted into their own debug
    sessions rather than being dropped, so neither relies on this archived
    record being re-read:
      - MUTANT 1 (the unpinned `log_sink.py` conditional / pattern rule masking
        the exact-value redaction path) -> `log-sink-conditional-override-unpinned`
      - SIBLING FINDING (the billable real-`claude`-CLI unit test) ->
        `claude-cli-test-spawns-real-binary-with-key-present`

  BLAMELESS POSTMORTEM. Why not caught: no gate ran the unit tier under a
    sanitized environment — 11-06's guard proves an IMPORT-TIME property over
    the `dark_factory` package and by construction cannot observe a runtime
    `get_settings()` on a conditionally-taken branch inside `tests/`. The
    masking mechanism (`env_file=".env"` resolved CWD-relative) made every
    local run green, so the absent gate cost nothing until the first real CI
    push. Guard now in place: `tests/unit/test_unit_tier_needs_no_database.py`
    (3 tests — sanitized full-tier child, stub-binary collection adversary,
    unguarded-`get_settings()` positive control).

files_changed: []
  # This session changed NO source. The fix set was applied by gap-closure
  # plan 11-09 while this session was paused; the files carrying it are:
  #   src/dark_factory/orchestrator/publish.py      (push_token parameter)
  #   tests/support/log_sink.py                     (conditional env supply)
  #   tests/support/live_runtime.py                 (ValidationError tolerance)
  #   tests/unit/test_unit_tier_needs_no_database.py (the recurrence guard)
  # The only file this session modified is this debug record.

