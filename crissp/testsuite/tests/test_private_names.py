"""C.R.I.S.S.P. is open source: no tracked file names the private projects or the company it came from. The names are
kept here only as SHA-256 hashes of the lower-case word, so this guard does not name them either."""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PRIVATE = {
    "598f7a741a1e3a05654d346033571fda567af6dc2bf099b34b930171519d995f",
    "ed078c3b90083544d15d50dc70d2bd70465ce5fa96b81fea2e163dc40e39af22",
    "77d0f44dd73361288b85b8fed1c3681bee103a1707b22855e7d0f115713895ef",
}


def private_words(text: str) -> set[str]:
    """The words of text (lower case, letters and digits) whose hash is a private name."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return {w for w in words if hashlib.sha256(w.encode()).hexdigest() in PRIVATE}


def test_a_private_name_is_found_in_any_case_and_inside_a_path():
    name = "aeg" + "is"  # spelled in two halves, so this file never holds the word
    assert private_words(f"Scanned by {name.upper()}: see ~/{name}-prod/x") == {name}
    assert private_words(f"an {name}x, the flow of work") == set()


# never in git, so never what a guard reads: generated output, installed tools, caches
LOCAL = {".git", "results", ".venv", "node_modules", "__pycache__", ".terraform", ".pytest_cache", "worktrees"}


def repository_files(repo: Path = REPO) -> list[str]:
    """The files git tracks; without git (a fresh copy, an unpacked release), every file but what git never keeps."""
    try:
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True).stdout
        names = list(filter(None, listed.decode().split("\0")))
    except (OSError, subprocess.CalledProcessError):
        names = []
    if names:
        return names
    return sorted(str(p.relative_to(repo)) for p in repo.rglob("*")
                  if p.is_file() and not LOCAL & set(p.relative_to(repo).parts) and p.name != ".DS_Store")


def test_without_git_every_file_but_what_git_never_keeps_is_read(tmp_path):
    (tmp_path / "crissp/testsuite/results").mkdir(parents=True)
    (tmp_path / "crissp/testsuite/results/run.log").write_text("x")
    (tmp_path / "crissp/a.py").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/x.js").write_text("x")
    (tmp_path / ".DS_Store").write_text("x")
    assert repository_files(tmp_path) == ["crissp/a.py"]


def test_no_tracked_file_names_a_private_project():
    hits = []
    for name in repository_files():
        path = REPO / name
        if not path.is_file():
            continue  # deleted in the working tree
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue  # binary
        if private_words(text) or private_words(name):
            hits.append(name)
    assert hits == []
