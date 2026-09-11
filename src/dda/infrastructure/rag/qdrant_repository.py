from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from dda.domain.entities import Chunk
from dda.domain.ports import IVectorRepository
from dda.infrastructure.rag.embedder import Embedder

_COLLECTION = "migration_kb"
_VECTOR_SIZE = 384  # bge-small-en-v1.5 output dimension


class QdrantVectorRepository(IVectorRepository):
    """Qdrant Cloud-backed vector store for migration prose chunks.

    Payload indexes on `package` and `doc_type` are created on collection init
    so filtered searches skip the full scan — this is the largest single
    precision win available and costs essentially nothing.

    The embedder is owned here rather than passed in because this class is the
    only caller of embed_documents, and co-locating the two keeps the upsert
    signature clean (callers pass Chunk, not (Chunk, vector)).
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = QdrantClient(url=url, api_key=api_key)
        self._embedder = Embedder()
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if _COLLECTION not in existing:
            self._client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
            # Payload indexes let Qdrant skip unrelated packages before vector scoring.
            self._client.create_payload_index(
                _COLLECTION, "package", PayloadSchemaType.KEYWORD
            )
            self._client.create_payload_index(
                _COLLECTION, "doc_type", PayloadSchemaType.KEYWORD
            )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        # chunk_id is a 16-char hex digest; Qdrant point IDs must be uint64 or
        # UUID — we derive a stable uint64 by taking the first 16 hex chars as
        # an integer (fits in uint64 and is collision-resistant enough at corpus
        # scale of ~300 docs).
        points = [
            PointStruct(
                id=int(chunk.chunk_id, 16) % (2**63),
                vector=vector,
                payload=_chunk_to_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._client.upsert(collection_name=_COLLECTION, points=points)

    def search(
        self, vector: list[float], filters: dict[str, Any] | None, top_k: int
    ) -> list[Chunk]:
        qdrant_filter = _build_filter(filters) if filters else None
        results = self._client.query_points(
            collection_name=_COLLECTION,
            query=vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        ).points
        return [_payload_to_chunk(hit.payload or {}, hit.id) for hit in results]


def _chunk_to_payload(chunk: Chunk) -> dict[str, Any]:
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


def _payload_to_chunk(payload: dict[str, Any], point_id: object) -> Chunk:
    return Chunk(
        chunk_id=str(payload.get("chunk_id", str(point_id))),
        text=str(payload.get("text", "")),
        package=str(payload.get("package", "")),
        doc_type=str(payload.get("doc_type", "")),
        source_url=str(payload.get("source_url", "")),
        header_path=str(payload.get("header_path", "")),
        version=payload.get("version"),
        token_count=int(payload.get("token_count", 0)),
    )


def _build_filter(filters: dict[str, Any]) -> Filter:
    conditions = [
        FieldCondition(key=key, match=MatchValue(value=value))
        for key, value in filters.items()
    ]
    return Filter(must=conditions)
