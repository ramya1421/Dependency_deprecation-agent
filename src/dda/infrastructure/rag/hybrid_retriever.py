from dda.domain.entities import Chunk
from dda.domain.ports import IRetriever, IVectorRepository
from dda.infrastructure.rag._scoring import ScoredChunk
from dda.infrastructure.rag.bm25_retriever import BM25Retriever
from dda.infrastructure.rag.embedder import Embedder
from dda.infrastructure.rag.fusion import reciprocal_rank_fusion
from dda.infrastructure.rag.reranker import Reranker

# Candidate pool fed into RRF before reranking. 20 gives the cross-encoder
# enough variety without blowing inference time; dropping it to 10 cuts the
# reranker value in half in ablation.
_RRF_CANDIDATE_K = 20


class HybridRetriever(IRetriever):
    """Dense + sparse + RRF + rerank pipeline implementing IRetriever.

    Each stage is independently togglable via constructor flags so Step 11's
    ablation study can isolate each component's contribution without changing
    any calling code.
    """

    def __init__(
        self,
        vector_repository: IVectorRepository,
        bm25_retriever: BM25Retriever,
        embedder: Embedder,
        reranker: Reranker,
        *,
        use_bm25: bool = True,
        use_rerank: bool = True,
    ) -> None:
        self._vector_repository = vector_repository
        self._bm25 = bm25_retriever
        self._embedder = embedder
        self._reranker = reranker
        self._use_bm25 = use_bm25
        self._use_rerank = use_rerank

    def retrieve(self, query: str, package: str | None, top_k: int) -> list[Chunk]:
        filters = {"package": package} if package else None

        # Dense retrieval: filter BEFORE vector scoring is the largest free
        # precision win — Qdrant applies the payload filter at HNSW index level.
        query_vector = self._embedder.embed_query(query)
        dense_k = _RRF_CANDIDATE_K if self._use_bm25 else top_k
        dense_chunks = self._vector_repository.search(query_vector, filters, dense_k)
        dense_scored = [ScoredChunk(c, 1.0) for c in dense_chunks]

        if self._use_bm25:
            sparse_scored = self._bm25.search(query, package, _RRF_CANDIDATE_K)
            fused = reciprocal_rank_fusion([dense_scored, sparse_scored])
        else:
            fused = dense_scored

        if self._use_rerank:
            rerank_k = min(_RRF_CANDIDATE_K, len(fused))
            final = self._reranker.rerank(query, fused[:rerank_k], top_k)
        else:
            final = fused[:top_k]

        return [sc.chunk for sc in final]
