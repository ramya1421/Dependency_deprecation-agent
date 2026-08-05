from collections import Counter
from pathlib import Path

from dda.domain.value_objects import Ecosystem
from dda.infrastructure.parsers.npm_parser import NpmManifestParser

FIXTURES = Path(__file__).parents[3] / "fixtures" / "manifests" / "npm" / "pathological"


def test_ecosystem_is_javascript() -> None:
    assert NpmManifestParser().ecosystem is Ecosystem.JAVASCRIPT


def test_detect_finds_package_json_and_lock(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")

    detected = NpmManifestParser().detect(tmp_path)

    assert {p.name for p in detected} == {"package.json", "package-lock.json"}


def test_package_json_fails_soft_on_pathological_cases() -> None:
    manifest = FIXTURES / "package.json"
    result = NpmManifestParser().parse_with_coverage(manifest)

    names = {dep.name: dep for dep in result.dependencies}
    assert set(names) == {"express", "@scope/pkg", "jest"}
    assert names["jest"].is_dev is True
    assert names["express"].is_dev is False

    reasons = Counter(s.reason for s in result.skipped)
    assert reasons == Counter(
        {"local_path": 2, "vcs_url": 2, "workspace_glob": 1}
    )
    assert result.total_declarations == 8


def test_package_lock_v3_resolves_versions_and_hoisting() -> None:
    manifest = FIXTURES / "package-lock.json"
    result = NpmManifestParser().parse_with_coverage(manifest)

    by_name = {dep.name: dep for dep in result.dependencies}
    assert by_name["express"].resolved_version == "4.18.2"
    assert by_name["express"].is_direct is True
    assert by_name["jest"].is_dev is True
    assert by_name["debug"].is_direct is False, "nested node_modules copy is transitive"
    assert result.skipped == []


def test_parse_returns_only_dependencies() -> None:
    manifest = FIXTURES / "package.json"
    parser = NpmManifestParser()
    assert parser.parse(manifest) == parser.parse_with_coverage(manifest).dependencies
