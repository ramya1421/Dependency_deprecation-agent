from dataclasses import dataclass

from dda.domain.entities.dependency import Dependency
from dda.domain.entities.migration_plan import MigrationPlan
from dda.domain.entities.risk_score import RiskScore
from dda.domain.entities.signal import Signal
from dda.domain.entities.usage_site import UsageSite


@dataclass(frozen=True)
class Finding:
    dependency: Dependency
    risk_score: RiskScore
    signals: list[Signal]
    usage_sites: list[UsageSite]
    migration_plan: MigrationPlan | None
