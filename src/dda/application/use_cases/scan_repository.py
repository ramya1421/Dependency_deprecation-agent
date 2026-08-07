from datetime import UTC, datetime
from uuid import uuid4

from dda.application.services.parser_registry import ParserRegistry
from dda.application.services.risk_scoring_service import RiskScoringService
from dda.application.services.signal_collector import SignalCollector
from dda.domain.entities import Finding
from dda.domain.ports import IRepoFetcher, IScanRepository


class ScanRepositoryUseCase:
    """Orchestrates a full scan: clone-or-read -> detect manifests -> parse ->
    collect signals -> score risk -> persist. The CLI and (later) API both
    call this one object, so the pipeline is defined in exactly one place.
    """

    def __init__(
        self,
        repo_fetcher: IRepoFetcher,
        parser_registry: ParserRegistry,
        signal_collector: SignalCollector,
        risk_scoring_service: RiskScoringService,
        scan_repository: IScanRepository,
    ) -> None:
        self._repo_fetcher = repo_fetcher
        self._parser_registry = parser_registry
        self._signal_collector = signal_collector
        self._risk_scoring_service = risk_scoring_service
        self._scan_repository = scan_repository

    async def execute(self, repo_path_or_url: str) -> str:
        scan_id = str(uuid4())
        # `dependencies`/`findings` carry a FOREIGN KEY on scans.id (enforced,
        # PRAGMA foreign_keys=ON), and IScanRepository.save_scan is insert-only
        # with no update, so the scan row is written once, up front.
        self._scan_repository.save_scan(scan_id, repo_path_or_url, "completed", datetime.now(UTC))

        repo_root = self._repo_fetcher.fetch(repo_path_or_url)
        dependencies = self._parser_registry.parse_all(repo_root)
        self._scan_repository.save_dependencies(scan_id, dependencies)

        signals_by_name = await self._signal_collector.collect(dependencies)

        findings = []
        for dependency in dependencies:
            signals = signals_by_name.get(dependency.name, [])
            self._scan_repository.save_signals(dependency.name, signals)
            findings.append(
                Finding(
                    dependency=dependency,
                    risk_score=self._risk_scoring_service.score(dependency, signals),
                    signals=signals,
                    usage_sites=[],
                    migration_plan=None,
                )
            )
        self._scan_repository.save_findings(scan_id, findings)
        return scan_id
