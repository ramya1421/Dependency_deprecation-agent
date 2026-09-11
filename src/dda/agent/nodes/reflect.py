import json
import logging

from dda.agent.prompts.loader import load
from dda.agent.state import AgentState, SubQuestion
from dda.domain.ports import ILLMClient

logger = logging.getLogger(__name__)

# After 3 reflections the graph moves on regardless — an infinite reflect
# loop would exhaust the free-tier quota silently.
MAX_REFLECTIONS = 3

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "sufficient": {"type": "boolean"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "reformulated_query": {"type": "string"},
    },
    "required": ["sufficient", "missing"],
}


def reflect_node(state: AgentState, llm: ILLMClient) -> AgentState:
    """Judge whether retrieved context is sufficient to answer outstanding questions.

    Returns sufficient=True (or hits MAX_REFLECTIONS) to proceed to synthesis.
    On insufficient, adds a new PROSE_QUERY sub-question using the reformulated
    query so the retrieve node will fetch better context next iteration.
    """
    reflection_count = state.get("reflection_count", 0) + 1

    # Cap: move on regardless after MAX_REFLECTIONS.
    if reflection_count > MAX_REFLECTIONS:
        logger.warning("reflect_max_reached", extra={"package": state["package"]})
        return {
            **state,
            "reflection_count": reflection_count,
            "route_history": state.get("route_history", []) + ["reflect:cap_reached"],
        }

    unanswered_prose = [
        q for q in state["sub_questions"]
        if not q["answered"] and q["route"] == "PROSE_QUERY"
    ]
    if not unanswered_prose:
        return {
            **state,
            "reflection_count": reflection_count,
            "route_history": state.get("route_history", []) + ["reflect:no_prose_pending"],
        }

    context_text = _format_chunks(state.get("retrieved_chunks", []))
    question_text = unanswered_prose[0]["text"]

    prompt = load("reflect").format(
        sub_question=question_text,
        context=context_text,
        schema=json.dumps(_SCHEMA, indent=2),
    )
    result = llm.generate_structured(prompt, _SCHEMA)
    sufficient: bool = bool(result.get("sufficient", False))
    reformulated: str = str(result.get("reformulated_query") or "")

    if not sufficient and reformulated:
        # Inject reformulated query as a new unanswered PROSE_QUERY.
        new_question = SubQuestion(
            text=reformulated, route="PROSE_QUERY", answered=False, answer=""
        )
        updated_questions = list(state["sub_questions"]) + [new_question]
    else:
        updated_questions = state["sub_questions"]

    logger.info("reflect_node", extra={
        "package": state["package"],
        "sufficient": sufficient,
        "reflection_count": reflection_count,
    })

    return {
        **state,
        "sub_questions": updated_questions,
        "reflection_count": reflection_count,
        "route_history": state.get("route_history", []) + [
            f"reflect:{'sufficient' if sufficient else 'insufficient'}"
        ],
    }


def should_continue_reflecting(state: AgentState) -> str:
    """Edge function: route back to retrieve if more context is needed."""
    if state.get("reflection_count", 0) >= MAX_REFLECTIONS:
        return "synthesize"
    # If there are still unanswered questions, go back to route/retrieve.
    unanswered = [q for q in state["sub_questions"] if not q["answered"]]
    if unanswered:
        return "route"
    return "synthesize"


def _format_chunks(chunks: list) -> str:  # type: ignore[type-arg]
    if not chunks:
        return "No context retrieved yet."
    parts = [f"[{c.chunk_id}] {c.header_path}\n{c.text[:400]}" for c in chunks[:8]]
    return "\n\n---\n\n".join(parts)
