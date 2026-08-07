import asyncio
import logging
from collections import defaultdict

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY = 10


class SignalCollector:
    """Fans every dependency out across every signal source concurrently,
    bounded by a semaphore so a scan never opens unbounded connections.
    """

    def __init__(self, sources: list[ISignalSource]) -> None:
        self._sources = sources

    async def collect(self, dependencies: list[Dependency]) -> dict[str, list[Signal]]:
        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        tasks = [
            self._fetch_one(semaphore, dependency, source)
            for dependency in dependencies
            for source in self._sources
        ]
        results = await asyncio.gather(*tasks)

        collected: dict[str, list[Signal]] = defaultdict(list)
        for name, signals in results:
            collected[name].extend(signals)
        return dict(collected)

    async def _fetch_one(
        self, semaphore: asyncio.Semaphore, dependency: Dependency, source: ISignalSource
    ) -> tuple[str, list[Signal]]:
        async with semaphore:
            try:
                signals = await source.fetch(dependency)
            except Exception:
                # One dead/misbehaving source shouldn't fail the whole scan;
                # the circuit breaker already limits how hard we hit it.
                logger.warning(
                    "signal_fetch_failed",
                    extra={"source": source.source_name, "dependency": dependency.name},
                    exc_info=True,
                )
                return dependency.name, []
            return dependency.name, signals
