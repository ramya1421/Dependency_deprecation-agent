import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any


class LLMCache:
    """SQLite-backed LLM response cache keyed on sha256(model + prompt + temperature).

    Makes evaluation re-runs free on a 15 RPM free tier — without this,
    a 40-question golden set re-run burns through the daily quota.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def make_key(model: str, prompt: str, temperature: float) -> str:
        material = f"{model}:{prompt}:{temperature}"
        return hashlib.sha256(material.encode()).hexdigest()

    def get(self, cache_key: str) -> str | None:
        row = self._connection.execute(
            "SELECT response FROM llm_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def put(self, cache_key: str, response: str) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, response, cached_at) VALUES (?, ?, ?)",
            (cache_key, response, datetime.now(UTC).isoformat()),
        )
        self._connection.commit()

    def get_structured(self, cache_key: str) -> dict[str, Any] | None:
        raw = self.get(cache_key)
        if raw is None:
            return None
        try:
            result = json.loads(raw)
            return result if isinstance(result, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def put_structured(self, cache_key: str, data: dict[str, Any]) -> None:
        self.put(cache_key, json.dumps(data))
