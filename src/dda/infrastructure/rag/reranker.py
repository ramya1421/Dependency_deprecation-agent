from functools import lru_cache

from sentence_transformers import CrossEncoder

from dda.domain.entities import Chunk
from dda.infrastructure.rag._scoring import ScoredChunk

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _model() -> CrossEncoder:  # type: ignore[type-arg]
    return CrossEncoder(_MODEL_NAME)


class Reranker:
    """Cross-encoder reranker over the fused candidate set.

    Runs inference on (query, chunk_text) pairs — a much richer signal than
    cosine distance, but O(n) inference cost makes it only practical over a
    small candidate window (top-20 from RRF → top-5 out).
    """

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        if not candidates:
            return []
        pairs = [[query, sc.chunk.text] for sc in candidates]
        scores: list[float] = _model().predict(pairs).tolist()  # type: ignore[union-attr]
        ranked = sorted(
            (ScoredChunk(sc.chunk, float(score)) for sc, score in zip(candidates, scores, strict=True)),
            key=lambda sc: sc.score,
            reverse=True,
        )
        return ranked[:top_k]
