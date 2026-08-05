from collections import Counter
from pathlib import Path

from dda.domain.value_objects import Ecosystem
from dda.infrastructure.parsers.python_parser import PythonManifestParser

FIXTURES = Path(__file__).parents[3] / "fixtures" / "manifests"


def test_ecosystem_is_python() -> None:
    assert PythonManifestParser().ecosystem is Ecosystem.PYTHON


def test_detect_finds_requirements_pyproject_and_lock(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "requirements-dev.txt").write_text("pytest\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "poetry.lock").write_text("")
    (tmp_path / "unrelated.txt").write_text("")

    detected = PythonManifestParser().detect(tmp_path)

    assert set(p.name for p in detected) == {
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
    }


def test_requirements_txt_fails_soft_on_pathological_cases() -> None:
    manifest = FIXTURES / "requirements" / "pathological.txt"
    result = PythonManifestParser().parse_with_coverage(manifest)

    assert {dep.name for dep in result.dependencies} == {"numpy", "requests"}
    assert result.total_declarations == 19

    reasons = Counter(
        s.reason if not s.reason.startswith("unparseable") else "unparseable"
        for s in result.skipped
    )
    assert reasons == Counter(
        {
            "comment": 1,
            "blank_line": 1,
            "recursive_include": 2,
            "editable_install": 2,
            "vcs_url": 2,
            "local_path": 3,
            "index_url_option": 3,
            "environment_marker": 1,
            "hash_pin": 1,
            "unparseable": 1,
        }
    )


def test_parse_returns_only_dependencies() -> None:
    manifest = FIXTURES / "requirements" / "pathological.txt"
    parser = PythonManifestParser()
    assert parser.parse(manifest) == parser.parse_with_coverage(manifest).dependencies


def test_pyproject_toml_parses_pep621_and_poetry_sections() -> None:
    manifest = FIXTURES / "pyproject" / "pathological" / "pyproject.toml"
    result = PythonManifestParser().parse_with_coverage(manifest)

    names = [dep.name for dep in result.dependencies]
    assert names.count("flask") == 1
    assert names.count("requests") == 2
    assert names.count("pydantic") == 1
    assert "python" not in names

    reasons = Counter(s.reason for s in result.skipped)
    assert reasons == Counter({"vcs_url": 2, "local_path": 2, "environment_marker": 1})


def test_poetry_lock_reports_resolved_versions_and_dev_category() -> None:
    manifest = FIXTURES / "pyproject" / "pathological" / "poetry.lock"
    result = PythonManifestParser().parse_with_coverage(manifest)

    by_name = {dep.name: dep for dep in result.dependencies}
    assert by_name["flask"].resolved_version == "2.3.0"
    assert by_name["flask"].is_dev is False
    assert by_name["pytest"].is_dev is True
    assert result.skipped == []
