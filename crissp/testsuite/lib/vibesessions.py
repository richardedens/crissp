"""What Mistral Vibe's sessions in this repository do now (F-101): the Activity page's second source, next to Claude
Code's transcripts (lib/activity.py).

Vibe keeps every session under VIBE_HOME (else ~/.vibe) in logs/session/unified/<session id>/: meta.json (its folder,
title, parent session, end time), a journal (journal/*.jsonl: what went into the model and what came back) and
context-breakdown.json (the size of its context now). This reads, for the sessions of this repository written in the
last half hour (a subagent is a session whose meta.json names its parent):

- the title and the last prompt;
- the main thread's latest step (Vibe's tool, the path or the command, masked) and since when; busy while the session
  wrote something in the last two minutes;
- the history its last request carried (the model's input tokens, else the context breakdown) and whether it is past
  300k tokens (measure.LONG): then it is time for a fresh session;
- its subagents, running until their meta.json has an end time, each with its own latest step;
- F-104: the images in its main context and the big files it read whole, said past measure's lines.

Only what Vibe sent to its tools is shown, never what came back.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import measure
import sessionview as sv

WINDOW_S = 30 * 60  # as the Activity page: a session written longer ago than this is not activity any more
QUIET_S = 120
KIND = {"read_file": "read", "grep": "read", "glob": "read", "list_dir": "read", "search_tool_functions": "read",
        "write_file": "change", "edit": "change", "search_replace": "change", "bash": "run",
        "ask_user_question": "ask", "task": "agent"}


def folder(home: Path) -> Path:
    return home / "logs" / "session" / "unified"


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def journal(session: Path) -> list[dict]:
    return [r for p in sorted((session / "journal").glob("*.jsonl")) for r in sv.records(p)]


def updated(session: Path) -> float:
    return max(p.stat().st_mtime for p in (session / "meta.json", *(session / "journal").glob("*.jsonl")))


def belongs(meta: dict, root: Path) -> bool:
    """A session of this repository: its repository root or its working directory is the repository or inside it."""
    for where in (meta.get("repository_root"), (meta.get("environment") or {}).get("working_directory")):
        if where and (Path(where) == root or root in Path(where).parents):
            return True
    return False


def step(name: str, args: dict, repo: sv.Repo, since: str | None) -> dict:
    """One of Vibe's tool calls as the Activity page shows a step: its kind and what it was about."""
    kind = KIND.get(name, "other")
    if kind in ("read", "change") and (args.get("path") or args.get("file_path")):
        where = args.get("path") or args.get("file_path")
        text = repo.rel(where) or where
    elif kind == "run":
        text = sv.mask((args.get("command", "").splitlines() or [""])[0][:120])
    elif kind == "agent":
        text = f"started an agent: {args.get('description') or args.get('task', '')[:120]}"
    else:
        text = name
    return {"tool": name, "kind": kind, "text": text, "since": since}


def _when(millis: int | None) -> str | None:
    return datetime.fromtimestamp(millis / 1000, UTC).isoformat() if millis else None


def read(session: Path, repo: sv.Repo) -> dict:
    """The prompts, the latest step and the last request's input tokens of one session's journal."""
    prompts, latest, history, millis, pictures, wholes = [], None, 0, None, 0, []
    for r in journal(session):
        payload = r.get("payload") or {}
        if r.get("type") == "core_input":
            given = payload.get("input") or {}
            pictures += measure.images(given)  # F-104: what went into the model
            millis = (given.get("determinism") or {}).get("time_unix_ms") or millis
            command = given.get("command") or {}
            if command.get("type") == "user_message":
                prompts.append(" ".join(c.get("text", "") for c in command.get("content", []) if c.get("type") == "text"))
        elif r.get("type") == "action_result":
            result = (payload.get("result") or {}).get("result") or {}
            history = (result.get("usage") or {}).get("input_tokens", history)
            for part in result.get("parts", []):
                if part.get("type") == "tool_call":
                    args = _json_args(part.get("arguments_json"))
                    latest = step(part.get("name", ""), args, repo, _when(millis))
                    if part.get("name") == "read_file" and (w := measure.whole(repo.rel(args.get("path", "")), args,
                                                                               repo.root)):
                        wholes.append(w)
    if not history:
        breakdown = _json(session / "context-breakdown.json") or {}
        history = sum(v for v in breakdown.values() if isinstance(v, int))
    return {"prompts": prompts, "main": latest, "history": history, "images": pictures, "whole": sorted(set(wholes))}


def _json_args(text: str | None) -> dict:
    try:
        given = json.loads(text or "{}")
    except ValueError:
        given = {}
    return given if isinstance(given, dict) else {}


def sessions(root: Path, home: Path, now: float) -> list[dict]:
    """This repository's Vibe sessions written in the last half hour, in the Activity page's shape."""
    base = folder(home)
    metas = {d: m for d in (sorted(base.iterdir()) if base.is_dir() else [])
             if isinstance(m := _json(d / "meta.json"), dict)}
    repo = sv.Repo(root)
    out = []
    for d, meta in metas.items():
        if meta.get("parent_session_id") or not belongs(meta, root) or now - updated(d) > WINDOW_S:
            continue
        seen = read(d, repo)
        agents = []
        for child, cm in metas.items():
            if cm.get("parent_session_id") == meta.get("session_id"):
                agents.append({"name": cm.get("title") or "agent", "type": cm.get("agent") or "subagent",
                               "running": not cm.get("end_time"),
                               **(read(child, repo)["main"] or {"tool": "", "kind": "", "text": "", "since": None})})
        agents.sort(key=lambda a: not a["running"])
        last = updated(d)
        out.append({"id": meta.get("session_id") or d.name, "source": "vibe", "title": sv.mask(meta.get("title") or ""),
                    "history": seen["history"], "long": seen["history"] > measure.LONG,
                    "prompt": sv.mask(seen["prompts"][-1][:300]) if seen["prompts"] else "", "busy": now - last < QUIET_S,
                    "updated": last, "main": seen["main"], "agents": agents, "earlier": 0, "images": seen["images"],
                    "whole": seen["whole"], "budget": measure.budget(seen["images"], seen["whole"])})
    return out
