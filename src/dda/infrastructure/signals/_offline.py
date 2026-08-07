from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.infrastructure.http.exceptions import OfflineCacheMissError

_T = TypeVar("_T", bound=ISignalSource)
# Matches what mypy infers for an `async def fetch(...) -> list[Signal]`
# override, so the decorated method stays override-compatible with the
# ISignalSource ABC (a plain Awaitable[...] alias doesn't satisfy mypy strict).
_FetchMethod = Callable[[_T, Dependency], Coroutine[Any, Any, list[Signal]]]


def empty_on_offline_miss(fetch: _FetchMethod[_T]) -> _FetchMethod[_T]:
    """Offline mode plus a cold cache is an expected condition, not a
    failure — treat it as "no signal" instead of letting a noisy exception
    propagate up through SignalCollector for every uncached lookup.
    """

    @wraps(fetch)
    async def wrapper(self: _T, dependency: Dependency) -> list[Signal]:
        try:
            return await fetch(self, dependency)
        except OfflineCacheMissError:
            return []

    return wrapper
