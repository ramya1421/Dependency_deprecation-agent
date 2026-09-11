import logging
from typing import Any

from dda.domain.ports import ILLMClient

logger = logging.getLogger(__name__)

# HTTP status codes that warrant a provider switch. 4xx client errors (bad
# prompt, content policy) are NOT retried — they'll fail on the fallback too.
_FALLBACK_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_rate_limit_or_server_error(exc: Exception) -> bool:
    """Check whether an exception from any provider SDK warrants fallback.

    Both google-genai and groq surface status codes differently, so we check
    the message string as a last resort rather than importing SDK-specific
    exception types here (which would create infrastructure cross-imports).
    """
    msg = str(exc).lower()
    for code in _FALLBACK_STATUS_CODES:
        if str(code) in msg:
            return True
    return "rate limit" in msg or "quota" in msg or "overloaded" in msg


class FallbackLLMClient(ILLMClient):
    """Wraps a primary and fallback ILLMClient, switching on 429 or 5xx.

    The application layer never knows which provider answered — this is a
    compact demonstration of the Dependency Inversion Principle: callers
    depend on ILLMClient, not on Gemini or Groq.
    """

    def __init__(self, primary: ILLMClient, fallback: ILLMClient) -> None:
        self._primary = primary
        self._fallback = fallback

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        try:
            return self._primary.generate(prompt, system, temperature)
        except Exception as exc:
            if not _is_rate_limit_or_server_error(exc):
                raise
            logger.warning("llm_primary_failed_falling_back", extra={"error": str(exc)})
            return self._fallback.generate(prompt, system, temperature)

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        system: str = "",
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        try:
            return self._primary.generate_structured(prompt, schema, system, temperature)
        except Exception as exc:
            if not _is_rate_limit_or_server_error(exc):
                raise
            logger.warning(
                "llm_primary_structured_failed_falling_back", extra={"error": str(exc)}
            )
            return self._fallback.generate_structured(prompt, schema, system, temperature)
