"""The product owner's verdicts: on a piece of advice (agree · disagree · later), on a design (approve · redo · reject) and
on a need a discovery round found (approve · reject), and on what was built from an approved design (accept ·
send-back).

Every verdict is one line appended to results/decisions.jsonl; a later line for the same item replaces an earlier one,
which stays in the file as history. What a verdict sets going:
- redo a design: the reason is the focus of the next design of that walk (started now, or queued)
- approve a design: it becomes a PBI in the backlog (ux_backlog), once
- approve a need: it becomes a design request, a walk with a brief, whose first design starts (ux_discovery)
- accept what was built (judged on the walk shot after the approval): its PBI moves to review, for the product owner
- send it back: its PBI moves to doing, and the reason becomes a finding that goes to it
A disagreement, a redo and a rejection need a reason: that is what the team learns from.

A verdict on a rule, an area or a screen ("rule/<id>", "area/<area>", "screen/<walk>": agree · disagree · later) holds
for its advice that has none of its own (ux_review.held); a proposed rule ("proposed/<theme>": approve · reject),
approved, becomes a rule file.

Ids: advice "<walk>/r<round>/a<index>", a design "<walk>#v<version>", a need "product/d<round>/n<index>", what was built "<walk>#v<version>/built".
"""

from __future__ import annotations

import json
import re

import ux_backlog
import ux_cards
import ux_discovery
import ux_review
import ux_team
from ux_config import Suite, speak

ADVICE = ("agree", "disagree", "later")
DESIGN = ("approve", "redo", "reject")
ADVICE_ID = re.compile(r"([a-z0-9][a-z0-9-]*)/r(\d+)/a(\d+)")
DESIGN_ID = re.compile(r"([a-z0-9][a-z0-9-]*)#v(\d+)")
NEED = ("approve", "reject")
BUILT = ("accept", "send-back")
BUILT_ID = re.compile(r"([a-z0-9][a-z0-9-]*)#v(\d+)/built")
NEED_ID = re.compile(rf"{ux_team.PRODUCT}/d(\d+)/n(\d+)")
TREE_ID = re.compile(r"(rule|area|screen)/([a-z0-9][a-z0-9-]*)")
PROPOSED_ID = re.compile(r"proposed/([a-z0-9][a-z0-9-]*)")
PROPOSED = ("approve", "reject")
NEEDS_A_REASON = {"disagree", "redo", "reject", "send-back"}


def latest(suite: Suite) -> dict[str, dict]:
    """The verdict that holds per item."""
    return {d["id"]: d for d in ux_team.decisions(suite)}


def _result(suite: Suite, kind: str, walk: str, n: int):
    return next((v["result"] for v in ux_team.versions(suite, kind, walk) if v["version"] == n), None)


def _built(suite: Suite, conf: dict, walk: str, n: int, verdict) -> str:
    """Check a verdict on what was built from a design; the design's title."""
    found = _result(suite, "proposal", walk, n) if walk in conf["walks"] else None
    if not found:
        raise ValueError("unknown design")
    if verdict not in BUILT:
        raise ValueError("a verdict on a built design is accept or send-back")
    held = latest(suite).get(f"{walk}#v{n}")
    if not held or held["verdict"] != "approve":
        raise ValueError("only an approved design is built and accepted")
    shot = ux_team.shot_at(suite, walk)
    if not shot or shot <= held["at"]:
        raise ValueError(speak(f"shoot the walk again once it is built: crissp/ux.sh --shoot {walk}"))
    return found.get("title", "")


def _node(suite: Suite, conf: dict, level: str, key: str) -> str:
    """A rule, an area or a screen a verdict holds for, by its title."""
    if level == "rule":
        names = {r["id"]: r["title"] for r in ux_cards.rules(suite)}
    elif level == "area":
        names = {ux_review.area_of(w): ux_review.area_of(w) for w in conf["walks"].values()}
    else:
        names = {w["id"]: w["title"] for w in conf["walks"].values()}
    if key not in names:
        raise ValueError(f"unknown {level}")
    return names[key]


def _proposed(suite: Suite, conf: dict) -> list[dict]:
    return ux_review.proposed(suite, conf, latest(suite), ux_cards.rules(suite))


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
    elif (m := BUILT_ID.fullmatch(item)):
        level, title = "built", _built(suite, conf, m.group(1), int(m.group(2)), verdict)
    elif (m := NEED_ID.fullmatch(item)):
        needs = (_result(suite, "discovery", ux_team.PRODUCT, int(m.group(1))) or {}).get("needs", [])
        if int(m.group(2)) >= len(needs):
            raise ValueError("unknown need")
        if verdict not in NEED:
            raise ValueError("a verdict on a need is approve or reject")
        level, title = "need", needs[int(m.group(2))].get("title", "")
    elif (m := DESIGN_ID.fullmatch(item)):
        found = _result(suite, "proposal", m.group(1), int(m.group(2))) if m.group(1) in conf["walks"] else None
        if not found:
            raise ValueError("unknown design")
        if verdict not in DESIGN:
            raise ValueError("a verdict on a design is approve, redo or reject")
        level, title = "design", found.get("title", "")
    elif (m := TREE_ID.fullmatch(item)):
        level, title = m.group(1), _node(suite, conf, m.group(1), m.group(2))
        if verdict not in ADVICE:
            raise ValueError("a verdict on a rule, an area or a screen is agree, disagree or later")
    elif PROPOSED_ID.fullmatch(item):
        found = next((p for p in _proposed(suite, conf) if p["id"] == item), None)
        if not found:
            raise ValueError("unknown proposal")
        if verdict not in PROPOSED:
            raise ValueError("a verdict on a proposed rule is approve or reject")
        level, title = "proposed", found["title"]
    else:
        raise ValueError("unknown item")
    if verdict in NEEDS_A_REASON and not reason:
        raise ValueError("say why (for a redo: what the team should do differently)")
    line = {"id": item, "level": level, "verdict": verdict, "reason": reason, "title": str(title)[:300], "at": ux_team.now()}
    suite.results.mkdir(parents=True, exist_ok=True)
    with (suite.results / "decisions.jsonl").open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def _move(suite: Suite, line: dict) -> dict:
    """Accept moves the design's PBI to review; send-back moves it to doing and files the reason as a finding for it."""
    key = line["id"].removesuffix("/built")
    crissp = ux_backlog.tool(suite)
    pbi = ux_backlog.pbis(suite, crissp).get(key)
    if not pbi:
        return {"not_moved": f"{key} has no PBI in the backlog"}
    try:
        moved = crissp.item(suite.root, {"id": pbi, "status": "review" if line["verdict"] == "accept" else "doing"})
    except (ValueError, LookupError) as why:  # done already, or the backlog changed: the verdict stands
        return {"pbi": pbi, "not_moved": str(why)}
    out = {"pbi": pbi, "moved": moved}
    if line["verdict"] == "send-back":
        said = crissp.finding(suite.root, {"seen": f"UX suite, built design {key} ({pbi})",
                                           "observation": ux_backlog._flat(line["reason"]), "goes_to": pbi})
        out["finding"] = said.split()[0]
    return out


def after(suite: Suite, conf: dict, line: dict) -> dict:
    """What the verdict sets going: a PBI for an approved design, the next design for a redo, a design request for an
    approved need; {} for the rest."""
    if line["level"] == "built":
        return _move(suite, line)
    if line["level"] == "proposed":
        if line["verdict"] != "approve":
            return {}
        p = next(p for p in _proposed(suite, conf) if p["id"] == line["id"])
        rid = line["id"].split("/", 1)[1]
        ux_cards.save_rule(suite, {"id": rid, "title": p["title"], "severity": p["severity"], "text": p["text"]})
        return {"rule": rid}
    if line["verdict"] == "reject" or line["level"] not in ("design", "need"):
        return {}
    if line["level"] == "need":
        m = NEED_ID.fullmatch(line["id"])
        need = _result(suite, "discovery", ux_team.PRODUCT, int(m.group(1)))["needs"][int(m.group(2))]
        return ux_discovery.approved(suite, conf, line["id"], need)
    walk, _, n = line["id"].partition("#v")
    if line["verdict"] == "approve":
        return {"pbi": ux_backlog.file_pbi(suite, conf, walk, int(n), _result(suite, "proposal", walk, int(n)), remark=line["reason"])}
    try:
        return ux_team.request(suite, conf, "proposal", walk, line["reason"])
    except ValueError as why:  # the team works on it already, or the walk lost its screenshots: the verdict stands
        return {"not_started": str(why)}
