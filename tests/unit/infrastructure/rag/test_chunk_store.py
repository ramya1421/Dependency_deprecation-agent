from pathlib import Path

from dda.domain.entities import Chunk
from dda.infrastructure.rag.chunk_store import ChunkStore


def _chunk(chunk_id: str = "abc123", version: str | None = "1.0.0") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text="Changelog > 1.0.0\n\nsome text",
        package="flask",
        doc_type="changelog",
        source_url="https://example.test/CHANGELOG.md",
        header_path="Changelog > 1.0.0",
        version=version,
        token_count=5,
    )


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path)
    store.save("flask", [_chunk()])

    loaded = store.load("flask")

    assert loaded == [_chunk()]


def test_load_missing_package_returns_empty_list(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path)

    assert store.load("nonexistent") == []


def test_none_version_round_trips(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path)
    store.save("flask", [_chunk(version=None)])

    loaded = store.load("flask")

    assert loaded[0].version is None


def test_save_overwrites_previous_contents(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path)
    store.save("flask", [_chunk("first")])
    store.save("flask", [_chunk("second")])

    loaded = store.load("flask")

    assert [c.chunk_id for c in loaded] == ["second"]


def test_load_all_returns_every_package(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path)
    store.save("flask", [_chunk("a")])
    store.save("pydantic", [_chunk("b")])

    loaded = store.load_all()

    assert set(loaded.keys()) == {"flask", "pydantic"}
    assert [c.chunk_id for c in loaded["flask"]] == ["a"]


def test_load_all_on_empty_directory(tmp_path: Path) -> None:
    store = ChunkStore(tmp_path / "does-not-exist")

    assert store.load_all() == {}
