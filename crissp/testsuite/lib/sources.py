"""The files a lint or a scan looks at in a project: its own, never its build output (F-150).

What git tracks or would track in the folder (git ls-files: tracked and untracked files, every .gitignore counting,
wherever it is), without the common build folders (BUILD) even where nothing ignores them. Without git the folder is
walked, the same build folders left out. A tool's own ignore patterns are no substitute: crissp's configs live in its
cache, and some tools read their patterns from the config's folder, so they never match a project's dist/.
"""

import os
import subprocess
from pathlib import Path

# Folders that hold what was built, installed or measured, never code to lint or scan: by their name, at any depth.
BUILD = ("node_modules", "dist", "build", "coverage", ".next", ".nuxt", ".svelte-kit", ".turbo", ".git")
LIMIT = 100_000  # characters of file names per command line: far below what any system allows


def built(path: str) -> bool:
    """A path inside a build folder (BUILD): one of its folders has that name."""
    return any(part in BUILD for part in Path(path).parts[:-1])


def listed(folder: Path) -> list[str] | None:
    """What git lists in the folder, relative to it; None when the folder is not in a git repository."""
    done = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return None
    return [name for name in done.stdout.split("\0") if name and (folder / name).is_file()]


def walked(folder: Path) -> list[str]:
    out = []
    for here, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in BUILD]
        out += [str((Path(here) / name).relative_to(folder)) for name in names]
    return out


def files(folder: Path, suffixes: tuple[str, ...]) -> list[str]:
    """The project's own files in the folder that end in one of the suffixes, relative to it, sorted."""
    names = listed(folder)
    if names is None:
        names = walked(folder)
    return sorted(name for name in names if name.endswith(suffixes) and not built(name))


def batches(names: list[str], limit: int = LIMIT) -> list[list[str]]:
    """The names in order, split so that no command line holds more than limit characters of them."""
    out: list[list[str]] = []
    size = limit
    for name in names:
        if size + len(name) + 1 > limit:
            out.append([])
            size = 0
        out[-1].append(name)
        size += len(name) + 1
    return out
