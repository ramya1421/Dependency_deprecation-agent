import sqlite3
from pathlib import Path

import httpx
import pytest
import respx
from tenacity import wait_none

import dda.infrastructure.signals.osv_client as osv_client_module
from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.osv_client import OsvClient


def _dependency() -> Dependency:
    return Dependency(
        name="django",
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version="3.2.0",
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def test_source_name_is_osv(connection: sqlite3.Connection) -> None:
    assert OsvClient(_http_client(connection)).source_name == "osv"


@respx.mock
async def test_uses_batch_endpoint_and_resolves_vuln_details(
    connection: sqlite3.Connection,
) -> None:
    batch_route = respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "GHSA-xxxx"}]}]})
    )
    detail_route = respx.get("https://api.osv.dev/v1/vulns/GHSA-xxxx").mock(
        return_value=httpx.Response(
            200,
            json={
                "summary": "SQL injection",
                "affected": [{"package": {"name": "django"}}],
                "database_specific": {"severity": "HIGH"},
            },
        )
    )
    client = OsvClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert batch_route.call_count == 1
    assert detail_route.call_count == 1
    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.VULNERABILITY
    assert signals[0].severity == Severity.HIGH
    assert signals[0].payload["id"] == "GHSA-xxxx"


@respx.mock
async def test_no_vulns_produces_no_signals(connection: sqlite3.Connection) -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(200, json={"results": [{}]})
    )
    client = OsvClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []


@respx.mock
async def test_missing_severity_defaults_to_medium(connection: sqlite3.Connection) -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "CVE-1"}]}]})
    )
    respx.get("https://api.osv.dev/v1/vulns/CVE-1").mock(
        return_value=httpx.Response(200, json={"summary": "no normalized severity"})
    )
    client = OsvClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals[0].severity == Severity.MEDIUM


@respx.mock
async def test_unmapped_ecosystem_makes_no_network_call(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(osv_client_module, "_OSV_ECOSYSTEM", {})
    client = OsvClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []
