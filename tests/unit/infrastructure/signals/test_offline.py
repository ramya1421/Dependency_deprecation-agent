from datetime import UTC, datetime
from pathlib import Path

import pytest

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.http.exceptions import OfflineCacheMissError
from dda.infrastructure.signals._offline import empty_on_offline_miss


class _RaisingSource(ISignalSource):
    @property
    def source_name(self) -> str:
        return "raising"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        raise OfflineCacheMissError("https://example.test")


class _OtherErrorSource(ISignalSource):
    @property
    def source_name(self) -> str:
        return "other-error"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        raise RuntimeError("boom")


class _SucceedingSource(ISignalSource):
    @property
    def source_name(self) -> str:
        return "succeeding"

    @empty_on_offline_miss
    async def fetch(self, dependency: Dependency) -> list[Signal]:
        return [
            Signal(
                source=self.source_name,
                signal_type=SignalType.DEPRECATED,
                severity=Severity.HIGH,
                payload={},
                fetched_at=datetime.now(UTC),
            )
        ]


def _dependency() -> Dependency:
    return Dependency(
        name="flask",
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version=None,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


async def test_offline_cache_miss_becomes_empty_list() -> None:
    assert await _RaisingSource().fetch(_dependency()) == []


async def test_other_exceptions_still_propagate() -> None:
    with pytest.raises(RuntimeError):
        await _OtherErrorSource().fetch(_dependency())


async def test_successful_fetch_is_unaffected() -> None:
    signals = await _SucceedingSource().fetch(_dependency())
    assert len(signals) == 1
