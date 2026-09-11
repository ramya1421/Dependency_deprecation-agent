import json
import sqlite3
from typing import Any

from groq import Groq

from dda.domain.ports import ILLMClient
from dda.infrastructure.llm.llm_cache import LLMCache

_MODEL = "llama-3.3-70b-versatile"


class GroqClient(ILLMClient):
    """Groq Llama 3.3 70B — used as the fallback provider and as the
    independent judge in citation verification (Groq judging Gemini avoids
    the generator confirming its own output).
    """

    def __init__(self, api_key: str, connection: sqlite3.Connection) -> None:
        self._client = Groq(api_key=api_key)
        self._cache = LLMCache(connection)

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        cache_key = self._cache.make_key(_MODEL, system + prompt, temperature)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
        )
        text = response.choices[0].message.content or ""
        self._cache.put(cache_key, text)
        return text

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        system: str = "",
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        cache_key = self._cache.make_key(
            _MODEL + ":structured", system + prompt + json.dumps(schema, sort_keys=True), temperature
        )
        cached = self._cache.get_structured(cache_key)
        if cached is not None:
            return cached

        # Groq doesn't support response_format=json_schema on all models, so we
        # instruct JSON output via the system prompt and parse the response.
        schema_str = json.dumps(schema, indent=2)
        json_system = (system + "\n" if system else "") + (
            f"Respond ONLY with valid JSON matching this schema:\n{schema_str}"
        )
        messages = [
            {"role": "system", "content": json_system},
            {"role": "user", "content": prompt},
        ]
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        result: dict[str, Any] = json.loads(text)
        self._cache.put_structured(cache_key, result)
        return result
