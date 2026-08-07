from datetime import UTC, datetime
from typing import Any

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals._offline import empty_on_offline_miss
from dda.infrastructure.signals._versions import (
    major_versions_behind,
    severity_for_major_versions_behind,
)


def _registry_url(name: str) -> str:
    # Scoped package names (@scope/pkg) need the slash percent-encoded.
    encoded = name.replace("/", "%2f") if name.startswith("@") else name
    return f"https://registry.npmjs.org/{encoded}"


class NpmClient(ISignalSource):
    """Unlike PyPI, npm exposes an explicit `deprecated` field per version."""

    def __init__(self, http_client: BaseHttpClient) -> None:
        self._http_client = http_client

    @property
    def source_name(self) -> str:
        return "npm"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        if dependency.ecosystem is not Ecosystem.JAVASCRIPT:
            return []
        data = await self._http_client.request(
            "GET",
            _registry_url(dependency.name),
            self.source_name,
        )
        versions: dict[str, Any] = data.get("versions", {})
        latest_version = data.get("dist-tags", {}).get("latest")
        target_version = dependency.resolved_version or latest_version
        version_data: dict[str, Any] = versions.get(target_version, {}) if target_version else {}
        fetched_at = datetime.now(UTC)
        signals: list[Signal] = []

        deprecated_message = version_data.get("deprecated")
        if deprecated_message:
            last_modified = data.get("time", {}).get("modified")
            signals.append(
                Signal(
                    source=self.source_name,
                    signal_type=SignalType.DEPRECATED,
                    severity=Severity.HIGH,
                    payload={
                        "message": deprecated_message,
                        "version": target_version,
                        "last_modified": last_modified,
                    },
                    fetched_at=fetched_at,
                )
            )

        behind = major_versions_behind(dependency.resolved_version, latest_version)
        if behind is not None:
            signals.append(
                Signal(
                    source=self.source_name,
                    signal_type=SignalType.OUTDATED,
                    severity=severity_for_major_versions_behind(behind),
                    payload={
                        "resolved_version": dependency.resolved_version,
                        "latest_version": latest_version,
                        "major_versions_behind": behind,
                    },
                    fetched_at=fetched_at,
                )
            )

        return signals
