from packaging.version import InvalidVersion, Version

from dda.domain.value_objects import Severity


def major_versions_behind(resolved: str | None, latest: str | None) -> int | None:
    """How many major versions `resolved` trails `latest`, or None if unknown,
    unparseable, or not behind. Shared by PyPIClient and NpmClient to populate
    SignalType.OUTDATED, which risk scoring's "major versions behind" weight
    depends on.
    """
    if resolved is None or latest is None:
        return None
    try:
        behind = Version(latest).major - Version(resolved).major
    except InvalidVersion:
        return None
    return behind if behind > 0 else None


def severity_for_major_versions_behind(count: int) -> Severity:
    if count >= 4:
        return Severity.HIGH
    if count >= 2:
        return Severity.MEDIUM
    return Severity.LOW
