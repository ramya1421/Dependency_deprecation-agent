"""Agent tool registry — thin typed wrappers over existing services.

Each tool is a plain dataclass describing its inputs/outputs so the agent
graph can call them without knowing which infrastructure class answers.
Structured-fact tools (metadata, advisories, EOL, repo activity) NEVER route
through the vector store. The retrieval tool is the ONLY entry to RAG. That
separation is the central architectural claim of this project.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dda.domain.entities import Chunk, Dependency, UsageSite
from dda.domain.ports import IRetriever, IUsageAnalyzer
from dda.domain.value_objects import Ecosystem
from dda.infrastructure.signals.eol_client import EolClient
from dda.infrastructure.signals.github_client import GitHubClient
from dda.infrastructure.signals.npm_client import NpmClient
from dda.infrastructure.signals.osv_client import OsvClient
from dda.infrastructure.signals.pypi_client import PyPIClient


@dataclass(frozen=True)
class PackageMetadata:
    name: str
    ecosystem: str
    latest_version: str | None
    deprecated: bool
    deprecation_message: str | None
    classifiers: list[str]


@dataclass(frozen=True)
class AdvisoryResult:
    package: str
    advisories: list[dict[str, Any]]


@dataclass(frozen=True)
class EolResult:
    product: str
    cycle: str | None
    eol: str | None
    severity: str | None


@dataclass(frozen=True)
class RepoActivityResult:
    package: str
    archived: bool
    last_commit_date: str | None
    stars: int
    open_issue_ratio: float


class AgentToolRegistry:
    """Wires together all agent-callable tools.  The agent graph holds one
    instance of this registry and calls the named methods; no tool imports
    infrastructure classes directly.
    """

    def __init__(
        self,
        pypi_client: PyPIClient,
        npm_client: NpmClient,
        osv_client: OsvClient,
        eol_client: EolClient,
        github_client: GitHubClient,
        retriever: IRetriever,
        usage_analyzers: list[IUsageAnalyzer],
        repo_root: Path,
    ) -> None:
        self._pypi = pypi_client
        self._npm = npm_client
        self._osv = osv_client
        self._eol = eol_client
        self._github = github_client
        self._retriever = retriever
        self._analyzers = usage_analyzers
        self._repo_root = repo_root

    async def get_package_metadata(
        self, package: str, ecosystem: str
    ) -> PackageMetadata:
        """Fetch registry metadata: latest version, deprecation flag, classifiers."""
        dep = _stub_dependency(package, ecosystem)
        if ecosystem == "python":
            signals = await self._pypi.fetch(dep)
        else:
            signals = await self._npm.fetch(dep)

        deprecated = any(s.signal_type.value == "deprecated" for s in signals)
        dep_msg = next(
            (str(s.payload.get("message") or s.payload.get("yanked_reason", ""))
             for s in signals if s.signal_type.value == "deprecated"),
            None,
        )
        latest = next(
            (str(s.payload.get("latest_version", "")) for s in signals
             if s.signal_type.value == "outdated"),
            None,
        )
        classifiers: list[str] = []
        return PackageMetadata(
            name=package,
            ecosystem=ecosystem,
            latest_version=latest,
            deprecated=deprecated,
            deprecation_message=dep_msg,
            classifiers=classifiers,
        )

    async def get_advisories(self, package: str, version: str | None) -> AdvisoryResult:
        """Fetch CVE/vulnerability advisories from OSV."""
        dep = _stub_dependency(package, "python", version)
        signals = await self._osv.fetch(dep)
        advisories = [
            {"id": s.payload.get("id"), "summary": s.payload.get("summary"),
             "severity": s.severity.value}
            for s in signals
        ]
        return AdvisoryResult(package=package, advisories=advisories)

    async def get_eol_status(self, product: str, version: str | None) -> EolResult:
        """Check end-of-life status from endoflife.date."""
        dep = _stub_dependency(product, "python", version)
        signals = await self._eol.fetch(dep)
        if not signals:
            return EolResult(product=product, cycle=None, eol=None, severity=None)
        s = signals[0]
        return EolResult(
            product=product,
            cycle=str(s.payload.get("cycle", "")),
            eol=str(s.payload.get("eol", "")),
            severity=s.severity.value,
        )

    async def get_repo_activity(self, package: str) -> RepoActivityResult:
        """Fetch GitHub repo activity: last commit, archived flag, issue ratio."""
        dep = _stub_dependency(package, "python")
        signals = await self._github.fetch(dep)
        if not signals:
            return RepoActivityResult(
                package=package, archived=False,
                last_commit_date=None, stars=0, open_issue_ratio=0.0,
            )
        s = signals[0]
        return RepoActivityResult(
            package=package,
            archived=bool(s.payload.get("archived", False)),
            last_commit_date=s.payload.get("last_commit_date"),
            stars=int(s.payload.get("stars", 0)),
            open_issue_ratio=float(s.payload.get("open_issue_ratio", 0.0)),
        )

    def get_usage_sites(self, package: str) -> list[UsageSite]:
        """Return static analysis call sites for a package in the scanned repo."""
        sites: list[UsageSite] = []
        for analyzer in self._analyzers:
            sites.extend(analyzer.analyze(self._repo_root, [package]))
        return [s for s in sites if s.package.lower() == package.lower()]

    def search_migration_kb(
        self, query: str, package: str | None = None, top_k: int = 5
    ) -> list[Chunk]:
        """Search the migration knowledge base — the ONLY tool that hits the vector store."""
        return self._retriever.retrieve(query, package, top_k)


def _stub_dependency(
    name: str, ecosystem: str, version: str | None = None
) -> Dependency:
    """Build a minimal Dependency for signal-source calls that only need name+ecosystem."""
    return Dependency(
        name=name,
        ecosystem=Ecosystem(ecosystem) if ecosystem in Ecosystem._value2member_map_ else Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version=version,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("unknown"),
    )
