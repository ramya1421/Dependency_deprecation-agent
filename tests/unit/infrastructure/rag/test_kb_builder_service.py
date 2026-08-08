import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.rag.chunk_store import ChunkStore
from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.kb_builder_service import KbBuilderService
from dda.infrastructure.rag.kb_fetcher import KbFetcher
from dda.infrastructure.rag.repo_resolver import RepoResolver

_MISSING_FILES = (
    "CHANGES.rst", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md",
    "MIGRATION.md", "UPGRADING.md", "UPGRADE.md",
)


def _word_count(text: str) -> int:
    return len(text.split())


def _service(connection: sqlite3.Connection, tmp_path: Path) -> KbBuilderService:
    http_client = BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())
    return KbBuilderService(
        repo_resolver=RepoResolver(http_client),
        kb_fetcher=KbFetcher(http_client, tmp_path / "raw"),
        chunker=MarkdownChunker(count_tokens=_word_count),
        chunk_store=ChunkStore(tmp_path / "chunks"),
    )


def _mock_flask_endpoints() -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200, json={"info": {"project_urls": {"Source": "https://github.com/pallets/flask"}}}
        )
    )
    respx.get("https://registry.npmjs.org/flask").mock(return_value=httpx.Response(404))
    respx.get("https://api.github.com/repos/pallets/flask").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"})
    )
    respx.get("https://api.github.com/repos/pallets/flask/releases").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://raw.githubusercontent.com/pallets/flask/main/CHANGELOG.md").mock(
        return_value=httpx.Response(200, text="# Changelog\n\n## 1.0.0\n\n- did a thing\n")
    )
    for filename in _MISSING_FILES:
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )


@respx.mock
async def test_build_resolves_fetches_cleans_chunks_and_persists(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    _mock_flask_endpoints()
    service = _service(connection, tmp_path)

    results = await service.build(["flask"])

    assert len(results) == 1
    result = results[0]
    assert result.package == "flask"
    assert result.resolved is True
    assert result.document_count == 1
    assert result.chunk_count == 1

    stored = ChunkStore(tmp_path / "chunks").load("flask")
    assert len(stored) == 1
    assert stored[0].header_path == "Changelog > 1.0.0"
    assert "did a thing" in stored[0].text


@respx.mock
async def test_build_records_unresolved_package_without_crashing(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respx.get("https://pypi.org/pypi/totally-unknown-xyz/json").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://registry.npmjs.org/totally-unknown-xyz").mock(
        return_value=httpx.Response(404)
    )
    service = _service(connection, tmp_path)

    results = await service.build(["totally-unknown-xyz"])

    assert results[0].resolved is False
    assert results[0].document_count == 0
    assert results[0].chunk_count == 0


@respx.mock
async def test_build_handles_multiple_packages_independently(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    _mock_flask_endpoints()
    respx.get("https://pypi.org/pypi/totally-unknown-xyz/json").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://registry.npmjs.org/totally-unknown-xyz").mock(
        return_value=httpx.Response(404)
    )
    service = _service(connection, tmp_path)

    results = await service.build(["flask", "totally-unknown-xyz"])

    by_package = {r.package: r for r in results}
    assert by_package["flask"].resolved is True
    assert by_package["totally-unknown-xyz"].resolved is False
