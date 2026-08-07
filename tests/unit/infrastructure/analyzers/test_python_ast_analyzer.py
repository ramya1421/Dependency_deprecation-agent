from pathlib import Path

from dda.domain.value_objects import Confidence, Ecosystem
from dda.infrastructure.analyzers.python_ast_analyzer import PythonAstAnalyzer


def test_ecosystem_is_python() -> None:
    assert PythonAstAnalyzer().ecosystem is Ecosystem.PYTHON


def test_direct_call_is_static_confirmed(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import flask\nflask.Flask(__name__)\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    site = sites[0]
    assert site.symbol == "flask.Flask"
    assert site.package == "flask"
    assert site.usage_kind == "call"
    assert site.confidence is Confidence.STATIC_CONFIRMED
    assert site.line_number == 2
    assert site.snippet == "flask.Flask(__name__)"


def test_from_import_as_alias_resolves_qualified_name(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "from flask import Flask as F\napp = F(__name__)\n"
    )

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.Flask"
    assert sites[0].usage_kind == "call"


def test_dotted_import_without_alias_binds_root(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import a.b.c\na.b.c.helper()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["a"])

    assert len(sites) == 1
    assert sites[0].symbol == "a.b.c.helper"
    assert sites[0].package == "a"


def test_import_as_alias(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import numpy as np\nnp.array([1])\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["numpy"])

    assert len(sites) == 1
    assert sites[0].symbol == "numpy.array"


def test_plain_attribute_access_without_call(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import flask\nx = flask.config\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "attribute"
    assert sites[0].symbol == "flask.config"


def test_nested_attribute_chain_emits_once_not_per_prefix(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import flask\nflask.helpers.nested.deep()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.helpers.nested.deep"


def test_untracked_package_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import os\nos.path.join('a', 'b')\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []


def test_relative_import_does_not_crash_or_match(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("from . import flask\nflask.thing()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []


def test_star_import_is_possible_confidence(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("from flask import *\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "star_import"
    assert sites[0].confidence is Confidence.POSSIBLE


def test_getattr_on_tracked_package_is_possible_confidence(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import flask\ngetattr(flask, 'Flask')\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "getattr"
    assert sites[0].confidence is Confidence.POSSIBLE


def test_importlib_import_module_is_possible_confidence(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import importlib\nimportlib.import_module('flask')\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "dynamic_import"
    assert sites[0].symbol == "flask"
    assert sites[0].confidence is Confidence.POSSIBLE


def test_importlib_import_module_direct_import(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "from importlib import import_module as im\nim('flask')\n"
    )

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "dynamic_import"


def test_syntax_error_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n")
    (tmp_path / "app.py").write_text("import flask\nflask.Flask()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1


def test_respects_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored/\n")
    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "app.py").write_text("import flask\nflask.Flask()\n")
    (tmp_path / "kept.py").write_text("import flask\nflask.Flask()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].file_path.name == "kept.py"


def test_skips_venv_directories(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "app.py").write_text("import flask\nflask.Flask()\n")

    sites = PythonAstAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []
