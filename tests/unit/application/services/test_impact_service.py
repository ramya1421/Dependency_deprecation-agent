from datetime import UTC, datetime
from pathlib import Path

from dda.application.services.impact_service import ImpactService
from dda.domain.entities import Signal, UsageSite
from dda.domain.value_objects import Confidence, EffortEstimate, Severity, SignalType


def _usage_site(
    file_name: str, symbol: str, confidence: Confidence = Confidence.STATIC_CONFIRMED
) -> UsageSite:
    return UsageSite(
        package="flask",
        symbol=symbol,
        file_path=Path(file_name),
        line_number=1,
        column_number=0,
        usage_kind="call",
        confidence=confidence,
        snippet="",
    )


def _signal(severity: Severity) -> Signal:
    return Signal(
        source="osv",
        signal_type=SignalType.VULNERABILITY,
        severity=severity,
        payload={},
        fetched_at=datetime.now(UTC),
    )


def test_no_usage_sites_gives_trivial_effort() -> None:
    impact = ImpactService().assess("flask", [], [])

    assert impact.total_call_sites == 0
    assert impact.distinct_files == 0
    assert impact.affected_symbols == []
    assert impact.effort is EffortEstimate.TRIVIAL


def test_counts_and_distinct_files_and_symbols() -> None:
    sites = [
        _usage_site("a.py", "flask.Flask"),
        _usage_site("a.py", "flask.jsonify"),
        _usage_site("b.py", "flask.Flask"),
    ]

    impact = ImpactService().assess("flask", sites, [])

    assert impact.total_call_sites == 3
    assert impact.distinct_files == 2
    assert impact.affected_symbols == ["flask.Flask", "flask.jsonify"]


def test_filters_to_requested_package_only() -> None:
    sites = [_usage_site("a.py", "flask.Flask")]
    other_package_site = UsageSite(
        package="numpy",
        symbol="numpy.array",
        file_path=Path("a.py"),
        line_number=1,
        column_number=0,
        usage_kind="call",
        confidence=Confidence.STATIC_CONFIRMED,
        snippet="",
    )

    impact = ImpactService().assess("flask", [*sites, other_package_site], [])

    assert impact.total_call_sites == 1


def test_confidence_tiers_are_reported_separately() -> None:
    sites = [
        _usage_site("a.py", "flask.Flask", Confidence.STATIC_CONFIRMED),
        _usage_site("a.py", "flask.jsonify", Confidence.POSSIBLE),
    ]

    impact = ImpactService().assess("flask", sites, [])

    assert impact.confirmed_call_sites == 1
    assert impact.possible_call_sites == 1
    assert impact.total_call_sites == 2


def test_effort_scales_with_call_site_count() -> None:
    service = ImpactService()

    small = service.assess("flask", [_usage_site("a.py", "flask.Flask")] * 3, [])
    medium = service.assess("flask", [_usage_site("a.py", "flask.Flask")] * 10, [])
    large = service.assess("flask", [_usage_site("a.py", "flask.Flask")] * 25, [])

    assert small.effort is EffortEstimate.SMALL
    assert medium.effort is EffortEstimate.MEDIUM
    assert large.effort is EffortEstimate.LARGE


def test_severe_signal_bumps_effort_up_one_tier() -> None:
    sites = [_usage_site("a.py", "flask.Flask")] * 3  # would be SMALL alone

    bumped = ImpactService().assess("flask", sites, [_signal(Severity.CRITICAL)])
    not_bumped = ImpactService().assess("flask", sites, [_signal(Severity.LOW)])

    assert bumped.effort is EffortEstimate.MEDIUM
    assert not_bumped.effort is EffortEstimate.SMALL


def test_severe_signal_bump_is_capped_at_large() -> None:
    sites = [_usage_site("a.py", "flask.Flask")] * 25  # already LARGE

    impact = ImpactService().assess("flask", sites, [_signal(Severity.CRITICAL)])

    assert impact.effort is EffortEstimate.LARGE
