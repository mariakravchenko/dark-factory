---
phase: "10"
slug: "github-issue-intake-idempotent-publishing-comment-resume"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-28"
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| GitHub API -> Dark Factory | Issue title, body, comment text and label names are attacker-influenceable input reaching `NormalizedTask` and eventually a role's prompt. | Untrusted text |
| Dark Factory -> worker subprocess | `github_token` / `github_webhook_secret` must never appear in a worker's environment, prompt, artifact or event payload. | Infrastructure credentials |
| PyPI -> the build | New third-party dependency (`githubkit`) enters the supply chain. | Package artifact |
| Dark Factory -> GitHub | Outbound create-type side effects (PR, comment) visible to every collaborator. | Repository writes |
| GitHub -> Dark Factory | Pull-request list / comment responses are attacker-influenceable. | Untrusted API responses |
| Dark Factory -> a public GitHub issue | Comment bodies are world-readable and permanent. | Public text |
| Internet -> the webhook receiver | Unauthenticated network edge, the first non-CLI entry point in the codebase. | Inbound HTTP |
| The receiver -> Neon | Receiver shares the DB with the orchestrator and can move a run's lifecycle state. | Run state mutation |
| Dark Factory -> Dark Factory | GitHub fires `issue_comment` for Dark Factory's own posted question -- Dark Factory is its own untrusted input source here. | Self-authored text |
| shipped `.dark-factory.yaml` -> throwaway `tmp_path` repo | A config authored for dark-factory's own checkout crosses into an environment satisfying neither -- the G-10-1 boundary. | Repo-local config |
| harness gate command string -> `shlex.split` -> `shell_execute` subprocess | A configured command string becomes a spawned process. | Shell argv |
| `runner.py` source -> structural guard assertion | What the guard accepts is the entire enforcement of the SEC-01 single-scrub-path contract. | Source code (AST) |
| untracked working-tree file -> committed repository | Evidence in one dev's working tree is not evidence the project holds. | Test evidence |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-10-SC | Tampering | `uv add githubkit` (PyPI) | high | mitigate | `uv.lock` pins githubkit 0.16.1 with sha256; human checkpoint verified PyPI project/repo/name before install (10-01-SUMMARY.md) | closed |
| T-10-01 | Information Disclosure | `github/client.py` error paths | high | mitigate | `_raise_api_error` -> `redact(..., known_secrets=...)`; every `except GitHubException` arm routes through it | closed |
| T-10-02 | Elevation of Privilege | `Settings.github_token` reaching a worker | high | mitigate | Token unwrapped at exactly one frame each in `client.py`/`runner.py`/`publish.py`; `WORKER_ENV_ALLOWLIST` excludes `GITHUB_TOKEN` | closed |
| T-10-03 | Tampering | issue text entering `NormalizedTask` | medium | mitigate | No `eval`/`exec`/`yaml.load` in `loaders.py`; comment text concatenated as data only | closed |
| T-10-04 | Spoofing | which repository the issue is fetched from | medium | mitigate | `_POSITIVE_INTEGER_LOCATOR` validation; owner/repo read only from the `repository` snapshot mapping | closed |
| T-10-07 | Information Disclosure | `github_webhook_secret` | medium | mitigate | `SecretStr \| None`; covered by `known_secret_values()`'s `model_fields` walk automatically | closed |
| T-10-08 | Repudiation | a crash between `pulls.create` and its commit | high | mitigate | Existence read runs before every create; `PUBLISH_STARTED` appended before the GitHub call | closed |
| T-10-09 | Spoofing | adopting a pull request that is not this run's | high | mitigate | Adoption matches on head-branch equality against deterministic `working_branch_name(run_id)` only | closed |
| T-10-10 | Tampering | a resumed step rewriting an existing pull request | medium | mitigate | Adoption branch issues no write at all -- no retitle/body/base/reopen | closed |
| T-10-11 | Denial of Service | treating an unreadable GitHub state as "no PR exists" | medium | mitigate | `GitHubError` on the existence check returns a failed `PublishResult`, never falls through to create | closed |
| T-10-12 | Information Disclosure | the clarification comment body | high | mitigate | `build_clarification_comment` takes only the question list -- no identifiers in scope | closed |
| T-10-13 | Information Disclosure | agent-authored question text republished publicly | medium | accept | Question text already redacted in the one mutation path; constraining role questions is out of scope (D-08) | closed |
| T-10-14 | Spoofing | a machine question read as a human one | medium | mitigate | `CLARIFICATION_COMMENT_PREFIX` fixed marker naming Dark Factory as asker | closed |
| T-10-15 | Denial of Service | repeated comment posting on every resume | medium | mitigate | Skip-post when `clarification_comment_id` already set (D-05 persisted-identifier check) | closed |
| T-10-16 | Repudiation | a question lost to a GitHub outage | high | mitigate | `create_comment` wrapped in `GitHubError` catch; pause/WAITING/question all still committed by the same transaction | closed |
| T-10-17 | Information Disclosure | `github_token` reaching a worker or a log | high | mitigate | Client obtained only through the `github_client_factory` seam; allowlist/env untouched | closed |
| T-10-18 | Spoofing | inbound webhook POST | critical | mitigate | `githubkit.webhooks.verify` over raw bytes before any parse/session/log; unset secret fails closed (401); no hand-rolled HMAC | closed |
| T-10-19 | Elevation of Privilege | Dark Factory answering its own question | high | mitigate | Two independent filters: comment id vs `clarification_comment_id`, AND commenter login vs `authenticated_login()` | closed |
| T-10-20 | Tampering | replayed or redelivered deliveries | high | mitigate | Business-level dedup on `github_comment_id`; `submit_answer`'s `WAITING_HUMAN` guard inside the lease | closed |
| T-10-21 | Denial of Service | pipeline execution at the network edge | high | mitigate | Receiver's only mutation is `submit_answer`; import-closure guard asserts no `advance`/`drive` reachability | closed |
| T-10-22 | Information Disclosure | rejection and error responses | medium | mitigate | Every non-success response carries a fixed short string; `IgnoreReason` logged server-side only | closed |
| T-10-23 | Information Disclosure | `github_webhook_secret` in logs or events | medium | mitigate | `SecretStr \| None` + structlog redaction processor installed before `JSONRenderer` | closed |
| T-10-24 | Tampering | untrusted comment text reaching a role's prompt | medium | mitigate | Answer stored through the one mutation path (redacted); receiver derives no control flow from body | closed |
| T-10-25 | Spoofing | answering a run the commenter has no relationship to | high | mitigate | Query requires `source_kind`, `WAITING_HUMAN`, `WAITING` interaction, AND owner+repo+issue_number together | closed |
| T-10-26 | Elevation of Privilege | a second `githubkit` call site outside the wrapper | high | mitigate | AST walk over whole source tree; 3-entry reasoned allowlist; catches all import shapes | closed |
| T-10-27 | Elevation of Privilege | the webhook package gaining the ability to run the pipeline | high | mitigate | Name-level AST walk for `advance`/`drive` imports and calls under `webhook/`, incl. aliased imports | closed |
| T-10-28 | Tampering | the orchestrator core importing the receiver | medium | mitigate | Transitive import-closure walk from five core roots asserts `dark_factory.webhook` unreachable | closed |
| T-10-29 | Repudiation | a structural guard that silently matches nothing | high | mitigate | Every walk ships self-sanity tests (violating/non-violating/emptied-allowlist cases) | closed |
| T-10-30 | Denial of Service | an allowlist pointing at a renamed file | low | mitigate | Test asserts every allowlisted path exists on disk | closed |
| T-10-31 | Elevation of Privilege | `Settings.github_token` reaching a worker (publish path) | high | mitigate | Exactly 3 `get_secret_value()` frames repo-wide, none in a worker-env path; corroborated by the live-run PR | closed |
| T-10-05 | Tampering | writes reaching the base branch | high | mitigate | `push_working_branch` pushes only the run's working branch; base appears only as the PR's `base` param | closed |
| T-10-06 | Repudiation | a publish attempt with no durable trace | medium | mitigate | `PUBLISH_STARTED` before the call, exactly one of `PR_CREATED`/`PUBLISH_FAILED` after, one `apply_transition` | closed |
| T-10-32 | Repudiation | a run reported COMPLETED with no pull request | high | mitigate | Failed `create_pull_request` sets `Signal.ROLE_FAILED`; run cannot reach COMPLETED | closed |
| T-10-33 | Tampering | a second writer to the publish columns | medium | mitigate | Factual half holds (grep confirms `pr_number`/`pr_url`/`published_commit_sha` writes exist only in `mutations.py`); the AST walk (`test_single_mutation_path.py`) does not yet cover these three column names -- a future writer outside `mutations.py` would trip nothing today | open — below `high` threshold (non-blocking) |
| T-10-34 | Information Disclosure | internal state inside the PR body | medium | mitigate | PR body emits only the source-issue link + attribution line -- no run id/worktree path/worker name/branch/credential | closed |
| T-10-07-01 | Tampering | `neutralize_repo_local_config` | medium | mitigate | Snapshot-diff test asserts differing keys are exactly `{quality_gate, publishing}` | closed |
| T-10-07-02 | Tampering / Elevation | `HARNESS_GATE_COMMANDS` -> `shell_execute` | low | mitigate | Fixed module constant, never task/repo-derived; `shlex.split`, no `shell=True` anywhere in `src/` | closed |
| T-10-07-03 | Information disclosure | copied `.dark-factory.yaml` under `tmp_path` | low | accept | Config contains no secret values by construction; harness rewrites exactly two keys | closed |
| T-10-07-04 | Repudiation | the three negative-control tests | high | mitigate | All three assert persisted `role_executions.error` content, not just exit code | closed |
| T-10-07-05 | Spoofing | `publishing.create_pr: false` in the harness | medium | accept | Deferred live-publish proof now discharged: real PR opened once at `mariakravchenko/app-new/pull/10` (UAT test 2) | closed |
| T-10-08-01 | Repudiation | LOOP-04 adjacency evidence | medium | mitigate | Untracked throwaway promoted to a committed `tests/db/` test | closed |
| T-10-08-02 | Information disclosure | narrowed redaction guard | high | mitigate | Named allowlist + no-question/answer assertion + self-detection counterexample test | closed |
| T-10-08-03 | Tampering | `ast`-based extraction over `runner.py` | low | accept | Parses first-party source via `__file__`, `ast.parse` only, no eval/compile/exec | closed |
| T-10-08-04 | Repudiation | adjacency assertion pointed at the wrong event | medium | mitigate | Asserts reason on `ROLE_FAILED` event + `role_executions.error`; inverts the `RUN_FAILED` no-exhaustion-key assertion | closed |

*Status: open · closed · open — below `high` threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (`high`) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Follow-up (non-blocking):** T-10-33's AST walk in `tests/unit/test_single_mutation_path.py` covers the four lifecycle-constructor calls and `.status` assignments but not `.pr_number`/`.pr_url`/`.published_commit_sha`. Suggested one-line fix: extend `_violations()`'s guarded-attribute set to include the three publish columns. Not filed as a Phase 10 gap (medium severity, below the `high` block threshold, and the factual guarantee already holds today) — worth picking up in a future hardening pass.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-1 | T-10-13 | Agent-authored clarification question text is republished verbatim on the public GitHub issue. Already passes through `redact()` in the one mutation path (no known credential can survive), but the content itself is not further constrained — deciding what a role may ask is Phase 3's role-instruction surface, not this call site's (D-08 boundary). Constraining it here would mean Dark Factory rewriting a role's own words. | secure-phase audit (gsd-security-auditor) | 2026-09-28 |
| AR-10-2 | T-10-07-03 | The shipped `.dark-factory.yaml` copied into throwaway test repos contains no secret values by construction (its own header states infrastructure credentials live in `.env`/`Settings`), and the harness only rewrites two keys (`quality_gate`, `publishing`) — never injects a credential. No new disclosure surface. | secure-phase audit (gsd-security-auditor) | 2026-09-28 |
| AR-10-3 | T-10-07-05 | The shipped-config test harness forces `publishing.create_pr: false`, so these four tests never exercise the publish branch — a throwaway repo has no GitHub remote to publish to, and forcing one would require real credentials in the integration tier, a far larger risk than the coverage it buys. The live-GitHub proof was deliberately deferred to manual UAT rather than faked — and has since been discharged: a real PR opened exactly once at `github.com/mariakravchenko/app-new/pull/10` during this session's UAT test 2. | secure-phase audit (gsd-security-auditor) | 2026-09-28 |
| AR-10-4 | T-10-08-03 | The narrowed redaction guard's AST-based extraction parses a first-party source file (`runner.py`) from the installed package path — not untrusted input. `ast.parse` performs no evaluation; no new execution surface. | secure-phase audit (gsd-security-auditor) | 2026-09-28 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-28 | 44 | 43 | 1 (non-blocking, below `high`) | gsd-security-auditor (opus) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-28
