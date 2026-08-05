import json
from pathlib import Path
from typing import Any

from dda.domain.entities import Dependency
from dda.domain.ports import IManifestParser
from dda.domain.value_objects import Ecosystem
from dda.infrastructure.parsers.parse_result import ParseResult, SkippedDeclaration


def _classify_spec(name: str, spec: str) -> SkippedDeclaration | None:
    if spec.startswith("file:"):
        return SkippedDeclaration(f"{name}: {spec}", "local_path")
    if spec.startswith("link:"):
        return SkippedDeclaration(f"{name}: {spec}", "local_path")
    if spec.startswith("git+ssh:") or "git+" in spec or spec.startswith("git://"):
        return SkippedDeclaration(f"{name}: {spec}", "vcs_url")
    if spec.startswith("workspace:"):
        return SkippedDeclaration(f"{name}: {spec}", "workspace_glob")
    return None


class NpmManifestParser(IManifestParser):
    @property
    def ecosystem(self) -> Ecosystem:
        return Ecosystem.JAVASCRIPT

    def detect(self, repo_root: Path) -> list[Path]:
        found: list[Path] = []
        for name in ("package.json", "package-lock.json"):
            path = repo_root / name
            if path.is_file():
                found.append(path)
        return found

    def parse(self, manifest: Path) -> list[Dependency]:
        return self.parse_with_coverage(manifest).dependencies

    def parse_with_coverage(self, manifest: Path) -> ParseResult:
        if manifest.name == "package-lock.json":
            return self._parse_package_lock(manifest)
        return self._parse_package_json(manifest)

    def _parse_package_json(self, manifest: Path) -> ParseResult:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        dependencies: list[Dependency] = []
        skipped: list[SkippedDeclaration] = []
        for field, is_dev in (("dependencies", False), ("devDependencies", True)):
            for name, spec in data.get(field, {}).items():
                skip = _classify_spec(name, str(spec))
                if skip is not None:
                    skipped.append(skip)
                    continue
                dependencies.append(
                    Dependency(
                        name=name,
                        ecosystem=Ecosystem.JAVASCRIPT,
                        declared_spec=str(spec),
                        resolved_version=None,
                        is_direct=True,
                        is_dev=is_dev,
                        manifest_path=manifest,
                    )
                )
        return ParseResult(dependencies, skipped)

    def _parse_package_lock(self, manifest: Path) -> ParseResult:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if "packages" in data:
            return self._parse_lock_packages(data["packages"], manifest)
        return self._parse_lock_dependencies_v1(data.get("dependencies", {}), manifest)

    def _parse_lock_packages(
        self, packages: dict[str, Any], manifest: Path
    ) -> ParseResult:
        dependencies: list[Dependency] = []
        for path, entry in packages.items():
            if path == "" or "node_modules/" not in path:
                continue
            name = path.rsplit("node_modules/", 1)[1]
            # more than one "node_modules/" segment means a nested, non-hoisted
            # transitive copy rather than a direct/hoisted dependency
            is_direct = path.count("node_modules/") == 1
            version = entry.get("version")
            if version is None:
                continue
            dependencies.append(
                Dependency(
                    name=name,
                    ecosystem=Ecosystem.JAVASCRIPT,
                    declared_spec=version,
                    resolved_version=version,
                    is_direct=is_direct,
                    is_dev=bool(entry.get("dev", False)),
                    manifest_path=manifest,
                )
            )
        return ParseResult(dependencies, [])

    def _parse_lock_dependencies_v1(
        self, deps: dict[str, Any], manifest: Path
    ) -> ParseResult:
        # v1 lockfiles nest transitive dependencies recursively; only the
        # top-level (direct/hoisted) entries are read to keep this simple.
        dependencies: list[Dependency] = []
        for name, entry in deps.items():
            version = entry.get("version")
            if version is None:
                continue
            dependencies.append(
                Dependency(
                    name=name,
                    ecosystem=Ecosystem.JAVASCRIPT,
                    declared_spec=version,
                    resolved_version=version,
                    is_direct=True,
                    is_dev=bool(entry.get("dev", False)),
                    manifest_path=manifest,
                )
            )
        return ParseResult(dependencies, [])
