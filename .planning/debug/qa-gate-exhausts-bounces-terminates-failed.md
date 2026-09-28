---
status: diagnosed
trigger: "G-10-1: The real-CLI-subprocess pipeline (shipped .dark-factory.yaml config, driven via `python -m dark_factory run text:...` against a real Postgres/Neon database) never reaches PUBLISHING. It bounces QA -> DEVELOPMENT three times, exhausts retry.qa_developer_max_iterations: 3, and terminates in FAILED at QA."
created: 2026-09-28T00:00:00Z
updated: 2026-09-28T00:00:00Z
---

## Current Focus

hypothesis: |
  CONFIRMED (two independent, serial causes):

  (1) The shipped `.dark-factory.yaml` declares
      `quality_gate.commands: ["uv run pytest -q", "uv run ruff check ."]`.
      Since Phase 9 (commit 4a7a19e) those commands are actually EXECUTED, in the
      run's own worktree, once the terminal role (QA) produces a PASS verdict. The
      four failing integration tests copy that shipped config into a throwaway git
      repo that contains only `.dark-factory.yaml`, `.dark-factory/`, `.gitignore`
      and `README.md` -- no Python project and no tests. `uv run pytest -q` there
      exits **5** (pytest EXIT_NOTESTSCOLLECTED). `QualityGateResult.status`
      requires `exit_code == 0` for EVERY command, so the gate is FAIL on every
      attempt, forever. `_bounce_or_fail` then bounces QA -> DEVELOPMENT against
      `quality_gate_iterations` (cap 2): bounce, bounce, then ROLE_FAILED ->
      RUN_FAILED with `quality_gate_max_iterations_exhausted`. That is 3 QA
      attempts / 3 "QA ->" transitions on the CLI -- which is what was counted as
      "three bounces" and mis-attributed to `qa_developer_max_iterations: 3`.

  (2) LATENT, SERIAL: the same shipped `.dark-factory.yaml` sets
      `publishing.create_pr: true` but declares NO `repository.github_owner` /
      `repository.github_repo`. The moment cause (1) is fixed and the gate PASSes,
      runner.py:1309 enters the publish branch, `default_github_client_factory()`
      raises `MissingGitHubCredentialError` (no GITHUB_TOKEN in the throwaway
      repo's cwd, and `Settings.model_config.env_file=".env"` is CWD-relative) or,
      if a token happens to be inherited, `run_publish_step` returns
      `error="cannot open a pull request: repository.github_owner is not set"`.
      Either way -> PUBLISH_FAILED -> `signal = Signal.ROLE_FAILED` -> run FAILED.
      Fixing only (1) will NOT make these four tests green.

test: |
  DB-free probe reproducing runner.py's terminal-role gate step exactly
  (scratchpad/probe_gate.py): copy shipped config into a make_git_repo throwaway,
  ensure_worktree, then call run_quality_gate with the snapshot's own commands.
expecting: |
  status == FAIL with `uv run pytest -q` exit_code != 0 -> confirms cause (1).
  Falsification: plant one trivially-passing test file in the same worktree and
  re-run the same command -> exit 0 -> gate would PASS, proving nothing else
  about the worktree/fakes/artifacts/transition logic is at fault.
next_action: |
  Diagnosis complete (goal: find_root_cause_only). No fix applied. Hand the two
  root causes plus the three test-defect findings to the fix owner.

reasoning_checkpoint:
  hypothesis: |
    The QA -> DEVELOPMENT bounce loop is driven by the QUALITY GATE branch
    (`quality_gate_iterations`, cap 2), not the QA-verdict branch
    (`qa_developer_iterations`, cap 3). The gate can never pass because the
    shipped config's `uv run pytest -q` exits 5 in a throwaway repo with no tests.
  confirming_evidence:
    - "Direct execution: run_quality_gate(commands=<shipped>, cwd=<real worktree>) returned status=FAIL, `uv run pytest -q` exit_code=5, `uv run ruff check .` exit_code=0."
    - "QualityGateResult.status (quality_gate.py:117) folds PASS iff `exit_code == 0 and not timed_out` for every entry -- exit 5 is FAIL."
    - "tests/conftest.py:373 `_write_config_tree` writes `quality_gate:\\n  commands: []\\n` -- every other end-to-end test folds to PASS over ZERO commands, which is exactly why only the 4 shipped-config tests fail."
    - "Exactly the 4 reported-failing integration tests are the only tests in the suite that call `_copy_shipped_config_into` (grep-verified)."
    - "git log -S run_quality_gate -- runner.py returns exactly one commit: 4a7a19e feat(09-01). Before Phase 9 the shipped quality_gate.commands were inert config ('Stored in the snapshot this phase; executed in Phase 9' -- .dark-factory.yaml:23)."
    - "The 4 tests were last touched in edec6ac (08-04), i.e. before the gate became executable, and no Phase 9 or Phase 10 planning artifact references them."
  falsification_test: |
    Plant a single passing test file into the same worktree and re-run
    `uv run pytest -q`. If the hypothesis is right the exit code flips 5 -> 0.
    RESULT: `1 passed in 0.00s`, PYTEST_EXIT=0. Hypothesis survived.
  fix_rationale: |
    NOT APPLIED (find_root_cause_only). Direction: the defect is in the TEST
    FIXTURE, not the orchestrator -- `_copy_shipped_config_into` imports a config
    whose `quality_gate.commands` and `publishing.create_pr` are specific to the
    dark-factory repo + a real GitHub remote, into a repo that satisfies neither.
    The orchestrator behaved exactly as designed at every step.
  blind_spots: |
    - Could not re-run the real end-to-end reproduction: no PostgreSQL is
      reachable here (no Docker, no local initdb, no DARK_FACTORY_TEST_DATABASE_URL),
      so the exact bounce COUNT (2 bounces / 3 QA attempts) and the exact
      RUN_FAILED reason string (`quality_gate_max_iterations_exhausted` vs
      `qa_developer_max_iterations_exhausted`) are derived from code + the DB-free
      gate probe, not observed in a live run. This is the single highest-value
      thing for the fix owner to confirm: read the run_events rows and check for
      QUALITY_GATE_FAILED events and the RUN_FAILED payload's `counter` field.
    - `uv run ruff check .` exited 0 HERE only because a `ruff` binary was
      resolvable on the ambient PATH. On a machine without one it exits 2, so the
      gate fails for two reasons, not one. Either way the verdict is FAIL.
    - Cause (2) is proven by code read (runner.py:1309-1376, publish.py:288-307,
      github/client.py:138-141, settings.py:92-93) but not executed.
  candidate_causes:
    - "code: `_bounce_or_fail` / transition logic is wrong -- ELIMINATED, behaves exactly as documented"
    - "code: QA worker emits a FAIL verdict -- ELIMINATED, the fakes synthesize status=PASS with all criteria PASS (workers/fake.py:298-307)"
    - "config: shipped `.dark-factory.yaml` declares repo-specific gate commands + `publishing.create_pr: true` with no github_owner/github_repo -- CONFIRMED CONTRIBUTING (both causes)"
    - "environment: the throwaway worktree has no Python project/tests and no GITHUB_TOKEN -- CONFIRMED CONTRIBUTING"
    - "data/fixture: `_copy_shipped_config_into` copies the gate + publishing config verbatim with no override -- CONFIRMED, the actionable defect"
  and_gate: |
    YES -- two independent conditions must BOTH be resolved. Cause (1) (gate can
    never pass) currently masks cause (2) (publish can never succeed). They are
    serial, not alternative: a fix that only neutralises the gate will surface
    PUBLISH_FAILED -> ROLE_FAILED and the run will still terminate FAILED. Both
    share one upstream condition -- the shipped config being imported wholesale
    into an environment that cannot satisfy its repo-specific declarations.

## Symptoms

expected: |
  A full unrestricted `uv run pytest -q` sweep (unit, contract, db, integration)
  passes cleanly. Tests that drive `python -m dark_factory run <source>` as a real
  subprocess against the shipped `.dark-factory.yaml` + `.dark-factory/roles/*.yaml`
  configuration should reach terminal status COMPLETED (exit 0), matching the
  FakeWorker-only path.

actual: |
  6 failures out of 1169 collected. Four share an identical pattern: the run
  bounces QA -> DEVELOPMENT repeatedly, exhausts a retry budget, and terminates
  FAILED at QA; the subprocess exits 1 instead of 0.

  Failing tests:
  - tests/integration/test_artifact_scope_enforcement.py::test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts (POSITIVE CONTROL)
  - tests/integration/test_real_pipeline_zero_config.py::test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script (simplest repro)
  - tests/integration/test_artifact_cross_clone.py::test_fresh_clone_of_the_working_branch_carries_every_artifact_byte
  - tests/integration/test_role_reassignment_sc2.py::test_reassigned_roles_reach_completed_identically_to_all_fake

  Fifth:
  - tests/db/test_manual_check_loop04_adjacency.py::test_a_one_role_pipeline_fails_immediately_never_bounces
    AssertionError: RUN_FAILED payload does not name the adjacency reason: {'role': 'QA'}

  Sixth:
  - tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site
    assert 'redact(' not in runner_src

errors: |
  No tracebacks for the QA-bounce failures - subprocess exits 1 with terminal
  status FAILED at QA after exhausting a retry budget.

reproduction: |
  uv run pytest -q tests/integration/test_real_pipeline_zero_config.py::test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script
  against a real reachable PostgreSQL DATABASE_URL.

  DB-FREE equivalent for the root cause (used in this session):
  scratchpad/probe_gate.py -- copies the shipped config into a make_git_repo
  throwaway, ensure_worktree, then calls run_quality_gate with the snapshot's own
  commands. Needs no database.

started: |
  Discovered during Phase 10 UAT (/gsd-verify-work 10), Test 1. Latent since
  Phase 9 (commit 4a7a19e, feat(09-01) "independent quality gate runs after a PASS
  QA verdict") -- the four affected tests were last touched in edec6ac (08-04),
  before the gate became executable, and the integration tier was never fully
  re-run after Phase 9.

## Eliminated

- hypothesis: "The QA worker emits a FAIL verdict.json, driving the qa_developer_iterations bounce loop (cap 3)"
  evidence: |
    `_synthesize_machine_artifact` (src/dark_factory/workers/fake.py:298-307) builds
    verdict.json with every criterion `result=PASS` and `status=PASS`. The same
    function is what the fake claude/copilot/hermes CLIs call (tests/support/fake_cli.py
    `_DECLARED_OUTPUTS_STEP` imports `synthesize_artifact_content` directly), so all
    four roles across all three runtimes emit a PASS verdict. A FAIL verdict
    short-circuits BEFORE the gate (runner.py:1248-1266); the observed shape has the
    gate running. Also arithmetically: qa_developer cap 3 yields 3 bounces + a 4th QA
    attempt; the observed CLI shows 3 "QA ->" transitions total, which is
    quality_gate cap 2 (2 bounces + 1 FAILED).
  timestamp: 2026-09-28T00:00:00Z

- hypothesis: "A write-scope violation (knowledge-base pattern phase4-artifact-commit-bugs) flips QA's signal -- e.g. `uv run pytest` leaving .pytest_cache in the worktree, outside QA's `write_scope: [\"tests/**\"]`"
  evidence: |
    Directly observed in the probe: `uv run pytest -q` DOES create `.pytest_cache/`
    in the worktree, but `git status --porcelain` in that worktree afterwards is
    EMPTY -- pytest writes `.pytest_cache/.gitignore` containing `*`, so git never
    sees it. `enforce_write_scope` therefore observes zero changed paths and cannot
    fire. Separately, a WriteScopeViolation produces ROLE_FAILED directly (runner.py
    :1490-1504 clears counter_increments and bounce_reason), never the observed
    multi-bounce loop.
  timestamp: 2026-09-28T00:00:00Z

- hypothesis: "The bounce/transition logic in _bounce_or_fail or lifecycle.transition is defective"
  evidence: |
    `_bounce_or_fail` (runner.py:314-341) is correct and matches its docstring:
    bounce iff `bounce_target is not None and current_value < cap`. With
    quality_gate_iterations starting at 0 (persistence/models.py:147-149,
    server_default 0) and cap 2: 0<2 bounce, 1<2 bounce, 2<2 false -> ROLE_FAILED
    with `quality_gate_max_iterations_exhausted`. Exactly the observed shape. No
    defect.
  timestamp: 2026-09-28T00:00:00Z

- hypothesis: "The failure is caused by the external-runtime fakes (claude/copilot/hermes) or by GitHub/webhook integration"
  evidence: |
    The gate step runs AFTER all four roles have completed and produced a PASS
    verdict -- the fakes did their job. The gate is a plain orchestrator function
    call spawning `uv`, with no worker and no GitHub involvement. Reproduced
    standalone with zero workers and zero GitHub in the DB-free probe.
  timestamp: 2026-09-28T00:00:00Z

## Evidence

- timestamp: 2026-09-28T00:00:00Z
  checked: .planning/debug/knowledge-base.md (Phase 0 known-pattern lookup)
  found: |
    One prior entry -- phase4-artifact-commit-bugs. Its "Why not caught" names the
    class: "a config field changes from inert to enforced and existing fixtures
    declaring the permissive-LOOKING value are not swept".
  implication: |
    The SPECIFIC cause did not match (that was write_scope; this is quality_gate),
    and the write_scope hypothesis it suggested was actively eliminated. But the
    CLASS matched exactly and predicted where to look: `.dark-factory.yaml:23`
    literally says "Stored in the snapshot this phase; executed in Phase 9."

- timestamp: 2026-09-28T00:00:00Z
  checked: .dark-factory.yaml (shipped config)
  found: |
    workflow.roles = [BA, ARCHITECTURE, DEVELOPMENT, QA] -- QA is the TERMINAL role.
    quality_gate.commands = ["uv run pytest -q", "uv run ruff check ."]
    retry: qa_developer_max_iterations: 3, quality_gate_max_iterations: 2
    publishing.create_pr: true
    repository: base_branch: main   <-- NO github_owner, NO github_repo
  implication: |
    QA being terminal means the gate runs in the same step as QA. Two separate
    bounce budgets exist; the reported "3" must be disambiguated. And
    `create_pr: true` with no github_owner/github_repo is a second problem.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Direct execution of runner.py's gate step, DB-free
    (scratchpad/probe_gate.py): make_git_repo -> copy the 3 shipped config paths
    -> commit -> load_effective_config -> ensure_worktree -> run_quality_gate.
  found: |
    snapshot quality_gate.commands = ['uv run pytest -q', 'uv run ruff check .']
    snapshot retry = {'qa_developer_max_iterations': 3, 'quality_gate_max_iterations': 2}
    work_dir contents = ['.dark-factory', '.dark-factory.yaml', '.git', '.gitignore', 'README.md']

    === GATE RESULT ===
    status = FAIL
      command='uv run pytest -q'    exit_code=5  timed_out=False  stdout='\nno tests ran in 0.00s\n'
      command='uv run ruff check .' exit_code=0  timed_out=False  stdout='All checks passed!\n'
                                                                  stderr='warning: No Python files found under the given path(s)\n'

    leftover files: .pytest_cache added; `git status --porcelain` -> EMPTY
  implication: |
    ROOT CAUSE (1) CONFIRMED BY DIRECT OBSERVATION. The gate is deterministically
    FAIL in these tests' worktree. pytest exit 5 = EXIT_NOTESTSCOLLECTED (there are
    no tests in a repo containing only README.md + config). Also eliminates the
    write-scope hypothesis: git sees nothing.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Falsification -- planted `tests/test_trivial.py` (one passing assert) into the
    SAME worktree and re-ran the SAME command.
  found: "`1 passed in 0.00s`, PYTEST_EXIT=0"
  implication: |
    The gate command flips 5 -> 0 with a single collectible test. Nothing about the
    worktree, the git worktree mechanics, the env allowlist, the fakes, the
    artifacts or the transition code contributes -- the sole input is "does this
    repo have any tests". Hypothesis survived its falsification test.

- timestamp: 2026-09-28T00:00:00Z
  checked: src/dark_factory/orchestrator/quality_gate.py:113-122
  found: |
    `QualityGateResult.status` = PASS iff `all(entry.exit_code == 0 and not
    entry.timed_out for entry in self.commands)`. A zero-length commands list folds
    to PASS with no empty-list special case.
  implication: |
    Non-zero for ANY reason (including pytest's "no tests collected" 5) is FAIL.
    And an EMPTY commands list is PASS -- which is the differential below.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Differential -- why every OTHER end-to-end test reaches COMPLETED.
    tests/conftest.py:365-376 `_write_config_tree`.
  found: |
    `_write_config_tree` writes `quality_gate:\n  commands: []\n` plus
    `retry:\n  qa_developer_max_iterations: 3\n  quality_gate_max_iterations: 2\n`.
    Grep-verified: the ONLY tests in the suite that call `_copy_shipped_config_into`
    (and therefore execute the real gate commands) are exactly the four reported
    failures -- test_real_pipeline_zero_config.py, test_artifact_scope_enforcement.py,
    test_artifact_cross_clone.py, test_role_reassignment_sc2.py.
  implication: |
    Clean pass/fail split with a single discriminating variable. Every green
    end-to-end test folds to PASS over ZERO gate commands; every red one executes
    the real ones. This is the sibling-control proof of single-cause for cause (1).

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    `git log -S "run_quality_gate" --oneline -- src/dark_factory/orchestrator/runner.py`
    and `git log --oneline -5 -- tests/integration/test_real_pipeline_zero_config.py`
  found: |
    Gate execution landed in exactly one commit: 4a7a19e `feat(09-01): independent
    quality gate runs after a PASS QA verdict`. The four affected tests were last
    touched in edec6ac `test(08-04)` -- one phase EARLIER. No Phase 9 or Phase 10
    planning artifact references any of the four test names (only 10-UAT.md does,
    reporting the failure).
  implication: |
    PRE-EXISTING since Phase 9, not a Phase 10 regression. Latent for two phases
    because the integration tier was never fully re-run after the gate went live.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    runner.py:1289-1376 (the gate-PASS arm), publish.py:288-307,
    github/client.py:134-145, config/settings.py:92-96, .dark-factory.yaml:33-36
  found: |
    On gate PASS the runner enters `if publishing_config.get("create_pr", True)`.
    The shipped config sets `create_pr: true`. `default_github_client_factory()` ->
    `GitHubClient.from_settings(get_settings())` raises `MissingGitHubCredentialError`
    when `settings.github_token is None`; `Settings.model_config.env_file=".env"` is
    CWD-RELATIVE and the CLI's cwd is the throwaway repo, which has no `.env`. Even
    with a token inherited from the parent env, `run_publish_step` returns
    `error="cannot open a pull request: repository.github_owner is not set"` --
    the shipped `.dark-factory.yaml` has only `repository.base_branch: main`.
    Either path sets `signal = Signal.ROLE_FAILED` (runner.py:1372).
    Note: tests/conftest.py `_write_config_tree` was changed in 10-06 to default
    `publishing.create_pr` to FALSE specifically to avoid breaking ~24 db-tier
    tests -- but the four integration tests copy the SHIPPED config and were never
    covered by that mitigation.
  implication: |
    ROOT CAUSE (2). Serial/latent: currently masked by cause (1). Fixing only the
    gate will move the failure from QA-gate-exhaustion to PUBLISH_FAILED, and the
    run will still end FAILED with exit 1.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Failure 5 -- tests/db/test_manual_check_loop04_adjacency.py (git status: `??`,
    untracked) vs runner.py:1538-1555.
  found: |
    The test asserts `"no_earlier_role_to_bounce_to" in str(run_failed.payload)`.
    Production DELIBERATELY does not put that string in the RUN_FAILED payload:
    `_EXHAUSTION_REASON_TO_COUNTER` (runner.py:308-311) maps ONLY the two
    exhaustion reasons, and the comment at runner.py:1543-1545 states verbatim
    "A no-earlier-role-to-bounce-to failure ... the lookup simply misses and the
    payload stays `{"role": node.name}`". The adjacency reason IS persisted -- on
    the ROLE_FAILED event's `error` field (runner.py:1556-1563) and on
    `role_executions.error` -- just not on RUN_FAILED. The test reads the wrong
    event. This file is the untracked throwaway flagged as a Blocker in
    .planning/STATE.md and its own docstring says to delete it after running.
  implication: |
    INDEPENDENT test-only defect. Not a production bug and not related to the
    QA-bounce issue. Assertion targets the wrong event type.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Failure 6 -- tests/integration/test_redaction_interactions.py:306
    (`assert "redact(" not in runner_src`) vs the two real `redact(` call sites in
    runner.py.
  found: |
    runner.py has exactly two `redact(` call sites, BOTH added legitimately in
    Phase 10 and both on the GitHub path, neither on the human-interaction path:
      - line 1331 (10-06, cb2f325): redacts a GitHubError string before it enters
        `PublishResult.error`.
      - line 1683 (10-03, dc4d36b): redacts a GitHubError string before it enters
        the QUESTION_CREATED payload's `clarification_comment_error` key.
    The test's own docstring scopes the claim narrowly -- "the runner never scrubs
    on the pause path" -- but the assertion is a blanket token search over the
    whole 1825-line file.
  implication: |
    INDEPENDENT stale structural guard, over-broad by construction. The single-
    mutation-path redaction contract for human interactions is NOT violated
    (question/answer are still scrubbed only in `_write_human_interaction`).
    Separate concern from the QA-bounce issue, as the reporter suspected.

- timestamp: 2026-09-28T00:00:00Z
  checked: |
    Masked-assertion risk -- the sibling tests in the two multi-test files that
    were NOT reported as failing.
  found: |
    tests/integration/test_artifact_scope_enforcement.py's two NEGATIVE cases
    (`..._qa_that_overwrites_architectures_artifact_is_reverted_and_fails`,
    `..._architecture_that_overwrites_bas_artifact_is_reverted_and_fails`) pass
    `expected_exit=1`, and test_role_reassignment_sc2.py's
    `test_shipped_config_with_no_fake_binaries_fails_visibly_not_silently` expects
    a visible failure. All three currently exit 1 -- but from gate exhaustion, not
    from the artifact-scope violation / missing-binary condition they claim to prove.
  implication: |
    These three are passing for the wrong reason right now. Whoever fixes the four
    red tests must re-confirm that the three green negative controls still fail for
    THEIR OWN stated reason (assert on the ROLE_FAILED error / event payload, not
    merely on exit code 1).

## Resolution

root_cause: |
  Two independent, serial causes, both rooted in one upstream condition -- the four
  affected integration tests import the SHIPPED `.dark-factory.yaml` verbatim into a
  throwaway git repo that cannot satisfy its repo-specific declarations:

  (1) [produces the observed symptom] `quality_gate.commands: ["uv run pytest -q",
      "uv run ruff check ."]` became EXECUTABLE in Phase 9 (commit 4a7a19e); before
      that it was inert snapshot data. In the throwaway repo (only `.dark-factory.yaml`,
      `.dark-factory/`, `.gitignore`, `README.md`) `uv run pytest -q` exits 5
      (EXIT_NOTESTSCOLLECTED). `QualityGateResult.status` requires exit 0 from every
      command, so the gate is FAIL on every attempt. `_bounce_or_fail` bounces
      QA -> DEVELOPMENT against `quality_gate_iterations` (cap 2), then fails the run
      with `quality_gate_max_iterations_exhausted`. The reported "three bounces
      exhausting qa_developer_max_iterations: 3" is a mis-attribution: it is 2 bounces
      + 1 terminal failure = 3 "QA ->" CLI transitions, driven by the gate counter
      (cap 2), not the QA-verdict counter (cap 3).

  (2) [latent, surfaces the moment (1) is fixed] `publishing.create_pr: true` with no
      `repository.github_owner` / `repository.github_repo` and no GITHUB_TOKEN
      reachable from the throwaway cwd. On gate PASS the runner enters the publish
      branch, `default_github_client_factory()` raises `MissingGitHubCredentialError`
      (or `run_publish_step` returns "repository.github_owner is not set"), the runner
      sets `signal = Signal.ROLE_FAILED`, and the run still ends FAILED.

  The orchestrator, the gate, the bounce logic, the workers and the artifact handoff
  are all behaving exactly as designed. This is a TEST-FIXTURE defect, same class as
  knowledge-base entry `phase4-artifact-commit-bugs`: a config field moved from inert
  to enforced and the fixtures that declare it were never swept.

  Plus two unrelated test-only defects: (5) an untracked throwaway script asserting
  the adjacency reason on the wrong event, and (6) an over-broad `"redact(" not in
  runner_src` structural guard that Phase 10's two legitimate GitHub-error redaction
  call sites now trip.

fix: "NOT APPLIED -- goal: find_root_cause_only"
verification: "N/A"
files_changed: []
