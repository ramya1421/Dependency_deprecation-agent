from dataclasses import dataclass
from pathlib import Path

import httpx

from dda.infrastructure.http.base_client import BaseHttpClient

_CHANGELOG_FILES = ("CHANGELOG.md", "CHANGES.rst", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md")
_MIGRATION_FILES = ("MIGRATION.md", "UPGRADING.md", "UPGRADE.md")


@dataclass(frozen=True)
class RawDocument:
    package: str
    doc_type: str  # "changelog" | "migration_guide" | "release_note"
    source_url: str
    content: str
    version: str | None = None


class KbFetcher:
    """Fetches migration knowledge for one package: changelog/migration files
    from the repo's default branch, and GitHub release bodies. Raw content is
    saved verbatim under data/kb/raw/{package}/ so the corpus stays
    inspectable and rebuildable without re-fetching.
    """

    def __init__(self, http_client: BaseHttpClient, raw_dir: Path) -> None:
        self._http_client = http_client
        self._raw_dir = raw_dir

    async def fetch(self, package: str, owner: str, repo: str) -> list[RawDocument]:
        documents = [
            *await self._fetch_files(package, owner, repo),
            *await self._fetch_releases(package, owner, repo),
        ]
        self._save_raw(package, documents)
        return documents

    async def _fetch_files(self, package: str, owner: str, repo: str) -> list[RawDocument]:
        branch = await self._default_branch(owner, repo)
        docs: list[RawDocument] = []
        for filename in (*_CHANGELOG_FILES, *_MIGRATION_FILES):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            content = await self._get_raw_text(url)
            if content is None:
                continue
            doc_type = "migration_guide" if filename in _MIGRATION_FILES else "changelog"
            docs.append(RawDocument(package, doc_type, url, content))
        return docs

    async def _default_branch(self, owner: str, repo: str) -> str:
        try:
            data = await self._http_client.request(
                "GET", f"https://api.github.com/repos/{owner}/{repo}", "kb_fetcher"
            )
        except Exception:
            return "main"
        return str(data.get("default_branch") or "main")

    async def _get_raw_text(self, url: str) -> str | None:
        try:
            text = await self._http_client.request(
                "GET", url, "kb_fetcher_raw", parse_json=False
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return str(text) if str(text).strip() else None

    async def _fetch_releases(self, package: str, owner: str, repo: str) -> list[RawDocument]:
        try:
            releases = await self._http_client.request(
                "GET",
                f"https://api.github.com/repos/{owner}/{repo}/releases",
                "kb_fetcher",
                params={"per_page": "30"},
            )
        except Exception:
            return []
        docs: list[RawDocument] = []
        for release in releases:
            body = release.get("body")
            if not body or not body.strip():
                continue
            fallback_url = f"https://github.com/{owner}/{repo}/releases"
            docs.append(
                RawDocument(
                    package=package,
                    doc_type="release_note",
                    source_url=release.get("html_url") or fallback_url,
                    content=body,
                    version=_normalize_tag(release.get("tag_name")),
                )
            )
        return docs

    def _save_raw(self, package: str, documents: list[RawDocument]) -> None:
        package_dir = self._raw_dir / package
        package_dir.mkdir(parents=True, exist_ok=True)
        for index, doc in enumerate(documents):
            filename = Path(doc.source_url).name or f"{doc.doc_type}-{index}"
            path = package_dir / f"{index:03d}-{doc.doc_type}-{filename}.md"
            path.write_text(doc.content, encoding="utf-8")


def _normalize_tag(tag: str | None) -> str | None:
    if tag and len(tag) > 1 and tag[0] in "vV" and tag[1].isdigit():
        return tag[1:]
    return tag
