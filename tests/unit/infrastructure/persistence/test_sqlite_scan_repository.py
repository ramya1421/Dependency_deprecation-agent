import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dda.domain.entities import (
    Claim,
    Dependency,
    Finding,
    MigrationPlan,
    RiskScore,
    Signal,
    UsageSite,
)
from dda.domain.value_objects import (
    Confidence,
    Ecosystem,
    EffortEstimate,
    Severity,
    SignalType,
)
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    MigrationRunner(conn).apply_all()
    return conn


def test_migrations_are_idempotent(connection: sqlite3.Connection) -> None:
    MigrationRunner(connection).apply_all()
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert [r[0] for r in rows] == ["0001_initial"]


def test_wal_and_foreign_keys_enabled(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_save_and_get_scan(connection: sqlite3.Connection) -> None:
    repo = SqliteScanRepository(connection)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)

    repo.save_scan("scan-1", "/repo", "running", started_at)

    scan = repo.get_scan("scan-1")
    assert scan is not None
    assert scan["repo_path"] == "/repo"
    assert scan["status"] == "running"
    assert repo.get_scan("missing") is None


def test_save_and_get_dependencies(connection: sqlite3.Connection) -> None:
    repo = SqliteScanRepository(connection)
    repo.save_scan("scan-1", "/repo", "running", datetime.now(UTC))
    dep = Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
        declared_spec=">=2.0",
        resolved_version="2.3.0",
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )

    repo.save_dependencies("scan-1", [dep])

    assert repo.get_dependencies("scan-1") == [dep]


def test_save_and_get_findings_round_trip(connection: sqlite3.Connection) -> None:
    repo = SqliteScanRepository(connection)
    repo.save_scan("scan-1", "/repo", "running", datetime.now(UTC))
    dep = Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
        declared_spec=">=2.0",
        resolved_version="2.3.0",
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )
    repo.save_dependencies("scan-1", [dep])

    signal = Signal(
        source="pypi",
        signal_type=SignalType.DEPRECATED,
        severity=Severity.HIGH,
        payload={"reason": "superseded"},
        fetched_at=datetime.now(UTC),
    )
    repo.save_signals("flask", [signal])

    usage_site = UsageSite(
        package="flask",
        symbol="Flask",
        file_path=Path("app.py"),
        line_number=10,
        column_number=4,
        usage_kind="call",
        confidence=Confidence.STATIC_CONFIRMED,
        snippet="app = Flask(__name__)",
    )
    repo.save_usage_sites("scan-1", [usage_site])

    claim = Claim(text="No change needed.", chunk_id="c1", verified=True, entailment_score=0.9)
    plan = MigrationPlan(
        package="flask",
        summary="Bump to 2.3.0",
        steps=["Update requirements.txt"],
        claims=[claim],
        usage_sites=[usage_site],
        effort=EffortEstimate.SMALL,
    )
    risk_score = RiskScore(total=30.0, components={"deprecation": 30.0}, rationale=["dep"])
    finding = Finding(
        dependency=dep,
        risk_score=risk_score,
        signals=[signal],
        usage_sites=[usage_site],
        migration_plan=plan,
    )

    repo.save_findings("scan-1", [finding])
    [loaded] = repo.get_findings("scan-1")

    assert loaded.dependency == dep
    assert loaded.risk_score == risk_score
    assert loaded.signals == [signal]
    assert loaded.usage_sites == [usage_site]
    assert loaded.migration_plan == plan

    citations = connection.execute("SELECT chunk_id FROM citations").fetchall()
    assert [c[0] for c in citations] == ["c1"]


def test_save_findings_without_migration_plan(connection: sqlite3.Connection) -> None:
    repo = SqliteScanRepository(connection)
    repo.save_scan("scan-1", "/repo", "running", datetime.now(UTC))
    dep = Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
        declared_spec=">=2.0",
        resolved_version=None,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )
    repo.save_dependencies("scan-1", [dep])
    risk_score = RiskScore(total=0.0, components={}, rationale=[])
    finding = Finding(
        dependency=dep, risk_score=risk_score, signals=[], usage_sites=[], migration_plan=None
    )

    repo.save_findings("scan-1", [finding])
    [loaded] = repo.get_findings("scan-1")

    assert loaded.migration_plan is None
