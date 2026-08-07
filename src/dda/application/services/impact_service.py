from dda.domain.entities import Impact, Signal, UsageSite
from dda.domain.value_objects import Confidence, EffortEstimate, Severity

_EFFORT_ORDER = (
    EffortEstimate.TRIVIAL,
    EffortEstimate.SMALL,
    EffortEstimate.MEDIUM,
    EffortEstimate.LARGE,
)
_SEVERE_SEVERITIES = {Severity.CRITICAL, Severity.HIGH}


class ImpactService:
    """Cross-joins a package's usage sites against its signals: usage sites
    say HOW MUCH code touches the package, signals say how urgent that
    exposure is. Coarse by design — this is a triage signal, not a precise
    migration estimate.
    """

    def assess(
        self, package: str, usage_sites: list[UsageSite], signals: list[Signal]
    ) -> Impact:
        package_sites = [s for s in usage_sites if s.package.lower() == package.lower()]
        confirmed = [s for s in package_sites if s.confidence is Confidence.STATIC_CONFIRMED]
        possible = [s for s in package_sites if s.confidence is Confidence.POSSIBLE]

        effort = self._base_effort(len(package_sites))
        if any(s.severity in _SEVERE_SEVERITIES for s in signals):
            effort = self._bump(effort)

        return Impact(
            package=package,
            total_call_sites=len(package_sites),
            confirmed_call_sites=len(confirmed),
            possible_call_sites=len(possible),
            distinct_files=len({s.file_path for s in package_sites}),
            affected_symbols=sorted({s.symbol for s in package_sites}),
            effort=effort,
        )

    @staticmethod
    def _base_effort(total_call_sites: int) -> EffortEstimate:
        # Coarse, documented thresholds — not a precise LOC/hour estimate.
        if total_call_sites == 0:
            return EffortEstimate.TRIVIAL
        if total_call_sites <= 5:
            return EffortEstimate.SMALL
        if total_call_sites <= 20:
            return EffortEstimate.MEDIUM
        return EffortEstimate.LARGE

    @staticmethod
    def _bump(effort: EffortEstimate) -> EffortEstimate:
        index = _EFFORT_ORDER.index(effort)
        return _EFFORT_ORDER[min(index + 1, len(_EFFORT_ORDER) - 1)]
