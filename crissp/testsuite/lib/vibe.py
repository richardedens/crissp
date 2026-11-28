"""Mistral Vibe's trusted folders (F-24, F-26): one place for crissp init and crissp repair.

Vibe loads a project's .vibe/config.toml only in a folder listed under `trusted` in VIBE_HOME/trusted_folders.toml
(else ~/.vibe). The file is read with tomllib and written back in Vibe's own shape. It never adds a folder twice
(backslash and forward-slash spellings are the same folder), never trusts a folder listed under `untrusted`, never
removes an entry, and leaves a file it does not know (anything but the two lists of strings) as it is.
"""

import json
import os
import shutil
import sys
import tomllib
from pathlib import Path, PurePath

FILE = "trusted_folders.toml"
CONFIG = Path(__file__).resolve().parents[2] / "template" / "vibe" / "config.toml"  # the engine's, beside this file


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
            isinstance(x, list) and all(isinstance(s, str) for s in x) for x in lists):
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


def fields(root: PurePath, command: str, args: list[str], path: str | None = None) -> dict[str, str]:
    """F-100: the config's placeholders as TOML values (json.dumps: a backslash in a Windows path stays valid). F-107:
    the PATH of the shell this runs in (else the given one), for what the server starts."""
    return {"VIBE_COMMAND": json.dumps(command), "VIBE_ARGS": json.dumps(args), "VIBE_ROOT": json.dumps(str(root)),
            "VIBE_PATH": json.dumps(os.environ.get("PATH", "") if path is None else path)}


def config(root: PurePath, command: str, args: list[str], path: str | None = None) -> str:
    """F-100: .vibe/config.toml for this machine. Vibe's desktop app starts the server from its own folder with only
    HOME, PATH and a few more, so the project's folder is named (cwd and CRISSP_ROOT) and the command is a full path;
    the first `uvx crissp==x` downloads, so it gets 60 s instead of Vibe's 10. F-107: the app's PATH is not the
    terminal's (on a Mac, bash 3.2 and python 3.9 first), so the checks the server starts get this shell's PATH."""
    text = CONFIG.read_text()
    for key, value in fields(root, command, args, path).items():
        text = text.replace("{{" + key + "}}", value)
    return text


def server(root: Path, version: str | None, engine: bool = False) -> tuple[str, list[str]]:
    """F-100: what starts the crissp server for a project: uvx (by its full path when it is on PATH) with this
    crissp's pin; in the framework's own checkout (engine), its own server with the Python that runs this."""
    if engine:
        return sys.executable, ["-I", str(root / "crissp" / "tool" / "server.py")]
    return shutil.which("uvx") or "uvx", [f"crissp=={version}", "mcp"]


def pinned(text: str, root: PurePath) -> bool:
    """F-100: whether a config's crissp server names this project's folder (cwd and CRISSP_ROOT) and, F-107, a PATH, as
    Vibe's desktop app needs; a config crissp does not know counts as pinned (left as it is)."""
    try:
        servers = tomllib.loads(text).get("mcp_servers")
    except tomllib.TOMLDecodeError:
        return True
    mine = [s for s in servers if isinstance(s, dict) and s.get("name") == "crissp"] if isinstance(servers, list) else []
    if not mine:
        return True
    env = mine[0].get("env") if isinstance(mine[0].get("env"), dict) else {}
    return _key(mine[0].get("cwd", "")) == _key(root) and _key(env.get("CRISSP_ROOT", "")) == _key(root) \
        and bool(env.get("PATH"))
