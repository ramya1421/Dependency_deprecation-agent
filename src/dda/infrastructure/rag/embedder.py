from functools import lru_cache

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge models require this exact prefix on QUERIES ONLY, not on documents.
# Omitting it on queries silently degrades recall; applying it to documents
# silently degrades precision. The separate methods enforce the contract.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(_MODEL_NAME)


class Embedder:
    """Wraps bge-small-en-v1.5 with separate query and document methods so
    the instruction prefix cannot be applied incorrectly.
    """

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query with the required bge instruction prefix."""
        vec = _model().encode(_QUERY_PREFIX + text, normalize_embeddings=True)
        return vec.tolist()  # type: ignore[return-value]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed corpus documents WITHOUT the instruction prefix."""
        vecs = _model().encode(texts, normalize_embeddings=True, batch_size=64)
        return [v.tolist() for v in vecs]  # type: ignore[union-attr]
