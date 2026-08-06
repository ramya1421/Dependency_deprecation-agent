import sqlite3
from datetime import UTC, datetime, timedelta

from dda.infrastructure.http.cache import HttpCache


def test_make_key_is_stable_and_source_sensitive() -> None:
    key_a = HttpCache.make_key("pypi", "https://example.test", "")
    key_b = HttpCache.make_key("npm", "https://example.test", "")

    assert key_a == HttpCache.make_key("pypi", "https://example.test", "")
    assert key_a != key_b


def test_put_then_get_round_trips(connection: sqlite3.Connection) -> None:
    cache = HttpCache(connection)
    key = HttpCache.make_key("pypi", "https://example.test", "")

    cache.put(key, '{"n": 1}', 200, ttl_seconds=3600)
    entry = cache.get(key)

    assert entry is not None
    assert entry.body == '{"n": 1}'
    assert entry.status_code == 200


def test_get_returns_none_when_missing(connection: sqlite3.Connection) -> None:
    cache = HttpCache(connection)
    assert cache.get("nonexistent") is None


def test_get_returns_none_when_expired(connection: sqlite3.Connection) -> None:
    cache = HttpCache(connection)
    key = HttpCache.make_key("pypi", "https://example.test", "")
    stale_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    connection.execute(
        "INSERT INTO http_cache (cache_key, response_body, status_code, cached_at, ttl_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (key, '{"n": 1}', 200, stale_time, 3600),
    )
    connection.commit()

    assert cache.get(key) is None
