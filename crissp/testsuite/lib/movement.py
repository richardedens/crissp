"""How the backlog moved (E3-F2-01): every PBI's moves on the board, from where to where, when, and in which commit, or
"not committed yet" for what the working tree holds beyond the last commit.

It replays the epic files (crissp/backlog/E*.md and crissp/backlog/done/E*.md) through every commit that changed them,
reading only the files a commit changed, and parses them with the crissp tool's own parser (crissp/tool/server.py: one
parser, never a second, so three-level ids such as E2-F1-01 count). A file an old commit holds in another encoding is
read as UTF-8, else Windows' cp1252 (F-16). A PBI that moves to the done folder is one move, not a new PBI.

    moves(root, tool)            {pbi: [{from, to, at, commit, subject}, ...]}, oldest first; from None: new
    recent(moves, titles, n)     the n newest moves of all PBIs, with their titles, newest first
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path

EPIC_FILE = re.compile(r"^crissp/backlog/(?:done/)?E[^/]*\.md$")


def _git(root: Path, *args: str) -> bytes | None:
    done = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=off", *args], capture_output=True, check=False)
    return done.stdout if done.returncode == 0 else None


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _statuses(tool, text: str) -> dict[str, str]:
    return {m.group(1): m.group(3) for m in tool.ITEM.finditer(text)}


def _merged(per_file: dict[str, dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for states in per_file.values():
        out.update(states)
    return out


def _record(
    before: dict[str, str], after: dict[str, str], at: str, commit: str | None, subject: str, out: dict[str, list[dict]]
) -> None:
    for pbi, status in after.items():
        if before.get(pbi) != status:
            out.setdefault(pbi, []).append(
                {"from": before.get(pbi), "to": status, "at": at, "commit": commit, "subject": subject}
            )


def moves(root: Path, tool) -> dict[str, list[dict]]:
    """Each PBI's moves, oldest first: the commits that changed the epic files, then the working tree."""
    out: dict[str, list[dict]] = {}
    log = _git(
        root,
        "log",
        "--reverse",
        "--no-renames",
        "--format=%x00%H%x09%h%x09%cI%x09%s",
        "--name-status",
        "--",
        "crissp/backlog",
    )
    per_file: dict[str, dict[str, str]] = {}
    state: dict[str, str] = {}
    for chunk in _text(log or b"").split("\x00")[1:]:
        head, _, changed = chunk.partition("\n")
        sha, short, at, subject = head.split("\t", 3)
        for line in changed.splitlines():
            kind, _, path = line.partition("\t")
            if not EPIC_FILE.match(path):
                continue
            if kind == "D":
                per_file.pop(path, None)
            else:
                per_file[path] = _statuses(tool, _text(_git(root, "show", f"{sha}:{path}") or b""))
        now = _merged(per_file)
        _record(state, now, at, short, subject, out)
        state = now
    files = tool.epic_files(root)
    tree = {str(f.relative_to(root)): _statuses(tool, _text(f.read_bytes())) for f in files}
    if files:
        at = datetime.fromtimestamp(max(f.stat().st_mtime for f in files)).astimezone().isoformat(timespec="seconds")
        _record(state, _merged(tree), at, None, "", out)
    return out


def recent(found: dict[str, list[dict]], titles: dict[str, str], limit: int = 12) -> list[dict]:
    """The newest moves of all PBIs, newest first, each with its PBI's id and title."""
    every = [{"id": pbi, "title": titles.get(pbi, ""), **m} for pbi, ms in found.items() for m in ms]
    every.sort(key=lambda m: datetime.fromisoformat(m["at"]), reverse=True)
    return every[:limit]
