import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dda.config.settings import Settings
from dda.domain.entities import Chunk
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.rag.bm25_retriever import BM25Retriever
from dda.infrastructure.rag.chunk_store import ChunkStore
from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.kb_builder_service import KbBuildResult, KbBuilderService
from dda.infrastructure.rag.kb_fetcher import KbFetcher
from dda.infrastructure.rag.repo_resolver import RepoResolver

kb_app = typer.Typer(help="Build and inspect the migration-knowledge corpus")
console = Console()

_RAW_DIR = Path("data/kb/raw")
_CHUNKS_DIR = Path("data/kb/chunks")


async def _run_build(packages: list[str], settings: Settings) -> list[KbBuildResult]:
    connection = connect(Path(settings.database_path))
    MigrationRunner(connection).apply_all()
    async with BaseHttpClient(connection, correlation_id="kb-build") as http_client:
        service = KbBuilderService(
            repo_resolver=RepoResolver(http_client),
            kb_fetcher=KbFetcher(http_client, _RAW_DIR),
            chunker=MarkdownChunker(),
            chunk_store=ChunkStore(_CHUNKS_DIR),
        )
        return await service.build(packages)


@kb_app.command("build")
def build(
    packages: str = typer.Option(..., "--packages", help="Comma-separated package names"),
) -> None:
    """Fetch, clean, and chunk migration docs for the given packages."""
    package_list = [p.strip() for p in packages.split(",") if p.strip()]
    results = asyncio.run(_run_build(package_list, Settings()))

    table = Table(title="KB build results")
    table.add_column("Package")
    table.add_column("Resolved", justify="center")
    table.add_column("Documents", justify="right")
    table.add_column("Chunks", justify="right")
    for result in results:
        table.add_row(
            result.package,
            "yes" if result.resolved else "no",
            str(result.document_count),
            str(result.chunk_count),
        )
    console.print(table)


@kb_app.command("stats")
def stats() -> None:
    """Show document count, chunk count, and token distribution per package."""
    by_package = ChunkStore(_CHUNKS_DIR).load_all()
    if not by_package:
        console.print("[yellow]No chunks found — run `dda kb build` first.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title="Knowledge base stats")
    table.add_column("Package")
    table.add_column("Documents", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Tokens (min/mean/max)", justify="right")
    for package, chunks in sorted(by_package.items()):
        table.add_row(package, *_package_row(chunks))
    console.print(table)


def _package_row(chunks: list[Chunk]) -> tuple[str, str, str]:
    if not chunks:
        return "0", "0", "0/0/0"
    token_counts = [c.token_count for c in chunks]
    documents = len({c.source_url for c in chunks})
    mean_tokens = round(sum(token_counts) / len(token_counts))
    token_summary = f"{min(token_counts)}/{mean_tokens}/{max(token_counts)}"
    return str(documents), str(len(chunks)), token_summary


@kb_app.command("ingest")
def ingest(
    packages: str = typer.Option(..., "--packages", help="Comma-separated package names"),
) -> None:
    """Embed chunks and upsert into Qdrant. Requires QDRANT_URL in .env."""
    settings = Settings()
    if not settings.qdrant_url:
        console.print("[red]QDRANT_URL is not set — cannot ingest.[/red]")
        raise typer.Exit(code=1)

    # Import here to avoid loading heavy ML deps unless this command is called.
    from dda.infrastructure.rag.qdrant_repository import QdrantVectorRepository

    package_list = [p.strip() for p in packages.split(",") if p.strip()]
    repo = QdrantVectorRepository(settings.qdrant_url, settings.qdrant_api_key)
    store = ChunkStore(_CHUNKS_DIR)

    total_upserted = 0
    for package in package_list:
        chunks = store.load(package)
        if not chunks:
            console.print(f"[yellow]{package}: no chunks found — run `dda kb build` first.[/yellow]")
            continue
        repo.upsert(chunks)
        total_upserted += len(chunks)
        console.print(f"[green]{package}: upserted {len(chunks)} chunk(s)[/green]")

    console.print(f"\nTotal upserted: {total_upserted}")


@kb_app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    package: str = typer.Option("", "--package", "-p", help="Filter to a specific package"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results"),
    dense_only: bool = typer.Option(False, "--dense-only", help="Skip BM25 and reranking"),
    no_rerank: bool = typer.Option(False, "--no-rerank", help="Skip cross-encoder reranking"),
) -> None:
    """Search the migration knowledge base and show ranked results with scores."""
    settings = Settings()
    if not settings.qdrant_url:
        console.print("[red]QDRANT_URL is not set — cannot search.[/red]")
        raise typer.Exit(code=1)

    # Import heavy deps only when this command runs.
    from dda.infrastructure.rag.embedder import Embedder
    from dda.infrastructure.rag.hybrid_retriever import HybridRetriever
    from dda.infrastructure.rag.qdrant_repository import QdrantVectorRepository
    from dda.infrastructure.rag.reranker import Reranker

    store = ChunkStore(_CHUNKS_DIR)
    all_chunks: list[Chunk] = []
    for chunks in store.load_all().values():
        all_chunks.extend(chunks)

    pkg_filter = package.strip() if package.strip() else None
    retriever = HybridRetriever(
        vector_repository=QdrantVectorRepository(settings.qdrant_url, settings.qdrant_api_key),
        bm25_retriever=BM25Retriever(all_chunks),
        embedder=Embedder(),
        reranker=Reranker(),
        use_bm25=not dense_only,
        use_rerank=not dense_only and not no_rerank,
    )

    results = retriever.retrieve(query, pkg_filter, top_k)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, chunk in enumerate(results, 1):
        panel_title = f"[bold]#{i}[/bold]  {chunk.package} · {chunk.doc_type}  [{chunk.chunk_id}]"
        header = f"[dim]{chunk.header_path}[/dim]"
        body = chunk.text[:500] + ("…" if len(chunk.text) > 500 else "")
        console.print(Panel(f"{header}\n\n{body}", title=panel_title, expand=False))
