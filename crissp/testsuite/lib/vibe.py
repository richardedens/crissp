"""Mistral Vibe's trusted folders (F-24, F-26): one place for crissp init and crissp repair.

Vibe loads a project's .vibe/config.toml only in a folder listed under `trusted` in VIBE_HOME/trusted_folders.toml
(else ~/.vibe). The file is read with tomllib and written back in Vibe's own shape. It never adds a folder twice
(backslash and forward-slash spellings are the same folder), never trusts a folder listed under `untrusted`, never
removes an entry, and leaves a file it does not know (anything but the two lists of strings) as it is.
"""

import json
import os
import tomllib
from pathlib import Path, PurePath

FILE = "trusted_folders.toml"


def home(env: dict) -> Path:
    """Where Vibe keeps its configuration: VIBE_HOME, else ~/.vibe (the same on Windows, macOS and Linux)."""
    return Path(env.get("VIBE_HOME") or Path.home() / ".vibe")


def _key(path: str | PurePath) -> str:
    return str(path).replace("\\", "/").rstrip("/")


def _lists(db: Path) -> tuple[list[str], list[str]] | None:
    """(trusted, untrusted), or None when the file is not the shape Vibe writes."""
    if not db.is_file():
        return [], []
    try:
        data = tomllib.loads(db.read_text())
    except tomllib.TOMLDecodeError:
        return None
    lists = data.get("trusted", []), data.get("untrusted", [])
    if set(data) - {"trusted", "untrusted"} or not all(
        isinstance(x, list) and all(isinstance(s, str) for s in x) for x in lists
    ):
        return None
    return lists


def state(vibe_home: Path, root: PurePath) -> str:
    """'trusted', 'untrusted', 'absent', or 'unreadable' (a file crissp does not know)."""
    lists = _lists(vibe_home / FILE)
    if lists is None:
        return "unreadable"
    trusted, untrusted = lists
    if any(_key(x) == _key(root) for x in untrusted):
        return "untrusted"
    return "trusted" if any(_key(x) == _key(root) for x in trusted) else "absent"


def _array(items: list[str]) -> str:
    return "[\n" + "".join(f"    {json.dumps(x)},\n" for x in items) + "]" if items else "[]"


def trust(vibe_home: Path, root: PurePath) -> str:
    """Add root to the trusted folders when it is absent; says what it did."""
    db = vibe_home / FILE
    now = state(vibe_home, root)
    if now == "trusted":
        return f"{db} already trusts {root}"
    if now == "untrusted":
        return f"{root} is marked untrusted in {db}: left as you set it"
    if now == "unreadable":
        return f"{db} is not in a shape crissp knows: left alone; trust {root} from vibe itself"
    trusted, untrusted = _lists(db)
    tmp = db.with_name(db.name + ".tmp")
    tmp.write_text(f"trusted = {_array([*trusted, str(root)])}\nuntrusted = {_array(untrusted)}\n")
    os.replace(tmp, db)
    return f"trusted {root} in {db} (to undo: remove that line)"
