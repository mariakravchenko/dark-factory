"""Live-runtime skip-condition helpers shared by all three real-adapter live
integration suites (D-02, QUAL-03, Plan 08-03 Task 1).

The single definition of "this runtime is available": a real CLI binary on
``PATH`` and its credential configured through ``Settings``. Every live
integration module (``tests/integration/test_claude_code_live.py``,
``test_copilot_live.py``, ``test_hermes_live.py``) imports from here instead
of re-deriving its own skip condition, so the three modules cannot drift on
what "absent" means (08-RESEARCH.md Pattern 1).

The two checks are deliberately separate functions rather than one combined
boolean: a half-configured environment (binary present, credential absent --
or vice versa) must produce a skip reason naming the *specific* unmet
precondition, not a generic "environment not ready" message -- this is
QUAL-03's own literal "skipped ... with a reason" requirement (08-03-PLAN.md,
Edge probe QUAL-03/adjacency). :func:`credential_missing` reads through
:func:`~dark_factory.config.settings.get_settings` rather than ``os.environ``
directly, so a credential supplied only through an operator's ``.env`` file
-- which ``pydantic-settings`` loads into ``Settings`` but a bare
``os.environ`` check would miss -- still counts as configured, exactly as it
does for the adapter itself at spawn time.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from dark_factory.config.settings import get_settings

__all__ = [
    "LIVE_RUNTIMES",
    "LiveRuntime",
    "binary_missing",
    "credential_missing",
    "skip_reason",
]


class LiveRuntime(BaseModel):
    """One real adapter's live-spike preconditions: the ``PATH`` binary name
    and the ``Settings`` field that holds its credential."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_name: str
    binary: str
    credential_field: str
    credential_label: str


LIVE_RUNTIMES: Mapping[str, LiveRuntime] = {
    "claude-code": LiveRuntime(
        worker_name="claude-code",
        binary="claude",
        credential_field="anthropic_api_key",
        credential_label="Settings.anthropic_api_key",
    ),
    "copilot": LiveRuntime(
        worker_name="copilot",
        binary="copilot",
        credential_field="copilot_github_token",
        credential_label="Settings.copilot_github_token",
    ),
    "hermes": LiveRuntime(
        worker_name="hermes",
        binary="hermes",
        # Hermes has no dedicated credential (08-RESEARCH.md Finding 1) --
        # it reuses the same Anthropic key ClaudeCodeWorker does.
        credential_field="anthropic_api_key",
        credential_label="Settings.anthropic_api_key",
    ),
}


def binary_missing(runtime: LiveRuntime) -> bool:
    """``True`` iff ``runtime.binary`` cannot be resolved on ``PATH``."""
    return shutil.which(runtime.binary) is None


def credential_missing(runtime: LiveRuntime) -> bool:
    """``True`` iff ``runtime``'s credential ``Settings`` field is unset.

    Reads through :func:`~dark_factory.config.settings.get_settings` (never
    ``os.environ`` directly), so an operator's ``.env`` file counts.
    """
    return getattr(get_settings(), runtime.credential_field) is None


def skip_reason(runtime: LiveRuntime) -> str | None:
    """``None`` when both preconditions hold; otherwise one sentence naming
    ``runtime`` and the specific unmet precondition.

    The binary check runs first: when the binary is absent, the reason
    names the binary and never mentions the credential field, even when the
    credential also happens to be unset -- and symmetrically, when only the
    credential is missing, the reason never mentions the binary. This is
    what makes a half-configured environment's skip reason diagnostic
    rather than generic (Edge probe QUAL-03/adjacency, resolved).
    """
    if binary_missing(runtime):
        return (
            f"{runtime.worker_name}: {runtime.binary!r} not found on PATH -- "
            "install the CLI to run this live suite"
        )
    if credential_missing(runtime):
        return (
            f"{runtime.worker_name}: {runtime.credential_label} is not "
            "configured -- set it to run this live suite"
        )
    return None
