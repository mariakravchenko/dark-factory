---
phase: "07"
slug: "claude-code-the-first-real-worker"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-21"
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Dark Factory process -> `claude` subprocess | The parent holds `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`; the child must receive only `ANTHROPIC_API_KEY` plus the `WORKER_ENV_ALLOWLIST` names. | Environment variables |
| `claude` subprocess stdout/stderr -> run tree on disk | Untrusted, model-authored text crosses into files that `commit_run_artifacts` later force-adds onto the branch that becomes a public PR. | Log/artifact text |
| Repo/artifact content -> agent prompt -> agent's own native tools | Repo-controlled text reaches a model that can invoke `Bash`/`Write` inside the worktree. | Prompt text, tool invocations |
| GitHub-hosted runner -> repository contents | The workflow token can read repository contents; it must never be able to write, tag, or publish. | `GITHUB_TOKEN` scope |
| Pull-request author -> CI execution | A PR from a fork executes workflow definitions; the job must hold no secrets it does not need. | CI job environment |
| Human answer text -> agent prompt | `RoleContext.answer` and `previous.questions` are human- and model-authored text crossing into a `-p` argument. | Prompt text |
| Opaque `worker_session_id` (persisted in Neon) -> CLI argv | A value the orchestrator stored verbatim from a prior attempt is handed straight back to an external process. | Session id string |
| Model-authored `result` text -> orchestrator control flow | The `NEEDS_INPUT:` marker lets model output select a lifecycle branch. | Result text |
| Role config `tools:` grants -> the spawned agent's native tool surface | Operator-declared grants must bound what the external process can do with its own tools. | Tool grant config |
| Repo/artifact content -> agent prompt -> agent's native `Bash`/`Write` tools | Untrusted text can attempt to steer the agent into actions outside the role's intent. | Prompt text, tool invocations |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-07-01 | Information Disclosure | `ClaudeCodeWorker` -> attempt logs -> `commit_run_artifacts` | critical | mitigate | `_scrub_log_in_place` runs `redact()` with `Settings.known_secret_values()` in a `finally` block on every exit path; proven by `test_captured_output_is_redacted`. | closed |
| T-07-02 | Information Disclosure | worker subprocess environment | high | mitigate | Environment built only via `build_worker_env(...)`; `os.environ.copy()` structurally impossible, guarded by `tests/unit/test_no_environ_copy.py`. | closed |
| T-07-03 | Tampering | `subprocess.Popen` argv construction | high | mitigate | Argv always an explicit `list[str]`, never joined, never through a shell; prompt crosses as a single inert `-p` argument. | closed |
| T-07-04 | Denial of Service (of observability) | `ClaudeCodeWorker.execute` -> `orchestrator/runner.py` call site | high | mitigate | Outermost `try/except Exception` converts every failure into `WorkerResult(FAILED)`. | closed |
| T-07-05 | Denial of Service | hung/runaway `claude` subprocess and descendants | medium | mitigate | `Popen.wait(timeout=...)` plus `os.killpg(...)` with `start_new_session=True`; proven by grandchild-pid assertion. | closed |
| T-07-06 | Elevation of Privilege | prompt injection steering native tools | medium | accept | `--permission-mode dontAsk` refuses non-allowed actions, `cwd=work_dir` confines reads, `enforce_write_scope` (ROLE-05) independently rejects out-of-scope diffs after the fact; narrowed further by T-07-15/16 in plan 07-04. | closed |
| T-07-SC (07-01) | Tampering | npm/pip/cargo installs | low | accept | No package-manager install task this plan; 07-RESEARCH.md records zero new external packages. | closed |
| T-07-07 | Elevation of Privilege | `GITHUB_TOKEN` granted to the `quality` CI job | medium | mitigate | Top-level `permissions: contents: read`; job declares no `secrets:`. | closed |
| T-07-08 | Repudiation | a quality gate present but non-blocking | high | mitigate | Every CI step at default blocking behaviour; `test_no_worker_name_leak.py` fails the suite if the leak-guard step disappears or is defanged. Confirmed live in UAT Test 1 (real green run + real red run on deliberate leak). | closed |
| T-07-09 | Information Disclosure | secrets injected into a CI run | low | accept | `quality` job requests no secrets and runs no `db`/`integration` tier — no `DATABASE_URL` or agent credential in the runner environment to leak. Revisit at Phase 8 credential-gated integration jobs. | closed |
| T-07-SC (07-02) | Tampering | npm/pip/cargo installs | medium | mitigate | `uv sync --all-extras --dev --frozen` resolves strictly from committed `uv.lock`; zero new external packages this phase. | closed |
| T-07-10 | Tampering | `resume()` argv assembly with persisted session id | high | mitigate | Session id crosses as one opaque `list[str]` element after `--resume`, never joined/shell-interpreted/reformatted. | closed |
| T-07-11 | Spoofing | model-authored `result` text selecting `NEEDS_INPUT` branch | medium | accept | Deliberate D-01 convention: worst case is a spurious human-resolved pause; line-anchored regex plus empty-question degradation limit false triggers. Structured-output hardening deferred, recorded in 07-RESEARCH.md. | closed |
| T-07-12 | Information Disclosure | resume transcripts in `logs/<role>/` | critical | mitigate | `resume()` routes through the same spawn/redact/parse pipeline as `execute()`; redaction re-proven through `resume()` by a dedicated test. | closed |
| T-07-13 | Denial of Service | a hung `resume()` subprocess | medium | mitigate | Shares `Settings.worker_timeout_seconds` and process-group kill; re-proven by a `resume()`-specific timeout test. | closed |
| T-07-14 | Repudiation | contract suite weakened to accommodate the real adapter | high | mitigate | Acceptance criteria forbid weakening/skipping/adapter-conditioning any contract assertion. | closed |
| T-07-SC (07-03) | Tampering | npm/pip/cargo installs | low | accept | No package-manager install task this plan; zero new external packages recorded. | closed |
| T-07-15 | Elevation of Privilege | prompt injection into destructive shell/write actions | medium | mitigate | `--allowedTools` built strictly from `context.tools` with deny-by-omission; `enforce_write_scope` (ROLE-05) remains the authoritative after-the-fact boundary. | closed |
| T-07-16 | Elevation of Privilege | `artifacts.write` widening to whole worktree | medium | mitigate | `artifacts.write` excluded from `_TOOL_NAMES`; emits only a path-scoped `Edit(<artifacts glob>/**)` specifier. | closed |
| T-07-17 | Repudiation | contract table documenting an unenforced restriction | high | mitigate | Every `claude_code` entry names the real mechanism (`cwd=<worktree>`); unit test asserts the note is present. | closed |
| T-07-18 | Tampering | future capability added to `NATIVE_TOOL_CONTRACT` with no adapter translation | medium | mitigate | `_native_tool_contract_is_fully_translated` unit test asserts `_TOOL_NAMES` coverage equals `NATIVE_TOOL_CONTRACT` capabilities, failing the build on drift. | closed |
| T-07-19 | Repudiation | inertness guard deleted rather than narrowed | medium | mitigate | Guard renamed/narrowed to a three-path allowlist with a detects-its-own-subject sanity test. | closed |
| T-07-SC (07-04) | Tampering | npm/pip/cargo installs | low | accept | No package-manager install task this plan; zero new external packages recorded. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-06 | Prompt-injection into native tools accepted for the tracer scope; `dontAsk` permission mode + worktree `cwd` confinement + independent post-hoc `enforce_write_scope` bound the blast radius. Narrowed further by T-07-15/16. | Plan 07-01 author | 2026-09-21 |
| AR-07-02 | T-07-09 | No secrets or `db`/`integration` tier in the CI `quality` job — nothing to leak. Revisit when Phase 8 adds credential-gated integration jobs. | Plan 07-02 author | 2026-09-21 |
| AR-07-03 | T-07-11 | `NEEDS_INPUT:` marker deliberately trusts model-authored text to select a pause branch (D-01); worst case is a spurious human-resolved pause, not privilege escalation. | Plan 07-03 author | 2026-09-21 |
| AR-07-04 | T-07-SC (all 4 plans) | Zero new external packages introduced across Phase 7; `07-RESEARCH.md` §"Package Legitimacy Audit" records this for each plan. | Phase 7 author | 2026-09-21 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-21 | 21 | 21 | 0 | /gsd-secure-phase (L1 grep-depth, ASVS 1, register authored at plan time — short-circuit per workflow step 3) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-21
