from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from dda.domain.entities import Dependency, Finding, Signal, UsageSite


class IScanRepository(ABC):
    # No Scan entity exists yet (none was specified for this layer), so scan
    # metadata is passed/returned as primitives until a use case needs a richer type.
    @abstractmethod
    def save_scan(
        self, scan_id: str, repo_path: str, status: str, started_at: datetime
    ) -> None: ...

    @abstractmethod
    def get_scan(self, scan_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_dependencies(self, scan_id: str, dependencies: list[Dependency]) -> None: ...

    @abstractmethod
    def get_dependencies(self, scan_id: str) -> list[Dependency]: ...

    @abstractmethod
    def save_signals(self, dependency_name: str, signals: list[Signal]) -> None: ...

    @abstractmethod
    def save_usage_sites(self, scan_id: str, usage_sites: list[UsageSite]) -> None: ...

    @abstractmethod
    def save_findings(self, scan_id: str, findings: list[Finding]) -> None: ...

    @abstractmethod
    def get_findings(self, scan_id: str) -> list[Finding]: ...
