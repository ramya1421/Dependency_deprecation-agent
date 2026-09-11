"""FastAPI dependency injection wiring.

All route handlers call these functions via Depends() — no business logic
lives in routes, and no infrastructure classes are instantiated in routes.
"""
import sqlite3
import uuid
from functools import lru_cache
from pathlib import Path

from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.application.use_cases.scan_repository import ScanRepositoryUseCase
from dda.config.settings import Settings
from dda.infrastructure.parsers.npm_parser import NpmManifestParser
from dda.infrastructure.parsers.python_parser import PythonManifestParser
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    conn = connect(Path(settings.database_path))
    MigrationRunner(conn).apply_all()
    return conn


def get_scan_repository() -> SqliteScanRepository:
    return SqliteScanRepository(get_connection())


def get_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())
    return registry
