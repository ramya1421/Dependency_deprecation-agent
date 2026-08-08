import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from dda.domain.entities import Chunk
from dda.infrastructure.rag._markdown import is_fence_delimiter, match_heading
from dda.infrastructure.rag.tokenizer import count_tokens as _default_count_tokens

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
_VERSION_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)?(?:[-.][A-Za-z0-9]+)?\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class _Section:
    header_path: tuple[str, ...]
    content: str


class MarkdownChunker:
    """Splits cleaned markdown along its own heading structure, not at fixed
    offsets, and prepends each chunk's full header path into the chunk TEXT
    itself (not just metadata) — "removed .format()" means nothing without
    the "4.0.0 > Breaking Changes" context above it.
    """

    def __init__(
        self,
        count_tokens: Callable[[str], int] | None = None,
        target_tokens: int = 450,
        max_tokens: int = 511,  # bge-small's 512-token context, minus a margin
        overlap_ratio: float = 0.15,
    ) -> None:
        # Target sits at the low end of the prompt's stated 400-800 range:
        # the top of that range would exceed bge-small's 512-token limit.
        self._count_tokens = count_tokens or _default_count_tokens
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = max(int(target_tokens * overlap_ratio), 1)

    def chunk(
        self,
        markdown: str,
        *,
        package: str,
        doc_type: str,
        source_url: str,
        version: str | None = None,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in _parse_sections(markdown):
            section_version = version or _parse_version(section.header_path)
            header_prefix = " > ".join(section.header_path)
            for index, text in enumerate(self._split_section(header_prefix, section.content)):
                chunks.append(
                    Chunk(
                        chunk_id=_make_chunk_id(source_url, section.header_path, index),
                        text=text,
                        package=package,
                        doc_type=doc_type,
                        source_url=source_url,
                        header_path=header_prefix,
                        version=section_version,
                        token_count=self._count_tokens(text),
                    )
                )
        return chunks

    def _split_section(self, header_prefix: str, body: str) -> list[str]:
        blocks = [b for b in _split_into_blocks(body) if b.strip()]
        if not blocks:
            return []
        prefix_text = f"{header_prefix}\n\n" if header_prefix else ""
        prefix_tokens = self._count_tokens(prefix_text)
        budget = max(self._target_tokens - prefix_tokens, 50)
        hard_cap = max(self._max_tokens - prefix_tokens, 50)
        pieces = self._accumulate(blocks, budget, hard_cap)
        return [f"{prefix_text}{piece}" for piece in pieces]

    def _accumulate(self, blocks: list[str], budget: int, hard_cap: int) -> list[str]:
        pieces: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for block in blocks:
            for sub_block in self._split_oversized(block, hard_cap):
                block_tokens = self._count_tokens(sub_block)
                if current and current_tokens + block_tokens > budget:
                    pieces.append("\n\n".join(current))
                    current, current_tokens = self._take_overlap(current)
                current.append(sub_block)
                current_tokens += block_tokens
        if current:
            pieces.append("\n\n".join(current))
        return pieces

    def _split_oversized(self, block: str, hard_cap: int) -> list[str]:
        if self._count_tokens(block) <= hard_cap:
            return [block]
        # Pathological case: one block (e.g. an unbroken paragraph) still
        # exceeds the cap alone. Fall back to sentences, then to a hard
        # word-window cut, so the cap is never actually violated.
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(block) if s]
        if len(sentences) > 1:
            result: list[str] = []
            for sentence in sentences:
                result.extend(self._split_oversized(sentence, hard_cap))
            return result
        return self._hard_split(block, hard_cap)

    def _hard_split(self, text: str, hard_cap: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        pieces: list[str] = []
        current: list[str] = []
        for word in words:
            current.append(word)
            if self._count_tokens(" ".join(current)) > hard_cap:
                current.pop()
                if current:
                    pieces.append(" ".join(current))
                current = [word]
        if current:
            pieces.append(" ".join(current))
        return pieces

    def _take_overlap(self, current: list[str]) -> tuple[list[str], int]:
        overlap: list[str] = []
        tokens = 0
        for block in reversed(current):
            block_tokens = self._count_tokens(block)
            if tokens and tokens + block_tokens > self._overlap_tokens:
                break
            overlap.insert(0, block)
            tokens += block_tokens
        return overlap, tokens


def _parse_sections(markdown: str) -> list[_Section]:
    lines = markdown.splitlines()
    stack: list[tuple[int, str]] = []
    sections: list[_Section] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            sections.append(_Section(header_path=tuple(h for _, h in stack), content=text))
        current.clear()

    for line in lines:
        if is_fence_delimiter(line):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence:
            heading = match_heading(line)
            if heading is not None:
                flush()
                level, text = heading
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                continue
        current.append(line)
    flush()
    return sections


def _split_into_blocks(text: str) -> list[str]:
    """Blank lines are natural block boundaries, but changelog bullet lists
    usually have none between adjacent items — so a list-item start is also
    treated as a boundary, with its indented continuation lines grouped in.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    blocks: list[str] = []
    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        if sum(1 for line in lines if _LIST_ITEM_RE.match(line)) <= 1:
            blocks.append(paragraph)
            continue
        current: list[str] = []
        for line in lines:
            if _LIST_ITEM_RE.match(line) and current:
                blocks.append("\n".join(current))
                current = []
            current.append(line)
        if current:
            blocks.append("\n".join(current))
    return blocks


def _parse_version(header_path: tuple[str, ...]) -> str | None:
    for heading in reversed(header_path):
        match = _VERSION_RE.search(heading)
        if match:
            return match.group(0)
    return None


def _make_chunk_id(source_url: str, header_path: tuple[str, ...], index: int) -> str:
    material = f"{source_url}|{' > '.join(header_path)}|{index}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]
