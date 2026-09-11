import sqlite3
from pathlib import Path

import pytest

from dda.infrastructure.llm.llm_cache import LLMCache
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    MigrationRunner(conn).apply_all()
    return conn


def test_cache_miss_returns_none(connection: sqlite3.Connection) -> None:
    cache = LLMCache(connection)
    assert cache.get("nonexistent") is None


def test_put_and_get_round_trips(connection: sqlite3.Connection) -> None:
    cache = LLMCache(connection)
    key = LLMCache.make_key("gemini", "hello", 0.2)

    cache.put(key, "response text")

    assert cache.get(key) == "response text"


def test_put_structured_and_get_structured(connection: sqlite3.Connection) -> None:
    cache = LLMCache(connection)
    key = LLMCache.make_key("gemini", "hello", 0.0)
    data = {"steps": ["a", "b"], "effort": "small"}

    cache.put_structured(key, data)

    assert cache.get_structured(key) == data


def test_different_temperatures_produce_different_keys() -> None:
    k1 = LLMCache.make_key("gemini", "prompt", 0.0)
    k2 = LLMCache.make_key("gemini", "prompt", 0.5)
    assert k1 != k2


def test_put_overwrites_existing_entry(connection: sqlite3.Connection) -> None:
    cache = LLMCache(connection)
    key = LLMCache.make_key("groq", "p", 0.1)

    cache.put(key, "first")
    cache.put(key, "second")

    assert cache.get(key) == "second"
