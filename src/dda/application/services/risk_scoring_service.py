from dda.domain.entities import Dependency, RiskScore, Signal
from dda.domain.value_objects import Severity, SignalType

DEFAULT_RISK_WEIGHTS: dict[str, float] = {
    "deprecation": 30.0,
    "vulnerability": 25.0,
    "abandonment": 20.0,
    "eol": 15.0,
    "major_versions_behind": 10.0,
}

_NEAR_TERM_SEVERITIES = {Severity.CRITICAL, Severity.HIGH}


class RiskScoringService:
    """Turns raw signals into an explainable RiskScore. Every component maps to
    one configured weight and one rationale line — a bare number is
    unfalsifiable, so this never returns one without an accompanying trail.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or DEFAULT_RISK_WEIGHTS

    def score(self, dependency: Dependency, signals: list[Signal]) -> RiskScore:
        components: dict[str, float] = {}
        rationale: list[str] = []

        self._score_deprecation(dependency, signals, components, rationale)
        self._score_vulnerability(signals, components, rationale)
        self._score_abandonment(signals, components, rationale)
        self._score_eol(signals, components, rationale)
        self._score_outdated(signals, components, rationale)

        if not components:
            rationale.append(f"{dependency.name}: no risk signals found")

        total = min(sum(components.values()), 100.0)
        return RiskScore(total=total, components=components, rationale=rationale)

    def _score_deprecation(
        self,
        dependency: Dependency,
        signals: list[Signal],
        components: dict[str, float],
        rationale: list[str],
    ) -> None:
        deprecated = [s for s in signals if s.signal_type is SignalType.DEPRECATED]
        if not deprecated:
            return
        components["deprecation"] = self._weights["deprecation"]
        sources = ", ".join(sorted({s.source for s in deprecated}))
        rationale.append(f"{dependency.name} is explicitly deprecated (source: {sources})")

    def _score_vulnerability(
        self, signals: list[Signal], components: dict[str, float], rationale: list[str]
    ) -> None:
        severe = [
            s
            for s in signals
            if s.signal_type is SignalType.VULNERABILITY and s.severity in _NEAR_TERM_SEVERITIES
        ]
        if not severe:
            return
        components["vulnerability"] = self._weights["vulnerability"]
        ids = ", ".join(sorted({str(s.payload.get("id", "unknown")) for s in severe}))
        rationale.append(f"{len(severe)} critical/high vulnerability(ies): {ids}")

    def _score_abandonment(
        self, signals: list[Signal], components: dict[str, float], rationale: list[str]
    ) -> None:
        abandoned = [s for s in signals if s.signal_type is SignalType.ABANDONED]
        if not abandoned:
            return
        components["abandonment"] = self._weights["abandonment"]
        reason = "archived" if abandoned[0].payload.get("archived") else "no commits in 18 months"
        rationale.append(f"repository appears abandoned ({reason})")

    def _score_eol(
        self, signals: list[Signal], components: dict[str, float], rationale: list[str]
    ) -> None:
        near_term = [
            s
            for s in signals
            if s.signal_type is SignalType.EOL and s.severity in _NEAR_TERM_SEVERITIES
        ]
        if not near_term:
            return
        components["eol"] = self._weights["eol"]
        eol_date = near_term[0].payload.get("eol")
        rationale.append(f"end-of-life within 6 months or already reached (eol: {eol_date})")

    def _score_outdated(
        self, signals: list[Signal], components: dict[str, float], rationale: list[str]
    ) -> None:
        outdated = [s for s in signals if s.signal_type is SignalType.OUTDATED]
        if not outdated:
            return
        components["major_versions_behind"] = self._weights["major_versions_behind"]
        behind = outdated[0].payload.get("major_versions_behind")
        rationale.append(f"{behind} major version(s) behind latest")
