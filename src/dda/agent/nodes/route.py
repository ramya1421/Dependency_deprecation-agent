import logging

from dda.agent.state import AgentState

logger = logging.getLogger(__name__)

# Hard cap on tool calls — an uncapped loop will exhaust a free tier at 2am.
MAX_TOOL_CALLS = 12


def route_node(state: AgentState) -> AgentState:
    """Classify each unanswered sub-question as STRUCTURED_FACT or PROSE_QUERY
    and record which one to execute next.  The classification was already made
    by the plan node; this node just picks the next unanswered question and
    updates route_history so the graph edge knows which executor to call.
    """
    unanswered = [q for q in state["sub_questions"] if not q["answered"]]

    if not unanswered or state["tool_call_count"] >= MAX_TOOL_CALLS:
        # No more questions or cap reached — signal move to synthesis.
        next_route = "DONE"
    else:
        next_route = unanswered[0]["route"]

    logger.info("route_node", extra={
        "package": state["package"],
        "next_route": next_route,
        "tool_call_count": state["tool_call_count"],
        "unanswered": len(unanswered),
    })

    return {
        **state,
        "route_history": state.get("route_history", []) + [f"route:{next_route}"],
    }


def next_route(state: AgentState) -> str:
    """Edge function: returns the route string for the next conditional edge."""
    unanswered = [q for q in state["sub_questions"] if not q["answered"]]
    if not unanswered or state["tool_call_count"] >= MAX_TOOL_CALLS:
        return "synthesize"
    return unanswered[0]["route"]
