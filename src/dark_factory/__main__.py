"""``python -m dark_factory`` entry point.

Plan 07's fresh-process resume test spawns the orchestrator this way, so the
module entry point must exist and simply hand off to the Typer app.
"""

from dark_factory.cli import app

if __name__ == "__main__":
    app()
