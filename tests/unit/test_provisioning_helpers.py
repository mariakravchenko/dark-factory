"""Unit coverage for the pure helpers in the test provisioning ladder.

`_to_psycopg3_url` sits on the path between every provisioning rung and
`create_engine` — an externally supplied URL almost always arrives on the bare
`postgresql://` or legacy `postgres://` scheme and must be forced onto
`postgresql+psycopg://` (psycopg 3) before SQLAlchemy sees it.
"""

import pytest

from tests.conftest import _RUNG_LABELS, _to_psycopg3_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgres://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg2://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql://u:p@h/db?sslmode=require",
            "postgresql+psycopg://u:p@h/db?sslmode=require",
        ),
    ],
)
def test_to_psycopg3_url_forces_psycopg_v3_scheme(raw: str, expected: str) -> None:
    assert _to_psycopg3_url(raw) == expected


def test_to_psycopg3_url_leaves_non_postgres_urls_untouched() -> None:
    assert _to_psycopg3_url("mysql://u:p@h/db") == "mysql://u:p@h/db"


def test_every_rung_key_has_a_human_label() -> None:
    assert set(_RUNG_LABELS) == {
        "testcontainers",
        "pytest-postgresql",
        "external",
        "none",
    }
