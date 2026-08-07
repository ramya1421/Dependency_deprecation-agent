from pathlib import Path

from dda.infrastructure.analyzers._file_walk import iter_source_files


def test_finds_files_matching_pattern(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")

    found = list(iter_source_files(tmp_path, ("*.py",)))

    assert [p.name for p in found] == ["a.py"]


def test_supports_multiple_patterns_without_duplicates(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("")
    (tmp_path / "b.jsx").write_text("")

    found = list(iter_source_files(tmp_path, ("*.js", "*.jsx", "*.js")))

    assert sorted(p.name for p in found) == ["a.js", "b.jsx"]


def test_skips_hardcoded_noise_dirs(tmp_path: Path) -> None:
    for dirname in (".venv", "node_modules", "__pycache__", ".git"):
        d = tmp_path / dirname
        d.mkdir()
        (d / "file.py").write_text("")
    (tmp_path / "kept.py").write_text("")

    found = list(iter_source_files(tmp_path, ("*.py",)))

    assert [p.name for p in found] == ["kept.py"]


def test_respects_gitignore_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("build/\n*.generated.py\n")
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "out.py").write_text("")
    (tmp_path / "x.generated.py").write_text("")
    (tmp_path / "kept.py").write_text("")

    found = list(iter_source_files(tmp_path, ("*.py",)))

    assert [p.name for p in found] == ["kept.py"]


def test_no_gitignore_file_is_fine(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")

    found = list(iter_source_files(tmp_path, ("*.py",)))

    assert [p.name for p in found] == ["a.py"]
