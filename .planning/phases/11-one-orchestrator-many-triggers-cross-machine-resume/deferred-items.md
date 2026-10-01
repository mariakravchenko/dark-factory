## 11-07: Pre-existing environment-dependent test failure (out of scope)

- **Test:** `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
- **Observed:** Fails in this sandbox because a live `ANTHROPIC_API_KEY` and `claude` CLI binary are both present/configured, so `ClaudeCodeWorker.execute({})` makes a real call and returns `COMPLETED` instead of the test's expected `FAILED` (the test assumes no credential is configured in the test environment).
- **Scope:** Plan 11-07 touches only `README.md` and `tests/unit/test_resume_workflow_reference_doc.py`. This failure is unrelated to those files and pre-exists this plan's changes.
- **Action:** Not fixed (scope boundary). Deferred for a future plan/environment-hygiene pass to either mock the credential gate or isolate `ANTHROPIC_API_KEY` from this test's environment.
