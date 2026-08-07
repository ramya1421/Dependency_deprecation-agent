from datetime import UTC, datetime
from typing import Any

import httpx

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals._offline import empty_on_offline_miss

_NEAR_TERM_DAYS = 365


class EolClient(ISignalSource):
    """endoflife.date only tracks major platforms/frameworks, not arbitrary
    packages, so most dependency names 404 — that's an expected miss, not a
    failure, and is handled here rather than left to propagate.
    """

    def __init__(self, http_client: BaseHttpClient) -> None:
        self._http_client = http_client

    @property
    def source_name(self) -> str:
        return "eol"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        try:
            data = await self._http_client.request(
                "GET",
                f"https://endoflife.date/api/{dependency.name.lower()}.json",
                self.source_name,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise

        cycle = self._matching_cycle(data, dependency.resolved_version)
        if cycle is None:
            return []

        eol_value = cycle.get("eol")
        severity = self._severity_for(eol_value)
        if severity is None:
            return []

        return [
            Signal(
                source=self.source_name,
                signal_type=SignalType.EOL,
                severity=severity,
                payload={"cycle": cycle.get("cycle"), "eol": eol_value},
                fetched_at=datetime.now(UTC),
            )
        ]

    @staticmethod
    def _matching_cycle(data: Any, resolved_version: str | None) -> dict[str, Any] | None:
        if not isinstance(data, list):
            return None
        if resolved_version is None:
            return data[0] if data else None
        for entry in data:
            cycle = str(entry.get("cycle", ""))
            if resolved_version == cycle or resolved_version.startswith(f"{cycle}."):
                return dict(entry)
        return None

    @staticmethod
    def _severity_for(eol_value: Any) -> Severity | None:
        if not isinstance(eol_value, str):
            return None  # `false` (still supported) or missing: nothing to signal
        eol_date = datetime.fromisoformat(eol_value).replace(tzinfo=UTC)
        days_remaining = (eol_date - datetime.now(UTC)).days
        if days_remaining < 0:
            return Severity.CRITICAL
        if days_remaining <= 180:
            return Severity.HIGH
        if days_remaining <= _NEAR_TERM_DAYS:
            return Severity.MEDIUM
        return None
