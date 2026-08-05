from dataclasses import dataclass
from pathlib import Path

from dda.domain.value_objects import Ecosystem


@dataclass(frozen=True)
class Dependency:
    name: str
    ecosystem: Ecosystem
    declared_spec: str
    resolved_version: str | None
    is_direct: bool
    is_dev: bool
    manifest_path: Path
