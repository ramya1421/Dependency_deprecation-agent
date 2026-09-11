"""Pydantic request/response schemas for every API route.

Kept in one file — the surface area is small enough that splitting per-route
would be premature. Extract if this grows past ~150 lines.
"""
from typing import Any

from pydantic import BaseModel, Field


# ── Scans ──────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    repo_path: str = Field(..., description="Local path or git URL to scan")
    offline: bool = Field(False, description="Serve signals from SQLite cache only")


class ScanCreatedResponse(BaseModel):
    scan_id: str
    status: str = "queued"


class ScanStatusResponse(BaseModel):
    scan_id: str
    repo_path: str
    status: str
    started_at: str


# ── Dependencies ────────────────────────────────────────────────────────────

class DependencyResponse(BaseModel):
    name: str
    ecosystem: str
    declared_spec: str
    resolved_version: str | None
    is_direct: bool
    is_dev: bool
    manifest_path: str


# ── Findings ────────────────────────────────────────────────────────────────

class RiskScoreResponse(BaseModel):
    total: float
    components: dict[str, float]
    rationale: list[str]


class FindingResponse(BaseModel):
    dependency_name: str
    ecosystem: str
    risk_score: RiskScoreResponse
    signal_count: int
    usage_site_count: int
    has_migration_plan: bool


# ── Migration plan ──────────────────────────────────────────────────────────

class ClaimResponse(BaseModel):
    text: str
    chunk_id: str
    verified: bool
    entailment_score: float | None


class MigrationPlanResponse(BaseModel):
    package: str
    summary: str
    steps: list[str]
    effort: str
    claims: list[ClaimResponse]
    usage_site_count: int


# ── KB search ───────────────────────────────────────────────────────────────

class KbSearchRequest(BaseModel):
    query: str
    package: str | None = None
    top_k: int = Field(5, ge=1, le=20)


class KbSearchHit(BaseModel):
    chunk_id: str
    package: str
    doc_type: str
    source_url: str
    header_path: str
    version: str | None
    text_preview: str  # first 300 chars


class KbSearchResponse(BaseModel):
    hits: list[KbSearchHit]


# ── Report ──────────────────────────────────────────────────────────────────

class ReportFinding(BaseModel):
    package: str
    ecosystem: str
    risk_total: float
    rationale: list[str]
    effort: str | None


class ScanReportResponse(BaseModel):
    scan_id: str
    repo_path: str
    status: str
    dependency_count: int
    findings: list[ReportFinding]


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    qdrant: str
    llm: str
    details: dict[str, Any] = {}
