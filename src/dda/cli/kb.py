import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dda.config.settings import Settings
from dda.domain.entities import Chunk
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.rag.chunk_store import ChunkStore
from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.kb_builder_service import KbBuilderService, KbBuildResult
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
