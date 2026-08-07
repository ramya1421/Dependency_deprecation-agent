from pathlib import Path

import tree_sitter_javascript as tsjavascript
from tree_sitter import Language, Node, Parser, Query, QueryCursor, Tree

from dda.domain.entities import UsageSite
from dda.domain.ports import IUsageAnalyzer
from dda.domain.value_objects import Confidence, Ecosystem
from dda.infrastructure.analyzers._file_walk import iter_source_files

_JS_PATTERNS = ("*.js", "*.jsx", "*.mjs", "*.cjs")

# Order matters: query sibling patterns must follow the grammar's own child
# order (import_clause before the `source:` field) or the match silently
# drops the optional captures.
_IMPORT_QUERY = """
(import_statement
  (import_clause (identifier) @default)?
  (import_clause (namespace_import (identifier) @ns))?
  (import_clause (named_imports (import_specifier
     name: (identifier) @name
     alias: (identifier)? @alias)))?
  source: (string (string_fragment) @src)
) @stmt
"""

_REQUIRE_BINDING_QUERY = """
(variable_declarator
  name: (identifier) @binding
  value: (call_expression
    function: (identifier) @require_fn
    arguments: (arguments (string (string_fragment) @src))
    (#eq? @require_fn "require")))
"""

_MEMBER_QUERY = "(member_expression) @member"


def _package_root(module: str) -> str:
    if module.startswith("@"):
        parts = module.split("/")
        return "/".join(parts[:2]).lower() if len(parts) >= 2 else module.lower()
    return module.split("/")[0].lower()


def _is_relative(module: str) -> bool:
    return module.startswith((".", "/"))


def _resolve_chain(node: Node, alias_map: dict[str, str]) -> str | None:
    if node.type == "identifier":
        return alias_map.get(node.text.decode("utf-8")) if node.text else None
    if node.type == "member_expression":
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        if obj is None or prop is None or prop.text is None:
            return None
        base = _resolve_chain(obj, alias_map)
        return f"{base}.{prop.text.decode('utf-8')}" if base is not None else None
    return None


def _is_root_member(node: Node) -> bool:
    parent = node.parent
    return not (
        parent is not None
        and parent.type == "member_expression"
        and parent.child_by_field_name("object") == node
    )


def _is_call_target(node: Node) -> bool:
    parent = node.parent
    return (
        parent is not None
        and parent.type == "call_expression"
        and parent.child_by_field_name("function") == node
    )


class TreeSitterJsAnalyzer(IUsageAnalyzer):
    """Uses tree-sitter's error-tolerant parser, so a file with syntax errors
    still yields whatever usage sites can be found in its valid portions
    instead of failing the whole scan.
    """

    def __init__(self) -> None:
        self._language = Language(tsjavascript.language())
        self._parser = Parser(self._language)
        self._import_query = Query(self._language, _IMPORT_QUERY)
        self._require_query = Query(self._language, _REQUIRE_BINDING_QUERY)
        self._member_query = Query(self._language, _MEMBER_QUERY)

    @property
    def ecosystem(self) -> Ecosystem:
        return Ecosystem.JAVASCRIPT

    def analyze(self, repo_root: Path, packages: list[str]) -> list[UsageSite]:
        tracked = {p.lower() for p in packages}
        usage_sites: list[UsageSite] = []
        for file_path in iter_source_files(repo_root, _JS_PATTERNS):
            usage_sites.extend(self._analyze_file(file_path, tracked))
        return usage_sites

    def _analyze_file(self, file_path: Path, tracked: set[str]) -> list[UsageSite]:
        try:
            source = file_path.read_bytes()
        except OSError:
            return []
        tree = self._parser.parse(source)
        alias_map = self._build_alias_map(tree, tracked)
        if not alias_map:
            return []
        source_lines = source.decode("utf-8", errors="replace").splitlines()
        return self._find_usages(tree, alias_map, file_path, source_lines)

    def _build_alias_map(self, tree: Tree, tracked: set[str]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for _, caps in QueryCursor(self._import_query).matches(tree.root_node):
            module = _text(caps["src"][0])
            if _is_relative(module) or _package_root(module) not in tracked:
                continue
            if "default" in caps:
                alias_map[_text(caps["default"][0])] = module
            if "ns" in caps:
                alias_map[_text(caps["ns"][0])] = module
            if "name" in caps:
                exported = _text(caps["name"][0])
                bound = _text(caps["alias"][0]) if "alias" in caps else exported
                alias_map[bound] = f"{module}.{exported}"

        for _, caps in QueryCursor(self._require_query).matches(tree.root_node):
            module = _text(caps["src"][0])
            if _is_relative(module) or _package_root(module) not in tracked:
                continue
            alias_map[_text(caps["binding"][0])] = module
        return alias_map

    def _find_usages(
        self, tree: Tree, alias_map: dict[str, str], file_path: Path, source_lines: list[str]
    ) -> list[UsageSite]:
        usage_sites: list[UsageSite] = []
        for _, caps in QueryCursor(self._member_query).matches(tree.root_node):
            node = caps["member"][0]
            if not _is_root_member(node):
                continue
            resolved = _resolve_chain(node, alias_map)
            if resolved is None:
                continue
            usage_kind = "call" if _is_call_target(node) else "attribute"
            usage_sites.append(
                _make_usage_site(node, resolved, usage_kind, file_path, source_lines)
            )
        return usage_sites


def _text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text else ""


def _make_usage_site(
    node: Node, symbol: str, usage_kind: str, file_path: Path, source_lines: list[str]
) -> UsageSite:
    line = node.start_point.row + 1
    snippet = source_lines[line - 1].strip() if 0 < line <= len(source_lines) else ""
    return UsageSite(
        package=symbol.split(".")[0],
        symbol=symbol,
        file_path=file_path,
        line_number=line,
        column_number=node.start_point.column,
        usage_kind=usage_kind,
        confidence=Confidence.STATIC_CONFIRMED,
        snippet=snippet,
    )
