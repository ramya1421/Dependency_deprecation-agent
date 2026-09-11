# ADR-003: SQLite over Redis

**Status:** Accepted  
**Date:** 2026-09

---

## Context

The system needs to cache HTTP responses from signal sources (PyPI, OSV, GitHub, etc.) and LLM responses for evaluation re-runs. Both caches need TTL support. The HTTP cache also needs to be keyed on `sha256(source + url + body)` and support offline mode (serve from cache, raise on miss).

Redis is the conventional choice for application caching. It was explicitly evaluated.

---

## Decision

Use **SQLite** (WAL mode) with two tables: `http_cache` and `llm_cache`.

---

## Alternatives Considered

**Redis.**  
Rejected. Redis requires a running daemon, adds an infrastructure dependency, complicates local development setup, and costs money on every hosted tier. The workload here is single-process, low-concurrency (one scan at a time), and read-heavy once the cache is warm. SQLite in WAL mode handles this without contention. A key difference: Redis cache data is opaque and ephemeral; the SQLite cache is a plain file, inspectable with any SQL tool, and survives process restarts. The `--offline` flag, which serves an entire scan from the cache with zero network calls, is trivially implementable with SQLite and would require explicit serialization with Redis.

**In-process dict (lru_cache / functools).**  
Rejected. Dies on process restart. The `--offline` flag requires persistence across invocations, and LLM response caching only saves money if the cache survives between evaluation runs.

**DynamoDB / PostgreSQL.**  
Rejected as over-engineered. A single-file SQLite database has no operational overhead, no connection pooling, and no hosted cost. The step up to Postgres is warranted at multi-instance or multi-user scale, neither of which applies here.

---

## Consequences

- The `http_cache` table stores `(cache_key, response_body, status_code, cached_at, ttl_seconds)`. TTL is checked at read time — SQLite has no background eviction, so stale entries accumulate. This is acceptable; the table will not grow unboundedly in a single-scan workload.
- WAL mode (`PRAGMA journal_mode=WAL`) allows concurrent reads while a write is in progress, which matters during async signal collection where multiple coroutines may read the cache simultaneously.
- `PRAGMA foreign_keys=ON` is set on every connection so `scan_id` FK constraints are actually enforced. SQLite disables them by default, which silently allows orphaned rows.
- The entire database is a single file (`dda.db`), easy to back up, share for debugging, or delete to reset state.
