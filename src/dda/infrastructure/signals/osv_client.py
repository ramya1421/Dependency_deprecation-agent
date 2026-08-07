from datetime import UTC, datetime
from typing import Any

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.base_client import BaseHttpClient
from dda.infrastructure.signals._offline import empty_on_offline_miss

_OSV_ECOSYSTEM = {
    Ecosystem.PYTHON: "PyPI",
    Ecosystem.JAVASCRIPT: "npm",
    Ecosystem.GO: "Go",
    Ecosystem.JAVA: "Maven",
    Ecosystem.RUST: "crates.io",
    Ecosystem.CSHARP: "NuGet",
}

_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MODERATE": Severity.MEDIUM,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


def _extract_severity(vuln: dict[str, Any]) -> Severity:
    raw = vuln.get("database_specific", {}).get("severity")
    if isinstance(raw, str) and raw.upper() in _SEVERITY_MAP:
        return _SEVERITY_MAP[raw.upper()]
    # OSV doesn't guarantee a normalized severity label across every advisory
    # source (NVD-derived entries often carry only a raw CVSS vector), so we
    # default to MEDIUM rather than silently dropping the finding.
    return Severity.MEDIUM


class OsvClient(ISignalSource):
    """Queries OSV's batch endpoint (never the singular per-package endpoint),
    then resolves full details for each vuln id it returns.
    """

    def __init__(self, http_client: BaseHttpClient) -> None:
        self._http_client = http_client

    @property
    def source_name(self) -> str:
        return "osv"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        osv_ecosystem = _OSV_ECOSYSTEM.get(dependency.ecosystem)
        if osv_ecosystem is None:
            return []

        query: dict[str, Any] = {
            "package": {"name": dependency.name, "ecosystem": osv_ecosystem}
        }
        if dependency.resolved_version:
            query["version"] = dependency.resolved_version

        batch_result = await self._http_client.request(
            "POST",
            "https://api.osv.dev/v1/querybatch",
            self.source_name,
            json_body={"queries": [query]},
        )
        results = batch_result.get("results", [])
        vuln_refs = results[0].get("vulns", []) if results else []
        if not vuln_refs:
            return []

        fetched_at = datetime.now(UTC)
        signals: list[Signal] = []
        for ref in vuln_refs:
            vuln_id = ref["id"]
            vuln = await self._http_client.request(
                "GET",
                f"https://api.osv.dev/v1/vulns/{vuln_id}",
                self.source_name,
            )
            signals.append(
                Signal(
                    source=self.source_name,
                    signal_type=SignalType.VULNERABILITY,
                    severity=_extract_severity(vuln),
                    payload={
                        "id": vuln_id,
                        "summary": vuln.get("summary"),
                        "affected": vuln.get("affected", []),
                    },
                    fetched_at=fetched_at,
                )
            )
        return signals
