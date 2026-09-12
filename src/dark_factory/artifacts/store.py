"""Artifact content read/write (ART-01, ART-02, T-04-02, T-04-03).

Neither function here opens a ``Session`` or constructs an ORM row -- this
module is pure filesystem I/O. Callers in
:mod:`dark_factory.artifacts.validation` and :mod:`dark_factory.context.builder`
turn the return values into :class:`~dark_factory.persistence.mutations.ArtifactReferenceWrite`
/ :class:`~dark_factory.context.builder.ArtifactInput` respectively.
"""

from __future__ import annotations

from pathlib import Path

from dark_factory.artifacts.paths import (
    _MAX_ARTIFACT_BYTES,
    checksum,
    resolve_under_run_root,
)

__all__ = ["read_artifact_text", "write_artifact_text"]


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
    (:mod:`tests.support.fake_artifacts`) to write scripted artifact content;
    production code never fabricates artifact files.
    """
    relative_path = f"artifacts/{role}/{filename}"
    path = resolve_under_run_root(root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    return str(path.relative_to(root.resolve())), checksum(data)
