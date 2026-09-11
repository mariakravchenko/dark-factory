---
phase: 03
slug: configuration-driven-pipeline
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: 2026-09-11
---

# Phase 03 - Security

> Per-phase security contract for the plan-authored threat register. This audit
> verifies declared mitigations and does not add threats outside that register.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Repository config -> loader | Repository-controlled YAML selects roles, workers, actions, and file paths. | Untrusted configuration data |
| Instruction path -> filesystem | A role definition selects Markdown that is inlined into the persisted snapshot. | Repository file path and text |
| Registry name -> Python callable | Persisted worker and hook names select registered implementation objects. | Identifier selecting executable code |
| CLI config -> run creation | Validated configuration becomes durable run state. | Effective-config snapshot |
| Persisted snapshot -> resume | Every later process reconstructs the pipeline from PostgreSQL rather than live files. | Durable orchestration state |
| Hook -> lifecycle mutation | Hooks execute around a worker but outside the lifecycle transaction. | ActionContext and worker result |
| Dependency source -> build | PyYAML enters the runtime dependency graph through the lockfile. | Third-party package code |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|-------------|-----------------------|--------|
| T-03-01 | Tampering / Elevation | YAML parsing | mitigate | `_safe_load_mapping` calls `yaml.safe_load`; `test_loader_only_ever_calls_yaml_safe_load` guards against `yaml.load` and explicit loaders. | closed |
| T-03-02 | Elevation | Worker and action selection | mitigate | `load_effective_config` validates names by membership in `WorkerRegistry` and `ActionRegistry`; unknown names raise `ConfigError`; no `getattr` or `importlib` dispatch. | closed |
| T-03-03 | Information disclosure | Instruction path resolution | mitigate | Instruction paths are resolved and required to be files under the repository root; bad-config DB/UAT coverage verifies traversal rejection with no orphan run. | closed |
| T-03-04 | Information disclosure | Persisted config snapshot | mitigate | `create_run` applies recursive `redact()` before writing `runs.workflow`; config types remain isolated from infrastructure `Settings`. | closed |
| T-03-05 | Tampering | Resume determinism | mitigate | `_advance_once` builds from `state.workflow`; the orchestrator import-graph guard excludes `config.loader`; Neon UAT verified pause/edit/resume behavior. | closed |
| T-03-06 | Elevation / command injection | `quality_gate.commands` | accept | Phase 3 stores commands but has no execution path. Execution is deferred to Phase 9, whose plan constraint requires argument lists and forbids `shell=True`. | closed |
| T-03-07 | Elevation | Action lifecycle access | mitigate | Shipped actions are leaf no-ops with no persistence, orchestrator, events, or config imports; the single-mutation-path AST guard passes. | closed |
| T-03-08 | Tampering | Missing pipeline snapshot | mitigate | `pipeline_from_snapshot` indexes `snapshot["roles"]` directly and raises when absent; `DEFAULT_PIPELINE` is fixture-only. | closed |
| T-03-09 | Tampering | Invalid role persistence | mitigate | `WorkflowConfig` rejects non-role statuses before `start_run`; DB/UAT tests verify `ConfigError` and unchanged run count. | closed |
| T-03-10 | Elevation | Hardcoded pipeline fallback | mitigate | `start_run` requires `snapshot`; production orchestration contains no `DEFAULT_PIPELINE` or `_workflow_snapshot` reference. | closed |
| T-03-11 | Denial of service | Role literals in orchestration | mitigate | `test_no_role_name_literal.py` AST-scans the orchestrator and pipeline and includes a self-proving sanity case. | closed |
| T-03-12 | Denial of service | Hooks inside DB transaction | mitigate | Before/after hooks bracket the worker call before `apply_transition`; no transaction spans hook or worker execution. Runtime hook-order tests pass. | closed |
| T-03-13 | Tampering | Role-specific hook branch | mitigate | `_role_definition` performs data lookup and hook execution has no role-name branch; the role-literal guard passes. | closed |
| T-03-14 | Repudiation | Acceptance-proof disappearance | mitigate | The Phase 3 acceptance gate fails for missing, empty, or test-less proof files and drift-checks the validation map; full UAT passed. | closed |
| T-03-SC | Tampering | PyYAML supply chain | mitigate | PyYAML was approved at the blocking package-legitimacy checkpoint, constrained to `>=6,<7`, locked in `uv.lock`, and `uv lock --check` passes. | closed |

*Status: open / closed.*
*Disposition: mitigate (implementation verified) / accept (risk documented) / transfer (third party).*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-06 | Quality-gate command execution is outside Phase 3. Commands are inert snapshot data until Phase 9 implements constrained subprocess execution without `shell=True`. | Phase 3 plan | 2026-09-10 |

Accepted risks do not resurface in future audit runs unless their scope changes.

---

## Verification Evidence

| Check | Result |
|-------|--------|
| Phase 3 Neon UAT | 8 passed, 0 issues (`03-UAT.md`) |
| Focused security-relevant unit suite | 41 passed |
| `uv lock --check` | passed; 54 packages resolved |
| `mypy src/dark_factory` | passed; 45 source files |
| `ruff check .` | passed |
| Forbidden action-package imports | none found |
| Live config-loader use in orchestrator | none found outside docstrings; import-graph guard passed |
| Quality-gate command execution in Phase 3 | none found |

The Phase 3 code review's `WR-01` roles-directory containment advisory is not a
plan-authored threat and is therefore outside this verification-only register.
It remains recorded in `03-REVIEW.md` as non-blocking hardening work.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-11 | 15 | 15 | 0 | OpenCode security audit |

---

## Sign-Off

- [x] All plan-time threats have a disposition.
- [x] Accepted risks are documented in the Accepted Risks Log.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-09-11
