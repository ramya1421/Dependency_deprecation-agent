import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.application.use_cases.scan_repository import ScanRepositoryUseCase
from dda.domain.entities import Dependency, Signal
from dda.domain.ports import IRepoFetcher, ISignalSource
from dda.domain.value_objects import Severity, SignalType
from dda.infrastructure.parsers.python_parser import PythonManifestParser
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository


class _PassthroughFetcher(IRepoFetcher):
    def fetch(self, repo_path_or_url: str) -> Path:
        return Path(repo_path_or_url)


class _StubSignalSource(ISignalSource):
    def __init__(self, flagged_package: str) -> None:
        self._flagged_package = flagged_package

    @property
    def source_name(self) -> str:
        return "stub"

    async def fetch(self, dependency: Dependency) -> list[Signal]:
        if dependency.name != self._flagged_package:
            return []
        return [
            Signal(
                source=self.source_name,
                signal_type=SignalType.DEPRECATED,
                severity=Severity.HIGH,
                payload={},
                fetched_at=datetime.now(UTC),
            )
        ]


def _use_case(connection: sqlite3.Connection, flagged_package: str) -> ScanRepositoryUseCase:
    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    return ScanRepositoryUseCase(
        repo_fetcher=_PassthroughFetcher(),
        parser_registry=registry,
        signal_collector=SignalCollector([_StubSignalSource(flagged_package)]),
        risk_scoring_service=RiskScoringService(),
        scan_repository=SqliteScanRepository(connection),
    )


async def test_execute_persists_dependencies_signals_and_scored_findings(
    tmp_path: Path, connection: sqlite3.Connection
) -> None:
    (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
    use_case = _use_case(connection, flagged_package="flask")

    scan_id = await use_case.execute(str(tmp_path))

    findings = SqliteScanRepository(connection).get_findings(scan_id)
    by_name = {f.dependency.name: f for f in findings}
    assert set(by_name) == {"flask", "requests"}
    assert by_name["flask"].risk_score.total == 30.0
    assert by_name["flask"].signals[0].signal_type == SignalType.DEPRECATED
    assert by_name["requests"].risk_score.total == 0.0


async def test_execute_marks_scan_completed(
    tmp_path: Path, connection: sqlite3.Connection
) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")
    use_case = _use_case(connection, flagged_package="flask")

    scan_id = await use_case.execute(str(tmp_path))

    scan = SqliteScanRepository(connection).get_scan(scan_id)
    assert scan is not None
    assert scan["status"] == "completed"
    assert scan["repo_path"] == str(tmp_path)


async def test_execute_with_no_manifests_produces_no_findings(
    tmp_path: Path, connection: sqlite3.Connection
) -> None:
    use_case = _use_case(connection, flagged_package="flask")

    scan_id = await use_case.execute(str(tmp_path))

    assert SqliteScanRepository(connection).get_findings(scan_id) == []
