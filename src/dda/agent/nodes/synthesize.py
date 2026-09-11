import json
import logging
import re

from dda.agent.prompts.loader import load
from dda.agent.state import AgentState
from dda.domain.ports import ILLMClient

logger = logging.getLogger(__name__)

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "effort": {
            "type": "string",
            "enum": ["trivial", "small", "medium", "large"],
        },
    },
    "required": ["summary", "steps", "effort"],
}

# Matches inline citations like [abc123ef]
_CITATION_RE = re.compile(r"\[([0-9a-f]{16})\]")


def synthesize_node(state: AgentState, llm: ILLMClient) -> AgentState:
    """Draft the migration plan with inline [chunk_id] citations.

    Temperature 0.1 — this is a factual synthesis task, not creative writing.
    The prompt explicitly instructs: if context is absent, say so rather than
    infer. The verify node will drop unsupported claims regardless.
    """
    usage_sites = state.get("usage_sites", [])
    distinct_files = len({str(s.file_path) for s in usage_sites})
    context_text = _format_chunks(state.get("retrieved_chunks", []))
    facts_text = json.dumps(state.get("structured_facts", {}), indent=2, default=str)

    prompt = load("synthesize").format(
        package=state["package"],
        ecosystem=state["ecosystem"],
        usage_sites=_format_usage(usage_sites),
        context=context_text,
        structured_facts=facts_text,
        total_call_sites=len(usage_sites),
        distinct_files=distinct_files,
        schema=json.dumps(_SCHEMA, indent=2),
    )

    result = llm.generate_structured(prompt, _SCHEMA, temperature=0.1)

    summary = str(result.get("summary", ""))
    steps: list[str] = [str(s) for s in result.get("steps", [])]
    effort = str(result.get("effort", "medium"))

    # Extract all cited chunk IDs from the combined text.
    combined = summary + " " + " ".join(steps)
    cited_ids = set(_CITATION_RE.findall(combined))
    chunk_map = {c.chunk_id: c for c in state.get("retrieved_chunks", [])}

    claims = [
        {"text": step, "chunk_id": cid}
        for step in steps
        for cid in _CITATION_RE.findall(step)
        if cid in chunk_map
    ]

    logger.info("synthesize_node", extra={
        "package": state["package"],
        "steps": len(steps),
        "cited_chunks": len(cited_ids),
    })

    return {
        **state,
        "draft_plan": summary,
        "draft_steps": steps,
        "claims": claims,
        "route_history": state.get("route_history", []) + ["synthesize"],
    }


def _format_chunks(chunks: list) -> str:  # type: ignore[type-arg]
    if not chunks:
        return "No migration context retrieved."
    parts = [f"[{c.chunk_id}] {c.header_path}\n{c.text}" for c in chunks[:10]]
    return "\n\n---\n\n".join(parts)


def _format_usage(sites: list) -> str:  # type: ignore[type-arg]
    if not sites:
        return "None found."
    lines = [f"  {s.file_path}:{s.line_number}  {s.symbol}  ({s.usage_kind})" for s in sites[:20]]
    return "\n".join(lines)
