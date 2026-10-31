---
task: 261031-lhn-rename-dark-factory-s-own-github-api-tok
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [SEC-01, TOOL-04]
files_modified:
  - src/dark_factory/config/settings.py
  - src/dark_factory/events/redaction.py
  - src/dark_factory/github/client.py
  - src/dark_factory/github/__init__.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/tools/env.py
  - src/dark_factory/git/client.py
  - src/dark_factory/git/committed.py
  - tests/conftest.py
  - tests/support/shipped_config.py
  - tests/unit/test_settings.py
  - tests/unit/test_github_client.py
  - tests/unit/test_git_push.py
  - tests/unit/test_log_redaction.py
  - tests/unit/test_worker_env.py
  - tests/unit/test_claude_code_worker.py
  - tests/unit/test_copilot_worker.py
  - tests/unit/test_hermes_worker.py
  - tests/unit/test_shell_execute.py
  - tests/unit/test_git_worktree.py
  - tests/integration/test_worker_env_boundary.py
  - tests/integration/test_capability_denial_no_secret_leak.py
  - tests/integration/test_redaction_interactions.py
  - tests/integration/test_secret_redaction_e2e.py
  - tests/db/test_run_report.py
  - tests/db/test_artifacts_show_reads_committed_content.py
  - tests/db/test_secret_redaction_e2e_full_pipeline.py
  - README.md
  - docs/CONFIGURATION.md
  - docs/GETTING-STARTED.md
  - .env.example
  - .gitignore
  - scripts/scaffold_target_repo.py

estimate:
  tokens: 150000
  raw_tokens: 75000
  tasks: 5
  confidence: low

must_haves:
  truths:
    - "`Settings` exposes `dark_factory_github_token` and has no `github_token` attribute; `DARK_FACTORY_GITHUB_TOKEN` in the environment populates it."
    - "A value configured as `DARK_FACTORY_GITHUB_TOKEN` is still redacted everywhere it appears, carrying the label `[redacted:dark_factory_github_token]`."
    - "A `dark_factory_github_token` dict key, and a `dark_factory_github_token=<value>` key/value pair in untrusted text, are redacted by the D-15 key-name rule."
    - "Third-party text still carrying the old spelling (a target repo's own workflow echoed into a WorkerResult) is still redacted — the old D-15 vocabulary entry is retained, not replaced."
    - "A scaffolded target repo's generated `run.yml` / `resume.yml` reference `secrets.DARK_FACTORY_GITHUB_TOKEN` — a secret name GitHub permits a user to create — and never hand the reserved Actions auto-token to dark-factory as its own credential."
    - "`mypy --strict`, `ruff check`, `ruff format --check` are clean; the unit and contract tiers are green."
    - "No stale reference to the old field name or old env var name survives outside a documented three-file allowlist."
  artifacts:
    - src/dark_factory/config/settings.py
    - src/dark_factory/events/redaction.py
    - src/dark_factory/github/client.py
    - src/dark_factory/orchestrator/runner.py
    - scripts/scaffold_target_repo.py
    - README.md
    - docs/CONFIGURATION.md
    - docs/GETTING-STARTED.md
    - .env.example
  key_links:
    - "Settings field name -> `known_secret_values()` label -> `[redacted:<label>]`. The label IS the field name, so renaming the field changes observable redaction output in persisted payloads, logs and error messages. Any test asserting the old label while configuring the credential must change in lockstep."
    - "Settings field name -> `_SENSITIVE_KEYS` (events/redaction.py). This link is NOT automatic. `_SENSITIVE_KEYS` is a hand-maintained D-15 vocabulary of key names; the new name must be added by hand or key-name redaction coverage silently drops to nothing for the renamed credential. Proven empirically — see Task 1."
    - "`scripts/scaffold_target_repo.py` templates <-> README's `resume-workflow-reference` sentinel block. Guarded by `tests/unit/test_resume_workflow_reference_doc.py`; either changing alone is drift."
    - "`secrets.DARK_FACTORY_GITHUB_TOKEN` -> the GitHub platform rule that forbids a repository secret named `GITHUB_TOKEN`. The new name is creatable as a secret; the old one was not, which is why the old template silently resolved to the reserved auto-token."
---

<objective>
Rename dark-factory's own GitHub API credential from `github_token` / `GITHUB_TOKEN` to
`dark_factory_github_token` / `DARK_FACTORY_GITHUB_TOKEN` across production code, tests,
documentation, `.env.example`, and the target-repo scaffold templates.

Purpose: the literal name `GITHUB_TOKEN` collides with GitHub Actions' reserved
`secrets.GITHUB_TOKEN` — the ephemeral installation token auto-injected into every job.
A repository secret named `GITHUB_TOKEN` cannot be created, so a generated workflow
writing `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` silently resolves to that reserved
token, which can never call `GET /user` (a hard GitHub platform rule, not a
permissions-scoping gap). That produced a real live `403 Resource not accessible by
integration`. Distinguishing the name at the source makes the mistake unrepresentable.

Output: a credential whose attribute name, environment variable name, redaction label,
documentation and scaffolded workflow templates all agree, with D-15 redaction coverage
preserved for both the new and the old spelling.
</objective>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

@src/dark_factory/config/settings.py
@src/dark_factory/events/redaction.py
@src/dark_factory/github/client.py
@src/dark_factory/orchestrator/runner.py
</context>

<investigation_findings>
These were established empirically against the working tree before planning. Treat them as
given; do not re-derive them.

**F1 — The consumer set is wider than the task brief stated.** The brief named
`orchestrator/runner.py` as the confirmed consumer. `src/dark_factory/github/client.py` is a
second real attribute-access consumer (`GitHubClient.from_settings`, 3 accesses plus a
hardcoded redaction label), and `src/dark_factory/github/__init__.py` documents the field by
name in two docstrings.

**F2 — The brief's assumption about `events/redaction.py` is HALF RIGHT, and the other half
is a security regression.** The assumption that `[redacted:github_token]` in the *pattern
table* is a shape-matched descriptive label independent of the Settings field name is
CORRECT — those rows match token shapes (`ghp_*`, `github_pat_*`, bare 40/64-hex) and must
keep their label. But two couplings were missed:

- `_SENSITIVE_KEYS` (redaction.py line 41) contains the literal key name. It is a
  hand-maintained D-15 vocabulary, matched against dict keys and `key=value` text in
  untrusted content. The renamed key is NOT covered by it, and the alternation regex
  `\b(<keys>)\b` cannot match the old entry inside the new name because the preceding
  character is an underscore (a word character, so no word boundary). Measured against the
  real `redact()`:

  | input | today | after rename, if `_SENSITIVE_KEYS` is left alone |
  |---|---|---|
  | `GITHUB_TOKEN=abcd1234secretvalue` | `GITHUB_TOKEN=[redacted:github_token]` | unchanged |
  | `DARK_FACTORY_GITHUB_TOKEN=abcd1234secretvalue` | n/a | **value passes through in the clear** |
  | `{"DARK_FACTORY_GITHUB_TOKEN": "abcd1234secretvalue"}` | n/a | **value passes through in the clear** |

  So the new name must be ADDED to `_SENSITIVE_KEYS`. The old entry must be RETAINED — a
  target repo's own workflow text echoed into a `WorkerResult` still uses the old spelling,
  and dropping it would be a second, opposite regression.

- `Settings.known_secret_values()` returns `{secret_value: field_name}`, and `_scrub_known`
  interpolates that field name directly into `[redacted:<label>]`. Renaming the field
  therefore changes observable redaction output for the *exact-value* path.

**F3 — Known-value substitution beats the pattern table, so the label changes even for a
shape-matching token.** `_redact_str` runs `_scrub_known` before `_PATTERNS`. Measured:

```
ghp_LIVEint06github00000000000000000000000000   (40 chars after the prefix)
  not configured            -> [redacted:github_token]              (pattern)
  configured under new name -> [redacted:dark_factory_github_token]  (known value)
  re-redacting that output  -> unchanged (idempotent, no pattern re-match)
```

**F4 — The classification rule for every `[redacted:github_token]` assertion.** Follows
directly from F3, and is the rule a blind find-and-replace gets half wrong:

> If the test **configures** the credential into `Settings` (so the value is in
> `known_secret_values()`), the label becomes `[redacted:dark_factory_github_token]`.
> If the test relies **only on the token's shape** (credential unset, or the label is passed
> in as a literal `known_secrets` argument), the label stays `[redacted:github_token]`.

Pre-classified:

| site | provenance | label |
|---|---|---|
| `tests/unit/test_redaction.py` (all 13 sites) | pattern table, or a test-supplied literal `known_secrets` label | **stays** |
| `tests/unit/test_log_redaction.py:126` | pattern (the test `delenv`s the credential first) | **stays** |
| `tests/unit/test_git_push.py:249` | known value (`setenv` at line 210; the token matches no pattern) | **changes** |
| `tests/integration/test_redaction_interactions.py:283,293` | known value (configured at line 132) | **changes** |
| `tests/integration/test_secret_redaction_e2e.py:342` | known value (configured at line 139) | **changes** |

Note `test_log_redaction.py` is a split case: its three `delenv` calls must be renamed (they
exist to force the credential unset) while its label assertion must not. This is the single
likeliest place to get the rename wrong.

**F5 — Nothing reads the environment variable directly.** `grep` for `os.environ[...]` /
`os.getenv(...)` against the name returns zero hits in `src/`, `tests/` and `scripts/`.
`Settings` is the only reader, so the environment-variable rename has exactly one binding
site. This repository's own `.github/` workflows never reference the name either.

**F6 — `Settings.model_config` sets `extra="ignore"`.** A stale `github_token=` keyword in a
`Settings(...)` call will therefore be *silently dropped* rather than raising. Those call
sites fail later, at an assertion, with the credential unset — never at construction. Do not
rely on an error to find them; rely on Gate A.

**F7 — Allowlisted residual sites (must survive unchanged).** After the rename, exactly three
files legitimately still contain the old spelling:

1. `src/dark_factory/events/redaction.py` — the retained `_SENSITIVE_KEYS` entry (per F2).
2. `tests/unit/test_redaction.py` — a test-supplied literal `known_secrets` label argument.
3. `tests/integration/test_phase6_acceptance.py` (2 sites) — **verbatim quotations of frozen
   Phase 6 success-criteria and `TOOL-04` requirement text.** These mirror `.planning/`
   artifacts, which are out of scope; editing them would create drift against the frozen
   phase record. Leave them.

**F8 — Confirmed out of scope by inspection.** `copilot_github_token` /
`COPILOT_GITHUB_TOKEN` is a genuinely separate worker credential
(`workers/copilot.py`, `tests/support/live_runtime.py:64`, `tests/support/fake_copilot_cli.py`)
— untouched. The webhook subsystem is gone: `dispatch_github_token` no longer exists on
`Settings`, and no stale reference to it survives anywhere in `src/` or `tests/`. Separately,
`tests/unit/test_copilot_worker.py:226,232` *is* in scope despite living in a copilot test
file — those two lines concern dark-factory's own credential not leaking into the copilot
child process.

**F9 — `.claude/CLAUDE.md` and `.planning/PROJECT.md` are deliberately excluded.** Both
describe the credential-boundary principle by naming the credential class. `CLAUDE.md` is
generated/mirrored from `.planning/PROJECT.md`, which this task does not touch, so editing it
would be overwritten and would drift from its source. Flagged for the next regeneration of
those documents rather than silently omitted.
</investigation_findings>

<naming_discipline>
Two rules apply to every task below.

1. **Attribute name and environment variable name must agree.** Use the field
   `dark_factory_github_token` bound to `DARK_FACTORY_GITHUB_TOKEN` by pydantic-settings'
   default upper-casing. Do **not** add a `validation_alias`, `AliasChoices`, or any
   backward-compatibility alias — a mismatched field/env pair is precisely the confusion this
   task exists to remove.

2. **When rewording a comment or docstring, describe the new name only.** Do not carry the
   old spelling into replacement prose "for context". Gate A scans `src/` and `tests/`
   including comments, so a helpful explanatory comment naming the old spelling will fail the
   gate. The one place the old spelling may be discussed is prose in `README.md` /
   `docs/CONFIGURATION.md` (Task 5), which Gate A does not scan — and there it is genuinely
   valuable.
</naming_discipline>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Rename the credential end-to-end through production code, closing the D-15 coverage regression</name>
  <files>src/dark_factory/config/settings.py, src/dark_factory/events/redaction.py, src/dark_factory/github/client.py, src/dark_factory/github/__init__.py, src/dark_factory/orchestrator/runner.py, tests/conftest.py, tests/unit/test_settings.py, tests/unit/test_github_client.py, tests/unit/test_git_push.py, tests/unit/test_log_redaction.py</files>
  <read_first>src/dark_factory/config/settings.py, src/dark_factory/events/redaction.py (lines 28-50 and 186-220), src/dark_factory/github/client.py (lines 120-160)</read_first>
  <behavior>
    New coverage to add to `tests/unit/test_redaction.py` (or a sibling unit module) BEFORE
    changing `_SENSITIVE_KEYS`, so the regression in F2 is observed red first:

    - Test A: `redact("DARK_FACTORY_GITHUB_TOKEN=abcd1234secretvalue", known_secrets={})`
      removes the value and emits the new label. Red before the vocabulary edit (the value
      survives verbatim), green after.
    - Test B: the same for a mapping key — `{"DARK_FACTORY_GITHUB_TOKEN": "<value>"}` — since
      `redact()` dispatches on `key.lower() in _SENSITIVE_KEYS` on a separate code path from
      the `key=value` regex. Both paths must be proven; one passing does not imply the other.
    - Test C: the retention half of F2 — text using the old spelling in an assignment form is
      still redacted. This is what stops the vocabulary edit from being a replace instead of
      an add.
    - Test D: a credential configured into `Settings` and carrying no recognisable token
      shape is redacted under the new label, proving the F2 `known_secret_values()` coupling.

    Existing `Settings` coverage to update, per F4: `known_secret_values()` now labels the
    credential with the new field name.
  </behavior>
  <action>
Rename the field and every production consumer of it, then close the redaction-coverage
regression documented in F2.

`config/settings.py`: rename the `SecretStr | None` field to `dark_factory_github_token`,
keeping its `None` default and its position among the optional credentials. Rewrite the three
class-docstring passages that name it — the `DATABASE_URL`/`DATABASE_URL_DIRECT` paragraph,
the `anthropic_api_key`-is-also-optional comparison, and the `copilot_github_token`
separate-field rationale. That last paragraph is the most important prose in this task: it
already explains why a worker credential and dark-factory's own credential are deliberately
distinct fields, and it should now also record that the environment variable is deliberately
not the bare reserved name, because GitHub forbids creating a repository secret under that
name and auto-injects an installation token there instead — an installation token that cannot
call `GET /user`. Per naming_discipline rule 2, state this without writing the reserved name
itself; refer to it as the name GitHub reserves. `known_secret_values()` needs no change: it
walks `model_fields` and picks up the new name automatically — that automatic pickup is
exactly why the label changes.

`events/redaction.py`: ADD `dark_factory_github_token` to the `_SENSITIVE_KEYS` frozenset and
RETAIN the existing entry (F2 — this is an add, never a replace). Extend the comment above
the set to record that both spellings are carried deliberately: one is this project's own
credential, the other is still the spelling that appears in third-party workflow text a
worker may echo back. Leave every `_PATTERNS` row and every pattern label untouched — those
are shape-matched and name the credential class, not the field (F2, first half). Note
`_KV_KEYS` sorts the set before joining it into the alternation, and the new entry sorts
ahead of the old one, so the longer name is tried first and the shorter cannot shadow it.

`github/client.py`: update the three `from_settings` accesses, the hardcoded fallback
redaction label in `__init__` (it labels this same credential and must match the new field
name so one credential never produces two different labels), the module docstring, and the
`MissingGitHubCredentialError` message text so the message names the environment variable an
operator must actually set. `github/__init__.py`: update the two docstrings naming the field.

`orchestrator/runner.py`: update the four attribute accesses (two in the publish-step
`push_token` argument, two in the artifact-push `push_token` block) and the three comments
that name the field while explaining that a run which publishes nothing never needs it
configured.

`tests/conftest.py`: update the `fake_settings` fixture keyword. Per F6 a stale keyword here
is silently ignored rather than raising, which would quietly disarm every redaction fixture
in the suite — so verify the fixture's credential is actually populated after the edit rather
than assuming the edit took.

`tests/unit/test_settings.py`, `tests/unit/test_github_client.py`: update every field access,
`Settings(...)` keyword, environment-variable name, and the `known_secret_values()` label
assertion. `tests/unit/test_git_push.py`: both the `setenv` name and the label assertion
change together (F4). `tests/unit/test_log_redaction.py`: rename the three `delenv` calls and
leave the label assertion alone — this is the split case in F4; getting it wrong in either
direction produces a test that passes while proving nothing.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; uv run mypy --strict src/ &amp;&amp; uv run ruff check . &amp;&amp; uv run ruff format --check . &amp;&amp; uv run pytest -m "unit or contract" -q</automated>
  </verify>
  <done>
`mypy --strict`, `ruff check`, `ruff format --check` clean. The unit and contract tiers are
green. Tests A-D pass, and A/B were each observed failing before the `_SENSITIVE_KEYS` edit.
`Settings` has no attribute under the old name. The db and integration tiers are expected
red at this point; Task 2 closes them.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update the db- and integration-tier credential call sites and known-value label assertions</name>
  <files>tests/db/test_run_report.py, tests/db/test_artifacts_show_reads_committed_content.py, tests/db/test_secret_redaction_e2e_full_pipeline.py, tests/integration/test_capability_denial_no_secret_leak.py, tests/integration/test_redaction_interactions.py, tests/integration/test_secret_redaction_e2e.py</files>
  <action>
Update the `Settings(...)` keyword in each of these six modules to the new field name, and
rename the module-level fake-credential constants and any local variable names that carry the
old spelling so the greppability these security proofs rely on is preserved.

Then apply F4 to the three known-value label assertions: `test_redaction_interactions.py` (two
sites, in the swept question and the swept answer) and `test_secret_redaction_e2e.py` (one
site, in the captured log text). All three configure the credential into `Settings`, so
known-value substitution wins over the pattern table and the label is now the new field name
(F3). Confirm per site that the credential really is configured in that test's own setup
rather than assuming it from this list.

`test_secret_redaction_e2e_full_pipeline.py` and `test_capability_denial_no_secret_leak.py`
assert on seeded credential *values* and on the presence of a generic redaction marker, not on
this specific label, so they need the keyword and constant renames only. Per F6, a missed
keyword here does not raise — it silently unsets the credential and turns an SC5 security
proof into a test that asserts the absence of a value that was never configured. After editing,
confirm each seeded credential is still present in the configured settings object.

These tiers need real PostgreSQL and run long (the db tier is historically about an hour against
remote Neon, per STATE.md), so the automated gate below is static plus collection. Record the
full db-tier run as a deferred human-verification item in the summary, consistent with this
repository's established practice.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; uv run ruff check . &amp;&amp; uv run pytest --collect-only -q -m "db or integration" &gt;/dev/null &amp;&amp; test "$(grep -rniE '(^|[^_a-z])github_token' --include='*.py' tests/db/ tests/integration/ | grep -vi 'redacted:github_token' | grep -vc 'test_phase6_acceptance')" = "0"</automated>
  </verify>
  <done>
All six modules construct `Settings` with the new field name. The three known-value label
assertions name the new label; no other label assertion in these tiers changed. Collection
of the db and integration tiers succeeds with no import or fixture errors. The only residual
old-spelling hit under `tests/db/` and `tests/integration/` is the allowlisted
`test_phase6_acceptance.py` (F7). Full db-tier execution recorded as deferred.
  </done>
</task>

<task type="auto">
  <name>Task 3: Retarget the credential-boundary tests at the renamed environment variable</name>
  <files>tests/unit/test_worker_env.py, tests/unit/test_claude_code_worker.py, tests/unit/test_copilot_worker.py, tests/unit/test_hermes_worker.py, tests/unit/test_shell_execute.py, tests/unit/test_git_worktree.py, tests/integration/test_worker_env_boundary.py</files>
  <action>
These seven modules each seed dark-factory's own credential into the parent environment and
then assert it is absent from a child process environment, a command's captured output, or a
constructed git environment — the TOOL-04 / SEC-01 credential boundary.

They currently pass and will keep passing untouched, because the boundary is an additive
allowlist that excludes every name not on it. That is exactly the hazard: left alone they
would seed and assert an environment variable dark-factory no longer reads, so they would
still be green while no longer proving anything about the credential they are named for.
Retarget them — rename both the seeding call and the matching absence assertion in each
module, together, so each test still seeds a live credential and still proves that credential
does not cross the boundary.

`tests/unit/test_worker_env.py` carries the name as an entry in a collection of
expected-excluded variable names rather than as a bare pair; update that entry.
`tests/unit/test_copilot_worker.py` is in scope here despite its filename (F8): its two sites
concern dark-factory's own credential not reaching the copilot child process, not the copilot
worker credential, which stays untouched.

Prove the retargeted assertions are not vacuous: an assertion that a name is absent from a
child environment passes trivially if the seeding step no longer seeds anything. For at least
one module, confirm the seeded value is observable in the parent process at the moment the
child is spawned.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; uv run ruff check . &amp;&amp; uv run pytest tests/unit/test_worker_env.py tests/unit/test_claude_code_worker.py tests/unit/test_copilot_worker.py tests/unit/test_hermes_worker.py tests/unit/test_shell_execute.py tests/unit/test_git_worktree.py -q</automated>
  </verify>
  <done>
Each of the seven modules seeds and asserts the renamed environment variable, with seeding and
assertion changed in lockstep. The six unit-tier modules pass. At least one module carries a
non-vacuity check proving the seeded credential was actually present in the parent environment.
No worker-owned credential was modified.
  </done>
</task>

<task type="auto">
  <name>Task 4: Reword the credential-boundary comments and docstrings in production and test-support code</name>
  <files>src/dark_factory/tools/env.py, src/dark_factory/git/client.py, src/dark_factory/git/committed.py, tests/support/shipped_config.py</files>
  <action>
These four modules name dark-factory's own credential only in comments and docstrings that
describe the general credential-boundary principle — an allowlist that admits neither the
database URL nor this credential nor anything ending in an API-key suffix. There is no
attribute access and no behavior to change.

Reword each to the new name. `tools/env.py` has two sites (a module docstring and the comment
above the allowlist), `git/client.py` one (the comment above its own allowlist),
`git/committed.py` one (a module docstring explaining which credentials must not reach a child
process), and `tests/support/shipped_config.py` one (a docstring noting which credential is
reachable from a throwaway repository's working directory via `Settings`).

Per naming_discipline rule 2, write the replacement prose naming only the new spelling. These
are the stale-docstring sites the task brief singled out as the difference between a careful
rename and a partial one, so after this task Gate A should reduce to exactly the three
allowlisted files in F7 — run it and confirm the residual set matches, rather than assuming it.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; uv run ruff check . &amp;&amp; uv run mypy --strict src/ &amp;&amp; diff <(grep -rniE '(^|[^_a-z])github_token' --include='*.py' src/ tests/ | grep -vi 'redacted:github_token' | cut -d: -f1 | sort -u) <(printf 'src/dark_factory/events/redaction.py\ntests/integration/test_phase6_acceptance.py\ntests/unit/test_redaction.py\n')</automated>
  </verify>
  <done>
Gate A's residual set is exactly the three allowlisted files from F7 — no more, and no fewer
(a shorter list would mean the retained D-15 vocabulary entry or a frozen phase quotation was
wrongly edited). `mypy --strict` and `ruff check` clean.
  </done>
</task>

<task type="auto">
  <name>Task 5: Rename the credential in documentation, .env.example, and the scaffold templates — the live-bug fix</name>
  <files>scripts/scaffold_target_repo.py, README.md, docs/CONFIGURATION.md, docs/GETTING-STARTED.md, .env.example, .gitignore</files>
  <read_first>scripts/scaffold_target_repo.py (the env-file template and both workflow templates), README.md (the resume-workflow-reference sentinel block and the permissions-block prose preceding it)</read_first>
  <action>
This is the task that actually fixes the reported 403.

`scripts/scaffold_target_repo.py`: in the generated env-file template, rename the credential
assignment and update the comment above it to say why the name is distinguished. In both
generated workflow templates (the resume workflow and the run workflow), change the `env:` key
AND the `${{ secrets.* }}` expression it reads from — both halves, in both templates. Changing
only the key would leave the job still reading the reserved secret; changing only the
expression would leave dark-factory reading an unset variable. The new secret name is one a
user can actually create, which the old one was not.

`README.md`: the sentinel-delimited reference workflow must stay byte-compatible with the
scaffold's resume template — `tests/unit/test_resume_workflow_reference_doc.py` guards that
pairing, so update both in the same task. Then correct the surrounding prose, which is now
factually wrong in a load-bearing way: the permissions-block explanation currently states that
the job hands the reserved Actions auto-token to dark-factory as its own credential, and
justifies the issue-write permission by that token's scoping. With a user-supplied
fine-grained or classic PAT, authority comes from the token's own scopes, not from the job's
permissions block. Rewrite that bullet to describe the credential the job now passes and where
its authority comes from, and keep the permissions block's remaining, still-correct rationale
(the checkout credential's push scope, and publication after QA and quality-gate PASS). Also
update the secrets-this-job-needs sentence and the configuration-reference entry.

`docs/CONFIGURATION.md` and `docs/GETTING-STARTED.md`: rename the credential's row in each
environment-variable table and every prose mention of it, including the lists enumerating
which variables a CI environment needs. In `GETTING-STARTED.md`, the worker-credential row
contrasts the copilot credential against dark-factory's own by name — update the contrast
while leaving the copilot credential itself unchanged (F8).

Add a short, durable explanation of the collision in one place — `docs/CONFIGURATION.md`'s
entry for this credential is the natural home, with README's configuration reference pointing
at it. State the mechanism, not just the conclusion: the reserved name cannot be created as a
repository secret, Actions auto-injects an installation token under it, and that installation
token cannot call `GET /user` as a matter of platform rule rather than permission scoping.
Naming the reserved spelling IS appropriate here — this is the one place where the old name
earns a mention, and Gate A does not scan these files (naming_discipline rule 2).

`.env.example`: rename the assignment and replace its comment, which is doubly stale — it
claims the credential is unused and cites a phase that has long shipped.
`.gitignore`: reword the comment naming which credentials the ignored environment file keeps
out of git.

Do not touch anything under `app-int` — a separate repository, out of scope, to be updated by
a human once this lands (its workflow currently passes a dispatch secret through under the old
variable name, so it will break until that human edit happens; call this out in the summary).
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; test "$(grep -rcE 'GITHUB_TOKEN:[[:space:]]*\$\{\{[[:space:]]*secrets\.GITHUB_TOKEN' README.md scripts/scaffold_target_repo.py | grep -vc ':0$')" = "0" &amp;&amp; test "$(grep -cE 'DARK_FACTORY_GITHUB_TOKEN:[[:space:]]*\$\{\{[[:space:]]*secrets\.DARK_FACTORY_GITHUB_TOKEN[[:space:]]*\}\}' scripts/scaffold_target_repo.py)" = "2" &amp;&amp; uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q &amp;&amp; uv run ruff check .</automated>
  </verify>
  <done>
Zero occurrences anywhere in `README.md` or the scaffold of a workflow `env:` key assigned from
the reserved secret expression. Both generated workflow templates declare the renamed key
reading the renamed secret. The README sentinel block still parses and still matches the
scaffold template — `test_resume_workflow_reference_doc.py` passes. Both documentation tables
name the renamed variable, `docs/CONFIGURATION.md` explains the collision mechanism including
the `GET /user` platform rule, and `.env.example` / `.gitignore` are current. The copilot
worker credential is unchanged. No file outside this repository was modified.
  </done>
</task>

</tasks>

<verification>
Run after all five tasks:

1. `uv run mypy --strict src/` — clean.
2. `uv run ruff check .` and `uv run ruff format --check .` — clean.
3. `uv run pytest -m "unit or contract" -q` — green.
4. Gate A (residual field-name allowlist), the Task 4 command: the residual file set is
   exactly the three files in F7.
5. Gate B (reserved-token passthrough), the Task 5 command: zero hits.
6. `uv run pytest --collect-only -q -m "db or integration"` — no collection errors.
7. Negative control for the rename's whole point: confirm `Settings` built from an environment
   providing only the OLD variable name leaves the credential unset, and one providing the new
   name populates it. This is the behavior change the task exists to produce; assert it
   directly rather than inferring it from a green suite.

Deferred to `/gsd-verify-work` (needs real PostgreSQL, historically ~1h for the db tier):
full db- and integration-tier execution, in particular the SC5 secret-sweep proofs touched by
Task 2.
</verification>

<success_criteria>
- `Settings` exposes the credential as `dark_factory_github_token` bound to
  `DARK_FACTORY_GITHUB_TOKEN`, with no alias and no attribute under the old name.
- `_SENSITIVE_KEYS` carries BOTH spellings; a `dark_factory_github_token` dict key and a
  `dark_factory_github_token=<value>` pair are both redacted, and old-spelling third-party
  text is still redacted.
- Every known-value label assertion names the new label; every shape-pattern label assertion
  is unchanged (F4).
- Both scaffolded workflow templates and the README sentinel block pass the renamed secret;
  no template reads the reserved secret expression.
- `docs/CONFIGURATION.md` records why the name is distinguished, including the `GET /user`
  platform rule.
- Gate A residual set equals the three-file F7 allowlist.
- `mypy --strict` / `ruff check` / `ruff format --check` clean; unit and contract tiers green.
- `copilot_github_token` / `COPILOT_GITHUB_TOKEN` untouched; nothing outside this repository
  modified; no webhook-subsystem code resurrected.
</success_criteria>

<output>
Create `.planning/quick/261031-lhn-rename-dark-factory-s-own-github-api-tok/261031-lhn-SUMMARY.md` when done.

Record in the summary:
- The F2 finding and its resolution (the `_SENSITIVE_KEYS` add-not-replace), since it is a
  security regression this rename would otherwise have introduced silently.
- The F4 label-provenance rule, as the reason the rename was not a find-and-replace.
- The deferred full db/integration-tier verification.
- That `app-int` still passes the old variable name and will break until a human updates its
  workflow files and repository secret.
- That `.claude/CLAUDE.md` and `.planning/PROJECT.md` still carry the old spelling by design
  (F9), pending their next regeneration.
</output>
