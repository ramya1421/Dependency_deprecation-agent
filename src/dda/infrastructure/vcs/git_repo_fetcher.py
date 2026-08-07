import subprocess
import tempfile
from pathlib import Path

from dda.domain.ports import IRepoFetcher

_URL_PREFIXES = ("http://", "https://", "git@", "ssh://")


class GitRepoFetcher(IRepoFetcher):
    """Local paths pass through unchanged; remote URLs are shallow-cloned into
    a fresh temp directory via the system `git` binary.
    """

    def fetch(self, repo_path_or_url: str) -> Path:
        if not repo_path_or_url.startswith(_URL_PREFIXES):
            return Path(repo_path_or_url)
        dest = Path(tempfile.mkdtemp(prefix="dda-clone-"))
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_path_or_url, str(dest)],
            check=True,
            capture_output=True,
        )
        return dest
