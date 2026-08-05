from abc import ABC, abstractmethod
from pathlib import Path

from dda.domain.entities import Dependency
from dda.domain.value_objects import Ecosystem


class IManifestParser(ABC):
    @property
    @abstractmethod
    def ecosystem(self) -> Ecosystem: ...

    @abstractmethod
    def detect(self, repo_root: Path) -> list[Path]: ...

    @abstractmethod
    def parse(self, manifest: Path) -> list[Dependency]: ...
