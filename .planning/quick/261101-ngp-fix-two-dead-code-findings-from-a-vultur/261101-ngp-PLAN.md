---
phase: quick
plan: 261101-ngp
type: execute
wave: 1
depends_on: []
files_modified:
  - src/dark_factory/git/__init__.py
  - src/dark_factory/github/client.py
autonomous: true
requirements: [QUICK-NGP]

estimate:
  tokens: 18000
  raw_tokens: 18000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "`uv run ruff check --select F401 src/ tests/` reports zero errors. Today it reports exactly one: `pathlib.Path` imported but unused at `src/dark_factory/git/__init__.py:58`. This is the whole-tree F401 count, so the gate also proves the cleanup introduced no new unused import anywhere."
    - "`GitHubClient.__init__` no longer copies its `token` or `timeout` parameters onto private instance attributes. After this change the project's own GitHub credential is reachable from a live `GitHubClient` in exactly two places it already had to be -- as a value inside the `_known_secrets` redaction map, and inside the `githubkit` client held on `_client` -- and NOT as a third, independently-named long-lived attribute that `vars(client)`, an accidental `repr`, or a debugger frame would surface. That is the security-hygiene half of the finding: the attribute was dead code *and* a redundant credential copy."
    - "`timeout` still reaches the `githubkit` constructor unchanged, as `float(timeout)`. The removal targets the stored copies only -- what the SDK client is built with is identical before and after, which is why no behavioral test needs to change."
    - "Every one of the 40 names `dark_factory.git.__all__` declares still resolves after the import line is deleted. `Path` is not among them and nothing in the repository imports `Path` from `dark_factory.git`, so the removal is not a silent re-export break."
    - "`tests/unit/test_github_client.py` (11 tests) passes with the test file unedited, and so do `tests/unit/test_load_github.py` and `tests/unit/test_redaction_dark_factory_github_token.py`. If a test had to change, the vulture finding was a false positive and the task's own instruction applies: investigate, do not adjust the test to fit."
    - "`uv run mypy --strict src/`, `uv run ruff check .` and `uv run ruff format --check src/` are clean, and `uv run pytest -q -m \"unit or contract\"` is green. The format gate is scoped to `src/` deliberately: `uv run ruff format --check .` fails on 13 pre-existing files today, every one of them under `tests/` (see Pre-existing Conditions). `src/` is fully format-clean (76 files) and this plan touches only `src/`, so a `src/`-scoped gate is both attributable to this change and unweakened."
  artifacts:
    - "src/dark_factory/git/__init__.py -- one import line (line 58) removed; the surrounding module docstring, the 40-entry `__all__` and all six re-export blocks untouched"
    - "src/dark_factory/github/client.py -- two constructor assignment lines (131-132) removed; the constructor signature, the `_known_secrets` default, the `GitHub(...)` construction and `_authenticated_login` untouched"
  key_links:
    - "`GitHubClient.__init__`'s local `token` parameter <-> the `_known_secrets` default map (line 136) and the `GitHub(token, timeout=float(timeout))` construction (line 138). Both are reads of the *parameter*, not of a stored attribute, which is exactly why the stored attributes are dead. This is the one way to break the change: sweeping the `token`/`timeout` names out of the constructor along with the two dead assignments would silently stop the project's own GitHub token from being registered for redaction, so every error message this module raises would stop scrubbing it -- a security regression dressed as a cleanup. A positive grep gate pins the construction line; the test selection pins the redaction behavior."
    - "`dark_factory.git.__init__`'s `WorktreePathError` name (in `__all__` at line 75 and the `errors` import at line 136) <-> the `Path` token being removed at line 58. Four lines in that file contain the substring `Path`; only line 58 is the unused import. A name-based find-and-replace or an over-eager editor would take out the package's error surface. Delete the single import line, nothing else."
---

<objective>
A vulture/ruff dead-code scan surfaced two findings in `src/dark_factory/`, both
confirmed genuine during planning:

1. `src/dark_factory/git/__init__.py:58` imports `pathlib.Path` and never uses it.
   The package's `[tool.ruff.lint] select` is `["I", "UP", "B", "SIM", "RUF"]`,
   which *overrides* ruff's default `F` rule set -- that is why the routine
   `uv run ruff check .` gate has never flagged it and why the finding needed an
   explicit `--select F401` run to surface. It is the only F401 offender in the
   whole tree.

2. `src/dark_factory/github/client.py:131-132` copies the constructor's `token`
   and `timeout` parameters onto private instance attributes that nothing ever
   reads. The `githubkit` client is built from the local parameters directly
   (line 138), and the redaction map from the local `token` (line 136).

Finding 2 is not purely cosmetic. One of the two dead attributes holds the raw,
unwrapped value of `Settings.dark_factory_github_token` -- the credential this
module's own docstring promises is unwrapped "at the single construction frame"
and "never placed in an exception message, log field or event payload." Keeping
a second, independently-named long-lived copy of it on the instance widens where
that credential can leak by inspection (`vars(client)`, an accidental `repr`, a
debugger frame, a crash dump) for zero functional benefit. Removing it narrows
the in-process credential surface, so the commit rationale must say so rather
than describing a generic dead-code sweep.

Purpose: close both findings with no behavior change, and make the cleanup
self-proving -- the F401 gate is whole-tree, and a grep gate pins the lines that
must *survive* so the removal cannot quietly take the credential-redaction
wiring with it.

Output: two atomic commits, two files touched, zero test files edited.
</objective>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@src/dark_factory/git/__init__.py
@src/dark_factory/github/client.py
</context>

<planning_evidence>
Both findings were verified against the working tree during planning. Record of
what was checked, so execution confirms rather than re-derives:

- `uv run ruff check --select F401 src/ tests/` -> **1 error**, the `Path` import
  at `src/dark_factory/git/__init__.py:58`. No other F401 offender in `src/` or
  `tests/`.
- `grep -rn "from dark_factory.git import" src/ tests/ scripts/` -> the only
  `Path`-containing hits are `WorktreePathError`. Nothing imports `Path` from
  `dark_factory.git`; `Path` is not in that package's `__all__` (40 entries, all
  resolve).
- `grep -rn "_token\b" src/dark_factory/github/` -> line 131 is the only
  assignment; every other hit is the `dark_factory_github_token` settings field
  name. `grep -rn "_timeout\b" src/dark_factory/` -> line 132 is the *only* hit
  in the entire package.
- `grep -rn "_token\b|_timeout\b" tests/` -> zero reads of a `GitHubClient`
  attribute. The hits are unrelated: lease `owner_token` locals in
  `tests/db/test_lease_*.py`, worker-credential settings tests, and
  `bad_timeout` parametrize ids in `tests/unit/test_settings.py`.
- `tests/unit/test_github_client.py:230-231` sets `self.token` / `self.timeout`
  on its own **stub `githubkit` `GitHub` class** (the thing patched over
  `dark_factory.github.client.GitHub`), not on `GitHubClient`. Those are
  reachable only via `_client` and are unaffected.
- No AST/source guard inspects `GitHubClient`'s attributes.
  `tests/unit/test_github_ownership_boundary.py` guards *`githubkit` imports*,
  not instance state.
- Baseline: the six-module unit selection used below is green today --
  `62 passed in 4.29s`.

Deliberately out of scope: adding a permanent regression guard forbidding the
credential attribute from coming back. This repository has a strong culture of
such guards, and one would be defensible here, but it is a new test asset the
task did not ask for. The grep gate in Task 2 is a one-time proof, not a
standing invariant.

## Pre-existing Conditions (do NOT fix in this plan)

`uv run ruff format --check .` **fails today, before any edit**, reporting
"13 files would be reformatted." Measured at planning time with ruff 0.16.6:

- All 13 are under `tests/` (`uv run ruff format --check tests/` -> 13).
- `src/` is completely clean (`76 files already formatted`), including both
  files this plan touches.
- The drift is formatter-version disagreement over line joining in existing test
  code (e.g. `tests/db/test_ask_posts_comment.py:295` -- the installed ruff wants
  a `raise AssertionError(...)` call collapsed onto one line), not a syntax or
  correctness problem.

Consequences for execution, both mandatory:

1. Every format gate in this plan is scoped to `src/`, never `.`. A whole-tree
   format gate would fail for reasons this change did not cause, which makes it
   worthless as a signal.
2. Do **not** run `uv run ruff format .` or otherwise reformat those 13 test
   files. That would be 13 unrelated files in the diff, it would contradict the
   "zero test files edited" acceptance criterion, and it is a separate task.
   Scope the formatter to the file being edited:
   `uv run ruff format src/dark_factory/git/__init__.py`.

`uv run ruff check .` *is* clean today and stays a whole-tree gate.
</planning_evidence>

<tasks>

<task type="tracer">
  <name>Task 1: Remove the unused pathlib.Path import from the git package</name>
  <files>src/dark_factory/git/__init__.py</files>
  <action>
Delete line 58, the `from pathlib import Path` statement. That single-line
deletion is the entire change -- adjust no whitespace.

Deleting it leaves two consecutive blank lines between
`from __future__ import annotations` and the `__all__` assignment, which is what
ruff-format wants between top-level blocks anyway. This was verified at planning
time by piping the line-58-deleted content through
`uv run ruff format --check --stdin-filename src/dark_factory/git/__init__.py -`:
format-clean, no fixup required. So do not "tidy" the blank lines, and in
particular do not run `uv run ruff format .` -- that would rewrite 13 unrelated,
already-drifted test files (see Pre-existing Conditions). If you want the
formatter's opinion, scope it to the one file:
`uv run ruff format src/dark_factory/git/__init__.py`.

Change nothing else in this file. Three other lines contain the substring
`Path` and all three must survive untouched: the module docstring's
`Path.cwd()` mention (line 8), the `"WorktreePathError"` entry in `__all__`
(line 75), and the `WorktreePathError` name in the `dark_factory.git.errors`
import block (line 136). Do not run a find-and-replace on `Path`.

`Path` is not in `__all__` and nothing in the repository imports it from this
package, so this is a true dead-import removal and not a re-export break -- the
verify command proves the latter by resolving all 40 declared names.

Commit this on its own: `refactor(261101-ngp): drop unused pathlib.Path import
from the git package`. In the body, note that the project's `select` list omits
ruff's `F` rules, which is why a routine `ruff check .` never surfaced it and an
explicit `--select F401` run did.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; uv run ruff check --select F401 src/ tests/ &amp;&amp; uv run ruff format --check src/ &amp;&amp; uv run python -c "import dark_factory.git as g; [getattr(g, n) for n in g.__all__]; assert len(g.__all__) == 40, len(g.__all__); assert not hasattr(g, 'Path'); print('all 40 __all__ names resolve, Path is gone')" &amp;&amp; uv run pytest -q tests/unit/test_git_worktree.py tests/unit/test_git_ownership_boundary.py tests/unit/test_git_lifecycle.py</automated>
  </verify>
  <done>
`uv run ruff check --select F401 src/ tests/` reports zero errors across the
whole tree (was exactly 1). Importing `dark_factory.git` resolves all 40 names
in `__all__` and `Path` is no longer an attribute of the package -- the latter
assertion is non-vacuous: it evaluates True before the edit and must be False
after. The three git unit modules pass. `uv run ruff format --check src/` is
clean (76 files). One commit, one file, one line of production code removed, and
no file under `tests/` touched.
  </done>
</task>

<task type="auto">
  <name>Task 2: Stop retaining the GitHub token and timeout as dead instance attributes</name>
  <files>src/dark_factory/github/client.py</files>
  <precondition>Nothing in the tree reads either attribute: `grep -rnE '\._(token|timeout)\b' src/ tests/ scripts/` must return no hit that is an attribute access on a `GitHubClient` instance (planning saw zero; the only `src/` hits are the two assignment lines themselves). If a genuine reader exists, HALT and report -- the scan finding would be a false positive and the attribute is load-bearing, which is a different task than this one.</precondition>
  <action>
First re-run the precondition grep above and read its output. Expect the only
`src/` hits to be the two constructor assignment lines in this file, and no
`tests/` hit to be an attribute access on a `GitHubClient`. Note in the SUMMARY
that the check was re-run at execution time and what it returned. If it turns up
a real reader, stop and report instead of editing.

Then delete the two constructor statements in `GitHubClient.__init__` (currently
lines 131-132) that copy the `token` and `timeout` parameters onto the
underscore-prefixed `_token` and `_timeout` instance attributes. Delete exactly
those two statement lines.

Four things in the same constructor must survive byte-identical, because each is
a read of the *parameters* (which is precisely why the stored copies are dead):

- the signature `(*, token: str, timeout: int = 30, known_secrets: dict[str, str] | None = None)`
- the `_known_secrets` assignment and its `{token: "dark_factory_github_token"}`
  fallback -- this is what registers the project's own credential for redaction;
  losing it would stop every error message this module raises from scrubbing the
  token
- `self._client = GitHub(token, timeout=float(timeout))` -- the real consumer of
  both parameters
- the `_authenticated_login` initialization and its explanatory comment

Add no replacement comment at the deletion site and add no new test. There is no
behavioral delta to drive from a test, which is why this task carries no
`<behavior>` block: the proof is the unchanged existing suite plus the static
gates below (one negative, one positive).

Commit separately from Task 1: `refactor(261101-ngp): stop retaining the GitHub
token as an instance attribute`. The body must carry the security rationale, not
just the dead-code one -- one of the two removed attributes held the raw,
unwrapped value of `Settings.dark_factory_github_token` for the lifetime of the
client while nothing ever read it, so removing it narrows where that credential
can leak by inspection (`vars()`, an accidental `repr`, a debugger frame, a crash
dump). Say that the credential now lives only in the frames that genuinely need
it: the constructor-local parameter, the redaction map value, and the `githubkit`
client itself.
  </action>
  <verify>
    <automated>cd /Users/maryiakrauchanka/portfolio/dark-factory &amp;&amp; test "$(grep -v '^[[:space:]]*#' src/dark_factory/github/client.py | grep -cE '^[[:space:]]+self\._(token|timeout)[[:space:]]*=')" = "0" &amp;&amp; test "$(grep -cE 'GitHub\(token, timeout=float\(timeout\)\)' src/dark_factory/github/client.py)" = "1" &amp;&amp; test "$(grep -cE '\{token: "dark_factory_github_token"\}' src/dark_factory/github/client.py)" = "1" &amp;&amp; uv run pytest -q tests/unit/test_github_client.py tests/unit/test_load_github.py tests/unit/test_redaction_dark_factory_github_token.py tests/unit/test_github_ownership_boundary.py &amp;&amp; uv run mypy --strict src/ &amp;&amp; uv run ruff check . &amp;&amp; uv run ruff format --check src/</automated>
  </verify>
  <done>
The two dead constructor assignments are gone (negative grep, comment-filtered,
counts 0 -- was 2). The `githubkit` construction line and the redaction-map
fallback both still appear exactly once (positive greps, each 1), so the
parameters still reach the SDK and the project's own token is still registered
for redaction. All four github unit modules pass with zero test-file edits.
`mypy --strict src/`, `ruff check .` and `ruff format --check src/` are clean.
One commit whose body names the credential-surface narrowing, not only the dead
code.
  </done>
  <reversibility rating="reversible">Two deleted statement lines, recoverable from git history in one revert; no persisted state, schema or external side effect involved.</reversibility>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Settings -> `GitHubClient` | The one frame where `Settings.dark_factory_github_token` is unwrapped from `SecretStr` into a plain `str` (D-03). Everything downstream of this point handles a live credential. |
| `GitHubClient` -> in-process inspection | Anything that can read the instance's `__dict__`: a `repr`, `vars()`, a debugger frame, a crash dump, a traceback-rendering library that prints locals. Not a network boundary, but the leak surface this task shrinks. |
| `GitHubClient` -> raised exceptions / logs | Every error message this module emits passes through `redact()` before it is raised; the `_known_secrets` map built in the constructor is what makes that scrub the project's own token. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-NGP-01 | Information Disclosure | the dead credential attribute on `GitHubClient` | low | mitigate | Task 2 deletes it, so the raw token is no longer held as a separately-named long-lived instance attribute. After the change the credential exists only in frames that read it: the constructor-local parameter, the redaction-map value, and the `githubkit` client on `_client`. Proven by the comment-filtered negative grep counting 0. |
| T-NGP-02 | Tampering | this cleanup's own blast radius inside `__init__` | medium | mitigate | A cleanup that over-deletes could remove `{token: "dark_factory_github_token"}` and silently disable redaction of the project's own token in every error this module raises -- a security regression wearing a refactor's clothes. Two positive grep gates pin that line and the `GitHub(token, timeout=float(timeout))` construction at exactly one occurrence each, and `tests/unit/test_redaction_dark_factory_github_token.py` is in the selection. |
| T-NGP-03 | Information Disclosure | `GitHub`/SDK timeout wiring | low | accept | The `timeout` parameter still reaches the SDK unchanged; only the unread copy is removed. No denial-of-service or hang surface changes. Accepted because the positive grep on the construction line already makes a regression here impossible to land silently. |
| T-NGP-04 | Tampering | `dark_factory.git` public surface | low | mitigate | Deleting a line from a package `__init__` could break a re-export. `Path` is absent from `__all__` and unimported anywhere in the repo (verified at planning); Task 1's verify resolves all 40 declared names and asserts `Path` is gone. |

No package-manager install (`uv add` / `pip` / `npm` / `cargo`) occurs in this
plan -- no dependency is added, removed or version-changed -- so no supply-chain
(`T-*-SC`) row and no package-legitimacy checkpoint applies.
</threat_model>

<verification>
Run from `/Users/maryiakrauchanka/portfolio/dark-factory`:

1. `uv run ruff check --select F401 src/ tests/` -> zero errors (was exactly 1).
2. `uv run ruff check .` -> clean (whole tree; clean today too).
   `uv run ruff format --check src/` -> clean, 76 files. Scoped to `src/` because
   the whole-tree form has 13 pre-existing failures under `tests/` that this
   change neither causes nor should fix (see Pre-existing Conditions).
3. `uv run mypy --strict src/` -> clean.
4. `uv run pytest -q -m "unit or contract"` -> green, with zero test files edited
   by this plan: `git diff --stat $(git rev-parse HEAD~2) -- tests/` is empty and
   the full diff touches exactly `src/dark_factory/git/__init__.py` and
   `src/dark_factory/github/client.py`.
5. Negative gate: the comment-filtered count of constructor assignments onto the
   underscore-prefixed token/timeout attributes in
   `src/dark_factory/github/client.py` is 0.
6. Positive gates: `GitHub(token, timeout=float(timeout))` and
   `{token: "dark_factory_github_token"}` each still appear exactly once in
   `src/dark_factory/github/client.py`.
7. `git log --oneline -2` -> two commits, one per task, the second naming the
   credential-surface rationale in its body.

The `db` and `integration` tiers are not run: neither touches the removed
attributes, both require the remote Neon instance, and STATE.md records multi-hour
runtimes for them. `mypy --strict src/` plus the whole-tree `ruff check .` cover
the static risk, and the attributes have no reader anywhere in `tests/`.
</verification>

<success_criteria>
- [ ] `src/dark_factory/git/__init__.py` no longer imports `pathlib.Path`; its
      docstring, 40-entry `__all__` and six re-export blocks are otherwise
      unchanged.
- [ ] `uv run ruff check --select F401 src/ tests/` reports zero errors.
- [ ] `import dark_factory.git` resolves all 40 names in `__all__`; `Path` is not
      an attribute of the package.
- [ ] `GitHubClient.__init__` contains no assignment copying `token` or `timeout`
      onto an instance attribute (comment-filtered grep count 0, was 2).
- [ ] `GitHub(token, timeout=float(timeout))` and the
      `{token: "dark_factory_github_token"}` redaction fallback each still appear
      exactly once in `src/dark_factory/github/client.py`.
- [ ] `uv run pytest -q -m "unit or contract"` is green and no file under
      `tests/` is modified by this plan -- including the 13 test files the
      installed ruff would like to reformat, which stay untouched.
- [ ] `uv run mypy --strict src/`, `uv run ruff check .` and
      `uv run ruff format --check src/` are clean.
- [ ] Two atomic commits; the second commit body states that one removed
      attribute held the raw GitHub credential and that removing it narrows the
      in-process credential surface -- not merely that dead code was deleted.
- [ ] The Task 2 precondition grep was re-run at execution time and its result
      recorded in the SUMMARY.
</success_criteria>

<output>
Create `.planning/quick/261101-ngp-fix-two-dead-code-findings-from-a-vultur/261101-ngp-SUMMARY.md` when done.
</output>
