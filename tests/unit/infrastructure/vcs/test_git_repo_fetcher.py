import subprocess
from pathlib import Path
from typing import Any

import pytest

from dda.infrastructure.vcs.git_repo_fetcher import GitRepoFetcher


def test_local_path_passes_through_unchanged(tmp_path: Path) -> None:
    result = GitRepoFetcher().fetch(str(tmp_path))

    assert result == tmp_path


def test_remote_url_clones_into_a_temp_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = GitRepoFetcher().fetch("https://github.com/pallets/flask.git")

    assert captured["cmd"][:3] == ["git", "clone", "--depth"]
    assert "https://github.com/pallets/flask.git" in captured["cmd"]
    assert result.exists()
    result.rmdir()
