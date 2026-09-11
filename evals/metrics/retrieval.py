"""Retrieval metrics: precision@K against labelled relevant_chunk_ids."""
from __future__ import annotations


def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Fraction of top-K retrieved chunks that are in the relevant set.

    Returns 0.0 when relevant_ids is empty (unanswerable — cannot be precise).
    The golden set's relevant_chunk_ids are hand-labelled after KB is built;
    entries with empty lists are skipped in aggregate reporting.
    """
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    hits = sum(1 for cid in top_k if cid in relevant_set)
    return hits / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Fraction of relevant chunks found in the top-K retrieved set."""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    relevant_set = set(relevant_ids)
    hits = sum(1 for cid in relevant_set if cid in top_k)
    return hits / len(relevant_set)


def mean_precision(results: list[dict], k: int = 5) -> float:
    """Mean precision@K across all results that have non-empty relevant_chunk_ids."""
    scored = [
        precision_at_k(r["retrieved_chunk_ids"], r["relevant_chunk_ids"], k)
        for r in results
        if r.get("relevant_chunk_ids")
    ]
    return sum(scored) / len(scored) if scored else 0.0


def mean_recall(results: list[dict], k: int = 5) -> float:
    scored = [
        recall_at_k(r["retrieved_chunk_ids"], r["relevant_chunk_ids"], k)
        for r in results
        if r.get("relevant_chunk_ids")
    ]
    return sum(scored) / len(scored) if scored else 0.0
