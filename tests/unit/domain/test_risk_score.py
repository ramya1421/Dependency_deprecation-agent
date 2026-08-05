import pytest

from dda.domain.entities import RiskScore


def test_valid_risk_score() -> None:
    score = RiskScore(total=45.0, components={"deprecation": 30.0, "eol": 15.0}, rationale=["x"])
    assert score.total == 45.0


def test_rejects_total_out_of_range() -> None:
    with pytest.raises(ValueError):
        RiskScore(total=150.0, components={"deprecation": 150.0}, rationale=[])
    with pytest.raises(ValueError):
        RiskScore(total=-5.0, components={"deprecation": -5.0}, rationale=[])


def test_rejects_total_not_matching_components() -> None:
    with pytest.raises(ValueError):
        RiskScore(total=50.0, components={"deprecation": 30.0}, rationale=[])


def test_total_must_be_clamped_to_100() -> None:
    with pytest.raises(ValueError):
        RiskScore(total=110.0, components={"a": 60.0, "b": 50.0}, rationale=[])

    score = RiskScore(total=100.0, components={"a": 60.0, "b": 50.0}, rationale=["clamped"])
    assert score.total == 100.0
