from abc import ABC, abstractmethod
from pathlib import Path


class IRepoFetcher(ABC):
    @abstractmethod
    def fetch(self, repo_path_or_url: str) -> Path: ...
