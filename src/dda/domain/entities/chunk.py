from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    package: str
    doc_type: str
    source_url: str
    header_path: str
    version: str | None
    token_count: int
