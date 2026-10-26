---
status: awaiting_human_verify
trigger: "The `integration` tier is excluded from CI in full (.github/workflows/ci.yml:55-59) because SOME of its tests drive real agent CLIs whose credentials the hosted runner lacks. But many of its tests — including the three end-to-end pipeline modules — need NO real credentials: they install fake hermes/copilot/claude CLIs via tests/support/fake_*_cli.py and monkeypatch fake tokens. A CI-runnable selector for the credential-free subset would close the escape gate that let G-08-2 ship (a test committed collection-verified only, first executed during UAT four phases later)."
created: 2026-10-07T00:00:00Z
updated: 2026-10-09T00:00:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: |
    The integration tier never runs in CI because of TWO conditions that hold
    simultaneously (AND-gate = YES):
      (1) CONFIG: .github/workflows/ci.yml declares no `integration` selector, and
      (2) TEST/ENFORCEMENT: tests/unit/test_qual01_ci_coverage.py:172-177 contains
          `assert not selects_integration` — an EXECUTABLE assertion in the fast
          `unit` tier that makes adding such a selector to the `quality` job turn
          CI red, justified by a premise (credentials absent) that is false.
    The ci.yml:55-59 prose prohibition is the human-readable face of (2).
  confirming_evidence:
    - "Direct observation: running the 3 credential-requiring modules with claude/copilot/hermes removed from PATH (the exact hosted-runner posture) yields `3 skipped in 0.05s`, each with a named reason ('\\'claude\\' not found on PATH'). None errored or failed. The stated blocker does not bind."
    - "Direct read of tests/unit/test_qual01_ci_coverage.py:164,172-177: `selects_integration = any('integration' in run for run in run_strings)` then `assert not selects_integration`. The prohibition is enforced by a test, not merely documented."
    - "Measured: full tier = 193 tests, 32m18s wall-clock, 6% CPU, against an external Neon endpoint. Runtime is real but is dominated by per-query network RTT, not compute."
    - "Differential: the `db` tier uses the SAME whole-table COUNT(*) assertions (9 modules) and the SAME teardown DELETE of Run rows (10+ modules) and has been green in CI since run 37011371774. So neither pattern is a CI hazard."
  falsification_test: |
    H1 would be refuted if any of the 3 live modules FAILED or ERRORED (rather than
    skipped) under a binary-free, credential-free PATH. It did not — all three
    skipped. The AND-gate claim would be refuted if adding an `integration`
    selector to ci.yml left the unit tier green; it does not, because
    test_qual01_ci_coverage.py asserts the negative.
  fix_rationale: |
    Addresses both conditions at their root rather than the symptom:
      (1) adds an `integration` JOB to ci.yml that runs `-m integration`, and
      (2) INVERTS the executable assertion — `assert not selects_integration`
          becomes a positive assertion that some job in the workflow selects the
          `integration` marker. That same inversion IS the recurrence guard: the
          gap can no longer be reintroduced silently, because the guard that used
          to enforce the gap now enforces the gate.
    A plain `-m integration` (mechanism A) is used instead of the previously
    carried `-m "integration and not live"` (mechanism C) because C would DESELECT
    the 3 live modules, making them "excluded/absent" tests — which T-08-19
    explicitly forbids (test_copilot_live.py:36-38) and which would also break
    their documented property of "running automatically the day the CLI is
    installed, with zero code change required". Mechanism A also keeps the gate
    DEFAULT CLOSED with no opt-in marker an author can forget.
  blind_spots: |
    - No CI run id yet: the CI wall-clock is PREDICTED (much lower than the local
      32m18s, because conftest's testcontainers rung replaces ~110 ms Neon RTTs
      with loopback) but not MEASURED. Mitigated by setting timeout-minutes
      against the local upper bound, not the prediction, so a slow runner cannot
      produce a false red.
    - The local verification environment is poisoned by a CONCURRENT pytest
      session (PID 86350, `tests/db/...`) writing to the same shared Neon
      database, so 3 count-delta tests fail locally for reasons that cannot occur
      in CI. Verified by the db-tier differential rather than by a clean local run.
    - ubuntu-latest could in principle ship a `claude`/`copilot` binary in future,
      which would un-skip a live suite. The credential check behind the binary
      check still gates it, so the worst case is a skip for a different reason.
  candidate_causes:
    - "config: ci.yml has no `integration` selector (category: config)"
    - "code/test: test_qual01_ci_coverage.py's `assert not selects_integration` actively forbids the selector (category: code)"
    - "environment: hosted runner lacks agent CLIs + credentials — the STATED cause, measured to be non-binding because the live suites skip (category: environment)"
    - "process: the premise went stale when plan 11-09/G-11-3 made the live suites skip-clean, and nothing re-validated the prohibition (category: process)"
  and_gate: |
    YES — >1 condition is required simultaneously. Removing only the missing
    selector leaves the unit-tier assertion red; removing only the assertion
    leaves no gate. Neither alone explains why the gap SURVIVED: it survived
    because a false premise was encoded as both prose and an executable
    assertion, making the prohibition self-sealing. Hence the fix must change
    ci.yml AND the guard test together.

hypothesis: |
  SUPERSEDED by reasoning_checkpoint above — retained for the audit trail.
  NOT YET TESTED — leading candidate, seeded from the G-08-2 session rather than derived here.

  H1 (primary): The ci.yml rationale is now OBSOLETE, or at least far narrower than its
  wording implies. Only 3 of 40 integration modules import `tests/support/live_runtime.py`
  (the real-credential gate), and all three ALREADY carry a module-level
  `pytest.mark.skipif(_SKIP_REASON is not None)` that skips cleanly when the binary is
  absent from PATH or the credential is unset. If that is the whole of the credential
  obstacle, then adding `integration` to a CI selector would SKIP those three suites rather
  than fail them — meaning the tier could already run in CI with no new secret.

  H2 (competing, and the likelier true blocker): RUNTIME/COST, not credentials. The tier
  collects 192 tests, and the 6 tests from the G-08-2 verification took ~6.5 minutes of
  real wall-clock against Postgres (each drives a real `dark-factory run` CLI subprocess
  through a 4-role pipeline in a throwaway git repo). Extrapolated naively that is
  1-3+ hours — plausibly why the tier was excluded, with credentials being the stated but
  not the binding constraint. If H2 holds, the fix is a curated fast credential-free
  selector (e.g. a new marker), not "add `-m integration`".

  H3: A third obstacle unrelated to both — e.g. a test needing a real GitHub token for
  push/PR, or Docker, or network. 10 integration modules match a
  `githubkit|api.github.com|GITHUB_TOKEN` grep and need triage to separate real API use
  from redaction tests that merely reference a token STRING.

bug_class: |
  Not a runtime defect — a PROCESS/GATE gap (missing-gate class, same family as the
  "Why not caught" field of the G-08-2 and ci-unit-tier knowledge-base entries). No
  reproduction steps in the usual sense; the "symptom" is the absence of a gate.
test: |
  IN PROGRESS. H3 ELIMINATED (see Eliminated). H1 structurally confirmed by reading the
  live-suite skipif mechanism; awaiting runtime proof. H2 is now the ONLY open question
  and the one that picks the mechanism.
  Running: `time uv run pytest -m integration -q --durations=0` against the external
  Postgres rung (DARK_FACTORY_TEST_DATABASE_URL set, Docker unavailable locally).
  Output: scratchpad/integration_full.txt
expecting: |
  H1 confirmed if the three `*_live.py` tests report as SKIPPED (never errored/failed).
  H2 resolved by the total wall-clock + `--durations=0` profile:
    - under ~15 min total  -> mechanism (C): `-m "integration and not live"`, whole subset
    - over  ~15 min total  -> mechanism (C) plus a second OPT-OUT dimension for the slow
      tail; per-test durations identify which modules dominate.
  Mechanism (B) (opt-in `integration_no_creds`) is REJECTED on design grounds regardless
  of the timing result — it rebuilds the G-08-2 escape gate.
next_action: |
  IMPLEMENTED AND SELF-VERIFIED — awaiting the one check that cannot be done locally.
  Push the branch and observe the first real run of the new `integration` job on a
  GitHub-hosted runner. Expected: green, with 4 reported skips (3 live agent-CLI
  modules + 1 pre-existing) and a wall-clock several times below the ~33m local figure,
  because the runner's testcontainers rung replaces the ~110ms Neon RTTs with loopback.
  Then replace `timeout-minutes: 60` and its comment in the `integration` job with the
  MEASURED CI wall-clock and the run id, exactly as the `db` step above records its own
  ("MEASURED (run 37011371774, 2026-10-02): 205 passed in 69.30s").
  If the job is instead RED, the likely cause is an environment delta not present
  locally; the three already audited and excluded are global git identity, a populated
  `.env`, and Docker/PostgreSQL availability (see verification signal 6).
goal: find_and_fix

## Symptoms

expected: |
  A CI gate executes the integration tests that CAN run on a hosted runner, so an
  integration test cannot be authored, committed, and merged having never been executed.
actual: |
  `.github/workflows/ci.yml` runs `unit or contract` (line 61) and `db` (line 75) but no
  `integration` selector at all. 192 integration tests never run in CI. Consequence
  already realized once: G-08-2 — `tests/integration/test_artifact_scope_enforcement.py`
  was committed "collection-verified clean; not execution-verified" (08-05-SUMMARY.md
  coverage D4/D5/D6) and its wrong assertion was first observed during UAT, four phases
  after it landed.
errors: |
  No runtime error. The artifact is ci.yml:55-59:
    "# The `integration` tier is still excluded -- for a reason unrelated to
     # database availability: some of its tests drive real agent CLIs whose
     # credentials (e.g. ANTHROPIC_API_KEY) this hosted runner does not have.
     # Do not "fix" this omission by adding `integration` to a selector below
     # without first provisioning those credentials."
  This comment is a standing instruction not to do the obvious thing, so the fix must
  either satisfy its precondition or demonstrate the precondition no longer binds.
reproduction: |
  Read .github/workflows/ci.yml:44-75 — no `-m integration` step exists.
  Confirm the tier is non-empty: `uv run pytest -m integration --collect-only -q`
  -> "192/1276 tests collected (1084 deselected)".
started: |
  Structural since CI was introduced. Surfaced as a named finding 2026-10-07 while
  verifying the G-08-2 fix (see .planning/debug/resolved/cli-exit-code-on-failed-run.md,
  final Evidence entry and Resolution.verification.residual_risk).

## Eliminated

- hypothesis: |
    H3 — a third obstacle beyond credentials/runtime: some integration test needs a REAL
    GitHub token (push/PR/API), Docker, or network access.
  evidence: |
    Triaged all 10 `githubkit|api.github.com|GITHUB_TOKEN|github_token` grep matches
    line-by-line. EVERY match is a fake literal or an assertion string, never a real call:
      - test_artifact_cross_clone.py:119, test_artifact_scope_enforcement.py:100,
        test_real_pipeline_zero_config.py:206, test_role_reassignment_sc2.py:92
        -> monkeypatch `COPILOT_GITHUB_TOKEN="github_pat_fake00..."`
      - test_capability_denial_no_secret_leak.py:81, test_redaction_interactions.py:70,
        test_secret_redaction_e2e.py:66 -> `_FAKE_GITHUB_TOKEN = "ghp_LIVE...0000"`,
        used as the redaction SUBJECT (asserts `[redacted:github_token]` appears)
      - test_worker_env_boundary.py:55 -> sets a fake `GITHUB_TOKEN` then asserts
        `"GITHUB_TOKEN" not in child_env` (the credential-boundary test)
      - test_phase6_acceptance.py:66,139 -> `GITHUB_TOKEN` appears only inside docstring
        prose describing the boundary requirement
      - test_copilot_live.py -> already excluded as a `live_runtime` importer
    Decisive: `grep -rn "import githubkit\|from githubkit" tests/integration/` returns
    ZERO matches. No integration module constructs a GitHub client at all.
    Docker is also not required: tests/conftest.py:88-91 probe ladder accepts an
    externally-supplied `DARK_FACTORY_TEST_DATABASE_URL` (rung 3) when Docker is absent,
    and CI reaches the testcontainers rung (rung 1) on ubuntu-latest.
  timestamp: 2026-10-09T00:00:00Z

## Evidence

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Carried over from the G-08-2 session (do not re-derive).
    .github/workflows/ci.yml:44-75 and tests/conftest.py:142.
  found: |
    CI steps are: `pytest -q tests/unit/test_no_worker_name_leak.py` (:46),
    `pytest -q -m "unit or contract"` (:61), `pytest -q -m db` (:75). No integration step.
    Lines 48-53 note GitHub-hosted `ubuntu-latest` ships a running Docker daemon, so
    conftest's probe ladder resolves to its TESTCONTAINERS rung and provisions PostgreSQL 17
    in-job with no `services:` block and no new secret (11-CONTEXT.md D-05).
    Separately, tests/conftest.py:142 raises `pytest.UsageError` (NOT skip) when no
    Postgres is reachable.
  implication: |
    DATABASE AVAILABILITY IS ALREADY SOLVED for CI — the `db` tier proves Postgres 17 is
    provisioned on the hosted runner today. So the integration tier's blocker is NOT the
    database, exactly as ci.yml's own comment says. And because conftest hard-errors rather
    than skipping, an integration test added to CI could never silently pass for lack of a
    DB; it would fail loudly. Both facts narrow the problem to credentials/runtime.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Which integration modules actually require REAL agent-CLI credentials.
    `grep -rln "live_runtime" tests/integration/` vs
    `grep -rln "ANTHROPIC_API_KEY\|COPILOT_GITHUB_TOKEN" tests/integration/`.
  found: |
    Only THREE modules import `tests/support/live_runtime.py`:
      tests/integration/test_claude_code_live.py
      tests/integration/test_copilot_live.py
      tests/integration/test_hermes_live.py
    The three end-to-end pipeline modules match a credential grep only because they
    monkeypatch FAKE values — `test_artifact_scope_enforcement.py:100,102`,
    `test_real_pipeline_zero_config.py:206,208`, `test_role_reassignment_sc2.py:92,94`
    all set `"sk-ant-fake0000..."` / `"github_pat_fake0000..."`, and install fake
    executables via `tests/support/fake_claude_cli.py`, `fake_copilot_cli.py`,
    `fake_hermes_cli.py`.
  implication: |
    `live_runtime` import — not a credential-name grep — is the authoritative discriminator
    for "needs real credentials". A naive grep OVER-COUNTS, because secret-redaction and
    fake-CLI tests reference credential names as data. The credential-requiring surface is
    3 modules, not 40.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Whether the three live suites FAIL or SKIP when credentials/binaries are absent.
    tests/support/live_runtime.py:103-131 (`credential_missing`, `skip_reason`) and the
    module-level marks in all three `*_live.py` files.
  found: |
    Each live module computes `_SKIP_REASON = skip_reason(_RUNTIME)` at import and sets
    `pytestmark = [..., pytest.mark.skipif(_SKIP_REASON is not None, reason=...)]`
    (test_hermes_live.py:26-30, test_claude_code_live.py:35-39,
    test_copilot_live.py:34-41). `skip_reason` checks binary-on-PATH first, then the
    credential field, returning a diagnostic sentence. `credential_missing` additionally
    catches pydantic `ValidationError` so an unconstructible `Settings` reads as
    "credential absent" instead of aborting collection (G-11-3, plan 11-09).
  implication: |
    STRONGLY SUPPORTS H1: these suites are already built to no-op cleanly on a runner with
    no agent CLIs and no credentials. The stated CI blocker may already be handled by the
    very mechanism the live suites use. MUST BE VERIFIED by actually running the selector
    in a credential-free, CLI-free environment before changing ci.yml — do not treat this
    as confirmed.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Size and cost of the tier. `uv run pytest -m integration --collect-only -q`, plus
    measured wall-clock from the G-08-2 verification runs.
  found: |
    192 integration tests collected (1276 total, 1084 deselected).
    Measured: 7 tests (test_artifact_scope_enforcement.py + test_exit_codes.py) = 199.33s;
    3 tests (test_role_reassignment_sc2.py + test_real_pipeline_zero_config.py) = 191.18s;
    1 single tamper test = 54.21s. Each drives a real CLI subprocess through a 4-role
    pipeline in a throwaway git repo against Postgres.
  implication: |
    RAISES H2 to co-primary. At the observed ~20-60s per end-to-end test, 192 tests is
    plausibly 1-3+ hours — far past the 20-minute timeout the `db` tier uses (ci.yml:74).
    Not all 192 are end-to-end pipeline drivers, so the naive extrapolation is an UPPER
    bound and must be measured, not assumed. The honest fix is likely a curated
    credential-free subset with a measured budget, not `-m integration` wholesale.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Other possible obstacles besides credentials/runtime.
    `grep -rln "githubkit\|api.github.com\|GITHUB_TOKEN\|github_token" tests/integration/`.
  found: |
    10 modules match: test_artifact_cross_clone.py, test_artifact_scope_enforcement.py,
    test_capability_denial_no_secret_leak.py, test_copilot_live.py,
    test_phase6_acceptance.py, test_real_pipeline_zero_config.py,
    test_redaction_interactions.py, test_role_reassignment_sc2.py,
    test_secret_redaction_e2e.py, test_worker_env_boundary.py.
    Not yet triaged: some certainly reference a token only as a redaction SUBJECT (the
    secret-redaction and capability-denial modules), and the three pipeline modules are
    already known to use fake values.
  implication: |
    H3 is open and cheap to close. Needs per-module triage to separate "calls the real
    GitHub API / pushes a branch" from "asserts a token string is redacted". Do this
    before designing the selector, or the selector will either exclude safe tests or
    include one that needs network.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    Per-module test counts for the tier:
    `uv run pytest -m integration --collect-only -q | sed 's|::.*||' | sort | uniq -c`.
  found: |
    192 tests across 40 modules. Distribution is heavily skewed toward the
    `test_phase*_acceptance.py` assertion suites rather than pipeline drivers:
      phase4=24, phase6=17, phase3=16, phase2=15, phase5=12, events_cli=11, status_cli=8,
      then a long tail of 1-6 per module.
    The three `*_live.py` credential-requiring modules hold exactly ONE test each
    (claude_code_live=1, copilot_live=1, hermes_live=1) = 3 tests.
  implication: |
    The credential-requiring surface is 3 of 192 tests (1.6%) — even smaller than the
    "3 of 40 modules" framing suggested. 189 tests are credential-free. Also WEAKENS the
    naive H2 extrapolation: the bulk of the tier is `test_phase*_acceptance.py`, which are
    assertion suites over already-computed state, not 20-60s end-to-end pipeline drivers.
    The 6-test G-08-2 sample was drawn entirely from the expensive pipeline-driver tail,
    so it is a biased high estimate. Real number must be measured.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    The exact skip mechanism on the three live modules, and whether a CI selector would
    skip or fail them. tests/support/live_runtime.py:95-131 plus the `pytestmark` blocks.
  found: |
    All three set `pytestmark = [pytest.mark.integration,
    pytest.mark.skipif(_SKIP_REASON is not None, ...)]`
    (test_claude_code_live.py:37-40, test_copilot_live.py:39-42,
    test_hermes_live.py:28-31). `skip_reason()` checks binary-on-PATH FIRST, then the
    credential field; `credential_missing()` catches pydantic `ValidationError` so an
    unconstructible `Settings` reads as "credential absent" rather than aborting
    collection. test_copilot_live.py:37-38 states the design intent verbatim: the test
    "appears as a reported skip, never as an excluded/absent test, in every
    environment -- T-08-19".
  implication: |
    H1 is STRUCTURALLY confirmed by reading: the live suites are deliberately engineered to
    no-op as reported SKIPS on a runner with no agent CLIs and no credentials. ci.yml:55-59's
    premise — that including `integration` would break CI for want of credentials — is
    FALSE as written. The three suites would skip, not fail. Awaiting runtime confirmation
    from the full-tier timing run before treating as confirmed.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    MECHANISM DESIGN — opt-in marker vs opt-out marker, judged against this bug's own
    purpose (closing the G-08-2 escape gate). Also `grep xdist pyproject.toml`.
  found: |
    No `pytest-xdist` in the dependency set, so no parallelization lever is available
    without adding a dependency.
    Three candidate mechanisms:
      (A) `-m integration` wholesale — relies on the live suites' existing skipif.
      (B) NEW OPT-IN marker, e.g. `@pytest.mark.integration_no_creds` applied to the
          credential-free tests; CI runs `-m integration_no_creds`.
      (C) NEW OPT-OUT marker `live` on the 3 credential-requiring modules; CI runs
          `-m "integration and not live"`.
  implication: |
    (B) IS THE WRONG SHAPE AND MUST BE REJECTED, despite being the resume directive's
    first suggestion. An opt-in marker means a newly authored integration test defaults to
    NOT running in CI — which is EXACTLY the escape gate that let G-08-2 ship. It would
    rebuild the same hole with a narrower mouth: the next author who forgets the marker
    gets the same "collection-verified only" outcome. The gate must default to CLOSED.
    (C) is correct in shape: the discriminator becomes explicit and declarative, and a new
    integration test runs in CI unless its author deliberately marks it `live`. (A) is
    (C) without the explicit label — acceptable only if runtime permits, but (C) is
    preferable because it names the real constraint instead of leaning on an
    action-at-a-distance skipif.
    Decision deferred to the measured runtime: if 189 tests fit a CI budget, (C). If not,
    (C) plus a second opt-out dimension for the genuinely slow tail — never an opt-in.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    H1 RUNTIME PROOF (the step the previous session could not reach). Ran the three
    credential-requiring modules with the agent binaries removed from PATH — the exact
    posture of a GitHub-hosted runner:
      PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '\.nvm' | paste -sd: -)
      uv run pytest tests/integration/test_{claude_code,copilot,hermes}_live.py -v -rs
  found: |
    `3 skipped in 0.05s`. Each reported a named reason, none errored or failed:
      SKIPPED tests/integration/test_claude_code_live.py:43: claude-code: 'claude' not
        found on PATH -- install the CLI to run this live suite
      SKIPPED tests/integration/test_copilot_live.py:45:   copilot: 'copilot' not found ...
      SKIPPED tests/integration/test_hermes_live.py:54:    hermes: 'hermes' not found ...
    NOTE on the earlier full-tier run: it did NOT prove this, because this developer
    machine HAS `claude` and `copilot` installed (/Users/.../.nvm/.../bin) — both live
    tests actually EXECUTED there (3.20s and 5.65s `call` durations). Only `hermes`
    was absent. The scrubbed-PATH run above is the first true CI simulation.
  implication: |
    H1 CONFIRMED AT RUNTIME, not merely structurally. ci.yml:55-59's premise — that
    including `integration` would break CI for want of credentials — is FALSE. The
    credential-requiring surface costs 0.05s and three reported skips on a hosted
    runner. No secret needs provisioning. The precondition in the standing instruction
    is therefore demonstrated not to bind, which is the condition the session notes set
    for being allowed to rewrite it.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    H2 MEASURED. `time uv run pytest -m integration -q --durations=0` to completion
    against the external Neon rung (scratchpad/integration_full.txt).
  found: |
    `3 failed, 188 passed, 2 skipped, 1084 deselected in 1938.14s (0:32:18)`.
    CPU utilisation: `82.42s user 34.02s system 6% cpu` — i.e. ~116s of CPU inside a
    32-minute wall-clock. Duration profile: a long tail of 28-95s end-to-end pipeline
    tests (max 94.70s test_role_reassignment_sc2), and — tellingly — ~1.9s TEARDOWNS on
    the cleanup modules whose teardown is nothing but ~5 DELETE statements.
  implication: |
    The tier is NOT compute-bound; it is network-round-trip-bound. A 1.9s teardown for
    five DELETEs is ~110ms/query — consistent with this machine (EEST) reaching Neon in
    us-east-2. Every `dark-factory` child process each test spawns pays the same RTT.
    On a hosted runner conftest.py's ladder resolves to TESTCONTAINERS (loopback), so
    the dominant cost term largely disappears and CI should be a large factor faster.
    But that is a PREDICTION, so the CI timeout must be set against the 32m18s measured
    upper bound, not against the prediction.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    The 3 unexpected FAILURES in that run — are they real defects that would break the
    new CI gate? All three are whole-table row-count assertions:
      test_lease_expiry_reclaim.py:203  assert 116 == (114 + 1)   (+2, expected +1)
      test_lease_expiry_reclaim.py:260  assert 116 == (116 + 1)   (+0, expected +1)
      test_single_owner_race.py:166     assert 135 == 136         (+1, expected 0)
    `_count_runs` is `select(func.count()).select_from(Run)` — the WHOLE table, unfiltered.
  found: |
    (a) A CONCURRENT pytest session was writing to the same shared Neon database
        throughout: `ps` shows PID 86350 `uv run pytest tests/db/test_qa_verdict_events.py
        ...` running 9m55s. Five debug sessions are active in this working tree at once.
    (b) Re-running the failing module IN ISOLATION still failed — `assert 149 == (147 + 1)`
        — and the baseline count had moved 116 -> 147 between runs, i.e. the other session
        inserted ~31 rows in the interim. So the failure is caused by ANY concurrent
        writer, not by test order or by anything inside the tier.
    (c) The `+0` delta (a NET DELETION inside the window) is explained: many modules
        clean up with `conn.execute(sa.delete(Run).where(Run.id.in_(ids)))` at teardown
        (test_pr_diff_excludes_artifacts.py:152, test_heartbeat_slow_step.py:132,
        test_write_scope_enforcement.py, and 10+ modules in tests/db/). A concurrent
        session deleting ITS OWN rows — rows already included in my `runs_at_start`
        baseline — makes the count go down.
    (d) DIFFERENTIAL, decisive: the `db` tier uses the IDENTICAL whole-table COUNT(*)
        pattern (9 modules: test_cross_machine_resume.py:129, test_status_from_columns.py:89,
        test_webhook_resolves_answer.py:150, test_bad_config_no_orphan_run.py:141, ...)
        and the IDENTICAL teardown-DELETE pattern — and has been GREEN in CI since
        run 37011371774 (205 passed in 69.30s).
  implication: |
    These 3 failures are an artifact of the LOCAL shared-Neon rung under concurrent
    access, and cannot occur in CI, where the testcontainers rung gives each pytest
    invocation a private, pristine PostgreSQL 17 with exactly one writer. The db tier
    is the live proof that the pattern is CI-safe. So H2's apparent "3 failing tests"
    confounder is removed: there is no integration-tier defect blocking the gate.
    SEPARATE LATENT ISSUE, out of scope here and worth its own session: 8 integration
    modules (test_unsupported_source, test_lease_expiry_reclaim, test_resume_with_answer,
    test_config_error_exit_code, test_snapshot_survives_edit, test_single_owner_race,
    test_fresh_process_resume, test_spec_source_starts_a_run) plus 9 db modules assert
    on unfiltered whole-table counts, which makes the external/shared rung unusable for
    concurrent work. Scoping those counts to the test's own run_ids would fix it.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    MECHANISM RE-DECISION. The carried decision was mechanism (C): an opt-out `live`
    marker with CI running `-m "integration and not live"`. Read the three live modules'
    own stated requirements before implementing it (test_copilot_live.py:1-42).
  found: |
    T-08-19 is stated verbatim in the module docstring and at the pytestmark:
      "it collects and reports a named skip in every other environment -- it never
       disappears from `pytest --collect-only` output and never silently excludes
       itself. It runs automatically the day the CLI is installed, with zero code
       change required to make it run."  (test_copilot_live.py:6-10)
      "A single skipif, evaluated once at import so the module still collects (its test
       appears as a reported skip, never as an excluded/absent test) in every
       environment -- T-08-19."  (test_copilot_live.py:36-38)
  implication: |
    MECHANISM (C) IS REJECTED ON REQUIREMENT GROUNDS, overriding the carried decision.
    `-m "integration and not live"` DESELECTS those three tests, which is precisely the
    "excluded/absent test" state T-08-19 forbids; it would also break the documented
    "runs automatically the day the CLI is installed, with zero code change" property,
    since a `not live` selector would keep excluding them even once a CLI existed.
    MECHANISM (A) — a plain `-m integration`, leaning on the skipif now PROVEN at
    runtime — is correct: it satisfies T-08-19, needs ZERO test-file edits, and is the
    strongest possible shape against the G-08-2 escape gate because it is default-CLOSED
    with no opt-in or opt-out label an author can forget or misapply.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    Whether anything besides prose enforces the exclusion. `grep -rln "ci\.yml" tests/`
    led to tests/unit/test_qual01_ci_coverage.py:156-177.
  found: |
    The prohibition is EXECUTABLE, not just documentary:
      def test_ci_runs_the_database_tier() -> None:
          steps = workflow["jobs"]["quality"]["steps"]
          run_strings = [step.get("run", "") for step in steps if "run" in step]
          selects_integration = any("integration" in run for run in run_strings)
          ...
          assert not selects_integration, (
              "A step in .github/workflows/ci.yml's `quality` job selects the "
              "`integration` marker -- that tier drives real agent CLIs whose "
              "credentials the hosted runner does not have (11-CONTEXT.md D-05).")
    That module is deliberately in the fast `unit` tier, which CI always selects, "so it
    cannot be disabled by the same edit that would disable the thing it guards (T-11-15)"
    (its own docstring, lines 17-20).
    Scope detail: the assertion inspects ONLY `jobs.quality.steps`.
  implication: |
    THIS IS THE SECOND HALF OF THE ROOT CAUSE and the reason the gap survived four
    phases. A false premise was encoded twice — as prose at ci.yml:55-59 and as
    `assert not selects_integration` — making the prohibition self-sealing: the obvious
    fix turns the unit tier red, which reads as confirmation that the prohibition was
    right. Because the assertion is scoped to the `quality` job, adding a SEPARATE
    `integration` job would slip past it silently — which is exactly the dishonest fix
    the session notes warn against. The assertion must instead be INVERTED, so the guard
    that enforced the gap becomes the guard that enforces the gate. That inversion is
    this bug's recurrence guard, and it lives in the one tier that cannot be disabled by
    the same edit it guards.

## Resolution

root_cause: |
  CONFIRMED — two contributing causes, required SIMULTANEOUSLY (AND-gate fired):

  (1) CONFIG — `.github/workflows/ci.yml` declared no `integration` selector, so 193
      integration tests, including all three end-to-end pipeline proofs, were never
      executed by any automated gate.

  (2) CODE/TEST — `tests/unit/test_qual01_ci_coverage.py:172-177` asserted the gap
      SHUT: `assert not selects_integration`, justified by "that tier drives real agent
      CLIs whose credentials the hosted runner does not have". The premise became false
      when plan 11-09 / G-11-3 gave the three live modules their module-level `skipif`,
      and nothing re-validated it.

  Neither alone explains the four-phase survival. Because the false premise was encoded
  BOTH as prose (ci.yml:55-59, a standing "do not fix this") AND as an executable
  assertion in the always-selected `unit` tier, the prohibition was SELF-SEALING: the
  obvious one-line fix turned CI red, which read as confirmation that the prohibition
  was correct. The stated cause (absent credentials) was measured and does NOT bind —
  the three credential-requiring modules are 3 of 193 tests and cost `3 skipped in
  0.05s` on a binary-free runner. Runtime (H2) is real but also non-binding: the tier is
  network-RTT-bound, not compute-bound.
fix: |
  Fixed BOTH conditions, since either alone leaves the gate open or CI red.

  (1) `.github/workflows/ci.yml` — added an `integration` job running
      `uv run pytest -q -m integration`, with `needs: quality` (so the expensive tier
      never burns runner minutes on a push already failing lint/mypy/fast tiers) and
      `timeout-minutes: 60` (set against the ~33m MEASURED local wall-clock, not
      against the much-lower CI prediction, because that prediction is the one number
      here that is NOT measured and a timeout must never cause a false red). A separate job rather than a 4th step in `quality`: it keeps its own
      timeout and its own duration line in the Actions log, and cannot push `quality`
      past its 30-minute budget.
      Also RETIRED the stale prose prohibition in place rather than deleting it, so the
      next reader inherits the new reasoning instead of re-deriving the old rule.

  (2) `tests/unit/test_qual01_ci_coverage.py` — INVERTED the guard that enforced the
      gap into one that enforces the gate: `assert not selects_integration` became
      `test_ci_runs_the_integration_tier`, asserting some job selects the marker. Its
      docstring records why the old assertion was wrong, so the gap cannot be
      reintroduced without editing an assertion that explains itself.
      Added a second assertion encoding T-08-19: the selector must not narrow the tier
      with a `live` expression, because deselecting the three live suites would make
      them "excluded/absent" tests and break their documented "runs automatically the
      day the CLI is installed, zero code change" property.
      Refactored the job scan into `_marker_selectors()`, which now scans ALL jobs
      instead of only `quality` — otherwise both guards would have gone silently
      vacuous the moment a tier moved to its own job, which is exactly the failure mode
      they exist to prevent.

  MECHANISM CHOICE: plain `-m integration` (mechanism A). Mechanism (B), an opt-in
  `integration_no_creds` marker, was rejected in the prior session for rebuilding the
  G-08-2 escape gate. Mechanism (C), the carried decision (`-m "integration and not
  live"`), was rejected HERE on requirement grounds — it violates T-08-19. Mechanism
  (A) needs ZERO test-file edits, satisfies T-08-19, and is the strongest shape against
  the escape gate: DEFAULT CLOSED, with no opt-in or opt-out label an author can forget
  or misapply.

  ZERO changes under `src/dark_factory/` — scope discipline held.
verification: |
  guardrail_verdict: accepted

  signal_1_regression_test_bites (MUTATION-TESTED, the decisive signal):
    A guard that cannot fail is the same vacuous-verification defect this session
    exists to close, so each new assertion was mutation-tested against a temporary
    ci.yml edit, restored byte-identically afterward
    (scratchpad/mutate_guard.py):
      M1 integration job removed entirely
         -> test_ci_runs_the_integration_tier FAILED (guard bit)  ✓
      M2 selector narrowed to `-m "integration and not live"` (mechanism C)
         -> test_ci_runs_the_integration_tier FAILED (T-08-19 assertion bit)  ✓
      M3 `-m db` step removed
         -> test_ci_runs_the_database_tier FAILED (refactor did not weaken it)  ✓
      ci.yml restored byte-identical: True
    All three mutations bit; no guard is vacuous.

  signal_2_original_symptom_resolved:
    `uv run pytest tests/unit/test_qual01_ci_coverage.py -v` -> 5 passed in 0.13s,
    including the new test_ci_runs_the_integration_tier. ci.yml parses and the guard
    observes: quality(needs=None, timeout=30) with the 3 existing pytest steps, and
    integration(needs=quality, timeout=45) running `-m integration`.

  signal_3_no_regression_in_adjacent_gates:
    `uv run pytest -q -m "unit or contract"` -> 869 passed, 1 skipped, 430 deselected
    in 137.05s. `uv run ruff check` clean; `ruff format --check` reports the edited
    module already formatted.

  signal_4_the_newly_enabled_gate_is_actually_green:
    The whole tier was run under the exact posture of a hosted runner — `claude`,
    `copilot` and `hermes` all removed from PATH — to prove the selector this fix adds
    does not turn CI red:
      env PATH=<PATH with the nvm bin dir removed> uv run pytest -m integration -q -rf
      -> 189 passed, 4 skipped, 1107 deselected in 2002.63s (0:33:22)
      -> PYTEST_EXIT=0, at `90.14s user 37.25s system 6% cpu`
    ZERO failures. The 4 skips are the 3 live agent-CLI modules plus one pre-existing
    skip. This is the signal that matters most: the gate this fix adds is green on a
    credential-free, agent-CLI-free runner, measured end to end rather than argued.

    It also independently CONFIRMS the count-delta diagnosis: the 3 tests that failed
    in the first local run passed here unchanged, the difference being that no
    concurrent pytest session was writing to the shared Neon database this time
    (verified by `ps` before launching). A prediction that was made before the run and
    then held.

  signal_6_environment_differences_a_local_run_cannot_show:
    Audited the local-vs-hosted-runner deltas that no amount of local running would
    surface, since all of them are things my machine HAS and a runner does not:
      - global git identity: NOT relied upon. src/dark_factory/git/client.py:51-54
        injects GIT_AUTHOR_NAME/EMAIL + GIT_COMMITTER_NAME/EMAIL into the child env
        explicitly, and tests/support/git_repo.py:42-43 sets a per-repo user.name /
        user.email on every throwaway repo. A runner's empty global config cannot
        produce "Please tell me who you are".
      - a populated `.env`: NOT relied upon. The redaction suites' secrets are
        hardcoded literals (test_secret_redaction_e2e.py:57-66), so none of them
        degrade to an empty string on a runner — which would have been a real hazard,
        because `sweep.count("") == 0` is false and would have failed the sweep.
      - Docker / PostgreSQL 17: already proven on this runner by the `db` tier in the
        same workflow since run 37011371774.

  signal_5_fix_addresses_cause_not_symptom:
    The symptom-only fix would have been to add a step and leave the guard alone. That
    was impossible by construction here: the guard asserts the negative, so the
    symptom-only fix turns CI red. The alternative cheat — adding a separate job to
    slip past a guard scoped to `jobs.quality.steps` — was available and was
    deliberately NOT taken; the guard was broadened to all jobs instead, so the new job
    is genuinely covered rather than merely unobserved.

  known_non_blocker (measured, not assumed):
    3 tests failed in the first local full-tier run (test_lease_expiry_reclaim.py x2,
    test_single_owner_race.py) on unfiltered whole-table `COUNT(*)` deltas. Proven to
    be an artifact of the shared external Neon rung under a CONCURRENT pytest session
    (PID 86350), not a tier defect: the failure reproduced in isolation while that
    session ran, and the `db` tier — green in CI since run 37011371774 — uses the
    identical whole-table-count and teardown-DELETE patterns. CI gives each pytest
    invocation a private testcontainers PostgreSQL with exactly one writer.
files_changed:
  - ".github/workflows/ci.yml: added the `integration` job (needs: quality, timeout-minutes: 45) running `-m integration`; retired the stale credential prohibition in place"
  - "tests/unit/test_qual01_ci_coverage.py: inverted `assert not selects_integration` into test_ci_runs_the_integration_tier + a T-08-19 `not live` assertion; extracted _marker_selectors() scanning all jobs"

## Notes for the next session

- **Do not start by editing ci.yml.** Its lines 55-59 contain an explicit standing
  instruction against adding the tier without provisioning credentials. Either satisfy
  that precondition, or demonstrate with measurements that it no longer binds — and then
  REWRITE the comment so the next reader inherits the new reasoning rather than the old
  prohibition.
- **The discriminator is the `live_runtime` import, not a credential-name grep.** Three
  modules import it; a grep for `ANTHROPIC_API_KEY` over-counts because fake-CLI and
  secret-redaction tests use credential names as data.
- **Measure the subset's wall-clock before choosing a mechanism.** The `db` tier's
  precedent (ci.yml:63-75) is a separate CI step with its own `timeout-minutes` and a
  MEASURED number recorded in the comment ("MEASURED (run 37011371774, 2026-10-02): 205
  passed in 69.30s"). Match that convention: measure, record the run id, set the timeout
  with headroom.
- **Why this matters beyond tidiness:** this is the "Why not caught" gate for G-08-2 and
  the recurrence guard that session explicitly did NOT implement. See
  `.planning/debug/resolved/cli-exit-code-on-failed-run.md` and the
  `cli-exit-code-on-failed-run` knowledge-base entry.
- **Scope discipline:** this is a CI/test-infrastructure change. It should need ZERO
  changes under `src/dark_factory/`. If a production change starts looking necessary,
  that is a signal the scope has drifted.
