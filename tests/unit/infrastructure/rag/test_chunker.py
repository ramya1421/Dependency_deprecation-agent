from pathlib import Path

from dda.infrastructure.rag.chunker import MarkdownChunker
from dda.infrastructure.rag.cleaner import clean

FIXTURES = Path(__file__).parents[3] / "fixtures" / "changelogs"


def _word_count(text: str) -> int:
    # Fast, deterministic, offline stand-in for the real bge-small tokenizer
    # — tests care about chunking *behavior*, not exact token boundaries.
    return len(text.split())


def _chunker(**kwargs: object) -> MarkdownChunker:
    return MarkdownChunker(count_tokens=_word_count, **kwargs)  # type: ignore[arg-type]


def test_header_path_is_prepended_into_chunk_text() -> None:
    markdown = "# Changelog\n\n## 4.0.0\n\n### Breaking Changes\n\n- removed .format()\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/CHANGELOG.md"
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.header_path == "Changelog > 4.0.0 > Breaking Changes"
    assert chunk.text.startswith("Changelog > 4.0.0 > Breaking Changes")
    assert "removed .format()" in chunk.text


def test_real_changelog_fixture_preserves_header_context() -> None:
    """The explicit requirement: a bullet like "Drop support for Python 3.9"
    is meaningless without knowing which version it came from — assert that
    context is actually present in the same chunk, not just in metadata.
    """
    raw = (FIXTURES / "flask_CHANGES.rst").read_text(encoding="utf-8")
    cleaned = clean(raw)

    chunks = _chunker().chunk(
        cleaned,
        package="flask",
        doc_type="changelog",
        source_url="https://raw.githubusercontent.com/pallets/flask/main/CHANGES.rst",
    )

    assert len(chunks) > 1
    version_chunk = next(c for c in chunks if "Drop support for Python 3.9" in c.text)
    assert version_chunk.header_path == "Version 3.2.0"
    assert version_chunk.text.startswith("Version 3.2.0")
    assert version_chunk.version == "3.2.0"

    # Every chunk, not just one cherry-picked example, carries its header.
    for chunk in chunks:
        assert chunk.text.startswith(chunk.header_path)


def test_rst_underline_headings_are_recognized() -> None:
    raw = (FIXTURES / "flask_CHANGES.rst").read_text(encoding="utf-8")
    cleaned = clean(raw)

    chunks = _chunker().chunk(
        cleaned, package="flask", doc_type="changelog", source_url="https://example.test/CHANGES.rst"
    )

    header_paths = {c.header_path for c in chunks}
    assert "Version 3.2.0" in header_paths
    assert "Version 3.1.3" in header_paths
    assert "Version 3.0.0" in header_paths


def test_nested_headers_build_full_path() -> None:
    markdown = "# A\n\n## B\n\n### C\n\ncontent here\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert chunks[0].header_path == "A > B > C"


def test_sibling_headings_reset_the_path_correctly() -> None:
    markdown = "# Changelog\n\n## 2.0.0\n\nfirst\n\n## 1.0.0\n\nsecond\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    paths = [c.header_path for c in chunks]
    assert paths == ["Changelog > 2.0.0", "Changelog > 1.0.0"]


def test_container_heading_with_no_direct_content_produces_no_chunk() -> None:
    markdown = "# Changelog\n\n## 4.0.0\n\n### Breaking Changes\n\n- a thing\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    # "Changelog" and "Changelog > 4.0.0" have no content of their own —
    # only the deepest heading with an actual bullet should produce a chunk.
    assert [c.header_path for c in chunks] == ["Changelog > 4.0.0 > Breaking Changes"]


def test_code_fence_hash_is_not_treated_as_heading() -> None:
    markdown = "# Changelog\n\n## 1.0.0\n\n```python\n# not a heading\nx = 1\n```\n\nreal text\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert len(chunks) == 1
    assert chunks[0].header_path == "Changelog > 1.0.0"
    assert "# not a heading" in chunks[0].text


def test_chunks_never_exceed_max_tokens() -> None:
    bullets = "\n".join(f"- item number {i} with some extra words to pad it out" for i in range(60))
    markdown = f"# Changelog\n\n## 1.0.0\n\n{bullets}\n"

    chunker = _chunker(target_tokens=40, max_tokens=55, overlap_ratio=0.15)
    chunks = chunker.chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert _word_count(chunk.text) <= 55


def test_overlap_carries_trailing_content_into_next_chunk() -> None:
    bullets = "\n".join(f"- item number {i} with some extra words to pad it out" for i in range(40))
    markdown = f"# Changelog\n\n## 1.0.0\n\n{bullets}\n"

    chunker = _chunker(target_tokens=40, max_tokens=55, overlap_ratio=0.3)
    chunks = chunker.chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert len(chunks) >= 2
    first_lines = chunks[0].text.splitlines()
    second_lines = chunks[1].text.splitlines()
    assert any(line in second_lines for line in first_lines if line.startswith("- item"))


def test_explicit_version_overrides_header_parsed_version() -> None:
    markdown = "# Release notes\n\nsome release body text\n"

    chunks = _chunker().chunk(
        markdown,
        package="pkg",
        doc_type="release_note",
        source_url="https://example.test/releases/9.9.9",
        version="9.9.9",
    )

    assert chunks[0].version == "9.9.9"


def test_chunk_id_is_deterministic_across_runs() -> None:
    markdown = "# Changelog\n\n## 1.0.0\n\n- a bullet\n"

    first = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )
    second = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_token_count_is_recorded_on_the_chunk() -> None:
    markdown = "# Changelog\n\n## 1.0.0\n\n- a bullet with five words\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert chunks[0].token_count == _word_count(chunks[0].text)


def test_content_before_any_heading_has_empty_header_path() -> None:
    markdown = "Some intro text with no heading above it.\n"

    chunks = _chunker().chunk(
        markdown, package="pkg", doc_type="changelog", source_url="https://example.test/x"
    )

    assert len(chunks) == 1
    assert chunks[0].header_path == ""
    assert chunks[0].text == "Some intro text with no heading above it."
