"""Variant dispatch helpers for the evaluation runner.

Lives in src/dda/ so it can import from the main package without sys.path
gymnastics. Imported only by evals/run_eval.py.

Each variant builds on the previous:
  1 = naive dense
  2 = + BM25 + RRF
  3 = + rerank
  4 = + agent routing
  5 = + reflection
  6 = + citation verification (full system)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dda.domain.ports import ILLMClient, IRetriever, IVectorRepository


def build_retriever_for_variant(
    variant_id: int,
    vector_repo: IVectorRepository,
    bm25: Any,
    embedder: Any,
) -> IRetriever:
    """Return a HybridRetriever configured for the given variant."""
    from dda.infrastructure.rag.hybrid_retriever import HybridRetriever
    from dda.infrastructure.rag.reranker import Reranker

    use_bm25 = variant_id >= 2
    use_rerank = variant_id >= 3

    return HybridRetriever(
        vector_repository=vector_repo,
        bm25_retriever=bm25,
        embedder=embedder,
        reranker=Reranker(),
        use_bm25=use_bm25,
        use_rerank=use_rerank,
    )


async def run_entry_through_variant(
    variant_id: int,
    entry: dict[str, Any],
    llm: ILLMClient,
    judge_llm: ILLMClient,
    retriever: IRetriever,
    connection: sqlite3.Connection,
    settings: Any,
) -> dict[str, Any]:
    """Dispatch one golden-set entry to the correct variant pipeline."""
    if variant_id <= 3:
        return _run_naive(entry, llm, retriever)
    return await _run_agent(variant_id, entry, llm, judge_llm, retriever, connection, settings)


def _run_naive(
    entry: dict[str, Any],
    llm: ILLMClient,
    retriever: IRetriever,
) -> dict[str, Any]:
    """Variants 1-3: naive single-shot retrieval + one LLM call."""
    from evals.baselines.naive_rag import NaiveRagBaseline
    from dda.infrastructure.rag.embedder import Embedder

    # NaiveRagBaseline owns its own embedder for the query; retriever is passed
    # through HybridRetriever which owns its own embedder for consistency.
    # We reach into the retriever's embedder to avoid loading two model copies.
    embedder_inst = getattr(retriever, "_embedder", Embedder())

    class _RetrieverWrapper:
        """Thin adapter so NaiveRagBaseline can call retriever.search()."""
        def __init__(self, r: IRetriever, e: Any) -> None:
            self._r = r
            self._e = e

        def search(self, vector: list[float], filters: Any, top_k: int) -> list[Any]:
            # Delegate to the underlying IVectorRepository's search.
            vr = getattr(self._r, "_vector_repository", None)
            if vr is not None:
                return vr.search(vector, filters, top_k)
            return []

    from evals.baselines.naive_rag import NaiveRagBaseline
    baseline = NaiveRagBaseline(
        vector_repository=_RetrieverWrapper(retriever, embedder_inst),  # type: ignore[arg-type]
        embedder=embedder_inst,
        llm=llm,
        top_k=5,
    )
    return baseline.answer(entry["question"], entry.get("package"))


async def _run_agent(
    variant_id: int,
    entry: dict[str, Any],
    llm: ILLMClient,
    judge_llm: ILLMClient,
    retriever: IRetriever,
    connection: sqlite3.Connection,
    settings: Any,
) -> dict[str, Any]:
    """Variants 4-6: run through the LangGraph agent with selected caps."""
    from dda.agent.graph import build_graph
    from dda.agent.nodes.reflect import MAX_REFLECTIONS
    from dda.agent.state import AgentState
    from datetime import UTC, datetime
    import uuid

    # Variant 4 caps reflection at 0 (routing only, no reflection loop).
    # Variant 5 allows full reflection. Variant 6 adds verify node.
    # We control this by patching the graph's MAX_REFLECTIONS at import time
    # or by using the graph as-is (variant 6 uses the full graph).
    # Simplest: variants 4 and 5 skip verify by using FakeVerifyLLM.
    if variant_id == 4:
        effective_judge = _NoVerifyLLM()
        reflection_cap = 0
    elif variant_id == 5:
        effective_judge = _NoVerifyLLM()
        reflection_cap = MAX_REFLECTIONS
    else:  # variant 6: full system
        effective_judge = judge_llm
        reflection_cap = MAX_REFLECTIONS

    # Build a minimal tool registry without live signal sources for eval.
    tools = _build_eval_tools(retriever, settings)

    graph = build_graph(llm, effective_judge, tools, connection)
    compiled = graph.compile()

    initial: AgentState = {
        "package": entry.get("package", ""),
        "ecosystem": "python",
        "repo_root": str(Path("tests/fixtures/repos/stale-flask")),
        "usage_sites": [],
        "signals_summary": "",
        "sub_questions": [],
        "retrieved_chunks": [],
        "structured_facts": {},
        "draft_plan": "",
        "draft_steps": [],
        "claims": [],
        "verified_claims": [],
        "reflection_count": 0,
        "tool_call_count": 0,
        "route_history": [],
        "errors": [],
        "started_at": datetime.now(UTC),
        "migration_plan": None,
    }

    # Patch reflection cap for variant 4.
    if variant_id == 4:
        import dda.agent.nodes.reflect as reflect_mod
        _orig = reflect_mod.MAX_REFLECTIONS
        reflect_mod.MAX_REFLECTIONS = 0  # type: ignore[attr-defined]

    try:
        final: dict[str, Any] = await compiled.ainvoke(initial)
    finally:
        if variant_id == 4:
            reflect_mod.MAX_REFLECTIONS = _orig  # type: ignore[attr-defined]

    plan = final.get("migration_plan") or {}
    steps: list[str] = plan.get("steps", [])
    claims: list[dict[str, Any]] = plan.get("claims", [])

    return {
        "question": entry["question"],
        "package": entry.get("package"),
        "answer": plan.get("summary", "") + " " + " ".join(steps),
        "retrieved_chunk_ids": [c.chunk_id for c in final.get("retrieved_chunks", [])],
        "claims": claims,
        "route_history": final.get("route_history", []),
        "variant": f"variant_{variant_id}",
    }


def _build_eval_tools(retriever: IRetriever, settings: Any) -> Any:
    """Minimal AgentToolRegistry for evaluation — no live HTTP calls."""
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock
    from dda.agent.tools.registry import AgentToolRegistry

    # Use async mocks for signal sources so the agent graph runs without
    # real API keys during evaluation.
    mock_source = MagicMock()
    mock_source.fetch = AsyncMock(return_value=[])
    mock_source.source_name = "mock"

    return AgentToolRegistry(
        pypi_client=mock_source,  # type: ignore[arg-type]
        npm_client=mock_source,   # type: ignore[arg-type]
        osv_client=mock_source,   # type: ignore[arg-type]
        eol_client=mock_source,   # type: ignore[arg-type]
        github_client=mock_source, # type: ignore[arg-type]
        retriever=retriever,
        usage_analyzers=[],
        repo_root=Path("tests/fixtures/repos/stale-flask"),
    )


class _NoVerifyLLM(ILLMClient):
    """Judge LLM that approves every claim — used for variants 4 and 5
    where verification is intentionally disabled to isolate its contribution."""

    def generate(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        return "supported"

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], system: str = "", temperature: float = 0.0
    ) -> dict[str, Any]:
        return {"supported": True, "entailment_score": 1.0, "reason": "eval-bypass"}
