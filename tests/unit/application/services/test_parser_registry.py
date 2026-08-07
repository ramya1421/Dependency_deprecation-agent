from pathlib import Path

from dda.application.services.parser_registry import ParserRegistry
from dda.domain.value_objects import Ecosystem
from dda.infrastructure.parsers.npm_parser import NpmManifestParser
from dda.infrastructure.parsers.python_parser import PythonManifestParser


def test_detect_all_groups_manifests_by_ecosystem(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "package.json").write_text("{}")

    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())

    detected = registry.detect_all(tmp_path)

    assert set(detected.keys()) == {Ecosystem.PYTHON, Ecosystem.JAVASCRIPT}
    assert [p.name for p in detected[Ecosystem.PYTHON]] == ["requirements.txt"]
    assert [p.name for p in detected[Ecosystem.JAVASCRIPT]] == ["package.json"]


def test_detect_all_omits_ecosystems_with_no_manifests(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")

    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())

    detected = registry.detect_all(tmp_path)

    assert Ecosystem.JAVASCRIPT not in detected


def test_parse_all_flattens_dependencies_across_ecosystems(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
    (tmp_path / "package.json").write_text('{"dependencies": {"left-pad": "1.3.0"}}')

    registry = ParserRegistry()
    registry.register(PythonManifestParser())
    registry.register(NpmManifestParser())

    dependencies = registry.parse_all(tmp_path)

    assert {d.name for d in dependencies} == {"flask", "requests", "left-pad"}
