from abc import ABC, abstractmethod
from typing import Any


class ILLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str, temperature: float) -> str: ...

    @abstractmethod
    def generate_structured(
        self, prompt: str, schema: dict[str, Any], system: str, temperature: float
    ) -> dict[str, Any]: ...
