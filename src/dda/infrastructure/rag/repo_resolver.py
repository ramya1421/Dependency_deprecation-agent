import re

from dda.infrastructure.http.base_client import BaseHttpClient

# Handles https/git+https/ssh GitHub URLs, and npm's "github:owner/repo"
# shorthand (a real, fairly common `repository` field value).
_GITHUB_URL_RE = re.compile(
    r"(?:github\.com[:/]+|^github:)([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[?#].*)?$"
)
# GitHub paths that look like "owner/repo" but aren't a repository at all
# (e.g. a PyPI "Funding" link to github.com/sponsors/x outranking the real
# "Source" link just because of dict ordering — this actually happened for
# pydantic). Reject these regardless of which metadata key they came from.
_NON_REPO_OWNERS = {"sponsors", "marketplace", "apps", "orgs", "settings", "notifications"}
# Metadata keys more likely to be the actual source repo, checked first.
_PRIORITY_KEYS = ("source", "repository", "homepage", "code", "github")


class RepoResolver:
    """Resolves a bare package name to a GitHub (owner, repo) pair via PyPI's
    and npm's own registry metadata — there's no other reliable, general
    mapping from a distribution name to its source repo (the same gap
    GitHubClient's docstring notes).

    Package names collide across ecosystems (PyPI's "moment" is an obscure,
    unrelated library; npm's "moment" is the real moment.js — and the
    reverse is true for "flask"/"pydantic" on npm). Both registries are
    checked, and when they disagree, GitHub star count picks the real
    project rather than trusting whichever registry happened to answer.
    """

    def __init__(self, http_client: BaseHttpClient) -> None:
        self._http_client = http_client

    async def resolve(self, package: str) -> tuple[str, str] | None:
        pypi_result = await self._from_pypi(package)
        npm_result = await self._from_npm(package)
        if pypi_result and npm_result and pypi_result != npm_result:
            return await self._more_popular(pypi_result, npm_result)
        return pypi_result or npm_result

    async def _from_pypi(self, package: str) -> tuple[str, str] | None:
        try:
            data = await self._http_client.request(
                "GET", f"https://pypi.org/pypi/{package}/json", "repo_resolver"
            )
        except Exception:
            return None
        info = data.get("info", {})
        candidates = dict(info.get("project_urls", {}))
        home_page = info.get("home_page")
        if home_page:
            candidates.setdefault("Homepage", home_page)
        return _first_github_repo(candidates)

    async def _from_npm(self, package: str) -> tuple[str, str] | None:
        try:
            data = await self._http_client.request(
                "GET", f"https://registry.npmjs.org/{package}", "repo_resolver"
            )
        except Exception:
            return None
        repository = data.get("repository")
        url = repository.get("url") if isinstance(repository, dict) else repository
        return _first_github_repo({"repository": url} if url else {})

    async def _more_popular(
        self, a: tuple[str, str], b: tuple[str, str]
    ) -> tuple[str, str]:
        stars_a, stars_b = await self._stars(a), await self._stars(b)
        return a if stars_a >= stars_b else b

    async def _stars(self, owner_repo: tuple[str, str]) -> int:
        owner, repo = owner_repo
        try:
            data = await self._http_client.request(
                "GET", f"https://api.github.com/repos/{owner}/{repo}", "repo_resolver"
            )
        except Exception:
            return -1
        return int(data.get("stargazers_count") or 0)


def _first_github_repo(candidates: dict[str, object]) -> tuple[str, str] | None:
    for _, value in sorted(candidates.items(), key=_key_priority):
        if not isinstance(value, str):
            continue
        match = _GITHUB_URL_RE.search(value)
        if match and match.group(1).lower() not in _NON_REPO_OWNERS:
            return match.group(1), match.group(2)
    return None


def _key_priority(item: tuple[str, object]) -> int:
    key = item[0].lower()
    for index, priority_key in enumerate(_PRIORITY_KEYS):
        if priority_key in key:
            return index
    return len(_PRIORITY_KEYS)
