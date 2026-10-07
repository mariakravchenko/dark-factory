---
status: investigating
trigger: "The `integration` tier is excluded from CI in full (.github/workflows/ci.yml:55-59) because SOME of its tests drive real agent CLIs whose credentials the hosted runner lacks. But many of its tests — including the three end-to-end pipeline modules — need NO real credentials: they install fake hermes/copilot/claude CLIs via tests/support/fake_*_cli.py and monkeypatch fake tokens. A CI-runnable selector for the credential-free subset would close the escape gate that let G-08-2 ship (a test committed collection-verified only, first executed during UAT four phases later)."
created: 2026-10-07T00:00:00Z
updated: 2026-10-07T00:00:00Z
---

## Current Focus

hypothesis: |
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
test: (not started) — see next_action
expecting: |
  H1 confirmed if `-m integration` in a credential-free, CLI-free environment yields only
  skips (never errors/failures) for the three `*_live.py` suites.
  H2 confirmed if the measured wall-clock for the credential-free subset exceeds a
  tolerable CI budget, forcing a curated selector rather than the whole tier.
next_action: |
  Measure before designing. (1) Triage the 192 collected integration tests into
  credential-free vs real-credential-requiring, using `live_runtime` import as the
  authoritative discriminator and hand-checking the 10 GitHub-grep matches. (2) Time the
  credential-free subset against Postgres to get a real CI budget number — do NOT
  extrapolate from the 6-test sample. (3) Only then choose the mechanism (new pytest
  marker vs. explicit file list vs. `-m "integration and not live"`), and update
  ci.yml:55-59's comment, which currently instructs future readers NOT to add the tier.
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

<!-- none yet -->

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

## Resolution

root_cause: |
  NOT YET CONFIRMED. Candidate framing, to be tested:
  the `integration` tier is excluded from CI as a single all-or-nothing unit, so the
  credential-requiring minority (3 of 40 modules — which already skip cleanly on their own)
  blocks the credential-free majority (including all three end-to-end pipeline proofs) from
  ever being executed by an automated gate. Whether the binding constraint is credentials
  (H1), runtime budget (H2), or a third dependency (H3) is the open question.
fix: ""
verification: ""
files_changed: []

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
