import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.npm_client import NpmClient


def _dependency(name: str = "request", resolved_version: str | None = "2.88.0") -> Dependency:
    return Dependency(
        name=name,
        ecosystem=Ecosystem.JAVASCRIPT,
        declared_spec="*",
        resolved_version=resolved_version,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("package.json"),
    )


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def test_source_name_is_npm(connection: sqlite3.Connection) -> None:
    assert NpmClient(_http_client(connection)).source_name == "npm"


@respx.mock
async def test_deprecated_field_produces_signal(connection: sqlite3.Connection) -> None:
    respx.get("https://registry.npmjs.org/request").mock(
        return_value=httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "2.88.0"},
                "versions": {"2.88.0": {"deprecated": "request has been deprecated"}},
                "time": {"modified": "2023-02-01T00:00:00.000Z"},
            },
        )
    )
    client = NpmClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.DEPRECATED
    assert signals[0].payload["message"] == "request has been deprecated"


@respx.mock
async def test_healthy_package_produces_no_signals(connection: sqlite3.Connection) -> None:
    respx.get("https://registry.npmjs.org/request").mock(
        return_value=httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "2.88.0"},
                "versions": {"2.88.0": {}},
                "time": {"modified": "2023-02-01T00:00:00.000Z"},
            },
        )
    )
    client = NpmClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []


@respx.mock
async def test_scoped_package_name_is_percent_encoded(connection: sqlite3.Connection) -> None:
    route = respx.get("https://registry.npmjs.org/@scope%2fpkg").mock(
        return_value=httpx.Response(
            200,
            json={"dist-tags": {"latest": "1.0.0"}, "versions": {"1.0.0": {}}, "time": {}},
        )
    )
    client = NpmClient(_http_client(connection))

    await client.fetch(_dependency(name="@scope/pkg", resolved_version="1.0.0"))

    assert route.call_count == 1
