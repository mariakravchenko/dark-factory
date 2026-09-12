"""The artifact filesystem tier (ART-01, ART-02, ART-03).

Artifact **content** lives on disk under ``.dark-factory/runs/<run-id>/``; Neon
holds only :class:`~dark_factory.persistence.models.ArtifactReference`
metadata. This package is the one place that reads/writes artifact files and
resolves/validates their paths -- ``dark_factory.context`` and
``dark_factory.orchestrator`` call through it, never ``open()`` an artifact
path themselves.

Error hierarchy, in the ``ConfigError`` / ``ScriptExhaustedError`` register:
every artifact-tier failure is a named subclass of :class:`ArtifactError`
raised loudly, never a silent "artifact absent, continue".
"""

from __future__ import annotations

from dark_factory.artifacts.paths import (
    checksum,
    ensure_run_tree,
    resolve_under_run_root,
    role_artifact_dir,
    run_root,
)
from dark_factory.artifacts.store import read_artifact_text, write_artifact_text

__all__ = [
    "ArtifactContractError",
    "ArtifactError",
    "ArtifactPathError",
    "ArtifactSchemaError",
    "ArtifactTooLargeError",
    "MissingArtifactContentError",
    "checksum",
    "ensure_run_tree",
    "read_artifact_text",
    "resolve_under_run_root",
    "role_artifact_dir",
    "run_root",
    "write_artifact_text",
]


class ArtifactError(RuntimeError):
    """Base class for every artifact-tier failure."""


class ArtifactPathError(ArtifactError):
    """Raised when an artifact path escapes the run root (T-04-01) -- a parent-
    directory traversal, an absolute path outside the root, or a symlink whose
    resolved target lands outside it."""


class ArtifactTooLargeError(ArtifactError):
    """Raised when an artifact file exceeds the size cap (T-04-02), checked
    before the content is parsed."""


class MissingArtifactContentError(ArtifactError):
    """Raised when a reported or referenced artifact's file is absent on disk
    (T-04-03) -- never treated as "no prior artifact"."""


class ArtifactContractError(ArtifactError):
    """Raised when a role's declared ``outputs`` / ``inputs`` filename has no
    matching reported reference, or no producing role in the snapshot."""


class ArtifactSchemaError(ArtifactError):
    """Raised when a machine artifact's JSON content fails
    :class:`pydantic.ValidationError` against its registered model (ART-02)."""
