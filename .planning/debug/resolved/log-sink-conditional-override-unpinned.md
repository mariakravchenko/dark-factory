---
status: resolved
trigger: "The absence-conditional override in tests/support/log_sink.py::real_log_sink (supply fake DATABASE_URL/DATABASE_URL_DIRECT only when ABSENT, never clobber an already-set value) is correct but pinned by NO test: mutating it to an unconditional override left tests/unit/test_log_redaction.py fully green (4 passed). Mechanism: events/redaction.py's pattern rule for postgres://...@... URLs masks the exact-value path, so those assertions prove PATTERN redaction only, not KNOWN-SECRET exact-value redaction."
created: 2026-10-07T00:00:00Z
updated: 2026-10-09T00:00:00Z
symptoms_prefilled: true
goal: find_and_fix
origin: "Incidental MUTANT 1 finding of debug session ci-unit-tier-settings-validation-g-11-3 (archived at .planning/debug/resolved/ci-unit-tier-settings-validation-g-11-3.md, verification MUTANT 1). Opened by explicit human decision on 2026-10-07 (\"Confirmed + both follow-ups\"). Note this finding CORRECTED a claim the parent session's own file had asserted."
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

bug_class: Test-sensitivity gap (a surviving mutant), not a runtime defect. No
production behaviour is currently wrong; the defect is that a correct safety
property is UNDETECTED if broken, and that a test believed to prove known-secret
redaction actually proves something weaker.

status: INVESTIGATED, FIXED, SELF-VERIFIED — awaiting human confirmation. The
root cause is an AND-gate of two test-design conditions (see Resolution); the
remedy is test-only, all three mutants now die, and the reported symptom (B) was
corrected by measurement. The parent session classified this as a
test-sensitivity gap rather than a blocker, because the G-11-3 property itself is
pinned by its own Signals 1-3 — that classification held up.

hypothesis (CONFIRMED; kept verbatim below as the seeded starting point, with the
one over-strong clause corrected in Resolution.root_cause): Two layered facts.

(1) MEASURED. `tests/support/log_sink.py::real_log_sink` deliberately supplies
fake `DATABASE_URL`/`DATABASE_URL_DIRECT` ONLY when they are absent (see its
`supplied` list, `log_sink.py:68-74`), so it cannot clobber a value a test set
intentionally. Mutating that to an UNCONDITIONAL override left
`tests/unit/test_log_redaction.py` green — 4 passed. The mutant SURVIVED. So
nothing detects the clobbering, and the parent file's own CONSTRAINT claim
("...or those three tests become vacuous") is WRONG as written.

(2) MEASURED MECHANISM. `src/dark_factory/events/redaction.py` carries a PATTERN
rule — `re.compile(r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s@]+@\S+")` ->
`"[redacted:database_url]"`, the FIRST entry in `_PATTERNS` — which matches
`test_log_redaction.py`'s `FAKE_LIVE_DB_URL`
(`postgresql+psycopg://real:l1vepass@prod-host.example/darkfactory`) regardless
of whether that value is in `known_secrets`. The pattern layer therefore MASKS
the exact-value layer for any postgres-shaped URL. Consequence:
`test_live_known_secret_value_never_reaches_the_sink` (line 79) passes via the
pattern rule even if known-secret exact-value redaction were entirely broken.

OPEN QUESTION (the actual work): what should pin the exact-value layer? The
redaction module has TWO independent defences and the test suite currently
cannot distinguish them. A secret whose shape matches no pattern (the whole
point of the `known_secrets` mechanism) has no coverage demonstrated here.

test (next step): construct a known secret that does NOT match any `_PATTERNS`
entry (e.g. an opaque high-entropy value with no URL/token shape), assert it is
scrubbed, and verify THAT test fails when the known-secret path is disabled —
i.e. build a test the pattern layer cannot rescue. Then separately pin the
`log_sink.py` conditional with a test that fails if the override becomes
unconditional.
expecting: an opaque-value test will fail under a disabled known-secret path
(proving it isolates the right layer), whereas the existing `FAKE_LIVE_DB_URL`
tests will not.

next_action: NONE pending in this session — all three steps DONE (Step 1
isolation experiment; Step 2 the three pins; Step 3 the rename), and the
fix-acceptance guardrail passed on all five signals (Resolution.verification).
RE-VERIFIED 2026-10-09 after a rate-limit interruption cut the previous spawn
off mid-handoff: working-tree edits confirmed to match Resolution.fix 1-6, and
all non-mutation signals re-run and still green (see the
`signal_re_verification` block at the end of Resolution.verification — one
delta found, attributed, and NOT mine). Awaiting the human-verify checkpoint
response. If the user reports the fix is NOT good enough, resume at
Resolution.verification's signal list rather than re-running the isolation
experiment or the three mutants — all are already measured and recorded, and
re-mutating shared files in this non-hermetic tree is the riskier path.

reasoning_checkpoint:
  hypothesis: "Exactly two properties are unpinned, and one test kills both.
    (A) `real_log_sink`'s absence-conditional is unpinned because NO test ever
    observes the environment or `Settings` from inside the context manager —
    every existing test only looks at the sink's text, and the sink's text is
    identical either way because the pattern layer redacts any postgres-shaped
    URL regardless of which one `Settings` actually loaded. (B') The
    Settings->known_secret_values->processor->sink COMPOSITION is unpinned for
    pattern-immune values, because the only test file exercising that wiring
    uses exclusively pattern-rescuable fixtures."
  confirming_evidence:
    - "MEASURED: disabling `_scrub_known` entirely left test_log_redaction.py at
      4 passed (baseline also 4 passed) — direct observation, not inference."
    - "MEASURED: the same mutant kills 16 tests elsewhere in tests/unit,
      including test_redaction.py:271 which already pins the pure-function
      exact-value property — so the gap is the WIRING, not the function."
    - "READ: every `FAKE_LIVE_DB_URL` assertion in test_log_redaction.py asserts
      only on `buffer.getvalue()`; none touches `os.environ` or `get_settings()`
      inside the `with real_log_sink()` block."
    - "MEASURED: `_PATTERNS[0]` requires an `@`, so a credential-free DSN is
      pattern-immune while staying a realistic DATABASE_URL value."
  falsification_test: "If, after adding the three tests, making `real_log_sink`'s
    override unconditional still leaves the file green, hypothesis (A) is wrong
    about the mechanism. If disabling `_scrub_known` still leaves the file green,
    hypothesis (B') is wrong. Both mutants must now DIE — and the pattern test
    must still PASS under the `_scrub_known` mutant, proving the layers are
    genuinely separated rather than all newly coupled to one layer."
  fix_rationale: "Addresses the root cause (fixtures chosen so that one defence
    masks the other, and assertions aimed only at the sink's text) rather than
    the symptom. The new pattern-immune fixture removes the masking; the new
    env/Settings assertions remove the blind spot about which value Settings
    loaded. The self-validating guard `redact(v, known_secrets={}) == v` makes
    the pattern-immunity a CHECKED precondition instead of a comment, so the
    trap cannot silently re-form when `_PATTERNS` is next broadened."
  blind_spots: |
    Declared before the fix, then each one closed or consciously accepted:
      - "cross-test leakage under randomised ordering" — MOOT, measured:
        pytest-randomly is NOT installed in this project (`-p randomly` ->
        ImportError: No module named 'randomly'), so collection order is
        deterministic. Leakage was instead checked by running the file alone, in
        a 5-file group, and inside the whole `tests/unit` tier: no leakage.
      - "a credential-free DSN might trip a pattern row added by the CONCURRENT
        session editing redaction.py" — STILL OPEN BY DESIGN, and deliberately
        converted from a silent risk into a loud one: the guard assertion
        `redact(FAKE_OPAQUE_DB_URL, known_secrets={}) == FAKE_OPAQUE_DB_URL`
        fails immediately if any future `_PATTERNS` change starts matching it.
        Re-verified against that session's landed `_CHECKSUM_KEYS` work.
      - NEWLY FOUND, accepted and attributed: the working tree is non-hermetic
        (multiple concurrent debug sessions mutating `conftest.py` /
        `redaction.py`), so a full-tier run here cannot be read as a clean
        regression signal without per-failure attribution. Handled in
        verification signal 5 rather than ignored.
      - NOT covered and out of scope: the `patterns=False` /
        `scrub_known_values()` path (persisted task text) is untouched by this
        work; it has its own coverage in `tests/unit/test_redaction.py`.
  candidate_causes:
    - "code/test-design: fixture value chosen such that a second defence masks
      the layer under test (the actual cause)"
    - "code/test-design: assertions scoped only to the sink's output, never to
      the env/Settings state the helper is responsible for (the actual cause of
      (A) specifically)"
    - "environment: `real_log_sink` mutates real process env rather than using
      monkeypatch, so correctness depends on absent-vs-present env state that no
      test asserts"
    - "data: `Settings.known_secret_values()` silently skips values under 8
      chars, so a too-short fixture would make any new test vacuous too"
  and_gate: "YES — this failure genuinely required TWO conditions
    simultaneously, which is why it survived review. Condition 1: the fixture is
    pattern-shaped (so the pattern layer rescues the assertion). Condition 2:
    the assertions observe only the sink text (so a substituted env value is
    invisible). Break EITHER and mutant (A) dies. That is why the remedy must
    change both the fixture and the observation surface, and why a single new
    assertion would not have been enough."

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: Two distinct properties should each be pinned by a test that fails
when that property breaks.
  (A) `tests/support/log_sink.py::real_log_sink` must never clobber a
      `DATABASE_URL`/`DATABASE_URL_DIRECT` value a test set on purpose — it
      supplies fakes only to make `Settings` constructible when the vars are
      ABSENT. If that conditional is removed, some test should go red.
  (B) `src/dark_factory/events/redaction.py`'s KNOWN-SECRET (exact-value)
      redaction must be demonstrated independently of its PATTERN rules, since
      the two are separate defences and known-secrets exists precisely to catch
      values that match no pattern.

actual: Neither property is pinned.
  (A) Making the override unconditional (removing the absence guard) left
      `tests/unit/test_log_redaction.py` at 4 passed. The mutant survived; no
      test anywhere detected the clobbering.
  (B) `test_live_known_secret_value_never_reaches_the_sink`
      (`tests/unit/test_log_redaction.py:79`) logs `FAKE_LIVE_DB_URL` and
      asserts it is absent from the sink — but that value is postgres-shaped, so
      `_PATTERNS[0]` redacts it on shape alone. The assertion would hold even
      with known-secret redaction fully disabled. The test's NAME claims the
      known-secret property; its mechanism only demonstrates the pattern
      property.

errors: none — nothing fails. That is the symptom: a safety property and a
believed-covered defence are both invisible to the suite. This is a surviving
mutant, which has no error text by construction.

reproduction:
  For (A): in `tests/support/log_sink.py`, make the `supplied` list
  unconditional (always override both vars rather than only when absent), then
  run `uv run pytest -q tests/unit/test_log_redaction.py`. Observed: 4 passed —
  the mutant survives. Restore the file afterward.
  For (B): the masking is visible by inspection —
  `FAKE_LIVE_DB_URL = "postgresql+psycopg://real:l1vepass@prod-host.example/darkfactory"`
  (`tests/unit/test_log_redaction.py:22`) matches `_PATTERNS[0]`'s
  `(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s@]+@\S+`. The confirming experiment —
  disable the known-secret path and show these tests STILL pass — has not yet
  been run and is this session's first task.

started: Discovered 2026-10-06 during the verification phase of debug session
ci-unit-tier-settings-validation-g-11-3 (MUTANT 1). The `log_sink.py`
conditional itself was introduced by gap-closure plan 11-09 as the SINK A fix
for G-11-3, so the unpinned-ness dates from 2026-10. The redaction layer-masking
is older and independent of that plan — `FAKE_LIVE_DB_URL` and the pattern rule
both predate it.

## Eliminated
<!-- APPEND only - prevents re-investigating -->

- NOT a production defect, and NOT a reason to change the `log_sink.py`
  conditional. The absence-guard is CORRECT and worth keeping — a test that sets
  `DATABASE_URL` to a value it then asserts is scrubbed must not have that value
  silently replaced. The parent session's conclusion was "keep the conditional,
  pin it", not "remove it".

- NOT a reason to weaken or remove the pattern rule in `_PATTERNS[0]`. Defence in
  depth is intentional: the pattern rule catching postgres URLs on shape alone is
  a feature (it also catches URLs that were never registered as known secrets,
  cf. WR-06's note about passwords containing special characters). The problem is
  only that the pattern layer's success HIDES whether the exact-value layer works
  — a test-design problem, not a redaction-design problem.

- NOT the cause of any G-11-3 failure, and not a blocker for it. The G-11-3
  property is independently pinned by its own verification Signals 1-3
  (sanitized full-tier child, positive control, and a revert-mutant that
  reproduced the original 5 failures byte-for-byte).

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-10-06T00:00:00Z
  checked: MUTATION EXPERIMENT — dropped the absence guard in
    `tests/support/log_sink.py`, making the fake-value override unconditional,
    then ran `tests/unit/test_log_redaction.py`. Carried over from the parent
    session (MUTANT 1).
  found: 4 passed. The mutant SURVIVED.
  implication: The conditional is unpinned — if a future refactor makes the
    override unconditional, no test will say so. This also DISPROVED the parent
    debug file's own written CONSTRAINT that those tests would "become vacuous";
    they do not become vacuous, and worse, nothing detects the change. Recorded
    here because a claim that was asserted and then measured-false is exactly
    the kind of fact that must not be lost to an archive.

- timestamp: 2026-10-06T00:00:00Z
  checked: WHY the mutant survived — `src/dark_factory/events/redaction.py`'s
    `_PATTERNS` list versus `tests/unit/test_log_redaction.py:22`'s fixture
    value.
  found: `_PATTERNS[0]` is
    `(re.compile(r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s@]+@\S+"),
    "[redacted:database_url]")` — deliberately broad, with the credential span
    `[^\s@]+` so a password containing `/` or `:` cannot defeat the match
    (comment cites WR-06). `FAKE_LIVE_DB_URL` is
    `postgresql+psycopg://real:l1vepass@prod-host.example/darkfactory`, which
    matches that pattern.
  implication: Mechanism identified, observed not inferred: for ANY
    postgres-shaped URL the pattern layer fires regardless of `known_secrets`
    membership, so substituting a different fake DB URL changes nothing
    observable. The exact-value layer is shadowed for precisely the fixture
    value the tests chose.

- timestamp: 2026-10-06T00:00:00Z
  checked: Which tests in `tests/unit/test_log_redaction.py` depend on the
    DB-URL fixture, and what each claims to prove.
  found: `FAKE_LIVE_DB_URL` is set via `monkeypatch.setenv` in three tests —
    `test_pattern_shaped_secret_in_log_event_is_redacted` (line 50, sets it at
    53-54), `test_live_known_secret_value_never_reaches_the_sink` (line 79, sets
    it at 82-83, logs it at 93, asserts `FAKE_LIVE_DB_URL not in output` at 99),
    and `test_sink_helper_restores_previous_configuration` (line 103, sets it at
    106-107).
  implication: The first test's name is HONEST — it claims the pattern property
    and proves it. The second's name claims the KNOWN-SECRET property but its
    assertion is satisfiable by the pattern layer alone, so the name overstates
    what it demonstrates. The third is about sink-config restoration and only
    incidentally uses the value. So the remedy is narrower than "rewrite the
    file": one test needs a non-pattern-shaped value (or a sibling that uses
    one), and arguably a rename.

- timestamp: 2026-10-06T00:00:00Z
  checked: The shape of the thing that needs pinning in
    `tests/support/log_sink.py`.
  found: `real_log_sink()` (line 58) builds a `supplied: list[str]` (line 68) of
    only those of `DATABASE_URL`/`DATABASE_URL_DIRECT` that are absent, sets just
    those (line 71-72), calls `get_settings.cache_clear()` when it supplied
    anything (line 73-74), and on exit restores/unsets exactly what it supplied
    and clears the cache again (lines 80-83). The fakes themselves are
    `_FAKE_DATABASE_URL` / `_FAKE_DATABASE_URL_DIRECT` (lines 42-46).
  implication: The pinning test is cheap to write and does not need the redaction
    layer at all: enter `real_log_sink()` with `DATABASE_URL` already set to a
    sentinel and assert `os.environ["DATABASE_URL"]` is still that sentinel
    inside the context (and that `get_settings()` reflects it). That isolates
    property (A) from property (B) entirely, which is the cleanest decomposition
    and avoids re-entangling the two layers that caused this confusion.

- timestamp: 2026-10-09T00:00:00Z
  checked: THE ISOLATION EXPERIMENT the parent session inferred but never ran.
    Commented out `value = _scrub_known(value, known_secrets)` in
    `src/dark_factory/events/redaction.py::_redact_str` (known-secret exact-value
    layer fully disabled, pattern layer untouched), then ran
    `uv run pytest -q tests/unit/test_log_redaction.py`.
  found: 4 passed. Baseline before the mutation was also 4 passed.
  implication: LAYER MASKING CONFIRMED BY MEASUREMENT, not inference. Every
    secret assertion in `test_log_redaction.py` is satisfiable by the pattern
    layer alone. `test_live_known_secret_value_never_reaches_the_sink` passes
    with known-secret redaction entirely removed, so its name is measurably
    false advertising. The parent session's claim is now observed, not deduced.

- timestamp: 2026-10-09T00:00:00Z
  checked: SCOPE of that same mutant across the whole unit tier (`uv run pytest
    -q tests/unit`), to find out whether the exact-value layer is pinned
    ELSEWHERE rather than nowhere.
  found: 16 failed, 805 passed. Killers include
    `tests/unit/test_redaction.py::test_known_secret_value_is_substituted_even_without_a_pattern`
    (line 271, uses `"s3cr3t-not-a-pattern-value-1234"`),
    `test_longer_known_value_wins_over_a_shorter_substring`,
    `test_patterns_false_keeps_doc_style_uri_but_scrubs_known_value`, five
    `test_claude_code_worker.py` redaction tests (`sk-ant-fake...` matches no
    pattern), three `test_quality_gate.py` tests, plus `test_git_push.py`,
    `test_github_client.py`, `test_hermes_worker.py`,
    `test_unit_tier_needs_no_database.py`, `test_worker_registry_names.py`.
  implication: CORRECTS THE SYMPTOM AS WRITTEN. Symptom (B) — "known-secret
    exact-value redaction is not demonstrated independently of the pattern
    rules" — is TOO STRONG. At the `redact()` function level the property is
    already well pinned (16 killers). The genuine gaps are narrower and there
    are exactly two:
      (A) the `log_sink.py` absence-conditional — still a surviving mutant, the
          only truly unpinned property, and the real bug here; and
      (B') the COMPOSITION at the sink — Settings env var ->
          `known_secret_values()` -> structlog `_redaction_processor` -> real
          `StringIO` sink — for a value no pattern can rescue.
          `test_redaction.py` pins the pure function but never the wiring;
          `test_log_redaction.py` pins the wiring but only with
          pattern-rescuable values. No test covers the intersection.
    This matters for the remedy: (B') is not a duplicate of
    `test_redaction.py:271`, and it is the SAME test that kills mutant (A),
    because the only reason the conditional exists is to let a test-set
    `DATABASE_URL` reach `Settings`.

- timestamp: 2026-10-09T00:00:00Z
  checked: Whether a REALISTIC `DATABASE_URL` can be pattern-immune, so the
    (B') fixture does not have to be an unrealistic non-URL blob.
  found: Yes. `_PATTERNS[0]` requires an `@` (`[^\s@]+@\S+`) because it targets
    URIs carrying EMBEDDED CREDENTIALS. A credential-free DSN such as
    `postgresql://host.invalid:5432/db` (password supplied out-of-band via
    `PGPASSWORD`) is a perfectly valid Postgres URL that the pattern cannot
    match. Verified it also trips no other row: no `github_pat_`/`gh[porsu]_`
    prefix, no 40-or-64-char hex run for `_HEX_TOKEN`, no bearer header, and no
    `_SENSITIVE_KEYS` word followed by `:`/`=` for the generic kv rule.
  implication: The (B') fixture can be a realistic credential-free DSN rather
    than an artificial blob. More importantly this suggests the SELF-VALIDATING
    GUARD that stops the masking trap from ever re-forming: assert
    `redact(value, known_secrets={}) == value` — with no known secrets only the
    pattern layer runs, so an unchanged return PROVES the fixture is invisible
    to patterns, using public API only. Any future broadening of `_PATTERNS`
    that starts catching credential-free DSNs then fails this guard LOUDLY
    instead of silently re-masking the exact-value assertion.

- timestamp: 2026-10-09T00:00:00Z
  checked: Concurrency hazard — `git status` while preparing the fix.
  found: `src/dark_factory/events/redaction.py` is MODIFIED IN THE WORKING TREE
    by a concurrent debug session (`checksum-redaction-false-positive-in-error-
    payload`, which added `_CHECKSUM_KEYS` / `_SHA256_DIGEST`). The file changed
    underneath this session between the mutant and its restore; the restore was
    verified clean afterwards (`_scrub_known` present at line 212, no MUTANT
    marker).
  implication: This session must NOT edit `redaction.py`. The whole remedy is
    expressible in `tests/unit/test_log_redaction.py` plus (docs-only)
    `tests/support/log_sink.py`, so there is no collision. The guard assertion's
    use of public `redact()` rather than the private `_PATTERNS` list is doubly
    right here: it stays correct across the concurrent session's edits.

- timestamp: 2026-10-09T00:00:00Z
  checked: RE-VERIFICATION after a rate limit interrupted the prior spawn
    mid-handoff (before it could present the checkpoint). Re-ran every
    NON-mutation signal and diffed the working tree against Resolution.fix 1-6.
    Deliberately did NOT re-run the three mutation experiments: they are already
    measured and recorded, and re-mutating shared files (`redaction.py`,
    `log_sink.py`) in a tree that several concurrent sessions are editing is the
    riskier path for no new information.
  found: Working-tree edits match Resolution.fix items 1-6 exactly (227 insertions
    / 13 deletions across the two files; `FAKE_OPAQUE_DB_URL` present,
    `redact(v, known_secrets={})` guards on all three secret fixtures, both new
    tests present, the rename done, the `log_sink.py` docstring corrected).
    Focused run: 9 passed (recorded: 9). Static gates: `ruff check` clean,
    `ruff format --check` 2 files already formatted, `mypy --strict` Success —
    all three identical to the record. ONE DELTA in the 5-file combined run:
    113 passed + 1 error, where the record says 102 passed.
  implication: The fix holds; the delta is fully explained and none of it is
    mine. (i) 102 -> 113 is test COUNT GROWTH, not breakage — concurrent sessions
    added tests to `test_redaction.py` / `test_settings.py`, both of which show
    as modified in `git status`. (ii) The 1 error is
    `test_unit_tier_needs_no_database.py` — the aggregating guard test already
    named as known-not-mine in verification signal 5. Re-attributed from scratch
    rather than assumed, two independent ways, in the re-verification block
    below. The clean subset (the same 4 files minus that aggregator) is 110
    passed.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  An AND-gate of two test-design conditions, both required — which is why this
  survived review and why the parent session's single-cause framing was wrong.

  CAUSE 1 (fixture choice → layer masking). Every secret fixture in
  `tests/unit/test_log_redaction.py` was a credential-bearing postgres URL, a
  shape `_PATTERNS[0]` matches unconditionally. The pattern layer therefore
  satisfied every assertion on its own, so the known-secret exact-value layer —
  and with it the question of WHICH `DATABASE_URL` value `Settings` actually
  loaded — was unobservable through the sink. MEASURED: deleting `_scrub_known`
  entirely left the file at 4 passed.

  CAUSE 2 (observation surface). Every assertion in the file read only
  `buffer.getvalue()`. No test ever looked at `os.environ` or `Settings` from
  inside the `with real_log_sink()` block, which is the only place the helper's
  absence-conditional has an observable effect.

  Either condition alone would have been survivable: a pattern-immune fixture
  makes the substituted value visible in the sink; an env/Settings assertion
  makes it visible directly. Both held simultaneously, so mutating
  `real_log_sink`'s per-variable absence guard to an unconditional override was
  invisible to the entire suite.

  CORRECTION TO THE REPORTED SYMPTOM: symptom (B) as filed ("known-secret
  exact-value redaction is not demonstrated independently of the pattern
  rules") is too strong and was disproved by measurement. At the `redact()`
  function level that property is already well pinned — disabling
  `_scrub_known` kills 16 unit tests, including
  `tests/unit/test_redaction.py::test_known_secret_value_is_substituted_even_without_a_pattern`.
  The real gap was the COMPOSITION (env var -> `known_secret_values()` ->
  `_redaction_processor` -> real sink) for a pattern-immune value: the pure
  function was pinned, the wiring was pinned, their intersection was not.

fix: |
  Test-only. No production source changed — notably NOT
  `src/dark_factory/events/redaction.py` (a concurrent debug session owned that
  file) and NOT `real_log_sink`'s conditional, which was correct all along and
  is now pinned rather than altered.

  1. `tests/unit/test_log_redaction.py` — added `FAKE_OPAQUE_DB_URL`, a
     CREDENTIAL-FREE DSN (`postgresql://df-pin-host.invalid:5432/...`). Realistic
     (password out-of-band via `PGPASSWORD`) yet pattern-immune, because
     `_PATTERNS[0]` requires an `@` — it targets URIs carrying embedded
     credentials. Only exact-value substitution can remove it from a log line.
  2. SELF-VALIDATING PRECONDITION GUARDS on every secret fixture, using public
     API only: `redact(v, known_secrets={}) == v` proves pattern-immunity (no
     known secrets => only the pattern layer runs), `!= v` proves
     pattern-matchedness. This converts "which layer does this test exercise?"
     from a comment into a checked assertion, so the masking cannot silently
     re-form when `_PATTERNS` is next broadened — it fails loudly instead. This
     is the durable part of the fix.
  3. NEW `test_known_secret_value_no_pattern_can_rescue_never_reaches_the_sink`
     — pins the previously-unpinned composition, and is the end-to-end killer
     for the original mutant. Leaves `DATABASE_URL_DIRECT` deliberately ABSENT
     so the MIXED presence case is the one exercised.
  4. NEW `test_sink_helper_supplies_only_absent_database_vars_and_restores`,
     parametrized over all four cells of the presence matrix (both / only-pooled
     / only-direct / neither). Observes `os.environ` AND `Settings` from inside
     the context — the blind spot of cause 2 — and asserts post-exit restoration.
     Uses no redaction at all, keeping the two entangled properties decomposed.
     `neither-preset` is the original G-11-3 constructibility property.
  5. RENAMED `test_live_known_secret_value_never_reaches_the_sink` ->
     `test_pattern_shaped_database_url_from_env_never_reaches_the_sink`, with a
     docstring recording that the old name claimed a property it measurably did
     not test.
  6. `tests/support/log_sink.py` — docstring only. Replaced the parent session's
     measurably-false claim (that an unconditional override would make those
     redaction assertions "vacuous") with the measured truth (the mutant
     SURVIVED, and why), and named the two tests that now pin the conditional.

verification: |
  guardrail_verdict: accepted

  signal_1_regression_test_fails_before_fix (MUTATION, the decisive signal):
    MUTANT 1 — `real_log_sink`'s override made unconditional (`supplied =
    list(_REQUIRED_ENV_VARS)`), the exact mutation that SURVIVED at 4 passed
    before this fix: now 4 failed, 5 passed. Killed by the new composition test
    and by three of the four matrix cells. MUTANT DEAD.
    MUTANT 2 — all-or-nothing instead of per-variable (supply both whenever
    either is absent), a subtler mutant never previously considered: 3 failed,
    6 passed. Killed precisely by the two MIXED cells, with `both-preset`
    correctly unaffected — which validates the boundary-matrix design rather
    than just the headline case.
    MUTANT 3 — `_scrub_known` deleted from `_redact_str`: exactly ONE test fails
    (`...no_pattern_can_rescue...`) while both pattern tests still PASS. This was
    the pre-registered falsification criterion and it held: the layers are
    genuinely decomposed, not newly all-coupled to one layer. All three mutants
    reverted and verified clean (`grep MUTANT src tests` -> only prose).

  signal_2_fix_addresses_root_cause: Both AND-gate conditions are removed. Cause
    1 by a pattern-immune fixture plus the guard assertions; cause 2 by
    assertions on `os.environ`/`Settings` inside the context. The guards also
    make the failure mode self-reporting in future.

  signal_3_no_regression: `tests/unit/test_log_redaction.py` 4 -> 9 passed.
    Combined run of test_log_redaction + test_redaction + test_settings +
    test_config_module_isolation + test_unit_tier_needs_no_database: 102 passed.
    That last one spawns the whole `unit or contract` tier in a child process
    with DATABASE_URL/DATABASE_URL_DIRECT stripped and no readable `.env`, so the
    new tests are additionally proven in a genuinely credential-free process —
    which is exactly the G-11-3 environment the helper exists for.

  signal_4_static_gates: `ruff check` clean, `ruff format --check` clean
    (2 files already formatted), `mypy` (strict) Success on both changed files.

  signal_5_known_flake_attribution (NOT my change — proven, not assumed):
    A full `tests/unit` run shows 3 errors in
    `test_{claude_code,copilot,hermes}_worker.py::test_missing_*_binary_...`
    plus the guard test that aggregates them. These are a CONCURRENT debug
    session's in-flight work (`claude-cli-test-spawns-real-binary-with-key-
    present`), which is adding an agent-tripwire fixture to `tests/conftest.py`.
    Attribution evidence, three independent ways:
      (a) `git stash push` of ONLY my two files -> all 3 tests pass; stash
          popped and re-verified.
      (b) The errors FLAPPED mid-session as that session edited conftest.py:
          absent (3 passed) -> present (3 errors), while my files never changed.
      (c) `git status` shows `tests/conftest.py` with 102 uncommitted inserted
          lines and 9 `tripwire` hits; the failing assertion's own text is from
          that new fixture, and it concerns agent-binary PATH resolution with no
          relation to redaction or `log_sink`.
    Also worth recording as a METHOD hazard for future sessions in this repo:
    several debug sessions run concurrently against one working tree and mutate
    SHARED test infrastructure (`conftest.py`, `redaction.py`). Verification here
    is not hermetic; attribute every unexpected failure before acting on it. My
    own mutant on `redaction.py` was restored by inverse textual edit rather than
    `cp` from backup for exactly this reason, which preserved that session's
    concurrent `ruff format` reflow (verified: the only delta from my backup was
    its own reformatting).

  signal_re_verification (2026-10-09, after the rate-limit interruption):
    Re-ran all NON-mutation signals; the three mutants were deliberately not
    re-run (already measured; re-mutating shared files in this non-hermetic tree
    risks damage for no new information).
      * Working-tree edits vs Resolution.fix 1-6: MATCH, item by item.
      * Focused `tests/unit/test_log_redaction.py`: 9 passed (record: 9). HOLDS.
      * Static gates: `ruff check` clean; `ruff format --check` 2 files already
        formatted; `mypy --strict` Success on both files. ALL HOLD.
      * 5-file combined run: 113 passed, 1 error (record: 102 passed). Both
        deltas explained, neither mine:
          - 102 -> 113 is COUNT GROWTH from concurrent sessions adding tests to
            `test_redaction.py` / `test_settings.py` (both modified in
            `git status`), not a regression.
          - The 1 error is `test_unit_tier_needs_no_database.py`, the aggregating
            guard already identified in signal 5. RE-ATTRIBUTED, not assumed:
              (a) `git stash push` of ONLY my two files -> the test STILL fails
                  identically (child reports `2 failed, 858 passed`), so it is
                  red independently of this fix. Stash popped; both files then
                  verified BYTE-IDENTICAL to a pre-stash scratchpad backup
                  (`diff` clean, diffstat back to 34 / 206).
              (b) The failing assertion's own text ("tried to spawn a REAL agent
                  CLI") is an ADDED (`+`) line in the uncommitted
                  `tests/conftest.py` diff, and `git blame -L 330,345` on that
                  file returns 16/16 lines at the all-zeros SHA — i.e. that
                  entire tripwire block is uncommitted concurrent work from
                  session `claude-cli-test-spawns-real-binary-with-key-present`.
                  It concerns agent-binary PATH resolution, nothing in redaction
                  or `log_sink`.
      * Clean subset (the 4 files minus that aggregator): 110 passed.
      * CREDENTIAL-FREE CLAIM RESTORED INDEPENDENTLY. Signal 3 had leaned on the
        aggregator to prove the new tests pass in a database-free process, and
        that aggregator is now red for unrelated reasons — so the claim was
        re-established directly instead of dropped: replicated the aggregator's
        own `_ENV_ALLOWLIST`/`_sanitized_env()` idiom (asserting `DATABASE_URL`
        and `DATABASE_URL_DIRECT` absent from the child env) and ran the test
        file from a fresh `TemporaryDirectory` containing no `.env`. Result:
        exit 0, 9 passed. The G-11-3 environment the helper exists for is still
        covered.

files_changed:
  - tests/unit/test_log_redaction.py
  - tests/support/log_sink.py
