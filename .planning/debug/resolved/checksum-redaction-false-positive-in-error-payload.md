---
status: resolved
trigger: "In src/dark_factory/events/redaction.py, _HEX_TOKEN/_hex_token_replacement redacts any bare 40/64-hex-char string outside a git-object context, and a SHA-256 artifact checksum is exactly 64 hex chars, so a FAILED role's role_executions.error stores 'checksum': '[redacted:github_token]' instead of the real checksum. Blast radius bounded: artifact_references.checksum in the DB is intact and ARTIFACT_CREATED payloads carry no checksum, so artifact integrity itself is unaffected -- this is cosmetic audit-trail loss on the failure-error path only."
created: 2026-10-09T00:00:00Z
updated: 2026-10-09T12:20:00Z
goal: find_and_fix
symptoms_prefilled: true
bug_class: Bohrbug
---

## Current Focus

<!--
  SEEDED, NOT YET INVESTIGATED. This file was created at the closeout of
  .planning/debug/resolved/qa-gate-exhausts-bounces-terminates-failed.md, where
  the finding was discovered incidentally and deliberately NOT fixed (scope
  creep -- distinct root cause, distinct subsystem). The user elected to track
  it at that session's human-verify checkpoint ("Confirmed + track checksum
  bug").

  The mechanism below is ALREADY DERIVED and the blast radius ALREADY BOUNDED by
  direct DB query. The next session should NOT re-derive it. Start at the fix
  design, after confirming the mechanism still holds at current HEAD.
-->

hypothesis: |
  CONFIRMED AT HEAD (see Evidence E-3). `_HEX_TOKEN` matches any bare 40- or
  64-hex run. `_hex_token_replacement` suppresses it only in a git-object
  TEXTUAL context (`_GIT_OBJECT_CONTEXT`, D-18) or under a git-object DICT KEY
  (`_GIT_OBJECT_KEYS` + the `exempt_hex_token` flag). A SHA-256 artifact
  checksum is exactly 64 hex chars and sits under the key `checksum`, which is
  in neither exemption set -- so it matches the bare-hex credential pattern and
  is replaced with `[redacted:github_token]`.

  Failing CLOSED (over-redacting) -- the safe direction. Cost is audit-trail
  legibility, not a credential leak.

test: |
  DB-free reproduction established (E-3, E-4) -- no Neon needed, contradicting
  the symptom's "requires a real database" assumption:
    redact({"artifacts": [{"checksum": sha256(b"...").hexdigest()}]},
           known_secrets={})
  -> checksum becomes "[redacted:github_token]".

expecting: |
  Fix verified when BOTH polarities hold in the same field (see
  `reasoning_checkpoint.falsification_test`).

next_action: |
  NONE -- session RESOLVED. The shape-gated structural key exemption (direction
  (b)) is applied, both polarities are proven by mutation testing, every gate is
  green, and the Resolution section below carries the verbatim command output.

reasoning_checkpoint:
  hypothesis: |
    `redact()`'s `_HEX_TOKEN` rule cannot distinguish a 64-hex SHA-256 artifact
    checksum from a 64-hex bare credential, and the key `checksum` is in neither
    of the two existing exemption sets (`_GIT_OBJECT_CONTEXT` textual,
    `_GIT_OBJECT_KEYS` structural), so every `ArtifactRef.checksum` that is
    serialized into a redacted JSONB column is destroyed.
  confirming_evidence:
    - "E-3: direct observation at HEAD -- redact({'checksum': <64 hex>}) returns '[redacted:github_token]'. Reproduced DB-free in two scripts."
    - "E-4: WorkerResult.model_dump(mode='json') carries artifacts[].checksum verbatim; runner.py:1093 sets outcome = result.model_dump(mode='json')."
    - "E-5: mutations.py:426 AND :428 both pass outcome through redact() -- so role_executions.result (every COMPLETED/BOUNCED role) is affected, not only .error."
    - "E-6: ArtifactRef.checksum is computed by Dark Factory itself (artifacts/paths.py checksum() = hashlib.sha256().hexdigest()) at cli_runtime.py:366 and fake.py:378 -- never populated from untrusted worker text."
    - "E-7: grep finds zero error/exception messages in src/ that embed a checksum, so the structural (key-based) surface is the complete fix surface."
  falsification_test: |
    The fix is WRONG if either polarity fails in the SAME `checksum` field:
      (+) a real `hashlib.sha256(...).hexdigest()` value must survive verbatim;
      (-) a configured live secret (`known_secrets`) that happens to be 64
          lowercase hex chars must STILL be redacted, and so must a
          `ghp_`/`github_pat_`/postgres-URI/bearer shape, and so must a 40-hex
          PAT, and so must an UPPERCASE 64-hex run.
    If (-) fails anywhere, the fix has converted a false positive into a false
    negative on real credentials -- strictly worse than the bug. Revert.
  fix_rationale: |
    Direction (b) from the seeded plan (structural, not textual) -- and HEAD
    already provides the mechanism, which the seeded plan did not know: the
    `_GIT_OBJECT_KEYS` + `exempt_hex_token` key-aware exemption added for commit
    SHAs. So (b) is a ~6-line change along an established seam, and direction
    (a) (widening the TEXTUAL `_GIT_OBJECT_CONTEXT`) is rejected as strictly
    worse: it would exempt any prose reading "checksum: <64hex>", which an
    agent-authored summary or a third-party error string can trivially produce,
    making it a real credential-leak path. Direction (c) is rejected because the
    checksum reaches BOTH `.result` and `.error` through one shared `outcome`
    dict (E-5); stripping it would delete a correct audit fact from the success
    path to work around a redactor defect.

    The exemption is deliberately NARROWER than the git-object precedent -- it
    is SHAPE-GATED, not key-only:
      * only under a key in `_CHECKSUM_KEYS` ({"checksum"}),
      * only when the value matches `\A[0-9a-f]{64}\Z` exactly -- the precise
        output shape of `hexdigest()`; so 40-hex PATs, uppercase/mixed-case hex,
        and any value with surrounding prose are all still redacted,
      * only `_HEX_TOKEN` is suppressed; every other pattern row still runs,
      * `_scrub_known()` is NOT bypassed -- it runs before the pattern table
        inside `_redact_str`, so a configured live secret is still removed even
        when it passes the shape gate. This is what makes polarity (-) hold.
  blind_spots: |
    - A bare 64-LOWERCASE-hex third-party credential that is NOT in
      `known_secrets` and is placed under a literal `checksum` key would now
      survive. Accepted: E-6 shows Dark Factory computes that field itself from
      bytes it read, so no untrusted value reaches it. Residual risk is a FUTURE
      code path that assigns worker-supplied text to a `checksum` key -- not
      prevented by this fix, only by the narrowness of `_CHECKSUM_KEYS`.
    - Not tested against a real Neon instance in this session; the DB-free repro
      is the same `redact()` call the mutation path makes, but the end-to-end
      round-trip is covered only by the existing db-tier suite.
    - SHA-256 is assumed to be the only digest in use. A future switch to a
      40-hex digest (SHA-1) or a 128-hex one (SHA-512) would silently fall
      outside the shape gate and regress to over-redaction (fails safe).
  candidate_causes:
    - "code: `_HEX_TOKEN` is shape-indistinguishable from a SHA-256 digest and `checksum` is absent from both exemption sets -- CONFIRMED (E-3)."
    - "data: the specific 64-char length of a SHA-256 digest is what collides; a 32- or 48-char digest would never have matched -- CONTRIBUTING but not independently sufficient."
    - "config: a `known_secrets` entry could coincidentally equal a checksum -- ELIMINATED, no such entry, and the bug reproduces with known_secrets={}."
    - "environment: Neon/JSONB serialization mangling the value -- ELIMINATED, reproduced in-process with no database (E-3)."
  and_gate: |
    no. The failure needs only the single code condition: `checksum` absent from
    the exemption sets while its value matches `_HEX_TOKEN`. The "data" cause
    (SHA-256's 64-char length) is a precondition of the same single mechanism,
    not an independent second fault that must co-occur -- removing either the
    pattern match or the missing exemption alone stops the bug, so this is an
    OR over one mechanism, not an AND over two.

## Symptoms

expected: |
  A FAILED role's persisted `role_executions.error` blob preserves the real
  SHA-256 artifact checksum, so the failure is forensically reconstructable
  from Neon -- per the project's durability/observability requirement ("if the
  orchestrator cannot explain where a run is, it cannot reliably resume it").

actual: |
  The checksum is stored as `'checksum': '[redacted:github_token]'`. The real
  value is lost from that blob.

errors: |
  No exception and no test failure. This is SILENT audit-trail degradation --
  the redactor behaves exactly as written and the run proceeds normally. There
  is no current gate that would surface it; it was found by eye while reading
  a `role_executions.error` blob for an unrelated investigation.

reproduction: |
  Observed in `scratchpad/revert_probe.py` during the
  qa-gate-exhausts-bounces-terminates-failed session: drive a run to a FAILED
  role against a real database, then read `role_executions.error` for that
  role and look at the serialized WorkerResult's artifact entries.

  A cheaper DB-free reproduction almost certainly exists (call the redactor
  directly with a 64-hex string) and should be the first thing established.

started: |
  Unknown precisely -- not yet bisected. Bounded above by whenever the bare-hex
  `_HEX_TOKEN` pattern was introduced, and relevant only once SHA-256 artifact
  checksums began flowing into a redacted field. The `_GIT_OBJECT_CONTEXT`
  carve-out (D-18) shows the same class of false positive was already
  recognized once for commit SHAs; the checksum case was simply not considered
  at that time.

## Eliminated

<!-- APPEND only. -->

- hypothesis: |
    The blast radius is confined to the FAILURE path -- `role_executions.error`
    on a FAILED role only (as stated in the inherited Evidence entry E-2 and in
    the session trigger).
  evidence: |
    WRONG, and the correction widens the bug. `runner.py:1093` sets
    `outcome = result.model_dump(mode="json")` ONCE, and the same `outcome` dict
    is assigned to `re_result` on the ROLE_COMPLETED arm (runner.py:1596) and the
    ROLE_BOUNCED arm (runner.py:1694) as well as to `re_error` on the ROLE_FAILED
    arm (runner.py:1631). `mutations.py` then redacts BOTH: line 426
    `redact(spec.result...)` and line 428 `redact(spec.error...)`.
    Confirmed by direct execution (E-5): a COMPLETED WorkerResult's
    `model_dump` -> `redact` round-trip mangles the checksum identically.
    So every role attempt that produces an artifact loses its checksum from
    `role_executions.result`, not just failures. The prior session's SQL query
    found intact values in `artifact_references.checksum` and looked at
    `.error`; it never examined `.result`.
  timestamp: 2026-10-09T11:15:00Z

- hypothesis: |
    An environment/serialization factor (Neon JSONB round-trip, psycopg
    adaptation) contributes to the mangling.
  evidence: |
    Reproduced entirely in-process with no database and no SQLAlchemy in the
    call path (E-3): a direct `redact()` call returns
    `[redacted:github_token]`. The defect is wholly inside
    `events/redaction.py`.
  timestamp: 2026-10-09T11:05:00Z

- hypothesis: |
    Fix direction (a) from the seeded plan -- widen the TEXTUAL
    `_GIT_OBJECT_CONTEXT` regex to also accept a `checksum` label before the
    hex run.
  evidence: |
    REJECTED on security grounds, not on feasibility. `_GIT_OBJECT_CONTEXT` is
    matched against arbitrary free text, including agent-authored summaries and
    third-party error strings echoed into a `WorkerResult`. Accepting
    `checksum[\s:=]*` there would mean any prose containing
    `"checksum: <64 hex>"` suppresses credential redaction -- trivially
    producible by an untrusted worker, which is precisely the attacker-adjacent
    surface WR-06 / the D-15 pattern table exists to cover. The structural
    key-based seam (direction (b)) achieves the same recovery with no
    free-text exposure, so (a) carries strictly more risk for zero additional
    benefit.
  timestamp: 2026-10-09T11:20:00Z

- hypothesis: |
    Fix direction (c) from the seeded plan -- stop routing the checksum into
    `role_executions.error` at all, since `artifact_references.checksum` is the
    system of record.
  evidence: |
    REJECTED. Per the Eliminated entry above, the checksum reaches `.result`
    and `.error` through ONE shared `outcome` dict built at runner.py:1093, so
    "stop routing it into error" cannot be done without also stripping it from
    the success path -- deleting a correct audit fact from every COMPLETED role
    to work around a defect in the redactor. It also treats the symptom (a
    field that happens to be visible) rather than the cause (an exemption gap),
    and would leave the identical false positive live for any future 64-hex
    digest field.
  timestamp: 2026-10-09T11:22:00Z

## Evidence

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    INHERITED FINDING, carried verbatim from
    .planning/debug/resolved/qa-gate-exhausts-bounces-terminates-failed.md
    (its final Evidence entry and its
    `out_of_scope_findings_reported_not_fixed` block). Discovered while reading
    the revert probe's `role_executions.error` blob against a real Neon
    PostgreSQL 17.
  found: |
    Artifact checksums rendered as `'checksum': '[redacted:github_token]'`.
    Traced to `src/dark_factory/events/redaction.py`'s `_HEX_TOKEN` pattern and
    `_hex_token_replacement`, which redact any bare 40/64-hex run unless it is
    preceded by a git-object context (`_GIT_OBJECT_CONTEXT`, D-18). A SHA-256
    artifact checksum is exactly 64 hex characters, so it matches the
    bare-hex credential pattern and is replaced.
  implication: |
    The mechanism is already established by direct observation -- do not spend
    this session re-deriving it. The open questions are (a) the complete set of
    affected write paths and (b) the fix shape.

- timestamp: 2026-10-09T00:00:00Z
  checked: |
    BLAST RADIUS, bounded by direct SQL query against the same database in the
    prior session (not inferred).
  found: |
    - `artifact_references.checksum` holds intact real values
      (`9f1ede6e...c16c9` etc.) -- the system of record is NOT affected.
    - `ARTIFACT_CREATED` event payloads carry no checksum at all, so the event
      stream is not affected either.
    - The mangling therefore affects ONLY the serialized `WorkerResult` copy
      persisted into `role_executions.error`, which is written only on a FAILED
      role.
  implication: |
    The artifact-integrity mechanism is NOT compromised. This is cosmetic
    audit-trail degradation on the failure path only -- LOW severity. Scope the
    fix accordingly and resist widening it; in particular, do not weaken the
    redactor's default-deny posture to recover a cosmetic value.
  SUPERSEDED_BY: |
    E-5 -- the "failure path only" half of this entry is WRONG (see Eliminated).
    The artifact-integrity conclusion still stands.

- timestamp: 2026-10-09T11:05:00Z
  id: E-3
  checked: |
    CONFIRMATION AT HEAD, and establishment of a cheap DB-FREE reproduction.
    Read `src/dark_factory/events/redaction.py` in full, then executed a direct
    `redact()` call on a real `hashlib.sha256` digest with `known_secrets={}`.
  found: |
    Mechanism holds at HEAD. Repro (no database, no SQLAlchemy):
      checksum(b"hello artifact body")
        = 897f504dbfda8717a4df584dd0db651dcc1847df025c98662f9a8ce2bda73a7f (64 ch)
      redact({"artifacts": [{..., "checksum": <that>}]}, known_secrets={})
        -> "checksum": "[redacted:github_token]"
    In the same call a 40-hex value under the key `commit` SURVIVED intact.

    KEY STRUCTURAL FINDING the seeded hypothesis did not have: HEAD has TWO
    exemption mechanisms, not one.
      1. `_GIT_OBJECT_CONTEXT` (line 76) -- TEXTUAL, matched against the text
         preceding the hex run. This is the only one the seeded note described.
      2. `_GIT_OBJECT_KEYS` (line 89) + the `exempt_hex_token` parameter
         (lines 168/173/215-221) -- STRUCTURAL and KEY-AWARE: when `redact()`
         recurses into a Mapping under one of `commit`/`sha`/`revision`/
         `commit_sha`/`wip_commit_sha`, it suppresses `_HEX_TOKEN` for that
         value only, while every other pattern row still runs unconditionally.
  implication: |
    This reframes the fix decision recorded in the seeded plan. Seeded direction
    (b) ("redact structurally rather than textually") is not a new design to be
    invented -- it is an ALREADY-ESTABLISHED seam in this module with its own
    precedent, decision record and tests. The fix is therefore a small,
    in-pattern change, and seeded direction (a) (widening the textual context)
    can be rejected outright rather than weighed.
    The existing test `test_git_object_key_exemption_does_not_weaken_other_patterns`
    (tests/unit/test_redaction.py:180) is already the both-polarities template
    the resume directive demands.

- timestamp: 2026-10-09T11:10:00Z
  id: E-4
  checked: |
    How a checksum reaches a redacted field: `domain/worker.py` (`ArtifactRef`,
    `WorkerResult`) and `orchestrator/runner.py:1093`.
  found: |
    `ArtifactRef.checksum: str | None` is a declared field of `ArtifactRef`,
    which is a list element of `WorkerResult.artifacts`.
    `runner.py:1093`: `outcome = result.model_dump(mode="json")` -- verified by
    execution that the dump carries `artifacts[0]["checksum"]` verbatim.
  implication: |
    The checksum enters the redacted blob as a STRUCTURED dict value under the
    literal key `checksum`, never as free prose. That is exactly the shape the
    key-aware `exempt_hex_token` seam was built for.

- timestamp: 2026-10-09T11:15:00Z
  id: E-5
  checked: |
    The COMPLETE set of write paths carrying a checksum through `redact()`.
    Traced every `re_result` / `re_error` assignment in runner.py and both
    redaction call sites in `persistence/mutations.py`.
  found: |
    - runner.py:1596 `re_result = outcome`  (Signal.ROLE_COMPLETED)
    - runner.py:1631 `re_error  = outcome`  (Signal.ROLE_FAILED)
    - runner.py:1694 `re_result = outcome`  (Signal.ROLE_BOUNCED)
    - runner.py:1738 `re_result = outcome`
    - mutations.py:426 `redact(spec.result, ...)` and :428 `redact(spec.error, ...)`
    Executed the COMPLETED-path round-trip directly: a `WorkerResult` with
    status=COMPLETED, dumped and redacted, loses its checksum identically.
    Separately confirmed mutations.py:560 `checksum=spec.checksum` is assigned
    WITHOUT redaction -- which is why `artifact_references.checksum` stayed
    intact in the prior session's SQL query, and why that query did not reveal
    the `.result` damage.
  implication: |
    BLAST RADIUS CORRECTION (supersedes E-2's "failure path only"): the bug
    affects `role_executions.result` on EVERY artifact-producing role attempt,
    not just `.error` on a FAILED one. Severity is still LOW (cosmetic;
    `artifact_references.checksum` remains the intact system of record) but the
    FREQUENCY is far higher than recorded -- effectively every successful role.
    It also eliminates seeded fix direction (c): `.result` and `.error` share
    one `outcome` dict, so the checksum cannot be withheld from the error path
    alone.

- timestamp: 2026-10-09T11:18:00Z
  id: E-6
  checked: |
    PROVENANCE of `ArtifactRef.checksum` -- is it Dark-Factory-computed
    (trustworthy) or worker-supplied free text (untrusted)? This is the load-
    bearing question for whether a `checksum`-key exemption is safe.
    Grepped every `ArtifactRef(` construction in src/.
  found: |
    Every production construction computes the digest itself from bytes Dark
    Factory read:
      - `workers/cli_runtime.py:366`:
        `ArtifactRef(type=filename, path=relative_path, checksum=checksum(data))`
        where `data = resolved.read_bytes()`
      - `workers/fake.py:378`: digest from `write_artifact_text(...)`
      - `artifacts/paths.py:69`: `checksum(data) = hashlib.sha256(data).hexdigest()`
    The ONLY path where a `checksum` value could originate outside Dark Factory
    is `fake.py:392` `WorkerResult.model_validate(...)` reading the FakeWorker's
    scripted-outcome env var -- in-process test scaffolding, not a worker
    boundary.
  implication: |
    `checksum` is NOT a worker-controlled free-text field. A third-party
    credential cannot arrive in it from the untrusted side, which is what makes
    a key-scoped `_HEX_TOKEN` exemption defensible where a textual one would
    not be. `hexdigest()` also always returns LOWERCASE hex of exactly 64
    chars -- a shape the exemption can and should assert, making it narrower
    than the git-object precedent it follows.

- timestamp: 2026-10-09T11:20:00Z
  id: E-7
  checked: |
    Whether any checksum reaches a redacted field as PROSE rather than as a
    dict value -- which would leave a residual surface a key-based fix cannot
    reach. Grepped src/ for checksum interpolated into raise/error/f-string
    messages.
  found: |
    Zero matches. No exception message, error string or log line in src/
    embeds a checksum value.
  implication: |
    The structural key-based fix is the COMPLETE fix surface -- there is no
    prose path left over-redacting a checksum, so no textual exemption is
    needed even as a supplement. Confirms the direction-(a) rejection.

## Resolution

root_cause: |
  SINGLE CAUSE (the `and_gate` check above answered "no" -- one mechanism, not
  co-occurring faults).

  `src/dark_factory/events/redaction.py`'s `_HEX_TOKEN` pattern
  (`\b[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\b`) matches any bare 40- or 64-hex
  run, and `_hex_token_replacement` suppressed it in only two cases: a textual
  git-object context (`_GIT_OBJECT_CONTEXT`) or a git-object dict key
  (`_GIT_OBJECT_KEYS` + the `exempt_hex_token` flag). A SHA-256 artifact
  checksum from `artifacts/paths.py:checksum()` =
  `hashlib.sha256(data).hexdigest()` is exactly 64 hex characters and travels
  under the literal dict key `checksum`, which was in NEITHER exemption set --
  so it was shape-indistinguishable from a bare 64-hex credential and was
  replaced with `[redacted:github_token]`.

  Blast radius (corrected from the inherited note, see E-5): the damage was NOT
  confined to the failure path. `runner.py:1093` builds ONE
  `outcome = result.model_dump(mode="json")` dict that is assigned to
  `re_result` on ROLE_COMPLETED (:1596), ROLE_BOUNCED (:1694) and :1738 as well
  as to `re_error` on ROLE_FAILED (:1631); `mutations.py:426` and `:428` redact
  both. So every artifact-producing role attempt lost its checksum from
  `role_executions.result`, not just failures.
  `artifact_references.checksum` was never affected (`mutations.py:560` assigns
  it without redaction) and remains the intact system of record -- artifact
  integrity was never compromised. The defect failed CLOSED (over-redaction),
  so it was audit-trail legibility loss, never a credential leak.

fix: |
  Direction (b) -- a SHAPE-GATED structural key exemption along the existing
  `_GIT_OBJECT_KEYS` / `exempt_hex_token` seam. Directions (a) (widen the
  TEXTUAL context) and (c) (stop routing the checksum) were rejected on
  security and correctness grounds respectively; see the Eliminated section.

  In `src/dark_factory/events/redaction.py`:
    * added `_CHECKSUM_KEYS = frozenset({"checksum"})` and
      `_SHA256_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")`;
    * added the `_is_sha256_digest(value)` predicate (string AND anchored match);
    * in `redact()`'s Mapping branch, widened `item_exempt` to
      `key.lower() in _GIT_OBJECT_KEYS or (key.lower() in _CHECKSUM_KEYS and
      _is_sha256_digest(item))`;
    * documented the three narrowing invariants and the "do NOT add an
      agent-authorable key here / do NOT mirror this as a textual rule" warning.

  Deliberately NARROWER than the git-object precedent it follows, which is what
  makes negative polarity hold:
    1. SHAPE-GATED, not key-only -- the value must be 64 *lowercase* hex end to
       end, exactly what `hexdigest()` emits. A 40-hex PAT, an upper/mixed-case
       64-hex run, and any value with surrounding prose are all still redacted
       under a `checksum` key.
    2. `_HEX_TOKEN` ONLY -- the postgres-URI, `github_pat_`, `gh[porsu]_`,
       bearer and sensitive-`key=value` rows still run unconditionally.
    3. `_scrub_known` is NEVER exempted -- it runs before the pattern table in
       `_redact_str`, so a configured live secret that happens to pass the shape
       gate is still removed. Known-value substitution from `Settings`, not the
       shape heuristic, remains the authoritative defence.
    4. The gate inspects the value directly, so a list/dict under a `checksum`
       key earns no exemption -- no subtree is ever blanket-exempted.

verification: |
  All commands run from the repo root on 2026-10-09. Verbatim output.

  (1) THE GUARDRAIL -- BOTH POLARITIES, PROVEN BY MUTATION, NOT BY ASSERTION.
      A passing test proves nothing unless it can fail, so each polarity was
      mutation-tested independently.

      Mutation 1 -- revert redaction.py to HEAD (re-introduce the bug).
      POSITIVE polarity must break:
        $ uv run pytest tests/unit/test_redaction.py -k "checksum or sha256 or worker_result_dump" -q
        FAILED test_sha256_checksum_under_a_checksum_dict_key_survives
        FAILED test_worker_result_dump_round_trip_preserves_checksums_and_redacts_secrets
        2 failed, 9 passed, 55 deselected in 0.06s
        AssertionError: assert ['[redacted:github_token]'] == ['920de5214f0...']
      -> the positive guard genuinely detects the reported bug. Not vacuous.

      Mutation 2 -- keep the fix but DELETE the shape gate, making `checksum` an
      unconditional hex-token bypass. NEGATIVE polarity must break:
        $ uv run pytest tests/unit/test_redaction.py -k "checksum or sha256 or worker_result_dump" -q
        6 failed, 5 passed, 55 deselected in 0.08s
        FAILED test_checksum_key_exemption_is_shape_gated[40 hex ...]
        FAILED test_checksum_key_exemption_is_shape_gated[uppercase]
        FAILED test_checksum_key_exemption_is_shape_gated[mixed case]
        FAILED test_checksum_key_exemption_is_shape_gated[digest inside prose]
        FAILED test_checksum_key_exemption_is_shape_gated[digest + second hex run]
        FAILED test_checksum_exemption_does_not_propagate_into_a_nested_container
      -> the shape gate is load-bearing and independently guarded. A key-only
         exemption -- the exact false-negative the directive forbids -- CANNOT
         ship past this suite.

      NOTE on an instructive non-failure: `test_known_secret_is_still_scrubbed_
      from_a_checksum_field` PASSED under Mutation 2. That is correct and not a
      gap -- `_scrub_known` runs before the pattern table and is never exempted,
      so the live-secret defence is structurally independent of the shape gate.
      Two orthogonal defences, each with its own guard.

      Fix restored and byte-verified after both mutations:
        $ diff -q <saved fixed copy> src/dark_factory/events/redaction.py
        IDENTICAL - restore clean

  (2) BOTH POLARITIES GREEN WITH THE FIX APPLIED, in the SAME `checksum` field:
        $ uv run pytest tests/unit/test_redaction.py -k "checksum or sha256 or worker_result_dump" -v
        11 passed, 55 deselected in 0.05s
      (+) real `checksum(b"an artifact body")` digest survives VERBATIM, with
          `assert len(digest) == 64` guarding the premise;
      (-) in the SAME field, all still redacted: a `known_secrets` live secret
          that is 64 lowercase hex ("deadbeef"*8), `ghp_`, `github_pat_`,
          postgres URI, bearer, 40-hex PAT, UPPERCASE and mixed-case 64-hex,
          a digest in prose, a digest plus a second hex run, and a digest
          nested inside a list.

  (3) NO REGRESSION in the existing git-object exemption tests -- full file:
        $ uv run pytest tests/unit/test_redaction.py -q
        66 passed in 0.05s
      includes `test_git_object_key_exemption_does_not_weaken_other_patterns`,
      both idempotency corpora, and the `patterns=False` scope split.

  (4) FULL UNIT TIER:
        $ uv run pytest -m unit -q
        842 passed, 1 skipped, 456 deselected, 1 warning, 1 error in 156.90s
      The 1 error is NOT from this change -- ownership proven, not assumed:
        - it is `tests/unit/test_unit_tier_needs_no_database.py`, raised by a
          guard at `tests/conftest.py:338` ("tried to spawn a REAL agent CLI");
        - that guard text has 0 occurrences at HEAD -- it is a 102-line
          UNCOMMITTED addition from a different concurrent debug session;
        - the erroring test contains 0 references to redaction;
        - it reproduces identically with redaction.py reverted to HEAD
          (1 failed, 2 passed, 1 error) -- i.e. with this fix absent.
      Reported as a cross-session finding, not touched (per scope discipline).

  (5) EVERY SUITE IMPORTING `events.redaction`, including the other session's
      similarly-named file, which was read but NOT edited:
        $ uv run pytest tests/unit/test_log_redaction.py -q
        9 passed in 0.66s
        $ uv run pytest tests/unit/test_log_redaction.py tests/unit/test_redaction.py \
            tests/db/test_status_from_columns.py tests/db/test_snapshot_roundtrip.py \
            tests/db/test_secret_redaction_e2e_full_pipeline.py -q -p no:randomly
        1 failed, 89 passed in 203.37s
      The 1 failure was `tests/db/test_status_from_columns.py::
      test_read_status_performs_no_write` -- diagnosed as a FLAKE, not caused
      by this change, on three independent grounds:
        - its `_table_counts` helper counts `runs`/`role_executions`/
          `run_events` GLOBALLY (not scoped to its own `run_id`), so it is
          sensitive to any concurrent writer on the shared
          DARK_FACTORY_TEST_DATABASE_URL instance -- and several other debug
          sessions were in flight;
        - it passes in isolation: `1 passed in 16.89s`;
        - the same combined db set passes BOTH with the fix absent
          (`15 passed in 203.31s`) AND with the fix applied
          (`15 passed in 205.05s`) -- so the failure does not track the change;
        - mechanically, this fix alters only the string CONTENT of a redacted
          value and cannot alter any table's row count.
      `tests/db/test_secret_redaction_e2e_full_pipeline.py` -- the end-to-end
      redaction pipeline db test, the most relevant downstream consumer --
      passes.

  (6) LINT / TYPE GATES on the changed files:
        $ uv run ruff check src/dark_factory/events/redaction.py tests/unit/test_redaction.py
        All checks passed!                      (exit=0)
        $ uv run ruff format --check <same two>
        2 files already formatted               (exit=0)
        $ uv run mypy --strict <same two>
        Success: no issues found in 2 source files   (exit=0)

  (7) DOWNSTREAM TYPE SAFETY for every caller of `redact()`:
        $ uv run mypy --strict src/
        Found 2 errors in 1 file (checked 79 source files)
      Both errors are `import-not-found` for `mcp.server` in
      `tools/mcp_transport.py` -- the optional `mcp` extra is not installed.
      Pre-existing and unrelated; `redact()`'s public signature is unchanged
      (only module-private names were added).

  RESIDUAL RISK, accepted and recorded (see `reasoning_checkpoint.blind_spots`):
  a bare 64-LOWERCASE-hex third-party credential NOT in `known_secrets`, placed
  under a literal `checksum` key, would now survive. E-6 shows every production
  `ArtifactRef.checksum` is computed by Dark Factory from bytes it read, so no
  untrusted value reaches that key today; the in-code warning is the only guard
  against a future path that assigns worker-supplied text there. A future switch
  to a 40-hex (SHA-1) or 128-hex (SHA-512) digest falls outside the gate and
  regresses to over-redaction -- i.e. fails safe.

why_not_caught: |
  No gate existed for this class -- confirmed by Symptoms.errors: there was no
  exception, no test failure and no log line. The redactor behaved exactly as
  written and the run proceeded normally, so every existing gate (unit,
  typecheck, lint, review, verify, build) was silent BY CONSTRUCTION:

    * TESTS -- the pre-existing suite asserted the redactor's negative duty
      (secrets get redacted) thoroughly, but asserted its positive duty (real
      non-secret values SURVIVE) only for the git-object case that had already
      been reported once. There was no test that a checksum survives, because
      over-redaction produces no error signal to write a test against.
    * TYPECHECK -- `checksum: str | None` before and `str` after; a redacted
      checksum is still a perfectly well-typed `str`. Type systems cannot see
      value corruption.
    * REVIEW -- the `_GIT_OBJECT_CONTEXT` carve-out (D-18) proves this exact
      false-positive class was already recognised ONCE, for commit SHAs. The
      fix was applied to the instance that had been reported rather than to the
      class, and nothing prompted the reviewer to enumerate the other 40/64-hex
      field families in the codebase. SHA-256 checksums were simply not
      considered.
    * DB-TIER -- the one suite that round-trips a real blob
      (`test_secret_redaction_e2e_full_pipeline`) asserts that secrets are
      ABSENT, never that legitimate values are PRESENT.

  Root asymmetry: a one-way, default-deny transform was gated in one direction
  only. Over-redaction is silent by nature, and redaction is explicitly one-way
  ("an over-redacted value cannot be recovered either" -- module docstring), so
  the damage is unrecoverable at the moment it is least observable. It was
  ultimately found by eye, while reading a `role_executions.error` blob for an
  unrelated investigation.

recurrence_guard: |
  PRIMARY -- a both-polarities regression test group,
  `tests/unit/test_redaction.py` lines 199-345, introduced by a header comment
  that states the four cases are ONE guard and must not be deleted separately:
    * tests/unit/test_redaction.py::test_sha256_checksum_under_a_checksum_dict_key_survives
      -- positive polarity; uses a REAL `artifacts.paths.checksum()` digest, not
      a hand-built 64-char string, so it tracks the production digest shape
      instead of an assumption about it, and asserts `len(digest) == 64` to
      guard its own premise.
    * ::test_checksum_key_exemption_does_not_weaken_other_patterns
      -- negative; every credential SHAPE under a `checksum` key.
    * ::test_known_secret_is_still_scrubbed_from_a_checksum_field
      -- negative, the load-bearing one; a configured live secret that is 64
      lowercase hex, i.e. one that passes the shape gate exactly.
    * ::test_checksum_key_exemption_is_shape_gated (5 boundary neighbours)
      -- negative; 40-hex, uppercase, mixed case, digest-in-prose, digest plus a
      second hex run.
    * ::test_checksum_exemption_does_not_propagate_into_a_nested_container
      -- negative; no subtree is ever blanket-exempted.
    * ::test_sha256_digest_under_an_unrelated_key_is_still_redacted
      -- proves the 64-hex arm of `_HEX_TOKEN` was not globally retired.
    * ::test_worker_result_dump_round_trip_preserves_checksums_and_redacts_secrets
      -- both polarities in ONE payload at the ACTUAL blast-radius shape (the
      `result.model_dump(mode="json")` dict runner.py hands to `redact()`), so
      the guard is pinned to the real call shape, not a synthetic dict.

  Mutation-verified in both directions (see verification (1)): reverting the fix
  breaks the positive guard; deleting the shape gate breaks six negative guards.
  Neither the original bug nor its dangerous over-correction can ship past this
  suite.

  SECONDARY -- the oracle for the new group is `derived` (a contract: the
  redactor must preserve any value that is exactly a lowercase SHA-256 digest
  under a digest key, and must redact everything else there), NOT `implicit`;
  these tests fail on a wrong VALUE, not merely on a crash.

  TERTIARY -- an in-code invariant comment above `_CHECKSUM_KEYS` records why
  the exemption is safe (Dark Factory computes the digest itself) and states the
  two prohibitions that would make it unsafe: do NOT add a key whose value an
  agent can author, and do NOT mirror this as a textual
  `_GIT_OBJECT_CONTEXT` arm. This is what carries the reasoning forward to the
  next person who widens `_CHECKSUM_KEYS`.

  CLASS-LEVEL LESSON for the KB -- `_HEX_TOKEN` has now produced this same
  false positive TWICE (commit SHAs -> D-18, then SHA-256 checksums -> here).
  Any future hex-shaped identifier field (a SHA-1/SHA-512 digest, a blob OID, a
  UUID-without-dashes) is a third instance waiting to happen. The general guard
  is the pairing discipline, not the specific key: when adding a one-way
  default-deny transform, gate BOTH directions -- assert that legitimate values
  SURVIVE, not only that secrets are removed.

files_changed:
  - "src/dark_factory/events/redaction.py: added `_CHECKSUM_KEYS`, `_SHA256_DIGEST` and `_is_sha256_digest()`; widened `redact()`'s `item_exempt` with the shape-gated `checksum` arm; documented the three narrowing invariants and the two prohibitions (+57/-2)"
  - "tests/unit/test_redaction.py: added the both-polarities `checksum` regression group -- 1 positive + 8 negative cases incl. 5 shape-gate boundary neighbours and the model_dump round-trip at the real blast-radius shape (+149)"
  - ".planning/debug/checksum-redaction-false-positive-in-error-payload.md: session record, resolved"
