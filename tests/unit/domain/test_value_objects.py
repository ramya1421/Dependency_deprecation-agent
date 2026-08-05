import pytest

from dda.domain.value_objects import (
    Confidence,
    Ecosystem,
    EffortEstimate,
    Severity,
    SignalType,
)


def test_ecosystem_members() -> None:
    assert {e.value for e in Ecosystem} == {
        "python",
        "javascript",
        "go",
        "java",
        "rust",
        "csharp",
    }


def test_severity_members() -> None:
    assert {s.value for s in Severity} == {"critical", "high", "medium", "low", "none"}


def test_confidence_members() -> None:
    assert {c.value for c in Confidence} == {"static_confirmed", "possible"}


def test_effort_estimate_members() -> None:
    assert {e.value for e in EffortEstimate} == {"trivial", "small", "medium", "large"}


def test_signal_type_members() -> None:
    assert {s.value for s in SignalType} == {
        "deprecated",
        "vulnerability",
        "eol",
        "abandoned",
        "outdated",
    }


def test_ecosystem_is_string_comparable() -> None:
    assert Ecosystem.PYTHON == "python"


def test_ecosystem_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        Ecosystem("cobol")
