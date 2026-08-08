from dda.infrastructure.rag.cleaner import clean


def test_strips_shields_io_badges() -> None:
    text = "# Title\n\n![Build](https://img.shields.io/badge/build-passing-green)\n\nreal content\n"

    result = clean(text)

    assert "shields.io" not in result
    assert "real content" in result


def test_strips_html_comments() -> None:
    text = "# Title\n\n<!-- this is a generator marker -->\n\nreal content\n"

    result = clean(text)

    assert "generator marker" not in result
    assert "real content" in result


def test_strips_raw_html_tags() -> None:
    text = "# Title\n\n<p align='center'>centered</p>\n\nreal content\n"

    result = clean(text)

    assert "<p" not in result
    assert "centered" in result
    assert "real content" in result


def test_strips_link_reference_definitions() -> None:
    text = "# Title\n\nSee [the docs][1].\n\n[1]: https://example.test/docs\n"

    result = clean(text)

    assert "[1]: https://example.test/docs" not in result
    assert "See [the docs][1]" in result


def test_normalizes_heading_levels_when_document_starts_deep() -> None:
    text = "### Title\n\n#### Subsection\n\ncontent\n"

    result = clean(text)

    assert "# Title" in result.splitlines()
    assert "## Subsection" in result.splitlines()


def test_does_not_shift_headings_already_starting_at_one() -> None:
    text = "# Title\n\n## Subsection\n\ncontent\n"

    result = clean(text)

    assert "# Title" in result.splitlines()
    assert "## Subsection" in result.splitlines()


def test_does_not_treat_fenced_code_hash_as_heading_for_normalization() -> None:
    text = "### Title\n\n```python\n# a comment, not a heading\n```\n"

    result = clean(text)

    assert "# Title" in result.splitlines()
    assert "# a comment, not a heading" in result


def test_collapses_excess_blank_lines() -> None:
    text = "# Title\n\n\n\n\ncontent\n"

    result = clean(text)

    assert "\n\n\n" not in result


def test_converts_rst_underline_headings() -> None:
    text = "Version 3.2.0\n-------------\n\nsome content\n"

    result = clean(text)

    assert result.splitlines()[0] == "# Version 3.2.0"
