import json
import logging

from dda.agent.prompts.loader import load
from dda.agent.state import AgentState
from dda.domain.ports import ILLMClient

logger = logging.getLogger(__name__)

# If more than 30% of claims are dropped the plan is too speculative —
# send it back for one re-synthesis with a stricter prompt. One retry only.
_DROP_THRESHOLD = 0.30

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "entailment_score": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["supported", "entailment_score"],
}


def verify_node(state: AgentState, judge_llm: ILLMClient) -> AgentState:
    """Verify each claim against its cited chunk using a different model than
    the generator (Groq judges Gemini) — the generator confirming its own
    output is not verification.

    Drops unsupported claims and records the drop count. If > 30% are dropped
    the edge sends the state back to synthesize for one retry.
    """
    claims: list[dict[str, object]] = state.get("claims", [])
    chunk_map = {c.chunk_id: c for c in state.get("retrieved_chunks", [])}
    verified: list[dict[str, object]] = []
    dropped = 0

    for claim in claims:
        chunk_id = str(claim.get("chunk_id", ""))
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            # Claim cites a chunk that wasn't retrieved — drop it.
            dropped += 1
            continue

        prompt = load("verify").format(
            claim=claim["text"],
            chunk_id=chunk_id,
            chunk_text=chunk.text[:600],
            schema=json.dumps(_SCHEMA, indent=2),
        )
        result = judge_llm.generate_structured(prompt, _SCHEMA)
        supported = bool(result.get("supported", False))
        score = float(result.get("entailment_score", 0.0))

        if supported:
            verified.append({
                "text": claim["text"],
                "chunk_id": chunk_id,
                "verified": True,
                "entailment_score": score,
            })
        else:
            dropped += 1

    drop_rate = dropped / len(claims) if claims else 0.0

    logger.info("verify_node", extra={
        "package": state["package"],
        "claims": len(claims),
        "verified": len(verified),
        "dropped": dropped,
        "drop_rate": drop_rate,
    })

    return {
        **state,
        "verified_claims": verified,
        "route_history": state.get("route_history", []) + [
            f"verify:drop_rate={drop_rate:.2f}"
        ],
    }


def should_retry_synthesis(state: AgentState) -> str:
    """Edge: retry synthesis once if too many claims were dropped."""
    claims = state.get("claims", [])
    verified = state.get("verified_claims", [])
    if not claims:
        return "finalize"
    drop_rate = 1.0 - len(verified) / len(claims)
    # One retry only — check route_history for a prior synthesize re-run.
    already_retried = sum(1 for r in state.get("route_history", []) if r == "synthesize") > 1
    if drop_rate > _DROP_THRESHOLD and not already_retried:
        return "synthesize"
    return "finalize"
