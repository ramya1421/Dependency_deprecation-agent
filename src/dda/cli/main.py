import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import Protocol

import typer
from rich.console import Console
from rich.table import Table

from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.application.use_cases.scan_repository import ScanRepositoryUseCase
from dda.cli.kb import kb_app
from dda.config.settings import Settings
from dda.domain.entities import Finding, UsageSite
from dda.domain.ports import ISignalSource, IUsageAnalyzer
from dda.domain.value_objects import Confidence
from dda.infrastructure.analyzers.python_ast_analyzer import PythonAstAnalyzer
from dda.infrastructure.analyzers.tree_sitter_js_analyzer import TreeSitterJsAnalyzer
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.parsers.npm_parser import NpmManifestParser
from dda.infrastructure.parsers.parse_result import ParseResult
from dda.infrastructure.parsers.python_parser import PythonManifestParser
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository
from dda.infrastructure.signals.eol_client import EolClient
from dda.infrastructure.signals.github_client import GitHubClient
from dda.infrastructure.signals.npm_client import NpmClient
from dda.infrastructure.signals.osv_client import OsvClient
from dda.infrastructure.signals.pypi_client import PyPIClient
from dda.infrastructure.vcs.git_repo_fetcher import GitRepoFetcher

app = typer.Typer(help="Dependency Deprecation Agent")
app.add_typer(kb_app, name="kb")
console = Console()


class _CoverageParser(Protocol):
    def detect(self, repo_root: Path) -> list[Path]: ...
    def parse_with_coverage(self, manifest: Path) -> ParseResult: ...


def _connection(settings: Settings) -> sqlite3.Connection:
    conn = connect(Path(settings.database_path))
    MigrationRunner(conn).apply_all()
    return conn


def _parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())
    return registry


def _signal_sources(http_client: BaseHttpClient, settings: Settings) -> list[ISignalSource]:
    return [
        PyPIClient(http_client),
        NpmClient(http_client),
        OsvClient(http_client),
        EolClient(http_client),
        GitHubClient(http_client, token=settings.github_token),
    ]


async def _run_scan(
    repo_path: str, offline: bool, settings: Settings, connection: sqlite3.Connection
) -> str:
    async with BaseHttpClient(
        connection, correlation_id=str(uuid.uuid4()), offline=offline
    ) as http_client:
        use_case = ScanRepositoryUseCase(
            repo_fetcher=GitRepoFetcher(),
            parser_registry=_parser_registry(),
            signal_collector=SignalCollector(_signal_sources(http_client, settings)),
            risk_scoring_service=RiskScoringService(weights=settings.risk_weights),
            scan_repository=SqliteScanRepository(connection),
        )
        return await use_case.execute(repo_path)


def _print_findings_table(scan_id: str, findings: list[Finding]) -> None:
    table = Table(title=f"Scan {scan_id}")
    table.add_column("Package")
    table.add_column("Ecosystem")
    table.add_column("Risk", justify="right")
    table.add_column("Rationale")
    for finding in sorted(findings, key=lambda f: f.risk_score.total, reverse=True):
        table.add_row(
            finding.dependency.name,
            finding.dependency.ecosystem.value,
            f"{finding.risk_score.total:.0f}",
            "; ".join(finding.risk_score.rationale),
        )
    console.print(table)


@app.command()
def scan(
    repo_path: str = typer.Argument(..., help="Local path or git URL to scan"),
    offline: bool = typer.Option(False, "--offline", help="Serve signals from cache only"),
) -> None:
    """Scan a repo's dependencies and print a risk-ranked table."""
    settings = Settings()
    connection = _connection(settings)

    scan_id = asyncio.run(_run_scan(repo_path, offline, settings, connection))

    findings = SqliteScanRepository(connection).get_findings(scan_id)
    _print_findings_table(scan_id, findings)


@app.command()
def parse(repo_path: str = typer.Argument(..., help="Local repo path to inventory")) -> None:
    """Show manifest parse coverage for a repo, without contacting any signal source."""
    repo_root = Path(repo_path)
    parsers: list[_CoverageParser] = [PythonManifestParser(), NpmManifestParser()]

    table = Table(title=f"Parse coverage: {repo_path}")
    table.add_column("Manifest")
    table.add_column("Parsed", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Coverage", justify="right")

    for parser in parsers:
        for manifest in parser.detect(repo_root):
            result = parser.parse_with_coverage(manifest)
            parsed = len(result.dependencies)
            total = result.total_declarations
            table.add_row(
                str(manifest.relative_to(repo_root)),
                str(parsed),
                str(len(result.skipped)),
                f"{parsed}/{total}",
            )

    console.print(table)


@app.command()
def show(scan_id: str = typer.Argument(..., help="Scan id to display")) -> None:
    """Show detailed findings for a previous scan."""
    settings = Settings()
    connection = _connection(settings)
    findings = SqliteScanRepository(connection).get_findings(scan_id)
    if not findings:
        console.print(f"[red]No findings for scan {scan_id}[/red]")
        raise typer.Exit(code=1)
    _print_findings_table(scan_id, findings)


@app.command()
def usage(
    repo_path: str = typer.Argument(..., help="Local repo path to analyze"),
    package: str = typer.Option(..., "--package", help="Package name to find usage of"),
) -> None:
    """List every call site for a package's API, with file:line and confidence tier."""
    repo_root = Path(repo_path)
    analyzers: list[IUsageAnalyzer] = [PythonAstAnalyzer(), TreeSitterJsAnalyzer()]
    usage_sites: list[UsageSite] = []
    for analyzer in analyzers:
        usage_sites.extend(analyzer.analyze(repo_root, [package]))

    matching = sorted(
        (s for s in usage_sites if s.package.lower() == package.lower()),
        key=lambda s: (str(s.file_path), s.line_number),
    )

    table = Table(title=f"Usage of {package} in {repo_path}")
    table.add_column("File:Line")
    table.add_column("Symbol")
    table.add_column("Kind")
    table.add_column("Confidence")
    for site in matching:
        location = f"{site.file_path.relative_to(repo_root)}:{site.line_number}"
        table.add_row(location, site.symbol, site.usage_kind, site.confidence.value)
    console.print(table)

    # Never collapse the two confidence tiers into one blended number: static
    # analysis is a lower bound, not an exhaustive count (dynamic imports,
    # re-exports, and monkey-patching all defeat it).
    confirmed = sum(1 for s in matching if s.confidence is Confidence.STATIC_CONFIRMED)
    possible = len(matching) - confirmed
    console.print(
        f"[dim]{confirmed} confirmed, {possible} possible call site(s) — "
        "a lower bound, not exhaustive.[/dim]"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
