from datetime import UTC, datetime
from pathlib import Path

from dda.application.services.risk_scoring_service import RiskScoringService
from dda.domain.entities import Dependency, Signal
from dda.domain.value_objects import Ecosystem, Severity, SignalType


def _dependency(name: str = "flask") -> Dependency:
    return Dependency(
        name=name,
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version="1.0.0",
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


def _signal(
    signal_type: SignalType, severity: Severity, source: str = "pypi", **payload: object
) -> Signal:
    return Signal(
        source=source,
        signal_type=signal_type,
        severity=severity,
        payload=payload,
        fetched_at=datetime.now(UTC),
    )


def test_no_signals_gives_zero_score_with_rationale() -> None:
    score = RiskScoringService().score(_dependency(), [])

    assert score.total == 0.0
    assert score.components == {}
    assert score.rationale


def test_deprecation_signal_applies_configured_weight() -> None:
    score = RiskScoringService().score(
        _dependency(), [_signal(SignalType.DEPRECATED, Severity.MEDIUM)]
    )

    assert score.components["deprecation"] == 30.0
    assert score.total == 30.0
    assert any("deprecated" in line for line in score.rationale)


def test_low_severity_vulnerability_does_not_score() -> None:
    score = RiskScoringService().score(
        _dependency(), [_signal(SignalType.VULNERABILITY, Severity.LOW, id="CVE-low")]
    )

    assert "vulnerability" not in score.components
    assert score.total == 0.0


def test_high_severity_vulnerability_scores() -> None:
    score = RiskScoringService().score(
        _dependency(), [_signal(SignalType.VULNERABILITY, Severity.HIGH, id="CVE-1")]
    )

    assert score.components["vulnerability"] == 25.0
    assert any("CVE-1" in line for line in score.rationale)


def test_medium_severity_eol_does_not_score_but_critical_does() -> None:
    medium = RiskScoringService().score(
        _dependency(), [_signal(SignalType.EOL, Severity.MEDIUM, eol="2030-01-01")]
    )
    critical = RiskScoringService().score(
        _dependency(), [_signal(SignalType.EOL, Severity.CRITICAL, eol="2020-01-01")]
    )

    assert "eol" not in medium.components
    assert critical.components["eol"] == 15.0


def test_abandonment_and_outdated_signals_score_and_stack() -> None:
    score = RiskScoringService().score(
        _dependency(),
        [
            _signal(SignalType.ABANDONED, Severity.HIGH, archived=True),
            _signal(SignalType.OUTDATED, Severity.MEDIUM, major_versions_behind=2),
        ],
    )

    assert score.components["abandonment"] == 20.0
    assert score.components["major_versions_behind"] == 10.0
    assert score.total == 30.0


def test_total_is_clamped_to_100() -> None:
    all_signals = [
        _signal(SignalType.DEPRECATED, Severity.MEDIUM),
        _signal(SignalType.VULNERABILITY, Severity.CRITICAL, id="CVE-1"),
        _signal(SignalType.ABANDONED, Severity.HIGH, archived=True),
        _signal(SignalType.EOL, Severity.CRITICAL, eol="2020-01-01"),
        _signal(SignalType.OUTDATED, Severity.HIGH, major_versions_behind=5),
    ]

    score = RiskScoringService().score(_dependency(), all_signals)

    assert score.total == 100.0
    assert sum(score.components.values()) == 100.0


def test_custom_weights_override_defaults() -> None:
    service = RiskScoringService(weights={"deprecation": 50.0})

    score = service.score(_dependency(), [_signal(SignalType.DEPRECATED, Severity.MEDIUM)])

    assert score.components["deprecation"] == 50.0
