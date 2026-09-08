"""Wave 0 smoke test: prove the provisioned database is a real PostgreSQL 17+.

Every durability claim in Plans 04-08 is only meaningful against the same engine
family Neon runs (PostgreSQL 17). Per an explicit human decision the exact-17
gate was loosened to a **17 floor**: the operator's throwaway test instance is
PostgreSQL 18.6, so major >= 17 is accepted. This is a deliberate deviation from
the plan's exact-17 gate and from CLAUDE.md's `postgres:17-alpine` pin — see
01-01-SUMMARY.md § Deviations; it is flagged for the phase verifier. This test
still fails loudly for anything below 17 (or a non-PostgreSQL engine).
"""

import re

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


def test_provisioned_postgres_reports_major_version_17_or_newer(db_session):
    version_string = db_session.execute(text("SELECT version()")).scalar_one()

    assert isinstance(version_string, str) and version_string
    match = re.match(r"PostgreSQL (\d+)", version_string)
    assert match is not None, f"unexpected version() output: {version_string!r}"
    assert int(match.group(1)) >= 17, (
        f"expected PostgreSQL 17 or newer, got: {version_string!r}"
    )

    # server_version_num is the unambiguous numeric form: >= 170000 == v17 floor.
    version_num = int(db_session.execute(text("SHOW server_version_num")).scalar_one())
    assert version_num >= 170000, version_num
