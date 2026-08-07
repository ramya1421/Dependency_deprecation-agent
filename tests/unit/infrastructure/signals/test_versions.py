from dda.domain.value_objects import Severity
from dda.infrastructure.signals._versions import (
    major_versions_behind,
    severity_for_major_versions_behind,
)


def test_returns_none_when_not_behind() -> None:
    assert major_versions_behind("2.0.0", "2.0.0") is None
    assert major_versions_behind("3.0.0", "2.0.0") is None


def test_returns_gap_when_behind() -> None:
    assert major_versions_behind("1.0.0", "3.0.0") == 2


def test_returns_none_when_version_unknown() -> None:
    assert major_versions_behind(None, "3.0.0") is None
    assert major_versions_behind("1.0.0", None) is None


def test_returns_none_when_unparseable() -> None:
    assert major_versions_behind("not-a-version", "3.0.0") is None


def test_severity_bands() -> None:
    assert severity_for_major_versions_behind(1) == Severity.LOW
    assert severity_for_major_versions_behind(2) == Severity.MEDIUM
    assert severity_for_major_versions_behind(3) == Severity.MEDIUM
    assert severity_for_major_versions_behind(4) == Severity.HIGH
