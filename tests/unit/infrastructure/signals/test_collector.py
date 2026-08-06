from datetime import UTC, datetime
from pathlib import Path

from dda.domain.entities import Dependency, Signal
from dda.domain.ports import ISignalSource
from dda.domain.value_objects import Ecosystem, Severity, SignalType
from dda.infrastructure.signals.collector import SignalCollector


class _FakeSource(ISignalSource):
    def __init__(
        self, name: str, signal_type: SignalType | None = None, raises: bool = False
    ) -> None:
        self._name = name
        self._signal_type = signal_type
        self._raises = raises

    @property
    def source_name(self) -> str:
        return self._name

    async def fetch(self, dependency: Dependency) -> list[Signal]:
        if self._raises:
            raise RuntimeError("boom")
        if self._signal_type is None:
            return []
        return [
            Signal(
                source=self._name,
                signal_type=self._signal_type,
                severity=Severity.HIGH,
                payload={},
                fetched_at=datetime.now(UTC),
            )
        ]


def _dependency(name: str) -> Dependency:
    return Dependency(
        name=name,
        ecosystem=Ecosystem.PYTHON,
        declared_spec="*",
        resolved_version=None,
        is_direct=True,
        is_dev=False,
        manifest_path=Path("requirements.txt"),
    )


async def test_collects_signals_from_all_sources_for_all_dependencies() -> None:
    collector = SignalCollector(
        [_FakeSource("a", SignalType.DEPRECATED), _FakeSource("b", SignalType.VULNERABILITY)]
    )

    result = await collector.collect([_dependency("flask"), _dependency("django")])

    assert set(result.keys()) == {"flask", "django"}
    assert {s.source for s in result["flask"]} == {"a", "b"}
    assert {s.source for s in result["django"]} == {"a", "b"}


async def test_one_failing_source_does_not_break_the_others() -> None:
    collector = SignalCollector(
        [_FakeSource("a", SignalType.DEPRECATED), _FakeSource("broken", raises=True)]
    )

    result = await collector.collect([_dependency("flask")])

    assert {s.source for s in result["flask"]} == {"a"}


async def test_empty_dependency_list_returns_empty_dict() -> None:
    collector = SignalCollector([_FakeSource("a", SignalType.DEPRECATED)])

    result = await collector.collect([])

    assert result == {}
