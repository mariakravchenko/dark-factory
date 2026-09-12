"""Test-only helper: write scripted artifact files under a run root and return
the :class:`~dark_factory.domain.worker.ArtifactRef` list to embed in that
role's scripted :class:`~dark_factory.domain.worker.WorkerResult`.

Kept in ``tests/support/``, not shipped ``src/`` (04-RESEARCH assumption A3):
the shipped :class:`~dark_factory.workers.fake.FakeWorker` stays exactly as
simple as it is -- it never writes files itself. A db test writes the files a
scripted result *claims* to have produced, then hands the resulting refs to
the ``FakeWorker`` script.
"""

from __future__ import annotations

from pathlib import Path

from dark_factory.artifacts.store import write_artifact_text
from dark_factory.domain.worker import ArtifactRef

__all__ = ["write_role_artifacts"]


def write_role_artifacts(
    root: Path, role: str, files: dict[str, str]
) -> list[ArtifactRef]:
    """Write each ``{filename: content}`` entry under ``<root>/artifacts/<role>/``
    and return one :class:`ArtifactRef` per file, in ``files`` iteration order.
    """
    refs: list[ArtifactRef] = []
    for filename, content in files.items():
        path, digest = write_artifact_text(root, role, filename, content)
        refs.append(ArtifactRef(type=filename, path=path, checksum=digest))
    return refs
