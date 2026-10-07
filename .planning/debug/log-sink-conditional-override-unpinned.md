---
status: investigating
trigger: "The absence-conditional override in tests/support/log_sink.py::real_log_sink (supply fake DATABASE_URL/DATABASE_URL_DIRECT only when ABSENT, never clobber an already-set value) is correct but pinned by NO test: mutating it to an unconditional override left tests/unit/test_log_redaction.py fully green (4 passed). Mechanism: events/redaction.py's pattern rule for postgres://...@... URLs masks the exact-value path, so those assertions prove PATTERN redaction only, not KNOWN-SECRET exact-value redaction."
created: 2026-10-07T00:00:00Z
updated: 2026-10-07T00:00:00Z
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

status: NOT YET INVESTIGATED. Seeded from the parent session's mutation
experiment so the next session does not re-derive it. The parent session
classified this as a test-sensitivity gap rather than a blocker, because the
G-11-3 property itself is pinned by its own Signals 1-3.

hypothesis (PARTLY CONFIRMED by the parent session's mutation; the REMEDY is
what remains open): Two layered facts.

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

next_action: Confirm the layer-masking claim by disabling the known-secret path
and re-running `tests/unit/test_log_redaction.py` — the parent session inferred
masking from reading `_PATTERNS` plus the surviving mutant, but did NOT run that
specific isolation experiment. Then implement BOTH missing pins: (a) a
non-pattern-shaped known-secret test that isolates the exact-value layer, and
(b) a test that fails if `real_log_sink`'s absence-conditional is removed (so the
clobbering is detected). Also decide whether `test_log_redaction.py`'s existing
DB-URL assertions should be RELABELLED to say they prove pattern redaction —
leaving them named as-is is itself a trap for the next reader.

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

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: ""
fix: ""
verification: ""
files_changed: []
