import json
import sqlite3
from datetime import datetime
from typing import Any

from dda.domain.entities import Dependency, Finding, RiskScore, Signal, UsageSite
from dda.domain.ports import IScanRepository
from dda.infrastructure.persistence import mappers


class SqliteScanRepository(IScanRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        self._connection = connection

    def save_scan(self, scan_id: str, repo_path: str, status: str, started_at: datetime) -> None:
        self._connection.execute(
            "INSERT INTO scans (id, repo_path, status, started_at) VALUES (?, ?, ?, ?)",
            (scan_id, repo_path, status, started_at.isoformat()),
        )
        self._connection.commit()

    def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id, repo_path, status, started_at FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def save_dependencies(self, scan_id: str, dependencies: list[Dependency]) -> None:
        self._connection.executemany(
            """INSERT INTO dependencies
               (scan_id, name, ecosystem, declared_spec, resolved_version,
                is_direct, is_dev, manifest_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [mappers.dependency_to_row(scan_id, dep) for dep in dependencies],
        )
        self._connection.commit()

    def get_dependencies(self, scan_id: str) -> list[Dependency]:
        rows = self._connection.execute(
            "SELECT * FROM dependencies WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        return [mappers.row_to_dependency(row) for row in rows]

    def save_signals(self, dependency_name: str, signals: list[Signal]) -> None:
        self._connection.executemany(
            """INSERT INTO signals
               (dependency_name, source, signal_type, severity, payload, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [mappers.signal_to_row(dependency_name, signal) for signal in signals],
        )
        self._connection.commit()

    def _get_signals(self, dependency_name: str) -> list[Signal]:
        rows = self._connection.execute(
            "SELECT * FROM signals WHERE dependency_name = ?", (dependency_name,)
        ).fetchall()
        return [mappers.row_to_signal(row) for row in rows]

    def save_usage_sites(self, scan_id: str, usage_sites: list[UsageSite]) -> None:
        self._connection.executemany(
            """INSERT INTO usage_sites
               (scan_id, package, symbol, file_path, line_number, column_number,
                usage_kind, confidence, snippet)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [mappers.usage_site_to_row(scan_id, site) for site in usage_sites],
        )
        self._connection.commit()

    def _get_usage_sites(self, scan_id: str, package: str) -> list[UsageSite]:
        rows = self._connection.execute(
            "SELECT * FROM usage_sites WHERE scan_id = ? AND package = ?", (scan_id, package)
        ).fetchall()
        return [mappers.row_to_usage_site(row) for row in rows]

    def save_findings(self, scan_id: str, findings: list[Finding]) -> None:
        for finding in findings:
            plan_json = (
                json.dumps(mappers.migration_plan_to_dict(finding.migration_plan))
                if finding.migration_plan is not None
                else None
            )
            cursor = self._connection.execute(
                """INSERT INTO findings
                   (scan_id, dependency_name, risk_total, risk_components,
                    risk_rationale, migration_plan)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scan_id,
                    finding.dependency.name,
                    finding.risk_score.total,
                    json.dumps(finding.risk_score.components),
                    json.dumps(finding.risk_score.rationale),
                    plan_json,
                ),
            )
            if finding.migration_plan is not None:
                finding_id = cursor.lastrowid
                self._connection.executemany(
                    """INSERT INTO citations
                       (finding_id, chunk_id, claim_text, verified, entailment_score)
                       VALUES (?, ?, ?, ?, ?)""",
                    [
                        (finding_id, c.chunk_id, c.text, int(c.verified), c.entailment_score)
                        for c in finding.migration_plan.claims
                    ],
                )
        self._connection.commit()

    def get_findings(self, scan_id: str) -> list[Finding]:
        rows = self._connection.execute(
            "SELECT * FROM findings WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        findings: list[Finding] = []
        for row in rows:
            dep_row = self._connection.execute(
                "SELECT * FROM dependencies WHERE scan_id = ? AND name = ?",
                (scan_id, row["dependency_name"]),
            ).fetchone()
            if dep_row is None:
                continue
            dependency = mappers.row_to_dependency(dep_row)
            risk_score = RiskScore(
                total=row["risk_total"],
                components=json.loads(row["risk_components"]),
                rationale=json.loads(row["risk_rationale"]),
            )
            migration_plan = (
                mappers.migration_plan_from_dict(json.loads(row["migration_plan"]))
                if row["migration_plan"] is not None
                else None
            )
            findings.append(
                Finding(
                    dependency=dependency,
                    risk_score=risk_score,
                    signals=self._get_signals(row["dependency_name"]),
                    usage_sites=self._get_usage_sites(scan_id, row["dependency_name"]),
                    migration_plan=migration_plan,
                )
            )
        return findings
