---
status: investigating
trigger: "In src/dark_factory/events/redaction.py, _HEX_TOKEN/_hex_token_replacement redacts any bare 40/64-hex-char string outside a git-object context, and a SHA-256 artifact checksum is exactly 64 hex chars, so a FAILED role's role_executions.error stores 'checksum': '[redacted:github_token]' instead of the real checksum. Blast radius bounded: artifact_references.checksum in the DB is intact and ARTIFACT_CREATED payloads carry no checksum, so artifact integrity itself is unaffected -- this is cosmetic audit-trail loss on the failure-error path only."
created: 2026-10-09T00:00:00Z
updated: 2026-10-09T00:00:00Z
goal: find_and_fix
symptoms_prefilled: true
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
  The bare-hex credential pattern in `src/dark_factory/events/redaction.py`
  cannot distinguish a 64-hex-character SHA-256 ARTIFACT CHECKSUM from a 64-hex
  -character credential, so it redacts the former as
  `[redacted:github_token]`.

  `_HEX_TOKEN` matches any bare 40- or 64-hex-character run;
  `_hex_token_replacement` suppresses the match only when it is preceded by a
  git-object context (`_GIT_OBJECT_CONTEXT`, decision D-18 -- added so commit
  SHAs survive redaction). An artifact checksum appears in no such context, so
  it matches and is replaced.

  This is a FALSE POSITIVE in a security control, not a security hole: the
  redactor is failing closed (over-redacting), which is the safe direction. The
  cost is audit-trail legibility on the failure path.

test: |
  NOT YET DESIGNED. First step is confirmation-at-HEAD, not re-derivation --
  the mechanism was directly observed in the prior session's revert probe.

expecting: |
  N/A -- no experiment run in this session yet.

next_action: |
  1. Confirm the mechanism still holds at current HEAD: read
     `src/dark_factory/events/redaction.py` (`_HEX_TOKEN`,
     `_hex_token_replacement`, `_GIT_OBJECT_CONTEXT`) and check whether a
     64-hex checksum is still unprotected.
  2. Find every write path that can carry a checksum into a redacted field.
     The known one is the serialized `WorkerResult` persisted into
     `role_executions.error` on a FAILED role. Determine whether there are
     others (search for serialization of objects containing `checksum` that
     pass through `redact(...)`).
  3. Decide the fix shape. Candidate directions, NOT yet evaluated -- pick by
     evidence, and note that direction (a) widens a SECURITY control, so it
     needs the most scrutiny:
       (a) extend the context-exemption approach that D-18 already established
           for git objects to cover a checksum context (e.g. a `checksum`
           key/label immediately preceding the value) -- consistent with the
           existing design, but every widening of a redaction exemption is a
           potential credential-leak path and must be argued as such;
       (b) redact structurally rather than textually on this path -- redact the
           WorkerResult's FIELDS before serialization, so a checksum field is
           never offered to the bare-hex pattern at all;
       (c) accept the over-redaction and instead stop routing the checksum into
           `role_executions.error` (or record it separately), on the grounds
           that `artifact_references.checksum` is already the system of record.
  4. Whatever the direction: the regression test must assert BOTH polarities --
     a real 64-hex checksum survives, AND a real 64-hex credential in the same
     field is still redacted. A fix that only proves the first half would
     silently convert a false positive into a false negative, which is the
     dangerous direction.

reasoning_checkpoint: |
  NOT YET WRITTEN. Must be completed before any fix is applied, per the
  mandatory structured-reasoning checkpoint. Note in advance that the
  `candidate_causes` branching for this bug is likely shallow (the mechanism is
  already directly observed and single-category: code), so the AND-gate check
  will probably answer "no" -- but it must still be asked and recorded.

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

<!-- APPEND only. Nothing eliminated yet -- no hypothesis has been tested. -->

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

## Resolution

root_cause: |
  [empty -- mechanism is strongly indicated (see Evidence) but not yet
  confirmed at current HEAD, and the full set of affected write paths is not
  yet enumerated]

fix: |
  [empty]

verification: |
  [empty]

files_changed: []
