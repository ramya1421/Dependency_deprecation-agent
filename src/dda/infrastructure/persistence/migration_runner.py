import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationRunner:
    def __init__(
        self, connection: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR
    ) -> None:
        self._connection = connection
        self._migrations_dir = migrations_dir

    def apply_all(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"
        )
        applied = {
            row[0]
            for row in self._connection.execute("SELECT version FROM schema_migrations")
        }
        for path in sorted(self._migrations_dir.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            self._connection.executescript(path.read_text(encoding="utf-8"))
            self._connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
        self._connection.commit()
