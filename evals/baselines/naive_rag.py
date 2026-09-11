"""Naive RAG baseline for ablation comparison.

Intentionally simple: same corpus, same bge-small embeddings, single-shot
dense top-5, NO BM25, NO reranking, NO agent routing, NO reflection, NO
citation verification. One LLM call, one retrieval call, done.

Building this honestly matters: a rigged baseline inflates every downstream
number and is transparent to any reviewer. A fair baseline we still beat is
the actual story.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dda.domain.entities import Chunk
from dda.domain.ports import ILLMClient, IVectorRepository
from dda.infrastructure.rag.embedder import Embedder

_SYSTEM = (
    "You are a dependency migration expert. Answer the question using ONLY the "
    "provided context. If the context does not contain the answer, say so explicitly."
)

_PROMPT_TEMPLATE = """\
Question: {question}

Context (top-{k} dense retrieval results):
{context}

Answer the question based solely on the context above.
"""


class NaiveRagBaseline:
    """Single-shot dense retrieval + single LLM call. No agent, no tools."""

    def __init__(
        self,
        vector_repository: IVectorRepository,
        embedder: Embedder,
        llm: ILLMClient,
        top_k: int = 5,
    ) -> None:
        self._repo = vector_repository
        self._embedder = embedder
        self._llm = llm
        self._top_k = top_k

    def answer(self, question: str, package: str | None = None) -> dict[str, Any]:
        """Run naive RAG and return answer + retrieved chunk IDs."""
        filters = {"package": package} if package else None
        query_vec = self._embedder.embed_query(question)
        chunks = self._repo.search(query_vec, filters, self._top_k)

        context = _format_context(chunks)
        prompt = _PROMPT_TEMPLATE.format(
            question=question,
            k=self._top_k,
            context=context,
        )
        answer_text = self._llm.generate(prompt, system=_SYSTEM, temperature=0.1)

        return {
            "question": question,
            "package": package,
            "answer": answer_text,
            "retrieved_chunk_ids": [c.chunk_id for c in chunks],
            "variant": "naive_dense_only",
        }


def _format_context(chunks: list[Chunk]) -> str:
    if not chunks:
        return "No relevant context found."
    parts = [
        f"[{c.chunk_id}] {c.header_path}\n{c.text}"
        for c in chunks
    ]
    return "\n\n---\n\n".join(parts)
