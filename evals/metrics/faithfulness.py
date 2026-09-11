"""Faithfulness and hallucination metrics.

faithfulness  = verified_claims / total_claims
hallucination = claims with no cited chunk / total_claims

Both require that the answer contains inline [chunk_id] markers. Answers
without any citations score 0 faithfulness and 1.0 hallucination — this is
intentional and correct: an uncited claim cannot be verified.

The LLM judge uses a DIFFERENT model than the generator (same rule as the
agent's verify node) so it can't confirm its own output.
"""
from __future__ import annotations

import re
from typing import Any

from dda.domain.ports import ILLMClient

_CITATION_RE = re.compile(r"\[([0-9a-f]{16})\]")

_JUDGE_SYSTEM = (
    "You are a fact-checker. Answer only with JSON. "
    "Does the SOURCE PASSAGE directly support the CLAIM? "
    "No outside knowledge. Only use what is in the passage."
)
_JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["supported", "confidence"],
}


def hallucination_rate(answer: str, chunk_ids_available: set[str]) -> float:
    """Fraction of cited chunks that do not exist in the retrieved set.

    An uncited answer scores 1.0 (fully hallucinated from the system's
    perspective — we cannot verify it).
    """
    cited = set(_CITATION_RE.findall(answer))
    if not cited:
        return 1.0
    missing = cited - chunk_ids_available
    return len(missing) / len(cited)


def faithfulness_score(
    claims: list[dict[str, Any]],
    chunk_map: dict[str, str],
    judge_llm: ILLMClient,
) -> float:
    """Fraction of claims verified as supported by their cited chunk.

    claims: list of {text, chunk_id} dicts
    chunk_map: chunk_id -> chunk text
    judge_llm: a different model from the generator
    """
    if not claims:
        return 0.0
    supported = 0
    for claim in claims:
        chunk_text = chunk_map.get(str(claim.get("chunk_id", "")), "")
        if not chunk_text:
            continue
        result = judge_llm.generate_structured(
            prompt=f"CLAIM: {claim['text']}\n\nSOURCE PASSAGE:\n{chunk_text[:600]}",
            schema=_JUDGE_SCHEMA,
            system=_JUDGE_SYSTEM,
            temperature=0.0,
        )
        if result.get("supported"):
            supported += 1
    return supported / len(claims)


def extract_claims(answer: str, chunk_map: dict[str, str]) -> list[dict[str, Any]]:
    """Split answer into sentences with their cited chunk IDs."""
    claims: list[dict[str, Any]] = []
    # Split on sentence boundaries, keeping citation markers.
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    for sentence in sentences:
        cited = _CITATION_RE.findall(sentence)
        if cited:
            claims.append({"text": sentence.strip(), "chunk_id": cited[0]})
    return claims
