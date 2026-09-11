from dataclasses import dataclass

from dda.domain.entities import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    """Carries every stage's score for one chunk, not just the final one —
    collapsing them into a single number would hide exactly what Step 11's
    ablation study needs to see.
    """

    chunk: Chunk
    dense_score: float | None
    sparse_score: float | None
    fused_score: float | None
    rerank_score: float | None
