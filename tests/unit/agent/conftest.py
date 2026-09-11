from datetime import UTC, datetime
from typing import Any

from dda.agent.state import AgentState, SubQuestion
from dda.domain.entities import Chunk
from dda.domain.ports import ILLMClient


class FakeLLM(ILLMClient):
    """Deterministic fake LLM for node tests — returns preset responses."""

    def __init__(
        self,
        text_response: str = "",
        structured_response: dict[str, Any] | None = None,
    ) -> None:
        self._text = text_response
        self._structured = structured_response or {}

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        return self._text

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], system: str = "", temperature: float = 0.2
    ) -> dict[str, Any]:
        return self._structured


def make_state(**overrides: Any) -> AgentState:
    base: AgentState = {
        "package": "moment",
        "ecosystem": "javascript",
        "repo_root": "/repo",
        "usage_sites": [],
        "signals_summary": "deprecated",
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
    return {**base, **overrides}  # type: ignore[return-value]


def make_chunk(chunk_id: str = "a" * 16, text: str = "Migration guide text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        package="moment",
        doc_type="changelog",
        source_url="https://example.com",
        header_path="4.0.0 > Breaking Changes",
        version="4.0.0",
        token_count=10,
    )
