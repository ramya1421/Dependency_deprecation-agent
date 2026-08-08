import re

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# Both CommonMark setext headings (`===`/`---` under a title) and RST's
# underline-style headings (any repeated punctuation char, level order
# inferred from first appearance) use this same "text line, then underline"
# shape. CHANGES.rst-style docs (explicitly a target format) rely entirely
# on this — without it they'd get zero header structure at all.
_UNDERLINE_CHARS = set("=-~^\"'`:.*+#_")


def is_fence_delimiter(line: str) -> bool:
    return bool(_FENCE_RE.match(line))


def match_heading(line: str) -> tuple[int, str] | None:
    """Return (level, text) if `line` is an ATX heading, else None.

    Callers must track fence state themselves and skip calling this while
    inside a code fence — a `#` there is a shell comment, not a heading.
    """
    match = _ATX_HEADING_RE.match(line)
    if match is None:
        return None
    return len(match.group(1)), match.group(2).strip()


def convert_underline_headings(text: str) -> str:
    """Rewrite setext/RST-style underlined headings to ATX form (`# Title`)
    so the rest of the pipeline only ever has to recognize one heading
    syntax. Level is assigned by order of first appearance of each distinct
    underline character, which degrades correctly to markdown's fixed
    `=`->H1, `-`->H2 convention when only those two are used.
    """
    lines = text.splitlines()
    level_for_char: dict[str, int] = {}
    result: list[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_fence_delimiter(line):
            in_fence = not in_fence
            result.append(line)
            i += 1
            continue
        if not in_fence and i + 1 < len(lines) and line.strip() and match_heading(line) is None:
            char = _underline_char(lines[i + 1])
            if char is not None:
                if char not in level_for_char:
                    level_for_char[char] = len(level_for_char) + 1
                level = min(level_for_char[char], 6)
                result.append("#" * level + " " + line.strip())
                i += 2
                continue
        result.append(line)
        i += 1
    return "\n".join(result)


def _underline_char(line: str) -> str | None:
    stripped = line.strip()
    if len(stripped) < 3 or len(set(stripped)) != 1:
        return None
    char = stripped[0]
    return char if char in _UNDERLINE_CHARS else None
