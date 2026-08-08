import sqlite3
from pathlib import Path

import httpx
import respx
from tenacity import wait_none

from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.rag.kb_fetcher import KbFetcher


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def _mock_repo_and_releases(default_branch: str = "main", releases: list | None = None) -> None:
    respx.get("https://api.github.com/repos/pallets/flask").mock(
        return_value=httpx.Response(200, json={"default_branch": default_branch})
    )
    respx.get("https://api.github.com/repos/pallets/flask/releases").mock(
        return_value=httpx.Response(200, json=releases or [])
    )


@respx.mock
async def test_fetches_changelog_and_skips_missing_files(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    _mock_repo_and_releases()
    respx.get("https://raw.githubusercontent.com/pallets/flask/main/CHANGELOG.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://raw.githubusercontent.com/pallets/flask/main/CHANGES.rst").mock(
        return_value=httpx.Response(200, text="Version 1.0.0\n-------------\n\nfirst release\n")
    )
    for filename in (
        "CHANGELOG.rst",
        "CHANGES.md",
        "HISTORY.md",
        "MIGRATION.md",
        "UPGRADING.md",
        "UPGRADE.md",
    ):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )

    fetcher = KbFetcher(_http_client(connection), tmp_path)
    docs = await fetcher.fetch("flask", "pallets", "flask")

    assert len(docs) == 1
    assert docs[0].doc_type == "changelog"
    assert "first release" in docs[0].content
    assert docs[0].source_url.endswith("CHANGES.rst")


@respx.mock
async def test_migration_file_is_tagged_migration_guide(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    _mock_repo_and_releases()
    for filename in ("CHANGELOG.md", "CHANGES.rst", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md"):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )
    respx.get("https://raw.githubusercontent.com/pallets/flask/main/MIGRATION.md").mock(
        return_value=httpx.Response(200, text="# Migrating\n\ndo this\n")
    )
    for filename in ("UPGRADING.md", "UPGRADE.md"):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )

    fetcher = KbFetcher(_http_client(connection), tmp_path)
    docs = await fetcher.fetch("flask", "pallets", "flask")

    assert len(docs) == 1
    assert docs[0].doc_type == "migration_guide"


@respx.mock
async def test_fetches_release_bodies_and_normalizes_version_tag(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    _mock_repo_and_releases(
        releases=[
            {
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/pallets/flask/releases/v2.0.0",
                "body": "release body",
            },
            {
                "tag_name": "v1.0.0",
                "html_url": "https://github.com/pallets/flask/releases/v1.0.0",
                "body": "",
            },
        ]
    )
    for filename in (
        "CHANGELOG.md",
        "CHANGES.rst",
        "CHANGELOG.rst",
        "CHANGES.md",
        "HISTORY.md",
        "MIGRATION.md",
        "UPGRADING.md",
        "UPGRADE.md",
    ):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )

    fetcher = KbFetcher(_http_client(connection), tmp_path)
    docs = await fetcher.fetch("flask", "pallets", "flask")

    # The empty-body v1.0.0 release is skipped; only v2.0.0 survives.
    assert len(docs) == 1
    assert docs[0].doc_type == "release_note"
    assert docs[0].version == "2.0.0"
    assert docs[0].content == "release body"


@respx.mock
async def test_saves_raw_documents_to_disk(connection: sqlite3.Connection, tmp_path: Path) -> None:
    _mock_repo_and_releases()
    respx.get("https://raw.githubusercontent.com/pallets/flask/main/CHANGELOG.md").mock(
        return_value=httpx.Response(200, text="# Changelog\n\ncontent\n")
    )
    for filename in (
        "CHANGES.rst",
        "CHANGELOG.rst",
        "CHANGES.md",
        "HISTORY.md",
        "MIGRATION.md",
        "UPGRADING.md",
        "UPGRADE.md",
    ):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )

    fetcher = KbFetcher(_http_client(connection), tmp_path)
    await fetcher.fetch("flask", "pallets", "flask")

    saved = list((tmp_path / "flask").glob("*.md"))
    assert len(saved) == 1
    assert "content" in saved[0].read_text(encoding="utf-8")


@respx.mock
async def test_falls_back_to_main_branch_when_repo_lookup_fails(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respx.get("https://api.github.com/repos/pallets/flask").mock(return_value=httpx.Response(500))
    respx.get("https://api.github.com/repos/pallets/flask/releases").mock(
        return_value=httpx.Response(200, json=[])
    )
    for filename in (
        "CHANGELOG.md",
        "CHANGES.rst",
        "CHANGELOG.rst",
        "CHANGES.md",
        "HISTORY.md",
        "MIGRATION.md",
        "UPGRADING.md",
        "UPGRADE.md",
    ):
        respx.get(f"https://raw.githubusercontent.com/pallets/flask/main/{filename}").mock(
            return_value=httpx.Response(404)
        )

    fetcher = KbFetcher(_http_client(connection), tmp_path)
    docs = await fetcher.fetch("flask", "pallets", "flask")

    assert docs == []
