import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.pypi_client import PyPIClient


def _dependency(
    resolved_version: str | None = "2.0.0", ecosystem: Ecosystem = Ecosystem.PYTHON
) -> Dependency:
    return Dependency(
        name="flask",
        ecosystem=ecosystem,
        declared_spec="*",
        resolved_version=resolved_version,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def test_source_name_is_pypi(connection: sqlite3.Connection) -> None:
    assert PyPIClient(_http_client(connection)).source_name == "pypi"


async def test_offline_cache_miss_returns_empty_list(connection: sqlite3.Connection) -> None:
    offline_client = BaseHttpClient(connection, correlation_id="test", offline=True)
    client = PyPIClient(offline_client)

    signals = await client.fetch(_dependency())

    assert signals == []


@respx.mock
async def test_non_python_dependency_makes_no_network_call(
    connection: sqlite3.Connection,
) -> None:
    route = respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(200, json={"info": {}, "releases": {}, "urls": []})
    )
    client = PyPIClient(_http_client(connection))

    signals = await client.fetch(_dependency(ecosystem=Ecosystem.JAVASCRIPT))

    assert signals == []
    assert route.call_count == 0


@respx.mock
async def test_yanked_release_produces_deprecated_signal(connection: sqlite3.Connection) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {"version": "2.0.0", "classifiers": []},
                "releases": {
                    "2.0.0": [
                        {
                            "yanked": True,
                            "yanked_reason": "security issue",
                            "upload_time_iso_8601": "2021-05-01T00:00:00.000000Z",
                        }
                    ]
                },
                "urls": [],
            },
        )
    )
    client = PyPIClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.DEPRECATED
    assert signals[0].payload["yanked_reason"] == "security issue"


@respx.mock
async def test_inactive_classifier_produces_abandoned_signal(
    connection: sqlite3.Connection,
) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {
                    "version": "2.0.0",
                    "classifiers": ["Development Status :: 7 - Inactive"],
                },
                "releases": {"2.0.0": []},
                "urls": [],
            },
        )
    )
    client = PyPIClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.ABANDONED


@respx.mock
async def test_healthy_package_produces_no_signals(connection: sqlite3.Connection) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {"version": "2.0.0", "classifiers": []},
                "releases": {
                    "2.0.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00.000000Z"}]
                },
                "urls": [],
            },
        )
    )
    client = PyPIClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []


@respx.mock
async def test_major_versions_behind_produces_outdated_signal(
    connection: sqlite3.Connection,
) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {"version": "3.0.0", "classifiers": []},
                "releases": {"1.0.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00Z"}]},
                "urls": [],
            },
        )
    )
    client = PyPIClient(_http_client(connection))

    signals = await client.fetch(_dependency(resolved_version="1.0.0"))

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.OUTDATED
    assert signals[0].severity == Severity.MEDIUM
    assert signals[0].payload["major_versions_behind"] == 2
