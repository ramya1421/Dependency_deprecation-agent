from datetime import datetime
from typing import Any, TypedDict

from dda.domain.entities import Chunk, UsageSite
from dda.domain.value_objects import Ecosystem


class SubQuestion(TypedDict):
    text: str
    # "STRUCTURED_FACT" routes to a deterministic tool; "PROSE_QUERY" routes to retrieval.
    route: str
    answered: bool
    answer: str


class AgentState(TypedDict):
    # Inputs
    package: str
    ecosystem: str
    repo_root: str

    # Collected during execution
    usage_sites: list[UsageSite]
    signals_summary: str
    sub_questions: list[SubQuestion]
    retrieved_chunks: list[Chunk]
    structured_facts: dict[str, Any]

    # Generation state
    draft_plan: str
    draft_steps: list[str]

    # Verification state
    claims: list[dict[str, Any]]       # [{text, chunk_id}]
    verified_claims: list[dict[str, Any]]  # [{text, chunk_id, verified, score}]

    # Control flow
    reflection_count: int
    tool_call_count: int
    route_history: list[str]
    errors: list[str]
    started_at: datetime

    # Output
    migration_plan: dict[str, Any] | None
