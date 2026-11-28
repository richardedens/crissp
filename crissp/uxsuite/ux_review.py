"""The review screen (E7-F4-01): where every screen stands, from new to accepted, and what it waits for.

Decide once (E7-F4-02): a verdict on a rule ("rule/<id>"), an area ("area/<area>") or a screen ("screen/<walk>") holds
for every piece of advice under it that has no verdict of its own, the nearest one first (screen, area, rule). Advice the
product owner agreed with that comes back on several screens under the same theme (or title) is proposed as a rule
("proposed/<theme>"); approved, it becomes a rule file.

A screen is a walk's screen: what its shots show, the team's advice on it, its designs and what was built from them. Its
status is the furthest step it reached:

    new · seen (shot) · discussed (a round) · decided (every piece of the last round's advice has a verdict)
    · designed · approved · built (shot again after the approval) · accepted

and it waits for the product owner ("you": advice to decide, a design to judge, a build to accept), for the team (a
round, a design, a build, a shoot) or for nobody (accepted). The page goes through the screens that wait for the product
owner first, the must-advice first, one verdict at a time.
"""

from __future__ import annotations

import re

import ux_map
import ux_team

STEPS = ("new", "seen", "discussed", "decided", "designed", "approved", "built", "accepted")
PRIORITY = {"must": 0, "should": 1, "could": 2}


def _done(versions: list[dict]) -> list[dict]:
    return [v for v in versions if v.get("result")]


def _running(versions: list[dict]) -> str | None:
    last = versions[-1] if versions else None
    if last and not last.get("result") and (last.get("status") or {}).get("phase") not in ("done", "failed"):
        return (last.get("status") or {}).get("phase") or "queued"
    return None


def area_of(walk: dict) -> str:
    """The area of a walk's screen: that of its first page."""
    first = next((s["path"] for s in walk["steps"] if s["do"] == "goto"), "/")
    return ux_map.area(ux_map.screen_key(first))


def open_advice(w: dict, verdicts: dict) -> list[tuple[int, str]]:
    """The advice of the walk's last round that has no verdict yet, must first: (priority, id)."""
    rounds = _done(w["rounds"])
    if not rounds:
        return []
    last = rounds[-1]
    advice = last["result"].get("advice") or []
    return sorted(
        (PRIORITY.get(a.get("priority"), 3), f"{w['id']}/r{last['version']}/a{i}")
        for i, a in enumerate(advice)
        if f"{w['id']}/r{last['version']}/a{i}" not in verdicts
    )


def screen(walk: dict, w: dict, verdicts: dict) -> dict:
    """One screen's status, whose turn it is and what comes next. `w` is the walk as the page's state has it."""
    rounds, designs = _done(w["rounds"]), _done(w["proposals"])
    held = open_advice(w, verdicts)
    pending = [i for _, i in held]
    approved = next((p for p in reversed(designs) if (p.get("verdict") or {}).get("verdict") == "approve"), None)
    rebuilt = bool(approved and w["shot_at"] and w["shot_at"] > approved["verdict"]["at"])
    built = (approved or {}).get("built") or {}
    reached = {
        "seen": any(s["path"] for s in w["shots"]) or bool(rounds),
        "discussed": bool(rounds),
        "decided": bool(rounds) and not pending,
        "designed": bool(designs),
        "approved": bool(approved),
        "built": rebuilt,
        "accepted": rebuilt and built.get("verdict") == "accept",
    }
    status = next((s for s in reversed(STEPS[1:]) if reached[s]), "new")
    design = approved or (designs[-1] if designs else None)
    waits, said = _next(walk, w, reached, pending, designs, built)
    return {
        "walk": w["id"],
        "title": w["title"],
        "area": area_of(walk),
        "status": status,
        "step": STEPS.index(status),
        "waits": waits,
        "next": said,
        "open": pending,
        "must": sum(1 for p, _ in held if p == 0),
        "design": design["key"] if design else None,
    }


def _next(walk: dict, w: dict, reached: dict, pending: list, designs: list, built: dict) -> tuple[str | None, str]:
    shoot = f"crissp/ux.sh --shoot {w['id']}"
    if reached["accepted"]:
        return None, "done"
    if reached["built"] and not (built.get("verdict") == "send-back" and w["shot_at"] <= built["at"]):
        return "you", "accept what was built, or send it back"
    if reached["approved"]:
        return "team", f"build it, then shoot it again: {shoot}"
    running = _running(w["rounds"]) or _running(w["proposals"])
    if running:
        return "team", f"the team is at it ({running})"
    if pending:
        return "you", f"decide {len(pending)} piece(s) of advice"
    if designs and not designs[-1].get("verdict"):
        return "you", f"judge design {designs[-1]['version']}"
    if not reached["seen"]:
        return "team", f"shoot it: {shoot}"
    if not reached["discussed"]:
        return "team", "ask the team for a round"
    return "team", "ask the team for a design"


def map_status(m: dict | None, statuses: dict[str, str]) -> dict[str, str]:
    """Per mapped screen, the status of the least advanced walk that looks at it; seen when none does."""
    out = {}
    for s in (m or {}).get("screens", []):
        held = [statuses[k] for k in s["walks"] if k in statuses]
        out[s["key"]] = min(held, key=STEPS.index) if held else "seen"
    return out


def review(conf: dict, walks: list[dict], verdicts: dict, m: dict | None) -> dict:
    """Every screen with its status, those that wait for the product owner first, and how far the product is."""
    order = {w["id"]: i for i, w in enumerate(walks)}
    screens = [screen(conf["walks"][w["id"]], w, verdicts) for w in walks]
    screens.sort(key=lambda s: (s["waits"] != "you", -s["must"], -s["step"], order[s["walk"]]))
    progress = {step: sum(1 for s in screens if s["status"] == step) for step in STEPS}
    return {
        "steps": list(STEPS),
        "screens": screens,
        "progress": progress,
        "total": len(screens),
        "waiting": sum(1 for s in screens if s["waits"] == "you"),
        "map": map_status(m, {s["walk"]: s["status"] for s in screens}),
    }


# ------------------------------------------------------------------------------------------------------- decide once


def theme(advice: dict) -> str:
    """What a piece of advice is about, as a key: its theme when the team gave one, else its title."""
    return "-".join(re.findall(r"[a-z0-9]+", str(advice.get("theme") or advice.get("title") or "").lower()))[:60]


def _advice(suite, conf: dict):
    """Every piece of advice of every finished round: (walk id, advice id, advice)."""
    for wid in conf["walks"]:
        for r in ux_team.versions(suite, "round", wid):
            for i, a in enumerate((r["result"] or {}).get("advice") or []):
                yield wid, f"{wid}/r{r['version']}/a{i}", a


def held(suite, conf: dict, verdicts: dict) -> dict:
    """Per piece of advice without a verdict of its own, the verdict higher up that holds for it."""
    out = {}
    for wid, aid, a in _advice(suite, conf):
        if aid in verdicts:
            continue
        up = [f"screen/{wid}", f"area/{area_of(conf['walks'][wid])}"] + ([f"rule/{a['rule']}"] if a.get("rule") else [])
        by = next((u for u in up if u in verdicts), None)
        if by:
            out[aid] = {"verdict": verdicts[by]["verdict"], "reason": verdicts[by].get("reason", ""), "by": by}
    return out


def proposed(suite, conf: dict, verdicts: dict, rules: list[dict]) -> list[dict]:
    """Agreed advice without a rule, on two screens or more under one theme: proposed as a rule (not when that rule is
    there already)."""
    groups: dict[str, list] = {}
    for wid, aid, a in _advice(suite, conf):
        if not a.get("rule") and (verdicts.get(aid) or {}).get("verdict") == "agree" and theme(a):
            groups.setdefault(theme(a), []).append((wid, aid, a))
    have = {r["id"] for r in rules}
    out = []
    for key, found in groups.items():
        walks = list(dict.fromkeys(w for w, _, _ in found))
        if len(walks) < 2 or key in have:
            continue
        first = found[0][2]
        out.append(
            {
                "id": f"proposed/{key}",
                "title": str(first.get("theme") or first.get("title")).strip(),
                "severity": min((a.get("priority") for _, _, a in found), key=lambda p: PRIORITY.get(p, 3)),
                "text": "\n".join(dict.fromkeys(str(a.get("detail") or a.get("title")).strip() for _, _, a in found)),
                "walks": walks,
                "advice": [i for _, i, _ in found],
                "verdict": verdicts.get(f"proposed/{key}"),
            }
        )
    return out
