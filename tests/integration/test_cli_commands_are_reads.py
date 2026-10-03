"""Every ``@app.command()`` body in ``cli.py`` is read, not orchestration
(Plan 12-01, Task 2, OBS-03) -- the generalisation of
``tests/integration/test_status_cli.py``'s
``test_status_command_body_carries_no_lifecycle_logic`` to every command the
module declares, present and future.

A command that compares a value to a ``RunStatus`` enum member to decide
what to do next is doing the orchestrator's job -- that decision belongs to
``dark_factory.orchestrator.lifecycle.transition``, never a CLI command
body. This guard walks every ``@app.command()``-decorated function in
``cli.py`` and asserts none of them contains such a comparison.

``tests/integration/test_status_cli.py``'s own
``test_status_command_body_carries_no_lifecycle_logic`` stays in place
unchanged -- it additionally pins that ``status`` sources its data from
``read_status``, which this generalised guard does not check.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SRC = _REPO_ROOT / "src" / "dark_factory" / "cli.py"

# Non-vacuity baseline (acceptance criterion): a matcher that discovers zero
# commands must fail loudly rather than pass silently.
_BASELINE_COMMAND_NAMES = frozenset({"run", "resume", "status", "events"})


def _discover_command_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Every top-level function decorated ``@app.command()`` or
    ``@app.command`` -- matched by the decorator's attribute name so both
    the called and bare forms are found, keyed by function name."""
    commands: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(target, ast.Attribute) and target.attr == "command":
                commands[node.name] = node
                break
    return commands


def _compares_to_run_status(node: ast.FunctionDef) -> bool:
    """``True`` iff any comparison inside ``node`` has a ``RunStatus.<MEMBER>``
    attribute access as an operand -- e.g. ``if status == RunStatus.FAILED``.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Compare):
            continue
        for operand in (sub.left, *sub.comparators):
            if (
                isinstance(operand, ast.Attribute)
                and isinstance(operand.value, ast.Name)
                and operand.value.id == "RunStatus"
            ):
                return True
    return False


def test_every_command_body_avoids_a_run_status_comparison() -> None:
    source = _CLI_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_CLI_SRC))

    commands = _discover_command_functions(tree)

    # Non-vacuity: a broken decorator matcher that finds nothing must fail
    # loudly, not pass trivially.
    assert commands, "discovered zero @app.command() functions in cli.py"
    assert commands.keys() >= _BASELINE_COMMAND_NAMES, (
        f"expected at least {sorted(_BASELINE_COMMAND_NAMES)} among discovered "
        f"commands, found {sorted(commands)}"
    )

    offenders = [
        name for name, node in commands.items() if _compares_to_run_status(node)
    ]
    assert not offenders, (
        f"the following @app.command() bodies compare a value to a RunStatus "
        f"member -- that decision belongs to the orchestrator, not a CLI "
        f"command: {offenders}"
    )


def test_the_guard_detects_its_own_subject() -> None:
    """Self-detection: the discovery + comparison checks above are only
    meaningful if they actually surface a violation when one exists. Run
    both over an inline counterexample containing a command function that
    DOES compare the enum, and confirm the guard would have caught it --
    the same non-vacuity discipline
    ``tests/integration/test_redaction_interactions.py`` already uses."""
    counterexample_src = (
        "import typer\n"
        "from dark_factory.domain.status import RunStatus\n"
        "\n"
        "app = typer.Typer()\n"
        "\n"
        "\n"
        "@app.command()\n"
        "def fake_offender(run_id: str) -> None:\n"
        "    status = read_status(run_id)\n"
        "    if status == RunStatus.FAILED:\n"
        "        do_the_orchestrators_job()\n"
    )
    tree = ast.parse(counterexample_src)

    commands = _discover_command_functions(tree)
    assert "fake_offender" in commands, (
        "the decorator matcher failed to discover the counterexample's "
        "@app.command() function"
    )

    assert _compares_to_run_status(commands["fake_offender"]), (
        "the comparison check failed to surface the counterexample's "
        "RunStatus comparison"
    )
