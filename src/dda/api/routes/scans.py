import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from dda.api.dependencies import get_connection, get_scan_repository, get_settings
from dda.api.schemas import (
    DependencyResponse,
    FindingResponse,
    RiskScoreResponse,
    ScanCreatedResponse,
    ScanReportResponse,
    ScanRequest,
    ScanStatusResponse,
    ReportFinding,
)
from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.application.use_cases.scan_repository import ScanRepositoryUseCase
from dda.config.settings import Settings
from dda.infrastructure.analyzers.python_ast_analyzer import PythonAstAnalyzer
from dda.infrastructure.analyzers.tree_sitter_js_analyzer import TreeSitterJsAnalyzer
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.parsers.npm_parser import NpmManifestParser
from dda.infrastructure.parsers.python_parser import PythonManifestParser
from dda.infrastructure.persistence.sqlite_scan_repository import SqliteScanRepository
from dda.infrastructure.signals.eol_client import EolClient
from dda.infrastructure.signals.github_client import GitHubClient
from dda.infrastructure.signals.npm_client import NpmClient
from dda.infrastructure.signals.osv_client import OsvClient
from dda.infrastructure.signals.pypi_client import PyPIClient
from dda.infrastructure.vcs.git_repo_fetcher import GitRepoFetcher

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


async def _run_scan_task(scan_id: str, repo_path: str, offline: bool) -> None:
    """BackgroundTask: runs the full scan pipeline for one scan_id.

    Streamlit re-runs the whole script on every interaction, so scans are
    async with polling rather than run inline — this is why BackgroundTasks
    is enough without Celery.
    """
    settings = get_settings()
    connection = get_connection()
    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())

    async with BaseHttpClient(
        connection, correlation_id=scan_id, offline=offline
    ) as http_client:
        sources = [
            PyPIClient(http_client),
            NpmClient(http_client),
            OsvClient(http_client),
            EolClient(http_client),
            GitHubClient(http_client, token=settings.github_token),
        ]
        use_case = ScanRepositoryUseCase(
            repo_fetcher=GitRepoFetcher(),
            parser_registry=registry,
            signal_collector=SignalCollector(sources),
            risk_scoring_service=RiskScoringService(weights=settings.risk_weights),
            scan_repository=SqliteScanRepository(connection),
        )
        # ScanRepositoryUseCase.execute persists results and returns the scan_id.
        await use_case.execute(repo_path)


@router.post("", status_code=202, response_model=ScanCreatedResponse)
async def create_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> ScanCreatedResponse:
    """Trigger a scan and return immediately. Poll GET /scans/{id} for status."""
    from datetime import UTC, datetime
    scan_id = str(uuid.uuid4())
    repo.save_scan(scan_id, body.repo_path, "queued", datetime.now(UTC))
    background_tasks.add_task(_run_scan_task, scan_id, body.repo_path, body.offline)
    return ScanCreatedResponse(scan_id=scan_id)


@router.get("/{scan_id}", response_model=ScanStatusResponse)
def get_scan(
    scan_id: str,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> ScanStatusResponse:
    scan = repo.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return ScanStatusResponse(
        scan_id=str(scan["id"]),
        repo_path=str(scan["repo_path"]),
        status=str(scan["status"]),
        started_at=str(scan["started_at"]),
    )


@router.get("/{scan_id}/dependencies", response_model=list[DependencyResponse])
def get_dependencies(
    scan_id: str,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> list[DependencyResponse]:
    _require_scan(scan_id, repo)
    deps = repo.get_dependencies(scan_id)
    return [
        DependencyResponse(
            name=d.name,
            ecosystem=d.ecosystem.value,
            declared_spec=d.declared_spec,
            resolved_version=d.resolved_version,
            is_direct=d.is_direct,
            is_dev=d.is_dev,
            manifest_path=str(d.manifest_path),
        )
        for d in deps
    ]


@router.get("/{scan_id}/findings", response_model=list[FindingResponse])
def get_findings(
    scan_id: str,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> list[FindingResponse]:
    _require_scan(scan_id, repo)
    findings = repo.get_findings(scan_id)
    return [
        FindingResponse(
            dependency_name=f.dependency.name,
            ecosystem=f.dependency.ecosystem.value,
            risk_score=RiskScoreResponse(
                total=f.risk_score.total,
                components=f.risk_score.components,
                rationale=f.risk_score.rationale,
            ),
            signal_count=len(f.signals),
            usage_site_count=len(f.usage_sites),
            has_migration_plan=f.migration_plan is not None,
        )
        for f in sorted(findings, key=lambda x: x.risk_score.total, reverse=True)
    ]


@router.get("/{scan_id}/findings/{dep_name}/migration")
def get_migration_plan(
    scan_id: str,
    dep_name: str,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> dict:  # type: ignore[type-arg]
    _require_scan(scan_id, repo)
    findings = repo.get_findings(scan_id)
    match = next((f for f in findings if f.dependency.name == dep_name), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Dependency not found in this scan")
    if match.migration_plan is None:
        raise HTTPException(status_code=404, detail="No migration plan for this dependency")
    plan = match.migration_plan
    return {
        "package": plan.package,
        "summary": plan.summary,
        "steps": plan.steps,
        "effort": plan.effort.value,
        "claims": [
            {
                "text": c.text,
                "chunk_id": c.chunk_id,
                "verified": c.verified,
                "entailment_score": c.entailment_score,
            }
            for c in plan.claims
        ],
        "usage_site_count": len(plan.usage_sites),
    }


@router.get("/{scan_id}/report", response_model=ScanReportResponse)
def get_report(
    scan_id: str,
    repo: SqliteScanRepository = Depends(get_scan_repository),
) -> ScanReportResponse:
    scan = repo.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    findings = repo.get_findings(scan_id)
    deps = repo.get_dependencies(scan_id)
    return ScanReportResponse(
        scan_id=scan_id,
        repo_path=str(scan["repo_path"]),
        status=str(scan["status"]),
        dependency_count=len(deps),
        findings=[
            ReportFinding(
                package=f.dependency.name,
                ecosystem=f.dependency.ecosystem.value,
                risk_total=f.risk_score.total,
                rationale=f.risk_score.rationale,
                effort=f.migration_plan.effort.value if f.migration_plan else None,
            )
            for f in sorted(findings, key=lambda x: x.risk_score.total, reverse=True)
        ],
    )


def _require_scan(scan_id: str, repo: SqliteScanRepository) -> None:
    if repo.get_scan(scan_id) is None:
        raise HTTPException(status_code=404, detail="Scan not found")
