---
status: investigating
trigger: "tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder spawns the REAL `claude` CLI — a real, billable external call — whenever ANTHROPIC_API_KEY is present in the ambient environment (e.g. via the repo-root .env), instead of being hermetic. The test asserts WorkerResultStatus.FAILED on a comment-stated premise that no credential is configured, with no injected settings override."
created: 2026-10-07T00:00:00Z
updated: 2026-10-07T00:00:00Z
symptoms_prefilled: true
goal: find_and_fix
origin: "Incidental SIBLING FINDING of debug session ci-unit-tier-settings-validation-g-11-3 (archived at .planning/debug/resolved/ci-unit-tier-settings-validation-g-11-3.md, verification SIGNAL 5 + SIBLING FINDING). Opened by explicit human decision on 2026-10-07 (\"Confirmed + both follow-ups\")."
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

bug_class: Likely Bohrbug with an environment-dependent polarity — deterministic
given a fixed environment, but the SIGN of the outcome flips on whether
`ANTHROPIC_API_KEY` is resolvable. Measured both ways 1/1 each (see Evidence).

status: NOT YET INVESTIGATED. Seeded from the parent session's incidental
findings so the next session does not re-derive them. The parent session
deliberately did NOT fix this: it is outside G-11-3's scope and the fix changes
what the test proves, so it warrants its own plan.

hypothesis (UNVERIFIED — carried over as the parent's reading, to be confirmed
or falsified here): `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
asserts `worker.execute({}).status is WorkerResultStatus.FAILED` while relying
on an AMBIENT premise — a source comment (`tests/unit/test_worker_registry_names.py:49-51`)
states "with no ANTHROPIC_API_KEY configured in this test's environment, the
credential gate returns FAILED, not an exception". Nothing enforces that
premise: no settings override, no monkeypatched env, no injected worker. When a
developer HAS credentials configured (pydantic-settings resolves them from the
repo-root `.env` because `Settings.model_config` sets a CWD-relative
`env_file=".env"`), the credential gate OPENS, `execute({})` proceeds to spawn
the real `claude` binary, the assertion fails, and the suite makes a real
billable API call from the unit tier.

This is the SAME root-cause class as G-11-3 — a unit test whose outcome depends
on ambient environment rather than an injected settings override — with the
polarity MIRRORED: G-11-3 broke when the environment was EMPTY; this breaks when
it is POPULATED. That symmetry is the most important structural fact here, and
suggests the real defect may be class-level (no autouse hermeticity fixture)
rather than confined to this one test.

test (next step): confirm whether `copilot` and `hermes` siblings in the same
file (lines 66-109, same comment-stated-premise shape, same bare `execute({})`)
have the same exposure for their own credential vars; and decide what the test
SHOULD prove — "resolves to a real adapter, not a placeholder" does not actually
require calling `execute()` at all.
expecting: the two siblings are armed identically and currently masked only by
which credentials a given developer happens to have configured.

next_action: Verify the sibling exposure for `copilot`/`hermes`, then decide the
fix shape. Two candidate directions, NOT yet chosen: (a) make the test hermetic
by injecting a settings override that guarantees NO credential (Idiom B,
`monkeypatch.setattr(<module>, "get_settings", ...)`), preserving the current
assertion but making its premise enforced rather than ambient; or (b) drop the
`execute({})` call entirely and assert the adapter-identity property directly
(`type(worker)` / `capabilities()`), since spawning a subprocess is not needed
to prove "not a placeholder". Direction (b) is likely stronger — it removes the
subprocess from the unit tier outright rather than relying on a gate staying
shut — but it narrows what the test covers, so the call belongs to the fix plan.
ALSO IN SCOPE: a recurrence guard that detects a unit-tier test spawning a real
agent binary, so this class cannot return silently.

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: A test in the `unit` tier is hermetic — it never spawns a real agent
CLI and never makes a billable external call, regardless of what credentials the
developer running it happens to have configured. Its pass/fail must not depend
on ambient environment. `tests/unit/test_worker_registry_names.py` self-describes
as unit coverage for `WorkerRegistry` membership and adapter-vs-placeholder
resolution — proving an adapter "is not a placeholder" should not require
invoking it against a live API.

actual: `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
fails, and the whole `unit or contract` tier slows from ~37s to 418.79s, whenever
`ANTHROPIC_API_KEY` is resolvable from the ambient environment. Line 52-53 calls
`worker.execute({})` and asserts `result.status is WorkerResultStatus.FAILED`;
with a credential present the gate opens and the real `claude` CLI is spawned as
a subprocess, so the status is not FAILED and the assertion blows. The cost is
not just a red test: a unit test is making a real, billable external CLI call.

errors: Assertion failure on `assert result.status is WorkerResultStatus.FAILED`
(exact text not yet captured in this session — the parent session observed the
failure in aggregate as `1 failed, 842 passed, 1 skipped, 430 deselected in
418.79s`). Capturing the verbatim assertion output and confirming the subprocess
spawn (e.g. by observing the `claude` process or its latency signature) is the
first task of this session.

reproduction:
  FAILS (credential present): run `uv run pytest -q tests/unit/test_worker_registry_names.py`
  from the repo root, where the git-ignored `.env` supplies `ANTHROPIC_API_KEY`.
  PASSES (credential absent): run the same file from a scratch CWD with no
  readable `.env` and the key unset — `6 passed in 0.14s`.
  The 0.14s-vs-418.79s latency gap is itself strong evidence of a real network
  call and is the cheapest available detector.
  NOTE: CI is unaffected — the hosted runner has no `ANTHROPIC_API_KEY` — which
  is exactly why this has stayed invisible. Do not expect CI to catch it.

started: Observed 2026-10-06 during the verification phase of debug session
ci-unit-tier-settings-validation-g-11-3 (SIGNAL 5, the broader-suite run).
Pre-existing and NOT a regression from that session's fix set, which touched
only `log_sink.py`, `publish.py`'s push token, `live_runtime.py` and test-side
overrides. Age unknown — the test's own docstring attributes `claude-code`'s
promotion from placeholder to real adapter to Plan 07-01, so the exposure
plausibly dates from there.

## Eliminated
<!-- APPEND only - prevents re-investigating -->

- NOT a regression from the G-11-3 fix set (ci-unit-tier-settings-validation-g-11-3).
  That fix touched `src/dark_factory/orchestrator/publish.py` (push_token param),
  `tests/support/log_sink.py`, `tests/support/live_runtime.py` and test-side
  settings overrides. None of them is on this test's path. Confirmed by the
  parent session: the test fails from the repo root and passes from a sanitized
  CWD with the fix set fully in place, so the variable is the environment, not
  the fix.

- NOT a CI problem and NOT reproducible in CI. The GitHub-hosted runner has no
  `ANTHROPIC_API_KEY`, so the credential gate stays shut and the test passes
  there. Any investigation that waits on CI to show the symptom will stall.

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-10-06T00:00:00Z
  checked: Measured the same test file both ways — the central control pair.
    Carried over from the parent session's verification (SIBLING FINDING).
  found: From a SANITIZED CWD (no readable `.env`, key unset):
    `6 passed in 0.14s`. From the REPO ROOT (where `.env` supplies
    `ANTHROPIC_API_KEY`): the test FAILS, and the full `-m "unit or contract"`
    tier reports `1 failed, 842 passed, 1 skipped, 430 deselected in 418.79s`
    versus the sanitized tier's ~37s.
  implication: The outcome is controlled entirely by ambient credential
    resolution — nothing in the test or the production code changed between the
    two runs. The ~0.14s -> 418.79s latency blowup is independent evidence that
    a real subprocess + network round-trip is happening, not merely that an
    assertion flipped. This is a measured control pair, not an inference.

- timestamp: 2026-10-06T00:00:00Z
  checked: `tests/unit/test_worker_registry_names.py` lines 42-63 — the failing
    test's body and its stated premise.
  found: Line 49-51 carries the comment "execute() never raises (WORK-04) --
    with no ANTHROPIC_API_KEY configured in this test's environment, the
    credential gate returns FAILED, not an exception". Line 52 calls
    `worker.execute({})`; line 53 asserts `result.status is
    WorkerResultStatus.FAILED`. Line 57 repeats the premise for the resume path
    and line 60 asserts FAILED again. There is NO settings override, NO
    `monkeypatch.delenv`, and NO injected worker anywhere in the test.
  implication: The premise is stated in a COMMENT and enforced NOWHERE. A
    comment is documentation, not a fixture. This is the precise defect shape,
    and it is the same shape as G-11-3's "No database:" docstrings — an author
    reasoned correctly about a precondition and then did not install it.

- timestamp: 2026-10-06T00:00:00Z
  checked: The two sibling tests in the same file (NOT yet measured — flagged
    for this session to verify).
  found: `test_copilot_resolves_to_a_real_adapter_not_a_placeholder` (lines
    66-85) and `test_hermes_resolves_to_a_real_adapter_not_a_placeholder` (lines
    89-109) have the IDENTICAL shape: a comment-stated credential premise
    (line 99-100, line 105), a bare `worker.execute({})` (lines 77, 101), and an
    `assert result.status is WorkerResultStatus.FAILED` (lines 78, 83, 102, 107).
  implication: HIGH-PRIORITY UNVERIFIED LEAD — this is probably three armed
    tests, not one, each masked by whichever credential the developer lacks.
    The parent session only observed the `claude` one firing because that is the
    key its `.env` supplied. Verify before scoping the fix; a fix that repairs
    only the `claude` test leaves two landmines of the same class.

- timestamp: 2026-10-06T00:00:00Z
  checked: Why the ambient credential is resolvable at all — the masking
    mechanism, shared with the parent session's root cause.
  found: `Settings.model_config` sets `env_file=".env"`, a CWD-RELATIVE path.
    Any run from the repo root loads the git-ignored `.env`, which on this
    machine supplies `ANTHROPIC_API_KEY`. `get_settings()` is
    `functools.lru_cache(maxsize=1)`-wrapped, so whichever test populates the
    cache first can also influence what later tests see within one process.
  implication: Same mechanism, opposite polarity, as G-11-3 — there the `.env`
    HID the bug by supplying `DATABASE_URL`; here it CAUSES the bug by supplying
    `ANTHROPIC_API_KEY`. A fix should not merely delete the ambient read for
    this one test; the class-level question is why the unit tier has no autouse
    hermeticity fixture that makes credential-absence the default and requires
    tests to opt IN to a configured credential. Note the `lru_cache` also means
    test ORDER may affect reproducibility — worth checking under
    `-p no:randomly` versus default.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: ""
fix: ""
verification: ""
files_changed: []
