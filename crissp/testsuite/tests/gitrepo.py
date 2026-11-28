"""git in a test's throwaway repository, as a test user, never signing: the helper four test modules carried a copy of."""

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    """Run git in root and return its stdout; a failure fails the test."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
