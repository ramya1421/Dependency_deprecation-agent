import re

from dda.infrastructure.rag._markdown import (
    convert_underline_headings,
    is_fence_delimiter,
    match_heading,
)

_BADGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*shields\.io[^)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>\n]+>")
_LINK_REF_DEF_RE = re.compile(r"^\s*\[[^\]]+\]:\s*\S.*$", re.MULTILINE)


def clean(markdown: str) -> str:
    """Strips noise that consumes embedding capacity without adding meaning:
    shields.io badges, raw HTML, and markdown link-reference footers. Also
    normalises heading levels so documents pulled from different repos (one
    starting at `#`, another at `###`) nest consistently.
    """
    text = convert_underline_headings(markdown)
    text = _BADGE_RE.sub("", text)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _LINK_REF_DEF_RE.sub("", text)
    text = _normalize_heading_levels(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_heading_levels(text: str) -> str:
    lines = text.splitlines()
    levels = _collect_heading_levels(lines)
    if not levels:
        return text
    shift = min(levels) - 1
    if shift <= 0:
        return text
    return "\n".join(_shift_headings(lines, shift))


def _collect_heading_levels(lines: list[str]) -> list[int]:
    levels: list[int] = []
    in_fence = False
    for line in lines:
        if is_fence_delimiter(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = match_heading(line)
        if heading is not None:
            levels.append(heading[0])
    return levels


def _shift_headings(lines: list[str], shift: int) -> list[str]:
    result: list[str] = []
    in_fence = False
    for line in lines:
        if is_fence_delimiter(line):
            in_fence = not in_fence
            result.append(line)
            continue
        if not in_fence:
            heading = match_heading(line)
            if heading is not None:
                level, heading_text = heading
                result.append("#" * max(level - shift, 1) + " " + heading_text)
                continue
        result.append(line)
    return result
