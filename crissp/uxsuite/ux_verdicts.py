"""The product owner's verdicts: on a piece of advice (agree · disagree · later) and on a design (approve · redo · reject).

Every verdict is one line appended to results/decisions.jsonl; a later line for the same item replaces an earlier one,
which stays in the file as history. What a verdict sets going:
- redo a design: the reason is the focus of the next design of that walk (started now, or queued)
- approve a design: it becomes a PBI in the backlog (ux_backlog), once
A disagreement, a redo and a rejection need a reason: that is what the team learns from.

Ids: advice "<walk>/r<round>/a<index>", a design "<walk>#v<version>".
"""

from __future__ import annotations

import json
import re

import ux_backlog
import ux_team
from ux_config import Suite

ADVICE = ("agree", "disagree", "later")
DESIGN = ("approve", "redo", "reject")
ADVICE_ID = re.compile(r"([a-z0-9][a-z0-9-]*)/r(\d+)/a(\d+)")
DESIGN_ID = re.compile(r"([a-z0-9][a-z0-9-]*)#v(\d+)")
NEEDS_A_REASON = {"disagree", "redo", "reject"}


def latest(suite: Suite) -> dict[str, dict]:
    """The verdict that holds per item."""
    return {d["id"]: d for d in ux_team.decisions(suite)}


def _result(suite: Suite, kind: str, walk: str, n: int):
    return next((v["result"] for v in ux_team.versions(suite, kind, walk) if v["version"] == n), None)


def record(suite: Suite, conf: dict, body: dict) -> dict:
    """Check one verdict and append it to the log; returns the stored line."""
    item, verdict = str(body.get("id") or ""), body.get("verdict")
    reason = str(body.get("reason") or "").strip()
    if len(reason) > 4000:
        raise ValueError("the reason is too long (at most 4000 characters)")
    if (m := ADVICE_ID.fullmatch(item)):
        found = _result(suite, "round", m.group(1), int(m.group(2))) if m.group(1) in conf["walks"] else None
        advice = (found or {}).get("advice", [])
        if int(m.group(3)) >= len(advice):
            raise ValueError("unknown advice")
        if verdict not in ADVICE:
            raise ValueError("a verdict on advice is agree, disagree or later")
        level, title = "advice", advice[int(m.group(3))].get("title", "")
    elif (m := DESIGN_ID.fullmatch(item)):
        found = _result(suite, "proposal", m.group(1), int(m.group(2))) if m.group(1) in conf["walks"] else None
        if not found:
            raise ValueError("unknown design")
        if verdict not in DESIGN:
            raise ValueError("a verdict on a design is approve, redo or reject")
        level, title = "design", found.get("title", "")
    else:
        raise ValueError("unknown item")
    if verdict in NEEDS_A_REASON and not reason:
        raise ValueError("say why (for a redo: what the team should do differently)")
    line = {"id": item, "level": level, "verdict": verdict, "reason": reason, "title": str(title)[:300], "at": ux_team.now()}
    suite.results.mkdir(parents=True, exist_ok=True)
    with (suite.results / "decisions.jsonl").open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def after(suite: Suite, conf: dict, line: dict) -> dict:
    """What the verdict sets going: a PBI for an approved design, the next design for a redo; {} for the rest."""
    if line["level"] != "design" or line["verdict"] == "reject":
        return {}
    walk, _, n = line["id"].partition("#v")
    if line["verdict"] == "approve":
        return {"pbi": ux_backlog.file_pbi(suite, conf, walk, int(n), _result(suite, "proposal", walk, int(n)), remark=line["reason"])}
    try:
        return ux_team.request(suite, conf, "proposal", walk, line["reason"])
    except ValueError as why:  # the team works on it already, or the walk lost its screenshots: the verdict stands
        return {"not_started": str(why)}
