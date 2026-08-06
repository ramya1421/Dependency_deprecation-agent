from datetime import UTC, datetime
from typing import Any

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient

_INACTIVE_CLASSIFIER = "Development Status :: 7 - Inactive"


class PyPIClient(ISignalSource):
    """PyPI has no explicit deprecation field (unlike npm's `deprecated`), so
    deprecation is inferred from yanked releases and the "Inactive" classifier.
    """

    def __init__(self, http_client: BaseHttpClient) -> None:
        self._http_client = http_client

    @property
    def source_name(self) -> str:
        return "pypi"

    async def fetch(self, dependency: Dependency) -> list[Signal]:
        data = await self._http_client.request(
            "GET",
            f"https://pypi.org/pypi/{dependency.name}/json",
            self.source_name,
        )
        info: dict[str, Any] = data.get("info", {})
        releases: dict[str, list[dict[str, Any]]] = data.get("releases", {})
        target_version = dependency.resolved_version or info.get("version")
        files = releases.get(target_version, []) if target_version else []

        last_upload_date = self._latest_upload_date(files) or self._latest_upload_date(
            data.get("urls", [])
        )
        fetched_at = datetime.now(UTC)
        signals: list[Signal] = []

        yanked_reason = next(
            (str(f.get("yanked_reason") or "yanked") for f in files if f.get("yanked")), None
        )
        if yanked_reason is not None:
            signals.append(
                Signal(
                    source=self.source_name,
                    signal_type=SignalType.DEPRECATED,
                    severity=Severity.MEDIUM,
                    payload={
                        "reason": "yanked",
                        "yanked_reason": yanked_reason,
                        "version": target_version,
                        "last_upload_date": last_upload_date,
                    },
                    fetched_at=fetched_at,
                )
            )

        if _INACTIVE_CLASSIFIER in info.get("classifiers", []):
            signals.append(
                Signal(
                    source=self.source_name,
                    signal_type=SignalType.ABANDONED,
                    severity=Severity.MEDIUM,
                    payload={
                        "reason": "inactive_classifier",
                        "last_upload_date": last_upload_date,
                    },
                    fetched_at=fetched_at,
                )
            )

        return signals

    @staticmethod
    def _latest_upload_date(files: list[dict[str, Any]]) -> str | None:
        dates = [f["upload_time_iso_8601"] for f in files if f.get("upload_time_iso_8601")]
        return max(dates) if dates else None
