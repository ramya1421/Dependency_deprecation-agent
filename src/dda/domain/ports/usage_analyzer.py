from abc import ABC, abstractmethod
from pathlib import Path

from dda.domain.entities import UsageSite
from dda.domain.value_objects import Ecosystem


class IUsageAnalyzer(ABC):
    @property
    @abstractmethod
    def ecosystem(self) -> Ecosystem: ...

    @abstractmethod
    def analyze(self, repo_root: Path, packages: list[str]) -> list[UsageSite]: ...
