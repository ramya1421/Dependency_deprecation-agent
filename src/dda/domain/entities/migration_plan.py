from dataclasses import dataclass

from dda.domain.entities.claim import Claim
from dda.domain.entities.usage_site import UsageSite
from dda.domain.value_objects import EffortEstimate


@dataclass(frozen=True)
class MigrationPlan:
    package: str
    summary: str
    steps: list[str]
    claims: list[Claim]
    usage_sites: list[UsageSite]
    effort: EffortEstimate
