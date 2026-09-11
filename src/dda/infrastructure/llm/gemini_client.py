import json
import sqlite3
from typing import Any

from google import genai
from google.genai import types

from dda.domain.ports import ILLMClient
from dda.infrastructure.llm.llm_cache import LLMCache

_MODEL = "gemini-2.0-flash"


class GeminiClient(ILLMClient):
    """Gemini 2.0 Flash with structured output via response schema and
    SQLite response caching so evaluation re-runs don't burn quota.
    """

    def __init__(self, api_key: str, connection: sqlite3.Connection) -> None:
        self._client = genai.Client(api_key=api_key)
        self._cache = LLMCache(connection)

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        cache_key = self._cache.make_key(_MODEL, system + prompt, temperature)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
        )
        response = self._client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=config,
        )
        text = response.text or ""
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

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
            response_mime_type="application/json",
            response_schema=schema,
        )
        response = self._client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=config,
        )
        text = response.text or "{}"
        result: dict[str, Any] = json.loads(text)
        self._cache.put_structured(cache_key, result)
        return result
