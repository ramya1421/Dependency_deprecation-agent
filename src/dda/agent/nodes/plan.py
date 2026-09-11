import json
import logging

from dda.agent.prompts.loader import load
from dda.agent.state import AgentState, SubQuestion
from dda.agent.tools.registry import AgentToolRegistry
from dda.domain.ports import ILLMClient

logger = logging.getLogger(__name__)

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "sub_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "route": {"type": "string", "enum": ["STRUCTURED_FACT", "PROSE_QUERY"]},
                },
                "required": ["text", "route"],
            },
        }
    },
    "required": ["sub_questions"],
}


def plan_node(
    state: AgentState, llm: ILLMClient, tools: AgentToolRegistry
) -> AgentState:
    """Decompose the migration task into sub-questions grounded in actual usage sites.

    Questions are grounded in usage_sites rather than generated generically —
    "how do I replace moment().format()" is useful; "how do I migrate off moment" is not.
    """
    usage_sites = tools.get_usage_sites(state["package"])
    usage_summary = _format_usage_sites(usage_sites)

    prompt = load("plan").format(
        package=state["package"],
        ecosystem=state["ecosystem"],
        usage_sites=usage_summary,
        signals_summary=state.get("signals_summary", "none"),
        schema=json.dumps(_SCHEMA, indent=2),
    )

    result = llm.generate_structured(prompt, _SCHEMA)
    raw_questions: list[dict[str, object]] = result.get("sub_questions", [])

    sub_questions: list[SubQuestion] = [
        SubQuestion(
            text=str(q["text"]),
            route=str(q.get("route", "PROSE_QUERY")),
            answered=False,
            answer="",
        )
        for q in raw_questions
    ]

    logger.info("plan_node_complete", extra={
        "package": state["package"],
        "sub_question_count": len(sub_questions),
    })

    return {
        **state,
        "usage_sites": usage_sites,
        "sub_questions": sub_questions,
        "route_history": state.get("route_history", []) + ["plan"],
    }


def _format_usage_sites(sites: list) -> str:  # type: ignore[type-arg]
    if not sites:
        return "No static usage sites found."
    lines = [f"  {s.file_path}:{s.line_number}  {s.symbol}  [{s.confidence.value}]" for s in sites]
    return "\n".join(lines[:30])  # cap at 30 lines to stay within context
