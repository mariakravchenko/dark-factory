---
phase: "08"
slug: "copilot-hermes-worker-independence-proven"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-22"
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Dark Factory process -> `copilot` subprocess | The parent holds `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`; the child must receive only `COPILOT_GITHUB_TOKEN` plus the `WORKER_ENV_ALLOWLIST` names and the temp `XDG_*` entries. | infrastructure credentials |
| Dark Factory process -> `hermes` subprocess | The parent holds `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`; the child must receive only `ANTHROPIC_API_KEY` plus the `WORKER_ENV_ALLOWLIST` names, the temp `XDG_*` entries, and an isolated `HERMES_HOME`. | infrastructure credentials |
| Operator's real home-directory Hermes state -> `hermes` subprocess | The CLI's default state directory holds a session database and an environment file that can carry credentials and prior-run state from unrelated roles. | credentials, cross-run state |
| `copilot`/`hermes` subprocess stdout/stderr -> run tree on disk | Untrusted, model-authored text crosses into files that `commit_run_artifacts` later force-adds onto the branch that becomes a public PR. | worker credentials |
| Role YAML `outputs:` filenames -> adapter path resolution | Repository-controlled configuration text is joined into a filesystem path the adapter reads back. | path traversal |
| Repo/artifact content -> agent prompt -> the CLI's own native tools | Repo-controlled text reaches a model that can invoke native read/write/shell tools inside the worktree. | prompt injection surface |
| Role `tools:` grant list -> a runtime with no native restriction mechanism | A capability the configuration withholds cannot be withheld by any flag this CLI accepts. | capability confinement |
| Developer/CI machine with a real credential -> a live test's side effects | When live integration suites execute, they run a real agent runtime with a real credential on a real machine. | real credentials |
| Test environment configuration -> skip decision | Whether a suite runs at all is decided from `PATH` and `Settings`, both attacker-irrelevant but operator-mistakable. | availability of test coverage |
| Shipped role configuration -> which external process performs a role | A `worker:` value decides which binary runs with the run's worktree and a worker credential; the value is repository-controlled configuration. | worker identity/spoofing |
| Adapter-written run-tree content -> the branch that becomes a public PR | Artifacts and per-attempt logs written by three different external runtimes are force-added onto the working branch. | worker credentials, model output |
| Prompt text -> the test-support fake CLI's filesystem writes | The generated script derives both filenames and a destination directory from the prompt string it was handed. | path traversal (test-only) |
| Role A's worker subprocess -> role B's artifact subtree | Both live inside the same run worktree under `.dark-factory/runs/<run_id>/artifacts/`; nothing in the filesystem separates them, and the subprocess `cwd` reaches both. | cross-role artifact tampering |
| A granted capability -> the reach a runtime can actually restrict | `artifacts.write`/`artifacts.read` name a scope narrower than `repo.*`; two of the three shipped runtimes can express no such narrowing natively. | capability confinement |
| Worker-written artifact content -> `commit_run_artifacts` -> `push_working_branch` | Tampered content that survives the post-worker checks is committed to the working branch and pushed, after which it has left the machine and a later role's verdict is computed from it. | integrity of pushed artifacts |
| Published design contract (`NATIVE_TOOL_CONTRACT`) -> the reader deciding a future role's grants | A contract that overstates confinement causes an over-grant that looks deliberate in review. | documentation-as-control drift |
| The CR-01 negative-path proof -> the confidence the phase claims from it | A tamper test that no longer asserts the failure it was written to observe still reports green; the boundary between "proven" and "believed" is a single assertion in a shared harness. | test-integrity |
| `src/dark_factory/cli.py`'s D-05 exit mapping -> every downstream consumer of those codes | The Phase 11 CI trigger, `tests/integration/test_exit_codes.py`, and operators reading a run's outcome all decode the same three integers; a change here is costly to reverse and reaches beyond this phase. | exit-code contract integrity |
| The phase record (`08-05-SUMMARY.md` coverage entries) -> a future reader deciding whether a proof ran | Entries recorded as collection-verified are the only trace of how this defect escaped; overwriting them erases the evidence that motivated the execution gate. | audit-trail integrity |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Information Disclosure | `CopilotWorker` argv construction (`_base_argv`) | high | mitigate | Transcript-sharing flags never emitted; test asserts built argv disjoint from `_FORBIDDEN_COPILOT_FLAGS` | closed |
| T-08-02 | Information Disclosure | `CopilotWorker` logs -> `commit_run_artifacts` | critical | mitigate | `scrub_log_in_place` runs in a `finally` over both log files on every exit path before anything re-reads them | closed |
| T-08-03 | Information Disclosure | `copilot` subprocess environment | high | mitigate | Environment built only via `build_worker_env`; cross-process env-log readback proves no infra credential reaches the child | closed |
| T-08-04 | Elevation of Privilege | `--allow-tool` translation in `_base_argv` | high | mitigate | Blanket tool/path-permission flags never emitted; translation is deny-by-omission from `NATIVE_TOOL_CONTRACT` | closed |
| T-08-05 | Elevation of Privilege | Copilot's unscoped `read`/`write` vs Claude Code's path-scoped specifiers | medium | accept | `cwd` confines the worktree; `enforce_write_scope` reverts/fails any out-of-scope change post-attempt | closed |
| T-08-06 | Tampering | `subprocess.Popen` argv construction | high | mitigate | argv always an explicit `list[str]`, never joined/shell-interpreted | closed |
| T-08-07 | Tampering | role YAML `outputs:` filename -> path join | medium | mitigate | Every filename resolved through `resolve_under_run_root`, rejecting absolute paths/escapes/symlinks | closed |
| T-08-08 | Denial of Service (observability) | `CopilotWorker.execute` -> runner call site | high | mitigate | Outermost `try/except Exception` converts every failure into `WorkerResult(FAILED)` | closed |
| T-08-09 | Denial of Service | hung/runaway `copilot` subprocess and descendants | medium | mitigate | `worker_timeout_seconds` + process-group kill via `start_new_session=True` | closed |
| T-08-10 | Repudiation | `WorkerCapabilities` declared by `CopilotWorker` | medium | mitigate | Declaration derived from actual adapter behaviour; contract suite drives it against observed behaviour | closed |
| T-08-11 | Information Disclosure | `hermes` subprocess reading real home-directory Hermes state | high | mitigate | `HERMES_HOME` set to a role-scoped disposable subdirectory | closed |
| T-08-12 | Elevation of Privilege | Hermes-assigned role exercising a withheld capability | high | mitigate | `spawn_is_permitted` refuses any denied capability with no post-hoc control | closed |
| T-08-13 | Information Disclosure | `HermesWorker` logs -> `commit_run_artifacts` | critical | mitigate | `scrub_log_in_place` runs in a `finally` over both log files on every exit path | closed |
| T-08-14 | Information Disclosure | `hermes` subprocess environment | high | mitigate | Environment built only via `build_worker_env` + single `HERMES_HOME` key | closed |
| T-08-15 | Denial of Service | interactive-mode invocation hanging on DEVNULL stdin | medium | mitigate | Interactive flag never emitted, one-shot flag always emitted; timeout + process-group kill as backstop | closed |
| T-08-16 | Denial of Service (observability) | `HermesWorker.execute` -> runner call site | high | mitigate | Outermost `try/except Exception` converts every failure, incl. spawn refusal, into `WorkerResult(FAILED)` | closed |
| T-08-17 | Denial of Service | hung/runaway `hermes` subprocess and descendants | medium | mitigate | `worker_timeout_seconds` + process-group kill | closed |
| T-08-18 | Repudiation | narrowing a published security contract to unblock a configured assignment | high | mitigate | Surfaced at a blocking decision checkpoint; chosen option recorded in summary + `tools/native.py` docstring; honesty-guard test unchanged | closed |
| T-08-19 | Repudiation | a live suite silently never running | high | mitigate | `skipif` at module scope; module collected, skips reported with a named reason; "no tests ran" treated as failure | closed |
| T-08-20 | Information Disclosure | live test's captured transcript with a real credential | high | mitigate | Adapter `scrub_log_in_place` runs before `execute()` returns; run root inside `tmp_path`, outside checkout/committed tree | closed |
| T-08-21 | Tampering | live suite quietly repointed at a fake executable | medium | mitigate | Acceptance criterion asserts no live module imports any fake-CLI helper; docstring states the prohibition | closed |
| T-08-22 | Elevation of Privilege | live Hermes test granting a broad capability set | low | accept | Minimum grant set `spawn_is_permitted` admits, commented as such; `cwd` confinement limits reach | closed |
| T-08-23 | Spoofing | a run recording work as performed by a runtime that did not perform it | high | mitigate | Negative test: binary absent -> role fails visibly, recorded worker still equals configured one | closed |
| T-08-24 | Elevation of Privilege | reassigning a role to a runtime that cannot honour the role's capability denials | high | mitigate | `spawn_is_permitted` refuses Hermes for a denied-capability role; shipped `QA` grant confirmed admitted under the chosen checkpoint option | closed |
| T-08-25 | Tampering | widening `write_scope` to accommodate an adapter's logging side effect | high | mitigate | Named as a forbidden fix; executor stops and reports rather than editing scope | closed |
| T-08-26 | Tampering | prompt-derived filenames/directories driving writes in the generated fake CLI | medium | accept | Test-support code only, never shipped in `src/`; runs inside per-test temp worktree; adapter side separately mitigated by T-08-07 | closed |
| T-08-27 | Information Disclosure | three runtimes' transcripts committed onto the working branch in one run | high | mitigate | Each adapter's `scrub_log_in_place` runs before returning; all three transcripts redacted before force-add | closed |
| T-08-28 | Repudiation | a proof passing by quietly simplifying the configuration under test | medium | mitigate | First assertion: config trees differ only on `worker:` lines; relaxing any existing assertion forbidden | closed |
| T-08-29 | Tampering | a role's worker overwriting/deleting another role's artifact | critical | mitigate | `enforce_artifact_scope` enumerates via git, reverts out-of-subtree paths, fails role+run; proven on both runtimes + positive control | closed |
| T-08-30 | Tampering | a tampered artifact surviving into commit/push | critical | mitigate | Control runs before the artifact collect/commit/push sequence; ordering documented in `advance()`'s docstring | closed |
| T-08-31 | Elevation of Privilege | a role with no `artifacts.write` grant writing under the run's artifacts tree | high | mitigate | Allowed-pattern list empty for such a role; D-14 zero-tolerance polarity makes every path a violation | closed |
| T-08-32 | Information Disclosure | a role reading beyond intended artifact scope, no path-scoped read specifier | medium | accept | No post-hoc control can undo a read; residual documented in contract + adapter prose + pinned by test | closed |
| T-08-33 | Repudiation | a published contract claiming confinement the shipped code does not perform | high | mitigate | Overclaiming prose replaced with real posture; pinned by assertions tying contract text to `copilot._TOOL_NAMES` | closed |
| T-08-34 | Denial of Service (of correct runs) | an over-broad control reverting a role's own legitimate output or Dark Factory's own run-tree writes | medium | mitigate | Pathspec covers only `artifacts/` subtree; positive-control + mixed-scope tests assert legitimate work survives | closed |
| T-08-35 | Tampering | a "fix" that makes a failed run exit 0 (`cli.py::_drive_and_exit`) | critical | mitigate | Task 1 forbids editing the CLI; Task 2 gates on `git diff --numstat -- src/dark_factory/` empty; `test_exit_codes.py` runs in the same invocation | closed |
| T-08-36 | Repudiation | a "fix" that deletes/loosens the CR-01 exit assertion instead of correcting it | high | mitigate | Expectation made explicit per-caller with no default, plus a cross-check; acceptance criteria pin exactly one surviving assert + three explicit expectations | closed |
| T-08-37 | Repudiation | the harness silently accepting a drifted exit mapping | medium | mitigate | D-05 cross-check unreachable while mapping holds, fires the moment it drifts; acceptance criteria gate on its structural presence via AST check | closed |
| T-08-38 | Repudiation | `08-05-SUMMARY.md` coverage entries D4/D5/D6 rewritten instead of appended | medium | mitigate | Task 2 appends an addendum, gates on zero deleted lines for that file — verified: 53 added, 0 deleted | closed |
| T-08-39 | Denial of Service (of correct runs) | the repair applied uniformly to all three callers, breaking the positive control | medium | mitigate | Untampered control kept asserting the success exit code; without it every tamper-case assertion would still pass under a uniformly-failing scope check | closed |
| T-08-SC | Tampering | npm/pip/cargo installs | low | accept | Recorded once per plan (08-01 through 08-06): zero new external packages introduced across the phase — `copilot`/`hermes` are externally provisioned binaries, not project dependencies; 08-RESEARCH.md's Package Legitimacy Audit confirms | closed |

*Status: open · closed · open — below `high` threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-1 | T-08-05 | Copilot's unscoped native `read`/`write` names cannot express path-scoped narrowing; `cwd` confinement + `enforce_write_scope` compensate | plan 08-01 author | 2026-09 |
| AR-08-2 | T-08-22 | Live Hermes test's broad capability grant is the minimum `spawn_is_permitted` admits; `tmp_path` + `cwd` confinement bound the reach | plan 08-03 author | 2026-09 |
| AR-08-3 | T-08-26 | Prompt-derived path construction is test-support-only code, never shipped in `src/`, running inside a per-test temp worktree | plan 08-04 author | 2026-09 |
| AR-08-4 | T-08-32 | No post-hoc control can undo an out-of-scope read; residual documented in contract, adapter prose, and pinned by test | plan 08-05 author | 2026-09 |
| AR-08-5 | T-08-SC | Zero new external packages introduced across all six plans in this phase (08-RESEARCH.md Package Legitimacy Audit) | phase 08 authors | 2026-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-22 | 40 | 40 | 0 | `/gsd-secure-phase` (retroactive, plan-time register — short-circuit per ASVS L1, `register_authored_at_plan_time: true`) |

Every threat in this register was authored at plan time (all six `08-*-PLAN.md` files carry a `<threat_model>` block) with a stated disposition and mitigation, verified implemented across the phase's SUMMARY files and the passing test suites re-run during plan 08-06's execution (unit/contract: 640 passed; integration UAT set: 10 passed; db-tier four-role tests: 8 passed). At ASVS level 1 with `threats_open: 0` and a plan-time-authored register, the `gsd-security-auditor` deep-verification spawn was skipped per the documented short-circuit rule — L1 grep-depth confidence is sufficient; no L2/L3 boundary-placement or end-to-end trace verification was required.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-22
