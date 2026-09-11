from dda.infrastructure.rag._scoring import ScoredChunk

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[ScoredChunk]], k: int = DEFAULT_K
) -> list[ScoredChunk]:
    """Combines multiple ranked lists (e.g. dense + sparse) by rank position,
    not raw score — dense cosine similarity and BM25 scores live on
    incomparable scales, so fusing on rank avoids needing to normalise
    between them. score = sum(1 / (k + rank)) per ranking a chunk appears in.
    """
    fused_scores: dict[str, float] = {}
    chunks_by_id: dict[str, ScoredChunk] = {}
    for ranking in rankings:
        for rank, scored in enumerate(ranking, start=1):
            chunk_id = scored.chunk.chunk_id
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk_id] = scored

    fused = [
        ScoredChunk(chunks_by_id[chunk_id].chunk, score)
        for chunk_id, score in fused_scores.items()
    ]
    fused.sort(key=lambda sc: sc.score, reverse=True)
    return fused
