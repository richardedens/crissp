"""E3-F2-01: every PBI's moves on the board, from the backlog's git history and the working tree (lib/movement.py), read
with the crissp tool's own parser: from where to where, when, in which commit or not committed yet."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENGINE / "testsuite" / "lib"))
import movement  # noqa: E402

spec = importlib.util.spec_from_file_location("crissp_tool_for_moves", ENGINE / "tool" / "server.py")
TOOL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TOOL)

EPIC = "# E1 · Board\n\nWhy: w\n\n## E1-F1 · Moves   [doing]\nWhy        y\n\n{items}"
PBI = "### E1-F1-0{n} · Thing {n}   [{s}] [S]\nWhy        z\n\n"


def git(repo: Path, *args: str, when: str | None = None) -> None:
    env = {**os.environ, **({"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when} if when else {})}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env=env)


def epic(repo: Path, *states: str, encoding: str = "utf-8") -> None:
    path = repo / "crissp" / "backlog" / "E1-board.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(EPIC.format(items="".join(PBI.format(n=i + 1, s=s) for i, s in enumerate(states))).encode(encoding))


def commit(repo: Path, msg: str, when: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg, when=when)


def test_every_move_from_where_to_where_when_and_in_which_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    assert movement.moves(repo, TOOL) == {}  # no commit yet, no backlog yet
    epic(repo, "todo")
    commit(repo, "E1: written", "2026-11-20T09:00:00+00:00")
    epic(repo, "doing")
    (repo / "notes.txt").write_text("not the backlog")
    (repo / "crissp" / "backlog" / "FINDINGS.md").write_text("### E1-F1-09 · Not a PBI   [done]\n")  # not an epic file
    commit(repo, "E1-F1-01: started", "2026-11-21T09:00:00+00:00")
    epic(repo, "review", "todo", encoding="cp1252")  # saved on Windows: the · is 0xb7 (F-16), still read
    commit(repo, "E1-F1-01: built; E1-F1-02 written", "2026-11-22T09:00:00+00:00")
    commit_ids = subprocess.run(["git", "-C", str(repo), "log", "--reverse", "--format=%h"], capture_output=True,
                                text=True, check=False).stdout.split()
    epic(repo, "doing", "todo")  # sent back, not committed yet
    found = movement.moves(repo, TOOL)
    one = [(m["from"], m["to"], m["at"][:10], m["commit"]) for m in found["E1-F1-01"]]
    assert one == [(None, "todo", "2026-11-20", commit_ids[0]), ("todo", "doing", "2026-11-21", commit_ids[1]),
                   ("doing", "review", "2026-11-22", commit_ids[2]), ("review", "doing", one[3][2], None)]
    assert found["E1-F1-01"][1]["subject"] == "E1-F1-01: started" and found["E1-F1-01"][3]["subject"] == ""
    assert [(m["from"], m["to"]) for m in found["E1-F1-02"]] == [(None, "todo")]  # new → todo, and no move since
    assert "E1-F1-09" not in found


def test_a_pbi_that_moves_to_the_done_folder_is_one_move_not_a_new_pbi(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    epic(repo, "review")
    commit(repo, "E1: written", "2026-11-20T09:00:00+00:00")
    done = repo / "crissp" / "backlog" / "done"
    done.mkdir()
    (repo / "crissp" / "backlog" / "E1-board.md").rename(done / "E1-board.md")
    text = (done / "E1-board.md").read_text(encoding="utf-8").replace("[review]", "[done]")
    (done / "E1-board.md").write_text(text, encoding="utf-8")
    commit(repo, "E1 accepted", "2026-11-23T09:00:00+00:00")
    assert [(m["from"], m["to"]) for m in movement.moves(repo, TOOL)["E1-F1-01"]] == [(None, "review"), ("review", "done")]


def test_recent_moves_newest_first_with_the_pbi_s_title():
    found = {"E1-F1-01": [{"from": None, "to": "todo", "at": "2026-11-20T09:00:00+00:00", "commit": "a", "subject": "s"},
                          {"from": "todo", "to": "review", "at": "2026-11-22T09:00:00+00:00", "commit": None, "subject": ""}],
             "E1-F1-02": [{"from": None, "to": "todo", "at": "2026-11-21T09:00:00+00:00", "commit": "b", "subject": "t"}]}
    recent = movement.recent(found, {"E1-F1-01": "One", "E1-F1-02": "Two"}, limit=2)
    assert [(r["id"], r["title"], r["to"]) for r in recent] == [("E1-F1-01", "One", "review"), ("E1-F1-02", "Two", "todo")]
