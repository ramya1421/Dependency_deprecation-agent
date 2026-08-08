import sqlite3

import httpx
import pytest
import respx
from tenacity import wait_none

from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.http.circuit_breaker import CircuitBreaker
from dda.infrastructure.http.exceptions import CircuitOpenError, OfflineCacheMissError


def _client(
    connection: sqlite3.Connection,
    *,
    offline: bool = False,
    circuit_breaker: CircuitBreaker | None = None,
) -> BaseHttpClient:
    return BaseHttpClient(
        connection,
        correlation_id="test-correlation-id",
        offline=offline,
        circuit_breaker=circuit_breaker,
        retry_wait=wait_none(),
    )


@respx.mock
async def test_request_returns_parsed_json(connection: sqlite3.Connection) -> None:
    respx.get("https://example.test/ok").mock(return_value=httpx.Response(200, json={"n": 1}))
    client = _client(connection)

    result = await client.request("GET", "https://example.test/ok", "example")

    assert result == {"n": 1}
    await client.aclose()


@respx.mock
async def test_parse_json_false_returns_raw_text(connection: sqlite3.Connection) -> None:
    respx.get("https://example.test/raw.md").mock(
        return_value=httpx.Response(200, text="# Changelog\n\nnot json\n")
    )
    client = _client(connection)

    result = await client.request(
        "GET", "https://example.test/raw.md", "example", parse_json=False
    )

    assert result == "# Changelog\n\nnot json\n"
    await client.aclose()


@respx.mock
async def test_parse_json_false_cache_hit_also_returns_raw_text(
    connection: sqlite3.Connection,
) -> None:
    route = respx.get("https://example.test/raw.md").mock(
        return_value=httpx.Response(200, text="raw content")
    )
    client = _client(connection)

    first = await client.request(
        "GET", "https://example.test/raw.md", "example", parse_json=False
    )
    second = await client.request(
        "GET", "https://example.test/raw.md", "example", parse_json=False
    )

    assert first == second == "raw content"
    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_retries_on_429_then_succeeds(connection: sqlite3.Connection) -> None:
    route = respx.get("https://example.test/flaky").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    client = _client(connection)

    result = await client.request("GET", "https://example.test/flaky", "example")

    assert result == {"ok": True}
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_retries_on_500_up_to_three_attempts_then_raises(
    connection: sqlite3.Connection,
) -> None:
    route = respx.get("https://example.test/down").mock(return_value=httpx.Response(500))
    client = _client(connection)

    with pytest.raises(httpx.HTTPStatusError):
        await client.request("GET", "https://example.test/down", "example")

    assert route.call_count == 3
    await client.aclose()


@respx.mock
async def test_does_not_retry_on_404(connection: sqlite3.Connection) -> None:
    route = respx.get("https://example.test/missing").mock(return_value=httpx.Response(404))
    client = _client(connection)

    with pytest.raises(httpx.HTTPStatusError):
        await client.request("GET", "https://example.test/missing", "example")

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_cache_hit_skips_network(connection: sqlite3.Connection) -> None:
    route = respx.get("https://example.test/cached").mock(
        return_value=httpx.Response(200, json={"n": 1})
    )
    client = _client(connection)

    first = await client.request("GET", "https://example.test/cached", "example")
    second = await client.request("GET", "https://example.test/cached", "example")

    assert first == second == {"n": 1}
    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_cache_expiry_refetches(connection: sqlite3.Connection) -> None:
    route = respx.get("https://example.test/ttl").mock(
        side_effect=[
            httpx.Response(200, json={"n": 1}),
            httpx.Response(200, json={"n": 2}),
        ]
    )
    client = _client(connection)

    first = await client.request("GET", "https://example.test/ttl", "example", ttl_seconds=0)
    second = await client.request("GET", "https://example.test/ttl", "example", ttl_seconds=0)

    assert first == {"n": 1}
    assert second == {"n": 2}
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_circuit_opens_after_repeated_failures(connection: sqlite3.Connection) -> None:
    respx.get("https://example.test/down").mock(return_value=httpx.Response(500))
    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=60)
    client = _client(connection, circuit_breaker=breaker)

    for _ in range(2):
        with pytest.raises(httpx.HTTPStatusError):
            await client.request("GET", "https://example.test/down", "example")

    with pytest.raises(CircuitOpenError):
        await client.request("GET", "https://example.test/down", "example")
    await client.aclose()


@respx.mock
async def test_repeated_404s_do_not_open_the_circuit(connection: sqlite3.Connection) -> None:
    respx.get("https://example.test/missing").mock(return_value=httpx.Response(404))
    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=60)
    client = _client(connection, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(httpx.HTTPStatusError):
            await client.request("GET", "https://example.test/missing", "example")

    assert breaker.is_open("example") is False
    await client.aclose()


@respx.mock
async def test_offline_mode_serves_from_cache_with_no_network_call(
    connection: sqlite3.Connection,
) -> None:
    route = respx.get("https://example.test/warm").mock(
        return_value=httpx.Response(200, json={"n": 1})
    )
    warm_client = _client(connection)
    await warm_client.request("GET", "https://example.test/warm", "example")
    await warm_client.aclose()
    assert route.call_count == 1

    offline_client = _client(connection, offline=True)
    result = await offline_client.request("GET", "https://example.test/warm", "example")

    assert result == {"n": 1}
    assert route.call_count == 1
    await offline_client.aclose()


@respx.mock
async def test_offline_mode_raises_on_cache_miss(connection: sqlite3.Connection) -> None:
    route = respx.get("https://example.test/cold").mock(
        return_value=httpx.Response(200, json={"n": 1})
    )
    client = _client(connection, offline=True)

    with pytest.raises(OfflineCacheMissError):
        await client.request("GET", "https://example.test/cold", "example")

    assert route.call_count == 0
    await client.aclose()
