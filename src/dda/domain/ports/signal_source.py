from abc import ABC, abstractmethod

from dda.domain.entities import Dependency, Signal


class ISignalSource(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    async def fetch(self, dependency: Dependency) -> list[Signal]: ...
