import json
import logging
import sqlite3
from typing import Any, Self

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter
from tenacity.wait import wait_base

from dda.infrastructure.http.cache import HttpCache
from dda.infrastructure.http.circuit_breaker import CircuitBreaker
from dda.infrastructure.http.exceptions import CircuitOpenError, OfflineCacheMissError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


class BaseHttpClient:
    """Shared async HTTP client: caching, retry, a circuit breaker, and offline mode.

    One instance is meant to be shared across all signal sources for a scan, so the
    cache and circuit breaker are correctly keyed per (source, url, body) rather than
    per client instance.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        correlation_id: str,
        offline: bool = False,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 10.0,
        retry_wait: wait_base | None = None,
    ) -> None:
        self._cache = HttpCache(connection)
        self._correlation_id = correlation_id
        self._offline = offline
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._client = httpx.AsyncClient(timeout=timeout)
        self._retry_wait = retry_wait or wait_exponential_jitter(initial=1, max=10)

    async def request(
        self,
        method: str,
        url: str,
        source: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        ttl_seconds: int = 3600,
        parse_json: bool = True,
    ) -> Any:
        # JSON APIs here return either an object or a top-level array (e.g.
        # endoflife.date), so the parsed payload is `Any`, not `dict[str, Any]`.
        # `parse_json=False` is for plain-text endpoints (e.g. raw file
        # content) that were never JSON to begin with.
        body_str = json.dumps(json_body, sort_keys=True) if json_body is not None else ""
        # `params` is folded into the cache key too: two GETs to the same path
        # with different query params (e.g. GitHub's issue search) must not collide.
        params_str = json.dumps(params, sort_keys=True) if params is not None else ""
        cache_key = self._cache.make_key(source, f"{url}?{params_str}", body_str)

        cached = self._cache.get(cache_key)
        if cached is not None:
            self._log(source, method, url, cache_hit=True, status_code=cached.status_code)
            return json.loads(cached.body) if parse_json else cached.body

        if self._offline:
            raise OfflineCacheMissError(url)

        if self._circuit_breaker.is_open(source):
            raise CircuitOpenError(source)

        try:
            response = await self._send_with_retry(method, url, json_body, params, headers)
        except Exception as exc:
            # Only count genuine failures (429/5xx/timeouts) against the circuit.
            # A clean 4xx like 404 is a valid answer from a healthy API and
            # shouldn't trip the breaker for every other source sharing this key.
            if _is_retryable(exc):
                self._circuit_breaker.record_failure(source)
            self._log(source, method, url, cache_hit=False, status_code=None)
            raise
        self._circuit_breaker.record_success(source)

        self._cache.put(cache_key, response.text, response.status_code, ttl_seconds)
        self._log(source, method, url, cache_hit=False, status_code=response.status_code)
        return response.json() if parse_json else response.text

    async def _send_with_retry(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None,
        params: dict[str, str] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=self._retry_wait,
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                response = await self._client.request(
                    method, url, json=json_body, params=params, headers=headers
                )
                response.raise_for_status()
                return response
        raise AssertionError("unreachable: AsyncRetrying always returns or raises")

    def _log(
        self, source: str, method: str, url: str, *, cache_hit: bool, status_code: int | None
    ) -> None:
        logger.info(
            "http_request",
            extra={
                "correlation_id": self._correlation_id,
                "source": source,
                "method": method,
                "url": url,
                "cache_hit": cache_hit,
                "status_code": status_code,
                "offline": self._offline,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
