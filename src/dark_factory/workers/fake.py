"""``FakeWorker`` -- a scripted :class:`CodingWorker` with no external AI call (WORK-10).

This is shipped package code, not a test fixture: WORK-10 names it as a
deliverable and Phases 7-8 reuse it in the shared contract suite. It resolves its
script in this order:

1. the explicit ``script`` argument (an empty list is honoured -- it is not a
   missing script, so it exhausts immediately);
2. a JSON array in ``DARK_FACTORY_FAKE_SCRIPT``, each element validated through
   ``WorkerResult.model_validate`` -- how the subprocess-level tests in Plans 05
   and 06 drive the failure arm across a process boundary;
3. the D-10 default -- a single COMPLETED result with a ``fake-<uuid>`` session id.
"""

import json
import os
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


class FakeWorker(CodingWorker):
    """Returns a fixed sequence of :class:`WorkerResult`s, one per ``execute()`` call."""

    def __init__(self, script: Sequence[WorkerResult] | None = None) -> None:
        if script is not None:
            self._script: list[WorkerResult] = list(script)
        else:
            from_env = _script_from_env()
            self._script = from_env if from_env is not None else _default_script()
        self._index = 0

    def execute(self, context: object) -> WorkerResult:
        if self._index >= len(self._script):
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
