from pathlib import Path

from dda.domain.value_objects import Confidence, Ecosystem
from dda.infrastructure.analyzers.tree_sitter_js_analyzer import TreeSitterJsAnalyzer


def test_ecosystem_is_javascript() -> None:
    assert TreeSitterJsAnalyzer().ecosystem is Ecosystem.JAVASCRIPT


def test_default_import_call_is_static_confirmed(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("import flask from 'flask';\nflask.route('/x');\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    site = sites[0]
    assert site.symbol == "flask.route"
    assert site.package == "flask"
    assert site.usage_kind == "call"
    assert site.confidence is Confidence.STATIC_CONFIRMED
    assert site.line_number == 2


def test_named_import_with_alias_resolves_original_export_name(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "import { DataFrame as DF } from 'pandas';\nDF.method();\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["pandas"])

    assert len(sites) == 1
    assert sites[0].symbol == "pandas.DataFrame.method"


def test_namespace_import(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "import * as flaskns from 'flask';\nflaskns.create();\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.create"


def test_require_call_binding(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "const flask = require('flask');\nflask.route('/x');\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.route"


def test_nested_member_chain_emits_once(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "import flask from 'flask';\nflask.helper.nested('/y');\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.helper.nested"
    assert sites[0].usage_kind == "call"


def test_plain_attribute_access_without_call(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("import flask from 'flask';\nconst x = flask.config;\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].usage_kind == "attribute"


def test_untracked_package_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("import lodash from 'lodash';\nlodash.map([1]);\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []


def test_relative_import_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("import flask from './flask';\nflask.route();\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []


def test_scoped_package_root(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "import x from '@scope/pkg';\nx.method();\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["@scope/pkg"])

    assert len(sites) == 1
    assert sites[0].symbol == "@scope/pkg.method"


def test_syntax_error_file_still_yields_valid_matches(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(
        "import flask from 'flask';\nflask.route('/x');\nfunction broken( {\n"
    )

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].symbol == "flask.route"


def test_respects_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored/\n")
    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "app.js").write_text("import flask from 'flask';\nflask.route();\n")
    (tmp_path / "kept.js").write_text("import flask from 'flask';\nflask.route();\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert len(sites) == 1
    assert sites[0].file_path.name == "kept.js"


def test_skips_node_modules(tmp_path: Path) -> None:
    nm_dir = tmp_path / "node_modules" / "somepkg"
    nm_dir.mkdir(parents=True)
    (nm_dir / "index.js").write_text("import flask from 'flask';\nflask.route();\n")

    sites = TreeSitterJsAnalyzer().analyze(tmp_path, ["flask"])

    assert sites == []
