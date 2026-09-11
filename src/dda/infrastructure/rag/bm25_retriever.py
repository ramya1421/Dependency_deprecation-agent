import re

from rank_bm25 import BM25Okapi

from dda.domain.entities import Chunk
from dda.infrastructure.rag._scoring import ScoredChunk

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    # Deliberately simple word-boundary splitting, not stemming/lowercasing
    # everything away — BM25's whole value here is catching exact symbol
    # names (useEffect, moment().format) that dense embeddings blur.
    return _TOKEN_RE.findall(text.lower())


class BM25Retriever:
    """rank_bm25 over the whole corpus, in memory — the corpus is small
    enough (Step 6's target: 150-300 documents) that this is trivial, no
    external index needed.
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in chunks]) if chunks else None

    def search(self, query: str, package: str | None, top_k: int) -> list[ScoredChunk]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        scored = [
            ScoredChunk(chunk, float(score))
            for chunk, score in zip(self._chunks, scores, strict=True)
            if (package is None or chunk.package.lower() == package.lower()) and score > 0
        ]
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_k]
