---
phase: 01-walking-skeleton-one-durable-run
plan: 03
subsystem: infra
tags: [pydantic-settings, secretstr, structlog, redaction, regex, tdd, security]

# Dependency graph
requires:
  - phase: 01-02
    provides: "domain contracts (RunStatus, WorkerResult, EventType) — imported by later plans, not by this one; this plan adds config/ + events/redaction.py + logging.py + tests/support/"
provides:
  - "config/settings.py — Settings(BaseSettings) with SecretStr fields (database_url, database_url_direct, github_token) + log_level; known_secret_values() walks model_fields; get_settings() lru_cache singleton"
  - "events/redaction.py — the one recursive redact(value, *, known_secrets, patterns=True); scrub_known_values() = patterns=False alias (D-18); compiled-once D-15 pattern table + sensitivity frozenset; idempotent; [redacted:<label>] tokens (D-17)"
  - "logging.py — configure_logging() installs the redaction processor after merge_contextvars and before JSONRenderer; sole caller of structlog.configure"
  - "tests/support/log_sink.py — real_log_sink() StringIO capture over the production chain (NOT structlog.testing); reused by Plan 08 SC5 proof"
  - "Task 1 decision checkpoint resolved: known-values-only (D-18 as recorded)"
affects: [01-04, 01-05, 01-06, 01-07, 01-08, 01-09, "Phase 6 secret-grep checks", "Phase 12 secret-grep checks"]

actuals:
  tokens: 6950
  tasks: 2
  commits: 4
  plan_head_before: c82808c24624af3777560bd7a775d5286a796fe9

tech-stack:
  added: []
  patterns:
    - "One redaction path: a single recursive redact() is the only scrubbing implementation — no per-call-site .replace(), no second helper (D-14). scrub_known_values() is a thin patterns=False alias, not a parallel implementation"
    - "Scope split by argument, not by duplication: redact(patterns=True) for events/results/logs; redact(patterns=False) for persisted task text (D-18) — same function, same tokens"
    - "Settings is the single declared source of live secret values: known_secret_values() derives {value: label} by walking model_fields + isinstance(SecretStr), so a credential added in a later phase is covered automatically"
    - "Compile regexes once at import into a module-level table; never per-call — every event write would otherwise pay a regex-compilation"
    - "Redaction tokens are self-immune: no rule re-matches [redacted:...], so redact() is idempotent over the whole test corpus"
    - "Log-path proof runs against a real StringIO sink with the full processor chain active, never structlog.testing.capture_logs (which bypasses processors — RESEARCH Pitfall 5)"

key-files:
  created:
    - "src/dark_factory/config/__init__.py, src/dark_factory/config/settings.py"
    - "src/dark_factory/events/redaction.py"
    - "src/dark_factory/logging.py"
    - "tests/support/__init__.py, tests/support/log_sink.py"
    - "tests/unit/test_settings.py, tests/unit/test_redaction.py, tests/unit/test_log_redaction.py"
  modified: []

key-decisions:
  - "Task 1 decision checkpoint (blocking-human, pre-decided by the operator): Option A known-values-only (D-18 as recorded). Persisted task text (runs.normalized_task, runs.source_ref) is scrubbed only for exact matches of the live SecretStr values; pattern redaction applies fully to every run_events.payload, every role_executions.result/error, and every log line."
  - "40-hex classic-PAT rule uses `github\\w*` as the context anchor (not bare `github`) and case-insensitive `[0-9a-fA-F]{40}` — tighter than the RESEARCH starting regex; within the plan's explicit 'tune against the test corpus' latitude. Tests prove both directions: a bare commit SHA in prose survives, a 40-hex value in a github-ish context does not."
  - "The sensitive key=value rule uses a callable replacement that lowercases the label ([redacted:database_url], not [redacted:DATABASE_URL]) while leaving the operator's original key text in place — D-17 labels are lowercase."
  - "Authorization: Bearer rule replaces the whole match with [redacted:authorization] (drops the header name) rather than keeping the key visible — simplest form that cannot leak the token through the generic key=value rule's narrower capture."
  - "configure_logging() filters at INFO and does not yet consume Settings.log_level — the field is declared per the plan's Task 2 behavior block; wiring the level is left for a later plan."

patterns-established:
  - "Redaction-at-birth: redact() + the structlog processor exist before any persistence code (Plan 04). SEC-02 is 'from the first persistence code, not retrofitted'."
  - "Real-sink logging tests: tests/support/log_sink.py is the sanctioned capture helper; capture_logs is banned for redaction assertions."
  - "RED (test-only, fails on ModuleNotFoundError / assertion) -> GREEN (feat) two-commit TDD rhythm, continuing the 01-02 convention; workflow.tdd_mode is false so the plan-level RED-evidence verb gate is not enforced."

requirements-completed: [SEC-02]

coverage:
  - id: D1
    description: "Settings (pydantic-settings, SecretStr for DATABASE_URL / DATABASE_URL_DIRECT / GITHUB_TOKEN, plus LOG_LEVEL), get_settings() cached singleton, known_secret_values() -> {live value: lowercase field name} derived by walking model_fields, skipping unset and <8-char values"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_settings.py (10 tests: SecretStr fields, repr masks live values, required URLs, optional token None, LOG_LEVEL default, known_secret_values mapping + <8-char + unset omission, get_settings identity)"
        status: pass
      - kind: other
        ref: "uv run mypy src/dark_factory (strict) — Success"
        status: pass
    human_judgment: false
  - id: D2
    description: "One recursive redact() covering all four D-15 pattern families (DB URIs with creds; sensitive key=value/key: value; GitHub token shapes ghp_/gho_/ghu_/ghs_/ghr_ + github_pat_ + context-scoped 40-hex; Authorization: Bearer) plus dict-key matching plus exact-value substitution from Settings; idempotent; honours the patterns=False scope split (D-18) via scrub_known_values(); [redacted:<label>] tokens (D-17)"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_redaction.py (38 tests incl. per-pattern-row cases, bare-SHA-survives vs github-context-redacted, <8-char known-value skip, longest-first ordering, patterns=False keeps doc-style URI, idempotency corpus x2)"
        status: pass
      - kind: other
        ref: "uv run ruff check . — All checks passed; uv run mypy src/dark_factory (strict) — Success"
        status: pass
    human_judgment: false
  - id: D3
    description: "configure_logging() installs the redaction processor into the structlog chain after merge_contextvars and before JSONRenderer, and is the sole caller of structlog.configure; tests/support/log_sink.py is a real StringIO-sink capture helper (not structlog.testing) reused by Plan 08's SC5 proof"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_log_redaction.py (4 tests: pattern-shaped secret redacted in a real log line, live known secret value never reaches the sink, JSON line parses, sink helper restores prior config, AST check that structlog.testing is not imported/used)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-08
status: complete
---

# Phase 01 Plan 03: Redaction at Birth Summary

**One recursive `redact()` (D-15 pattern table + dict-key + exact-value substitution from `Settings`, idempotent, `patterns=False` scope split for persisted task text) wired as the sole structlog processor, with `Settings` (`SecretStr` fields + `known_secret_values()`) as its single source of live secret values — all delivered RED to GREEN.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-08T08:09:11Z
- **Completed:** 2026-09-08T08:16:09Z (task commits); SUMMARY + state after
- **Tasks:** 2 executed (Task 1 was a pre-decided decision checkpoint)
- **Files modified:** 9 created (2 empty package markers; 7 with content)

## Task 1 decision — recorded (plan `<output>` requires it)

**Checkpoint:** `type="checkpoint:decision" gate="blocking-human"` — "How aggressively should Dark Factory scrub the operator's own task text before persisting it?"

**Selected: Option A — `known-values-only` (D-18 as recorded).** Pre-decided by the operator; not re-prompted.

- Pattern-based redaction (the D-15 set below) applies **fully** to every `run_events.payload`, every `role_executions.result` / `error`, and every log line.
- Persisted task text (`runs.normalized_task`, `runs.source_ref`) is scrubbed **only for exact matches of the live secret values** from the `Settings` object (`scrub_known_values()` / `redact(..., patterns=False)`), never by generic pattern — so a task legitimately discussing connection-string syntax persists as written, while a genuinely leaked live credential is removed everywhere.
- `redact()` honours this `patterns=False` scope split and is idempotent.

## Final pattern table — as implemented in `src/dark_factory/events/redaction.py`

Compiled once at import, applied in this order (order matters: the token-shape and `Authorization: Bearer` rules run before the generic `key=value` rule so a bearer value cannot leak through the narrower capture):

| # | Target | Regex (implemented) | Replacement |
|---|--------|---------------------|-------------|
| 1 | Postgres/DB connection URI with embedded credentials | `(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:[^\s:/@]+@\S+` | `[redacted:database_url]` |
| 2 | GitHub fine-grained PAT | `\bgithub_pat_[A-Za-z0-9_]{22,}\b` | `[redacted:github_token]` |
| 3 | GitHub classic / OAuth token shapes (`ghp_ gho_ ghu_ ghs_ ghr_`) | `\b(gh[porsu])_[A-Za-z0-9]{36,}\b` | `[redacted:github_token]` |
| 4 | 40-hex classic PAT — **github-context-scoped only** | `(?i)(github\w*[^\n]{0,40}?)\b[0-9a-fA-F]{40}\b` | `\1[redacted:github_token]` |
| 5 | `Authorization: Bearer <value>` header | `(?i)authorization"?\s*[:=]\s*"?bearer\s+[A-Za-z0-9._\-]+` | `[redacted:authorization]` |
| 6 | sensitive `key=value` / `key: value` | `(?i)\b(<sensitive-keys>)\b(\s*[:=]\s*)("?)([^\s"',}]+)\3` | `<key><sep>[redacted:<key-lowercased>]` (callable) |
| — | **dict-key match** (structural, not regex) | `key.lower()` ∈ sensitivity set → value replaced regardless of type | `[redacted:<key-lowercased>]` |
| — | **exact-value substitution (D-16)** | literal-substring match of each `known_secret_values()` entry, length ≥ 8, **longest value first** | `[redacted:<field-label>]` |

**Sensitivity set** (`_SENSITIVE_KEYS`, drives rows 6 and the dict-key match): `password, passwd, secret, secret_key, token, api_key, apikey, access_key, database_url, github_token, authorization, bearer`.

**Scope modes:**
- `redact(value, known_secrets=…)` — exact-value substitution **then** rows 1–6 + dict-key. Used for `run_events.payload`, `role_executions.result` / `error`, every log line.
- `redact(value, known_secrets=…, patterns=False)` / `scrub_known_values(value, known_secrets=…)` — exact-value substitution + dict-key match only. Used for persisted task text (D-18).

`known_secret_values()` maps `{live SecretStr value: lowercase field name}` — e.g. the `DATABASE_URL` value → label `database_url`, the `GITHUB_TOKEN` value → `github_token` — omitting any unset optional secret and any value shorter than 8 characters.

## Accomplishments

- **`Settings`** (`config/settings.py`): `pydantic-settings` `BaseSettings` with `SettingsConfigDict(env_file=".env", extra="ignore")`. `database_url` / `database_url_direct` are required `SecretStr`; `github_token` is optional `SecretStr | None = None`; `log_level: str = "INFO"`. `repr()` / `str()` render every secret masked. `known_secret_values()` walks `type(self).model_fields` with an `isinstance(SecretStr)` check — not a hardcoded name list — so a credential added in Phase 6/7 is covered automatically. `get_settings()` is a `functools.lru_cache(maxsize=1)` singleton.
- **`redact()`** (`events/redaction.py`): the one recursive redaction path — recurses into `Mapping` values and `list`/`tuple` elements (tuples returned as lists), returns `int`/`float`/`bool`/`None` unchanged, applies known-value substitution then (when `patterns`) the compiled table to strings. `scrub_known_values()` is a two-line `patterns=False` alias, not a parallel implementation. Idempotent across the whole test corpus — the `[redacted:…]` tokens are matched by no rule.
- **`configure_logging()`** (`logging.py`): the **only** `structlog.configure` call in the codebase. Chain: `merge_contextvars` → `add_log_level` → `TimeStamper(iso, utc)` → **redaction processor** → `JSONRenderer`. The processor sits after `merge_contextvars` (bound `run_id`/`role`/`attempt` context is also scrubbed) and before the renderer (nothing reaches the sink unscrubbed; JSON encoding stops a newline in task text forging a log line). Accepts an optional `logger_factory` so a test can point the same chain at a `StringIO`.
- **`tests/support/log_sink.py`**: `real_log_sink()` context manager — configures the production chain against a `StringIO`, yields the buffer, restores the prior `structlog` config on exit. Explicitly not `structlog.testing.capture_logs` (bypasses processors → false green on an unrecoverable-leak criterion, RESEARCH Pitfall 5). Plan 08's SC5 end-to-end proof reuses it.
- All four D-15 families plus dict-key matching plus exact-value substitution are covered by 38 passing unit tests in `test_redaction.py`, incl. a bare-commit-SHA-in-prose case that proves the 40-hex rule does not clobber legitimate task text.

## Task Commits

1. **Task 2: Settings — the single choke point for infrastructure secrets** (`tdd="true"`)
   - RED `6f0b697` — `test(01-03)`: 10 failing tests (ModuleNotFoundError — `dark_factory.config` absent)
   - GREEN `b573868` — `feat(01-03)`: `Settings` + `get_settings()` + `known_secret_values()`
2. **Task 3: `redact()` and the structlog processor — redaction at birth** (`tdd="true"`)
   - RED `db29bdb` — `test(01-03)`: 34 failing redaction tests + `test_log_redaction.py` collection failure (`dark_factory.events.redaction` and `tests.support` absent)
   - GREEN `41f812c` — `feat(01-03)`: `events/redaction.py`, `logging.py`, `tests/support/log_sink.py`

**Task 1** was a `checkpoint:decision` pre-resolved by the operator (`known-values-only`); it produced no code commit — the decision is recorded in this SUMMARY and was already captured as D-18 in `01-CONTEXT.md`.

**Plan metadata:** docs commit (see final commit).

## TDD Gate Compliance

| Task | RED (`test(01-03)`) | GREEN (`feat(01-03)`) | REFACTOR | Status |
|------|---------------------|-----------------------|----------|--------|
| 2 | `6f0b697` | `b573868` | — | Pass |
| 3 | `db29bdb` | `41f812c` | — | Pass |

Each RED commit failed at the time it was made because the target module did not yet exist (`ModuleNotFoundError`), continuing the 01-02 convention. `workflow.tdd_mode` is `false`, so the plan-level `check tdd-red-evidence` verb gate is not enforced; the RED→GREEN discipline was followed per the execution prompt. No gate violations.

## Files Created/Modified

- `src/dark_factory/config/__init__.py` — empty package marker
- `src/dark_factory/config/settings.py` — `Settings(BaseSettings)`, `get_settings()`, `known_secret_values()`
- `src/dark_factory/events/redaction.py` — `_SENSITIVE_KEYS`, compiled `_PATTERNS`, `_scrub_known`, `_redact_str`, `redact()`, `scrub_known_values()`
- `src/dark_factory/logging.py` — `_redaction_processor`, `configure_logging()`
- `tests/support/__init__.py` — empty package marker
- `tests/support/log_sink.py` — `real_log_sink()` real-sink capture helper
- `tests/unit/test_settings.py` — 10 unit tests (hermetic: `_env_file=None` + `monkeypatch`, no real `.env` read)
- `tests/unit/test_redaction.py` — 38 unit tests (per behavior bullet + per pattern row + idempotency corpus)
- `tests/unit/test_log_redaction.py` — 4 unit tests via `tests/support/log_sink.py`, incl. an AST check that `structlog.testing` is neither imported nor referenced

## Decisions Made

- **Task 1: `known-values-only` (Option A / D-18).** Recorded above. Implemented as the `patterns` flag on `redact()` plus the `scrub_known_values()` alias.
- **40-hex rule anchored on `github\w*` and case-insensitive hex.** Tighter than the RESEARCH starting regex; the plan invited tuning against the test corpus. Both directions are tested.
- **Row-6 replacement lowercases the label via a callable**, keeping the operator's original key text — D-17 tokens are lowercase.
- **`Authorization: Bearer` replaced whole-match** with `[redacted:authorization]` — cannot leak the token through row 6's narrower `[^\s"',}]+` capture.
- **`ruff format` run alongside `ruff check`** (CLAUDE.md mandates both; plan `<verify>` lists only `ruff check`). Formatting-only; folded into the two GREEN commits. Same call the 01-02 executor made.
- **Tests are hermetic against a local `.env`.** A developer `.env` exists on this machine; every `Settings` test passes `_env_file=None` and sets fake values via `monkeypatch`, and `get_settings()` tests `cache_clear()` before and after. No real credential enters the test process, any fixture, or this SUMMARY.

## Deviations from Plan

### Auto-fixed / tooling

**1. [Rule 3 - Tooling] `ruff format` run in addition to `ruff check`**
- **Found during:** Task 2 and Task 3 verification
- **Issue:** `.claude/CLAUDE.md` mandates `ruff check` + `ruff format`; the plan `<verify>` blocks list only `ruff check .`. `ruff format --check` flagged 3 test files.
- **Fix:** `uv run ruff format src tests` — whitespace / line-wrap only, no logic change. Folded into the RED commit (`test_settings.py`) and the two GREEN commits (`test_log_redaction.py`).
- **Files modified:** `tests/unit/test_settings.py`, `tests/unit/test_log_redaction.py`
- **Verification:** `ruff check .` + `ruff format --check src tests` both clean; all tests green.
- **Committed in:** `b573868`, `41f812c`

---

**Total deviations:** 1 (tooling). No scope creep — every file in the plan's `files_modified` list was produced with the specified exports.
**Impact on plan:** None substantive. All plan `<verify>` commands and both `<success_criteria>` blocks pass.

## Issues Encountered

- **Self-referential architectural check.** The first draft of `test_log_redaction.py`'s "does not use `structlog.testing`" guard did a raw-text substring scan, which tripped on the module's own docstring explaining *why* `structlog.testing.capture_logs` is banned. Rewrote it to parse the file's AST and assert no `Import` / `ImportFrom` targeting `structlog.testing` and no `structlog.testing` attribute access. Resolved within Task 3; the GREEN commit carries the AST version.

## Verification Results

| Command | Result |
|---------|--------|
| `uv run pytest -m unit -q` | 92 passed, 5 deselected — no marker warnings |
| `uv run pytest -m unit -q -W error::pytest.PytestUnknownMarkWarning` | 92 passed — confirms no unknown-marker warnings |
| `uv run pytest -m unit -q tests/unit/test_settings.py` | 10 passed (plan floor: ≥6) |
| `uv run pytest -m unit -q tests/unit/test_redaction.py tests/unit/test_log_redaction.py` | 38 passed (plan floor: ≥15) |
| `uv run mypy src/dark_factory` | Success: no issues found in 16 source files (strict) |
| `uv run mypy src/dark_factory/config` / `src/dark_factory/events src/dark_factory/logging.py` | Success |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check src tests` | all files formatted |

## User Setup Required

None — no external service configuration. Every `Settings` test is hermetic (`_env_file=None` + `monkeypatch`); no real `.env` is read and no real credential is asserted against.

## Next Phase Readiness

- **Ready for Plan 04 (schema + Alembic):** `redact()` exists and is importable as the single scrubbing path; Plan 04 wires it into `apply_transition()` before every JSONB write (`run_events.payload`, `role_executions.result`, `role_executions.error`). `get_settings().known_secret_values()` supplies the live-value map.
- **Ready for Plan 08 (SC5 proof):** `tests/support/log_sink.py::real_log_sink()` is the sanctioned real-sink capture helper.
- **Guard active:** `configure_logging()` is the only `structlog.configure` caller and `redact()` is the only redaction implementation — any later violation is catchable (an explicit sole-caller assertion test is a candidate for Plan 04/09).
- **Open (unchanged):** `Settings.log_level` is declared but not yet consumed by `configure_logging()` — a later plan wires the level. The three research-flagged blockers (artifact durability → Phase 5, lease TTL → Phase 2, Copilot/Hermes flag matrix → Phase 8) are untouched.

## Self-Check: PASSED

All 10 content/marker files verified present on disk. All 5 commits (`6f0b697`, `b573868`, `db29bdb`, `41f812c`, `2e0339a`) verified in `git log`.

---
*Phase: 01-walking-skeleton-one-durable-run*
*Completed: 2026-09-08*
