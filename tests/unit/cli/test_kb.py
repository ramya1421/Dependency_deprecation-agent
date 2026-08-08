from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

import dda.infrastructure.rag.chunker as chunker_module
from dda.cli.main import app

runner = CliRunner()

_MISSING_FILES = (
    "CHANGES.rst", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md",
    "MIGRATION.md", "UPGRADING.md", "UPGRADE.md",
)


@pytest.fixture(autouse=True)
def _isolated_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # `dda kb *` uses fixed relative paths (data/kb/raw, data/kb/chunks) for
    # the corpus, same spirit as DATABASE_PATH's relative default — isolate
    # them per test by running from a scratch cwd.
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.chdir(tmp_path)
    # The CLI wires MarkdownChunker() with its real default tokenizer, which
    # would otherwise need to load (and, on a cold cache, download) the
    # actual bge-small model — swap in a fast, offline stand-in so this test
    # file stays fully offline and deterministic like the rest of the suite.
    monkeypatch.setattr(chunker_module, "_default_count_tokens", lambda text: len(text.split()))


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


def _mock_unresolvable(package: str) -> None:
    respx.get(f"https://pypi.org/pypi/{package}/json").mock(return_value=httpx.Response(404))
    respx.get(f"https://registry.npmjs.org/{package}").mock(return_value=httpx.Response(404))


@respx.mock
def test_kb_build_reports_resolved_package_with_docs_and_chunks() -> None:
    _mock_flask_endpoints()

    result = runner.invoke(app, ["kb", "build", "--packages", "flask"])

    assert result.exit_code == 0
    assert "flask" in result.stdout
    assert "yes" in result.stdout


@respx.mock
def test_kb_build_reports_unresolved_package_without_error() -> None:
    _mock_unresolvable("totally-unknown-xyz")

    result = runner.invoke(app, ["kb", "build", "--packages", "totally-unknown-xyz"])

    assert result.exit_code == 0
    assert "no" in result.stdout


def test_kb_stats_with_no_prior_build_exits_nonzero() -> None:
    result = runner.invoke(app, ["kb", "stats"])

    assert result.exit_code == 1
    assert "No chunks found" in result.stdout


@respx.mock
def test_kb_stats_after_build_shows_counts_and_token_distribution() -> None:
    _mock_flask_endpoints()
    build_result = runner.invoke(app, ["kb", "build", "--packages", "flask"])
    assert build_result.exit_code == 0

    result = runner.invoke(app, ["kb", "stats"])

    assert result.exit_code == 0
    assert "flask" in result.stdout
