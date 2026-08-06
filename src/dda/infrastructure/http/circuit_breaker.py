from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_at: datetime | None = None


class CircuitBreaker:
    """Per-key closed/open circuit so one dead API can't stall a whole scan."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_after_seconds: float = 60.0,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_after_seconds = reset_after_seconds
        self._now_fn = now_fn
        self._state: dict[str, _CircuitState] = {}

    def is_open(self, key: str) -> bool:
        state = self._state.get(key)
        if state is None or state.opened_at is None:
            return False
        elapsed = (self._now_fn() - state.opened_at).total_seconds()
        if elapsed >= self._reset_after_seconds:
            # Cooldown elapsed: half-open, let the next call test the circuit.
            state.opened_at = None
            state.consecutive_failures = 0
            return False
        return True

    def record_success(self, key: str) -> None:
        self._state.pop(key, None)

    def record_failure(self, key: str) -> None:
        state = self._state.setdefault(key, _CircuitState())
        state.consecutive_failures += 1
        if state.consecutive_failures >= self._failure_threshold and state.opened_at is None:
            state.opened_at = self._now_fn()
