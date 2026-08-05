from dataclasses import dataclass
from pathlib import Path

from dda.domain.value_objects import Confidence


@dataclass(frozen=True)
class UsageSite:
    package: str
    symbol: str
    file_path: Path
    line_number: int
    column_number: int
    usage_kind: str
    confidence: Confidence
    snippet: str
