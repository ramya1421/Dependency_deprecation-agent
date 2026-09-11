# DEVELOPMENT.md

## Project
Dependency Deprecation Agent (DDA). Scans a Git repo's dependency manifests,
detects deprecated/vulnerable/abandoned/EOL packages, analyses which of those
packages' APIs the source code actually uses, and generates cited migration
plans with effort estimates.

Core thesis: Dependabot tells you WHAT to upgrade. DDA tells you WHAT IT WILL
BREAK, WHERE, and HOW TO FIX IT — with citations.

## Critical Architectural Decision
Not everything here is a RAG problem. Structured facts (deprecation flags,
CVEs, EOL dates, repo activity) are fetched via deterministic API calls, NOT
vector search. The vector store holds ONLY unstructured migration prose
(changelogs, migration guides, release notes). The agent's routing node decides
which path a sub-question takes. Never suggest embedding structured registry
metadata.

## Stack
Python 3.11+ · FastAPI · Streamlit · typer · SQLite · Qdrant Cloud ·
sentence-transformers (BAAI/bge-small-en-v1.5) · cross-encoder/ms-marco-MiniLM-L-6-v2 ·
rank_bm25 · LangGraph · Gemini 2.0 Flash (primary LLM) · Groq Llama 3.3 70B
(fallback) · httpx · tenacity · Pydantic v2 · pytest · ruff · mypy --strict ·
Docker · GitHub Actions

Explicitly NOT used: Redis (SQLite cache table is sufficient — single process,
low concurrency), Celery (FastAPI BackgroundTasks is enough), LangChain
AgentExecutor (LangGraph gives inspectable state), Postgres, React (V2).

## Architecture Rules
- Clean Architecture. Dependencies point inward only.
- src/dda/domain/ imports NOTHING external. Pure entities + ABC ports.
- src/dda/application/ depends on domain ports only, never on infrastructure.
- src/dda/infrastructure/ implements the ports. All I/O lives here.
- Constructor injection everywhere. No global state. No singletons.
- Type hints on every function signature. Code must pass `mypy --strict`.
- Files under 300 lines. Extract when approaching the limit.
- Every external call goes through a port interface so it can be faked in tests.

## Scope Discipline
This is a 14-day solo build. When implementing a feature, implement the simplest
version that satisfies the requirement. Do not add caching, abstraction layers,
config options, or extensibility hooks that were not asked for.

## Working Style
- Before writing code, state the plan in 3-5 bullets.
- Write the test alongside the implementation, not after.
- When making a non-obvious design choice, add a one-line comment explaining
  WHY, not what.
- Never write placeholder code or TODO stubs. If something cannot be implemented
  now, say so.
- Do not create files that were not asked for.
