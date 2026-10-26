---
status: resolved
trigger: "tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder spawns the REAL `claude` CLI — a real, billable external call — whenever ANTHROPIC_API_KEY is present in the ambient environment (e.g. via the repo-root .env), instead of being hermetic. The test asserts WorkerResultStatus.FAILED on a comment-stated premise that no credential is configured, with no injected settings override."
created: 2026-10-07T00:00:00Z
updated: 2026-10-07T00:00:00Z
symptoms_prefilled: true
goal: find_and_fix
origin: "Incidental SIBLING FINDING of debug session ci-unit-tier-settings-validation-g-11-3 (archived at .planning/debug/resolved/ci-unit-tier-settings-validation-g-11-3.md, verification SIGNAL 5 + SIBLING FINDING). Opened by explicit human decision on 2026-10-07 (\"Confirmed + both follow-ups\")."
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

status: ROOT CAUSE CONFIRMED by direct measurement (see the 2026-10-09 Evidence
entries). Entering fix_and_verify.

bug_class: CONFIRMED Bohrbug. Fully deterministic once the environment is
fixed; the apparent non-determinism was the AND-gate's condition (3) varying
per machine, not flakiness. Measured 1/1 in both polarities.

reasoning_checkpoint:
  hypothesis: "tests/unit/test_worker_registry_names.py calls execute({}) /
    resume({}, None, None) on real subprocess-spawning adapters with its
    no-credential premise stated only in a comment. When ambient credentials
    resolve (via the CWD-relative env_file='.env' read from pytest's rootdir)
    the gate opens and the real agent CLI is spawned with cwd = the live repo."
  confirming_evidence:
    - "Direct spawn capture via PATH-shadowed logging shims: claude SPAWNED,
       copilot SPAWNED, hermes not spawned — argv and cwd recorded verbatim."
    - "Both spawns recorded cwd = /Users/maryiakrauchanka/portfolio/dark-factory
       (the live tree), matching resolve_dirs' Path.cwd() fallback for a
       run_id-less context (cli_runtime.py:319-321)."
    - "Settings reports anthropic_api_key CONFIGURED and copilot_github_token
       CONFIGURED; `command -v` shows both real binaries installed."
    - "Control pair from the parent session: 6 passed in 0.14s from a sanitized
       CWD vs. 418.79s tier and a red test from the repo root."
    - "Every sibling worker-touching module (contract suite, per-adapter
       behavior suites, capabilities suite) already installs the fake_*_env
       fixture this module lacks."
  falsification_test: "If the hypothesis were wrong, the PATH-shadowed shims
    would never have been invoked — no argv log would exist — and the test would
    have failed for some other reason. Two argv logs exist. Additionally: if the
    premise WERE enforced somewhere, removing the ambient credential would not
    change the outcome; it does (0.14s pass vs. spawn)."
  fix_rationale: "Direction (b), now settled by evidence rather than judgement.
    Delete the execute({})/resume({}) calls and assert the adapter-identity
    property the tests' own names and docstrings promise (isinstance +
    capabilities()). This removes the subprocess from the unit tier OUTRIGHT
    rather than relying on a credential gate staying shut — which matters
    because evidence shows the FAILED oracle cannot even detect a breach. It
    costs nothing in coverage: tests/contract/test_coding_worker_contract.py
    already pins 'execute()/resume() never raise' for all four adapters
    hermetically, and the per-adapter behavior suites cover the rest. Addresses
    root-cause conditions (1) and (4); conditions (2) and (3) are properties of
    the product and the developer's machine and must NOT be 'fixed' in a test."
  blind_spots:
    - "Only execute() was observed spawning; resume() was never reached because
       the execute assertion blew first. resume() is armed by the same code path
       (claude/copilot _resume -> the same _spawn_and_parse) but is INFERRED,
       not measured. Removing both calls makes this moot."
    - "Did not verify the real copilot's exit status directly, so 'copilot fails
       and therefore masks' is inference from `1 failed` + a confirmed spawn.
       The spawn itself — the actual harm — is measured, so this does not affect
       the fix."
    - "The recurrence guard's blast radius against the existing suite is not yet
       measured; test_missing_claude_binary_returns_failed_without_raising
       deliberately uses an EMPTY PATH dir and is a known collision candidate
       for a PATH-based tripwire. Measure before committing to that guard shape."
  candidate_causes:
    - "code (test body): premise stated in a comment, enforced by nothing"
    - "code (test oracle): `status is FAILED` cannot detect a breach — the
       never-raise wrapper collapses gate-held and binary-ran-and-failed"
    - "config: Settings env_file='.env' is CWD-relative + get_settings is
       lru_cached"
    - "environment: developer has credential configured AND real binary on PATH;
       CI has neither"
  and_gate: "YES — all four must hold at once. CI lacks (3) so it can never see
    this. The copilot test holds (1)(2)(3) but is hidden by (4). The claude test
    holds all four and is the only one that ever went red. hermes is spared only
    by an unrelated Hermes-specific spawn-admission rule. A single-cause framing
    ('the claude test is wrong') would have fixed one of three tests and left
    the masking oracle in place."

next_action: NONE — RESOLVED. Human confirmed fixed on 2026-10-26
("Confirmed fixed"); all five guardrail signals passed (see
Resolution.verification). Fix committed as a6ca4f0, session doc as 83e59cc.
Archived to resolved/ and recorded in knowledge-base.md.

Human decision on oracle strictness: KEEP STRICT WORDING. The three repaired
`test_missing_*_binary_returns_failed_without_raising` tests retain the exact
`"No such file or directory"` errno-text assertion rather than the looser
"error merely names the binary" form. Accepted trade-off: the assertion is
pinned to CPython's `FileNotFoundError` message wording (stable, but a string
match). If a future CPython reworded it, these three tests would fail loudly
with an obvious cause — which is the preferred failure mode over an oracle weak
enough to let the original "passes for the wrong reason" defect back in.

former_bug_class_note: Previously recorded as "Likely Bohrbug with an
environment-dependent polarity — deterministic
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

- timestamp: 2026-10-09T00:00:00Z
  checked: THE DECISIVE EXPERIMENT — a zero-cost spawn detector. Wrote fake
    `claude`/`copilot`/`hermes` scripts into a scratch dir that append their
    argv + cwd to a log, prepended that dir to PATH (shadowing the real
    binaries, verified with `command -v`), and ran
    `uv run pytest -p no:randomly -q tests/unit/test_worker_registry_names.py`
    FROM THE REPO ROOT so the real `.env` was read. This reproduces the exact
    credential conditions of the bug while making a real billable call
    impossible.
  found: `2 failed, 4 passed in 0.87s`. Spawn log: **claude SPAWNED (1x),
    copilot SPAWNED (1x), hermes NOT spawned.** Both spawns recorded
    `cwd = /Users/maryiakrauchanka/portfolio/dark-factory` — the LIVE repository
    working tree. claude argv: `claude --output-format json --permission-mode
    dontAsk --model sonnet -p <prompt>`. copilot argv: `copilot --no-ask-user
    -s -p <prompt>`.
  implication: The hypothesis is CONFIRMED and the blast radius is LARGER than
    the parent session recorded, in two independent ways.
    (1) TWO tests are armed, not one. The sibling lead is confirmed for
    `copilot` and REFUTED for `hermes`.
    (2) The spawn's `cwd` is the real repo, not a disposable worktree — because
    `resolve_dirs(None)` (cli_runtime.py:319-321) falls back to `work_dir =
    Path.cwd()` when `run_id` is absent, and the bare `{}` context supplies no
    `run_id`. Combined with `--permission-mode dontAsk` / `--no-ask-user`, the
    unit tier launches a non-interactive auto-approving agent against the live
    working tree. The 418.79s the parent session measured is that agent actually
    running for ~7 minutes. This is a worse symptom than "a billable call".

- timestamp: 2026-10-09T00:00:00Z
  checked: Ambient credential + binary availability on this machine, read
    through `Settings` as booleans only (never values, per the secret guard).
  found: `anthropic_api_key: CONFIGURED`, `copilot_github_token: CONFIGURED`,
    `claude_model: CONFIGURED`. Real binaries: `claude` ->
    `~/.nvm/.../bin/claude` PRESENT, `copilot` -> `~/.nvm/.../bin/copilot`
    PRESENT, `hermes` -> ABSENT.
  implication: Both armed tests have BOTH preconditions satisfied here
    simultaneously — credential configured AND binary installed. This machine is
    the worst case, and it is a completely ordinary developer setup.

- timestamp: 2026-10-09T00:00:00Z
  checked: Why the `copilot` landmine has stayed GREEN while spawning — i.e.
    why the parent session saw `1 failed`, not `2 failed`.
  found: The assertion is `assert result.status is WorkerResultStatus.FAILED`.
    Every adapter's `execute()` is wrapped in a never-raise handler that
    converts ANY failure into `status=FAILED`. So FAILED is returned both when
    the credential gate blocks (nothing spawned) AND when the real binary is
    spawned and exits non-zero / returns unparseable output. The real `claude`
    with a valid key exits 0 with valid JSON -> COMPLETED -> assertion blows,
    which is the only reason this was ever noticed. The real `copilot` evidently
    fails (auth or flag rejection) -> FAILED -> assertion is SATISFIED while the
    binary still ran.
  implication: THIS IS THE MASKING MECHANISM, and it is a second, independent
    defect from the unenforced premise. The oracle is an implicit one (the
    weakest class) and is structurally incapable of distinguishing "gate held,
    nothing spawned" from "real agent ran and failed". A green test here is NOT
    evidence of hermeticity. Any fix that keeps `assert status is FAILED` as the
    proof of no-spawn is unsound on its face.

- timestamp: 2026-10-09T00:00:00Z
  checked: Whether the repo already has a correct idiom for this, and whether
    any OTHER test module shares the defective shape. Grepped every
    `.execute(None)` / `.execute({})` / `.resume(` call site under `tests/`.
  found: `tests/contract/test_coding_worker_contract.py` is FULLY HERMETIC and
    is the house idiom: its autouse `_fake_clis_on_path` fixture (lines 72-97)
    writes fake `claude`/`copilot`/`hermes` executables into one tmp dir,
    prepends it to PATH, and sets fake credentials via
    `fake_claude_env`/`fake_copilot_env`/`fake_hermes_env`. Its own docstring
    states the exact reasoning this bug violates: "Environment variables take
    precedence over `.env` in pydantic-settings, so this fixture behaves
    identically on a developer machine with a populated `.env` and on a CI
    runner with none." `tests/unit/test_claude_code_worker.py` and the other
    per-adapter behavior suites are hermetic by the same helpers PLUS a
    `repo_dir` fixture that `monkeypatch.chdir()`s out of the repo root (so the
    CWD-relative `env_file=".env"` resolves to nothing).
    `tests/unit/test_worker_capabilities_match_behaviour.py` is hermetic too
    (its one `execute(None)` is `FakeWorker`, which spawns nothing).
  implication: `tests/unit/test_worker_registry_names.py` is the SOLE
    non-hermetic worker-touching module in the repo — every sibling module
    already installs the fixture it lacks. The fix is not inventing a mechanism,
    it is applying an established one. Equally important: the contract suite
    ALREADY pins "execute()/resume() never raise" for all four adapters
    hermetically, which means the `execute({})`/`resume({})` calls in
    test_worker_registry_names.py contribute ZERO unique coverage. That settles
    the fix-direction question the prior session left open in favour of
    direction (b).

- timestamp: 2026-10-09T00:00:00Z
  checked: Whether `hermes` is safe by design or by accident —
    `spawn_is_permitted` (hermes.py:169-199) against the bare `{}` context.
  found: `{}` is not None, so the admission check runs:
    `getattr({}, "tools", None) or []` -> `[]` -> the first non-write-compensated
    capability in `NATIVE_TOOL_CONTRACT` is unheld -> `UnenforceableGrantError`
    is raised BEFORE `get_settings()` is reached. `_resume` routes through the
    same `_spawn_and_parse`, so both entry points are blocked. Confirmed by the
    spawn log (hermes: no log).
  implication: hermes is protected by a Hermes-SPECIFIC admission rule that has
    nothing to do with test hermeticity, and its binary is absent here anyway.
    It is one adapter-design change away from being armed, and it carries the
    identical defective test shape. Fix it alongside the other two rather than
    leaving a test whose safety rests on an unrelated invariant.

- timestamp: 2026-10-09T00:00:00Z
  checked: GUARD POSITIVE CONTROL — does the tripwire actually catch the defect?
    Wrote a throwaway module with three probes: (a) a bare
    `subprocess.run(["claude","--version"])`, (b) the EXACT code deleted from
    test_worker_registry_names.py (`default_registry.get("claude-code").execute({})`),
    and (c) a spawn-free test that must stay green.
  found: `3 passed, 2 errors in 0.40s`. Both (a) and (b) were caught by the
    teardown assertion naming the binary and the nodeid; (c) was untouched.
  implication: The guard has teeth on BOTH vectors — a direct spawn and the
    original defect shape. Two independent properties confirmed at once: the
    0.40s runtime (vs. the ~7 MINUTES the real agent took) proves the shim
    PREVENTED the real spawn, and the teardown error proves it REPORTED it.
    Prevention and detection in one mechanism. Note the breach surfaces as a
    pytest ERROR (teardown), not FAILED — the run still goes red, which is what
    matters, and unlike a non-zero shim exit it CANNOT be swallowed by the
    never-raise wrapper that masked the original copilot landmine.

- timestamp: 2026-10-09T00:00:00Z
  checked: GUARD BLAST RADIUS — ran the full `-m "unit or contract"` tier from
    the repo root with the guard installed. This is the measurement the prior
    blind_spot flagged as mandatory before committing to the guard shape.
  found: `868 passed, 1 skipped, 430 deselected, 1 error in 160.16s`. Exactly
    ONE collision:
    `tests/unit/test_unit_tier_needs_no_database.py::test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file`
    tripped the OUTER breach log naming ALL THREE binaries — including `hermes`,
    which is NOT INSTALLED on this machine. Also note the tier ran in 160s, not
    418s, confirming the removed `execute({})` calls were the latency.
  implication: The `hermes` entry is the thread to pull — hermes cannot have
    been spawned from the real PATH, so the breach must come from a process that
    resolved the OUTER tripwire dir with no INNER tripwire ahead of it. That
    narrows it to precisely the tests the prior attempt EXEMPTED: Test 1 spawns
    a child pytest tier that deliberately inherits PATH (its docstring lines
    33-39 keep PATH in the allowlist on purpose), and an exempt test gets no
    inner tripwire prepended, so the inherited outer shim is the first match.

- timestamp: 2026-10-09T00:00:00Z
  checked: THE DECISIVE FOLLOW-UP — is the exemption's premise even true? The
    prior attempt's comment claims `fake_claude_env(monkeypatch, empty_dir)`
    makes `claude` "resolve nowhere". Probed `shutil.which` directly under that
    exact context manager.
  found: FALSE. `tests/support/fake_claude_cli.py:81-82` only PREPENDS:
    `monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{existing_path}")`.
    Measured under the context manager: `which("claude")` ->
    `/Users/.../node/v24.20.0/bin/claude` (the REAL binary), `which("copilot")`
    -> the REAL binary, PATH still 18 entries deep.
  implication: `test_missing_*_binary_returns_failed_without_raising` is a
    SECOND, INDEPENDENT INSTANCE OF THE SAME ROOT-CAUSE CLASS — conditions (1),
    (3) and (4) again. It relies on the binary being absent from AMBIENT PATH, a
    premise false on any machine with the CLI installed, and it is masked by the
    same `assert status is FAILED` oracle: `fake_claude_env` injects a BOGUS key
    (`sk-ant-fake...`), so the real binary runs, fails auth, returns FAILED, and
    the assertion is satisfied. The test passes FOR THE WRONG REASON — it proves
    "real binary + bad credential -> FAILED", not "binary absent -> FAILED".
    Therefore the prior attempt's `controls_agent_binary_path` marker SILENCED A
    TRUE POSITIVE rather than resolving a false one. The guard was right and the
    exemption was wrong.
    Corrected fix: make these tests genuinely own PATH by REPLACING it with the
    empty dir. `build_worker_env` keeps "PATH" in its allowlist
    (`src/dark_factory/tools/env.py:55`) and `Popen` resolves argv[0] via
    `os.get_exec_path(env)`, so a replaced PATH makes the binary unresolvable in
    the CHILD spawn too, not merely in the parent. This makes the exemption
    UNNECESSARY BY CONSTRUCTION: a test that truly owns PATH cannot reach a real
    binary and so can never trip the wire. Delete the marker rather than keep an
    unused silencing hatch that invites exactly this misuse.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: "FOUR conditions hold simultaneously (AND-gate — removing any one
  prevents the spawn, which is why this was invisible in CI and half-invisible
  locally):
  (1) CODE/test: `tests/unit/test_worker_registry_names.py` calls
      `worker.execute({})` and `worker.resume({}, None, None)` on real
      subprocess-spawning adapters while its no-credential premise is stated
      only in a source comment (lines 49-51, 73-76, 96-100) and enforced
      nowhere — it is the one worker-touching module in the repo with no
      `fake_*_env` fixture.
  (2) CONFIG: `Settings.model_config` sets `env_file='.env'`, a CWD-RELATIVE
      path, so any pytest run from the repo root (pytest's rootdir) loads the
      developer's git-ignored `.env`; `get_settings()` is `lru_cache`d, so the
      first read is process-wide.
  (3) ENVIRONMENT: the developer has the credential configured AND the real CLI
      installed on PATH (here: both `claude` and `copilot`). CI has neither,
      which is why CI is permanently blind to this.
  (4) CODE/oracle: the assertion `status is FAILED` is an implicit oracle that
      cannot distinguish 'credential gate held, nothing spawned' from 'real
      binary spawned and failed', because every adapter's never-raise wrapper
      collapses both to FAILED. This masked the `copilot` landmine completely —
      it spawns the real CLI on every run and still reports green.
  Severity is higher than 'a billable call': because the bare `{}` context has
  no `run_id`, `resolve_dirs` falls back to `work_dir = Path.cwd()`, so the real
  agent is spawned with `cwd` = the LIVE repo working tree under
  `--permission-mode dontAsk` / `--no-ask-user`."
fix: "Three parts — the hermeticity fix, a SECOND instance of the same class
  found by measuring the guard, and the guard itself.
  (A) tests/unit/test_worker_registry_names.py — direction (b): DELETED the six
      `execute({})` / `resume({}, None, None)` calls and their
      `assert status is FAILED` oracles from all three adapter tests, keeping
      the `isinstance` + `capabilities()` assertions that the tests' own names
      promise. `default_registry.get()` returning an instance of the real class
      IS the proof of 'not a placeholder' (a placeholder factory raised
      `NotImplementedError` when invoked), so the subprocess was never needed.
      Zero coverage lost: tests/contract/test_coding_worker_contract.py already
      pins 'execute()/resume() never raise' for all four adapters hermetically.
  (B) tests/unit/test_{claude_code,copilot,hermes}_worker.py —
      `test_missing_*_binary_returns_failed_without_raising` was a SECOND
      INSTANCE of the same root cause, found only because the guard's blast
      radius was measured. `fake_*_env(monkeypatch, empty_dir)` only PREPENDS
      (fake_claude_cli.py:81-82), so the real binary stayed resolvable and the
      test passed for the WRONG REASON — real binary + the helper's bogus
      `sk-ant-fake...` key -> FAILED, satisfying the same masking oracle. Fixed
      by REPLACING PATH (`monkeypatch.setenv(\"PATH\", str(empty_dir))`), which
      works through to the spawn because `build_worker_env` keeps PATH in its
      allowlist (tools/env.py:55) and `Popen` resolves argv[0] via
      `os.get_exec_path(env)`. Oracle HARDENED from implicit to derived: now
      also asserts the error names the binary and 'No such file or directory',
      so a revert to a prepend fails loudly instead of passing.
  (C) tests/conftest.py — added the `_no_real_agent_binary_spawn` autouse
      tripwire (+ session-scoped `_agent_tripwire_dir`): PATH-prepends shims
      named after all three agent CLIs that record a breach TO A FILE and exit
      97, with a teardown assertion naming the nodeid and binary. The breach is
      recorded to a file rather than signalled by the non-zero exit precisely
      because the adapters' never-raise wrapper would otherwise swallow it into
      the same `assert status is FAILED` that masked the original copilot half.
      Prevention and detection in one mechanism: the shim also stops the real
      spawn. `integration` is the ONLY exemption. The `controls_agent_binary_path`
      opt-out marker the first attempt added was DELETED from conftest.py,
      pyproject.toml and the three test modules — it had silenced the true
      positive in (B), and a test that truly owns PATH by replacing it can
      never reach a real binary and so needs no exemption by construction."
verification: |
  guardrail_verdict: accepted

  SIGNAL 1 — original symptom gone / bug returns on revert: PASS.
    The `unit or contract` tier from the repo root WITH credentials present ran
    `863 passed, 1 skipped, 0 failed, 0 error in 136.55s` — versus the symptom's
    `1 failed ... in 418.79s`. The 418s->136s collapse is the removed agent
    subprocesses. Revert polarity was established by the parent session's
    measured control pair (0.14s sanitized vs. spawn from repo root).
  SIGNAL 2 — guard positive control (teeth), measured TWICE: PASS.
    Throwaway probes for (a) a bare `subprocess.run(["claude","--version"])` and
    (b) the EXACT deleted code `default_registry.get("claude-code").execute({})`
    were both caught by the teardown assertion, while a spawn-free test stayed
    green (`3 passed, 2 errors in 0.40s`). Re-run AFTER the exemption marker was
    deleted: still `3 passed, 2 errors in 1.20s`. The 0.40s runtime (vs. ~7
    MINUTES for the real agent) proves the shim PREVENTED the spawn as well as
    reported it.
  SIGNAL 3 — the repaired tests now pass for the RIGHT reason: PASS.
    Probed directly: under the replaced PATH, `shutil.which("claude")` is None
    and the error is `[Errno 2] No such file or directory: 'claude'` (same for
    copilot and hermes) — the genuine missing-binary path. Before the fix the
    same test saw an AUTH failure from the real binary. The hardened derived
    oracle now pins this.
  SIGNAL 4 — blast radius / no masking: PASS, and this signal EARNED ITS KEEP.
    The first full-tier run surfaced exactly one collision
    (`test_unit_tier_needs_no_database.py::test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file`
    naming claude, copilot AND hermes — hermes being UNINSTALLED here was the
    thread that unravelled it) which turned out to be a TRUE POSITIVE exposing
    defect (B), not guard noise. After fixing (B) and deleting the exemption:
    that test is `3 passed`, and the tier is collision-free.
  SIGNAL 5 — lint/type gates: PASS. `ruff check` clean and `ruff format` clean
    on all five changed files. CI's type gate is `mypy src/dark_factory`; no
    `src` file was touched. Its 2 remaining errors (`mcp.server` import-not-found)
    and the test-file `resume(object)` / conftest `unused-ignore` findings are
    all PRE-EXISTING — the conftest `type: ignore` is HEAD line 346 merely
    shifted down by the added block, and tests are not in CI's type gate.
  CONFOUND CONTROLLED: the working tree carries other concurrent debug sessions'
    in-flight edits. A transient `2 failed` naming `..sums_and_redacts_secrets`
    (redaction code another session was mid-edit on, mtime 15:17:21 landing
    INSIDE my run window) and a collected-count drift of 863->865->866 across
    runs were both traced to that, NOT to this fix: my four modules' test counts
    are byte-identical to HEAD (6/53/34/28), the child tier re-run clean at
    `866 passed, 0 failed`, and the collision test re-run `3 passed`.
files_changed:
  - "tests/unit/test_worker_registry_names.py: deleted the six execute()/resume() calls + their FAILED oracles; module docstring now records why this module spawns nothing"
  - "tests/unit/test_claude_code_worker.py: REPLACE PATH instead of relying on fake_claude_env's prepend; oracle hardened to assert the errno text; controls_agent_binary_path marker removed"
  - "tests/unit/test_copilot_worker.py: same PATH replacement + hardened oracle; marker removed"
  - "tests/unit/test_hermes_worker.py: same PATH replacement + hardened oracle; marker removed"
  - "tests/conftest.py: added _agent_tripwire_dir + _no_real_agent_binary_spawn recurrence guard; integration is the sole exemption"
  - "pyproject.toml: NO NET CHANGE — the controls_agent_binary_path marker was added then removed, returning the file to its HEAD state"
