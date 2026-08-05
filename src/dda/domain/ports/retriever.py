from abc import ABC, abstractmethod

from dda.domain.entities import Chunk


class IRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, package: str | None, top_k: int) -> list[Chunk]: ...
