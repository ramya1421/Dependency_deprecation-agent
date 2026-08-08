import sqlite3

import httpx
import respx
from tenacity import wait_none

from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.rag.repo_resolver import RepoResolver


def _http_client(connection: sqlite3.Connection) -> BaseHttpClient:
    return BaseHttpClient(connection, correlation_id="test", retry_wait=wait_none())


def _no_npm_match(package: str) -> None:
    respx.get(f"https://registry.npmjs.org/{package}").mock(return_value=httpx.Response(404))


def _no_pypi_match(package: str) -> None:
    respx.get(f"https://pypi.org/pypi/{package}/json").mock(return_value=httpx.Response(404))


@respx.mock
async def test_resolves_from_pypi_project_urls(connection: sqlite3.Connection) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {
                    "project_urls": {"Source": "https://github.com/pallets/flask"},
                    "home_page": "",
                }
            },
        )
    )
    _no_npm_match("flask")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("flask")

    assert result == ("pallets", "flask")


@respx.mock
async def test_resolves_from_pypi_home_page_when_no_project_urls(
    connection: sqlite3.Connection,
) -> None:
    respx.get("https://pypi.org/pypi/somepkg/json").mock(
        return_value=httpx.Response(
            200, json={"info": {"project_urls": {}, "home_page": "https://github.com/org/repo"}}
        )
    )
    _no_npm_match("somepkg")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("somepkg")

    assert result == ("org", "repo")


@respx.mock
async def test_falls_back_to_npm_when_pypi_has_no_match(connection: sqlite3.Connection) -> None:
    _no_pypi_match("moment")
    respx.get("https://registry.npmjs.org/moment").mock(
        return_value=httpx.Response(
            200,
            json={
                "repository": {"type": "git", "url": "git+https://github.com/moment/moment.git"}
            },
        )
    )
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("moment")

    assert result == ("moment", "moment")


@respx.mock
async def test_npm_repository_as_bare_string(connection: sqlite3.Connection) -> None:
    _no_pypi_match("pkg")
    respx.get("https://registry.npmjs.org/pkg").mock(
        return_value=httpx.Response(200, json={"repository": "github:org/pkg"})
    )
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("pkg")

    assert result == ("org", "pkg")


@respx.mock
async def test_returns_none_when_unresolvable_anywhere(connection: sqlite3.Connection) -> None:
    _no_pypi_match("nope")
    _no_npm_match("nope")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("nope")

    assert result is None


@respx.mock
async def test_ssh_style_github_url_is_parsed(connection: sqlite3.Connection) -> None:
    respx.get("https://pypi.org/pypi/pkg/json").mock(
        return_value=httpx.Response(
            200, json={"info": {"project_urls": {"Repo": "git@github.com:org/pkg.git"}}}
        )
    )
    _no_npm_match("pkg")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("pkg")

    assert result == ("org", "pkg")


@respx.mock
async def test_funding_link_does_not_outrank_source_link(connection: sqlite3.Connection) -> None:
    """Regression test: pydantic's real project_urls has both a "Funding"
    link to github.com/sponsors/samuelcolvin and a "Source" link to the
    actual repo — the sponsors link must never win.
    """
    respx.get("https://pypi.org/pypi/pydantic/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {
                    "project_urls": {
                        "Funding": "https://github.com/sponsors/samuelcolvin",
                        "Homepage": "https://github.com/pydantic/pydantic",
                        "Source": "https://github.com/pydantic/pydantic",
                    }
                }
            },
        )
    )
    _no_npm_match("pydantic")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("pydantic")

    assert result == ("pydantic", "pydantic")


@respx.mock
async def test_disagreement_between_registries_is_settled_by_star_count(
    connection: sqlite3.Connection,
) -> None:
    """Regression test: PyPI's "moment" is an obscure, unrelated package;
    npm's "moment" is the real moment.js. Both resolve to *something*, so
    star count — not registry-check order — must decide.
    """
    respx.get("https://pypi.org/pypi/moment/json").mock(
        return_value=httpx.Response(
            200, json={"info": {"project_urls": {"Homepage": "https://github.com/zachwill/moment"}}}
        )
    )
    respx.get("https://registry.npmjs.org/moment").mock(
        return_value=httpx.Response(
            200, json={"repository": {"url": "git+https://github.com/moment/moment.git"}}
        )
    )
    respx.get("https://api.github.com/repos/zachwill/moment").mock(
        return_value=httpx.Response(200, json={"stargazers_count": 12})
    )
    respx.get("https://api.github.com/repos/moment/moment").mock(
        return_value=httpx.Response(200, json={"stargazers_count": 47000})
    )
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("moment")

    assert result == ("moment", "moment")


@respx.mock
async def test_agreement_between_registries_skips_star_lookup(
    connection: sqlite3.Connection,
) -> None:
    respx.get("https://pypi.org/pypi/flask/json").mock(
        return_value=httpx.Response(
            200, json={"info": {"project_urls": {"Source": "https://github.com/pallets/flask"}}}
        )
    )
    respx.get("https://registry.npmjs.org/flask").mock(
        return_value=httpx.Response(
            200, json={"repository": {"url": "https://github.com/pallets/flask"}}
        )
    )
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("flask")

    assert result == ("pallets", "flask")


@respx.mock
async def test_sponsors_only_link_is_rejected_entirely(connection: sqlite3.Connection) -> None:
    respx.get("https://pypi.org/pypi/pkg/json").mock(
        return_value=httpx.Response(
            200,
            json={"info": {"project_urls": {"Funding": "https://github.com/sponsors/someone"}}},
        )
    )
    _no_npm_match("pkg")
    resolver = RepoResolver(_http_client(connection))

    result = await resolver.resolve("pkg")

    assert result is None
