"""Filename -> artifact-model dispatch and the D-09 collection/validation gate
(ART-02, ART-03).

:func:`collect_role_artifacts` runs after a worker call returns
``COMPLETED`` and before the transition it produces is trusted: a role whose
declared ``outputs`` includes a machine filename that fails schema validation
must fail the attempt, not silently advance the run (ART-02, D-09).
Dispatch is always by **filename**, never by role name (config-driven,
no-role-name-branching discipline).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ValidationError

from dark_factory.artifacts import ArtifactContractError, ArtifactSchemaError
from dark_factory.artifacts.paths import checksum
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.domain.artifacts import AcceptanceCriteriaDocument
from dark_factory.domain.worker import ArtifactRef
from dark_factory.persistence.mutations import ArtifactReferenceWrite

__all__ = ["MACHINE_ARTIFACT_MODELS", "collect_role_artifacts"]

# filename -> pydantic model. Only ``acceptance_criteria.json`` is registered
# this phase (04-01); the remaining four artifact types are plan 04-02's scope.
MACHINE_ARTIFACT_MODELS: dict[str, type[BaseModel]] = {
    "acceptance_criteria.json": AcceptanceCriteriaDocument,
}


def collect_role_artifacts(
    root: Path,
    role: str,
    role_execution_id: UUID,
    declared_outputs: list[str],
    reported_refs: list[ArtifactRef],
) -> list[ArtifactReferenceWrite]:
    """Validate and collect one :class:`ArtifactReferenceWrite` per declared
    output filename.

    For every filename in ``declared_outputs``: find the reported
    :class:`~dark_factory.domain.worker.ArtifactRef` whose path basename
    matches, raising :class:`~dark_factory.artifacts.ArtifactContractError`
    when none does; read it through :func:`read_artifact_text` (T-04-02/03
    apply here); when the filename is a key of :data:`MACHINE_ARTIFACT_MODELS`,
    ``json.loads`` the text and validate it, converting a
    :class:`pydantic.ValidationError` into
    :class:`~dark_factory.artifacts.ArtifactSchemaError` naming the filename
    and the underlying message. Files not in :data:`MACHINE_ARTIFACT_MODELS`
    (Markdown documentation) get a reference row with no schema validation --
    the JSON contract is the authoritative one (ART-02).

    Returns the writes in ``declared_outputs`` order; no consumer may depend on
    that order (ART-03) -- artifact lookup is always by path/type, never row
    position.
    """
    by_basename = {Path(ref.path).name: ref for ref in reported_refs}
    writes: list[ArtifactReferenceWrite] = []

    for filename in declared_outputs:
        ref = by_basename.get(filename)
        if ref is None:
            raise ArtifactContractError(
                f"role {role!r} declares output {filename!r} but reported no "
                f"matching artifact"
            )

        text = read_artifact_text(root, ref.path)

        if filename in MACHINE_ARTIFACT_MODELS:
            model = MACHINE_ARTIFACT_MODELS[filename]
            try:
                model.model_validate(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ArtifactSchemaError(f"{filename}: not valid JSON: {exc}") from exc
            except ValidationError as exc:
                raise ArtifactSchemaError(f"{filename}: {exc}") from exc

        writes.append(
            ArtifactReferenceWrite(
                role_execution_id=role_execution_id,
                type=filename,
                path=ref.path,
                checksum=checksum(text.encode("utf-8")),
                metadata={},
            )
        )

    return writes
