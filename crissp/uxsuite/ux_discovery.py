"""Discovery (E7-F3-02): what a discovery round reads, and what a need becomes once the product owner approves it.

A discovery round (ux_team, kind "discovery", on the whole product) gets the mapped screens with their pictures; every
persona tries their jobs and says done, hard or impossible, and the moderator writes the needs: what the product is
missing. A need the product owner approves becomes a design request: a walk of its own, walks/need-<title>.json, with
the need as its brief (who needs it, for which jobs) and the screen where it would fit as its first page, and the first
design of that walk starts at once (or waits in the queue). A need approved twice keeps its one walk.
"""

from __future__ import annotations

import json

import ux_shoot
import ux_team
from ux_config import Suite


def screens_for_a_run(suite: Suite, m: dict) -> list[dict]:
    """The map's screens as a run reads them: each picture as a file it can open."""
    def file(url: str) -> str:
        return str(suite.results / url.removeprefix("/ux/results/"))
    return [{"key": s["key"], "title": s["title"], "area": s["area"], "gaps": s["gaps"],
             "pictures": [{"device": p["device"], "source": p["source"], "file": file(p["url"])} for p in s["shots"]]}
            for s in m["screens"]]


def brief(need: dict, names: dict[str, str]) -> str:
    """The design request's brief: the need in the moderator's words, then who needs it and for which jobs."""
    who = ", ".join(names.get(k, k) for k in need.get("personas") or [])
    jobs = "; ".join(need.get("jobs") or [])
    tail = (f"Who needs it: {who}." if who else "") + (f" For: {jobs}." if jobs else "")
    return str(need.get("detail") or need.get("title") or "").strip() + (f"\n{tail.strip()}" if tail else "")


def design_request(suite: Suite, conf: dict, need_id: str, need: dict) -> str:
    """The walk of an approved need: the one made before, or a new walks/need-<title>.json; its id."""
    made = next((w["id"] for w in conf["walks"].values() if w.get("need") == need_id), None)
    if made:
        return made
    base = "need-" + ux_shoot.slug(str(need.get("title") or "need"))[:40].rstrip("-")
    name, n = base, 1
    while (suite.here / "walks" / f"{name}.json").exists():
        n += 1
        name = f"{base}-{n}"
    start = next((s for s in need.get("screens") or [] if isinstance(s, str) and s.startswith("/")), "/")
    walk = {"title": str(need.get("title") or "A need from discovery").strip(), "need": need_id,
            "brief": brief(need, {p["key"]: p["name"] for p in conf["personas"]}),
            "steps": [{"do": "goto", "path": start}, {"do": "shot", "title": str(need.get("title") or "The screen")}]}
    (suite.here / "walks").mkdir(parents=True, exist_ok=True)
    (suite.here / "walks" / f"{name}.json").write_text(json.dumps(walk, ensure_ascii=False, indent=1) + "\n")
    return name


def approved(suite: Suite, conf: dict, need_id: str, need: dict) -> dict:
    """An approved need: its design request, and its first design started now or queued."""
    walk = design_request(suite, conf, need_id, need)
    conf = {**conf, "walks": {**conf["walks"]}}
    if walk not in conf["walks"]:
        import ux_config
        conf["walks"][walk] = ux_config.walk(suite.here / "walks" / f"{walk}.json")
    try:
        return {"walk": walk, **ux_team.request(suite, conf, "proposal", walk, "")}
    except ValueError as why:  # the team works on this request already: the request stands
        return {"walk": walk, "not_started": str(why)}
