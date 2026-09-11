from typing import Any
from unittest.mock import MagicMock

import pytest

from dda.domain.ports import ILLMClient
from dda.infrastructure.llm.fallback_client import FallbackLLMClient


class _StubLLM(ILLMClient):
    def __init__(self, response: str = "ok", raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.call_count = 0

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return self._response

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], system: str = "", temperature: float = 0.2
    ) -> dict[str, Any]:
        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return {}


def test_primary_success_returns_primary_response() -> None:
    primary = _StubLLM("from-primary")
    fallback = _StubLLM("from-fallback")
    client = FallbackLLMClient(primary, fallback)

    result = client.generate("hello")

    assert result == "from-primary"
    assert fallback.call_count == 0


def test_primary_429_switches_to_fallback() -> None:
    primary = _StubLLM(raises=RuntimeError("429 Too Many Requests"))
    fallback = _StubLLM("from-fallback")
    client = FallbackLLMClient(primary, fallback)

    result = client.generate("hello")

    assert result == "from-fallback"
    assert fallback.call_count == 1


def test_primary_rate_limit_message_switches_to_fallback() -> None:
    primary = _StubLLM(raises=RuntimeError("rate limit exceeded"))
    fallback = _StubLLM("fb")
    client = FallbackLLMClient(primary, fallback)

    assert client.generate("x") == "fb"


def test_primary_500_switches_to_fallback() -> None:
    primary = _StubLLM(raises=RuntimeError("500 Internal Server Error"))
    fallback = _StubLLM("fb")
    client = FallbackLLMClient(primary, fallback)

    assert client.generate("x") == "fb"


def test_primary_404_does_not_switch_to_fallback() -> None:
    # 4xx client errors (bad prompt, content policy) won't succeed on fallback.
    primary = _StubLLM(raises=RuntimeError("404 not found"))
    fallback = _StubLLM("should-not-be-called")
    client = FallbackLLMClient(primary, fallback)

    with pytest.raises(RuntimeError, match="404"):
        client.generate("x")

    assert fallback.call_count == 0


def test_generate_structured_falls_back_on_rate_limit() -> None:
    primary = _StubLLM(raises=RuntimeError("429"))
    fallback = _StubLLM()
    client = FallbackLLMClient(primary, fallback)

    result = client.generate_structured("prompt", {})

    assert result == {}
    assert fallback.call_count == 1
