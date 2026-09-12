"""Run-tree path resolution, the checksum primitive, and the T-04-01 path-
safety guard (ART-01).

Every function here names exactly one path. Nothing in this module lists,
globs or walks a directory (CTX-02's invariant extends to this package).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

__all__ = [
    "checksum",
    "ensure_run_tree",
    "resolve_under_run_root",
    "role_artifact_dir",
    "run_root",
]

# The cap a single artifact file may occupy on disk (T-04-02). Mirrors the
# ``_MAX_INSTRUCTION_BYTES`` idiom in ``config/loader.py``.
_MAX_ARTIFACT_BYTES = 256 * 1024


def run_root(repo_root: Path, run_id: UUID) -> Path:
    """The per-run directory: ``<repo_root>/.dark-factory/runs/<run_id>/``."""
    return repo_root / ".dark-factory" / "runs" / str(run_id)


def ensure_run_tree(root: Path) -> None:
    """Create ``input/``, ``artifacts/``, ``verification/`` and ``logs/`` under
    ``root``, with parents, idempotently. Re-running on an existing tree is not
    an error (ART-01)."""
    for child in ("input", "artifacts", "verification", "logs"):
        (root / child).mkdir(parents=True, exist_ok=True)


def role_artifact_dir(root: Path, role: str) -> Path:
    """``<root>/artifacts/<role>/``, created if absent."""
    path = root / "artifacts" / role
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_under_run_root(root: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` against ``root`` and reject any escape (T-04-01).

    Rejects an absolute ``relative_path``, a ``..`` parent-directory escape, and
    a symlink whose resolved target lands outside ``root`` -- uniformly, by
    resolving the candidate and requiring the result to satisfy
    ``Path.is_relative_to(root)``. A rejected path always raises
    :class:`~dark_factory.artifacts.ArtifactPathError`; it is never silently
    clamped back inside the root.
    """
    from dark_factory.artifacts import ArtifactPathError

    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ArtifactPathError(
            f"artifact path escapes run root {resolved_root}: {relative_path!r} "
            f"resolved to {candidate}"
        )
    return candidate


def checksum(data: bytes) -> str:
    """The SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()
