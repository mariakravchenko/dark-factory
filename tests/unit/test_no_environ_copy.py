"""Guard (T-01-07): no module copies the process environment wholesale.

Phase 1 spawns no worker subprocess, so this guards the *habit*, not a live leak.
By the time Phase 6 builds the explicit per-role env allowlist, a convenience
helper that did ``os.environ.copy()`` -- and would drag ``DATABASE_URL`` into a
worker process -- must not already exist. Reading individual keys
(``os.environ["PATH"]``, ``os.environ.get(...)``) is fine; only wholesale copies
are forbidden.
"""

import pathlib

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_FORBIDDEN_SNIPPETS = (
    "os.environ.copy(",
    "environ.copy(",
    "dict(os.environ)",
    "dict(environ)",
    "{**os.environ",
    "{**environ",
    "copy.copy(os.environ",
    "copy.deepcopy(os.environ",
    "dict(**os.environ",
)


def _strip_comment(line: str) -> str:
    marker = line.find("#")
    return line if marker == -1 else line[:marker]


def test_no_module_copies_the_process_environment_wholesale() -> None:
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            collapsed = _strip_comment(raw).replace(" ", "")
            for snippet in _FORBIDDEN_SNIPPETS:
                if snippet.replace(" ", "") in collapsed:
                    offenders.append(f"{path}:{lineno}: {raw.strip()!r}")
    assert not offenders, "wholesale process-environment copy found:\n" + "\n".join(
        offenders
    )
