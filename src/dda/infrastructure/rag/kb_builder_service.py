from dataclasses import dataclass

from dda.domain.entities import Chunk
from dda.infrastructure.rag.chunk_store import ChunkStore
from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.cleaner import clean
from dda.infrastructure.rag.kb_fetcher import KbFetcher
from dda.infrastructure.rag.repo_resolver import RepoResolver


@dataclass(frozen=True)
class KbBuildResult:
    package: str
    resolved: bool
    document_count: int
    chunk_count: int


class KbBuilderService:
    """Orchestrates one package end-to-end: resolve its GitHub repo, fetch
    raw docs, clean, chunk, and persist. Lives in infrastructure/ rather than
    application/ because it directly wires concrete, I/O-performing
    collaborators (RepoResolver, KbFetcher) rather than domain ports — the
    same reason the CLI, not a use case, is what constructs it.
    """

    def __init__(
        self,
        repo_resolver: RepoResolver,
        kb_fetcher: KbFetcher,
        chunker: MarkdownChunker,
        chunk_store: ChunkStore,
    ) -> None:
        self._repo_resolver = repo_resolver
        self._kb_fetcher = kb_fetcher
        self._chunker = chunker
        self._chunk_store = chunk_store

    async def build(self, packages: list[str]) -> list[KbBuildResult]:
        return [await self._build_one(package) for package in packages]

    async def _build_one(self, package: str) -> KbBuildResult:
        owner_repo = await self._repo_resolver.resolve(package)
        if owner_repo is None:
            return KbBuildResult(package, resolved=False, document_count=0, chunk_count=0)
        owner, repo = owner_repo

        documents = await self._kb_fetcher.fetch(package, owner, repo)
        chunks: list[Chunk] = []
        for document in documents:
            chunks.extend(
                self._chunker.chunk(
                    clean(document.content),
                    package=package,
                    doc_type=document.doc_type,
                    source_url=document.source_url,
                    version=document.version,
                )
            )
        self._chunk_store.save(package, chunks)
        return KbBuildResult(
            package, resolved=True, document_count=len(documents), chunk_count=len(chunks)
        )
