from datetime import UTC, datetime

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient

_ABANDONED_AFTER_DAYS = 547  # ~18 months


class GitHubClient(ISignalSource):
    """Extracts repo activity signals (last commit, archived flag, issue ratio,
    stars). Package-name -> GitHub-repo resolution isn't solved here: names
    that aren't already "owner/repo" are skipped rather than guessed. A real
    resolver (e.g. via PyPI/npm project URLs) is a separate concern.
    """

    def __init__(self, http_client: BaseHttpClient, token: str | None = None) -> None:
        self._http_client = http_client
        self._token = token

    @property
    def source_name(self) -> str:
        return "github"

    async def fetch(self, dependency: Dependency) -> list[Signal]:
        owner_repo = self._resolve_repo(dependency.name)
        if owner_repo is None:
            return []
        owner, repo = owner_repo
        headers = self._headers()

        repo_data = await self._http_client.request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}",
            self.source_name,
            headers=headers,
        )
        commits = await self._http_client.request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            self.source_name,
            params={"per_page": "1"},
            headers=headers,
        )
        total_issues = await self._http_client.request(
            "GET",
            "https://api.github.com/search/issues",
            self.source_name,
            params={"q": f"repo:{owner}/{repo} type:issue"},
            headers=headers,
        )
        open_issues = await self._http_client.request(
            "GET",
            "https://api.github.com/search/issues",
            self.source_name,
            params={"q": f"repo:{owner}/{repo} type:issue state:open"},
            headers=headers,
        )

        archived = bool(repo_data.get("archived", False))
        last_commit_date = commits[0]["commit"]["author"]["date"] if commits else None
        total_count = total_issues.get("total_count", 0)
        open_count = open_issues.get("total_count", 0)
        open_issue_ratio = open_count / total_count if total_count else 0.0

        if not archived and not self._is_stale(last_commit_date):
            return []

        return [
            Signal(
                source=self.source_name,
                signal_type=SignalType.ABANDONED,
                severity=Severity.HIGH if archived else Severity.MEDIUM,
                payload={
                    "archived": archived,
                    "last_commit_date": last_commit_date,
                    "stars": repo_data.get("stargazers_count", 0),
                    "open_issue_ratio": open_issue_ratio,
                },
                fetched_at=datetime.now(UTC),
            )
        ]

    def _headers(self) -> dict[str, str] | None:
        return {"Authorization": f"Bearer {self._token}"} if self._token else None

    @staticmethod
    def _resolve_repo(name: str) -> tuple[str, str] | None:
        parts = name.split("/")
        if len(parts) != 2 or not all(parts):
            return None
        return parts[0], parts[1]

    @staticmethod
    def _is_stale(last_commit_date: str | None) -> bool:
        if last_commit_date is None:
            return False
        commit_dt = datetime.fromisoformat(last_commit_date.replace("Z", "+00:00"))
        return (datetime.now(UTC) - commit_dt).days > _ABANDONED_AFTER_DAYS
