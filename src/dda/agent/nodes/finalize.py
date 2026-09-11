import logging
from pathlib import Path

from dda.agent.state import AgentState
from dda.domain.entities import Claim, MigrationPlan, UsageSite
from dda.domain.value_objects import EffortEstimate

logger = logging.getLogger(__name__)

_EFFORT_MAP = {
    "trivial": EffortEstimate.TRIVIAL,
    "small": EffortEstimate.SMALL,
    "medium": EffortEstimate.MEDIUM,
    "large": EffortEstimate.LARGE,
}


def finalize_node(state: AgentState) -> AgentState:
    """Assemble the final MigrationPlan entity from verified state.

    Uses only verified_claims — every claim in the output has been confirmed
    against its cited source chunk by an independent model.
    """
    verified = state.get("verified_claims", [])
    usage_sites: list[UsageSite] = state.get("usage_sites", [])

    # Infer effort from usage site count if synthesize didn't produce one.
    raw_effort = _infer_effort(len(usage_sites))
    # Prefer the synthesized effort estimate if present in draft steps.
    synthesized_effort = _extract_effort_from_steps(state.get("draft_steps", []))
    effort = synthesized_effort or raw_effort

    claims = [
        Claim(
            text=str(c["text"]),
            chunk_id=str(c["chunk_id"]),
            verified=True,
            entailment_score=float(c.get("entailment_score") or 0.0),
        )
        for c in verified
    ]

    plan = MigrationPlan(
        package=state["package"],
        summary=state.get("draft_plan", ""),
        steps=state.get("draft_steps", []),
        claims=claims,
        usage_sites=usage_sites,
        effort=effort,
    )

    logger.info("finalize_node", extra={
        "package": state["package"],
        "steps": len(plan.steps),
        "claims": len(plan.claims),
        "effort": effort.value,
    })

    return {
        **state,
        "migration_plan": {
            "package": plan.package,
            "summary": plan.summary,
            "steps": plan.steps,
            "effort": plan.effort.value,
            "claims": [
                {
                    "text": c.text,
                    "chunk_id": c.chunk_id,
                    "verified": c.verified,
                    "entailment_score": c.entailment_score,
                }
                for c in plan.claims
            ],
            "usage_site_count": len(plan.usage_sites),
        },
        "route_history": state.get("route_history", []) + ["finalize"],
    }


def _infer_effort(call_site_count: int) -> EffortEstimate:
    if call_site_count == 0:
        return EffortEstimate.TRIVIAL
    if call_site_count <= 5:
        return EffortEstimate.SMALL
    if call_site_count <= 20:
        return EffortEstimate.MEDIUM
    return EffortEstimate.LARGE


def _extract_effort_from_steps(steps: list[str]) -> EffortEstimate | None:
    combined = " ".join(steps).lower()
    for key, val in _EFFORT_MAP.items():
        if key in combined:
            return val
    return None
