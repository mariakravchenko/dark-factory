"""Pure-tier proof of the quality gate's PASS/FAIL fold, run-all-commands
ordering, argv splitting and redaction (Phase 9, plan 09-01, Task 1).

Every scenario drives real child processes via the current interpreter
(``sys.executable -c ...``) in a ``tmp_path`` cwd -- sub-second, no database,
and a real proof of the argv-splitting / no-shell-interpretation contract
rather than a stub standing in for it.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from dark_factory.domain.status import VerdictStatus
from dark_factory.orchestrator.quality_gate import (
    _MAX_CAPTURED_OUTPUT_BYTES,
    GateCommandResult,
    QualityGateResult,
    run_quality_gate,
    write_quality_gate_result,
)

pytestmark = pytest.mark.unit


def _py(*args: str) -> str:
    """A configured ``quality_gate.commands`` entry that invokes the current
    interpreter -- built with :func:`shlex.join` so it round-trips exactly
    through :func:`shlex.split` inside :func:`run_quality_gate`, the same
    way a real ``.dark-factory.yaml`` ``commands:`` string does."""
    return shlex.join([sys.executable, *args])


def test_two_passing_commands_yield_pass_with_two_entries_in_order(
    tmp_path: Path,
) -> None:
    first = _py("-c", "print('first')")
    second = _py("-c", "print('second')")

    result = run_quality_gate(
        commands=[first, second], cwd=tmp_path, timeout=30, known_secrets={}
    )

    assert result.status is VerdictStatus.PASS
    assert [c.command for c in result.commands] == [first, second]
    assert all(c.exit_code == 0 for c in result.commands)


def test_a_failing_first_command_does_not_stop_the_second_and_yields_fail(
    tmp_path: Path,
) -> None:
    failing = _py("-c", "import sys; sys.exit(1)")
    passing = _py("-c", "pass")

    result = run_quality_gate(
        commands=[failing, passing], cwd=tmp_path, timeout=30, known_secrets={}
    )

    assert result.status is VerdictStatus.FAIL
    assert len(result.commands) == 2  # D-09: the second command still ran
    assert result.commands[0].exit_code == 1
    assert result.commands[1].exit_code == 0


def test_an_empty_command_list_is_a_vacuous_pass(tmp_path: Path) -> None:
    result = run_quality_gate(commands=[], cwd=tmp_path, timeout=30, known_secrets={})

    assert result.status is VerdictStatus.PASS
    assert result.commands == []


def test_a_configured_command_with_spaces_splits_into_separate_argv_elements(
    tmp_path: Path,
) -> None:
    command = _py("-c", "import sys; print(len(sys.argv) - 1)", "one", "two", "three")

    result = run_quality_gate(
        commands=[command], cwd=tmp_path, timeout=30, known_secrets={}
    )

    assert result.commands[0].exit_code == 0
    assert result.commands[0].stdout.strip() == "3"


def test_a_shell_metacharacter_reaches_the_child_as_one_inert_argument(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "should_not_exist.txt"
    malicious_arg = f"foo; touch {sentinel}"
    command = _py("-c", "import sys; print(sys.argv[1])", malicious_arg)

    result = run_quality_gate(
        commands=[command], cwd=tmp_path, timeout=30, known_secrets={}
    )

    assert result.commands[0].exit_code == 0
    assert result.commands[0].stdout.strip() == malicious_arg
    assert not sentinel.exists()


def test_a_timed_out_command_yields_no_exit_code_and_fails_the_gate(
    tmp_path: Path,
) -> None:
    command = _py("-c", "import time; time.sleep(30)")

    result = run_quality_gate(
        commands=[command], cwd=tmp_path, timeout=1, known_secrets={}
    )

    assert result.commands[0].exit_code is None
    assert result.commands[0].timed_out is True
    assert result.status is VerdictStatus.FAIL


def test_a_known_secret_value_in_stdout_is_redacted(tmp_path: Path) -> None:
    secret = "supersecretvalue123"
    command = _py("-c", f"print({secret!r})")

    result = run_quality_gate(
        commands=[command],
        cwd=tmp_path,
        timeout=30,
        known_secrets={secret: "test_secret"},
    )

    assert secret not in result.commands[0].stdout
    assert "[redacted:test_secret]" in result.commands[0].stdout


def test_stdout_over_the_cap_is_tail_preserved_with_an_explicit_drop_marker(
    tmp_path: Path,
) -> None:
    total_chars = _MAX_CAPTURED_OUTPUT_BYTES + 4000
    command = _py("-c", f"import sys; sys.stdout.write('x' * {total_chars})")

    result = run_quality_gate(
        commands=[command], cwd=tmp_path, timeout=30, known_secrets={}
    )

    stdout = result.commands[0].stdout
    assert len(stdout.encode("utf-8")) <= _MAX_CAPTURED_OUTPUT_BYTES
    first_line, _, body = stdout.partition("\n")
    assert "dropped" in first_line
    assert body  # the retained tail is non-empty
    assert body == "x" * len(body)  # the retained body is a suffix of the original


def test_quality_gate_result_cannot_be_constructed_with_an_explicit_status() -> None:
    with pytest.raises(ValidationError):
        QualityGateResult(commands=[], status="PASS")  # type: ignore[call-arg]


def test_quality_gate_result_status_key_order_is_commands_then_status() -> None:
    import json

    result = QualityGateResult(commands=[])
    assert list(json.loads(result.model_dump_json()).keys()) == ["commands", "status"]


def test_gate_command_result_is_frozen_and_forbids_extra_fields() -> None:
    entry = GateCommandResult(
        command="true", exit_code=0, stdout="", stderr="", timed_out=False
    )
    with pytest.raises(ValidationError):
        GateCommandResult(
            command="true",
            exit_code=0,
            stdout="",
            stderr="",
            timed_out=False,
            extra_field="nope",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        entry.exit_code = 1  # type: ignore[misc]


def test_write_quality_gate_result_writes_under_verification(tmp_path: Path) -> None:
    from dark_factory.artifacts.paths import ensure_run_tree

    ensure_run_tree(tmp_path)
    result = QualityGateResult(
        commands=[
            GateCommandResult(
                command="true", exit_code=0, stdout="", stderr="", timed_out=False
            )
        ]
    )

    relative_path = write_quality_gate_result(tmp_path, result)

    assert relative_path == "verification/quality_gate.json"
    written = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert '"status":"PASS"' in written.replace(" ", "")
