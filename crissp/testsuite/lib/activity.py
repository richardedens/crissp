"""What the orchestrator and its agents do now (E3-F3-01): the Activity page's data (/dashboard/activity.json).

From Claude Code's transcripts of this repository (~/.claude/projects/<repository path>/, read the way the session pages
read them, lib/sessionview.py), the sessions written in the last half hour, newest first. Per session:

- its title and the last prompt;
- the orchestrator (the main thread): its latest step (the tool, and the path, the command's description or the command
  itself, masked) and since when; busy while the session wrote something in the last two minutes;
- the history its last request carried (as the sessions report measures it, measure.history) and whether it is past
  300k tokens (measure.LONG): then it is time for a fresh session (E4-F1-02);
- every subagent it started: its type and description, running or finished (the subagent's own record says so; without
  one, a result means finished), and its own latest step and since when. Running agents first; agents that finished
  more than an hour ago are only counted ("earlier").

Only what Claude sent to its tools is shown, never what came back.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import measure
import project
import sessionview as sv

WINDOW_S = 30 * 60  # a session written longer ago than this is not activity any more
QUIET_S = 120  # nothing written for this long: listed, no longer busy
FINISHED_S = 60 * 60  # a finished agent whose last step is older than this is counted, not listed


def _step(record: dict, block: dict, repo: sv.Repo) -> dict:
    if block.get("name") == "Agent":
        given = block.get("input") or {}
        return {"tool": "Agent", "kind": "agent", "text": f"started an agent: {given.get('description', '')}",
                "since": record.get("timestamp")}
    act = sv.action(block, repo, record.get("cwd"))
    return {"tool": block.get("name", ""), "kind": act["kind"], "text": act["text"], "since": record.get("timestamp")}


def _latest(records: list[dict], repo: sv.Repo, skip: str | None = None) -> dict | None:
    for r in reversed(records):
        for b in reversed(sv.tool_uses(r)):
            if b.get("id") != skip:
                return _step(r, b, repo)
    return None


def _subagents(path: Path) -> dict[str, tuple[dict, Path]]:
    """The subagents' own records, by the id of the tool call that started each."""
    out = {}
    for meta in sorted((path.with_suffix("") / "subagents").glob("*.meta.json")):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out[info.get("toolUseId", "")] = (info, meta.with_name(meta.name.removesuffix(".meta.json") + ".jsonl"))
    return out


def session(path: Path, root: Path, now: float) -> dict:
    repo = sv.Repo(root, sv.session_root(path))
    records = list(sv.records(path))
    main = [r for r in records if not r.get("isSidechain")]
    prompts = [p for r in main if (p := sv.prompt(r)) and not p.startswith("<task-notification>")]
    titles = [r["aiTitle"] for r in records if r.get("type") == "ai-title" and r.get("aiTitle")]
    answered = {b.get("tool_use_id") for r in main for b in ((r.get("message") or {}).get("content") or [])
                if isinstance(b, dict) and b.get("type") == "tool_result"}
    own = _subagents(path)
    updated = path.stat().st_mtime
    agents = []
    for r in main:
        for b in sv.tool_uses(r):
            if b.get("name") != "Agent":
                continue
            given = b.get("input") or {}
            info, transcript = own.get(b.get("id"), ({}, None))
            mine = list(sv.records(transcript)) if transcript and transcript.is_file() else []
            if mine:
                updated = max(updated, transcript.stat().st_mtime)
            step = _latest(mine, repo, skip=b.get("id")) or {"tool": "", "kind": "", "text": "", "since": r.get("timestamp")}
            running = not info["finished"] if "finished" in info else b.get("id") not in answered
            agents.append({"name": info.get("description") or given.get("description", "agent"),
                           "type": info.get("agentType") or given.get("subagent_type", "agent"), "running": running,
                           **step})
    old = [a for a in agents if not a["running"] and a["since"]
           and now - datetime.fromisoformat(a["since"]).timestamp() > FINISHED_S]
    agents = sorted((a for a in agents if a not in old), key=lambda a: not a["running"])
    sized = [r for r in main if r.get("type") == "assistant" and (r.get("message") or {}).get("usage")]
    history = measure.history(sized[-1]) if sized else 0
    return {"id": path.stem, "title": sv.mask(titles[-1]) if titles else "", "history": history,
            "long": history > measure.LONG,
            "prompt": sv.mask(prompts[-1][:300]) if prompts else "", "busy": now - updated < QUIET_S,
            "updated": updated, "main": _latest(main, repo), "agents": agents, "earlier": len(old)}


def state(root: Path, projects: Path = sv.PROJECTS, now: float | None = None) -> dict:
    """The sessions of this repository written in the last half hour, newest first, as the Activity page shows them."""
    now = time.time() if now is None else now
    folder = sv.project_dir(root, projects)
    recent = [p for p in folder.glob("*.jsonl") if now - p.stat().st_mtime <= WINDOW_S] if folder.is_dir() else []
    found = [session(p, root, now) for p in recent]
    try:
        conf = project.load(root)
    except project.ConfigError:
        conf = {"product": root.name, "monogram": root.name[:1].upper()}
    return {"sessions": sorted(found, key=lambda s: s["updated"], reverse=True), "now": now, "product": conf["product"],
            "monogram": conf["monogram"]}
