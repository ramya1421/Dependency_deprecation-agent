import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals.eol_client import EolClient


def _dependency(name: str = "django", resolved_version: str | None = "3.2") -> Dependency:
    return Dependency(
        name=name,
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version=resolved_version,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def test_source_name_is_eol(connection: sqlite3.Connection) -> None:
    assert EolClient(_http_client(connection)).source_name == "eol"


@respx.mock
async def test_unknown_product_returns_no_signals_not_an_error(
    connection: sqlite3.Connection,
) -> None:
    respx.get("https://endoflife.date/api/some-unknown-package.json").mock(
        return_value=httpx.Response(404)
    )
    client = EolClient(_http_client(connection))

    signals = await client.fetch(_dependency(name="some-unknown-package", resolved_version=None))

    assert signals == []


@respx.mock
async def test_past_eol_produces_critical_signal(connection: sqlite3.Connection) -> None:
    respx.get("https://endoflife.date/api/django.json").mock(
        return_value=httpx.Response(200, json=[{"cycle": "3.2", "eol": "2020-01-01"}])
    )
    client = EolClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.EOL
    assert signals[0].severity == Severity.CRITICAL


@respx.mock
async def test_still_supported_cycle_produces_no_signals(connection: sqlite3.Connection) -> None:
    respx.get("https://endoflife.date/api/django.json").mock(
        return_value=httpx.Response(200, json=[{"cycle": "3.2", "eol": False}])
    )
    client = EolClient(_http_client(connection))

    signals = await client.fetch(_dependency())

    assert signals == []


@respx.mock
async def test_no_matching_cycle_produces_no_signals(connection: sqlite3.Connection) -> None:
    respx.get("https://endoflife.date/api/django.json").mock(
        return_value=httpx.Response(200, json=[{"cycle": "4.2", "eol": "2020-01-01"}])
    )
    client = EolClient(_http_client(connection))

    signals = await client.fetch(_dependency(resolved_version="3.2"))

    assert signals == []
