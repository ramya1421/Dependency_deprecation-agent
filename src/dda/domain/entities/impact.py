from dataclasses import dataclass

from dda.domain.value_objects import EffortEstimate


@dataclass(frozen=True)
class Impact:
    package: str
    total_call_sites: int
    confirmed_call_sites: int
    possible_call_sites: int
    distinct_files: int
    affected_symbols: list[str]
    effort: EffortEstimate
