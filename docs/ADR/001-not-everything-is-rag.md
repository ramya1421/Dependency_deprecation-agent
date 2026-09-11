# ADR-001: Not Everything Is a RAG Problem

**Status:** Accepted  
**Date:** 2026-09

---

## Context

The initial design embedded all dependency information — deprecation flags, CVEs, EOL dates, registry metadata — into the vector store alongside migration prose. This felt natural: one retrieval path, one index, one latency budget.

The problem became visible during early testing. Querying "is moment deprecated?" returned chunks about *how to migrate from moment*, not the deprecation fact itself. The fact was in the index but dissolved into a nearest-neighbour search with no guarantee of exact retrieval. More critically, CVE records and EOL dates change on a timescale of days; a vector index refreshed weekly would serve stale advisories.

---

## Decision

Structured facts (deprecation flags, CVEs, EOL dates, GitHub repo activity) are fetched via **deterministic API calls**, not vector search. The vector store holds **only unstructured migration prose**: changelogs, migration guides, release notes.

The agent's `route` node classifies each sub-question as `STRUCTURED_FACT` or `PROSE_QUERY` and dispatches accordingly. `STRUCTURED_FACT` questions call PyPI, npm, OSV, endoflife.date, or GitHub directly. `PROSE_QUERY` questions call the hybrid retriever.

---

## Alternatives Considered

**Embed everything including structured facts.**  
Rejected. Cosine distance is not a reliable lookup mechanism for exact facts. "Is version 2.3.1 affected by CVE-2024-1234?" has a correct boolean answer; returning the five most similar chunks is not an answer.

**Separate vector collections for structured vs unstructured.**  
Rejected. Adds index management complexity without solving the core problem — structured facts are still degraded by going through an embedding model that wasn't trained to distinguish "affected: true" from "affected: false" in a JSON payload.

**Cache structured facts in the vector store payload, search by filter only.**  
Considered. Qdrant's payload filters are efficient, but this conflates storage with retrieval semantics. The deterministic API clients already do caching via the SQLite `http_cache` table, which is simpler and auditable without a running Qdrant instance.

---

## Consequences

- Signal sources (PyPI, OSV, etc.) must be kept up to date independently of the KB build cadence. The `http_cache` table handles this with configurable TTLs.
- The routing decision in the `route` node is a single point of classification error. If a question is misclassified as `PROSE_QUERY` when it should be `STRUCTURED_FACT`, it will get a retrieval answer that may be less precise. Prompt engineering and the plan node's schema mitigate this.
- The vector corpus is smaller and cleaner, which improves embedding quality and reduces Qdrant storage cost.
