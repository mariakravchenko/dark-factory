---
status: resolved
trigger: "mypy --strict reports 3 pre-existing errors in tests/support/fake_artifacts.py, unrelated to and not caused by the in-scope-edit-missing-after-completed fix (test-only change to tests/integration/test_write_scope_enforcement.py); discovered as an adjacent-tier lint/type check during that session's fix-acceptance guardrail."
created: 2026-10-07T00:00:00Z
updated: 2026-10-26T00:00:00Z
origin: ".planning/debug/resolved/in-scope-edit-missing-after-completed.md (verification.adjacent_tests.lint_type)"
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

bug_class: "Bohrbug — fully deterministic static-analysis defect; reproduces on every `mypy --strict` run at clean HEAD. SBFL not applicable (no failing runtime test; the failing oracle is the type checker)."

hypothesis: "CONFIRMED — `AttemptAwareFourRoleWorker._record` narrows its `role` key component but never its `attempt` component, so the composed lookup key is `tuple[Any, Any | None]` and `None` is not assignable to the `int` slot of the three dicts' declared `tuple[str, int]` key type."
test: "Minimal reproduction with `reveal_type` on the exact idiom (scratchpad/probe.py)."
expecting: "If true: `role` reveals as `Any` after the `in`-dict assert while `attempt` reveals as `Any | None`, and the composed tuple reveals as `tuple[Any, Any | None]` with the identical arg-type error."
next_action: "NONE -- SESSION RESOLVED AND ARCHIVED. Human verification received ('confirmed fixed'). Fix committed as b473a29 (exactly 2 files: tests/support/fake_artifacts.py +16, tests/unit/test_attempt_aware_worker_attempt_invariant.py +144, via explicit pathspec because a concurrent session had staged unrelated files into the shared index); session doc recorded in 3547fe7. This file moved to .planning/debug/resolved/ and a knowledge-base.md entry appended. Residual, deliberately OUT OF SCOPE for this session and worth its own work item: CI's typecheck step is `mypy src/dark_factory` only, so `tests/` is still never type-checked in CI -- this exact error class can recur in any other test-support fixture without any gate noticing."

reasoning_checkpoint:
  hypothesis: "The three errors are caused by a missing narrowing assert for `attempt`: `getattr(context, 'attempt', None)` is typed `Any | None` by typeshed, and unlike `role` (narrowed to `Any` by `assert role in _FOUR_ROLE_FILES`) nothing ever removes the `None`, so every `(role, attempt)` key is `tuple[Any, Any | None]` and fails against the dicts' `tuple[str, int]` key type."
  confirming_evidence:
    - "Direct `reveal_type` observation: `role`/`attempt` both start as `Union[Any, None]`; after `assert role in _FOUR_ROLE_FILES` only `role` becomes `Any`, `attempt` stays `Union[Any, None]`; the tuple reveals as `tuple[Any, Union[Any, None]]`."
    - "The minimal 12-line reproduction emits the byte-identical error message as the real file, confirming the mechanism with nothing else present."
    - "All 3 error lines (276/278/286) are precisely the 3 sites that compose `(role, attempt)`; the 4th `_FOUR_ROLE_FILES[role]` lookup using `role` alone is error-free, isolating the fault to the `attempt` component."
    - "`RoleContext.attempt` is declared `int` (non-optional) at src/dark_factory/context/builder.py:112, so the dicts' `tuple[str, int]` key type is correct and the narrowing — not the key type — is what is missing."
  falsification_test: "If the dict key type, not the narrowing, were wrong, then widening to `tuple[str, int | None]` would be the correct fix and `RoleContext.attempt` would be optional. It is declared `int`, and all 11 caller sites reach `_record` only through the real `drive()` orchestrator, which always populates `attempt`. Hypothesis survives."
  fix_rationale: "Adding `assert isinstance(attempt, int), attempt` narrows `Any | None` -> `int` at the construction site, making the key concretely `tuple[Any, int]` (assignable to `tuple[str, int]`) at all three sites with no cast and no `# type: ignore`. It is not a symptom patch: it restores for `attempt` the exact same loud-failure invariant the file already enforces for `role`, closing a latent test-integrity hole — a missing/non-int `attempt` would silently fall through all three `.get()` calls to the `_FOUR_ROLE_FILES[role]` PASS-shaped default, turning an attempt-specific scenario (e.g. 'QA FAILs on attempt 1') into a vacuous pass. That is the same failure mode `__init__` already raises ValueError to prevent."
  blind_spots:
    - "The repo-wide alternative idiom `getattr(context, 'attempt', None) or 1` (src/dark_factory/workers/hermes.py:279) would also satisfy mypy, but is deliberately rejected here: silent defaulting is precisely the vacuous-pass mode this fixture guards against. Chose the assert over the local convention for that reason."
    - "Full db suite needs Docker/Postgres; if unavailable the fix rests on mypy + collection + the non-db tiers."
    - "Under a (currently non-existent) caller that passes a context lacking `attempt`, the assert converts a silent wrong-content fallback into a loud AssertionError. That is the intended direction, but it is a behavior change in that hypothetical."
  candidate_causes:
    - "code: missing narrowing assert for `attempt` in `_record` — CONFIRMED"
    - "code (alt): dict key type `tuple[str, int]` is wrong, should be `tuple[str, int | None]` — ELIMINATED (`RoleContext.attempt: int` is non-optional; widening would mask the real contract)"
    - "config: `strict = true` in pyproject [tool.mypy] is overly strict / false positive — ELIMINATED (genuine type hole, intentional project-wide setting)"
    - "environment: mypy/typeshed version drift changed the 3-arg `getattr` overload return — ELIMINATED (reproduces deterministically on pinned toolchain; and correct narrowing is the right fix regardless of which typeshed introduced it)"
    - "data: n/a — static-analysis-only defect, no runtime data path involved"
  and_gate: "Partially yes, with one actionable term. The error requires BOTH (a) the `getattr(context, ..., None)` idiom yielding `Any | None` AND (b) the absence of a narrowing assert for `attempt`. But (a) is a fixed design constraint, not a defect: the `CodingWorker.execute(context: object)` port signature (src/dark_factory/workers/base.py:20) deliberately keeps `context` untyped so no adapter couples to `RoleContext`, and 8 other test fixtures use the same idiom. Only (b) is actionable, so root_cause records a single cause with (a) named as the enabling precondition."

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: `uv run mypy --strict src tests` (or the project's configured mypy invocation) reports zero errors in tests/support/fake_artifacts.py.

actual: 3 errors, reproducing on a clean HEAD (not caused by any uncommitted change):
  - tests/support/fake_artifacts.py:276: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"
  - tests/support/fake_artifacts.py:278: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"
  - tests/support/fake_artifacts.py:286: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"

errors: see actual above — all three are the identical mypy error class (dict.get key-type mismatch: tuple[Any, Any | None] vs the dict's declared tuple[str, int] key type), at three call sites in the same file.

reproduction: "uv run mypy --strict tests/support/fake_artifacts.py (or the project's standard mypy invocation) on a clean checkout — no uncommitted changes needed to reproduce."

started: "Discovered 2026-10-07 during the fix-acceptance guardrail for debug session in-scope-edit-missing-after-completed, as an adjacent-tier lint/type check unrelated to that session's own change (tests/integration/test_write_scope_enforcement.py). Not a regression from that fix — reproduces independently on clean HEAD in a file that fix never touched."

## Eliminated
<!-- APPEND only - prevents re-investigating -->

- hypothesis: "The dicts' declared key type `tuple[str, int]` is wrong and should be widened to `tuple[str, int | None]`."
  evidence: "`RoleContext.attempt` is declared `int` (non-optional) at src/dark_factory/context/builder.py:112, and all 11 call sites reach `_record` only via the real `drive()` orchestrator which always populates `attempt`. The declared key type correctly models reality; widening it would mask the missing-narrowing defect and permit a `None` attempt to silently select the wrong fixture content."
  timestamp: 2026-10-09T00:00:00Z

- hypothesis: "mypy `strict = true` is over-strict here / this is a false positive to be silenced."
  evidence: "The error flags a real hole: `attempt` genuinely can be `None` at the type level and nothing checks it, so the three `.get()` calls would silently fall back to the PASS-shaped default. `strict = true` is the intentional project-wide setting in pyproject [tool.mypy]. Not a false positive."
  timestamp: 2026-10-09T00:00:00Z

- hypothesis: "`role` also needs its narrowing changed (both tuple elements are at fault)."
  evidence: "Only `attempt` is at fault. `reveal_type` shows `assert role in _FOUR_ROLE_FILES` already narrows `role` from `Any | None` to `Any`, which is assignable to the key's `str` slot — and the `_FOUR_ROLE_FILES[role]` lookup using `role` alone produces no error. The existing role assert is also the idiom repeated in 8 other test fixtures, so changing it would break convention for zero error-fixing benefit."
  timestamp: 2026-10-09T00:00:00Z

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-10-07T00:00:00Z
  checked: "in-scope-edit-missing-after-completed.md verification.adjacent_tests.lint_type"
  found: "mypy --strict reports 3 PRE-EXISTING errors in tests/support/fake_artifacts.py:276/278/286 (reproduce in isolation at a clean HEAD, in a file this fix never touches)"
  implication: "unrelated pre-existing gap, worth its own session since pre-commit/CI run mypy strict and this will keep surfacing as noise on unrelated diffs until fixed."

- timestamp: 2026-10-09T00:00:00Z
  checked: "`uv run mypy --strict tests/support/fake_artifacts.py` at clean HEAD 9e2b062 (working tree clean apart from two untracked .DS_Store files)"
  found: "Reproduced verbatim: 3 errors, all `[arg-type]`, at lines 276/278/286 — `Argument 1 to \"get\" of \"dict\" has incompatible type \"tuple[Any, Any | None]\"; expected \"tuple[str, int]\"`."
  implication: "Deterministic Bohrbug, confirmed pre-existing and independent of any uncommitted change. Reproduction is the type checker itself, so verification is exact rather than statistical."

- timestamp: 2026-10-09T00:00:00Z
  checked: "tests/support/fake_artifacts.py:272-294 — the three flagged call sites and the key they compose"
  found: "All three sites compose the same key `(role, attempt)` from `role = getattr(context, 'role', None)` (line 273) and `attempt = getattr(context, 'attempt', None)` (line 274), against three dicts declared `dict[tuple[str, int], ...]` in `__init__` (lines 254-256: `attempt_files`, `sentinel_writes`, `out_of_scope_writes`). Line 275 asserts `role in _FOUR_ROLE_FILES`; there is no corresponding assert for `attempt` anywhere in the method."
  implication: "Pinpoints the asymmetry: the method defends its `role` invariant but not its `attempt` invariant. The 3 error sites are exactly the 3 `(role, attempt)` keys."

- timestamp: 2026-10-09T00:00:00Z
  checked: "Minimal 12-line reproduction of the idiom with `reveal_type` (scratchpad/probe.py), run under the project's own `uv run mypy --strict`"
  found: "`role` -> `Union[Any, None]`; `attempt` -> `Union[Any, None]`; after `assert role in FILES`, `role` -> `Any` (mypy's `in`-container narrowing drops `None`) while `attempt` remains `Union[Any, None]`; `(role, attempt)` -> `tuple[Any, Union[Any, None]]`; the `.get()` emits the byte-identical error."
  implication: "ROOT CAUSE MECHANISM CONFIRMED in isolation. `Any` satisfies the key's `str` slot, but `Any | None` fails the `int` slot because `None` is not assignable to `int`. The fault is the missing narrowing of `attempt`, not the key type and not the `getattr` idiom itself."

- timestamp: 2026-10-09T00:00:00Z
  checked: "src/dark_factory/context/builder.py:104-124 (`RoleContext`) and src/dark_factory/workers/base.py:20 (`CodingWorker.execute`)"
  found: "`RoleContext` declares `role: str` and `attempt: int`, both non-optional and `frozen=True`/`extra='forbid'`. The `CodingWorker` port deliberately types `context: object`, which is *why* every adapter and fixture must reach fields via `getattr` and loses the static types."
  implication: "Establishes both that the `tuple[str, int]` key type is correct, and that the `Any | None` erasure is an unavoidable consequence of the intentional port design — so the fix must restore the type by narrowing at the use site, not by changing the port or the key type."

- timestamp: 2026-10-09T00:00:00Z
  checked: "All 11 `AttemptAwareFourRoleWorker` construction sites across tests/db/*.py, plus the only wrapper (`_CapturingWorker`, tests/db/test_feedback_reaches_developer.py:163-224)"
  found: "Every caller hands the worker to the real `drive()` orchestrator, which builds a genuine `RoleContext` via `build_role_context`. The one wrapper forwards the original `context` object unmodified (`self._inner.execute(context)` / `.resume(context, previous, answer)`). No caller constructs a stub context lacking `attempt`, and no caller invokes `_record` directly."
  implication: "An `isinstance(attempt, int)` assert cannot break any existing caller — at runtime `attempt` is always a real `int`. Confirms the fix is safe and that the type-level `None` is unreachable in practice (which is exactly what the assert should state to the checker)."

- timestamp: 2026-10-09T00:00:00Z
  checked: "Revert test (fix-acceptance signals 1-3): removed ONLY the `assert isinstance(attempt, int)` line, re-ran `uv run mypy --strict tests/support/fake_artifacts.py` and the new regression test file, then restored from a scratchpad backup."
  found: "Both oracles flipped. mypy re-emitted the 3 original `[arg-type]` errors verbatim. The regression test went RED on both `test_non_int_attempt_raises_instead_of_a_vacuous_pass` parametrizations with `Failed: DID NOT RAISE AssertionError` -- the pre-fix code returned a normal COMPLETED result carrying the PASS-shaped default. After restore: mypy `Success`, 6/6 tests pass."
  implication: "Confirms the fix is causally responsible for both halves of the defect, and -- more importantly -- demonstrates the *runtime* vacuous-pass mode empirically rather than by argument. This is the strongest available signal because the same one-line change flips a static oracle and a runtime oracle in the same direction."

- timestamp: 2026-10-09T00:00:00Z
  checked: "Attribution of the 3 ERRORS in the full unit-tier run (846 passed, 1 skipped, 3 errors)"
  found: "None are caused by this fix. (a) 2 errors name tests/unit/test_zz_tmp_tripwire_control.py, which NO LONGER EXISTS -- a concurrent debug session deleted its temporary control file mid-run (`git ls-files` and `pytest` both report it absent). (b) 1 error is `test_unit_tier_needs_no_database`, a meta-test that re-runs the whole unit tier in a subprocess; it fails only because 2 `tests/unit/test_redaction.py` cases fail, and both that file and src/dark_factory/events/redaction.py are uncommitted work belonging to the concurrent `checksum-redaction-false-positive-in-error-payload` session. `grep` shows test_redaction.py contains 0 references to `fake_artifacts` or `AttemptAwareFourRoleWorker`."
  implication: "The working tree is shared with 4 other in-flight debug sessions, so the tier result must be read per-file rather than as a single pass/fail. Commit must stage exactly the 2 files of THIS session -- `git add -A`/`git add .` would capture 4 unrelated half-finished fixes."

- timestamp: 2026-10-09T00:00:00Z
  checked: "Test-database availability for the db tier (tests/conftest.py 3-rung ladder: testcontainers -> pytest-postgresql -> DARK_FACTORY_TEST_DATABASE_URL)"
  found: "Rung 1 unavailable (`docker info` fails -- no daemon). Rung 2 unavailable (no `initdb`/`pg_ctl`/`postgres`/`psql` on PATH, and none at the homebrew/Postgres.app PG-17 locations). Rung 3 AVAILABLE -- `DARK_FACTORY_TEST_DATABASE_URL` is set in the environment, so the db tier is runnable after all."
  implication: "Retires the blind spot recorded in reasoning_checkpoint ('Full db suite needs Docker/Postgres; if unavailable the fix rests on mypy + collection + the non-db tiers'). The 8 real consumers of this fixture can be executed, so the fix does not have to rest on static analysis alone."

- timestamp: 2026-10-09T00:00:00Z
  checked: "All 8 db-tier consumer files run against the rung-3 Postgres, with the fix in place"
  found: "28 passed, 0 failed in 1109s (18m29s). Covers every attempt-sensitive path through the real `drive()` orchestrator: QA bounce, iteration-cap exhaustion, feedback-reaches-developer (including the `_CapturingWorker` wrapper that forwards `context` unmodified), write-scope-enforced-on-bounce, events-reader-sees-every-bounce, qa-verdict-events, artifact-created-event, run-report."
  implication: "Closes the loop on the Evidence prediction that `isinstance(attempt, int)` cannot break any existing caller. The assert was executed on every role of every attempt of 28 real runs and never fired -- confirming the type-level `None` is genuinely unreachable in practice, which is precisely what the assert now states to mypy. The 18-minute runtime also explains why this tier is not in the fast loop, reinforcing the `why_not_caught` finding."

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: "`AttemptAwareFourRoleWorker._record` (tests/support/fake_artifacts.py) asserted its `role` invariant but never its `attempt` one. Because the `CodingWorker` port deliberately types `context: object` (src/dark_factory/workers/base.py:20, WORK-01 -- so no adapter couples to `RoleContext`), `getattr(context, 'attempt', None)` erases `RoleContext.attempt: int` to `Any | None`. `assert role in _FOUR_ROLE_FILES` narrows `role` to `Any` (assignable to the key's `str` slot) but nothing removes the `None` from `attempt`, so all three composed keys are `tuple[Any, Any | None]` and fail the three dicts' declared `tuple[str, int]` key type. Enabling precondition (not itself a defect): the untyped-port `getattr` idiom. Single actionable cause: the missing narrowing assert."

fix: "Added `assert isinstance(attempt, int), attempt` immediately after the existing `assert role in _FOUR_ROLE_FILES, role` in `_record` (tests/support/fake_artifacts.py:291), with a comment recording why it is load-bearing rather than type-checker appeasement. This narrows `Any | None` -> `int` at the construction site, making all three keys `tuple[Any, int]` with no cast and no `# type: ignore`. Deliberately an assert, NOT the repo's alternative `getattr(..., None) or 1` defaulting idiom (src/dark_factory/workers/hermes.py:279): silent defaulting is precisely the vacuous-pass mode this fixture must guard against. Added tests/unit/test_attempt_aware_worker_attempt_invariant.py (6 cases) as the recurrence guard."

verification:
  guardrail_verdict: accepted
  oracle_type: "specified (the mypy `tuple[str, int]` key contract) + derived (the fixture's own attempt-selection contract: a mapped `(role, attempt)` must yield its override, an unmapped one the shared default, a non-int must raise)"
  signal_1_regression_test_red_without_fix: "PASS -- removing only the assert turns `test_non_int_attempt_raises_instead_of_a_vacuous_pass` RED on BOTH parametrizations with `Failed: DID NOT RAISE AssertionError`, i.e. the pre-fix code returned a normal COMPLETED result carrying the PASS-shaped default. Directly demonstrates the vacuous-pass mode, not just the type error."
  signal_2_bug_returns_on_revert: "PASS -- with the assert removed, `uv run mypy --strict tests/support/fake_artifacts.py` re-emits the 3 original `[arg-type]` errors verbatim (`tuple[Any, Any | None]` vs `tuple[str, int]`) at the shifted lines 291/293/301 (shift = the 16 added comment/assert lines). Restored -> `Success: no issues found`."
  signal_3_mutation_at_fix_site: "PASS -- deleting the assert is the maximal mutation of a one-line guard (equivalent to replacing it with a tautology); it is killed by 2 of the 6 tests plus mypy. Boundary neighbours are also pinned: attempt 2 and 3 (the off-by-one neighbours of the mapped attempt 1) assert the `_FOUR_ROLE_FILES` fallback still works, so the narrowing cannot have turned the lookup into always-hit or always-miss."
  signal_4_not_deletion_only: "PASS -- the diff is +16 lines (1 assert + 15 comment lines), 0 deletions; plus a new 145-line test file. No code, test, assertion, or type annotation was weakened, and no key type was widened (widening to `tuple[str, int | None]` was explicitly eliminated)."
  signal_5_adjacent_tiers: "PASS -- `uv run mypy --strict` clean on both changed files; `ruff check` clean; `ruff format --check` clean; new test file 6/6 green; full unit tier 846 passed / 1 skipped. The 3 unit-tier ERRORS observed are provably NOT from this fix: 2 are a race with a concurrent session that deleted tests/unit/test_zz_tmp_tripwire_control.py mid-run (file no longer exists), and 1 is `test_unit_tier_needs_no_database` cascading from 2 `tests/unit/test_redaction.py` failures owned by the concurrent `checksum-redaction-false-positive-in-error-payload` session (uncommitted edits to src/dark_factory/events/redaction.py + tests/unit/test_redaction.py). `grep` confirms test_redaction.py has 0 references to `fake_artifacts`/`AttemptAwareFourRoleWorker`."
  signal_5_db_tier: "PASS -- all 8 db-tier files that consume this fixture ran green: 28 passed, 0 failed (1109s / 18m29s against the rung-3 remote Postgres). These exercise `_record` through the real `drive()` orchestrator across every attempt-sensitive scenario (QA bounce, iteration-cap exhaustion, feedback-reaches-developer, write-scope-on-bounce, events-reader-sees-every-bounce, run report), which is the decisive evidence that the new assert never fires on a legitimate context -- i.e. `attempt` is always a real `int` at runtime, exactly as Evidence predicted from the 11 construction sites."
  why_not_caught: "CI's typecheck step runs `mypy src/dark_factory` only (.github/workflows/ci.yml), so `tests/` is never type-checked in CI -- the 3 errors could only surface when a developer ran mypy over `tests` by hand (which is exactly how this was found, as an adjacent-tier check during a different session's guardrail). The runtime half had no gate at all: no test asserted the `attempt` invariant, and the fixture's own failure mode was a silent fallback rather than an exception."

files_changed:
  - "tests/support/fake_artifacts.py: added `assert isinstance(attempt, int), attempt` in `_record` (+ explanatory comment)"
  - "tests/unit/test_attempt_aware_worker_attempt_invariant.py: NEW -- 6-case recurrence guard (mapped attempt, 2 unmapped boundary neighbours, missing attempt, non-int attempt, unknown role)"
