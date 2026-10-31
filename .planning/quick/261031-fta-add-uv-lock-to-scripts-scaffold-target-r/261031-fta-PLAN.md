---
phase: quick
plan: 261031-fta
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/scaffold_target_repo.py
  - tests/unit/test_scaffold_target_repo.py
autonomous: true
requirements: [QUICK-FTA]

estimate:
  tokens: 22000
  raw_tokens: 22000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "A target repository scaffolded by `scripts/scaffold_target_repo.py` ignores `uv.lock`, so the lockfile that `uv` regenerates on every `uv run` invocation is invisible to `git ls-files --others --exclude-standard` and therefore never reaches `attempt_changed_paths()`. The live failure this closes, confirmed against a real `app-int` CI run: a role whose `write_scope` does not cover the repository root (QA's is `['tests/**']`) failed with `wrote outside its configured write_scope ... ['uv.lock']` -- even though that role's own agent explicitly deleted the file before finishing, because the WIP commit snapshot had already captured it as present."
    - "The added entry is the bare exact line `uv.lock` -- not `*.lock`, not `/uv.lock` -- so it matches at any depth (a target repo with nested packages regenerates one per `uv run` working directory) without over-ignoring a deployer's unrelated lockfiles"
    - "The entry reaches the file that is actually written, not just the module constant: `build_contents()[GITIGNORE_RELATIVE_PATH]` carries it, and a real `scripts/scaffold_target_repo.py --target <tmp> --yes` invocation writes a `.gitignore` that reads back from disk with the entry present"
    - "All eight pre-existing template entries survive byte-identical -- `.dark-factory/runs/` in particular, which the entire Phase 4 artifact-tree force-add mechanism depends on"
    - "No comment line is introduced into `GITIGNORE_CONTENT`: `_gitignore_missing_entries()` filters only *empty* lines, so any prose line would be printed to a deployer who already has a `.gitignore` under `NOTE: existing .gitignore is missing these template entries:`, where it would read as a path to ignore. The reasoning lives in the new test docstrings instead -- the house convention every sibling guard in `tests/unit/` already follows."
    - "Two committed unit tests pin the entry: one on the constant, one on the `build_contents` wiring -- so a future refactor that renders `.gitignore` from somewhere else still has to carry it, and a regrouping of the template's lines does not fail a test for a non-behavioral reason (membership is asserted, never index)"
    - "`src/dark_factory/git/scope.py` sees zero diff. `attempt_changed_paths()`'s `git ls-files --others --exclude-standard` already honors `.gitignore` -- confirmed by reading the source -- so the enforcement code is correct and this is purely a content gap in the generated config. Nothing from `261031-cp4`'s uv-install-step work is reopened: the `Install uv` step and its three tests stay byte-identical and the module's five existing tests still pass."
  artifacts:
    - "scripts/scaffold_target_repo.py -- one line added to `GITIGNORE_CONTENT` (currently eight entries, lines 374-383)"
    - "tests/unit/test_scaffold_target_repo.py -- two new tests plus one shared entry-parsing helper, extending the module `261031-cp4` created"
  key_links:
    - "`DEFAULT_QUALITY_GATE_COMMANDS` (`uv run pytest -q` / `uv run ruff check .`) -> the generated `.dark-factory.yaml`'s `quality_gate.commands` -> `run_quality_gate`'s subprocess -> `uv run` regenerates `uv.lock` in the worktree root -> `git ls-files --others --exclude-standard` in `git/scope.py`'s `attempt_changed_paths()` reports it as a changed path -> `enforce_write_scope()` raises for any role whose `write_scope` excludes the repository root. Every link in that chain is behaving as designed. The only one that was wrong is the one deciding whether git reports the file at all: the generated `.gitignore`."
    - "QA's `write_scope: ['tests/**']` (`ROLE_WRITE_SCOPE`, same script) <-> the generated `.gitignore`: one script renders both, and the two must agree about which repository-root paths a role is allowed to leave behind. This plan makes them agree about `uv.lock`."
    - "`GITIGNORE_CONTENT` (constant) <-> `build_contents()[GITIGNORE_RELATIVE_PATH]` (line 563) <-> `write_output_file` / `_gitignore_missing_entries`: the same constant is both the file written into a fresh repository and the checklist printed to a deployer who already has one. Task 1's two tests cover the first two hops; Task 2's smoke covers the third."
---

<objective>
`scripts/scaffold_target_repo.py` generates a `.gitignore` for a target repository from a
flat eight-entry `GITIGNORE_CONTENT` template (lines 374-383). It does not list `uv.lock`.

The same script's `DEFAULT_QUALITY_GATE_COMMANDS` is `("uv run pytest -q", "uv run ruff
check .")`, written verbatim into the generated `.dark-factory.yaml`. Every `uv run`
invocation -- the Quality Gate's two commands, plus QA's own test runs inside the role --
regenerates `uv.lock` in the worktree root.

Confirmed live against a real `app-int` CI run, not inferred: because the generated
`.gitignore` does not list it, that regenerated file is **untracked but not ignored**. So
`git/scope.py`'s `attempt_changed_paths()`, which runs
`git ls-files --others --exclude-standard`, reports it as a changed path, and
`enforce_write_scope()` fails any role whose `write_scope` does not cover the repository
root:

    wrote outside its configured write_scope ... ['uv.lock']

QA's `write_scope` is `['tests/**']`, so QA takes this every time. It fails even when the
role's own agent explicitly deleted `uv.lock` before finishing, because the WIP commit
snapshot had already captured it as present.

**This is not a bug in the enforcement code.** `attempt_changed_paths()`'s
`--exclude-standard` flag already honors `.gitignore` -- confirmed by reading the source.
The defect is entirely a content gap in the `.gitignore` the scaffold generates.

**The fix:** add a `uv.lock` line to `GITIGNORE_CONTENT`, and extend the test module
`261031-cp4` created with assertions that the generated `.gitignore` carries it.

Three decisions this plan locks:

**1. The entry is a bare `uv.lock` line with no explanatory comment.**
`_gitignore_missing_entries()` (lines 589-600) filters only *empty* lines -- every non-empty
template line, comment included, is printed to a deployer who already has a `.gitignore`
under `NOTE: existing .gitignore is missing these template entries:`. A prose line there
reads as a path to ignore. The two workflow templates take comments freely because they are
deployer-facing YAML with no such line-by-line consumer; this template has one. The "why"
goes in the new test docstrings instead, which is already how every sibling guard in
`tests/unit/` carries its live-failure narrative.

**2. The pattern is `uv.lock`, not `*.lock` and not `/uv.lock`.** A bare filename matches at
any depth, which is what is wanted: a target repository with nested packages regenerates one
per `uv run` working directory. `*.lock` would over-ignore a deployer's unrelated lockfiles;
`/uv.lock` would under-ignore a nested one.

**3. Position is not asserted.** The line goes immediately after `.venv/` (both are
uv-managed local byproducts; grouping keeps the flat list readable), but the tests assert
*membership*, never index. Git pattern order only matters for negation patterns, of which
this template has none. This is the deliberate opposite of `261031-cp4`, where step
*ordering* was the entire behavior under test -- here an index assertion would fail a future
regrouping for no behavioral reason.

**Deliberately out of scope:** `src/dark_factory/git/scope.py` and everything under `src/`
(the enforcement code is correct). The `app-int` repository (a separate repo, already fixed
directly there). Everything `261031-cp4` touched -- its `Install uv` step and three tests
stay byte-identical. Also noted so a reviewer does not go looking: unlike the
`261030-mcz` -> `261030-mng` permissions split and the still-open README uv-install gap,
there is **no second copy** of this template to chase. A grep of `README.md` and `docs/` for
the template's own entries returns zero hits; README names `.gitignore` only as a generated
filename.

Purpose: a run whose four roles all did honest work must not fail write-scope enforcement on
a lockfile the scaffold's own default gate commands regenerate.
Output: one template line, two new unit tests.
</objective>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@scripts/scaffold_target_repo.py
@tests/unit/test_scaffold_target_repo.py
</context>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Ignore uv.lock in the generated .gitignore, proven through the constant and the build_contents wiring</name>
  <files>tests/unit/test_scaffold_target_repo.py, scripts/scaffold_target_repo.py</files>
  <read_first>
- `scripts/scaffold_target_repo.py` lines 374-383 (`GITIGNORE_CONTENT` in full -- the eight
  current entries), 526-564 (`build_contents`, whose last statement at line 563 assigns
  `GITIGNORE_CONTENT` to the `GITIGNORE_RELATIVE_PATH` key), 589-600
  (`_gitignore_missing_entries` -- the function whose line filter is the reason decision 1
  forbids a comment), 39-65 (`ROLE_ORDER`, `DEFAULT_QUALITY_GATE_COMMANDS`,
  `DEFAULT_INSTALL_SOURCE`, `DEFAULT_BASE_BRANCH`, `GITIGNORE_RELATIVE_PATH`)
- `tests/unit/test_scaffold_target_repo.py` in full (170 lines) -- the module `261031-cp4`
  created. Reuse its established shape: the `from scripts.scaffold_target_repo import ...`
  import, `pytestmark = pytest.mark.unit`, `_REPO_ROOT`, the `_ROLE_WORKERS` fixture dict
  built over `ROLE_ORDER`, module-scope naming of every load-bearing literal, and docstrings
  that open with the task id and the live failure.
  </read_first>
  <behavior>
This task is the vertical slice: it touches the template constant, the `build_contents`
wiring that turns that constant into a written file's content, and the test that proves both
-- and its verification is an end-to-end check of the generated `.gitignore` content, not a
per-layer assertion.

Write the two tests FIRST and watch them fail for the right reason (the entry is absent from
the parsed entry set), then add the template line and watch them pass.

- Test 1 (`GITIGNORE_CONTENT` directly): the parsed entry set of the template contains the
  exact entry `uv.lock`. Exact-line membership, so a `*.lock` or `nested/uv.lock` variant
  does not satisfy it.
- Test 2 (`build_contents` wiring): a `build_contents(...)` call with this repository's own
  defaults returns a mapping whose `GITIGNORE_RELATIVE_PATH` value's parsed entry set
  contains the same exact entry -- proving the constant actually reaches the emitted file,
  so a refactor that renders `.gitignore` from somewhere else still has to carry it.
- Both tests reuse one shared helper, so there is a single definition of what counts as an
  entry.
- The module's five pre-existing tests continue to pass untouched.
  </behavior>
  <action>
**(a) Extend `tests/unit/test_scaffold_target_repo.py`.** Do not create a new module and do
not modify any of the three existing tests.

Widen the existing `from scripts.scaffold_target_repo import (...)` block with the four
names the new tests need: `DEFAULT_BASE_BRANCH`, `GITIGNORE_CONTENT`,
`GITIGNORE_RELATIVE_PATH`, `build_contents`. Keep the import list alphabetically sorted --
ruff's `I` rule set is enabled and will otherwise rewrite it.

Add one module-scope literal naming the entry under test, alongside the module's existing
`_SETUP_UV_PINNED_REF_PATTERN` / `_INSTALL_DARK_FACTORY_STEP_NAME` block, following that
module's convention of naming every load-bearing literal once.

Add one private helper beside the existing `_job_steps` that takes `.gitignore` text and
returns the set of its entries: strip each line, drop empty lines, drop lines beginning with
a hash. The hash filter is for *robustness of the helper*, not because the template has any
such line -- decision 1 in the plan objective forbids one. Give the helper a docstring
saying so, and saying that membership in this set is git-pattern semantics (a bare filename
matches at any depth), which is why exact membership and not a substring search is the right
assertion.

Then write the two tests from `<behavior>`, each with a docstring opening `261031-fta:` in
the module's established voice and carrying the full live narrative, because this is where
the "why" lives under decision 1. The narrative to record, from the confirmed `app-int` run:
the generated gate commands invoke `uv run`; every `uv run` regenerates `uv.lock` in the
worktree root; without this entry the file is untracked-but-not-ignored, so
`git ls-files --others --exclude-standard` in `git/scope.py`'s `attempt_changed_paths()`
reports it, and `enforce_write_scope()` fails any role whose `write_scope` excludes the
repository root (QA's is `['tests/**']`) with a message naming the lockfile -- and it fails
even when the role's own agent deleted the file first, because the WIP commit snapshot
already captured it. State plainly in Test 1's docstring that `--exclude-standard` already
honors `.gitignore`, so the enforcement code is correct and this was a content gap in
generated config.

Test 2's `build_contents(...)` call takes `base_branch=DEFAULT_BASE_BRANCH`, a placeholder
owner and repository name, `quality_gate_commands=DEFAULT_QUALITY_GATE_COMMANDS`,
`role_workers=_ROLE_WORKERS` (the dict already at module scope), and
`install_source=DEFAULT_INSTALL_SOURCE`. This call reads this repository's own four
instruction files through a path resolved from the script's `__file__`, not the working
directory, so it is deterministic and working-directory-independent -- verified by invoking
it in-process and observing all thirteen keys returned. The existing module already reads
`ci.yml` from disk inside a unit-marked test, so this is the established precedent, not a
new one.

Assert membership only. Do not assert the entry's index, the template's total entry count,
or the full entry list -- see decision 3.

Run the two new tests and confirm they fail before touching the template.

**(b) Add the entry to `GITIGNORE_CONTENT` in `scripts/scaffold_target_repo.py`.**

One line, inserted immediately after the `.venv/` entry: the bare filename, no leading
slash, no glob, no trailing slash, and no comment line of any kind (decision 1). Leave the
eight existing entries byte-identical.

Do not touch `RESUME_WORKFLOW_TEMPLATE`, `RUN_WORKFLOW_TEMPLATE`,
`DEFAULT_QUALITY_GATE_COMMANDS`, `ROLE_WRITE_SCOPE`, `build_contents`'s body, or anything
under `src/`. In particular, `src/dark_factory/git/scope.py` must see zero diff: its
`--exclude-standard` behavior is the mechanism this fix relies on, not the defect.

Re-run the module and confirm all seven tests pass.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_scaffold_target_repo.py -q && uv run python -c "from scripts.scaffold_target_repo import GITIGNORE_CONTENT; e=[l.strip() for l in GITIGNORE_CONTENT.splitlines() if l.strip()]; assert 'uv.lock' in e, e; assert len(e) == 9, e; print('GITIGNORE_OK', e)" && SRC_DIFF=$(git diff --name-only HEAD -- src/) && test -z "$SRC_DIFF" && echo SRC_CLEAN</automated>
  </verify>
  <done>
- `uv run pytest tests/unit/test_scaffold_target_repo.py -q` reports 7 passed, 0 failed (5
  pre-existing plus 2 new), and the three pre-existing test functions are unmodified in the
  diff.
- The gate above prints `GITIGNORE_OK` with a nine-entry list containing `uv.lock`.
- The gate prints `SRC_CLEAN`: no file under `src/` is modified relative to `HEAD`. If this
  task's edits are already committed by the time the gate runs, confirm the equivalent on
  the commit itself -- `git show --name-only --format= HEAD -- src/` must be empty.
- The two new tests' docstrings name `261031-fta`, the `app-int` CI failure, and the fact
  that `--exclude-standard` already honors `.gitignore`.
- `GITIGNORE_CONTENT` contains no line beginning with a hash.
  </done>
</task>

<task type="auto">
  <name>Task 2: Real-disk smoke of the written .gitignore, plus the repository's own lint and unit gates</name>
  <files>tests/unit/test_scaffold_target_repo.py, scripts/scaffold_target_repo.py</files>
  <read_first>
- `scripts/scaffold_target_repo.py` lines 603-620 (`write_output_file` -- the
  created/overwritten/skipped contract) and 620-680 (`build_arg_parser` -- the exact flag
  names the smoke invocation needs: `--target`, `--github-owner`, `--github-repo`, `--yes`)
- `.github/workflows/ci.yml` lines 39-43 (the exact lint and type commands CI runs, so this
  task's gates are the same ones, named the same way)
  </read_first>
  <action>
No production or test edits are expected in this task. It exists because Task 1 proves the
constant and the in-process wiring, and the thing a deployer actually gets is a file on
disk written by a real process.

**(a) Real-disk smoke.** Run the scaffold script as a real subprocess into a fresh temporary
directory, with a placeholder owner and repository name and the non-interactive flag, then
read the written `.gitignore` back from disk and confirm its parsed entries contain the
entry. Confirm the script exits zero and its own `parse_check` accepts the emitted YAML
(it runs as part of the normal invocation). Do this as a shell invocation recorded in the
SUMMARY, not as a new committed test -- Task 1's two tests are the committed regression
guard, and a subprocess scaffold-and-read test would belong to the integration tier, which
this one-line template change does not warrant.

**(b) Gates.** Run, and record each result in the SUMMARY:
- `uv run ruff check .` -- the same command CI's `Lint (ruff)` step runs.
- `uv run ruff format --check` on the two touched files only. If it reports drift in files
  this plan did not touch, record that as pre-existing drift (STATE.md already carries it as
  an acknowledged deferred item from 11-10 / 12-02) and do not reformat them.
- `uv run pytest -q -m "unit or contract"` -- the fast tiers. 0 failed expected.

`mypy` is deliberately not run: CI's `Types (mypy)` step targets `src/dark_factory` only,
and no file under `src/` is in scope here.

**(c) If a gate fails**, fix the cause in the two files this plan owns, or stop and report.
Do not widen scope into `src/`, `app-int`, or `261031-cp4`'s workflow-template work to make
a gate pass.
  </action>
  <verify>
    <automated>T=$(mktemp -d) && uv run python scripts/scaffold_target_repo.py --target "$T" --github-owner example-org --github-repo example-repo --yes >/dev/null && uv run python -c "
import sys, pathlib
entries = {l.strip() for l in pathlib.Path(sys.argv[1], '.gitignore').read_text(encoding='utf-8').splitlines() if l.strip()}
assert 'uv.lock' in entries, sorted(entries)
assert '.dark-factory/runs/' in entries, sorted(entries)
print('SMOKE_OK', sorted(entries))
" "$T" && uv run ruff check . && uv run ruff format --check scripts/scaffold_target_repo.py tests/unit/test_scaffold_target_repo.py && uv run pytest -q -m "unit or contract"</automated>
  </verify>
  <done>
- The smoke prints `SMOKE_OK` with a nine-entry list: the `.gitignore` a real scaffold
  invocation writes to disk ignores `uv.lock` and still ignores `.dark-factory/runs/`.
- The scaffold subprocess exits zero.
- `uv run ruff check .` is clean.
- `uv run ruff format --check` is clean on both touched files (any drift reported elsewhere
  is recorded as pre-existing and left alone).
- `uv run pytest -q -m "unit or contract"` reports 0 failed.
- `git status --porcelain` shows changes confined to `scripts/scaffold_target_repo.py`,
  `tests/unit/test_scaffold_target_repo.py`, and `.planning/`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| scaffold script -> target repository | Rendered text is written into a deployer's repository. Whatever this script emits governs that repository's behavior later, on somebody else's machine. |
| generated `.gitignore` -> git's reporting of changed paths | `git/scope.py`'s `attempt_changed_paths()` runs `git ls-files --others --exclude-standard`. That flag makes the generated `.gitignore` a direct input to what write-scope enforcement can see. Adding an entry *shrinks* the enforcement surface by exactly one path. |
| role agent (external AI runtime) -> target repository worktree | A role's agent runs with filesystem write access inside the worktree. Write-scope enforcement is the mechanism that bounds what it may leave behind. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-FTA-01 | Tampering | write-scope enforcement surface shrinks by one path | medium | accept | This is the real trade and it is accepted knowingly. A role's agent could write to `uv.lock` and `attempt_changed_paths()` would no longer report it. Four facts make accepting right: (1) `uv.lock` is a deterministic lockfile `uv` derives from the repository's own `pyproject.toml` -- it is tool output, not role-authored content, and a role cannot smuggle source changes through it without those changes also landing in a non-ignored manifest; (2) the alternative is strictly worse for the enforcement system's credibility -- today it raises a *false* violation that fails honest roles, and a gate that cries wolf gets switched off; (3) the ignore is one exact filename, not a glob and not a directory, so the shrink is a single well-understood path; (4) the generated `.gitignore` is a deployer-owned file they can narrow or delete, and `write_output_file` never clobbers an existing one. |
| T-FTA-02 | Tampering | precedent for ignoring a path the enforcement check reads | low | accept | Not a new pattern. `.dark-factory/runs/` is already in this same template for the same class of reason -- the Phase 4 artifact tree is deliberately ignored and then force-added by `commit_run_artifacts`. Task 2's smoke asserts that entry is still present, so this change cannot silently displace it. |
| T-FTA-03 | Information Disclosure | added template line | low | accept | One bare filename. No credential, secret name, connection string, or infrastructure value is introduced. Nothing in `scripts/` is rendered into a worker prompt, an artifact, or an event payload. Decision 1's no-comment rule also means no prose is added for a deployer-facing NOTE to misreport. |
| T-FTA-04 | Tampering | scope creep into enforcement code | medium | mitigate | A plausible wrong fix here is to "loosen" `attempt_changed_paths()` or `enforce_write_scope()`, weakening a security control to solve a config gap. Mitigated structurally: `files_modified` names exactly two files, neither under `src/`; Task 1's `<action>` forbids touching `git/scope.py` by name; Task 1's `<verify>` asserts `git diff --name-only src/` is empty; Task 2's `<done>` asserts the working tree is confined to the two files plus `.planning/`. |
| T-FTA-05 | Denial of Service | regression of `261031-cp4`'s uv-install fix | low | mitigate | The same file and the same test module were just changed by `261031-cp4`. A careless edit could disturb the workflow templates or their three ordering/pin/rationale guards, reintroducing the `FileNotFoundError: 'uv'` gate failure. Mitigated by Task 1's instruction not to modify the existing tests and by its `<done>` requiring 7 passed with the three pre-existing test functions unmodified in the diff. |
| T-FTA-SC | Tampering | npm/pip/cargo installs | n/a | accept | This plan adds no package-manager dependency. `pyproject.toml` is untouched, this repository's own `uv.lock` is untouched (it is tracked here and correctly so -- the ignore applies only to the *generated* target-repo template), and no install task exists. No package-legitimacy checkpoint applies. |
</threat_model>

<verification>
- `uv run pytest tests/unit/test_scaffold_target_repo.py -q` -- 7 passed (5 pre-existing from
  `261031-cp4`, 2 new), 0 failed.
- The nine-entry gate prints `GITIGNORE_OK` containing `uv.lock`, with the eight prior
  entries intact.
- A real `scripts/scaffold_target_repo.py --target $(mktemp -d) --github-owner example-org
  --github-repo example-repo --yes` invocation exits zero and writes a `.gitignore` that
  reads back from disk with both `uv.lock` and `.dark-factory/runs/` present.
- `git diff --name-only src/` is empty.
- `uv run ruff check .` and `uv run ruff format --check` clean on both touched files.
- `uv run pytest -q -m "unit or contract"` reports 0 failed.
- <human-check>The real proof is a live CI run: re-scaffold (or hand-add the `uv.lock` line
  to) a target repository's `.gitignore`, dispatch a run, and confirm QA -- whose
  `write_scope` is `['tests/**']` -- reaches its verdict instead of failing with
  `wrote outside its configured write_scope ... ['uv.lock']`. Record the run URL and QA's
  real outcome (PASS or a genuine content-based failure; both prove the lockfile is no
  longer reported as a changed path). Note that `app-int` itself was already fixed directly
  in that repository, so this check needs either a fresh scaffold or a different target
  repo.</human-check>
</verification>

<success_criteria>
- The generated `.gitignore` ignores `uv.lock`, so the lockfile every `uv run` regenerates is
  never reported as a changed path and never fails a role's write-scope check.
- The entry is a bare filename matching at any depth -- not a glob, not root-anchored.
- The entry is proven both on the constant and through the `build_contents` wiring by
  committed tests, and on disk by a real scaffold invocation.
- All eight pre-existing template entries survive, `.dark-factory/runs/` included.
- No comment line enters the template, so `_gitignore_missing_entries()`'s deployer NOTE
  still lists only real ignorable paths.
- No file under `src/` is modified: `git/scope.py`'s `--exclude-standard` behavior is the
  mechanism relied on, not the defect, and no security control is loosened to close a config
  gap.
- `261031-cp4`'s `Install uv` step and its three guards are byte-identical.
</success_criteria>

<output>
Create `.planning/quick/261031-fta-add-uv-lock-to-scripts-scaffold-target-r/261031-fta-SUMMARY.md` when done
</output>
