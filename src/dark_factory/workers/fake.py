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

   The true default is **artifact-aware** (CR-01): when the ``context`` handed
   to ``execute()``/``resume()`` exposes a non-empty ``outputs`` list (a
   :class:`~dark_factory.context.RoleContext`, as every real role attempt
   supplies), the default result synthesizes a minimal, schema-valid file for
   each declared output filename under the run's artifact tree
   (``<repo_root>/.dark-factory/runs/<run_id>/artifacts/<role>/``) and reports
   a matching :class:`~dark_factory.domain.worker.ArtifactRef` for each one --
   so the D-09 schema-validation gate in
   :func:`~dark_factory.artifacts.validation.collect_role_artifacts` is
   satisfied and a role completes rather than failing on "declared output
   with no matching artifact". This is what makes this repo's own shipped
   ``.dark-factory.yaml`` (BA -> ARCHITECTURE -> DEVELOPMENT -> QA, every role
   declaring machine-artifact outputs) driveable end to end by
   ``dark-factory run <source>`` with no explicit script -- see
   ``tests/integration/test_real_pipeline_zero_config.py``. When ``context``
   declares no outputs (including the bare ``None``/mock objects some unit
   tests pass as ``context``), the result reports no artifacts, exactly as the
   pre-CR-01 default did.

   The true default is now also **input-aware** (G-04-1): synthesis reads
   ``context.inputs`` -- the resolved upstream artifact content
   ``build_role_context`` already deposits there -- and extracts criterion ids
   from it via two strategies tried in order, stopping at the first that
   yields ids for a given input: (1) structural, parsing the input's content
   as :class:`~dark_factory.domain.artifacts.AcceptanceCriteriaDocument` and
   taking its criterion ids; (2) textual, scanning the raw content for a
   Markdown criterion-carrier line (``- Criterion <id> met``). When no input
   yields any id -- the BA role, which declares no ``inputs`` at all -- a
   single module-level origin-id constant is used, making BA the sole place a
   criterion id originates. Every synthesized document (JSON or Markdown) is
   then built from that id tuple rather than a second hardcoded literal, and
   every Markdown output carries its ids in the same machine-parseable
   carrier-line style so a role such as DEVELOPMENT -- whose declared
   ``inputs`` are ``design.md`` and ``constraints.json``, not
   ``acceptance_criteria.json`` -- still receives them through the Markdown
   hop.

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
import re
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from dark_factory.artifacts.paths import run_root
from dark_factory.artifacts.store import write_artifact_text
from dark_factory.domain.artifacts import (
    AcceptanceCriteriaDocument,
    AcceptanceCriterion,
    ConstraintItem,
    ConstraintsDocument,
    ImplementationSummary,
    TestCaseResult,
    TestReport,
    Verdict,
    VerdictCriterionResult,
)
from dark_factory.domain.status import VerdictStatus
from dark_factory.domain.worker import (
    ArtifactRef,
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.workers.base import CodingWorker

__all__ = ["FakeWorker", "ScriptExhaustedError"]

_SCRIPT_ENV_VAR = "DARK_FACTORY_FAKE_SCRIPT"
_SLEEP_MS_ENV_VAR = "DARK_FACTORY_FAKE_SLEEP_MS"

# G-04-1: the single place a criterion id originates when a role received no
# id-bearing input at all -- the BA shape (empty ``inputs``). Every other
# synthesized document derives its ids from this constant or from extraction,
# never from a second independent literal. Module-level (not a local/default
# argument) so a test can ``monkeypatch.setattr`` it -- the falsification
# case this whole fix exists to satisfy.
_ORIGIN_CRITERION_IDS: tuple[str, ...] = ("AC-1",)

# The Markdown criterion-carrier line D-07 already licenses ("Criterion AC-1
# met"), anchored to a full line so a JSON document's prose never accidentally
# matches it. Captures one whitespace-free token as the id.
_CRITERION_LINE_RE = re.compile(r"^- Criterion (\S+) met$", re.MULTILINE)

# T-04-21: bounds how many criterion ids one synthesis call will use,
# regardless of how many criteria/carrier lines an upstream input declares.
_MAX_CRITERION_IDS = 20

# T-04-19: a candidate id must be a single whitespace-free token of at most
# this many characters to be accepted -- bounds what upstream artifact
# content can inject into a downstream artifact.
_MAX_CRITERION_ID_LENGTH = 64


class ScriptExhaustedError(RuntimeError):
    """Raised when ``execute()`` is called with no scripted result left to return."""


def _is_valid_criterion_id(candidate: str) -> bool:
    """T-04-19's two safety filters: a single whitespace-free token of at
    most :data:`_MAX_CRITERION_ID_LENGTH` characters."""
    return (
        bool(candidate)
        and not any(character.isspace() for character in candidate)
        and len(candidate) <= _MAX_CRITERION_ID_LENGTH
    )


def _structural_criterion_ids(content: str) -> tuple[str, ...] | None:
    """Strategy 1: parse ``content`` as an
    :class:`~dark_factory.domain.artifacts.AcceptanceCriteriaDocument` and
    return its criterion ids in document order.

    Returns ``None`` (not an empty tuple -- that would be indistinguishable
    from "parsed but declared zero ids", which the model's own
    ``min_length=1`` already rules out) when ``content`` is not a valid
    document, so the caller falls through to the textual strategy. Pydantic
    v2 reports malformed JSON as a :class:`~pydantic.ValidationError` too, so
    this one ``except`` clause covers both non-JSON and wrong-shape input.
    """
    try:
        document = AcceptanceCriteriaDocument.model_validate_json(content)
    except ValidationError:
        return None
    return tuple(criterion.id for criterion in document.criteria)


def _textual_criterion_ids(content: str) -> tuple[str, ...]:
    """Strategy 2: scan ``content`` for the Markdown criterion-carrier line
    (``- Criterion <id> met``) -- how an id survives the hop through a
    Markdown artifact such as ``design.md`` into a role (e.g. DEVELOPMENT)
    whose declared ``inputs`` do not include ``acceptance_criteria.json``."""
    return tuple(_CRITERION_LINE_RE.findall(content))


def _extract_criterion_ids(inputs: Iterable[object] | None) -> tuple[str, ...]:
    """The role-agnostic G-04-1 extraction: an ordered, de-duplicated tuple
    of criterion ids found across ``inputs`` (a role's resolved upstream
    artifact content), or :data:`_ORIGIN_CRITERION_IDS` when none is found.

    ``inputs`` is read defensively (iterated as-is, tolerating ``None``/an
    empty sequence) matching the existing ``_default_script`` idiom. Each
    input's ``content`` attribute is read via ``getattr`` and skipped unless
    it is a string. Dispatch across strategies is on the content's shape
    only -- never on ``context.role`` and never a filesystem read -- so this
    function stays D-08/CTX-02 compliant regardless of caller.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for item in inputs or ():
        content = getattr(item, "content", None)
        if not isinstance(content, str):
            continue
        candidates = _structural_criterion_ids(content)
        if candidates is None:
            candidates = _textual_criterion_ids(content)
        for candidate in candidates:
            if not _is_valid_criterion_id(candidate) or candidate in seen:
                continue
            seen.add(candidate)
            ids.append(candidate)

    if not ids:
        return _ORIGIN_CRITERION_IDS
    return tuple(ids[:_MAX_CRITERION_IDS])


def _synthesize_machine_artifact(
    filename: str, criterion_ids: tuple[str, ...]
) -> str | None:
    """A minimal, schema-valid JSON document for ``filename``, built through
    the same pydantic models
    :func:`~dark_factory.artifacts.validation.collect_role_artifacts`
    validates a reported artifact against -- so a future schema change is
    automatically reflected here with no hand-maintained duplicate. Returns
    ``None`` for a filename that carries no JSON schema (Markdown
    documentation, e.g. ``requirements.md`` / ``design.md``).

    Dispatch is by filename only, mirroring
    ``artifacts/validation.py``'s ``MACHINE_ARTIFACT_MODELS`` table -- never a
    branch on which role produced it. Every id in every document below comes
    from ``criterion_ids`` (G-04-1) -- never a second independent literal.
    """
    if filename == "acceptance_criteria.json":
        return AcceptanceCriteriaDocument(
            criteria=[
                AcceptanceCriterion(
                    id=criterion_id,
                    description=f"acceptance criterion {criterion_id}",
                )
                for criterion_id in criterion_ids
            ]
        ).model_dump_json()
    if filename == "constraints.json":
        return ConstraintsDocument(
            constraints=[
                ConstraintItem(
                    id=f"C-{index}",
                    description=f"constraint covering criterion {criterion_id}",
                )
                for index, criterion_id in enumerate(criterion_ids, start=1)
            ]
        ).model_dump_json()
    if filename == "implementation_summary.json":
        joined_ids = ", ".join(criterion_ids)
        return ImplementationSummary(
            summary=f"implementation summary covering {joined_ids}",
        ).model_dump_json()
    if filename == "test_report.json":
        return TestReport(
            cases=[
                TestCaseResult(
                    name=f"verifies criterion {criterion_id}",
                    result=VerdictStatus.PASS,
                    detail="synthesized by FakeWorker's zero-config default",
                )
                for criterion_id in criterion_ids
            ]
        ).model_dump_json()
    if filename == "verdict.json":
        return Verdict(
            criteria=[
                VerdictCriterionResult(
                    criterion_id=criterion_id, result=VerdictStatus.PASS
                )
                for criterion_id in criterion_ids
            ],
            status=VerdictStatus.PASS,
        ).model_dump_json()
    return None


def _synthesize_artifact_content(filename: str, criterion_ids: tuple[str, ...]) -> str:
    """The file content written for one declared ``outputs`` filename: a
    schema-valid JSON document when ``filename`` is a D-10 machine artifact
    type, otherwise a minimal Markdown placeholder carrying one D-07-style
    criterion-carrier line per id (``- Criterion <id> met``) so a Markdown
    artifact round-trips its ids to the next role. Content stays
    non-task-aware throughout -- task-derived prose is Phase 7's scope."""
    machine_content = _synthesize_machine_artifact(filename, criterion_ids)
    if machine_content is not None:
        return machine_content
    carrier_lines = "\n".join(f"- Criterion {cid} met" for cid in criterion_ids)
    return f"# {filename}\n\nAuto-generated placeholder content.\n\n{carrier_lines}\n"


def _default_script(context: object) -> WorkerResult:
    """The D-10 true-default result (see module docstring): a fresh
    COMPLETED :class:`WorkerResult` with a new ``fake-<uuid>`` session id on
    every call.

    ``context`` is read defensively via ``getattr`` (never an ``isinstance``
    check against :class:`~dark_factory.context.RoleContext`) so a bare
    ``None`` or a test double with no ``outputs`` attribute degrades cleanly
    to the no-artifacts result rather than raising.
    """
    role = getattr(context, "role", None)
    run_id = getattr(context, "run_id", None)
    outputs = getattr(context, "outputs", None)

    if not outputs or not role or not run_id:
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            worker_session_id=f"fake-{uuid4()}",
        )

    criterion_ids = _extract_criterion_ids(getattr(context, "inputs", None))

    root = run_root(Path.cwd(), UUID(run_id))
    refs: list[ArtifactRef] = []
    for filename in outputs:
        content = _synthesize_artifact_content(filename, criterion_ids)
        path, digest = write_artifact_text(root, role, filename, content)
        refs.append(ArtifactRef(type=filename, path=path, checksum=digest))

    return WorkerResult(
        status=WorkerResultStatus.COMPLETED,
        summary=f"{role} completed with synthesized artifacts",
        worker_session_id=f"fake-{uuid4()}",
        artifacts=refs,
    )


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
                # No fixed list here (unlike the scripted branches): the true
                # default is regenerated fresh on every call from the
                # *current* ``context`` (see ``execute()`` below), because
                # CR-01's artifact synthesis depends on that call's declared
                # ``outputs`` -- something the constructor cannot see yet.
                self._script = []
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
                return _default_script(context)
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
