"""The one generator all three fake-CLI modules (``fake_claude_cli.py``,
``fake_copilot_cli.py``, ``fake_hermes_cli.py``) delegate to (08-04 Task 1).

Extracted from ``fake_claude_cli.py``/``fake_copilot_cli.py``, which were
identical module-for-module before this extraction: :func:`write_fake_cli`
writes a small, self-contained Python script named ``binary_name`` into a
directory and marks it executable. Prepending that directory to ``PATH`` is
enough for :func:`~dark_factory.tools.env.build_worker_env` to resolve the
bare command name to the fake script -- ``build_worker_env`` copies ``PATH``
from the parent process verbatim, and ``subprocess.Popen`` resolves a bare
command name against the ``PATH`` it is given.

Every configuration value (``stdout_payload``, ``exit_code``,
``sleep_seconds``, ``stderr_text``, the log paths, ``declared_outputs``) is
baked into the generated script source as a Python literal via ``repr()``. It
is deliberately never read back from the child's own environment at run
time, because :func:`~dark_factory.tools.env.build_worker_env` copies only
``WORKER_ENV_ALLOWLIST`` names -- a ``DARK_FACTORY_FAKE_*``-style env var
would be stripped before the child process ever saw it.

The generated script's shebang is the absolute path of the interpreter
running the tests (``sys.executable``), not a ``PATH``-resolved name:
``build_worker_env`` strips the Python-related environment names (no
``PYTHONPATH``, no ``VIRTUAL_ENV``), so interpreter identity is the only
reliable way to make ``import dark_factory`` work inside the generated
script's own ``declared_outputs`` step below.
"""

from __future__ import annotations

import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

__all__ = ["EXPECTED_OUTPUTS_HEADING", "OUTPUT_BULLET_RE", "write_fake_cli"]

_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

# The exact heading `cli_runtime.context_prompt_sections` emits ahead of a
# role's declared-outputs bullet list -- shared here so the producer
# (``context_prompt_sections``) and the parser (the generated script below)
# cannot drift on the literal string.
EXPECTED_OUTPUTS_HEADING = "## Expected outputs"

# The exact bullet shape `context_prompt_sections` emits per declared output
# filename: "- <filename> (write under <destination>)". Group 1 is the
# filename, group 2 is the destination directory (run-root-relative).
OUTPUT_BULLET_RE = re.compile(r"^- (\S+) \(write under (.+)\)$", re.MULTILINE)

# The declared-outputs step's own source, formatted into the generated
# script only when `declared_outputs=True` -- kept as a module-level
# template (not an f-string body inlined into `write_fake_cli`) so it reads
# as one coherent unit. `{expected_outputs_heading!r}` /
# `{output_bullet_pattern!r}` are substituted by `write_fake_cli`, baking the
# module-level constants above into the generated source as literals so the
# generated script has no import-time dependency on this module.
_DECLARED_OUTPUTS_STEP = """\
if declared_outputs:
    import glob
    import re as _re

    from dark_factory.workers.fake import (
        criterion_ids_from_text,
        synthesize_artifact_content,
    )

    _prompt = None
    for _arg in sys.argv[1:]:
        if expected_outputs_heading in _arg:
            _prompt = _arg
            break
    if _prompt is not None:
        _heading_index = _prompt.find(expected_outputs_heading)
        _section = _prompt[_heading_index:]
        _bullets = _re.findall(output_bullet_pattern, _section, _re.MULTILINE)
        if _bullets:
            _run_roots = sorted(glob.glob(os.path.join(".dark-factory", "runs", "*")))
            if _run_roots:
                _run_root = _run_roots[0]
                _criterion_ids = criterion_ids_from_text(_prompt)
                for _filename, _destination in _bullets:
                    _dest_dir = os.path.join(_run_root, _destination)
                    os.makedirs(_dest_dir, exist_ok=True)
                    _content = synthesize_artifact_content(_filename, _criterion_ids)
                    with open(
                        os.path.join(_dest_dir, _filename), "w", encoding="utf-8"
                    ) as _out_fh:
                        _out_fh.write(_content)
"""

# The run-root-writes step's own source, formatted into the generated
# script only when `run_root_writes` is given (plan 08-05, Task 1) -- the
# mechanism both the Hermes and Copilot negative proofs use to make a real
# adapter's real subprocess write outside its own artifact subtree.
# Deliberately self-contained (its own `glob` import) rather than sharing
# state with `_DECLARED_OUTPUTS_STEP` above, since either step may run
# without the other. Keys in `run_root_writes` are run-root-relative (the
# run id is not knowable when the fake script is written); a missing run
# root writes nothing and does not change the exit code, matching the
# declared-outputs step's own failure posture -- a fake that cannot locate
# its destination behaves like an agent that produced nothing, not like a
# crash.
_RUN_ROOT_WRITES_STEP = """\
if run_root_writes:
    import glob

    _write_run_roots = sorted(glob.glob(os.path.join(".dark-factory", "runs", "*")))
    if _write_run_roots:
        _write_run_root = _write_run_roots[0]
        for _write_rel_path, _write_content in run_root_writes.items():
            _write_target = os.path.join(_write_run_root, _write_rel_path)
            os.makedirs(os.path.dirname(_write_target), exist_ok=True)
            with open(_write_target, "w", encoding="utf-8") as _write_fh:
                _write_fh.write(_write_content)
"""


def write_fake_cli(
    directory: Path,
    binary_name: str,
    *,
    stdout_payload: str | bytes,
    exit_code: int = 0,
    sleep_seconds: float = 0.0,
    stderr_text: str = "",
    argv_log: Path | None = None,
    env_log: Path | None = None,
    declared_outputs: bool = False,
    run_root_writes: Mapping[str, str] | None = None,
) -> Path:
    """Write an executable ``binary_name`` script to ``directory``; return
    ``directory`` (the caller prepends it to ``PATH``).

    On invocation the generated script, in order:

    1. writes ``json.dumps(sys.argv)`` to ``argv_log`` when given;
    2. writes ``json.dumps(dict(os.environ))`` to ``env_log`` when given;
    3. sleeps for ``sleep_seconds`` when non-zero;
    4. when ``declared_outputs`` is true, performs the declared-outputs step
       (see module docstring) -- before writing stdout;
    5. when ``run_root_writes`` is given, performs the run-root-writes step
       (plan 08-05, Task 1) -- after the declared-outputs step, before
       writing stdout;
    6. writes ``stderr_text`` to stderr and flushes;
    7. writes ``stdout_payload`` to stdout (as raw bytes when
       ``stdout_payload`` is ``bytes`` -- how a test drives the non-UTF-8-byte
       case) and flushes;
    8. exits with ``exit_code``.

    The declared-outputs step, when armed, scans ``sys.argv`` for the single
    element containing :data:`EXPECTED_OUTPUTS_HEADING` (that element is the
    prompt, whichever flag preceded it, so this one generated step serves all
    three CLIs with no knowledge of their flag names), parses the bullets
    under that heading with :data:`OUTPUT_BULLET_RE`, locates the run root by
    globbing ``.dark-factory/runs/*`` relative to the process's own working
    directory, computes criterion ids by calling
    :func:`~dark_factory.workers.fake.criterion_ids_from_text` on the whole
    prompt string, and writes
    :func:`~dark_factory.workers.fake.synthesize_artifact_content` for each
    parsed bullet. A missing heading, a missing run root, or a zero-bullet
    parse writes nothing and does not change the exit code -- a fake that
    cannot find its destination behaves like an agent that produced nothing,
    which the artifact-validation gate then reports as a contract error,
    rather than crashing with a traceback that would be read as an adapter
    bug.

    The run-root-writes step, when ``run_root_writes`` is a non-empty
    mapping, discovers the run root by the same ``.dark-factory/runs/*``
    glob the declared-outputs step already uses, and for each
    ``{relative_path: content}`` entry creates the parent directory and
    writes ``content`` to
    ``<run_root>/<relative_path>`` -- keys are run-root-relative because the
    run id is not knowable when the fake script is written. A missing run
    root writes nothing and does not change the exit code, matching the
    declared-outputs step's own failure posture. This is the mechanism both
    the Hermes and Copilot CR-01 negative proofs use to make a real
    adapter's real subprocess write into another role's artifact subtree.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / binary_name
    interpreter = sys.executable
    declared_outputs_step = _DECLARED_OUTPUTS_STEP if declared_outputs else ""
    run_root_writes_step = _RUN_ROOT_WRITES_STEP if run_root_writes else ""
    script = f"""#!{interpreter}
import json
import os
import sys
import time

argv_log = {(str(argv_log) if argv_log is not None else None)!r}
env_log = {(str(env_log) if env_log is not None else None)!r}
sleep_seconds = {sleep_seconds!r}
stderr_text = {stderr_text!r}
stdout_payload = {stdout_payload!r}
exit_code = {exit_code!r}
declared_outputs = {declared_outputs!r}
expected_outputs_heading = {EXPECTED_OUTPUTS_HEADING!r}
output_bullet_pattern = {OUTPUT_BULLET_RE.pattern!r}
run_root_writes = {dict(run_root_writes) if run_root_writes else None!r}

if argv_log:
    with open(argv_log, "w", encoding="utf-8") as fh:
        json.dump(sys.argv, fh)
if env_log:
    with open(env_log, "w", encoding="utf-8") as fh:
        json.dump(dict(os.environ), fh)
if sleep_seconds:
    time.sleep(sleep_seconds)
{declared_outputs_step}
{run_root_writes_step}
if stderr_text:
    sys.stderr.write(stderr_text)
    sys.stderr.flush()
if isinstance(stdout_payload, bytes):
    sys.stdout.buffer.write(stdout_payload)
else:
    sys.stdout.write(stdout_payload)
sys.stdout.flush()
sys.exit(exit_code)
"""
    script_path.write_text(script, encoding="utf-8")
    mode = script_path.stat().st_mode
    script_path.chmod(mode | _EXEC_BITS)
    return directory
