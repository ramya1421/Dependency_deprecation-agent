"""Unit tests for each agent node in isolation.

Every test uses FakeLLM and makes zero network calls.
"""
from datetime import UTC, datetime

import pytest

from dda.agent.nodes.finalize import finalize_node
from dda.agent.nodes.reflect import MAX_REFLECTIONS, reflect_node, should_continue_reflecting
from dda.agent.nodes.route import MAX_TOOL_CALLS, next_route, route_node
from dda.agent.nodes.synthesize import synthesize_node
from dda.agent.nodes.verify import should_retry_synthesis, verify_node
from dda.agent.state import SubQuestion
from tests.unit.agent.conftest import FakeLLM, make_chunk, make_state


# ---------------------------------------------------------------------------
# route_node
# ---------------------------------------------------------------------------

def test_route_returns_prose_query_when_unanswered_prose() -> None:
    q = SubQuestion(text="how to replace moment.format", route="PROSE_QUERY", answered=False, answer="")
    state = make_state(sub_questions=[q])
    assert next_route(state) == "PROSE_QUERY"


def test_route_returns_structured_fact_for_cve_question() -> None:
    q = SubQuestion(text="are there CVEs?", route="STRUCTURED_FACT", answered=False, answer="")
    state = make_state(sub_questions=[q])
    assert next_route(state) == "STRUCTURED_FACT"


def test_route_returns_synthesize_when_all_answered() -> None:
    q = SubQuestion(text="q", route="PROSE_QUERY", answered=True, answer="done")
    state = make_state(sub_questions=[q])
    assert next_route(state) == "synthesize"


def test_route_returns_synthesize_at_tool_cap() -> None:
    q = SubQuestion(text="q", route="PROSE_QUERY", answered=False, answer="")
    state = make_state(sub_questions=[q], tool_call_count=MAX_TOOL_CALLS)
    assert next_route(state) == "synthesize"


# ---------------------------------------------------------------------------
# reflect_node
# ---------------------------------------------------------------------------

def test_reflect_adds_reformulated_question_when_insufficient() -> None:
    q = SubQuestion(text="original", route="PROSE_QUERY", answered=False, answer="")
    chunk = make_chunk()
    llm = FakeLLM(structured_response={
        "sufficient": False,
        "missing": ["specific API examples"],
        "reformulated_query": "moment format replacement dayjs",
    })
    state = make_state(sub_questions=[q], retrieved_chunks=[chunk])

    result = reflect_node(state, llm)

    texts = [sq["text"] for sq in result["sub_questions"]]
    assert "moment format replacement dayjs" in texts


def test_reflect_does_not_add_question_when_sufficient() -> None:
    q = SubQuestion(text="original", route="PROSE_QUERY", answered=False, answer="")
    llm = FakeLLM(structured_response={"sufficient": True, "missing": []})
    state = make_state(sub_questions=[q])

    result = reflect_node(state, llm)

    assert len(result["sub_questions"]) == 1  # no new question added


def test_reflect_caps_at_max_reflections() -> None:
    q = SubQuestion(text="q", route="PROSE_QUERY", answered=False, answer="")
    llm = FakeLLM(structured_response={"sufficient": False, "missing": [], "reformulated_query": "r"})
    state = make_state(sub_questions=[q], reflection_count=MAX_REFLECTIONS)

    result = reflect_node(state, llm)

    # Cap hit: no new question injected (node returns early before calling LLM reform)
    assert "cap_reached" in result["route_history"][-1]


def test_should_continue_reflecting_routes_to_synthesize_when_all_answered() -> None:
    q = SubQuestion(text="q", route="PROSE_QUERY", answered=True, answer="done")
    state = make_state(sub_questions=[q], reflection_count=1)
    assert should_continue_reflecting(state) == "synthesize"


def test_should_continue_reflecting_routes_back_when_unanswered() -> None:
    q = SubQuestion(text="q", route="PROSE_QUERY", answered=False, answer="")
    state = make_state(sub_questions=[q], reflection_count=1)
    assert should_continue_reflecting(state) == "route"


# ---------------------------------------------------------------------------
# synthesize_node
# ---------------------------------------------------------------------------

def test_synthesize_extracts_claims_from_cited_steps() -> None:
    chunk_id = "a" * 16
    chunk = make_chunk(chunk_id=chunk_id)
    llm = FakeLLM(structured_response={
        "summary": "Replace moment with dayjs.",
        "steps": [f"Step 1: swap import [{chunk_id}]"],
        "effort": "small",
    })
    state = make_state(retrieved_chunks=[chunk])

    result = synthesize_node(state, llm)

    assert result["draft_plan"] == "Replace moment with dayjs."
    assert len(result["claims"]) == 1
    assert result["claims"][0]["chunk_id"] == chunk_id


def test_synthesize_produces_no_claims_when_no_citations() -> None:
    llm = FakeLLM(structured_response={
        "summary": "summary",
        "steps": ["Step with no citation"],
        "effort": "trivial",
    })
    state = make_state()

    result = synthesize_node(state, llm)

    assert result["claims"] == []


# ---------------------------------------------------------------------------
# verify_node
# ---------------------------------------------------------------------------

def test_verify_keeps_supported_claims() -> None:
    chunk_id = "b" * 16
    chunk = make_chunk(chunk_id=chunk_id, text="dayjs is a modern alternative to moment")
    judge = FakeLLM(structured_response={"supported": True, "entailment_score": 0.95})
    claims = [{"text": "Use dayjs instead", "chunk_id": chunk_id}]
    state = make_state(claims=claims, retrieved_chunks=[chunk])

    result = verify_node(state, judge)

    assert len(result["verified_claims"]) == 1
    assert result["verified_claims"][0]["entailment_score"] == 0.95


def test_verify_drops_unsupported_claims() -> None:
    chunk_id = "c" * 16
    chunk = make_chunk(chunk_id=chunk_id)
    judge = FakeLLM(structured_response={"supported": False, "entailment_score": 0.1})
    claims = [{"text": "Unrelated claim", "chunk_id": chunk_id}]
    state = make_state(claims=claims, retrieved_chunks=[chunk])

    result = verify_node(state, judge)

    assert result["verified_claims"] == []


def test_verify_drops_claims_with_missing_chunk() -> None:
    claims = [{"text": "claim", "chunk_id": "0" * 16}]
    judge = FakeLLM(structured_response={"supported": True, "entailment_score": 0.9})
    state = make_state(claims=claims, retrieved_chunks=[])

    result = verify_node(state, judge)

    assert result["verified_claims"] == []


def test_should_retry_synthesis_when_drop_rate_exceeds_threshold() -> None:
    claims = [{"text": f"c{i}", "chunk_id": "x"} for i in range(10)]
    # Only 2 of 10 verified → 80% drop rate → retry
    verified = [{"text": "c0", "chunk_id": "x", "verified": True, "entailment_score": 0.9}] * 2
    state = make_state(claims=claims, verified_claims=verified, route_history=["synthesize"])
    assert should_retry_synthesis(state) == "synthesize"


def test_should_not_retry_synthesis_twice() -> None:
    claims = [{"text": f"c{i}", "chunk_id": "x"} for i in range(10)]
    verified: list[dict] = []
    # Two prior synthesize entries → already retried
    state = make_state(
        claims=claims,
        verified_claims=verified,
        route_history=["synthesize", "verify:drop_rate=0.80", "synthesize"],
    )
    assert should_retry_synthesis(state) == "finalize"


# ---------------------------------------------------------------------------
# finalize_node
# ---------------------------------------------------------------------------

def test_finalize_assembles_migration_plan() -> None:
    verified = [{"text": "swap import", "chunk_id": "a" * 16, "verified": True, "entailment_score": 0.9}]
    state = make_state(
        draft_plan="Replace moment with dayjs",
        draft_steps=["swap import [aaaaaaaaaaaaaaaa]"],
        verified_claims=verified,
    )

    result = finalize_node(state)

    plan = result["migration_plan"]
    assert plan is not None
    assert plan["package"] == "moment"
    assert plan["summary"] == "Replace moment with dayjs"
    assert len(plan["claims"]) == 1
    assert "finalize" in result["route_history"]


def test_finalize_with_no_verified_claims_still_produces_plan() -> None:
    state = make_state(draft_plan="summary", draft_steps=["step"], verified_claims=[])

    result = finalize_node(state)

    assert result["migration_plan"] is not None
    assert result["migration_plan"]["claims"] == []
