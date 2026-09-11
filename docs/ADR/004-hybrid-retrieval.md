# ADR-004: Hybrid Retrieval (Dense + BM25 + RRF + Cross-Encoder)

**Status:** Accepted  
**Date:** 2026-09

---

## Context

Migration queries contain two distinct signal types that favor different retrieval mechanisms:

1. **Semantic meaning** — "how do I replace the timezone API" should match "switch to the dayjs-timezone plugin" even without lexical overlap. Dense embeddings handle this.
2. **Exact symbol names** — `moment().format()`, `useEffect`, `df.append()` are precise identifiers. A query containing `df.append()` should preferentially retrieve chunks that contain exactly that string. Dense embeddings blur exact terms; BM25 preserves them.

A retriever optimized for one signal type underperforms on the other. The ablation study (evals/run_eval.py variant 1 vs 2 vs 3) was designed specifically to measure this.

---

## Decision

Use **hybrid retrieval**: dense (Qdrant + bge-small-en-v1.5) + sparse (rank_bm25 in-memory) combined via **Reciprocal Rank Fusion** (k=60), then reranked by a **cross-encoder** (ms-marco-MiniLM-L-6-v2) over the fused top-20.

Each stage is independently toggleable via `HybridRetriever` constructor flags (`use_bm25`, `use_rerank`) so the ablation study can isolate contributions without code changes.

---

## Alternatives Considered

**Dense-only (Qdrant).**  
Baseline variant 1. Works well for semantic queries, degrades on exact symbol lookups. Included as the honest baseline.

**Sparse-only (BM25).**  
Not included as a standalone variant because the corpus is too small for BM25 to distinguish between packages on semantic meaning alone. BM25's value is as a complementary signal, not a replacement.

**Score normalization instead of RRF.**  
Rejected. Dense scores are cosine similarities (bounded [-1, 1]); BM25 scores are unbounded positive reals. Normalizing to a common scale requires knowing the score distribution in advance, which varies per query. RRF fuses on rank position — no normalization needed, no distribution assumptions, same formula regardless of corpus or query.

**Qdrant's built-in sparse vector support (SPLADE / BM42).**  
Considered. Qdrant supports sparse vectors natively which would avoid maintaining an in-memory BM25 index. Rejected for this build because: (1) SPLADE requires a separate model for encoding; (2) rank_bm25 over a ~300-document corpus is O(1) effectively; (3) keeping BM25 in-process simplifies the test surface (no Qdrant dependency for BM25 unit tests).

---

## Consequences

- The BM25 index is rebuilt in-memory at retriever construction time from the ChunkStore. At ~300 documents this is negligible; at 10K+ documents it would need to be persisted.
- The cross-encoder runs inference on (query, chunk_text) pairs synchronously. At top-20 candidates this takes ~200ms on CPU, acceptable for a CLI tool. For the API, consider running reranking in a thread pool executor if p95 latency becomes a concern.
- The `_RRF_CANDIDATE_K = 20` constant controls the reranker input size. Increasing it improves recall at the cost of reranking time linearly.
- Filtering by `package` before vector search (Qdrant payload index) is applied before both dense and sparse stages, which is the largest free precision win available.
