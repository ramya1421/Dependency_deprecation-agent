from fastapi import APIRouter

from dda.api.dependencies import get_settings
from dda.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Checks Qdrant and LLM reachability. Returns degraded status rather
    than 5xx so load balancers can distinguish config errors from crashes.
    """
    settings = get_settings()
    qdrant_status = _check_qdrant(settings.qdrant_url)
    llm_status = _check_llm(settings.gemini_api_key, settings.groq_api_key)
    overall = "ok" if qdrant_status == "ok" and llm_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        qdrant=qdrant_status,
        llm=llm_status,
    )


def _check_qdrant(url: str | None) -> str:
    if not url:
        return "not_configured"
    try:
        from qdrant_client import QdrantClient
        QdrantClient(url=url).get_collections()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_llm(gemini_key: str | None, groq_key: str | None) -> str:
    if gemini_key or groq_key:
        return "ok"
    return "not_configured"
