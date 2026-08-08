import json
from pathlib import Path
from typing import Any

from dda.domain.entities import Chunk


class ChunkStore:
    """Persists chunks as JSON Lines, one file per package — plain text,
    inspectable, and diffable, matching the corpus's own "I can actually
    inspect this" requirement.
    """

    def __init__(self, chunks_dir: Path) -> None:
        self._chunks_dir = chunks_dir

    def save(self, package: str, chunks: list[Chunk]) -> None:
        self._chunks_dir.mkdir(parents=True, exist_ok=True)
        with self._path_for(package).open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(_to_dict(chunk)) + "\n")

    def load(self, package: str) -> list[Chunk]:
        return _load_file(self._path_for(package))

    def load_all(self) -> dict[str, list[Chunk]]:
        if not self._chunks_dir.is_dir():
            return {}
        return {
            path.stem: _load_file(path) for path in sorted(self._chunks_dir.glob("*.jsonl"))
        }

    def _path_for(self, package: str) -> Path:
        return self._chunks_dir / f"{package}.jsonl"


def _load_file(path: Path) -> list[Chunk]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_from_dict(json.loads(line)) for line in lines if line.strip()]


def _to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "package": chunk.package,
        "doc_type": chunk.doc_type,
        "source_url": chunk.source_url,
        "header_path": chunk.header_path,
        "version": chunk.version,
        "token_count": chunk.token_count,
    }


def _from_dict(data: dict[str, Any]) -> Chunk:
    return Chunk(
        chunk_id=str(data["chunk_id"]),
        text=str(data["text"]),
        package=str(data["package"]),
        doc_type=str(data["doc_type"]),
        source_url=str(data["source_url"]),
        header_path=str(data["header_path"]),
        version=None if data["version"] is None else str(data["version"]),
        token_count=int(data["token_count"]),
    )
