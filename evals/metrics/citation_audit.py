"""Citation audit CSV export for hand-review.

Exports up to 100 (claim, chunk_text, source_url) rows so a human can
audit whether citations are accurate. This is unglamorous but is the part
that makes numbers credible.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

_CITATION_RE = re.compile(r"\[([0-9a-f]{16})\]")
_MAX_ROWS = 100


def export_citation_csv(
    eval_results: list[dict[str, Any]],
    chunk_map: dict[str, Any],  # chunk_id -> Chunk
    output_path: Path,
) -> int:
    """Write citation audit CSV. Returns number of rows written."""
    rows: list[dict[str, str]] = []

    for result in eval_results:
        question = str(result.get("question", ""))
        answer = str(result.get("answer", ""))
        variant = str(result.get("variant", ""))
        package = str(result.get("package", ""))

        sentences = re.split(r"(?<=[.!?])\s+", answer)
        for sentence in sentences:
            cited = _CITATION_RE.findall(sentence)
            for chunk_id in cited:
                chunk = chunk_map.get(chunk_id)
                rows.append({
                    "question": question[:120],
                    "package": package,
                    "variant": variant,
                    "claim": sentence.strip()[:200],
                    "chunk_id": chunk_id,
                    "chunk_text": (chunk.text[:300] if chunk else "CHUNK NOT FOUND"),
                    "source_url": (chunk.source_url if chunk else ""),
                    "header_path": (chunk.header_path if chunk else ""),
                    "human_verdict": "",   # filled in manually
                })
                if len(rows) >= _MAX_ROWS:
                    break
            if len(rows) >= _MAX_ROWS:
                break
        if len(rows) >= _MAX_ROWS:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "question", "package", "variant", "claim",
            "chunk_id", "chunk_text", "source_url", "header_path", "human_verdict",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
