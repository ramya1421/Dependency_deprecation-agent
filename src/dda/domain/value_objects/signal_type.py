from enum import StrEnum


class SignalType(StrEnum):
    DEPRECATED = "deprecated"
    VULNERABILITY = "vulnerability"
    EOL = "eol"
    ABANDONED = "abandoned"
    OUTDATED = "outdated"
