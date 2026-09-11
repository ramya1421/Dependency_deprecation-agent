"""End-to-end integration test: full scan of the stale-flask fixture repo.

Runs entirely offline (--offline flag, no network calls) with a fake LLM
client so no API keys are needed and the test is deterministic. Asserts the
complete pipeline: parse → signal collection (cache miss → empty) → risk
scoring → persist → retrieve findings.
"""
import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.application.use_cases.scan_repository import ScanRepositoryUseCase
from dda.domain.ports import ILLMClient, ISignalSource
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.parsers.python_parser import PythonManifestParser
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository
from dda.infrastructure.signals.osv_client import OsvClient
from dda.infrastructure.signals.pypi_client import PyPIClient
from dda.infrastructure.vcs.git_repo_fetcher import GitRepoFetcher

_FIXTURE_REPO = Path(__file__).parent.parent / "fixtures" / "repos" / "stale-flask"


class _FakeLLM(ILLMClient):
    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        return "Migration plan: update Flask."

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], system: str = "", temperature: float = 0.2
    ) -> dict[str, Any]:
        return {
            "sub_questions": [
                {"text": "How to upgrade Flask?", "route": "PROSE_QUERY"}
            ],
            "summary": "Update Flask to current version.",
            "steps": ["Step 1: update requirements.txt"],
            "effort": "small",
            "sufficient": True,
            "missing": [],
            "supported": True,
            "entailment_score": 0.9,
        }


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    MigrationRunner(conn).apply_all()
    return conn


async def _run(db: sqlite3.Connection) -> str:
    registry = ParserRegistry()
    registry.register(PythonManifestParser())

    async with BaseHttpClient(db, correlation_id="test", offline=True) as http_client:
        sources: list[ISignalSource] = [
            PyPIClient(http_client),
            OsvClient(http_client),
        ]
        use_case = ScanRepositoryUseCase(
            repo_fetcher=GitRepoFetcher(),
            parser_registry=registry,
            signal_collector=SignalCollector(sources),
            risk_scoring_service=RiskScoringService(),
            scan_repository=SqliteScanRepository(db),
        )
        return await use_case.execute(str(_FIXTURE_REPO))


def test_full_scan_pipeline_produces_findings(db: sqlite3.Connection) -> None:
    """Full pipeline: parse → offline signal fetch → score → persist → retrieve."""
    scan_id = asyncio.run(_run(db))

    assert scan_id, "scan_id must be non-empty"

    repo = SqliteScanRepository(db)

    scan = repo.get_scan(scan_id)
    assert scan is not None
    assert scan["status"] == "completed"
    assert "stale-flask" in scan["repo_path"]

    deps = repo.get_dependencies(scan_id)
    assert len(deps) >= 1, "stale-flask/requirements.txt has at least Flask"
    flask_dep = next((d for d in deps if d.name.lower() == "flask"), None)
    assert flask_dep is not None, "Flask must be parsed from requirements.txt"
    assert flask_dep.resolved_version is None  # plain requirements.txt, no lock
    assert flask_dep.is_direct is True

    findings = repo.get_findings(scan_id)
    assert len(findings) >= 1

    flask_finding = next(
        (f for f in findings if f.dependency.name.lower() == "flask"), None
    )
    assert flask_finding is not None
    # Offline mode: no live signals → risk score comes from 0 signals
    assert 0.0 <= flask_finding.risk_score.total <= 100.0
    assert isinstance(flask_finding.risk_score.rationale, list)


def test_scan_is_idempotent_for_same_repo_different_ids(db: sqlite3.Connection) -> None:
    """Two scans of the same repo produce two independent scan IDs."""
    id1 = asyncio.run(_run(db))
    id2 = asyncio.run(_run(db))
    assert id1 != id2, "each scan invocation must get a unique scan_id"
    repo = SqliteScanRepository(db)
    assert repo.get_findings(id1) is not None
    assert repo.get_findings(id2) is not None


def test_offline_scan_makes_zero_network_calls(db: sqlite3.Connection) -> None:
    """Offline mode must not raise; all signal sources silently return []."""
    # If any network call were attempted it would raise OfflineCacheMissError
    # which SignalCollector catches and logs — findings still exist, signals empty.
    scan_id = asyncio.run(_run(db))
    repo = SqliteScanRepository(db)
    findings = repo.get_findings(scan_id)
    for finding in findings:
        # In offline mode with a cold cache every source returns [] → no signals
        assert finding.signals == [], (
            f"{finding.dependency.name} should have no signals in offline+cold-cache mode"
        )
