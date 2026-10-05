"""Artifact content read/write (ART-01, ART-02, T-04-02, T-04-03).

Neither function here opens a ``Session`` or constructs an ORM row -- this
module is pure filesystem I/O. Callers in
:mod:`dark_factory.artifacts.validation` and :mod:`dark_factory.context.builder`
turn the return values into :class:`~dark_factory.persistence.mutations.ArtifactReferenceWrite`
/ :class:`~dark_factory.context.builder.ArtifactInput` respectively.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from dark_factory.artifacts.paths import (
    _MAX_ARTIFACT_BYTES,
    checksum,
    resolve_under_run_root,
)

__all__ = [
    "read_artifact_text",
    "scrub_artifact_text_in_place",
    "write_artifact_text",
]


def read_artifact_text(root: Path, relative_path: str) -> str:
    """Read ``relative_path`` under ``root`` as UTF-8 text.

    Resolves through :func:`resolve_under_run_root` first (T-04-01). Raises
    :class:`~dark_factory.artifacts.MissingArtifactContentError` naming the
    absolute path when the file is absent (T-04-03), and
    :class:`~dark_factory.artifacts.ArtifactTooLargeError` when the byte length
    exceeds :data:`~dark_factory.artifacts.paths._MAX_ARTIFACT_BYTES` --
    checked **before** any parsing, so an oversized malformed document never
    reaches a JSON parser or a pydantic validator (T-04-02).
    """
    from dark_factory.artifacts import (
        ArtifactTooLargeError,
        MissingArtifactContentError,
    )

    path = resolve_under_run_root(root, relative_path)
    if not path.is_file():
        raise MissingArtifactContentError(f"artifact file not found: {path}")
    data = path.read_bytes()
    if len(data) > _MAX_ARTIFACT_BYTES:
        raise ArtifactTooLargeError(
            f"{path}: artifact exceeds {_MAX_ARTIFACT_BYTES} bytes ({len(data)} bytes)"
        )
    return data.decode("utf-8")


def write_artifact_text(
    root: Path, role: str, filename: str, text: str
) -> tuple[str, str]:
    """Write ``text`` to ``<root>/artifacts/<role>/<filename>``.

    Returns ``(run-root-relative path, checksum)``. Used by test scaffolding
    (:mod:`tests.support.fake_artifacts`) to write scripted artifact content,
    and by :class:`~dark_factory.workers.fake.FakeWorker`'s true no-script
    default (CR-01, 04-REVIEW) to synthesize minimal schema-valid files for a
    role's declared outputs when no explicit script is provided. A real
    agent-runtime adapter writes its own artifact files directly and never
    calls this helper.
    """
    relative_path = f"artifacts/{role}/{filename}"
    path = resolve_under_run_root(root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    return str(path.relative_to(root.resolve())), checksum(data)


def scrub_artifact_text_in_place(
    root: Path, relative_path: str, *, known_secrets: Mapping[str, str]
) -> None:
    """Rewrite the artifact file at ``relative_path`` under ``root`` through
    ``redact()``, using ``known_secrets`` (Plan 12-07, T-12-24, SEC-01/SEC-02).

    Mirrors :func:`dark_factory.workers.cli_runtime.scrub_log_in_place`'s
    rationale, applied to a role's own *reported artifact file* rather than
    its captured CLI transcript: once
    :func:`~dark_factory.git.diff.commit_run_artifacts` force-adds and
    commits this file onto the run's working branch -- which becomes the PR
    branch -- nothing downstream ever re-scrubs it. Before this function
    existed, a credential a role's own output happened to echo (e.g. one
    copied verbatim from a task description into a generated document) would
    reach a permanent, external PR diff with no scrubbing step anywhere in
    the pipeline -- every other sink (events, role-execution columns,
    comments, logs, the quality-gate command string) already had one.

    Called from ``orchestrator/runner.py`` **before**
    :func:`~dark_factory.artifacts.validation.collect_role_artifacts` reads
    the same file for schema validation and checksum computation, so the
    checksum persisted in ``artifacts.checksum`` and the content eventually
    committed always agree -- never a checksum computed over one version of
    the text and a commit carrying another.

    A missing file is a no-op, not an error -- mirrors
    :func:`~dark_factory.workers.cli_runtime.scrub_log_in_place`'s identical
    posture for the same reason (a role whose artifact write failed upstream
    has nothing here to scrub). Rewrites the file only when redaction
    actually changed something, so an already-clean file's mtime is left
    alone.
    """
    from dark_factory.events.redaction import redact

    path = resolve_under_run_root(root, relative_path)
    if not path.is_file():
        return
    raw = path.read_text("utf-8", errors="replace")
    scrubbed = redact(raw, known_secrets=known_secrets)
    if scrubbed != raw:
        path.write_text(scrubbed, encoding="utf-8")
