"""The minimal effective-config snapshot the Phase 1 / Phase 2 in-process
``start_run`` call sites pass.

Since 03-03, ``start_run`` requires a resolved ``snapshot`` -- there is no
``DEFAULT_PIPELINE`` default any more. The Phase 1 / Phase 2 db and integration
tests assert run status, events and lease behaviour, not ``runs.workflow``
contents, so they pass this one shared constant: the legacy bare-string
``{"roles": ["BA"]}`` shape, which ``pipeline_from_snapshot`` maps to a single
``RoleNode(name="BA", worker="fake")`` -- identical to the old
``DEFAULT_PIPELINE`` those tests used to get by default.
"""

from __future__ import annotations

__all__ = ["DEFAULT_TEST_SNAPSHOT"]

DEFAULT_TEST_SNAPSHOT: dict[str, object] = {"roles": ["BA"]}
