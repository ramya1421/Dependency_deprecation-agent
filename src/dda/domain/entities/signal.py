from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dda.domain.value_objects import Severity, SignalType


@dataclass(frozen=True)
class Signal:
    source: str
    signal_type: SignalType
    severity: Severity
    payload: dict[str, Any]
    fetched_at: datetime
