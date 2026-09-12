"""``FakeWorker`` -- a scripted :class:`CodingWorker` with no external AI call (WORK-10).

This is shipped package code, not a test fixture: WORK-10 names it as a
deliverable and Phases 7-8 reuse it in the shared contract suite. It resolves its
script in this order:

1. the explicit ``script`` argument (an empty list is honoured -- it is not a
   missing script, so it exhausts immediately);
2. a JSON array in ``DARK_FACTORY_FAKE_SCRIPT``, each element validated through
   ``WorkerResult.model_validate`` -- how the subprocess-level tests in Plans 05
   and 06 drive the failure arm across a process boundary;
3. the D-10 default -- a COMPLETED result with a fresh ``fake-<uuid>`` session
   id **on every call**, never exhausting. Phase 4 ships a multi-role pipeline
   (``.dark-factory.yaml``'s ``workflow.roles``), and an operator running
   ``dark-factory run ...`` with no ``DARK_FACTORY_FAKE_SCRIPT`` must be able to
   drive every role to completion with no explicit script -- an *explicit*
   script (argument or env), including an explicit empty one, still exhausts
   exactly as documented below; only the true no-script default is unbounded.

Test-only knob (alongside ``DARK_FACTORY_FAKE_SCRIPT``):
``DARK_FACTORY_FAKE_SLEEP_MS`` makes ``execute()`` deliberately slow, so a step
can be produced that outlives a short injected lease TTL (the heartbeat and race
proofs). It is read from the environment on every ``execute()`` call, never
cached at import, so it is inert on an ordinary run and a test can arm it for a
single subprocess. The explicit ``sleep_ms`` constructor argument takes
precedence over it. A malformed value raises rather than being silently ignored.
``resume()`` inherits the delay because it delegates to ``execute()``.
"""

import json
import os
import time
from collections.abc import Sequence
from uuid import uuid4

from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.workers.base import CodingWorker

__all__ = ["FakeWorker", "ScriptExhaustedError"]

_SCRIPT_ENV_VAR = "DARK_FACTORY_FAKE_SCRIPT"
_SLEEP_MS_ENV_VAR = "DARK_FACTORY_FAKE_SLEEP_MS"


class ScriptExhaustedError(RuntimeError):
    """Raised when ``execute()`` is called with no scripted result left to return."""


def _default_script() -> list[WorkerResult]:
    return [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            worker_session_id=f"fake-{uuid4()}",
        )
    ]


def _script_from_env() -> list[WorkerResult] | None:
    raw = os.environ.get(_SCRIPT_ENV_VAR)
    if raw is None:
        return None
    return [WorkerResult.model_validate(item) for item in json.loads(raw)]


def _resolve_sleep_ms(explicit: int | None) -> int | None:
    """The delay for one ``execute()`` call: the constructor argument if given,
    otherwise ``DARK_FACTORY_FAKE_SLEEP_MS`` parsed as an integer if set,
    otherwise ``None`` (no delay). Read at call time, never cached at import."""
    if explicit is not None:
        return explicit
    raw = os.environ.get(_SLEEP_MS_ENV_VAR)
    if raw is None:
        return None
    return int(raw)  # a malformed value raises ValueError -- fail loudly


class FakeWorker(CodingWorker):
    """Returns a fixed sequence of :class:`WorkerResult`s, one per ``execute()`` call."""

    def __init__(
        self,
        script: Sequence[WorkerResult] | None = None,
        *,
        sleep_ms: int | None = None,
    ) -> None:
        if script is not None:
            self._script: list[WorkerResult] = list(script)
            self._is_default = False
        else:
            from_env = _script_from_env()
            if from_env is not None:
                self._script = from_env
                self._is_default = False
            else:
                self._script = _default_script()
                self._is_default = True
        self._index = 0
        self._sleep_ms = sleep_ms

    def execute(self, context: object) -> WorkerResult:
        delay_ms = _resolve_sleep_ms(self._sleep_ms)
        if delay_ms is not None and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if self._index >= len(self._script):
            if self._is_default:
                # The true no-script default never exhausts (see module
                # docstring) -- a fresh COMPLETED result every call, so a
                # shipped multi-role pipeline completes with no explicit
                # script. An explicit script/env, including an explicit
                # empty one, still exhausts below.
                return _default_script()[0]
            raise ScriptExhaustedError(
                f"FakeWorker script exhausted after {self._index} result(s)"
            )
        result = self._script[self._index]
        self._index += 1
        return result

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self.execute(context)

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )
