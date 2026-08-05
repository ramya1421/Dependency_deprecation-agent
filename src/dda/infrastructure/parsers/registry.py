from pathlib import Path

from dda.domain.ports import IManifestParser
from dda.domain.value_objects import Ecosystem


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[IManifestParser] = []

    def register(self, parser: IManifestParser) -> None:
        self._parsers.append(parser)

    def detect_all(self, repo_root: Path) -> dict[Ecosystem, list[Path]]:
        detected: dict[Ecosystem, list[Path]] = {}
        for parser in self._parsers:
            manifests = parser.detect(repo_root)
            if manifests:
                detected[parser.ecosystem] = manifests
        return detected
