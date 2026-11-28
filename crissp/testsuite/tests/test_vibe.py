"""F-26: Vibe's trusted_folders.toml is read with tomllib and written in Vibe's own shape, in one place for init and
repair: never a duplicate, never invalid TOML, never a folder the user marked untrusted, never a file it does not know."""

import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import vibe

WIN = Path("C:\\Users\\x\\proj")


def db(home: Path) -> Path:
    return home / "trusted_folders.toml"


def lists(home: Path) -> dict:
    return tomllib.loads(db(home).read_text())


def test_home_is_vibe_home_else_dot_vibe():
    assert vibe.home({"VIBE_HOME": "/v"}) == Path("/v")
    assert vibe.home({}) == Path.home() / ".vibe"


def test_a_windows_path_is_added_once_however_often_it_runs(tmp_path):
    for _ in range(3):
        vibe.trust(tmp_path, WIN)
    assert lists(tmp_path) == {"trusted": [str(WIN)], "untrusted": []}
    assert "already trusts" in vibe.trust(tmp_path, WIN)
    assert vibe.state(tmp_path, WIN) == "trusted"


def test_vibes_own_forward_slash_entry_counts(tmp_path):
    db(tmp_path).write_text('trusted = [\n    "C:/Users/x/proj/",\n]\nuntrusted = []\n')
    assert vibe.state(tmp_path, WIN) == "trusted"


def test_a_one_line_list_stays_valid_toml_and_keeps_its_entries(tmp_path):
    db(tmp_path).write_text('trusted = ["/a"]\nuntrusted = ["/bad"]\n')
    assert vibe.trust(tmp_path, Path("/b")).startswith("trusted /b")
    assert lists(tmp_path) == {"trusted": ["/a", "/b"], "untrusted": ["/bad"]}
    assert db(tmp_path).read_text() == 'trusted = [\n    "/a",\n    "/b",\n]\nuntrusted = [\n    "/bad",\n]\n'


def test_an_untrusted_folder_stays_untrusted(tmp_path):
    before = 'trusted = []\nuntrusted = [\n    "/c",\n]\n'
    db(tmp_path).write_text(before)
    assert vibe.state(tmp_path, Path("/c")) == "untrusted"
    assert "marked untrusted" in vibe.trust(tmp_path, Path("/c"))
    assert db(tmp_path).read_text() == before


def test_a_file_it_does_not_know_is_left_alone(tmp_path):
    for text in ("trusted = [\n", 'trusted = "/a"\n', 'trusted = []\nother = 1\n', "trusted = [1]\n"):
        db(tmp_path).write_text(text)
        assert vibe.state(tmp_path, Path("/a")) == "unreadable"
        assert "left alone" in vibe.trust(tmp_path, Path("/a"))
        assert db(tmp_path).read_text() == text


def test_no_file_yet_and_missing_lists(tmp_path):
    assert vibe.state(tmp_path, Path("/a")) == "absent"
    vibe.trust(tmp_path, Path("/a"))
    assert lists(tmp_path) == {"trusted": ["/a"], "untrusted": []}
    db(tmp_path).write_text("untrusted = []\n")
    vibe.trust(tmp_path, Path("/b"))
    assert lists(tmp_path) == {"trusted": ["/b"], "untrusted": []}
    assert not (tmp_path / "trusted_folders.toml.tmp").exists()


# F-100: Vibe's desktop app starts every MCP server from its own app server: the server's cwd is the config's `cwd`
# (else the app server's own folder, never the session's), and its environment only the MCP SDK's safe variables
# (HOME, PATH, SHELL, TERM, USER, LOGNAME) plus the config's `env`. So a relative path never finds the server, and
# the server, without CRISSP_ROOT, never finds the project: the crissp tools did not load in a desktop session.
SAFE = ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
SERVER = REPO / "crissp" / "tool" / "server.py"


def start_like_vibe(text: str, elsewhere: Path) -> list[dict]:
    """Start the crissp server of a .vibe/config.toml the way Vibe's app server does, from another folder, and ask
    it what Vibe asks at the start of a session (initialize, tools/list) and then brief."""
    import json
    import os
    import subprocess

    server = next(s for s in tomllib.loads(text)["mcp_servers"] if s["name"] == "crissp")
    env = {k: os.environ[k] for k in SAFE if k in os.environ} | server.get("env", {})
    calls = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "brief", "arguments": {}}}]
    done = subprocess.run([server["command"], *server.get("args", [])], cwd=server.get("cwd") or elsewhere, env=env,
                          input="".join(json.dumps(c) + "\n" for c in calls), capture_output=True, text=True,
                          timeout=server.get("startup_timeout_sec", 10), check=False)
    return [json.loads(line) for line in done.stdout.splitlines() if line.strip()]


def listed(answers: list[dict]) -> set[str]:
    return {t["name"] for a in answers if a.get("id") == 2 for t in a["result"]["tools"]}


def test_a_relative_server_path_is_not_found_from_vibes_app_server(tmp_path):
    """F-100: the config crissp wrote before (a relative path, no cwd, no CRISSP_ROOT) gives a desktop session no
    tools: started from the app server's folder, python finds no crissp/tool/server.py."""
    old = '[[mcp_servers]]\nname = "crissp"\ntransport = "stdio"\ncommand = "python3"\n' \
          'args = ["-I", "crissp/tool/server.py"]\n'
    assert listed(start_like_vibe(old, tmp_path)) == set()


def test_the_config_crissp_writes_loads_the_tools_from_anywhere(tmp_path):
    """F-100: vibe.config pins the project's folder (cwd and CRISSP_ROOT) and gives the first uvx download time, so
    the server starts and answers for this project whatever folder Vibe starts it from."""
    text = vibe.config(REPO, sys.executable, ["-I", str(SERVER)])
    server = tomllib.loads(text)["mcp_servers"][0]
    assert server["cwd"] == str(REPO) and server["env"] == {"CRISSP_ROOT": str(REPO)}
    assert server["startup_timeout_sec"] >= 60
    answers = start_like_vibe(text, tmp_path)
    assert {"brief", "backlog", "finding", "item", "run", "status"} <= listed(answers)
    brief = next(a for a in answers if a.get("id") == 3)["result"]["content"][0]["text"]
    assert brief.startswith("crissp ") and "commit" in brief


def test_a_windows_path_stays_valid_toml_in_the_config():
    text = vibe.config(WIN, "C:\\Users\\x\\.local\\bin\\uvx.exe", ["crissp==1.2.3", "mcp"])
    server = tomllib.loads(text)["mcp_servers"][0]
    assert server["cwd"] == str(WIN) and server["command"].endswith("uvx.exe")
    assert server["args"] == ["crissp==1.2.3", "mcp"]
