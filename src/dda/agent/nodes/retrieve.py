import logging

from dda.agent.state import AgentState, SubQuestion
from dda.agent.tools.registry import AgentToolRegistry

logger = logging.getLogger(__name__)

_TOP_K = 5


async def retrieve_node(state: AgentState, tools: AgentToolRegistry) -> AgentState:
    """Execute the next unanswered sub-question.

    STRUCTURED_FACT questions call deterministic tools (no vector search).
    PROSE_QUERY questions call search_migration_kb — the only RAG path.
    This is the node where the routing decision made in plan_node becomes real.
    """
    unanswered = [q for q in state["sub_questions"] if not q["answered"]]
    if not unanswered:
        return state

    question = unanswered[0]
    route = question["route"]
    tool_call_count = state["tool_call_count"] + 1

    new_chunks = state.get("retrieved_chunks", [])
    structured_facts = dict(state.get("structured_facts", {}))
    answer = ""

    if route == "PROSE_QUERY":
        chunks = tools.search_migration_kb(question["text"], state["package"], _TOP_K)
        new_chunks = list(new_chunks) + [c for c in chunks if c not in new_chunks]
        answer = f"Retrieved {len(chunks)} chunk(s) from migration KB."

    elif route == "STRUCTURED_FACT":
        result = await _call_structured_tool(question["text"], state, tools)
        structured_facts[question["text"]] = result
        answer = str(result)

    # Mark the question answered and record in sub_questions list.
    updated_questions: list[SubQuestion] = [
        SubQuestion(**{**q, "answered": True, "answer": answer})
        if q["text"] == question["text"] and not q["answered"]
        else q
        for q in state["sub_questions"]
    ]

    logger.info("retrieve_node", extra={
        "package": state["package"],
        "route": route,
        "question": question["text"][:80],
        "tool_call_count": tool_call_count,
    })

    return {
        **state,
        "sub_questions": updated_questions,
        "retrieved_chunks": new_chunks,
        "structured_facts": structured_facts,
        "tool_call_count": tool_call_count,
        "route_history": state.get("route_history", []) + [f"retrieve:{route}"],
    }


async def _call_structured_tool(
    question: str, state: AgentState, tools: AgentToolRegistry
) -> object:
    """Dispatch to the right deterministic tool based on question keywords."""
    q = question.lower()
    package = state["package"]
    if "vulnerabilit" in q or "cve" in q or "advisor" in q:
        return await tools.get_advisories(package, None)
    if "eol" in q or "end of life" in q or "end-of-life" in q:
        return await tools.get_eol_status(package, None)
    if "github" in q or "activit" in q or "abandon" in q or "archive" in q:
        return await tools.get_repo_activity(package)
    # Default: fetch registry metadata (deprecation flag, latest version).
    return await tools.get_package_metadata(package, state["ecosystem"])
