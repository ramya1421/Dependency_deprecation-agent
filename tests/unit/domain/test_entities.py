from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dda.domain.entities import (
    Chunk,
    Claim,
    Dependency,
    Finding,
    MigrationPlan,
    RiskScore,
    Signal,
    UsageSite,
)
from dda.domain.value_objects import (
    Confidence,
    Ecosystem,
    EffortEstimate,
    Severity,
    SignalType,
)


def make_dependency() -> Dependency:
    return Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
        declared_spec="flask>=2.0",
        resolved_version="2.3.0",
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def test_dependency_construction() -> None:
    dep = make_dependency()
    assert dep.name == "flask"
    assert dep.ecosystem is Ecosystem.PYTHON


def test_dependency_is_frozen() -> None:
    dep = make_dependency()
    with pytest.raises(FrozenInstanceError):
        dep.name = "django"  # type: ignore[misc]


def test_signal_construction() -> None:
    signal = Signal(
        source="pypi",
        signal_type=SignalType.DEPRECATED,
        severity=Severity.HIGH,
        payload={"reason": "superseded"},
        fetched_at=datetime.now(UTC),
    )
    assert signal.signal_type is SignalType.DEPRECATED


def test_usage_site_construction() -> None:
    site = UsageSite(
        package="flask",
        symbol="Flask",
        file_path=Path("app.py"),
        line_number=10,
        column_number=4,
        usage_kind="call",
        confidence=Confidence.STATIC_CONFIRMED,
        snippet="app = Flask(__name__)",
    )
    assert site.confidence is Confidence.STATIC_CONFIRMED


def test_chunk_and_claim_construction() -> None:
    chunk = Chunk(
        chunk_id="flask-changelog-1",
        text="## 3.0.0\nRemoved deprecated `escape` import.",
        package="flask",
        doc_type="changelog",
        source_url="https://example.com/CHANGELOG.md",
        header_path="3.0.0",
        version="3.0.0",
        token_count=12,
    )
    claim = Claim(
        text="`escape` was removed in 3.0.0.",
        chunk_id=chunk.chunk_id,
        verified=True,
        entailment_score=0.92,
    )
    assert claim.chunk_id == chunk.chunk_id


def test_migration_plan_and_finding_construction() -> None:
    dep = make_dependency()
    usage_site = UsageSite(
        package="flask",
        symbol="Flask",
        file_path=Path("app.py"),
        line_number=10,
        column_number=4,
        usage_kind="call",
        confidence=Confidence.STATIC_CONFIRMED,
        snippet="app = Flask(__name__)",
    )
    claim = Claim(text="No change needed.", chunk_id="c1", verified=True, entailment_score=1.0)
    plan = MigrationPlan(
        package="flask",
        summary="Upgrade to 3.0.0",
        steps=["Bump version pin"],
        claims=[claim],
        usage_sites=[usage_site],
        effort=EffortEstimate.SMALL,
    )
    risk_score = RiskScore(
        total=30.0, components={"deprecation": 30.0}, rationale=["Deprecated on PyPI"]
    )
    finding = Finding(
        dependency=dep,
        risk_score=risk_score,
        signals=[],
        usage_sites=[usage_site],
        migration_plan=plan,
    )
    assert finding.migration_plan is not None
    assert finding.migration_plan.effort is EffortEstimate.SMALL
