import ast
from pathlib import Path

from dda.domain.entities import UsageSite
from dda.domain.ports import IUsageAnalyzer
from dda.domain.value_objects import Confidence, Ecosystem
from dda.infrastructure.analyzers._file_walk import iter_source_files

_PY_PATTERNS = ("*.py",)


class PythonAstAnalyzer(IUsageAnalyzer):
    @property
    def ecosystem(self) -> Ecosystem:
        return Ecosystem.PYTHON

    def analyze(self, repo_root: Path, packages: list[str]) -> list[UsageSite]:
        tracked = {p.lower() for p in packages}
        usage_sites: list[UsageSite] = []
        for file_path in iter_source_files(repo_root, _PY_PATTERNS):
            usage_sites.extend(_analyze_file(file_path, tracked))
        return usage_sites


def _analyze_file(file_path: Path, tracked: set[str]) -> list[UsageSite]:
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        # One unparseable file (a syntax error, a stray binary, ...) shouldn't
        # sink the whole scan.
        return []
    visitor = _UsageVisitor(file_path, source.splitlines(), tracked)
    visitor.visit(tree)
    return visitor.usage_sites


class _UsageVisitor(ast.NodeVisitor):
    """Resolves Attribute/Call expressions back to package.symbol form via an
    alias map built from this file's own imports, restricted to `tracked`.
    """

    def __init__(self, file_path: Path, source_lines: list[str], tracked: set[str]) -> None:
        self._file_path = file_path
        self._source_lines = source_lines
        self._tracked = tracked
        self._alias_map: dict[str, str] = {}
        # Track importlib specifically (even though it's not a tracked
        # package itself) so importlib.import_module("<tracked pkg>") calls
        # can be flagged as a dynamic, POSSIBLE-confidence reference.
        self._importlib_module_alias: str | None = None
        self._import_module_func_alias: str | None = None
        self.usage_sites: list[UsageSite] = []

    # --- imports: build the alias map --------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "importlib":
                self._importlib_module_alias = alias.asname or "importlib"
            root = alias.name.split(".")[0]
            if root.lower() not in self._tracked:
                continue
            if alias.asname:
                # `import a.b.c as x` binds x directly to the a.b.c module.
                self._alias_map[alias.asname] = alias.name
            else:
                # `import a.b.c` binds only "a"; `.b.c` comes from real
                # attribute traversal through a's actual submodules, not
                # from anything stored here.
                self._alias_map[root] = root

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level > 0 or node.module is None:
            return  # relative import: can't refer to an external tracked package
        if node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    self._import_module_func_alias = alias.asname or "import_module"
            return
        if node.module.split(".")[0].lower() not in self._tracked:
            return
        for alias in node.names:
            if alias.name == "*":
                self._emit(node, "*", "star_import", Confidence.POSSIBLE)
                continue
            self._alias_map[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    # --- usage sites ---------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        dynamic_target = self._dynamic_import_target(node)
        if dynamic_target is not None:
            if dynamic_target.split(".")[0].lower() in self._tracked:
                self._emit(node, dynamic_target, "dynamic_import", Confidence.POSSIBLE)
            self._visit_call_children(node)
            return

        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and node.args:
            base = self._resolve(node.args[0])
            if base is not None:
                self._emit(node, f"{base}.<dynamic>", "getattr", Confidence.POSSIBLE)
                self._visit_call_children(node, skip_first_arg=True)
                return

        resolved = self._resolve(node.func)
        if resolved is not None:
            self._emit(node, resolved, "call", Confidence.STATIC_CONFIRMED)
        else:
            self.visit(node.func)
        self._visit_call_children(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        resolved = self._resolve(node)
        if resolved is not None:
            self._emit(node, resolved, "attribute", Confidence.STATIC_CONFIRMED)
        else:
            self.generic_visit(node)

    # --- helpers ---------------------------------------------------------

    def _resolve(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name):
            return self._alias_map.get(expr.id)
        if isinstance(expr, ast.Attribute):
            base = self._resolve(expr.value)
            return f"{base}.{expr.attr}" if base is not None else None
        return None

    def _dynamic_import_target(self, node: ast.Call) -> str | None:
        func = node.func
        is_module_call = (
            self._importlib_module_alias is not None
            and isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == self._importlib_module_alias
        )
        is_direct_call = (
            self._import_module_func_alias is not None
            and isinstance(func, ast.Name)
            and func.id == self._import_module_func_alias
        )
        if not (is_module_call or is_direct_call) or not node.args:
            return None
        first_arg = node.args[0]
        return first_arg.value if isinstance(first_arg, ast.Constant) and isinstance(
            first_arg.value, str
        ) else None

    def _visit_call_children(self, node: ast.Call, skip_first_arg: bool = False) -> None:
        for arg in (node.args[1:] if skip_first_arg else node.args):
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def _emit(
        self, node: ast.AST, symbol: str, usage_kind: str, confidence: Confidence
    ) -> None:
        line: int = getattr(node, "lineno", 0)
        in_range = 0 < line <= len(self._source_lines)
        snippet = self._source_lines[line - 1].strip() if in_range else ""
        self.usage_sites.append(
            UsageSite(
                package=symbol.split(".")[0],
                symbol=symbol,
                file_path=self._file_path,
                line_number=line,
                column_number=getattr(node, "col_offset", 0),
                usage_kind=usage_kind,
                confidence=confidence,
                snippet=snippet,
            )
        )
