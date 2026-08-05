import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from dda.domain.entities import Dependency
from dda.domain.ports import IManifestParser
from dda.domain.value_objects import Ecosystem
from dda.infrastructure.parsers.parse_result import ParseResult, SkippedDeclaration

_REQUIREMENTS_PRAGMA_PREFIXES: tuple[tuple[str, str], ...] = (
    ("-r ", "recursive_include"),
    ("--requirement ", "recursive_include"),
    ("-e ", "editable_install"),
    ("--editable ", "editable_install"),
    ("--index-url", "index_url_option"),
    ("--extra-index-url", "index_url_option"),
    ("-i ", "index_url_option"),
)
_VCS_PREFIXES = ("git+", "hg+", "svn+", "bzr+")
_LOCAL_PATH_PREFIXES = (".", "/")


def _classify_requirements_line(line: str) -> str | None:
    """Return a skip reason for requirements.txt-only pragma lines, else None."""
    if not line:
        return "blank_line"
    if line.startswith("#"):
        return "comment"
    for prefix, reason in _REQUIREMENTS_PRAGMA_PREFIXES:
        if line.startswith(prefix):
            return reason
    if "--hash=" in line:
        return "hash_pin"
    return None


def _parse_pep508(
    text: str, manifest_path: Path, is_dev: bool
) -> Dependency | SkippedDeclaration:
    """Parse a single PEP 508 requirement string, failing soft on VCS/local/marker cases."""
    if any(prefix in text for prefix in _VCS_PREFIXES):
        return SkippedDeclaration(text, "vcs_url")
    if "file://" in text or text.startswith(_LOCAL_PATH_PREFIXES):
        return SkippedDeclaration(text, "local_path")
    if ";" in text:
        return SkippedDeclaration(text, "environment_marker")
    try:
        req = Requirement(text)
    except InvalidRequirement as exc:
        return SkippedDeclaration(text, f"unparseable: {exc}")
    return Dependency(
        name=req.name,
        ecosystem=Ecosystem.PYTHON,
        declared_spec=str(req.specifier) or "*",
        resolved_version=None,
        is_direct=True,
        is_dev=is_dev,
        manifest_path=manifest_path,
    )


class PythonManifestParser(IManifestParser):
    @property
    def ecosystem(self) -> Ecosystem:
        return Ecosystem.PYTHON

    def detect(self, repo_root: Path) -> list[Path]:
        found: list[Path] = []
        for pattern in ("requirements*.txt", "pyproject.toml", "poetry.lock"):
            found.extend(sorted(repo_root.glob(pattern)))
        return found

    def parse(self, manifest: Path) -> list[Dependency]:
        return self.parse_with_coverage(manifest).dependencies

    def parse_with_coverage(self, manifest: Path) -> ParseResult:
        if manifest.name == "poetry.lock":
            return self._parse_poetry_lock(manifest)
        if manifest.name == "pyproject.toml":
            return self._parse_pyproject_toml(manifest)
        return self._parse_requirements_txt(manifest)

    def _parse_requirements_txt(self, manifest: Path) -> ParseResult:
        is_dev = "dev" in manifest.stem.lower()
        dependencies: list[Dependency] = []
        skipped: list[SkippedDeclaration] = []
        for raw_line in manifest.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            reason = _classify_requirements_line(line)
            if reason is not None:
                skipped.append(SkippedDeclaration(raw_line, reason))
                continue
            result = _parse_pep508(line, manifest, is_dev)
            if isinstance(result, Dependency):
                dependencies.append(result)
            else:
                skipped.append(result)
        return ParseResult(dependencies, skipped)

    def _parse_pyproject_toml(self, manifest: Path) -> ParseResult:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        dependencies: list[Dependency] = []
        skipped: list[SkippedDeclaration] = []

        for entry in data.get("project", {}).get("dependencies", []):
            result = _parse_pep508(entry, manifest, is_dev=False)
            if isinstance(result, Dependency):
                dependencies.append(result)
            else:
                skipped.append(result)

        poetry_deps: dict[str, Any] = (
            data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        )
        for name, spec in poetry_deps.items():
            if name == "python":
                continue
            result = self._parse_poetry_dependency(name, spec, manifest)
            if isinstance(result, Dependency):
                dependencies.append(result)
            else:
                skipped.append(result)

        return ParseResult(dependencies, skipped)

    def _parse_poetry_dependency(
        self, name: str, spec: Any, manifest: Path
    ) -> Dependency | SkippedDeclaration:
        if isinstance(spec, dict):
            if "git" in spec:
                return SkippedDeclaration(f"{name} = {spec}", "vcs_url")
            if "path" in spec:
                return SkippedDeclaration(f"{name} = {spec}", "local_path")
            declared_spec = str(spec.get("version", "*"))
        else:
            declared_spec = str(spec)
        return Dependency(
            name=name,
            ecosystem=Ecosystem.PYTHON,
            declared_spec=declared_spec,
            resolved_version=None,
            is_direct=True,
            is_dev=False,
            manifest_path=manifest,
        )

    def _parse_poetry_lock(self, manifest: Path) -> ParseResult:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        dependencies: list[Dependency] = []
        # poetry.lock has no reliable direct/transitive marker across lock versions,
        # so every locked package is reported as direct; callers that need the
        # distinction should cross-reference pyproject.toml's parse result.
        for pkg in data.get("package", []):
            dependencies.append(
                Dependency(
                    name=pkg["name"],
                    ecosystem=Ecosystem.PYTHON,
                    declared_spec=pkg["version"],
                    resolved_version=pkg["version"],
                    is_direct=True,
                    is_dev=pkg.get("category") == "dev",
                    manifest_path=manifest,
                )
            )
        return ParseResult(dependencies, [])
