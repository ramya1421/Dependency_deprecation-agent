from abc import ABC, abstractmethod
from typing import Any

from dda.domain.entities import Chunk


class IVectorRepository(ABC):
    @abstractmethod
    def upsert(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    def search(
        self, vector: list[float], filters: dict[str, Any] | None, top_k: int
    ) -> list[Chunk]: ...
