"""Ensures the schema exists before any integration test runs. On a fresh
database (e.g. the empty Postgres service container in CI, which has no NHS
data loaded), `_skip_if_no_data()` needs the tables to exist to query them at
all - without this, every test fails with "relation does not exist" instead
of skipping gracefully.
"""

import pytest

from llm_project.db.models import init_db


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    init_db()
