"""Six-variant ablation evaluation runner.

Variants (each builds on the previous):
  1. naive_dense_only          — dense top-5, single LLM call, no tools
  2. hybrid_bm25_rrf           — + BM25 + RRF fusion
  3. hybrid_rerank             — + cross-encoder reranking
  4. agent_routing             — + agentic planning and structured-fact routing
  5. agent_reflection          — + reflection loop (up to 3 iterations)
  6. full_system               — + citation verification (full DDA pipeline)

Usage:
    python evals/run_eval.py [--variants 1,2,3] [--limit 10] [--output evals/results.md]

LLM responses are SQLite-cached so re-runs are free on a 15 RPM free tier.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"
_RESULTS_DIR = Path(__file__).parent / "results"
_CHUNKS_DIR = Path("data/kb/chunks")


def load_golden_set(limit: int | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with _GOLDEN_SET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[:limit] if limit else entries


def _build_infrastructure(
    settings: Any, connection: sqlite3.Connection
) -> tuple[Any, Any, Any, Any, Any]:
    """Return (llm, judge_llm, embedder, vector_repo, bm25) — lazy imports
    keep startup fast when only some variants are needed."""
    from dda.infrastructure.llm.fallback_client import FallbackLLMClient
    from dda.infrastructure.llm.gemini_client import GeminiClient
    from dda.infrastructure.llm.groq_client import GroqClient
    from dda.infrastructure.rag.bm25_retriever import BM25Retriever
    from dda.infrastructure.rag.chunk_store import ChunkStore
    from dda.infrastructure.rag.embedder import Embedder
    from dda.infrastructure.rag.qdrant_repository import QdrantVectorRepository

    gemini = GeminiClient(settings.gemini_api_key or "", connection) if settings.gemini_api_key else None
    groq = GroqClient(settings.groq_api_key or "", connection) if settings.groq_api_key else None
    if gemini and groq:
        llm: Any = FallbackLLMClient(gemini, groq)
        judge_llm: Any = groq
    elif gemini:
        llm = gemini
        judge_llm = gemini
    elif groq:
        llm = groq
        judge_llm = groq
    else:
        raise RuntimeError("Set GEMINI_API_KEY or GROQ_API_KEY in .env")

    embedder = Embedder()
    vector_repo = QdrantVectorRepository(settings.qdrant_url or "", settings.qdrant_api_key)

    store = ChunkStore(_CHUNKS_DIR)
    all_chunks = [c for chunks in store.load_all().values() for c in chunks]
    bm25 = BM25Retriever(all_chunks)

    return llm, judge_llm, embedder, vector_repo, bm25


async def _run_variant(
    variant_id: int,
    entries: list[dict[str, Any]],
    llm: Any,
    judge_llm: Any,
    embedder: Any,
    vector_repo: Any,
    bm25: Any,
    connection: sqlite3.Connection,
    settings: Any,
) -> list[dict[str, Any]]:
    """Run all golden-set entries through one variant configuration."""
    from dda.evals_support import build_retriever_for_variant, run_entry_through_variant
    results: list[dict[str, Any]] = []
    retriever = build_retriever_for_variant(variant_id, vector_repo, bm25, embedder)
    for entry in entries:
        t0 = time.perf_counter()
        result = await run_entry_through_variant(
            variant_id, entry, llm, judge_llm, retriever, connection, settings
        )
        elapsed = time.perf_counter() - t0
        result["latency_seconds"] = elapsed
        result["variant_id"] = variant_id
        result["question_id"] = entry["id"]
        result["category"] = entry.get("category", "")
        result["is_adversarial"] = entry.get("is_adversarial", False)
        result["relevant_chunk_ids"] = entry.get("relevant_chunk_ids", [])
        results.append(result)
        print(f"  [{variant_id}] {entry['id']}  {elapsed:.1f}s")
    return results


def _compute_metrics(
    results: list[dict[str, Any]],
    judge_llm: Any,
    chunk_map: dict[str, Any],
) -> dict[str, float]:
    """Aggregate metrics across all results for one variant."""
    from evals.metrics.faithfulness import extract_claims, faithfulness_score, hallucination_rate
    from evals.metrics.latency import summarise
    from evals.metrics.retrieval import mean_precision, mean_recall

    latencies = [r["latency_seconds"] for r in results]
    lat = summarise(latencies)

    # Retrieval metrics (only entries with labelled relevant_chunk_ids).
    p_at_5 = mean_precision(results, k=5)
    rec_at_5 = mean_recall(results, k=5)

    # Hallucination: fraction of cited chunks not in retrieved set.
    hallucination_scores = []
    for r in results:
        retrieved_set = set(r.get("retrieved_chunk_ids", []))
        answer = str(r.get("answer", ""))
        hallucination_scores.append(hallucination_rate(answer, retrieved_set))
    mean_hallucination = sum(hallucination_scores) / len(hallucination_scores) if hallucination_scores else 0.0

    # Faithfulness: LLM judge (expensive — run only when judge_llm available).
    faithfulness_scores: list[float] = []
    for r in results[:10]:   # Sample first 10 to limit judge LLM calls
        answer = str(r.get("answer", ""))
        claims = extract_claims(answer, chunk_map)
        if claims:
            score = faithfulness_score(claims, {k: v.text for k, v in chunk_map.items()}, judge_llm)
            faithfulness_scores.append(score)
    mean_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0

    return {
        "p50_latency": lat["p50"],
        "p95_latency": lat["p95"],
        "mean_latency": lat["mean"],
        "precision_at_5": p_at_5,
        "recall_at_5": rec_at_5,
        "hallucination_rate": mean_hallucination,
        "faithfulness": mean_faithfulness,
        "n": len(results),
    }


def _write_results_md(
    all_metrics: dict[int, dict[str, float]],
    output_path: Path,
) -> None:
    _VARIANT_NAMES = {
        1: "1. Naive dense-only",
        2: "2. + Hybrid BM25 + RRF",
        3: "3. + Cross-encoder reranking",
        4: "4. + Agentic planning & routing",
        5: "5. + Reflection loop",
        6: "6. + Citation verification (full system)",
    }
    lines = [
        "# DDA Evaluation Results",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Ablation Table",
        "",
        "| Variant | P@5 | Recall@5 | Faithfulness | Hallucination | p50 (s) | p95 (s) |",
        "|---------|-----|----------|--------------|---------------|---------|---------|",
    ]
    for vid, metrics in sorted(all_metrics.items()):
        name = _VARIANT_NAMES.get(vid, f"Variant {vid}")
        lines.append(
            f"| {name} "
            f"| {metrics['precision_at_5']:.3f} "
            f"| {metrics['recall_at_5']:.3f} "
            f"| {metrics['faithfulness']:.3f} "
            f"| {metrics['hallucination_rate']:.3f} "
            f"| {metrics['p50_latency']:.1f} "
            f"| {metrics['p95_latency']:.1f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Precision@5 and Recall@5 are computed only for golden-set entries",
        "  with hand-labelled `relevant_chunk_ids`. Entries without labels are excluded.",
        "- Faithfulness is computed by an independent LLM judge (Groq judging Gemini)",
        "  on a 10-entry sample per variant to limit API cost.",
        "- Hallucination rate = citations referencing chunks not in the retrieved set.",
        "- Latency includes end-to-end wall time per question (retrieval + LLM calls).",
        "",
        "## Threats to Validity",
        "",
        "- **Small N**: 40 golden-set questions is sufficient for directional comparison",
        "  but not for statistical significance testing.",
        "- **Self-labelling bias**: expected_facts and relevant_chunk_ids were labelled",
        "  by the same person who built the system. Independent labelling would be",
        "  preferable for publication-grade claims.",
        "- **LLM judge variance**: faithfulness scores vary with judge model and prompt.",
        "  The same judge model is used consistently across variants to make comparisons",
        "  internally valid even if absolute scores are uncertain.",
        "- **Corpus coverage**: the KB covers ~30 packages. Questions about packages not",
        "  in the KB will score 0 precision/recall regardless of system quality.",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to {output_path}")


async def main(
    variant_ids: list[int],
    limit: int | None,
    output_path: Path,
) -> None:
    from dda.config.settings import Settings
    from dda.infrastructure.persistence.connection import connect
    from dda.infrastructure.persistence.migration_runner import MigrationRunner
    from dda.infrastructure.rag.chunk_store import ChunkStore

    settings = Settings()
    connection = connect(Path(settings.database_path))
    MigrationRunner(connection).apply_all()

    entries = load_golden_set(limit)
    print(f"Running {len(entries)} golden-set entries across variants {variant_ids}")

    llm, judge_llm, embedder, vector_repo, bm25 = _build_infrastructure(settings, connection)

    # Build chunk_map for metrics.
    store = ChunkStore(_CHUNKS_DIR)
    chunk_map = {
        c.chunk_id: c
        for chunks in store.load_all().values()
        for c in chunks
    }

    all_metrics: dict[int, dict[str, float]] = {}
    all_results: list[dict[str, Any]] = []

    for vid in variant_ids:
        print(f"\n=== Variant {vid} ===")
        results = await _run_variant(
            vid, entries, llm, judge_llm, embedder, vector_repo, bm25, connection, settings
        )
        metrics = _compute_metrics(results, judge_llm, chunk_map)
        all_metrics[vid] = metrics
        all_results.extend(results)

        print(f"  P@5={metrics['precision_at_5']:.3f}  "
              f"Faithfulness={metrics['faithfulness']:.3f}  "
              f"Hallucination={metrics['hallucination_rate']:.3f}  "
              f"p50={metrics['p50_latency']:.1f}s")

    # Save citation audit CSV.
    from evals.metrics.citation_audit import export_citation_csv
    csv_path = output_path.parent / "citation_audit.csv"
    n_rows = export_citation_csv(all_results, chunk_map, csv_path)
    print(f"Citation audit CSV: {n_rows} rows → {csv_path}")

    # Save full results JSON.
    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")

    # Save markdown table.
    _write_results_md(all_metrics, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DDA ablation evaluation")
    parser.add_argument(
        "--variants",
        default="1,2,3,4,5,6",
        help="Comma-separated variant IDs to run (default: all six)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of golden-set entries (useful for smoke tests)",
    )
    parser.add_argument(
        "--output",
        default="evals/results.md",
        help="Output markdown file path",
    )
    args = parser.parse_args()
    variant_ids = [int(v.strip()) for v in args.variants.split(",")]
    asyncio.run(main(variant_ids, args.limit, Path(args.output)))
