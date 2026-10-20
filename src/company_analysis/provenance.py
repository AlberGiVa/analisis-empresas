"""Who ran the analysis and with which version of the code (recorded with every run)."""

import getpass
import subprocess
from pathlib import Path

from company_analysis import __version__
from company_analysis.settings import PROJECT_ROOT


def code_version() -> str:
    return __version__


def git_commit(root: Path = PROJECT_ROOT) -> str | None:
    """Short commit hash, with ``-dirty`` if there are uncommitted changes; None without git."""

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain")
    except OSError, subprocess.SubprocessError:
        return None
    return f"{commit}-dirty" if dirty else commit


def current_user() -> str:
    try:
        return getpass.getuser()
    except OSError, KeyError:
        return "desconocido"
