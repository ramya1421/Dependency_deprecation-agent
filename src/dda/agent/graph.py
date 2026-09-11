"""LangGraph state-machine for migration plan generation.

Graph shape:
  plan → route → retrieve → reflect → route  (loop while unanswered questions)
                                    ↓ (sufficient OR cap)
                          synthesize → verify → finalize
                               ↑           ↓ (>30% dropped, one retry)
                               └───────────┘
"""
import sqlite3
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from dda.agent.nodes.finalize import finalize_node
from dda.agent.nodes.plan import plan_node
from dda.agent.nodes.reflect import reflect_node, should_continue_reflecting
from dda.agent.nodes.retrieve import retrieve_node
from dda.agent.nodes.route import next_route, route_node
from dda.agent.nodes.synthesize import synthesize_node
from dda.agent.nodes.verify import should_retry_synthesis, verify_node
from dda.agent.state import AgentState
from dda.agent.tools.registry import AgentToolRegistry
from dda.domain.ports import ILLMClient


def build_graph(
    llm: ILLMClient,
    judge_llm: ILLMClient,
    tools: AgentToolRegistry,
    connection: sqlite3.Connection,
) -> StateGraph:
    """Assemble the LangGraph graph with all nodes and conditional edges.

    `llm` is the generator (Gemini 2.0 Flash).
    `judge_llm` is the verifier (Groq Llama 3.3) — a different model so
    verify is genuinely independent, not the generator confirming itself.
    """
    graph = StateGraph(AgentState)

    # Bind collaborators into each node via partial so node signatures stay
    # clean (state-in, state-out) without global state.
    graph.add_node("plan", partial(plan_node, llm=llm, tools=tools))
    graph.add_node("route", route_node)
    graph.add_node("retrieve", partial(retrieve_node, tools=tools))
    graph.add_node("reflect", partial(reflect_node, llm=llm))
    graph.add_node("synthesize", partial(synthesize_node, llm=llm))
    graph.add_node("verify", partial(verify_node, judge_llm=judge_llm))
    graph.add_node("finalize", finalize_node)

    # Linear start
    graph.set_entry_point("plan")
    graph.add_edge("plan", "route")

    # Route → retrieve (STRUCTURED_FACT or PROSE_QUERY) or synthesize (DONE)
    graph.add_conditional_edges(
        "route",
        next_route,
        {
            "STRUCTURED_FACT": "retrieve",
            "PROSE_QUERY": "retrieve",
            "synthesize": "synthesize",
        },
    )

    # After retrieval, reflect on sufficiency
    graph.add_edge("retrieve", "reflect")

    # Reflect → route again (more questions) or synthesize (sufficient/cap)
    graph.add_conditional_edges(
        "reflect",
        should_continue_reflecting,
        {
            "route": "route",
            "synthesize": "synthesize",
        },
    )

    # Synthesize → verify
    graph.add_edge("synthesize", "verify")

    # Verify → finalize OR back to synthesize (one retry if >30% dropped)
    graph.add_conditional_edges(
        "verify",
        should_retry_synthesis,
        {
            "synthesize": "synthesize",
            "finalize": "finalize",
        },
    )

    graph.add_edge("finalize", END)
    return graph


async def run_migration_agent(
    package: str,
    ecosystem: str,
    repo_root: str,
    signals_summary: str,
    llm: ILLMClient,
    judge_llm: ILLMClient,
    tools: AgentToolRegistry,
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Run the full migration agent for one package and return the final state."""
    graph = build_graph(llm, judge_llm, tools, connection)
    compiled = graph.compile()

    initial: AgentState = {
        "package": package,
        "ecosystem": ecosystem,
        "repo_root": repo_root,
        "usage_sites": [],
        "signals_summary": signals_summary,
        "sub_questions": [],
        "retrieved_chunks": [],
        "structured_facts": {},
        "draft_plan": "",
        "draft_steps": [],
        "claims": [],
        "verified_claims": [],
        "reflection_count": 0,
        "tool_call_count": 0,
        "route_history": [],
        "errors": [],
        "started_at": datetime.now(UTC),
        "migration_plan": None,
    }

    final_state: dict[str, Any] = await compiled.ainvoke(initial)
    return final_state
