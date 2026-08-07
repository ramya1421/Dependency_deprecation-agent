from collections.abc import Iterator
from pathlib import Path

import pathspec
from pathspec.pattern import Pattern

# Common dependency/build/venv dirs to skip outright, on top of whatever the
# repo's own .gitignore excludes (many repos don't bother gitignoring these).
_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "site-packages",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def iter_source_files(repo_root: Path, patterns: tuple[str, ...]) -> Iterator[Path]:
    """Yield files under `repo_root` matching any of `patterns`, skipping
    common non-source directories and anything the repo's .gitignore excludes.
    """
    spec = _load_gitignore(repo_root)
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(repo_root.rglob(pattern)):
            if path in seen:
                continue
            relative = path.relative_to(repo_root)
            if any(part in _SKIP_DIR_NAMES for part in relative.parts[:-1]):
                continue
            if spec.match_file(str(relative)):
                continue
            seen.add(path)
            yield path


def _load_gitignore(repo_root: Path) -> pathspec.PathSpec[Pattern]:
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.is_file():
        return pathspec.PathSpec.from_lines("gitignore", [])
    lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    return pathspec.PathSpec.from_lines("gitignore", lines)
