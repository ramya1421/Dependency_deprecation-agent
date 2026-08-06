import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.github_client import GitHubClient


def _dependency(name: str = "pallets/flask") -> Dependency:
    return Dependency(
        name=name,
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version=None,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def _mock_repo_endpoints(
    *, archived: bool, last_commit_date: str, total_issues: int, open_issues: int
) -> None:
    respx.get("https://api.github.com/repos/pallets/flask").mock(
        return_value=httpx.Response(200, json={"archived": archived, "stargazers_count": 100})
    )
    respx.get("https://api.github.com/repos/pallets/flask/commits").mock(
        return_value=httpx.Response(
            200, json=[{"commit": {"author": {"date": last_commit_date}}}]
        )
    )

    def _search_issues(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "")
        count = open_issues if "state:open" in q else total_issues
        return httpx.Response(200, json={"total_count": count})

    respx.get("https://api.github.com/search/issues").mock(side_effect=_search_issues)


def test_source_name_is_github(connection: sqlite3.Connection) -> None:
    assert GitHubClient(_http_client(connection)).source_name == "github"


@respx.mock
async def test_unresolvable_name_skips_network_entirely(connection: sqlite3.Connection) -> None:
    client = GitHubClient(_http_client(connection))

    signals = await client.fetch(_dependency(name="flask"))

    assert signals == []


@respx.mock
async def test_archived_repo_produces_abandoned_signal(connection: sqlite3.Connection) -> None:
    _mock_repo_endpoints(
        archived=True, last_commit_date="2024-01-01T00:00:00Z", total_issues=10, open_issues=2
    )
    client = GitHubClient(_http_client(connection), token="secret")

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.ABANDONED
    assert signals[0].severity == Severity.HIGH
    assert signals[0].payload["open_issue_ratio"] == 0.2


@respx.mock
async def test_stale_unarchived_repo_produces_medium_severity(
    connection: sqlite3.Connection,
) -> None:
    _mock_repo_endpoints(
        archived=False, last_commit_date="2020-01-01T00:00:00Z", total_issues=10, open_issues=1
    )
    client = GitHubClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].severity == Severity.MEDIUM


@respx.mock
async def test_active_repo_produces_no_signals(connection: sqlite3.Connection) -> None:
    recent = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _mock_repo_endpoints(
        archived=False, last_commit_date=recent, total_issues=10, open_issues=1
    )
    client = GitHubClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []
