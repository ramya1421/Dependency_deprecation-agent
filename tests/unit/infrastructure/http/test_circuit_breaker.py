from datetime import UTC, datetime, timedelta

from dda.infrastructure.http.circuit_breaker import CircuitBreaker


def test_closed_by_default() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    assert breaker.is_open("github") is False


def test_opens_after_threshold_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure("github")
    assert breaker.is_open("github") is False

    breaker.record_failure("github")
    assert breaker.is_open("github") is True


def test_success_resets_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure("github")
    breaker.record_success("github")
    breaker.record_failure("github")

    assert breaker.is_open("github") is False


def test_failures_are_isolated_per_key() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure("github")

    assert breaker.is_open("github") is True
    assert breaker.is_open("pypi") is False


def test_half_opens_after_cooldown() -> None:
    clock = {"now": datetime(2026, 1, 1, tzinfo=UTC)}
    breaker = CircuitBreaker(
        failure_threshold=1, reset_after_seconds=60, now_fn=lambda: clock["now"]
    )
    breaker.record_failure("github")
    assert breaker.is_open("github") is True

    clock["now"] += timedelta(seconds=61)
    assert breaker.is_open("github") is False
