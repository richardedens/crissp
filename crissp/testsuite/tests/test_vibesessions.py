"""F-101: the Activity page reads Mistral Vibe's sessions of this repository too (lib/vibesessions.py), from Vibe's own
session folders (VIBE_HOME/logs/session/unified/<id>/: meta.json and the journal), in the shape Vibe 3.1 writes:
the busy session, its last prompt, its latest step and since when, its subagents, and the history its last request
carried, with the 300k-token "start fresh" warning. Only what Vibe sent to its tools, masked like the session pages."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import activity  # noqa: E402
import vibesessions as vs  # noqa: E402

NOW = datetime.fromisoformat("2026-11-28T10:10:00+00:00").timestamp()


def ms(minute: int) -> int:
    return int(datetime.fromisoformat(f"2026-11-28T10:{minute:02d}:00+00:00").timestamp() * 1000)


def said(text: str, minute: int, images: int = 0) -> dict:
    content = [{"type": "text", "text": text}] + [{"type": "image", "data": "..."}] * images
    return {"type": "core_input", "payload": {"input": {"command": {"type": "user_message", "content": content},
                                                        "determinism": {"time_unix_ms": ms(minute)}}}}


def called(name: str, args: dict, history: int = 0) -> dict:
    result = {"parts": [{"type": "text", "text": "thinking"},
                        {"type": "tool_call", "id": "c", "name": name, "arguments_json": json.dumps(args)}]}
    if history:
        result["usage"] = {"input_tokens": history, "cached_input_tokens": history - 10, "output_tokens": 5}
    return {"type": "action_result", "payload": {"result": {"result": result}}}


def session(home: Path, sid: str, repo: Path, journal: list[dict], mtime: float, **meta) -> Path:
    folder = home / "logs" / "session" / "unified" / sid
    (folder / "journal").mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"session_id": sid, "environment": {"working_directory": str(repo)},
                                                  "repository_root": str(repo), "title": None, "end_time": None,
                                                  **meta}))
    path = folder / "journal" / "0000000000000001.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in journal) + "not json\n")
    for p in (path, folder / "meta.json"):
        os.utime(p, (mtime, mtime))
    return folder


def world(tmp_path: Path) -> tuple[Path, Path]:
    repo, home = tmp_path / "repo", tmp_path / "vibe-home"
    repo.mkdir()
    session(home, "v1", repo, [
        said("Make crissp Vibe compliant", 1),
        called("read_file", {"path": str(repo / "crissp" / "CLAUDE.md")}),
        said("and the activity page", 2),
        called("bash", {"command": "make TOKEN=abc123secret\nmore"}, history=343_000),
    ], NOW - 30, title="Vibe compliance")
    session(home, "v1-child", repo, [called("grep", {"pattern": "vibe", "path": str(repo)})], NOW - 20,
            parent_session_id="v1", title="Search the code", agent="explore")
    session(home, "v1-done", repo, [called("read_file", {"path": "x"})], NOW - 300, parent_session_id="v1",
            end_time="2026-11-28T10:05:00+00:00")
    session(home, "elsewhere", tmp_path / "other", [said("not this repo", 3)], NOW - 10)
    session(home, "old", repo, [said("long ago", 0)], NOW - 3 * 3600)
    (home / "logs" / "session" / "unified" / "broken").mkdir()
    (home / "logs" / "session" / "unified" / "broken" / "meta.json").write_text("{broken")
    return repo, home


def test_a_busy_vibe_session_with_its_prompt_step_agents_and_long_history(tmp_path):
    repo, home = world(tmp_path)
    found = vs.sessions(repo, home, NOW)
    assert [s["id"] for s in found] == ["v1"]  # the others: another repository, too old, a subagent, unreadable
    s = found[0]
    assert s["source"] == "vibe" and s["title"] == "Vibe compliance" and s["prompt"] == "and the activity page"
    assert s["busy"] and s["history"] == 343_000 and s["long"]
    assert s["main"]["kind"] == "run" and "abc123secret" not in s["main"]["text"] and s["main"]["text"].startswith("make")
    assert s["main"]["since"] == "2026-11-28T10:02:00+00:00"
    assert [(a["name"], a["type"], a["running"], a["kind"]) for a in s["agents"]] == [
        ("Search the code", "explore", True, "read"), ("agent", "subagent", False, "read")]


def test_the_activity_page_lists_vibe_sessions_next_to_claudes(tmp_path):
    repo, home = world(tmp_path)
    state = activity.state(repo, tmp_path / "no-claude", NOW, vibe_home=home)
    assert [(s["id"], s["source"]) for s in state["sessions"]] == [("v1", "vibe")]
    assert activity.state(repo, tmp_path / "no-claude", NOW, vibe_home=tmp_path / "no-vibe")["sessions"] == []


def test_a_session_without_a_journal_or_usage_still_shows(tmp_path):
    repo, home = tmp_path / "repo", tmp_path / "vibe-home"
    folder = session(home, "v2", repo, [], NOW - 5)
    (folder / "context-breakdown.json").write_text(json.dumps({"system": 20_000, "tools": 14_000, "conversation": 2}))
    s = vs.sessions(repo, home, NOW)[0]
    assert s["history"] == 34_002 and not s["long"] and s["main"] is None and s["prompt"] == ""
    assert s["title"] == "" and s["agents"] == []
    for name, args, kind in (("write_file", {"path": str(repo / "a.py")}, "change"), ("task", {"task": "look"}, "agent"),
                             ("ask_user_question", {}, "ask"), ("web_fetch", {}, "other")):
        assert vs.step(name, args, vs.sv.Repo(repo), None)["kind"] == kind
    assert vs.step("edit", {"file_path": str(repo / "b.py")}, vs.sv.Repo(repo), None)["text"] == "b.py"


def test_a_vibe_sessions_images_and_whole_big_reads_are_counted(tmp_path):
    """F-104: the same context-budget checks for a Vibe session: images it put into its main context, big files read
    whole (read_file without offset or limit)."""
    repo, home = tmp_path / "repo", tmp_path / "vibe-home"
    repo.mkdir()
    (repo / "big.py").write_text("x\n" * (activity.BIG_LINES + 1))
    session(home, "v3", repo, [said("look", 1, images=activity.IMAGES),
                               called("read_file", {"path": str(repo / "big.py")}),
                               called("read_file", {"path": str(repo / "big.py"), "offset": 10, "limit": 20}),
                               called("read_file", {"path": str(tmp_path / "outside.py")})], NOW - 5)
    s = vs.sessions(repo, home, NOW)[0]
    assert s["images"] == activity.IMAGES and s["whole"] == ["big.py"]
