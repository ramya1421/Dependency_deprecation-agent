from dataclasses import dataclass

from dda.domain.entities import Dependency


@dataclass(frozen=True)
class SkippedDeclaration:
    raw_text: str
    reason: str


@dataclass(frozen=True)
class ParseResult:
    dependencies: list[Dependency]
    skipped: list[SkippedDeclaration]

    @property
    def total_declarations(self) -> int:
        return len(self.dependencies) + len(self.skipped)
