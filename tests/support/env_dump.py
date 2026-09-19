"""Standalone environment-dump child script (D-10).

No import from the orchestrator package and no third-party import: this
file is spawned as a real, independent OS process by
``tests/integration/test_worker_env_boundary.py`` with a deliberately
narrow environment built by ``build_worker_env()`` -- one that lacks
PYTHONPATH and VIRTUAL_ENV on purpose, so anything this script needed to
import from outside the standard library might not resolve. Keeping it
dependency-free is the point: it exists to answer exactly one question --
what does a process spawned with ``build_worker_env()``'s output actually
see in its own environment -- and an in-process assertion cannot answer
that question, because it shares the parent's already-populated
``os.environ`` instead of what a genuinely separate process received at
spawn time.

Writes its complete ``os.environ`` mapping to stdout as JSON and exits 0.
Materialising the whole environment is correct *here* and only here: this
file is the observer, not the builder, and it lives under ``tests/`` so it
is outside the ``src/`` tree the wholesale-copy guard walks.
"""

from __future__ import annotations

import json
import os
import sys

if __name__ == "__main__":
    json.dump(dict(os.environ), sys.stdout)
