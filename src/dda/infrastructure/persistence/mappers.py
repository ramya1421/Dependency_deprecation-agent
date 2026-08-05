import json
import sqlite3
from pathlib import Path
from typing import Any

from dda.domain.entities import Claim, Dependency, MigrationPlan, Signal, UsageSite
from dda.domain.value_objects import Confidence, Ecosystem, EffortEstimate, Severity, SignalType


def dependency_to_row(scan_id: str, dep: Dependency) -> tuple[object, ...]:
    return (
        scan_id,
        dep.name,
        dep.ecosystem.value,
        dep.declared_spec,
        dep.resolved_version,
        int(dep.is_direct),
        int(dep.is_dev),
        str(dep.manifest_path),
    )


def row_to_dependency(row: sqlite3.Row) -> Dependency:
    return Dependency(
        name=row["name"],
        ecosystem=Ecosystem(row["ecosystem"]),
        declared_spec=row["declared_spec"],
        resolved_version=row["resolved_version"],
        is_direct=bool(row["is_direct"]),
        is_dev=bool(row["is_dev"]),
        manifest_path=Path(row["manifest_path"]),
    )


def signal_to_row(dependency_name: str, signal: Signal) -> tuple[object, ...]:
    return (
        dependency_name,
        signal.source,
        signal.signal_type.value,
        signal.severity.value,
        json.dumps(signal.payload),
        signal.fetched_at.isoformat(),
    )


def row_to_signal(row: sqlite3.Row) -> Signal:
    from datetime import datetime

    return Signal(
        source=row["source"],
        signal_type=SignalType(row["signal_type"]),
        severity=Severity(row["severity"]),
        payload=json.loads(row["payload"]),
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
    )


def usage_site_to_row(scan_id: str, site: UsageSite) -> tuple[object, ...]:
    return (
        scan_id,
        site.package,
        site.symbol,
        str(site.file_path),
        site.line_number,
        site.column_number,
        site.usage_kind,
        site.confidence.value,
        site.snippet,
    )


def row_to_usage_site(row: sqlite3.Row) -> UsageSite:
    return UsageSite(
        package=row["package"],
        symbol=row["symbol"],
        file_path=Path(row["file_path"]),
        line_number=row["line_number"],
        column_number=row["column_number"],
        usage_kind=row["usage_kind"],
        confidence=Confidence(row["confidence"]),
        snippet=row["snippet"],
    )


def migration_plan_to_dict(plan: MigrationPlan) -> dict[str, Any]:
    return {
        "package": plan.package,
        "summary": plan.summary,
        "steps": plan.steps,
        "effort": plan.effort.value,
        "claims": [
            {
                "text": c.text,
                "chunk_id": c.chunk_id,
                "verified": c.verified,
                "entailment_score": c.entailment_score,
            }
            for c in plan.claims
        ],
        "usage_sites": [
            {
                "package": u.package,
                "symbol": u.symbol,
                "file_path": str(u.file_path),
                "line_number": u.line_number,
                "column_number": u.column_number,
                "usage_kind": u.usage_kind,
                "confidence": u.confidence.value,
                "snippet": u.snippet,
            }
            for u in plan.usage_sites
        ],
    }


def migration_plan_from_dict(data: dict[str, Any]) -> MigrationPlan:
    claims_data: list[dict[str, Any]] = data["claims"]
    usage_sites_data: list[dict[str, Any]] = data["usage_sites"]
    return MigrationPlan(
        package=str(data["package"]),
        summary=str(data["summary"]),
        steps=list(data["steps"]),
        claims=[
            Claim(
                text=c["text"],
                chunk_id=c["chunk_id"],
                verified=c["verified"],
                entailment_score=c["entailment_score"],
            )
            for c in claims_data
        ],
        usage_sites=[
            UsageSite(
                package=u["package"],
                symbol=u["symbol"],
                file_path=Path(u["file_path"]),
                line_number=u["line_number"],
                column_number=u["column_number"],
                usage_kind=u["usage_kind"],
                confidence=Confidence(u["confidence"]),
                snippet=u["snippet"],
            )
            for u in usage_sites_data
        ],
        effort=EffortEstimate(data["effort"]),
    )
