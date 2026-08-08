"""Standalone corpus-builder entry point.

`dda kb build` wires the identical pipeline; this exists for scripted/CI use
without going through the typer CLI.
"""

import argparse
import asyncio
from pathlib import Path

from dda.config.settings import Settings
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.persistence.connection import connect
from dda.infrastructure.persistence.migration_runner import MigrationRunner
from dda.infrastructure.rag.chunk_store import ChunkStore
from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.kb_builder_service import KbBuilderService
from dda.infrastructure.rag.kb_fetcher import KbFetcher
from dda.infrastructure.rag.repo_resolver import RepoResolver

RAW_DIR = Path("data/kb/raw")
CHUNKS_DIR = Path("data/kb/chunks")


async def build(packages: list[str]) -> None:
    settings = Settings()
    connection = connect(Path(settings.database_path))
    MigrationRunner(connection).apply_all()
    async with BaseHttpClient(connection, correlation_id="build-kb-script") as http_client:
        service = KbBuilderService(
            repo_resolver=RepoResolver(http_client),
            kb_fetcher=KbFetcher(http_client, RAW_DIR),
            chunker=MarkdownChunker(),
            chunk_store=ChunkStore(CHUNKS_DIR),
        )
        results = await service.build(packages)
    for result in results:
        status = "ok" if result.resolved else "unresolved"
        print(
            f"{result.package}: {status} — "
            f"{result.document_count} docs, {result.chunk_count} chunks"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and chunk migration docs for packages")
    parser.add_argument("--packages", required=True, help="Comma-separated package names")
    args = parser.parse_args()
    packages = [p.strip() for p in args.packages.split(",") if p.strip()]
    asyncio.run(build(packages))


if __name__ == "__main__":
    main()
