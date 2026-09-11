from fastapi import APIRouter, HTTPException

from dda.api.dependencies import get_settings
from dda.api.schemas import KbSearchRequest, KbSearchHit, KbSearchResponse

router = APIRouter(prefix="/api/v1/kb", tags=["kb"])


@router.post("/search", response_model=KbSearchResponse)
def kb_search(body: KbSearchRequest) -> KbSearchResponse:
    """Debug endpoint: search the migration knowledge base directly."""
    settings = get_settings()
    if not settings.qdrant_url:
        raise HTTPException(status_code=503, detail="QDRANT_URL not configured")

    from pathlib import Path
    from dda.infrastructure.rag.bm25_retriever import BM25Retriever
    from dda.infrastructure.rag.chunk_store import ChunkStore
    from dda.infrastructure.rag.embedder import Embedder
    from dda.infrastructure.rag.hybrid_retriever import HybridRetriever
    from dda.infrastructure.rag.qdrant_repository import QdrantVectorRepository
    from dda.infrastructure.rag.reranker import Reranker

    store = ChunkStore(Path("data/kb/chunks"))
    all_chunks = [c for chunks in store.load_all().values() for c in chunks]
    retriever = HybridRetriever(
        vector_repository=QdrantVectorRepository(settings.qdrant_url, settings.qdrant_api_key),
        bm25_retriever=BM25Retriever(all_chunks),
        embedder=Embedder(),
        reranker=Reranker(),
    )

    results = retriever.retrieve(body.query, body.package, body.top_k)
    return KbSearchResponse(
        hits=[
            KbSearchHit(
                chunk_id=c.chunk_id,
                package=c.package,
                doc_type=c.doc_type,
                source_url=c.source_url,
                header_path=c.header_path,
                version=c.version,
                text_preview=c.text[:300],
            )
            for c in results
        ]
    )
