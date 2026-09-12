"""Role context assembly (CTX-01..CTX-04).

The invariant this package exists to hold: context assembly performs only
**named-path reads** -- a role's declared ``inputs``, the fixed D-02 baseline
filenames, and the role's declared ``examples`` -- and never enumerates the
repository tree. No module under ``dark_factory.context`` lists, globs or
walks a directory, and no module here imports, evaluates or executes any
content it reads (CTX-02, CTX-03). :mod:`tests.unit.test_no_tree_walk`
enforces this mechanically.
"""

from __future__ import annotations

from dark_factory.context.builder import (
    BASELINE_DOC_FILENAMES,
    ArtifactInput,
    ExampleDoc,
    RoleContext,
    build_role_context,
)

__all__ = [
    "BASELINE_DOC_FILENAMES",
    "ArtifactInput",
    "ExampleDoc",
    "RoleContext",
    "build_role_context",
]
