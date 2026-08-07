import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dda.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))


def test_scan_offline_prints_ranked_table_with_score_breakdown(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")

    result = runner.invoke(app, ["scan", str(tmp_path), "--offline"])

    assert result.exit_code == 0
    assert "flask" in result.stdout
    assert "Risk" in result.stdout
    assert "Rationale" in result.stdout


def test_parse_shows_manifest_coverage(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\nrequests\n")

    result = runner.invoke(app, ["parse", str(tmp_path)])

    assert result.exit_code == 0
    assert "requirements.txt" in result.stdout
    assert "2/2" in result.stdout


def test_show_unknown_scan_id_exits_nonzero() -> None:
    result = runner.invoke(app, ["show", "nonexistent-scan-id"])

    assert result.exit_code == 1
    assert "No findings" in result.stdout


def test_show_after_scan_displays_the_same_findings(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")
    scan_result = runner.invoke(app, ["scan", str(tmp_path), "--offline"])
    scan_id_match = re.search(r"[0-9a-f]{8}-[0-9a-f-]{27}", scan_result.stdout)
    assert scan_id_match is not None

    show_result = runner.invoke(app, ["show", scan_id_match.group(0)])

    assert show_result.exit_code == 0
    assert "flask" in show_result.stdout
