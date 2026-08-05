import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskScore:
    total: float
    components: dict[str, float]
    rationale: list[str]

    def __post_init__(self) -> None:
        if not (0.0 <= self.total <= 100.0):
            raise ValueError(f"RiskScore.total must be within 0-100, got {self.total}")
        expected = min(sum(self.components.values()), 100.0)
        if not math.isclose(self.total, expected, abs_tol=1e-6):
            raise ValueError(
                f"RiskScore.total ({self.total}) must equal the sum of components "
                f"clamped to 100 ({expected})"
            )
