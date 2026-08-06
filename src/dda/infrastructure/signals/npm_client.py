from datetime import UTC, datetime
from typing import Any

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient


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

    async def fetch(self, dependency: Dependency) -> list[Signal]:
        data = await self._http_client.request(
            "GET",
            _registry_url(dependency.name),
            self.source_name,
        )
        versions: dict[str, Any] = data.get("versions", {})
        target_version = dependency.resolved_version or data.get("dist-tags", {}).get("latest")
        version_data: dict[str, Any] = versions.get(target_version, {}) if target_version else {}

        deprecated_message = version_data.get("deprecated")
        if not deprecated_message:
            return []

        last_modified = data.get("time", {}).get("modified")
        return [
            Signal(
                source=self.source_name,
                signal_type=SignalType.DEPRECATED,
                severity=Severity.HIGH,
                payload={
                    "message": deprecated_message,
                    "version": target_version,
                    "last_modified": last_modified,
                },
                fetched_at=datetime.now(UTC),
            )
        ]
