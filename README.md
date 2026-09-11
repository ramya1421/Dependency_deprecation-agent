<div align="center">

# 🔍 Dependency Deprecation Agent

### *Dependabot tells you **what** to upgrade.*
### *DDA tells you **what it'll break, where, and how to fix it** — with citations.*

<br/>

[![CI](https://img.shields.io/github/actions/workflow/status/ramya1421/dependency-deprecation-agent/ci.yml?style=for-the-badge&logo=github&label=CI)](https://github.com/ramya1421/dependency-deprecation-agent/actions)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![mypy strict](https://img.shields.io/badge/mypy-strict-2596be?style=for-the-badge)](https://mypy.readthedocs.io)
[![ruff](https://img.shields.io/badge/ruff-passing-D7FF64?style=for-the-badge)](https://docs.astral.sh/ruff)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent-orange?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

<br/>

</div>

---

## 📌 Table of Contents

- [The Problem](#-the-problem)
- [What Makes DDA Different](#-what-makes-dda-different)
- [System Overview](#-system-overview)
- [Architecture](#-architecture)
- [The LangGraph Agent](#-the-langgraph-agent)
- [Retrieval Pipeline](#-retrieval-pipeline)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Quickstart](#-quickstart)
- [CLI Reference](#-cli-reference)
- [API Reference](#-api-reference)
- [Evaluation](#-evaluation)
- [Key Design Decisions](#-key-design-decisions)
- [Limitations](#-limitations)
- [Roadmap](#-roadmap)
- [Architecture Decision Records](#-architecture-decision-records)

---

## 🚨 The Problem

Every engineering team runs into this: a dependency is deprecated, a CVE drops, or a framework goes EOL. Existing tools tell you *a package needs updating*. None of them tell you what that upgrade will actually break in your codebase.

| Tool | What it tells you | What it doesn't |
|---|---|---|
| Dependabot / Renovate | Packages with newer versions available | What your code will break |
| Snyk / Trivy | CVEs that affect you | How to fix the affected call sites |
| `pip list --outdated` | Version gap | Anything about your actual code |
| **DDA** ✅ | All of the above + exact call sites + cited migration steps | — |

**The gap DDA fills:** You need to know *which symbols* you're importing from the deprecated package, *which files* use them, and *exactly how* the API changed — with a source you can verify.

---

## ✨ What Makes DDA Different

```
Traditional tools:   flask 0.10.1  →  upgrade to 3.x  ⚠️
                     (that's all you get)

DDA:                 flask 0.10.1  →  upgrade to 3.x
                     ├─ 📍 app.py:14   Flask.__init__()      [STATIC_CONFIRMED]
                     ├─ 📍 app.py:31   flask.jsonify()        [STATIC_CONFIRMED]
                     ├─ 📍 views.py:8  flask.request.form     [STATIC_CONFIRMED]
                     │
                     ├─ 📖 Migration steps (cited from Flask 2.0 changelog):
                     │   1. Remove before_first_request decorator [abc123ef]
                     │   2. Replace app.json_encoder with app.json.provider [def456gh]
                     │   3. Update error handlers to use @app.errorhandler [ghi789ij]
                     │
                     └─ ⚡ Effort estimate: MEDIUM (3 call sites, 2 files)
                        🔒 3 claims verified by independent LLM judge
```

---

## 🗺 System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INPUT: Git Repository                              │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
              ┌───────────────────┼────────────────────┐
              ▼                   ▼                    ▼
   ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │  Manifest Parser │  │ Signal Collector  │  │  Usage Analyzer  │
   │                 │  │                  │  │                  │
   │ requirements.txt│  │ PyPI  npm  OSV   │  │ Python AST       │
   │ pyproject.toml  │  │ GitHub  EOL date │  │ tree-sitter JS   │
   │ package.json    │  │                  │  │                  │
   │ poetry.lock     │  │ async fan-out    │  │ file:line:symbol  │
   └────────┬────────┘  │ SQLite cache     │  │ confidence tier  │
            │           └────────┬─────────┘  └────────┬─────────┘
            │                    │                      │
            └────────────────────┼──────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │    Risk Scoring        │
                    │                        │
                    │  deprecated  +30       │
                    │  CVE high    +25       │
                    │  abandoned   +20       │
                    │  EOL         +15       │
                    │  outdated    +10       │
                    │                        │
                    │  → RiskScore (0–100)   │
                    │    + rationale list    │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   LangGraph Agent      │◄── Migration KB
                    │   (migration planner)  │    (Qdrant + BM25)
                    └────────────┬───────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────┐
              │         OUTPUT: MigrationPlan         │
              │                                       │
              │  summary · steps · claims (verified)  │
              │  usage_sites · effort estimate        │
              └──────────────────────────────────────┘
                         │              │
              ┌──────────▼───┐   ┌──────▼──────────┐
              │  CLI (rich)  │   │  FastAPI + UI    │
              │  dda migrate │   │  Streamlit dash  │
              └──────────────┘   └─────────────────┘
```

---

## 🏛 Architecture

DDA follows **Clean Architecture** — the dependency rule is absolute: arrows point inward only.

```
╔══════════════════════════════════════════════════════════════╗
║              ENTRYPOINTS  (no business logic)                ║
║   CLI (typer)  │  FastAPI :8000  │  Streamlit :8501          ║
╠══════════════════════════════════════════════════════════════╣
║              APPLICATION LAYER                               ║
║   ScanRepositoryUseCase  ·  RiskScoringService               ║
║   SignalCollector  ·  ParserRegistry  ·  ImpactService       ║
║   ↑ imports domain ports only — never infrastructure         ║
╠══════════════════════════════════════════════════════════════╣
║              DOMAIN LAYER  (pure Python stdlib)              ║
║   Entities: Dependency · Signal · Finding · MigrationPlan    ║
║   Value Objects: Severity · Ecosystem · Confidence           ║
║   Ports (ABCs): ISignalSource · IRetriever · ILLMClient …    ║
╠══════════════════════════════════════════════════════════════╣
║              INFRASTRUCTURE LAYER  (all I/O here)            ║
║   parsers/   signals/   rag/   llm/   persistence/           ║
║   analyzers/   vcs/   http/   ui/                            ║
╚══════════════════════════════════════════════════════════════╝
```

**Why this matters:** Every external call goes through an ABC port, so any component can be faked in tests. The 155-test suite runs with zero network calls and no API keys.

---

## 🤖 The LangGraph Agent

The migration planner is an explicit, inspectable state machine — not a black-box ReAct loop. Each node is a plain Python function; control flow lives in code, not in prompts.

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  plan   │  ← decompose into sub-questions
                    │         │    grounded in actual call sites
                    └────┬────┘
                         │
                    ┌────▼────┐
              ┌────►│  route  │  ← classify: STRUCTURED_FACT
              │     │         │              or PROSE_QUERY
              │     └────┬────┘
              │          │
              │     ┌────▼──────┐
              │     │ retrieve  │  STRUCTURED_FACT → PyPI/OSV/GitHub API
              │     │           │  PROSE_QUERY     → Hybrid RAG retriever
              │     └────┬──────┘
              │          │
              │     ┌────▼──────┐
              │     │  reflect  │  ← LLM judges context sufficiency
              │     │           │    insufficient + count < 3?
              └─────┤           ├──► inject reformulated query → route
                    └────┬──────┘
                         │ sufficient or cap reached
                    ┌────▼──────────┐
                    │  synthesize   │  ← draft plan, temp=0.1
                    │               │    inline [chunk_id] citations
                    └────┬──────────┘
                         │
                    ┌────▼──────────┐
                    │    verify     │  ← Groq judges Gemini's claims
                    │               │    drops unsupported claims
                    └────┬──────────┘
                         │ >30% dropped?
                         │──────────────► synthesize (one retry)
                         │ ≤30% dropped
                    ┌────▼──────────┐
                    │   finalize    │  ← assemble MigrationPlan entity
                    └────┬──────────┘
                         │
                    ┌────▼────┐
                    │   END   │
                    └─────────┘
```

**Hard caps enforced in code (not prompts):**
- Max 3 reflection iterations
- Max 12 tool calls per run
- One synthesis retry on high claim drop-rate
- Every node transition persisted to `agent_runs` table for full replay

---

## 🔍 Retrieval Pipeline

The critical insight: **not everything is a RAG problem.**

```
Query: "how do I replace moment().format()?"
           │
           ▼
   ┌───────────────┐
   │  Route node   │  PROSE_QUERY → retrieval path below
   │  classifies   │  STRUCTURED_FACT → direct API call (never RAG)
   └───────┬───────┘
           │ PROSE_QUERY
           ▼
┌──────────────────────────────────────────────────────┐
│                  Hybrid Retriever                     │
│                                                       │
│  1. embed_query()  ←  "Represent this sentence for   │
│     bge-small-en-v1.5   searching relevant passages: │
│     (query prefix applied, never to documents)        │
│                                                       │
│  2. Qdrant dense search  ──┐                         │
│     384-dim cosine          │                         │
│     filtered by package     ├──► RRF fusion (k=60)   │
│                             │    rank-based, no       │
│  3. BM25 sparse search  ───┘    normalisation needed │
│     exact symbol matching                             │
│     (useEffect, df.append, moment.format)             │
│                                                       │
│  4. Cross-encoder reranking                          │
│     ms-marco-MiniLM-L-6-v2                           │
│     top-20 fused → top-5 reranked                    │
└──────────────────────────────────────────────────────┘
           │
           ▼
    top-5 chunks with scores at every stage
    (ablation flags: --dense-only, --no-rerank)
```

**Why BM25 + dense instead of dense alone:** Dense embeddings blur exact symbol names. A query for `moment().format()` might match "date formatting" semantically but miss the exact breaking-change note that says `.format()` was removed. BM25 preserves exact token matches; RRF combines both rankings without needing a shared score scale.

---

## 🛠 Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Language** | Python 3.11+ | Type safety, async, stdlib AST |
| **Agent framework** | LangGraph | Explicit inspectable state machine |
| **Primary LLM** | Gemini 2.0 Flash | Fast, structured output, cost-effective |
| **Fallback LLM** | Groq Llama 3.3 70B | Independent judge + 429 fallback |
| **Embeddings** | BAAI/bge-small-en-v1.5 | 384-dim, fits in Qdrant free tier |
| **Reranker** | ms-marco-MiniLM-L-6-v2 | Cross-encoder, CPU-viable |
| **Vector store** | Qdrant Cloud | Payload-indexed filtered search |
| **Sparse retrieval** | rank-bm25 | Exact symbol name matching |
| **HTTP layer** | httpx + tenacity | Async, retry, circuit breaker |
| **Persistence** | SQLite (WAL) | Zero infra, offline mode, inspectable |
| **API** | FastAPI + uvicorn | Async, Pydantic schemas, BackgroundTasks |
| **UI** | Streamlit | Rapid dashboard, 6-hour timebox |
| **CLI** | typer + rich | Rich tables, trace output |
| **JS analysis** | tree-sitter | Error-tolerant, handles syntax errors |
| **Python analysis** | stdlib ast | Alias resolution, importlib detection |
| **CI** | GitHub Actions | ruff + mypy + pytest + docker build |
| **Containers** | Docker multi-stage | Pre-baked HuggingFace models |

**Explicitly not used:** Redis (SQLite cache is sufficient), Celery (BackgroundTasks is enough), LangChain AgentExecutor (LangGraph gives inspectable state), Postgres, React.

---

## 📁 Project Structure

```
dependency-deprecation-agent/
│
├── src/dda/
│   ├── domain/                  # Pure Python — zero external imports
│   │   ├── entities/            # Dependency, Signal, Finding, MigrationPlan …
│   │   ├── value_objects/       # Severity, Ecosystem, Confidence …
│   │   └── ports/               # ABCs: ISignalSource, IRetriever, ILLMClient …
│   │
│   ├── application/             # Use cases + services (depends on domain only)
│   │   ├── use_cases/           # ScanRepositoryUseCase
│   │   └── services/            # RiskScoringService, SignalCollector, ParserRegistry
│   │
│   ├── infrastructure/          # All I/O — implements the domain ports
│   │   ├── parsers/             # PythonManifestParser, NpmManifestParser
│   │   ├── signals/             # PyPIClient, NpmClient, OsvClient, EolClient, GitHubClient
│   │   ├── analyzers/           # PythonAstAnalyzer, TreeSitterJsAnalyzer
│   │   ├── rag/                 # Embedder, QdrantRepo, BM25, Fusion, Reranker, HybridRetriever
│   │   ├── llm/                 # GeminiClient, GroqClient, FallbackClient, LLMCache
│   │   ├── persistence/         # SqliteScanRepository, MigrationRunner
│   │   ├── http/                # BaseHttpClient (cache + retry + circuit breaker)
│   │   ├── vcs/                 # GitRepoFetcher
│   │   └── ui/                  # Streamlit pages
│   │
│   ├── agent/                   # LangGraph state machine
│   │   ├── nodes/               # plan, route, retrieve, reflect, synthesize, verify, finalize
│   │   ├── prompts/             # Versioned .txt templates
│   │   ├── tools/               # AgentToolRegistry (wraps signal sources + retriever)
│   │   ├── state.py             # AgentState TypedDict
│   │   └── graph.py             # Graph assembly + run_migration_agent()
│   │
│   ├── api/                     # FastAPI application
│   │   ├── routes/              # scans, kb, health
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── app.py               # create_app() factory
│   │
│   └── cli/                     # typer CLI
│       ├── main.py              # scan, parse, show, usage, migrate
│       └── kb.py                # kb build, stats, ingest, search
│
├── tests/
│   ├── unit/                    # 152 tests, zero network, zero API keys
│   │   ├── agent/               # Node tests with FakeLLM
│   │   ├── domain/              # Entity + value object tests
│   │   ├── evals/               # Metric unit tests
│   │   └── infrastructure/      # Parsers, signals (respx mocks), persistence, LLM, RAG
│   └── integration/             # End-to-end offline scan of stale-flask fixture
│
├── evals/                       # Evaluation harness
│   ├── golden_set.jsonl         # 40 labelled questions (4 categories)
│   ├── run_eval.py              # 6-variant ablation runner
│   ├── baselines/               # naive_rag.py — honest dense-only baseline
│   └── metrics/                 # retrieval, faithfulness, latency, citation_audit
│
├── docs/
│   ├── ARCHITECTURE.md          # Layer guide + invariants + how to add an ecosystem
│   └── ADR/                     # 5 architecture decision records
│
├── scripts/
│   ├── build_kb.py              # Standalone corpus builder
│   ├── warmup.py                # Render cold-start keepalive
│   └── check_file_length.py     # Enforces 300-line file cap
│
├── Dockerfile                   # Multi-stage, pre-bakes HuggingFace models
├── docker-compose.yml           # API + UI together
└── DEVELOPMENT.md               # Architecture rules, stack decisions, working style
```

---

## ⚡ Quickstart

### Prerequisites

```bash
# API keys needed
GEMINI_API_KEY=...   # or GROQ_API_KEY for Groq-only mode
QDRANT_URL=...       # Qdrant Cloud free tier (1GB, sufficient for ~300 docs)
QDRANT_API_KEY=...
GITHUB_TOKEN=...     # Optional — raises rate limit 60→5000 req/hr
```

### Install & run

```bash
git clone https://github.com/ramya1421/dependency-deprecation-agent
cd dependency-deprecation-agent

cp .env.example .env    # fill in your keys
pip install -e ".[dev]"
```

### Scan a repo

```bash
# Risk-ranked dependency table with score breakdowns
dda scan ./my-python-project

# Show what manifests were parsed and coverage
dda parse ./my-python-project

# Every call site for a specific package (file:line, symbol, confidence)
dda usage ./my-python-project --package flask
```

### Build the migration knowledge base

```bash
# Fetch changelogs + release notes from GitHub, chunk, store locally
dda kb build --packages flask,moment,pydantic,sqlalchemy,numpy

# Embed and upsert into Qdrant
dda kb ingest --packages flask,moment,pydantic,sqlalchemy,numpy

# Verify the corpus
dda kb stats

# Test retrieval directly
dda kb search "flask before_first_request removed" --package flask
dda kb search "moment format breaking change" --package moment --no-rerank
```

### Generate a migration plan

```bash
# Full agent run with node-by-node trace
dda migrate ./my-project --package flask --trace

# Output:
# ┌ Migration plan: flask ──────────────────────────────────┐
# │ Update Flask from 0.x to 3.x. The before_first_request  │
# │ decorator was removed; app.json_encoder is deprecated.  │
# └─────────────────────────────────────────────────────────┘
# 1. Replace @app.before_first_request with app_context [abc123ef]
# 2. Switch to app.json.provider API [def456gh]
# ...
# Effort estimate: MEDIUM · 3 call site(s)
# 3 verified citation(s): score=0.92 score=0.88 score=0.91
#
# → plan → route:PROSE_QUERY → retrieve:PROSE_QUERY
# → reflect:sufficient → synthesize → verify:drop_rate=0.00 → finalize
```

### Docker

```bash
docker compose up --build
# FastAPI →  http://localhost:8000
# Streamlit → http://localhost:8501
# API docs →  http://localhost:8000/docs
```

---

## 📟 CLI Reference

| Command | Description |
|---|---|
| `dda scan <repo>` | Full scan: parse → signals → risk score → print ranked table |
| `dda scan <repo> --offline` | Serve entirely from SQLite cache, zero network |
| `dda parse <repo>` | Show manifest parse coverage (parsed/total per file) |
| `dda show <scan-id>` | Re-display findings from a previous scan |
| `dda usage <repo> --package <pkg>` | Every call site: file:line · symbol · confidence tier |
| `dda migrate <repo> --package <pkg>` | Run migration agent, print cited plan |
| `dda migrate ... --trace` | Print node-by-node execution path |
| `dda kb build --packages a,b,c` | Fetch + chunk migration docs for packages |
| `dda kb ingest --packages a,b,c` | Embed chunks and upsert to Qdrant |
| `dda kb stats` | Token distribution + document count per package |
| `dda kb search "<query>"` | Search KB with `--dense-only` / `--no-rerank` flags |

---

## 🌐 API Reference

```
POST  /api/v1/scans                          Trigger scan (async, returns scan_id)
GET   /api/v1/scans/{id}                     Poll status
GET   /api/v1/scans/{id}/dependencies        Parsed dependency list
GET   /api/v1/scans/{id}/findings            Risk-ranked findings
GET   /api/v1/scans/{id}/findings/{dep}/migration  Migration plan for one dep
GET   /api/v1/scans/{id}/report              Full scan report
POST  /api/v1/kb/search                      Debug: query the KB directly
GET   /health                                Qdrant + LLM reachability check
```

Interactive docs at `http://localhost:8000/docs` when running locally.

---

## 📊 Evaluation

DDA is evaluated with a **six-variant ablation study** that isolates each pipeline component's contribution. Each variant builds on the previous one.

```
Variant 1:  Naive dense-only          ← honest baseline
Variant 2:  + Hybrid BM25 + RRF
Variant 3:  + Cross-encoder reranking
Variant 4:  + Agentic planning & routing
Variant 5:  + Reflection loop
Variant 6:  + Citation verification   ← full system
```

### Golden set

40 hand-labelled questions across four categories:

```
15  migration how-to     "How do I replace moment().format() with dayjs?"
10  breaking changes     "What was removed in pydantic v2?"
10  structured facts     "Is moment deprecated? What CVEs affect flask 0.x?"
 5  adversarial          "Migrate away from flask 3.x" (no migration needed)
```

Adversarial entries verify the system doesn't hallucinate migration plans for healthy/current packages.

### Metrics

| Metric | Description |
|---|---|
| **Precision@5** | Fraction of retrieved chunks in the labelled relevant set |
| **Recall@5** | Fraction of relevant chunks found in top-5 |
| **Faithfulness** | LLM judge (Groq) verifies claims against cited chunks |
| **Hallucination rate** | Citations referencing chunks not in retrieved set |
| **p50 / p95 latency** | End-to-end wall time per question |

```bash
# Run the full ablation (requires KB built + API keys)
python evals/run_eval.py --variants 1,2,3,4,5,6

# Smoke test with 5 questions
python evals/run_eval.py --limit 5 --variants 1,2

# Output: evals/results.md  (markdown table)
#         evals/results.json (full results)
#         evals/citation_audit.csv (100 rows for hand review)
```

> **Results table** — run `python evals/run_eval.py` after building the KB to populate with real numbers. See [evals/results.md](evals/results.md).

### Threats to validity

- **Small N (40)** — sufficient for directional comparison, not for statistical significance tests
- **Self-labelling bias** — expected facts labelled by the builder; independent labelling preferred for publication-grade claims
- **LLM judge variance** — faithfulness varies with judge model; same judge used consistently across all variants for internal validity
- **Corpus coverage** — questions about packages not in the KB score zero P@5 regardless of system quality

---

## 🎯 Key Design Decisions

### 1. Not everything is a RAG problem

Structured facts go to **deterministic APIs**. Only unstructured prose goes through the vector store.

```
Question type           →  Routing decision
─────────────────────────────────────────────────────────
"Is moment deprecated?" →  STRUCTURED_FACT → npm registry API
"Any CVEs in flask 0.x?"→  STRUCTURED_FACT → OSV batch query
"When does Node 14 EOL?"→  STRUCTURED_FACT → endoflife.date API
"How to migrate format?"→  PROSE_QUERY     → Hybrid retriever
"What broke in pydantic?"→ PROSE_QUERY     → Hybrid retriever
```

CVE lookups through a vector index would be stale, imprecise, and slower. Direct API calls are exact and always current.

### 2. LangGraph over AgentExecutor

`AgentExecutor` is a black-box ReAct loop — the model decides control flow. With LangGraph:
- The routing decision (structured fact vs RAG) is enforced in code, not in a prompt
- Hard caps (MAX_REFLECTIONS=3, MAX_TOOL_CALLS=12) cannot be talked around by the LLM
- Every node transition is persisted with a state snapshot for replay
- Unit tests call node functions directly with a `FakeLLM` — no framework mocking needed

### 3. SQLite over Redis

Single process, low concurrency, read-heavy once warm. SQLite WAL mode handles this without contention. The entire cache is a single inspectable file. The `--offline` flag, which replays a full scan with zero network calls, is trivial with SQLite and would require explicit serialization with Redis.

### 4. Hybrid retrieval (dense + BM25 + RRF + rerank)

Dense embeddings blur exact symbol names. `moment().format()` may match "date formatting" semantically but miss the exact changelog note. BM25 preserves exact tokens. RRF fuses on rank position — no score normalization needed between incomparable scales. The cross-encoder over the fused top-20 is the most expensive step but the largest precision gain.

---

## ⚠️ Limitations

- **Static analysis is a lower bound** — dynamic imports, re-exports, and monkey-patching are not detected. DDA reports this explicitly; it never claims exhaustive coverage.
- **EOL coverage** — endoflife.date covers major platforms/frameworks. Most package names 404. This is an expected miss, not a failure.
- **Advisory data** — OSV, not a proprietary feed. Coverage gaps exist for some ecosystems.
- **Single-repo scope** — org-wide scanning across hundreds of repos is not supported.
- **Not production-hardened** — single SQLite file, single-process, no auth, no multi-tenancy. This is a research/demo tool.
- **Cold start** — Render free tier spins down after 15 min idle → ~50s cold start. Use `scripts/warmup.py` or run locally.

---

## 🗓 Roadmap

**V2**
- [ ] Go, Java, Rust manifest parsers (each requires one parser file + one analyzer + one `register()` call)
- [ ] Org-wide scanning across a GitHub org
- [ ] Streaming agent traces via Server-Sent Events
- [ ] Pull-request bot — comment migration plans directly on Dependabot PRs
- [ ] Continuous KB refresh via GitHub release webhooks

**Research directions**
- [ ] Multi-repo impact analysis — find all callers of a deprecated symbol across an org
- [ ] Automated PR generation from migration plans
- [ ] Structured diff analysis — parse changelogs into structured breaking-change records

---

## 📐 Architecture Decision Records

Five ADRs document the major tradeoffs made during development. Each states the alternatives considered and what was given up — not just a justification of the chosen option.

| ADR | Decision | Key tradeoff |
|---|---|---|
| [ADR-001](docs/ADR/001-not-everything-is-rag.md) | Structured facts via APIs, not RAG | Precision vs convenience |
| [ADR-002](docs/ADR/002-langgraph-over-agentexecutor.md) | LangGraph over AgentExecutor | Inspectability vs less boilerplate |
| [ADR-003](docs/ADR/003-sqlite-over-redis.md) | SQLite over Redis | Zero infra vs horizontal scale |
| [ADR-004](docs/ADR/004-hybrid-retrieval.md) | Dense + BM25 + RRF + reranker | Recall vs latency |
| [ADR-005](docs/ADR/005-streamlit-for-mvp.md) | Streamlit over React | Speed vs polish |

---

## 📚 Further Reading

- [Architecture Guide](docs/ARCHITECTURE.md) — layer responsibilities, dependency rule, how to add a new ecosystem
- [Development Guide](DEVELOPMENT.md) — stack decisions, architecture rules, working style
- [Evaluation Results](evals/results.md) — ablation table with methodology notes

---

<div align="center">

Built with Python 3.11 · LangGraph · FastAPI · Qdrant · Streamlit

</div>
