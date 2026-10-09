"""Unit coverage for WorkerRegistry membership + the (now former) placeholder
worker names (Plan 03-01 Task 2, WORK-02; ``claude-code`` updated by Plans
07-01/07-03; ``copilot`` updated by Plan 08-01; ``hermes`` updated by Plan
08-02).

Membership must work without constructing a worker. No name in
``default_registry`` resolves to a not-yet-implemented placeholder any more
(D-04). ``claude-code`` is no longer a placeholder as of Plan 07-01 -- it
resolves to a real :class:`~dark_factory.workers.claude_code.
ClaudeCodeWorker` (see ``tests/unit/test_claude_code_worker.py`` for the
full behavior suite). ``copilot`` is no longer a placeholder as of Plan
08-01 -- it resolves to a real
:class:`~dark_factory.workers.copilot.CopilotWorker` (see
``tests/unit/test_copilot_worker.py``). ``hermes`` is no longer a
placeholder as of Plan 08-02 -- it resolves to a real
:class:`~dark_factory.workers.hermes.HermesWorker` (see
``tests/unit/test_hermes_worker.py``).

**This module spawns nothing, deliberately.** A placeholder was a
*factory* that raised ``NotImplementedError`` when invoked
(``workers/registry.py``: "a placeholder factory would raise
``NotImplementedError`` during validation"), so ``default_registry.get()``
returning an instance of the real adapter class *is* the complete proof of
"not a placeholder" -- invoking the factory is the test. Nothing further is
needed, and nothing further may be done here.

The three adapter tests below used to go on to call ``worker.execute({})``
/ ``worker.resume({}, None, None)`` and assert
``status is WorkerResultStatus.FAILED``, on a *comment-stated* premise that
no credential was configured. That premise was enforced by nothing, and the
calls were removed as a real defect -- not a cleanup. Two independent
reasons, both measured (debug session
``.planning/debug/resolved/claude-cli-test-spawns-real-binary-with-key-present.md``):

1. ``Settings`` loads ``env_file=".env"`` **relative to the CWD**, and
   pytest's rootdir is the repo root, so a developer whose git-ignored
   ``.env`` supplies ``ANTHROPIC_API_KEY`` / ``COPILOT_GITHUB_TOKEN`` opened
   the credential gate and spawned the **real** ``claude`` / ``copilot``
   CLI. Worse than billable: the bare ``{}`` context carries no ``run_id``,
   so ``resolve_dirs`` falls back to ``work_dir = Path.cwd()`` and the agent
   ran against the **live repository working tree** under
   ``--permission-mode dontAsk`` / ``--no-ask-user``. The unit tier took
   418s instead of 37s.
2. ``assert status is FAILED`` could not have caught it anyway. Every
   adapter's ``execute()`` wraps itself in a never-raise handler, so FAILED
   means *either* "the credential gate held and nothing spawned" *or* "the
   real binary ran and exited non-zero". The ``copilot`` test therefore
   spawned the real CLI on every run and still reported green. A FAILED
   assertion is not evidence of hermeticity.

Coverage is unchanged by the removal:
``tests/contract/test_coding_worker_contract.py`` already pins
"``execute()``/``resume()`` never raise" for all four adapters, hermetically
-- its autouse ``_fake_clis_on_path`` fixture PATH-prepends fake executables
and sets fake credentials, which is this repo's established idiom for
touching a real adapter in a non-live tier. Any future test here that needs
to *invoke* an adapter must adopt that idiom (``fake_claude_env`` /
``fake_copilot_env`` / ``fake_hermes_env``) rather than rely on a credential
being absent. ``tests/conftest.py``'s ``_no_real_agent_binary_spawn``
tripwire enforces that mechanically.
"""

import pytest

from dark_factory.workers.registry import UnknownWorkerError, default_registry

pytestmark = pytest.mark.unit


def test_all_placeholder_names_plus_fake_are_members() -> None:
    for name in ("claude-code", "copilot", "hermes", "fake"):
        assert name in default_registry


def test_an_unregistered_name_is_not_a_member() -> None:
    assert "bogus" not in default_registry


def test_get_on_an_unregistered_name_raises_unknown_worker_error() -> None:
    with pytest.raises(UnknownWorkerError):
        default_registry.get("bogus")


def test_claude_code_resolves_to_a_real_adapter_not_a_placeholder() -> None:
    from dark_factory.workers.claude_code import ClaudeCodeWorker

    # `get` invokes the registered factory; a placeholder factory raised
    # NotImplementedError here. Reaching an instance of the real class is
    # the whole proof. No execute()/resume() call -- see the module docstring.
    worker = default_registry.get("claude-code")
    assert isinstance(worker, ClaudeCodeWorker)

    # capabilities() is implemented (not a placeholder), does not raise, and
    # spawns nothing.
    assert worker.capabilities().non_interactive is True


def test_copilot_resolves_to_a_real_adapter_not_a_placeholder() -> None:
    from dark_factory.workers.copilot import CopilotWorker

    worker = default_registry.get("copilot")
    assert isinstance(worker, CopilotWorker)

    assert worker.capabilities().non_interactive is True


def test_hermes_resolves_to_a_real_adapter_not_a_placeholder() -> None:
    from dark_factory.workers.hermes import HermesWorker

    worker = default_registry.get("hermes")
    assert isinstance(worker, HermesWorker)

    assert worker.capabilities().non_interactive is True
