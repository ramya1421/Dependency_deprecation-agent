import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.pypi_client import PyPIClient


def _dependency(resolved_version: str | None = "2.0.0") -> Dependency:
    return Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
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
