import sqlite3
from pathlib import Path

import pytest

from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    MigrationRunner(conn).apply_all()
    return conn
