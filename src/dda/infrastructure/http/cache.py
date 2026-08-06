import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CacheEntry:
    body: str
    status_code: int


class HttpCache:
    """SQLite-backed response cache, keyed on sha256(source + url + body)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def make_key(source: str, url: str, body: str) -> str:
        return hashlib.sha256(f"{source}:{url}:{body}".encode()).hexdigest()

    def get(self, cache_key: str) -> CacheEntry | None:
        row = self._connection.execute(
            "SELECT response_body, status_code, cached_at, ttl_seconds "
            "FROM http_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        response_body, status_code, cached_at, ttl_seconds = row
        cached_dt = datetime.fromisoformat(cached_at)
        if (datetime.now(UTC) - cached_dt).total_seconds() > ttl_seconds:
            return None
        return CacheEntry(body=response_body, status_code=status_code)

    def put(self, cache_key: str, body: str, status_code: int, ttl_seconds: int) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO http_cache "
            "(cache_key, response_body, status_code, cached_at, ttl_seconds) "
            "VALUES (?, ?, ?, ?, ?)",
            (cache_key, body, status_code, datetime.now(UTC).isoformat(), ttl_seconds),
        )
        self._connection.commit()
