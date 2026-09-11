# Architecture Guide

## Layer Responsibilities

DDA follows Clean Architecture. The dependency rule is absolute: arrows point inward only.

```
┌──────────────────────────────────────────────────────────┐
│  Entrypoints                                              │
│  CLI (typer) · FastAPI · Streamlit                        │
└───────────────────────────┬──────────────────────────────┘
                            │ calls
┌───────────────────────────▼──────────────────────────────┐
│  Application layer  (src/dda/application/)                │
│  Use cases + services. Imports domain ports only.         │
│  ScanRepositoryUseCase · RiskScoringService               │
│  SignalCollector · ParserRegistry · ImpactService         │
└───────────────────────────┬──────────────────────────────┘
                            │ calls (via ABC ports)
┌───────────────────────────▼──────────────────────────────┐
│  Domain layer  (src/dda/domain/)                          │
│  Entities, value objects, port ABCs.                      │
│  Zero external imports. Pure Python stdlib only.          │
└───────────────────────────┬──────────────────────────────┘
                            ▲ implements
┌───────────────────────────┴──────────────────────────────┐
│  Infrastructure layer  (src/dda/infrastructure/)          │
│  All I/O. Implements the domain ports.                    │
│  parsers/ · signals/ · rag/ · llm/ · persistence/        │
│  analyzers/ · vcs/ · ui/                                  │
└──────────────────────────────────────────────────────────┘
```

### Domain layer (`src/dda/domain/`)

Imports nothing outside the Python standard library. Contains:

- **Entities** (`entities/`): frozen dataclasses. `Dependency`, `Signal`, `UsageSite`, `RiskScore`, `Chunk`, `Claim`, `MigrationPlan`, `Finding`, `Impact`.
- **Value objects** (`value_objects/`): `StrEnum` subclasses. `Ecosystem`, `Severity`, `Confidence`, `EffortEstimate`, `SignalType`.
- **Port ABCs** (`ports/`): abstract interfaces that the application layer calls and the infrastructure layer implements. `IManifestParser`, `ISignalSource`, `IUsageAnalyzer`, `IRetriever`, `ILLMClient`, `IVectorRepository`, `IScanRepository`, `IRepoFetcher`.

The domain layer has no knowledge that Qdrant, SQLite, or Gemini exist. Tests for this layer require zero mocks.

### Application layer (`src/dda/application/`)

Contains services and use cases that orchestrate domain objects via port interfaces.

- `ScanRepositoryUseCase`: full scan pipeline — fetch → parse → collect signals → score → persist.
- `RiskScoringService`: weighted signal → `RiskScore` with per-component breakdown and rationale.
- `SignalCollector`: async fan-out across signal sources, bounded semaphore, per-source error isolation.
- `ParserRegistry`: open/closed extension point for manifest parsers.
- `ImpactService`: cross-joins usage sites and signals → `Impact` with effort estimate.

Application code never imports from `infrastructure/`. If you find such an import, it's a bug.

### Infrastructure layer (`src/dda/infrastructure/`)

All I/O lives here. Organized by concern:

| Package | Implements | Key classes |
|---------|-----------|-------------|
| `parsers/` | `IManifestParser` | `PythonManifestParser`, `NpmManifestParser` |
| `signals/` | `ISignalSource` | `PyPIClient`, `NpmClient`, `OsvClient`, `EolClient`, `GitHubClient` |
| `analyzers/` | `IUsageAnalyzer` | `PythonAstAnalyzer`, `TreeSitterJsAnalyzer` |
| `rag/` | `IRetriever`, `IVectorRepository` | `HybridRetriever`, `QdrantVectorRepository`, `BM25Retriever`, `Embedder`, `Reranker` |
| `llm/` | `ILLMClient` | `GeminiClient`, `GroqClient`, `FallbackLLMClient` |
| `persistence/` | `IScanRepository` | `SqliteScanRepository`, `MigrationRunner` |
| `http/` | — | `BaseHttpClient` (cache, retry, circuit breaker) |
| `vcs/` | `IRepoFetcher` | `GitRepoFetcher` |
| `ui/` | — | Streamlit pages |

### Agent (`src/dda/agent/`)

The LangGraph state machine lives here rather than in `application/` because it directly wires concrete infrastructure collaborators (LLM clients, tool registry). It is closer to an entrypoint than a use case.

- `state.py`: `AgentState` TypedDict — the single shared state object threaded through all nodes.
- `nodes/`: one file per node. Each node is a plain function: `AgentState → AgentState`.
- `graph.py`: assembles nodes + edges, exposes `run_migration_agent()`.
- `tools/registry.py`: thin wrappers over signal sources and the retriever. The `search_migration_kb` tool is the **only** entry point to the vector store.
- `prompts/`: versioned `.txt` templates loaded by name. Never inline prompt strings in Python code.

---

## Adding a New Ecosystem

To add Go support, three files are needed and nothing else changes:

1. **`src/dda/infrastructure/parsers/go_parser.py`** — implement `IManifestParser` for `go.mod` and `go.sum`. Detect, parse, and return `Dependency` objects with `Ecosystem.GO`.

2. **`src/dda/infrastructure/analyzers/go_analyzer.py`** — implement `IUsageAnalyzer`. Walk `.go` files and resolve import paths to call sites.

3. **Register in the CLI and API wiring** — add `registry.register(GoManifestParser())` in `cli/main.py`'s `_parser_registry()` and the equivalent in `api/routes/scans.py`'s `_run_scan_task`.

The signal sources (`OsvClient`, `EolClient`, `GitHubClient`) already handle Go packages — `OsvClient` maps `Ecosystem.GO` to OSV's `"Go"` ecosystem. No changes needed there.

---

## Key Invariants

These are checked by the test suite or enforced structurally. Breaking them silently degrades correctness:

1. **`domain/` imports nothing external.** Verified by the fact that `tests/unit/domain/` tests have no fixture setup — if domain code imported infrastructure, those tests would fail to collect.

2. **`search_migration_kb` is the only RAG entry point.** All other agent tools call deterministic APIs. Verified by reading `AgentToolRegistry` — no other method calls `_retriever`.

3. **The bge query prefix is applied only to queries, never documents.** Enforced by `Embedder`'s separate `embed_query()` / `embed_documents()` methods. Applying the prefix to documents silently degrades precision.

4. **`RiskScore.total` equals the clamped sum of components.** Enforced by `__post_init__` validation — a `RiskScore` with a lying total cannot be constructed.

5. **Every HTTP response cache key includes source + url + body.** A POST to the same URL with a different body (e.g. OSV batch query for different packages) must not collide. Verified in `HttpCache.make_key`.

6. **Offline mode raises `OfflineCacheMissError`, never makes a network call.** The `@empty_on_offline_miss` decorator on all signal source `fetch` methods converts this to an empty list at the collector boundary.
