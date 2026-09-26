---
status: resolved
trigger: "G-09-6 and G-09-7: LOOP-01 and LOOP-02 in tests/db/test_feedback_reaches_developer.py both fail with MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md when run against real PostgreSQL 17"
created: 2026-09-24
updated: 2026-09-26
resolution: "Fixed by 09-06-PLAN.md (commit 8df8f06): _record_and_maybe_rebuild now derives the worktree via ensure_worktree(base_branch, working_branch) read off the freshly loaded RunState, instead of the constructor's pre-computed repo_root. Behaviorally confirmed against real PostgreSQL 17: uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py -> 2 passed in 129.17s (0:02:09), 0 failed, 0 skipped. See 09-UAT.md tests 6-7."
---

## Current Focus

bug_class: Bohrbug (deterministic — both tests fail identically every run, given a real DB)

hypothesis: |
  H1 (test-fixture defect): `_CapturingWorker` is constructed with `repo_root=root`
  (the config root from `config_root_factory`, i.e. `<tmp_path>/repo`) and passes that
  value as the `repo_root` argument of `build_role_context`
  (tests/db/test_feedback_reaches_developer.py:190). The production runner instead
  passes `work_dir` — the git worktree — at src/dark_factory/orchestrator/runner.py:866.
  `worktree_path` (src/dark_factory/git/worktree.py:42) makes the worktree a SIBLING of
  repo_root: `<tmp_path>/dark-factory-runs/<run_id>/`. Therefore the rebuild resolves
  `run_root(<tmp_path>/repo, run_id)` = `<tmp_path>/repo/.dark-factory/runs/<run_id>/`,
  a directory that has never held a single artifact, while every artifact was written
  under `<tmp_path>/dark-factory-runs/<run_id>/.dark-factory/runs/<run_id>/`.
  design.md is simply the FIRST declared input of DEVELOPMENT, so it is the first read
  to fail — nothing about design.md specifically is broken.

test: |
  Non-DB differential experiment reproducing only the path arithmetic + filesystem read:
  build a real git repo at <tmp>/repo, ensure_worktree, write design.md via the same
  write_role_artifacts helper into run_root(work_dir, run_id), then call
  read_artifact_text() twice — once with run_root(root, run_id) and once with
  run_root(work_dir, run_id).

expecting: |
  CONFIRM H1 if the run_root(root, ...) read raises MissingArtifactContentError whose
  message matches the reported one verbatim in shape
  ("artifact file not found: .../.dark-factory/runs/<run_id>/artifacts/ARCHITECTURE/design.md")
  AND the run_root(work_dir, ...) read succeeds.
  REFUTE H1 if both reads fail or both succeed.

next_action: none — root cause confirmed; goal is find_root_cause_only, so no fix applied.

reasoning_checkpoint:
  hypothesis: "tests/db/test_feedback_reaches_developer.py:190 calls build_role_context with the REPO ROOT where the runner (runner.py:866) passes the WORKTREE; the worktree is a sibling of the repo root (worktree.py:42), so run_root() resolves to a directory that has never held an artifact, and design.md — DEVELOPMENT's first declared input — is the first read to fail."
  confirming_evidence:
    - "Direct observation (scratchpad experiment): read_artifact_text(run_root(repo_root, run_id), 'artifacts/ARCHITECTURE/design.md') raises MissingArtifactContentError with a path matching the reported error verbatim in shape; the identical read against run_root(work_dir, run_id) succeeds and returns the 89-char '# Design' fixture."
    - "worktree_path() returns <repo_root.parent>/dark-factory-runs/<run_id> — observed not equal to repo_root."
    - "runner.py:866 is the ONLY production call of build_role_context and it passes work_dir (grep over src/)."
    - "The reported error path contains no 'dark-factory-runs/' component and only ONE '.dark-factory/runs/<run_id>' segment — the signature of repo_root, not work_dir."
    - "Differential control: test_qa_bounce.py drives the same four-role pipeline with the same fixture worker and the same required design.md input and PASSES — it only passes repo_root to drive(), never to build_role_context."
    - "Differential control: test_context_builder_retry_isolation.py calls build_role_context(db_session, tmp_path, ...) and PASSES — because it also WRITES its artifacts under run_root(tmp_path, run_id) and never creates a worktree, so its root is self-consistent."
  falsification_test: "If both arms of the experiment had failed (or both succeeded), the root argument would not be the discriminator and the fault would lie in the artifact-commit machinery instead."
  fix_rationale: "Not applied (find_root_cause_only). The minimal correct change is to construct _CapturingWorker with repo_root=work_dir (both tests already compute work_dir at lines 262 and 358), or — more faithful to the D-07 claim the test makes — to call ensure_worktree(root, run_id, ...) inside _record_and_maybe_rebuild exactly as _advance_once does, and pass its return value. Either addresses the root cause (wrong root) rather than the symptom (one missing file)."
  blind_spots: "This sandbox has no PostgreSQL 17 (pg_ctl/psql/initdb absent, docker unavailable), so the db-tier tests could not be executed before or after. 'Fixing the root argument makes both tests green' is REASONED (the rebuild then runs identical code against identical DB state as the runner's own passing build) but NOT empirically verified. A second, latent assertion failure behind this first exception cannot be fully excluded."
  candidate_causes:
    - "code (test-side): wrong repo_root argument threaded into build_role_context — CONFIRMED"
    - "code (production): runner/context-builder path mismatch — REFUTED, runner.py:866 passes work_dir correctly"
    - "environment: worktree/git state in this sandbox — REFUTED, worktree_path() is pure arithmetic on repo_root.parent and diverges on every platform, not just here"
    - "data: artifacts row .path persisted wrongly — REFUTED, artifact_row.path is the run-root-relative 'artifacts/ARCHITECTURE/design.md', correct for either root; only the root differs"
  and_gate: "no — the failure is unconditional once a database exists. With the wrong root, _resolve_input's REQUIRED design.md lookup raises on every execution; no second condition has to co-occur. The absence of PostgreSQL in phases 6-9 is a DETECTION gap, not a contributing cause."

## Symptoms

expected: |
  test_qa_fail_delivers_structured_issues_to_developer_attempt_2 and
  test_gate_fail_delivers_real_command_output_to_developer_attempt_2 both drive a real
  four-role [BA, ARCHITECTURE, DEVELOPMENT, QA] pipeline via AttemptAwareFourRoleWorker,
  and expect the Developer's rebuilt RoleContext on attempt 2 to resolve successfully
  (carrying either verdict.json or quality_gate.json as an optional_input, per
  09-03-PLAN.md's feedback-delivery design).
actual: |
  Both tests FAILED with:
    dark_factory.artifacts.MissingArtifactContentError: artifact file not found:
    <tmp>/.dark-factory/runs/<run_id>/artifacts/ARCHITECTURE/design.md
  raised from:
    tests/db/test_feedback_reaches_developer.py:189 (_record_and_maybe_rebuild)
    -> src/dark_factory/context/builder.py:327 (build_role_context)
    -> src/dark_factory/context/builder.py:201 (_resolve_input)
    -> src/dark_factory/artifacts/store.py:41 (read_artifact_text)
errors: |
  dark_factory.artifacts.MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md
reproduction: |
  uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py
  Requires real PostgreSQL 17.
started: |
  09-03-PLAN.md added this test module in phase 9. Never executed against a real database
  until today — every phase 6-9 sandbox lacked PostgreSQL 17.

## Eliminated

- hypothesis: "(a) A real bug in how ARCHITECTURE's committed artifact is discoverable at context-rebuild time — a production path mismatch between commit_run_artifacts and read_artifact_text."
  evidence: "runner.py:861-866 resolves BOTH the run tree (`run_dir = run_root(work_dir, run_id)`) and the role context (`build_role_context(..., work_dir, ...)`) against the same `work_dir`. grep over src/ shows runner.py:866 is the ONLY production call of build_role_context. The runner's own build of the DEVELOPMENT attempt-2 context succeeded — it had to, because worker.execute() was reached, which is where the test's rebuild raised. Arm B of the experiment reads the same artifact under work_dir successfully."
  timestamp: 2026-09-24

- hypothesis: "(c) Environment-specific — the worktree/git state in this particular sandbox."
  evidence: "worktree_path() (git/worktree.py:42) is pure path arithmetic — `repo_root.resolve().parent / 'dark-factory-runs' / str(run_id)` — with no environment input. The divergence reproduces deterministically on this machine with no database at all, and would reproduce identically anywhere. Observed: worktree = <tmp>/dark-factory-runs/<id>, repo_root = <tmp>/repo, `same directory? False`."
  timestamp: 2026-09-24

- hypothesis: "The ARCHITECTURE role never ran, or its artifacts were never committed before the rebuild (fixture-ordering bug in AttemptAwareFourRoleWorker)."
  evidence: "AttemptAwareFourRoleWorker._record (tests/support/fake_artifacts.py:272-277) writes the role's files at execute() time into `self._run_root`, which both tests set to `run_root(work_dir, run_id)` (test lines 261 and 361) — the correct worktree run root. Experiment confirms design.md lands on disk there and is readable. ARCHITECTURE must also have COMPLETED, because _resolve_input got past its `_latest_completed_execution is None` and `artifact_row is None` guards (builder.py:182-199) and reached the filesystem read at builder.py:201 — the reported traceback proves the DB rows exist and only the FILE was missing."
  timestamp: 2026-09-24

- hypothesis: "Write-scope enforcement (D-14 zero tolerance, `write_scope: []`) reverted design.md before the rebuild — the phase4-artifact-commit-bugs knowledge-base pattern."
  evidence: "Refuted by the same builder.py:201 reasoning above plus Arm B: the file is present and readable under the worktree run root. Every role in this fixture writes only its own declared artifacts (force-added by commit_run_artifacts) plus, in LOOP-02, a sentinel deliberately placed under the gitignored `.dark-factory/runs/` prefix precisely to avoid enforce_write_scope (fake_artifacts.py:228-237)."
  timestamp: 2026-09-24

## Evidence

- timestamp: 2026-09-24 (phase 0)
  checked: .planning/debug/knowledge-base.md
  found: One prior entry — phase4-artifact-commit-bugs. Root cause was stale test fixtures declaring `write_scope: []` (D-14 zero tolerance) while their own workers wrote non-artifact files, causing enforce_write_scope to revert files and fail the run.
  implication: Adjacent machinery (artifact commit + write-scope revert in runner.py) is a known source of "file I wrote disappeared" symptoms. Hypothesis candidate: design.md is written but reverted/cleaned before the rebuild. Must test, not assume.

- timestamp: 2026-09-24 (phase 1)
  checked: tests/db/test_feedback_reaches_developer.py lines 149-205, 262-279, 358-377
  found: |
    `_CapturingWorker.__init__` takes `repo_root` and stores it as `self._repo_root`.
    `_record_and_maybe_rebuild` (line 189-191) calls
    `build_role_context(fresh_session, self._repo_root, self._run_id, fresh_state, role_def)`.
    Both tests construct it with `repo_root=root` (lines 275 and 373) — the value returned
    by `_write_four_role_tree(config_root_factory)`, i.e. `<tmp_path>/repo`.
    Both tests separately compute `work_dir = ensure_worktree(root, ...)` (lines 262, 358)
    and hand `run_dir = run_root(work_dir, run_id)` to the fixture worker (lines 261, 361).
  implication: The fixture WRITES artifacts under work_dir but the rebuild READS under root.

- timestamp: 2026-09-24 (phase 1)
  checked: src/dark_factory/context/builder.py:201, src/dark_factory/artifacts/paths.py:27
  found: |
    `_resolve_input` reads `read_artifact_text(run_root(repo_root, run_id), artifact_row.path)`.
    `run_root(repo_root, run_id)` == `<repo_root>/.dark-factory/runs/<run_id>/`.
    The DB lookups (`_latest_completed_execution`, the ArtifactReference row) are root-
    independent and succeed; only the final filesystem read is root-dependent.
  implication: A wrong `repo_root` produces exactly this error class, and design.md is
    simply the FIRST entry of DEVELOPMENT's `inputs: [design.md, constraints.json]`.

- timestamp: 2026-09-24 (phase 1)
  checked: src/dark_factory/git/worktree.py:37-42
  found: "`worktree_path(repo_root, run_id)` == `repo_root.resolve().parent / 'dark-factory-runs' / str(run_id)` — a SIBLING of repo_root, documented as 'never a descendant of repo_root'."
  implication: repo_root and work_dir can never coincide; the divergence is structural.

- timestamp: 2026-09-24 (phase 1)
  checked: src/dark_factory/orchestrator/runner.py:843-866 + grep for build_role_context across src/
  found: |
    `_advance_once` computes `resolved_root = repo_root or Path.cwd()` (843), then
    `work_dir = ensure_worktree(resolved_root, ...)` (854), `run_dir = run_root(work_dir, run_id)`
    (861), and `build_role_context(context_session, work_dir, run_id, state, role_def)` (866).
    The module docstring at 777-780 states the rule explicitly: "``work_dir`` -- not
    ``resolved_root`` -- is what the run tree and the role context resolve against."
    runner.py:866 is the ONLY call of build_role_context anywhere in src/.
  implication: Production — including the resume path, which re-enters this same function and
    re-derives work_dir via the idempotent ensure_worktree on every attempt — is CORRECT.
    The defect cannot reach a real orchestrator run.

- timestamp: 2026-09-24 (phase 3, decisive experiment)
  checked: |
    Differential experiment with no database (scratchpad/repro_path_divergence.py): real git
    repo at <tmp>/repo via tests.support.git_repo.make_git_repo (same as config_root_factory),
    real ensure_worktree, real write_role_artifacts with _FOUR_ROLE_FILES["ARCHITECTURE"] into
    run_root(work_dir, run_id), then two read_artifact_text calls differing only in root.
  found: |
    repo_root                : <tmp>/repo
    work_dir                 : <tmp>/dark-factory-runs/<run_id>   (same directory? False)
    file on disk             : <tmp>/dark-factory-runs/<run_id>/.dark-factory/runs/<run_id>/artifacts/ARCHITECTURE/design.md  (exists: True)
    Arm A (root)             : MissingArtifactContentError: artifact file not found:
                               <tmp>/repo/.dark-factory/runs/<run_id>/artifacts/ARCHITECTURE/design.md
    Arm B (work_dir)         : SUCCEEDED, 89 chars, first line '# Design'
  implication: |
    CONFIRMED. Arm A's message is the reported error verbatim in shape — note it contains NO
    'dark-factory-runs/' component and exactly ONE '.dark-factory/runs/<run_id>' segment,
    which is the fingerprint of repo_root rather than work_dir. One root fails, the other
    succeeds, with everything else held constant.

- timestamp: 2026-09-24 (phase 3, controls)
  checked: tests/db/test_qa_bounce.py:230,318 and tests/db/test_context_builder_retry_isolation.py:230,251
  found: |
    test_qa_bounce.py passes `repo_root=root` only to `drive()` (which correctly derives
    work_dir) and never calls build_role_context — it PASSES on the same four-role pipeline
    with the same design.md input.
    test_context_builder_retry_isolation.py DOES call `build_role_context(db_session, tmp_path, ...)`
    but also writes its artifacts into `run_root(tmp_path, run_id)` and never creates a
    worktree — self-consistent, so it PASSES.
  implication: Clean pass/fail split. The only failing module is the only one that pairs a
    build_role_context call with a root different from the one its artifacts were written under.

- timestamp: 2026-09-24 (phase 3, severity note)
  checked: builder.py:326-336 against the test's own assertion at line 315
  found: |
    Because design.md is a REQUIRED input, the wrong root raises loudly. Had it been optional,
    `_resolve_optional_input` would have swallowed the MissingArtifactContentError and returned
    None — so with the wrong root the D-07 assertion
    `rebuilt[("DEVELOPMENT", 2)].inputs == dev_attempt_2.inputs` could never have held either
    (the rebuilt context would have resolved ZERO inputs against an empty directory).
  implication: The test as written is UNCONDITIONALLY red — it was never capable of passing,
    in any environment. The required-input read is what converts a silent wrong answer into a
    loud failure.

## Resolution

root_cause: |
  TEST-FIXTURE DEFECT, zero production impact.

  `_CapturingWorker` in tests/db/test_feedback_reaches_developer.py is constructed with
  `repo_root=root` (lines 275 and 373) — the config root `<tmp_path>/repo` — and passes that
  value as the `repo_root` argument of `build_role_context` at line 190. The production runner
  passes `work_dir` instead (src/dark_factory/orchestrator/runner.py:866), and
  `worktree_path` (src/dark_factory/git/worktree.py:42) places the worktree at
  `<repo_root.parent>/dark-factory-runs/<run_id>/` — a SIBLING of repo_root, never the same
  directory. `build_role_context` -> `_resolve_input` (builder.py:201) therefore resolves
  `run_root(<tmp_path>/repo, run_id)` = `<tmp_path>/repo/.dark-factory/runs/<run_id>/`, a
  directory into which no artifact has ever been written, while every artifact the fixture
  worker produced lives under
  `<tmp_path>/dark-factory-runs/<run_id>/.dark-factory/runs/<run_id>/`.

  `design.md` is not special: it is merely the first entry of DEVELOPMENT's
  `inputs: [design.md, constraints.json]`, so it is the first read to fail. The DB lookups
  ahead of it (ARCHITECTURE's COMPLETED execution row and its ArtifactReference row) all
  succeed — which is itself proof that ARCHITECTURE ran and committed correctly.

fix: |
  NOT APPLIED — goal was find_root_cause_only.
  Minimal: construct _CapturingWorker with `repo_root=work_dir` in both tests (work_dir is
  already in scope at lines 262 and 358). Better, and more faithful to the D-07 claim the
  module docstring makes: have `_record_and_maybe_rebuild` call
  `ensure_worktree(root, run_id, base_branch=..., working_branch=working_branch_name(run_id))`
  itself and pass its return value, mirroring `_advance_once` (runner.py:854-866) exactly —
  that is literally what a fresh process does.
verification: |
  NOT PERFORMED — no PostgreSQL 17 in this sandbox (pg_ctl/psql/initdb absent, docker
  unavailable), so the db tier cannot be executed here.
files_changed: []
