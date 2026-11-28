"""E3-F3-01: what the orchestrator and its agents do now (lib/activity.py), read from Claude Code's transcripts of this
repository: the busy sessions, the main thread's current step and since when, every subagent running or finished with
its own latest step. Only what Claude sent to its tools, masked like the session pages; old sessions left out."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import activity  # noqa: E402
import sessionview as sv  # noqa: E402

T = "2026-11-24T10:{:02d}:00Z"
NOW = datetime.fromisoformat("2026-11-24T10:10:00+00:00").timestamp()


def use(name: str, given: dict, id_: str, minute: int, sidechain: bool = False, history: int = 0) -> dict:
    usage = {"input_tokens": 1000, "cache_read_input_tokens": history - 3000, "cache_creation_input_tokens": 2000}
    return {"type": "assistant", "timestamp": T.format(minute), "isSidechain": sidechain,
            "message": {"id": f"m{id_}", "content": [{"type": "tool_use", "id": id_, "name": name, "input": given}],
                        **({"usage": usage} if history else {})}}


def lines(path: Path, records: list[dict], mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + "not json\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def world(tmp_path: Path) -> tuple[Path, Path]:
    repo, projects = tmp_path / "repo", tmp_path / "projects"
    repo.mkdir()
    folder = sv.project_dir(repo, projects)
    busy = folder / "s1.jsonl"
    lines(busy, [
        {"type": "user", "timestamp": T.format(1), "cwd": str(repo), "message": {"content": "Build the board"}},
        {"type": "ai-title", "aiTitle": "The board moves"},
        use("Agent", {"description": "Write tests", "subagent_type": "general-purpose"}, "t1", 2, history=90_000),
        use("Agent", {"description": "Read docs", "subagent_type": "Explore"}, "t2", 3),
        use("Agent", {"description": "Just started", "subagent_type": "Plan"}, "t3", 7),
        {**use("Agent", {"description": "Last week", "subagent_type": "Explore"}, "t5", 0),
         "timestamp": "2026-11-17T10:00:00Z"},
        {"type": "user", "timestamp": T.format(4), "message": {"content": [{"type": "tool_result", "tool_use_id": "t5"}]}},
        {"type": "user", "timestamp": T.format(4), "message": {"content": [{"type": "tool_result", "tool_use_id": "t2"}]}},
        use("Bash", {"command": "make TOKEN=abc123secret", "description": ""}, "t4", 8, history=343_000),
    ], NOW - 30)
    agents = busy.with_suffix("") / "subagents"
    (agents / "agent-x.meta.json").parent.mkdir(parents=True)
    (agents / "agent-x.meta.json").write_text(json.dumps({"toolUseId": "t1", "description": "Write tests",
                                                          "agentType": "general-purpose", "finished": False}))
    lines(agents / "agent-x.jsonl", [use("Edit", {"file_path": str(repo / "a.py")}, "x1", 9, True),
                                     use("Agent", {"description": "Write tests"}, "t1", 9, True)],  # its own start: not a step
          NOW - 20)
    (agents / "agent-y.meta.json").write_text(json.dumps({"toolUseId": "t2", "finished": True}))
    lines(agents / "agent-y.jsonl", [use("Read", {"file_path": str(repo / "b.md")}, "y1", 3, True)], NOW - 400)
    (agents / "agent-z.meta.json").write_text("{broken")
    lines(folder / "old.jsonl", [{"type": "user", "timestamp": T.format(0), "message": {"content": "long ago"}}],
          NOW - 3 * 3600)
    return repo, projects


def test_the_busy_session_its_orchestrator_and_its_agents_now(tmp_path):
    repo, projects = world(tmp_path)
    found = activity.state(repo, projects, now=NOW, vibe_home=tmp_path / "no-vibe")
    assert found["now"] == NOW and [s["id"] for s in found["sessions"]] == ["s1"]  # the old session is left out
    s = found["sessions"][0]
    assert (s["title"], s["prompt"], s["busy"]) == ("The board moves", "Build the board", True)
    assert s["main"]["text"] == "make TOKEN=•••" and s["main"]["tool"] == "Bash" and s["main"]["since"] == T.format(8)
    agents = [(a["name"], a["type"], a["running"], a["text"]) for a in s["agents"]]
    assert agents == [("Write tests", "general-purpose", True, "a.py"), ("Just started", "Plan", True, ""),
                      ("Read docs", "Explore", False, "b.md")]  # running first, then finished
    assert s["agents"][0]["since"] == T.format(9) and s["agents"][2]["since"] == T.format(3)
    assert s["earlier"] == 1  # a finished agent's last step more than an hour ago: counted, not listed
    assert (s["history"], s["long"]) == (343_000, True)  # E4-F1-02: the last request's history, past 300k


def test_a_quiet_session_and_no_sessions_at_all(tmp_path):
    repo, projects = world(tmp_path)
    quiet = activity.state(repo, projects, now=NOW + 300, vibe_home=tmp_path / "no-vibe")["sessions"][0]
    assert quiet["busy"] is False  # nothing written for five minutes: still listed, no longer busy
    assert activity.state(repo, tmp_path / "nowhere", now=NOW, vibe_home=tmp_path / "no-vibe") == {"sessions": [], "now": NOW, "product": "repo",
                                                                    "monogram": "R"}  # no suites.json: the folder's name
    (repo / "crissp" / "testsuite").mkdir(parents=True)
    (repo / "crissp" / "testsuite" / "suites.json").write_text('{"product": "Shop", "monogram": "S", "steps": []}')
    assert activity.state(repo, projects, now=NOW, vibe_home=tmp_path / "no-vibe")["product"] == "Shop"


def test_a_session_whose_last_step_started_an_agent(tmp_path):
    repo, projects = tmp_path / "repo", tmp_path / "projects"
    repo.mkdir()
    lines(sv.project_dir(repo, projects) / "s2.jsonl",
          [use("Agent", {"description": "Review", "subagent_type": "general-purpose"}, "a1", 5, history=12_000)], NOW)
    s = activity.state(repo, projects, now=NOW, vibe_home=tmp_path / "no-vibe")["sessions"][0]
    assert s["main"] == {"tool": "Agent", "kind": "agent", "text": "started an agent: Review", "since": T.format(5)}
    assert s["title"] == "" and s["prompt"] == ""
    assert (s["history"], s["long"]) == (12_000, False)


def test_screenshots_and_whole_big_files_in_the_main_thread_are_flagged(tmp_path):
    """F-104 (F-18): the context-budget habits as checks. Images in the main thread (screenshots belong in a subagent
    that reports text) and big files read whole (offset/limit reads a part) are counted; past IMAGES images, or any
    whole read of a file past BIG_LINES lines, the session says so."""
    repo, projects = tmp_path / "repo", tmp_path / "projects"
    (repo / "big.py").parent.mkdir(parents=True)
    (repo / "big.py").write_text("x\n" * (activity.BIG_LINES + 1))
    (repo / "small.py").write_text("x\n")
    shot = {"type": "user", "timestamp": T.format(5), "message": {"content": [
        {"type": "tool_result", "tool_use_id": "s", "content": [{"type": "image", "source": {}}]}]}}
    lines(sv.project_dir(repo, projects) / "s.jsonl", [
        {"type": "user", "timestamp": T.format(1), "message": {"content": "check the page"}},
        *[shot] * activity.IMAGES,
        use("Read", {"file_path": str(repo / "big.py")}, "r1", 6),
        use("Read", {"file_path": str(repo / "big.py"), "offset": 1, "limit": 50}, "r2", 6),
        use("Read", {"file_path": str(repo / "small.py")}, "r3", 6),
        {**use("Read", {"file_path": str(repo / "big.py")}, "r4", 6, sidechain=True)},  # a subagent's: its own context
    ], NOW - 30)
    s = activity.state(repo, projects, now=NOW, vibe_home=tmp_path / "no-vibe")["sessions"][0]
    assert s["images"] == activity.IMAGES and s["whole"] == ["big.py"]
    assert activity.budget(s["images"] - 1, []) == [] and len(activity.budget(s["images"], ["big.py"])) == 2
